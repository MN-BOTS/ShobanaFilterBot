import logging
import asyncio
import re

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

from database.ia_filterdb import Media, USE_MONGO
from info import ADMINS

logger = logging.getLogger(__name__)

BATCH_SIZE = 20
SLEEP_TIME = 2


@Client.on_message(filters.command("deletefiles") & filters.user(ADMINS))
async def deletemultiplefiles(bot: Client, message: Message):
    if message.chat.type != enums.ChatType.PRIVATE:
        return await message.reply_text(
            f"<b>Hey {message.from_user.mention}, this command won't work in groups. It only works in my PM!</b>",
            parse_mode=enums.ParseMode.HTML,
        )

    try:
        keyword = message.text.split(" ", 1)[1].strip()
        if not keyword:
            raise IndexError
    except IndexError:
        return await message.reply_text(
            f"<b>Hey {message.from_user.mention}, give me a keyword along with the command to delete files.</b>\n"
            "Usage: <code>/deletefiles &lt;keyword&gt;</code>\n"
            "Example: <code>/deletefiles unwanted_movie</code>",
            parse_mode=enums.ParseMode.HTML,
        )

    confirm_button = InlineKeyboardButton("Yes, Continue !", callback_data=f"confirm_delete_files#{keyword}")
    abort_button = InlineKeyboardButton("No, Abort operation !", callback_data="close_message")

    await message.reply_text(
        text=(
            f"<b>Are you sure? Do you want to continue deleting files with the keyword: '{keyword}'?\n\n"
            "Note: This is a destructive action and cannot be undone!</b>"
        ),
        reply_markup=InlineKeyboardMarkup([[confirm_button], [abort_button]]),
        parse_mode=enums.ParseMode.HTML,
        quote=True,
    )


@Client.on_callback_query(filters.regex(r'^confirm_delete_files#'))
async def confirm_and_delete_files_by_keyword(bot: Client, query: CallbackQuery):
    await query.answer()

    _, keyword = query.data.split("#", 1)

    # Build regex used for Mongo matching and count_documents
    raw_pattern = r'(\b|[\.\+\-_])' + re.escape(keyword) + r'(\b|[\.\+\-_])'
    regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    filter_query = {'file_name': regex}

    await query.message.edit_text(
        f"🔍 Searching for files containing <b>'{keyword}'</b> in their filenames...",
        parse_mode=enums.ParseMode.HTML,
    )

    # count_documents works for both Mongo (multi-shard aware) and SQL
    initial_count = await Media.count_documents(filter_query)
    if initial_count == 0:
        return await query.message.edit_text(
            f"❌ No files found with <b>'{keyword}'</b> in their filenames. Deletion aborted.",
            parse_mode=enums.ParseMode.HTML,
        )

    await query.message.edit_text(
        f"Found <code>{initial_count}</code> files containing <b>'{keyword}'</b>. Starting batch deletion...",
        parse_mode=enums.ParseMode.HTML,
    )

    deleted_count = 0

    if USE_MONGO:
        # ── Mongo path (single or multi-shard) ──────────────────────────────
        # Media.collection is MongoMergedCollection which fans out across all shards.
        # find() is async; we await it, then chain limit/to_list on the cursor.
        while True:
            cursor = await Media.collection.find(filter_query, {"_id": 1})
            docs = await cursor.limit(BATCH_SIZE).to_list(length=BATCH_SIZE)

            if not docs:
                break

            ids_to_delete = [doc["_id"] for doc in docs]
            # delete_many fans out across all shards automatically
            result = await Media.collection.delete_many({"_id": {"$in": ids_to_delete}})
            deleted_in_batch = result.deleted_count
            deleted_count += deleted_in_batch

            await query.message.edit_text(
                f"🗑️ Deleted <code>{deleted_in_batch}</code> in this batch. "
                f"Total: <code>{deleted_count}</code> / <code>{initial_count}</code>",
                parse_mode=enums.ParseMode.HTML,
            )

            if deleted_count >= initial_count or deleted_in_batch == 0:
                break

            await asyncio.sleep(SLEEP_TIME)

    else:
        # ── SQL (PostgreSQL) path ────────────────────────────────────────────
        # Use ILIKE for efficient server-side filtering instead of loading the
        # entire media table into memory on every batch iteration.
        from database.sql_store import store
        from sqlalchemy import text as sa_text

        sql_pattern = f"%{keyword}%"

        while True:
            # Fetch + delete inside one transaction per batch so no rows are
            # left behind if the loop is interrupted.
            deleted_in_batch = 0
            with store.begin() as conn:
                rows = conn.execute(
                    sa_text(
                        "SELECT file_id FROM media WHERE file_name ILIKE :pat LIMIT :lim"
                    ),
                    {"pat": sql_pattern, "lim": BATCH_SIZE},
                ).fetchall()

                if rows:
                    ids = [r[0] for r in rows]
                    conn.execute(
                        sa_text(
                            "DELETE FROM media WHERE file_id = ANY(:ids)"
                        ),
                        {"ids": ids},
                    )
                    deleted_in_batch = len(ids)

            if not deleted_in_batch:
                break

            deleted_count += deleted_in_batch

            await query.message.edit_text(
                f"🗑️ Deleted <code>{deleted_in_batch}</code> in this batch. "
                f"Total: <code>{deleted_count}</code> / <code>{initial_count}</code>",
                parse_mode=enums.ParseMode.HTML,
            )

            if deleted_count >= initial_count:
                break

            await asyncio.sleep(SLEEP_TIME)

    await query.message.edit_text(
        f"✅ Finished! Keyword: <b>'{keyword}'</b> — "
        f"Total files deleted: <code>{deleted_count}</code>",
        parse_mode=enums.ParseMode.HTML,
    )


@Client.on_callback_query(filters.regex(r'^close_message$'))
async def close_message(bot: Client, query: CallbackQuery):
    await query.answer()
    await query.message.delete()
