import logging
import asyncio
import time
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
BATCH_SIZE      = 5000    # IDs enqueued per producer iteration
TG_CHUNK        = 200     # Telegram API hard max per get_messages call
FETCH_WORKERS   = 6       # high-speed concurrent get_messages fetch workers
SAVE_WORKERS    = 12      # higher concurrent save_file calls for faster indexing
PROGRESS_EVERY  = 60.0    # seconds between status-message edits
QUEUE_MAXSIZE   = 10      # max pending batches between producer and consumer
# ─────────────────────────────────────────────────────────────────────────────

CANCEL_MARKUP = InlineKeyboardMarkup(
    [[InlineKeyboardButton('Cancel', callback_data='index_cancel')]]
)

MEDIA_TYPES = (
    enums.MessageMediaType.VIDEO,
    enums.MessageMediaType.AUDIO,
    enums.MessageMediaType.DOCUMENT,
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
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except Exception:
        pass


async def _flood_safe(coro_fn, _max_retries: int = 10, status_msg=None):
    """
    Retry a coroutine *factory* (callable that returns a new coroutine each
    time it is called) transparently on:
      • FloodWait  – edit status_msg with countdown, sleep, then auto-resume
      • OSError / ConnectionError (Connection lost, etc.) – exponential backoff

    ⚠️  IMPORTANT: pass a callable, NOT an already-created coroutine.
        ✅  _flood_safe(lambda: bot.get_messages(chat, ids))
        ❌  _flood_safe(bot.get_messages(chat, ids))   ← causes "cannot reuse
                                                          already awaited coroutine"
    """
    attempt = 0
    while True:
        try:
            # Call the factory to get a *fresh* coroutine on every attempt.
            return await coro_fn()
        except FloodWait as fw:
            wait_sec = fw.value + 1
            logger.warning("FloodWait – sleeping %ss", wait_sec)
            if status_msg is not None:
                await _safe_edit(
                    status_msg,
                    f"⏳ <b>FloodWait!</b>\n\n"
                    f"Telegram asked us to slow down.\n"
                    f"Sleeping <code>{wait_sec}s</code> – indexing will "
                    f"<b>resume automatically</b> afterwards."
                )
            await asyncio.sleep(wait_sec)
            if status_msg is not None:
                await _safe_edit(
                    status_msg,
                    "⚡ <b>Resuming indexing…</b>\n\nFloodWait is over.",
                )
            # Reset attempt counter after a FloodWait – the connection is fine.
            attempt = 0
        except (OSError, ConnectionError, asyncio.TimeoutError) as e:
            attempt += 1
            if attempt > _max_retries:
                logger.error("Giving up after %d retries: %s", _max_retries, e)
                raise
            delay = min(2 ** attempt + random.uniform(0, 1), 60)
            logger.warning(
                "Connection error (%s) – retry %d/%d in %.1fs",
                e, attempt, _max_retries, delay
            )
            await asyncio.sleep(delay)


# ─── stage 1 : producer  (fetch) ─────────────────────────────────────────────

async def _fetch_worker(bot, chat, id_queue: asyncio.Queue,
                        msg_queue: asyncio.Queue, sem: asyncio.Semaphore,
                        status_msg=None):
    """
    Pull a chunk of IDs from *id_queue*, fetch the messages, push the list
    onto *msg_queue*. Runs FETCH_WORKERS copies concurrently.
    status_msg is the Telegram message used to show FloodWait notices.
    """
    while True:
        chunk_ids = await id_queue.get()
        if chunk_ids is None:          # sentinel
            id_queue.task_done()
            await msg_queue.put(None)  # forward sentinel to consumer
            return
        try:
            async with sem:
                # ── FIX: pass a lambda so _flood_safe can create a *new*
                #    coroutine on every retry attempt.  Passing the coroutine
                #    object directly caused "cannot reuse already awaited
                #    coroutine" because a coroutine is exhausted after the
                #    first await, even when it raises an exception. ──────────
                messages = await _flood_safe(
                    lambda ids=chunk_ids: bot.get_messages(chat, ids),
                    status_msg=status_msg,
                )
            if not isinstance(messages, list):
                messages = [messages]
            await msg_queue.put(messages)
        except (OSError, ConnectionError, asyncio.TimeoutError) as e:
            # _flood_safe exhausted retries – log and skip this chunk rather
            # than crashing the whole worker.
            logger.error("Fetch permanently failed for chunk (ids %s…): %s",
                         chunk_ids[:3], e)
            await msg_queue.put([])    # push empty so consumer doesn't stall
        except Exception as e:
            logger.exception("Fetch error: %s", e)
            await msg_queue.put([])    # push empty so consumer doesn't stall
        finally:
            id_queue.task_done()


# ─── stage 2 : consumer  (save) ──────────────────────────────────────────────

async def _classify(message):
    """Return (media_object | None, counter_key)."""
    if message is None or message.empty:
        return None, 'deleted'
    if not message.media:
        return None, 'no_media'
    if message.media not in MEDIA_TYPES:
        return None, 'unsupported'
    media = getattr(message, message.media.value, None)
    if not media:
        return None, 'unsupported'
    media.file_type = message.media.value
    media.caption   = message.caption
    return media, None


async def _save_concurrently(eligible):
    """
    Save a list of media objects with SAVE_WORKERS concurrency.
    Compatible with both MongoDB (motor) and PostgreSQL (asyncpg / SQLAlchemy
    async) backends – save_file must return (saved: bool, code: int) where:
        saved=True          → new record written
        saved=False, code=0 → duplicate
        saved=False, code=2 → error
    """
    sem = asyncio.Semaphore(SAVE_WORKERS)

    async def _one(media):
        async with sem:
            try:
                return await save_file(media)
            except Exception as exc:
                # Catch DB-level exceptions (MotorError, asyncpg exceptions,
                # SQLAlchemy exceptions, etc.) uniformly.
                logger.exception("save_file raised unexpectedly: %s", exc)
                return exc   # treat as exception result in gather

    results = await asyncio.gather(*[_one(m) for m in eligible],
                                   return_exceptions=True)
    total_files = duplicate = errors = 0
    for res in results:
        if isinstance(res, Exception):
            errors += 1
        else:
            saved, code = res
            if saved:
                total_files += 1
            elif code == 0:
                duplicate += 1
            elif code == 2:
                errors += 1
    return total_files, duplicate, errors


# ─── main indexing loop ───────────────────────────────────────────────────────

async def index_files_to_db(lst_msg_id: int, chat, msg, bot):
    """
    Fastest possible indexing:
      • Producer: FETCH_WORKERS goroutines pump get_messages concurrently.
      • Consumer: main loop drains msg_queue and saves in bulk.
      • Progress: updated on a wall-clock timer, never blocking the hot path.
    Works with both MongoDB (motor) and PostgreSQL (asyncpg/SQLAlchemy) via
    the save_file abstraction in database/ia_filterdb.
    """
    total_files = duplicate = errors = deleted = no_media = unsupported = 0

    async with lock:
        try:
            temp.CANCEL = False
            start_id    = max(1, temp.CURRENT + 1)
            current     = temp.CURRENT

            all_ids   = list(range(lst_msg_id, start_id - 1, -1))
            total_ids = len(all_ids)
            logger.info("Indexing %d messages from %s (ids %d→%d)",
                        total_ids, chat, lst_msg_id, start_id)

            # ── queues ────────────────────────────────────────────────────────
            id_queue  = asyncio.Queue(maxsize=QUEUE_MAXSIZE * FETCH_WORKERS)
            msg_queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
            sem       = asyncio.Semaphore(FETCH_WORKERS)

            # ── start fetch workers ───────────────────────────────────────────
            workers = [
                asyncio.create_task(
                    _fetch_worker(bot, chat, id_queue, msg_queue, sem,
                                  status_msg=msg)
                )
                for _ in range(FETCH_WORKERS)
            ]

            # ── enqueue all IDs in TG_CHUNK slices ───────────────────────────
            async def _enqueue():
                for i in range(0, total_ids, TG_CHUNK):
                    await id_queue.put(all_ids[i:i + TG_CHUNK])
                # send one sentinel per worker
                for _ in range(FETCH_WORKERS):
                    await id_queue.put(None)

            enqueue_task = asyncio.create_task(_enqueue())

            # ── consume ───────────────────────────────────────────────────────
            last_edit    = time.monotonic()
            done_workers = 0

            while done_workers < FETCH_WORKERS:
                if temp.CANCEL:
                    enqueue_task.cancel()
                    for w in workers:
                        w.cancel()
                    await _safe_edit(
                        msg,
                        "✅ <b>Indexing Cancelled!</b>\n\n" +
                        _status_text(current, total_files, duplicate,
                                     deleted, no_media, unsupported, errors)
                    )
                    return

                try:
                    batch = await asyncio.wait_for(msg_queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue

                if batch is None:           # one worker finished
                    done_workers += 1
                    continue

                # classify
                eligible = []
                for message in batch:
                    media, key = await _classify(message)
                    if media:
                        eligible.append(media)
                    elif key == 'deleted':
                        deleted     += 1
                    elif key == 'no_media':
                        no_media    += 1
                    else:
                        unsupported += 1

                current += len(batch)

                # save
                if eligible:
                    tf, dup, err = await _save_concurrently(eligible)
                    total_files += tf
                    duplicate   += dup
                    errors      += err

                # progress (timer-gated)
                now = time.monotonic()
                if now - last_edit >= PROGRESS_EVERY:
                    pct = int(current / max(total_ids, 1) * 100)
                    await _safe_edit(
                        msg,
                        f"⚡ <b>Indexing… {pct}%</b>  "
                        f"(<code>{current}</code>/<code>{total_ids}</code>)\n\n" +
                        _status_text(current, total_files, duplicate,
                                     deleted, no_media, unsupported, errors),
                        reply_markup=CANCEL_MARKUP
                    )
                    last_edit = now

            await enqueue_task          # make sure enqueuer finished cleanly
            await asyncio.gather(*workers, return_exceptions=True)

        except Exception as e:
            logger.exception(e)
            await msg.edit(f'❌ Error: <code>{e}</code>')
            return

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

    await msg.edit("⚡ Starting Indexing…", reply_markup=CANCEL_MARKUP)

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
        chat_id     = match.group(4)
        last_msg_id = int(match.group(5))
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
