#  @MrMNTG @MusammilN
# please give credits https://github.com/MN-BOTS/ShobanaFilterBot

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
import datetime
import time
import asyncio
from database.users_chats_db import db
from info import ADMINS
from utils import broadcast_messages

# ── Tuning ──────────────────────────────────────────────────────────────────
MAX_CONCURRENT  = 150  # ⬆ raised: Telegram allows ~30 msg/sec per bot session
CHUNK_SIZE      = 150  # process this many tasks per gather round
BATCH_UPDATE_AT = 500  # update status every N sends (less edits = less flood)
# ────────────────────────────────────────────────────────────────────────────


class BroadcastStats:
    def __init__(self):
        self.lock    = asyncio.Lock()
        self.done    = 0
        self.success = 0
        self.blocked = 0
        self.deleted = 0
        self.failed  = 0

    async def record(self, result: str):
        async with self.lock:
            self.done += 1
            if result == "success":
                self.success += 1
            elif result == "blocked":
                self.blocked += 1
            elif result == "deleted":
                self.deleted += 1
            else:
                self.failed += 1


async def _send_one(sem: asyncio.Semaphore, user_id: int, b_msg, stats: BroadcastStats):
    async with sem:
        retries = 0
        while retries < 3:
            try:
                pti, sh = await broadcast_messages(user_id, b_msg)
                if pti:
                    await stats.record("success")
                elif sh == "Blocked":
                    await db.delete_user(user_id)
                    await stats.record("blocked")
                elif sh == "Deleted":
                    await db.delete_user(user_id)
                    await stats.record("deleted")
                else:
                    await stats.record("failed")
                return
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
                retries += 1
            except Exception:
                await stats.record("failed")
                return
        await stats.record("failed")


async def _get_all(db_call):
    """Handles both async-generator and list return types."""
    try:
        result = await db_call()
        if hasattr(result, '__aiter__'):
            return [item async for item in result]
        return result
    except TypeError:
        items = []
        async for item in db_call():
            items.append(item)
        return items


async def _run_chunked(all_tasks, sts, stats, total, start_time, progress_fn):
    """
    Runs tasks in CHUNK_SIZE batches using gather().
    Much faster than asyncio.wait(FIRST_COMPLETED) — no per-task overhead.
    """
    last_update = 0
    for i in range(0, len(all_tasks), CHUNK_SIZE):
        chunk = all_tasks[i:i + CHUNK_SIZE]
        await asyncio.gather(*chunk, return_exceptions=True)

        if stats.done - last_update >= BATCH_UPDATE_AT:
            last_update = stats.done
            try:
                await sts.edit(progress_fn())
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                pass


# ── /broadcast ───────────────────────────────────────────────────────────────
@Client.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast(bot, message):
    b_msg       = message.reply_to_message
    sts         = await message.reply_text("⏳ Loading users…")
    start_time  = time.time()
    total_users = await db.total_users_count()
    stats       = BroadcastStats()
    sem         = asyncio.Semaphore(MAX_CONCURRENT)

    def _progress():
        elapsed = datetime.timedelta(seconds=int(time.time() - start_time))
        pct = round((stats.done / total_users) * 100) if total_users else 0
        bar = "▓" * (pct // 10) + "░" * (10 - pct // 10)
        return (
            f"📡 **Broadcast in progress…**\n\n"
            f"[{bar}] {pct}%\n\n"
            f"👥 Total   : `{total_users}`\n"
            f"✅ Done    : `{stats.done}` / `{total_users}`\n"
            f"✔️ Success  : `{stats.success}`\n"
            f"🚫 Blocked  : `{stats.blocked}`\n"
            f"🗑 Deleted  : `{stats.deleted}`\n"
            f"❌ Failed   : `{stats.failed}`\n"
            f"⏱ Elapsed  : `{elapsed}`"
        )

    users = await _get_all(db.get_all_users)
    await sts.edit(f"⏳ Loaded `{len(users)}` users. Starting broadcast…")

    all_tasks = [
        _send_one(sem, int(u['id']), b_msg, stats)
        for u in users
    ]

    await _run_chunked(all_tasks, sts, stats, total_users, start_time, _progress)

    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
    await sts.edit(
        f"✅ **Broadcast Completed!**\n\n"
        f"⏱ Time taken  : `{time_taken}`\n"
        f"👥 Total users : `{total_users}`\n"
        f"✔️ Success  : `{stats.success}`\n"
        f"🚫 Blocked  : `{stats.blocked}`\n"
        f"🗑 Deleted  : `{stats.deleted}`\n"
        f"❌ Failed   : `{stats.failed}`"
    )


# ── /grpbroadcast ─────────────────────────────────────────────────────────────
async def _send_group_one(sem: asyncio.Semaphore, chat_id: int, b_msg, stats: BroadcastStats):
    async with sem:
        retries = 0
        while retries < 3:
            try:
                await b_msg.copy(chat_id=chat_id)
                await stats.record("success")
                return
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
                retries += 1
            except Exception:
                await stats.record("failed")
                return
        await stats.record("failed")


@Client.on_message(filters.command("grpbroadcast") & filters.user(ADMINS) & filters.reply)
async def grpbroadcast(bot, message):
    b_msg       = message.reply_to_message
    sts         = await message.reply_text("⏳ Loading groups…")
    start_time  = time.time()
    total_chats = await db.total_chat_count()
    stats       = BroadcastStats()
    sem         = asyncio.Semaphore(MAX_CONCURRENT)

    def _progress():
        elapsed = datetime.timedelta(seconds=int(time.time() - start_time))
        pct = round((stats.done / total_chats) * 100) if total_chats else 0
        bar = "▓" * (pct // 10) + "░" * (10 - pct // 10)
        return (
            f"📡 **Group Broadcast in progress…**\n\n"
            f"[{bar}] {pct}%\n\n"
            f"💬 Total   : `{total_chats}`\n"
            f"✅ Done    : `{stats.done}` / `{total_chats}`\n"
            f"✔️ Success  : `{stats.success}`\n"
            f"❌ Failed   : `{stats.failed}`\n"
            f"⏱ Elapsed  : `{elapsed}`"
        )

    chats = await _get_all(db.get_all_chats)
    await sts.edit(f"⏳ Loaded `{len(chats)}` groups. Starting broadcast…")

    all_tasks = [
        _send_group_one(sem, int(c['id']), b_msg, stats)
        for c in chats
    ]

    await _run_chunked(all_tasks, sts, stats, total_chats, start_time, _progress)

    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
    await sts.edit(
        f"✅ **Group Broadcast Completed!**\n\n"
        f"⏱ Time taken   : `{time_taken}`\n"
        f"💬 Total groups : `{total_chats}`\n"
        f"✔️ Success  : `{stats.success}`\n"
        f"❌ Failed   : `{stats.failed}`"
    )

#  @MrMNTG @MusammilN
# please give credits https://github.com/MN-BOTS/ShobanaFilterBot
