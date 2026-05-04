from pyrogram import Client, filters
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, PeerIdInvalid
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
from database.users_chats_db import db
from info import ADMINS
from utils import broadcast_messages

MAX_CONCURRENT = 60
CHUNK_SIZE = 100

# Central store — one entry per active broadcast
# Keys: "msg", "users" (set of failed ids), "stats_text" (last summary line)
BC = {}


# ─────────────────────────── helpers ────────────────────────────

def _make_btn(failed_ids: set):
    """Return retry button with live count, or None if nothing failed."""
    if not failed_ids:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            f"🔁 Retry Failed ({len(failed_ids)})",
            callback_data="bc_retry_failed"
        )]]
    )


def _summary(stats: dict, extra: str = "") -> str:
    lines = [
        "📊 **Broadcast Report**",
        f"✅ Success : `{stats['success']}`",
        f"❌ Failed  : `{stats['failed']}`",
        f"🚫 Blocked : `{stats['blocked']}`",
        f"🗑 Deleted : `{stats['deleted']}`",
    ]
    if extra:
        lines.append(extra)
    return "\n".join(lines)


async def _safe_edit(msg, text, reply_markup=None):
    """Edit a message, silently ignoring 'message not modified' errors."""
    try:
        await msg.edit(text, reply_markup=reply_markup)
    except Exception:
        pass


# ─────────────── core sender (never-fail on FloodWait) ──────────

async def _send_one(sem, user_id, b_msg, stats: dict):
    """
    Send to one user.
    - Retries FloodWait indefinitely (never-fail).
    - Categorises permanent errors (Blocked / Deleted / other).
    - Updates shared stats dict in place.
    """
    async with sem:
        while True:                         # infinite loop — only FloodWait loops
            try:
                pti, sh = await broadcast_messages(user_id, b_msg)
                stats["done"] += 1
                if pti:
                    stats["success"] += 1
                elif sh == "Blocked":
                    await db.delete_user(user_id)
                    stats["blocked"] += 1
                elif sh == "Deleted":
                    await db.delete_user(user_id)
                    stats["deleted"] += 1
                else:
                    stats["failed"] += 1
                    BC.setdefault("users", set()).add(user_id)
                return

            except FloodWait as e:
                # Wait exactly as long as Telegram demands, then retry
                await asyncio.sleep(e.value + 1)

            except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid) as e:
                # Permanent — clean up DB and move on
                stats["done"] += 1
                await db.delete_user(user_id)
                if isinstance(e, UserIsBlocked):
                    stats["blocked"] += 1
                else:
                    stats["deleted"] += 1
                return

            except Exception:
                stats["done"] += 1
                stats["failed"] += 1
                BC.setdefault("users", set()).add(user_id)
                return


async def _send_group_one(sem, chat_id, b_msg, stats: dict):
    async with sem:
        while True:
            try:
                await b_msg.copy(chat_id=chat_id)
                stats["done"] += 1
                stats["success"] += 1
                return
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception:
                await db.delete_chat(chat_id)
                stats["done"] += 1
                stats["failed"] += 1
                return


# ─────────────── live-progress runner ───────────────────────────

async def _run_broadcast(tasks, stats, sts_msg, total, update_interval=5):
    """
    Run tasks in chunks and edit the status message every `update_interval` seconds.
    """
    async def _progress_updater():
        while True:
            await asyncio.sleep(update_interval)
            pct = int(stats["done"] / total * 100) if total else 100
            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
            await _safe_edit(
                sts_msg,
                f"📡 **Broadcasting…** {pct}%\n`{bar}`\n\n"
                + _summary(stats)
            )

    updater = asyncio.create_task(_progress_updater())
    try:
        for i in range(0, len(tasks), CHUNK_SIZE):
            await asyncio.gather(*tasks[i:i + CHUNK_SIZE], return_exceptions=True)
    finally:
        updater.cancel()


# ─────────────────────── /broadcast ─────────────────────────────

@Client.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast(bot, message):
    b_msg = message.reply_to_message
    sts = await message.reply_text("⏳ Loading users…")

    users = await db.get_all_users()
    users = [u async for u in users] if hasattr(users, "__aiter__") else users
    total = len(users)

    # Reset global state for this broadcast
    BC.clear()
    BC["msg"] = b_msg

    stats = {"done": 0, "success": 0, "blocked": 0, "deleted": 0, "failed": 0}
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [_send_one(sem, int(u["id"]), b_msg, stats) for u in users]

    await _run_broadcast(tasks, stats, sts, total)

    failed_ids = BC.get("users", set())
    BC["stats"] = stats  # store for retry summary

    final_text = f"✅ **Broadcast Complete** — {total} users\n\n" + _summary(stats)
    await _safe_edit(sts, final_text, reply_markup=_make_btn(failed_ids))


# ─────────────────── Retry failed callback ──────────────────────

@Client.on_callback_query(filters.regex("^bc_retry_failed$") & filters.user(ADMINS))
async def retry_failed(bot, query):
    failed_ids = BC.get("users", set())
    if not failed_ids:
        return await query.answer("✅ No failed users left!", show_alert=True)

    b_msg = BC.get("msg")
    if b_msg is None:
        return await query.answer("⚠️ Original message unavailable.", show_alert=True)

    # Acknowledge button press immediately so Telegram doesn't show "loading"
    await query.answer("⏳ Retrying failed users…")

    # Disable the button while retrying so admin can't double-click
    await _safe_edit(
        query.message,
        query.message.text + "\n\n⏳ Retrying…",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⏳ Retrying…", callback_data="bc_noop")]]
        )
    )

    failed_snapshot = list(failed_ids)
    retry_stats = {"done": 0, "success": 0, "blocked": 0, "deleted": 0, "failed": 0}
    sem = asyncio.Semaphore(20)

    async def _retry_one(uid):
        async with sem:
            while True:
                try:
                    await b_msg.copy(chat_id=uid)
                    failed_ids.discard(uid)          # remove from global failed set
                    retry_stats["done"] += 1
                    retry_stats["success"] += 1
                    return
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)  # never-fail
                except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid):
                    failed_ids.discard(uid)
                    retry_stats["done"] += 1
                    retry_stats["blocked"] += 1
                    return
                except Exception:
                    retry_stats["done"] += 1
                    retry_stats["failed"] += 1
                    return

    await asyncio.gather(*[_retry_one(uid) for uid in failed_snapshot], return_exceptions=True)

    # Build updated message after retry
    remaining = BC.get("users", set())
    retry_note = (
        f"\n\n🔁 **Retry Result** ({len(failed_snapshot)} users)\n"
        f"✅ Recovered: `{retry_stats['success']}`  |  ❌ Still failed: `{len(remaining)}`"
    )

    prev_stats = BC.get("stats", {})
    base_text = f"✅ **Broadcast Complete**\n\n" + _summary(prev_stats, extra=retry_note)

    await _safe_edit(query.message, base_text, reply_markup=_make_btn(remaining))


# Noop handler so the disabled "Retrying…" button doesn't cause errors
@Client.on_callback_query(filters.regex("^bc_noop$") & filters.user(ADMINS))
async def bc_noop(bot, query):
    await query.answer()


# ─────────────────── /grpbroadcast ──────────────────────────────

@Client.on_message(filters.command("grpbroadcast") & filters.user(ADMINS) & filters.reply)
async def grpbroadcast(bot, message):
    b_msg = message.reply_to_message
    sts = await message.reply_text("⏳ Loading groups…")

    chats = await db.get_all_chats()
    chats = [c async for c in chats] if hasattr(chats, "__aiter__") else chats
    total = len(chats)

    stats = {"done": 0, "success": 0, "blocked": 0, "deleted": 0, "failed": 0}
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [_send_group_one(sem, int(c["id"]), b_msg, stats) for c in chats]

    await _run_broadcast(tasks, stats, sts, total)

    await _safe_edit(
        sts,
        f"✅ **Group Broadcast Complete** — {total} chats\n\n" + _summary(stats)
    )
