import asyncio
import logging
import re
from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.users_chats_db import db
from info import ADMINS
from utils import get_poster

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
PAGE_SIZE  = 20       # items per page in the daily summary
SEND_DELAY = 0.5      # seconds between sends to respect Telegram rate limits

LANG_MAP = {
    "mal": "Malayalam",
    "eng": "English",
    "tam": "Tamil",
    "hin": "Hindi",
    "kan": "Kannada",
    "tel": "Telugu",
}

# ─── In-memory queue: guarantees NO file is skipped during bulk uploads ───────
# post_new_content_update() is the public API – it simply enqueues.
# _queue_consumer() drains one item at a time so check+announce is never racy.
_update_queue: asyncio.Queue           = asyncio.Queue()
_queue_consumer_started: bool          = False


# ══════════════════════════════════════════════════════════════════════════════
#  TITLE / SEASON PARSING
# ══════════════════════════════════════════════════════════════════════════════

def normalize_compact_title(title: str) -> str:
    """Join isolated single letters: 'K G F' → 'KGF'."""
    parts   = title.split()
    compact: list[str] = []
    i = 0
    while i < len(parts):
        if len(parts[i]) == 1 and parts[i].isalpha():
            letters = [parts[i]]
            j = i + 1
            while j < len(parts) and len(parts[j]) == 1 and parts[j].isalpha():
                letters.append(parts[j])
                j += 1
            if len(letters) >= 2:
                compact.append("".join(letters))
                i = j
                continue
        compact.append(parts[i])
        i += 1
    return " ".join(compact)


def parse_title_year_and_season(file_name: str) -> tuple[str, str | None, str | None]:
    """
    Returns (clean_title, year | None, season_number | None).

    Key fixes over the original:
    1. Strip extension first (avoids '.mkv' in title).
    2. Use str.index() not str.split() for year boundary (handles duplicate tokens).
    3. Capture season BEFORE stripping it from the title string.
    4. Wider codec/tag blocklist.
    """
    # 1. Strip extension
    file_name = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", file_name)
    # 2. Normalise separators
    clean = re.sub(r"[._\-]+", " ", file_name)

    # 3. Detect year
    year_match   = re.search(r"\b((?:19|20)\d{2})\b", clean)
    # 4. Detect season: S01, S1, Season 1, season01  (capture the number only)
    season_match = re.search(r"\b(?:s(?:eason)?\s*0?(\d{1,2}))\b", clean, re.I)

    # 5. Trim title to everything before the year
    title = clean
    if year_match:
        title = clean[: clean.index(year_match.group(1))].strip()

    # 6. Strip episode markers (S01E03, E05, ep5 …) from title text
    title = re.sub(
        r"\b(s\d{1,2}e\d{1,3}|e\d{1,3}|ep\s*\d+|episode\s*\d+)\b",
        "", title, flags=re.I
    ).strip()

    # 7. Strip bare season tokens from title text
    title = re.sub(r"\b(season\s*\d+|s\d{1,2})\b", "", title, flags=re.I).strip()

    # 8. Strip quality / codec tags
    title = re.sub(
        r"\b(2160p|1080p|720p|480p|x264|x265|h264|h265|hevc|webrip|hdrip|"
        r"web[-\s]?dl|blu[-\s]?ray|aac|ac3|dts|esub|mkv|mp4|avi|hdtv|hq|"
        r"dvdrip|bdrip|nf|amzn|hmax|proper|repack)\b",
        "", title, flags=re.I
    ).strip()

    # 9. Collapse whitespace + acronym-join
    title = normalize_compact_title(re.sub(r"\s+", " ", title)).strip()

    return (
        title or clean.strip(),
        year_match.group(1)   if year_match   else None,
        season_match.group(1) if season_match else None,
    )


def detect_language(file_name: str) -> str | None:
    low   = file_name.lower()
    found = [v for k, v in LANG_MAP.items() if re.search(rf"\b{k}\b", low)]
    return ", ".join(found) if found else None


def _esc(val) -> str:
    """HTML-escape a value for Telegram parse_mode='HTML'."""
    if val is None:
        return "N/A"
    return str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ══════════════════════════════════════════════════════════════════════════════
#  DEDUPLICATION KEY
# ══════════════════════════════════════════════════════════════════════════════

def _make_key(title: str, year: str | None, season: str | None) -> str:
    """
    Season IS part of the key: S01 and S02 are different announcements.
    Two files for the same season are duplicates → skip the second.
    Movies (no season) use '::movie' suffix.
    """
    base = f"{title.strip().lower()}::{year or 'na'}"
    return f"{base}::s{int(season):02d}" if season else f"{base}::movie"


# ══════════════════════════════════════════════════════════════════════════════
#  QUEUE CONSUMER  (serial processor – zero skips)
# ══════════════════════════════════════════════════════════════════════════════

async def _queue_consumer(bot: Client) -> None:
    """Drains _update_queue one item at a time to avoid races."""
    while True:
        file_name: str = await _update_queue.get()
        try:
            await _process_one_update(bot, file_name)
        except Exception:
            logger.exception("Unhandled error processing '%s'", file_name)
        finally:
            _update_queue.task_done()
            await asyncio.sleep(SEND_DELAY)


async def _process_one_update(bot: Client, file_name: str) -> None:
    """Parse → dedup → IMDb → format → send → record."""

    title, year, season = parse_title_year_and_season(file_name)
    key = _make_key(title, year, season)

    # ── Deduplication ─────────────────────────────────────────────────────────
    if await db.check_announced_key(key):
        logger.debug("Duplicate, skipping: %s", key)
        return

    # ── IMDb lookup with fallbacks ────────────────────────────────────────────
    imdb = await get_poster(title, file=file_name)
    if not imdb:
        fallback = re.sub(r"\b(?:19|20)\d{2}\b", "", title).strip()
        if fallback and fallback != title:
            imdb = await get_poster(fallback, file=file_name)
    if not imdb:
        imdb = await get_poster(title)   # bare title, no file hint

    # ── Display name: always include season for series ────────────────────────
    base_name: str    = (imdb.get("title") if imdb else None) or title
    if season:
        display_name  = f"{base_name} S{int(season):02d}"
    else:
        display_name  = base_name

    # ── Build message ─────────────────────────────────────────────────────────
    lang    = detect_language(file_name)
    genre   = _esc(imdb.get("genres") if imdb else None)
    rating  = _esc(imdb.get("rating", "N/A") if imdb else "N/A")
    imdb_yr = _esc(imdb.get("year",   "N/A") if imdb else "N/A")
    kind    = _esc(imdb.get("kind",   "N/A") if imdb else "N/A")
    url     = (imdb.get("url") or "") if imdb else ""

    content_label = "📺 Series" if season else "🎬 Movie"

    lines: list[str] = [
        f"{content_label} <b>{_esc(display_name)}</b>\n",
        f"• <b>Genre:</b> {genre}",
    ]
    if lang:
        lines.append(f"• <b>Language:</b> {_esc(lang)}")
    if season:
        lines.append(f"• <b>Season:</b> {int(season):02d}")
    lines.append(f"• <b>IMDb:</b> ⭐ {rating} | 📅 {imdb_yr} | 🎭 {kind}")
    if url:
        lines.append(f"• <b>More:</b> {url}")

    text = "\n".join(lines)

    # ── Inline button ─────────────────────────────────────────────────────────
    bot_me    = await bot.get_me()
    start_key = re.sub(r"[^a-zA-Z0-9_]+", "_", display_name).strip("_")[:50]
    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🔍 Search in Bot",
            url=f"https://t.me/{bot_me.username}?start=mntgx_{start_key}"
        )
    ]])

    # ── Send to every update channel ──────────────────────────────────────────
    channel_ids = await db.get_update_chat_ids()
    for cid in channel_ids:
        try:
            await bot.send_message(
                cid, text,
                disable_web_page_preview=True,
                reply_markup=btn
            )
        except Exception as exc:
            logger.warning("Failed sending update to channel %s: %s", cid, exc)

    # ── Persist AFTER sending ─────────────────────────────────────────────────
    await db.add_announced_key(key)
    await db.add_daily_added(display_name)
    logger.info("✅ Announced: %s", display_name)


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC ENTRY POINT  (called from file-indexer / media handler)
# ══════════════════════════════════════════════════════════════════════════════

async def post_new_content_update(bot: Client, file_name: str) -> None:
    """
    Non-blocking.  Pushes file_name onto the serial queue.
    The consumer runs in the background so NO file is ever skipped,
    even when dozens of files are indexed at the same time.
    """
    global _queue_consumer_started
    if not _queue_consumer_started:
        asyncio.get_event_loop().create_task(_queue_consumer(bot))
        _queue_consumer_started = True
    await _update_queue.put(file_name)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGINATED DAILY SUMMARY  (20 items / page, Prev / Next buttons)
# ══════════════════════════════════════════════════════════════════════════════

def _build_summary_page(
    items: list[str],
    page: int,
    total_pages: int,
    today: str,
) -> tuple[str, InlineKeyboardMarkup]:
    """Return (message_text, reply_markup) for one page."""
    start = page * PAGE_SIZE
    chunk = items[start : start + PAGE_SIZE]

    header = (
        f"<b>📋 Today's Added Movies/Series</b>  [{today}]\n"
        f"<i>Page {page + 1}/{total_pages}  •  {len(items)} total</i>\n\n"
    )
    body   = "\n".join(f"• {_esc(x)}" for x in chunk)
    text   = header + body

    # Navigation buttons
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"sumpage:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"sumpage:{page + 1}"))

    markup = InlineKeyboardMarkup([nav]) if nav else InlineKeyboardMarkup([[]])
    return text, markup


@Client.on_callback_query(filters.regex(r"^sumpage:(\d+)$"))
async def summary_page_callback(bot: Client, query) -> None:
    """Handle Prev / Next taps on the paginated daily summary."""
    page  = int(query.matches[0].group(1))
    items = await db.get_daily_added()

    if not items:
        return await query.answer("No summary data available.", show_alert=True)

    total_pages = max(1, -(-len(items) // PAGE_SIZE))   # ceiling division

    if page < 0 or page >= total_pages:
        return await query.answer("Invalid page.", show_alert=True)

    today        = datetime.now(timezone.utc).date().isoformat()
    text, markup = _build_summary_page(items, page, total_pages, today)

    try:
        await query.edit_message_text(text, reply_markup=markup)
    except Exception as exc:
        logger.warning("Failed editing summary page: %s", exc)

    await query.answer()


async def _send_paginated_summary(bot: Client, cid: int, items: list[str]) -> None:
    """Send page 0 of the daily summary to one channel."""
    if not items:
        return
    total_pages  = max(1, -(-len(items) // PAGE_SIZE))
    today        = datetime.now(timezone.utc).date().isoformat()
    text, markup = _build_summary_page(items, 0, total_pages, today)
    try:
        await bot.send_message(cid, text, reply_markup=markup)
    except Exception as exc:
        logger.warning("Failed sending summary to %s: %s", cid, exc)


# ══════════════════════════════════════════════════════════════════════════════
#  BACKGROUND TASK: nightly summary dispatcher
# ══════════════════════════════════════════════════════════════════════════════

async def run_daily_summary(bot: Client) -> None:
    """
    Checks every 60 s.  At 23:55 UTC sends the paginated summary once per day.
    sleep(60) ensures we never miss the narrow 23:55–23:59 window.
    """
    last_summary_date: str | None = None

    while True:
        now   = datetime.now(timezone.utc)
        today = now.date().isoformat()

        if now.hour == 23 and now.minute >= 55:
            if last_summary_date != today and not await db.is_daily_summary_done(today):
                items = await db.get_daily_added()
                for cid in await db.get_update_chat_ids():
                    await _send_paginated_summary(bot, cid, items)
                await db.mark_daily_summary_done(today)
                await db.clear_daily_added()
                last_summary_date = today

        await asyncio.sleep(60)


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("setupchat") & filters.user(ADMINS))
async def setupchat_cmd(bot: Client, message) -> None:
    if len(message.command) < 2:
        chats = await db.get_update_chat_ids()
        return await message.reply(
            f"Current update chats: {', '.join(map(str, chats)) if chats else 'None'}"
        )
    raw = " ".join(message.command[1:]).replace(" ", "")
    ids = [int(x) for x in raw.split(",") if x.strip().lstrip("-").isdigit()]
    await db.set_update_chat_ids(ids)
    await message.reply(f"✅ Update chats saved: {ids}")


@Client.on_message(filters.command("movieupdates") & filters.user(ADMINS))
async def toggle_updates(bot: Client, message) -> None:
    if len(message.command) < 2 or message.command[1].lower() not in {"on", "off"}:
        status = await db.get_new_updates_enabled()
        return await message.reply(
            f"Current status: {'ON' if status else 'OFF'}\nUsage: /movieupdates on|off"
        )
    enabled = message.command[1].lower() == "on"
    await db.set_new_updates_enabled(enabled)
    await message.reply(f"✅ New movie/series updater {'enabled' if enabled else 'disabled'}")
