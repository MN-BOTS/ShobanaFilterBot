import logging
import asyncio
import random
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import (
    ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
)
from info import ADMINS
from info import INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
lock = asyncio.Lock()

# ─── tunables ────────────────────────────────────────────────────────────────
BATCH_SIZE       = 1000   # messages fetched per "big batch"
TG_CHUNK         = 200    # Telegram API max IDs per get_messages call
PROGRESS_EVERY   = 1000   # update status message every N fetched
SLEEP_MIN        = 3      # random sleep between batches – minimum seconds
SLEEP_MAX        = 7      # random sleep between batches – maximum seconds
# ─────────────────────────────────────────────────────────────────────────────

CANCEL_MARKUP = InlineKeyboardMarkup(
    [[InlineKeyboardButton('Cancel', callback_data='index_cancel')]]
)


# ─── helpers ─────────────────────────────────────────────────────────────────

def _status_text(current, total_files, duplicate, deleted, no_media, unsupported, errors):
    return (
        f"Total messages fetched: <code>{current}</code>\n"
        f"Total messages saved: <code>{total_files}</code>\n"
        f"Duplicate Files Skipped: <code>{duplicate}</code>\n"
        f"Deleted Messages Skipped: <code>{deleted}</code>\n"
        f"Non-Media messages skipped: <code>{no_media + unsupported}</code> "
        f"(Unsupported Media – <code>{unsupported}</code>)\n"
        f"Errors Occurred: <code>{errors}</code>"
    )


async def _safe_edit(msg, text, reply_markup=None):
    """Edit a message, silently ignore MessageNotModified."""
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except Exception:
        pass


async def _flood_safe(coro):
    """Await *coro*, retrying after any FloodWait automatically."""
    while True:
        try:
            return await coro
        except FloodWait as fw:
            logger.warning("FloodWait: sleeping %s s", fw.value)
            await asyncio.sleep(fw.value + 1)


# ─── batch-fetch  ─────────────────────────────────────────────────────────────

async def _fetch_chunk(bot, chat, msg_ids: list):
    """
    Fetch up to TG_CHUNK message IDs in one API call with FloodWait handling.
    Returns list[Message].
    """
    return await _flood_safe(bot.get_messages(chat, msg_ids))


async def _process_batch(bot, chat, batch_ids: list):
    """
    Split *batch_ids* into TG_CHUNK groups, fetch concurrently, return flat
    list of Message objects in original order.
    """
    chunks = [batch_ids[i:i + TG_CHUNK] for i in range(0, len(batch_ids), TG_CHUNK)]
    results = await asyncio.gather(*[_fetch_chunk(bot, chat, c) for c in chunks])
    # flatten while preserving order
    messages = []
    for group in results:
        if isinstance(group, list):
            messages.extend(group)
        else:
            messages.append(group)
    return messages


async def _save_media_batch(messages):
    """
    Filter eligible messages, save all concurrently, return counters dict.
    """
    counters = dict(total_files=0, duplicate=0, errors=0,
                    deleted=0, no_media=0, unsupported=0)

    eligible = []
    for message in messages:
        if message is None or message.empty:
            counters['deleted'] += 1
            continue
        if not message.media:
            counters['no_media'] += 1
            continue
        if message.media not in (
            enums.MessageMediaType.VIDEO,
            enums.MessageMediaType.AUDIO,
            enums.MessageMediaType.DOCUMENT,
        ):
            counters['unsupported'] += 1
            continue
        media = getattr(message, message.media.value, None)
        if not media:
            counters['unsupported'] += 1
            continue
        media.file_type = message.media.value
        media.caption  = message.caption
        eligible.append(media)

    if not eligible:
        return counters

    save_results = await asyncio.gather(
        *[save_file(m) for m in eligible],
        return_exceptions=True
    )

    for res in save_results:
        if isinstance(res, Exception):
            logger.exception(res)
            counters['errors'] += 1
        else:
            saved, code = res
            if saved:
                counters['total_files'] += 1
            elif code == 0:
                counters['duplicate'] += 1
            elif code == 2:
                counters['errors'] += 1

    return counters


# ─── main indexing loop ───────────────────────────────────────────────────────

async def index_files_to_db(lst_msg_id: int, chat, msg, bot):
    total_files = 0
    duplicate   = 0
    errors      = 0
    deleted     = 0
    no_media    = 0
    unsupported = 0

    async with lock:
        try:
            current    = temp.CURRENT
            temp.CANCEL = False
            start_id   = max(1, temp.CURRENT + 1)

            # Build descending range: lst_msg_id … start_id
            all_ids = list(range(lst_msg_id, start_id - 1, -1))
            logger.info("Indexing %d messages from %s (start=%d end=%d)",
                        len(all_ids), chat, start_id, lst_msg_id)

            big_batches = [
                all_ids[i:i + BATCH_SIZE]
                for i in range(0, len(all_ids), BATCH_SIZE)
            ]

            for batch_num, batch_ids in enumerate(big_batches):
                if temp.CANCEL:
                    await _safe_edit(
                        msg,
                        "✅ <b>Indexing Cancelled!</b>\n\n" +
                        _status_text(current, total_files, duplicate,
                                     deleted, no_media, unsupported, errors)
                    )
                    return

                # fetch all messages in this big batch (chunked internally)
                messages = await _process_batch(bot, chat, batch_ids)

                # save concurrently
                c = await _save_media_batch(messages)
                total_files += c['total_files']
                duplicate   += c['duplicate']
                errors      += c['errors']
                deleted     += c['deleted']
                no_media    += c['no_media']
                unsupported += c['unsupported']
                current     += len(batch_ids)

                # update progress
                await _safe_edit(
                    msg,
                    f"⚡ <b>Batch {batch_num + 1}/{len(big_batches)}</b>\n\n" +
                    _status_text(current, total_files, duplicate,
                                 deleted, no_media, unsupported, errors),
                    reply_markup=CANCEL_MARKUP
                )

                # random sleep between batches (skip after last one)
                if batch_num < len(big_batches) - 1:
                    sleep_time = random.uniform(SLEEP_MIN, SLEEP_MAX)
                    logger.info("Batch %d done – sleeping %.1fs before next batch",
                                batch_num + 1, sleep_time)
                    await asyncio.sleep(sleep_time)

        except FloodWait as fw:
            # top-level safety net – inner calls handle their own FloodWaits
            logger.warning("Top-level FloodWait %s s – waiting and will NOT resume automatically here", fw.value)
            await msg.edit(
                f"⚠️ FloodWait hit ({fw.value}s). Indexing paused.\n\n" +
                _status_text(current, total_files, duplicate,
                             deleted, no_media, unsupported, errors)
            )
            await asyncio.sleep(fw.value + 1)
            # re-raise so lock is released cleanly; admin can restart
            raise

        except Exception as e:
            logger.exception(e)
            await msg.edit(f'❌ Error: <code>{e}</code>')
            return

    # success (outside lock so edit is not blocked)
    await _safe_edit(
        msg,
        "✅ <b>Indexing Complete!</b>\n\n" +
        _status_text(current, total_files, duplicate,
                     deleted, no_media, unsupported, errors)
    )


# ─── callback: accept / reject / cancel ──────────────────────────────────────

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing")

    _, raju, chat, lst_msg_id, from_user = query.data.split("#")

    if raju == 'reject':
        await query.message.delete()
        await bot.send_message(
            int(from_user),
            f'Your Submission for indexing {chat} has been declined by our moderators.',
            reply_to_message_id=int(lst_msg_id)
        )
        return

    if lock.locked():
        return await query.answer('Wait until previous process completes.', show_alert=True)

    msg = query.message
    await query.answer('Processing…⏳', show_alert=True)

    if int(from_user) not in ADMINS:
        await bot.send_message(
            int(from_user),
            f'Your Submission for indexing {chat} has been accepted by our moderators and will be added soon.',
            reply_to_message_id=int(lst_msg_id)
        )

    await msg.edit(
        "⚡ Starting Indexing…",
        reply_markup=CANCEL_MARKUP
    )

    try:
        chat = int(chat)
    except Exception:
        pass

    await index_files_to_db(int(lst_msg_id), chat, msg, bot)


# ─── handler: submit link / forward for indexing ─────────────────────────────

@Client.on_message(
    (
        filters.forwarded |
        (filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$") & filters.text)
    ) & filters.private & filters.incoming
)
async def send_for_index(bot, message):
    if message.text:
        regex = re.compile(
            r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$"
        )
        match = regex.match(message.text)
        if not match:
            return await message.reply('Invalid link')
        chat_id      = match.group(4)
        last_msg_id  = int(match.group(5))
        if chat_id.isnumeric():
            chat_id = int("-100" + chat_id)
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id     = message.forward_from_chat.username or message.forward_from_chat.id
    else:
        return

    try:
        await bot.get_chat(chat_id)
    except ChannelInvalid:
        return await message.reply('Private channel/group – make me an admin there to index files.')
    except (UsernameInvalid, UsernameNotModified):
        return await message.reply('Invalid link specified.')
    except Exception as e:
        logger.exception(e)
        return await message.reply(f'Error – {e}')

    try:
        k = await bot.get_messages(chat_id, last_msg_id)
    except Exception:
        return await message.reply('Make sure I am an admin in the channel/group.')
    if k.empty:
        return await message.reply('This may be a group where I am not an admin.')

    if message.from_user.id in ADMINS:
        buttons = [
            [InlineKeyboardButton('Yes', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')],
            [InlineKeyboardButton('Close', callback_data='close_data')],
        ]
        return await message.reply(
            f'Index this chat?\n\nChat ID/Username: <code>{chat_id}</code>\nLast Message ID: <code>{last_msg_id}</code>',
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    if isinstance(chat_id, int):
        try:
            link = (await bot.create_chat_invite_link(chat_id)).invite_link
        except ChatAdminRequired:
            return await message.reply('Make sure I am an admin with invite permissions.')
    else:
        link = f"@{message.forward_from_chat.username}"

    buttons = [
        [InlineKeyboardButton('Accept Index', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')],
        [InlineKeyboardButton('Reject Index', callback_data=f'index#reject#{chat_id}#{message.id}#{message.from_user.id}')],
    ]
    await bot.send_message(
        LOG_CHANNEL,
        f'#IndexRequest\n\nBy: {message.from_user.mention} (<code>{message.from_user.id}</code>)\n'
        f'Chat – <code>{chat_id}</code>\nLast Msg ID – <code>{last_msg_id}</code>\nInvite – {link}',
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await message.reply('Thanks! Wait for our moderators to verify.')


# ─── command: /setskip ───────────────────────────────────────────────────────

@Client.on_message(filters.command('setskip') & filters.user(ADMINS))
async def set_skip_number(bot, message):
    parts = message.text.split()
    if len(parts) < 2:
        return await message.reply('Usage: /setskip <number>')
    try:
        skip = int(parts[1])
    except ValueError:
        return await message.reply('Skip number must be an integer.')
    temp.CURRENT = skip
    await message.reply(f'SKIP set to <code>{skip}</code>')
