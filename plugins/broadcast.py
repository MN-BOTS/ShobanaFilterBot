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
MAX_CONCURRENT   = 50   # simultaneous Telegram API calls (safe ceiling)
BATCH_UPDATE_AT  = 200  # refresh status message every N completions
INTER_SEND_DELAY = 0.05 # tiny pause between acquiring semaphore slots (seconds)
# ────────────────────────────────────────────────────────────────────────────


# ── Shared mutable state with a lock to prevent race conditions ──────────────
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


# ── Per-user send with internal FloodWait retry ──────────────────────────────
async def _send_one(sem: asyncio.Semaphore, user_id: int, b_msg, stats: BroadcastStats):
    async with sem:
        await asyncio.sleep(INTER_SEND_DELAY)
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
                await asyncio.sleep(e.value + 5)
                retries += 1
            except Exception:
                await stats.record("failed")
                return
        await stats.record("failed")


# ── /broadcast ───────────────────────────────────────────────────────────────
@Client.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast(bot, message):
    b_msg       = message.reply_to_message
    sts         = await message.reply_text("⏳ Preparing broadcast…")
    start_time  = time.time()
    total_users = await db.total_users_count()
    stats       = BroadcastStats()
    sem         = asyncio.Semaphore(MAX_CONCURRENT)

    def _progress() -> str:
        elapsed = datetime.timedelta(seconds=int(time.time() - start_time))
        return (
            f"📡 **Broadcast in progress…**\n\n"
            f"👥 Total  : `{total_users}`\n"
            f"✅ Done   : `{stats.done}` / `{total_users}`\n"
            f"✔️ Success : `{stats.success}`\n"
            f"🚫 Blocked : `{stats.blocked}`\n"
            f"🗑 Deleted : `{stats.deleted}`\n"
            f"❌ Failed  : `{stats.failed}`\n"
            f"⏱ Elapsed : `{elapsed}`"
        )

    # ── Build task list (fix: await first, then iterate) ────────────────────
    all_tasks = []
    try:
        # Case 1: get_all_users() returns an async generator after await
        async for user in await db.get_all_users():
            uid = int(user['id'])
            all_tasks.append(_send_one(sem, uid, b_msg, stats))
    except TypeError:
        # Case 2: get_all_users() returns a plain list after await
        users = await db.get_all_users()
        for user in users:
            uid = int(user['id'])
            all_tasks.append(_send_one(sem, uid, b_msg, stats))

    # ── Run all tasks, updating status periodically ──────────────────────────
    async def _run_with_updates():
        pending = [asyncio.ensure_future(t) for t in all_tasks]
        last_update = 0
        while pending:
            await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED,
                timeout=2.0
            )
            pending = [f for f in pending if not f.done()]

            if stats.done - last_update >= BATCH_UPDATE_AT:
                last_update = stats.done
                try:
                    await sts.edit(_progress())
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                except Exception:
                    pass  # status edit failure must never kill the broadcast

    await _run_with_updates()

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


# ── Per-group send with internal FloodWait retry ─────────────────────────────
async def _send_group_one(sem: asyncio.Semaphore, chat_id: int, b_msg, stats: BroadcastStats):
    async with sem:
        await asyncio.sleep(INTER_SEND_DELAY)
        retries = 0
        while retries < 3:
            try:
                await b_msg.copy(chat_id=chat_id)
                await stats.record("success")
                return
            except FloodWait as e:
                await asyncio.sleep(e.value + 5)
                retries += 1
            except Exception:
                await stats.record("failed")
                return
        await stats.record("failed")


# ── /grpbroadcast ─────────────────────────────────────────────────────────────
@Client.on_message(filters.command("grpbroadcast") & filters.user(ADMINS) & filters.reply)
async def grpbroadcast(bot, message):
    b_msg       = message.reply_to_message
    sts         = await message.reply_text("⏳ Preparing group broadcast…")
    start_time  = time.time()
    total_chats = await db.total_chat_count()
    stats       = BroadcastStats()
    sem         = asyncio.Semaphore(MAX_CONCURRENT)

    def _progress() -> str:
        elapsed = datetime.timedelta(seconds=int(time.time() - start_time))
        return (
            f"📡 **Group Broadcast in progress…**\n\n"
            f"💬 Total  : `{total_chats}`\n"
            f"✅ Done   : `{stats.done}` / `{total_chats}`\n"
            f"✔️ Success : `{stats.success}`\n"
            f"❌ Failed  : `{stats.failed}`\n"
            f"⏱ Elapsed : `{elapsed}`"
        )

    # ── Build task list (fix: await first, then iterate) ────────────────────
    all_tasks = []
    try:
        # Case 1: get_all_chats() returns an async generator after await
        async for chat in await db.get_all_chats():
            cid = int(chat['id'])
            all_tasks.append(_send_group_one(sem, cid, b_msg, stats))
    except TypeError:
        # Case 2: get_all_chats() returns a plain list after await
        chats = await db.get_all_chats()
        for chat in chats:
            cid = int(chat['id'])
            all_tasks.append(_send_group_one(sem, cid, b_msg, stats))

    # ── Run all tasks, updating status periodically ──────────────────────────
    async def _run_with_updates():
        pending = [asyncio.ensure_future(t) for t in all_tasks]
        last_update = 0
        while pending:
            await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED,
                timeout=2.0
            )
            pending = [f for f in pending if not f.done()]

            if stats.done - last_update >= BATCH_UPDATE_AT:
                last_update = stats.done
                try:
                    await sts.edit(_progress())
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                except Exception:
                    pass

    await _run_with_updates()

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
