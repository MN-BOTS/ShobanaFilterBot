from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import asyncio
from database.users_chats_db import db
from info import ADMINS
from utils import broadcast_messages

MAX_CONCURRENT = 60
CHUNK_SIZE = 100
FAILED_BROADCASTS = {}

class BroadcastStats:
    def __init__(self):
        self.done = self.success = self.blocked = self.deleted = self.failed = 0

async def _send_one(sem, user_id, b_msg, stats):
    async with sem:
        for _ in range(3):
            try:
                pti, sh = await broadcast_messages(user_id, b_msg)
                stats.done += 1
                if pti:
                    stats.success += 1
                elif sh == "Blocked":
                    await db.delete_user(user_id); stats.blocked += 1
                elif sh == "Deleted":
                    await db.delete_user(user_id); stats.deleted += 1
                else:
                    stats.failed += 1; FAILED_BROADCASTS.setdefault("users", set()).add(user_id)
                return
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception:
                stats.done += 1; stats.failed += 1
                FAILED_BROADCASTS.setdefault("users", set()).add(user_id)
                return
        stats.done += 1; stats.failed += 1
        FAILED_BROADCASTS.setdefault("users", set()).add(user_id)

async def _send_group_one(sem, chat_id, b_msg, stats):
    async with sem:
        for _ in range(3):
            try:
                await b_msg.copy(chat_id=chat_id)
                stats.done += 1; stats.success += 1
                return
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception:
                await db.delete_chat(chat_id)
                stats.done += 1; stats.failed += 1
                return
        await db.delete_chat(chat_id)
        stats.done += 1; stats.failed += 1

@Client.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast(bot, message):
    b_msg = message.reply_to_message
    sts = await message.reply_text("⏳ Loading users…")
    users = await db.get_all_users()
    users = [u async for u in users] if hasattr(users, '__aiter__') else users
    stats, sem = BroadcastStats(), asyncio.Semaphore(MAX_CONCURRENT)
    FAILED_BROADCASTS["msg"] = b_msg
    tasks = [_send_one(sem, int(u['id']), b_msg, stats) for u in users]
    for i in range(0, len(tasks), CHUNK_SIZE):
        await asyncio.gather(*tasks[i:i+CHUNK_SIZE], return_exceptions=True)
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("Retry Failed (20)", callback_data="bc_retry_failed")]]) if FAILED_BROADCASTS.get("users") else None
    await sts.edit(f"✅ Broadcast done\nSuccess: {stats.success}\nFailed: {stats.failed}\nBlocked: {stats.blocked}\nDeleted: {stats.deleted}", reply_markup=btn)

@Client.on_callback_query(filters.regex("^bc_retry_failed$") & filters.user(ADMINS))
async def retry_failed(bot, query):
    failed = list(FAILED_BROADCASTS.get("users", set()))
    if not failed:
        return await query.answer("No failed users", show_alert=True)

    b_msg = FAILED_BROADCASTS.get("msg")
    sem = asyncio.Semaphore(20)
    ok = 0

    async def _retry_one(uid):
        nonlocal ok
        async with sem:
            for _ in range(3):
                try:
                    await b_msg.copy(chat_id=uid)
                    FAILED_BROADCASTS["users"].discard(uid)
                    ok += 1
                    return
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                except Exception:
                    return

    await asyncio.gather(*[_retry_one(uid) for uid in failed], return_exceptions=True)
    await query.answer(f"Retried {len(failed)} failed users with max concurrency 20. Success: {ok}", show_alert=True)

@Client.on_message(filters.command("grpbroadcast") & filters.user(ADMINS) & filters.reply)
async def grpbroadcast(bot, message):
    b_msg = message.reply_to_message
    sts = await message.reply_text("⏳ Loading groups…")
    chats = await db.get_all_chats()
    chats = [c async for c in chats] if hasattr(chats, '__aiter__') else chats
    stats, sem = BroadcastStats(), asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [_send_group_one(sem, int(c['id']), b_msg, stats) for c in chats]
    for i in range(0, len(tasks), CHUNK_SIZE):
        await asyncio.gather(*tasks[i:i+CHUNK_SIZE], return_exceptions=True)
    await sts.edit(f"✅ Group broadcast done\nSuccess: {stats.success}\nFailed: {stats.failed}\n(Removed failed chats from DB)")
