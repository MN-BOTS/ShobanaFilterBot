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
PAGE_SIZE          = 20   # items per page in the daily summary
SEND_DELAY         = 0.5  # seconds between channel sends (flood-wait safety)
GETDLINK_PAGE_SIZE = 5    # results per page in /getdlink picker (no hard cap)

LANG_MAP = {
    "mal": "Malayalam",
    "eng": "English",
    "tam": "Tamil",
    "hin": "Hindi",
    "kan": "Kannada",
    "tel": "Telugu",
}

# ─── Serial queue – guarantees zero skips during bulk indexing ────────────────
_update_queue: asyncio.Queue  = asyncio.Queue()
_queue_consumer_started: bool = False

# ─── Per-admin session state for /getdlink flow ───────────────────────────────
# Structure: { user_id: { "results": [...], "query": str, "page": int } }
_getdlink_sessions: dict[int, dict] = {}


# ══════════════════════════════════════════════════════════════════════════════
#  TITLE / SEASON PARSING
# ══════════════════════════════════════════════════════════════════════════════

def normalize_compact_title(title: str) -> str:
    """Join isolated single letters into acronyms: 'K G F' → 'KGF'."""
    parts: list[str] = title.split()
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

    Handles messy real-world filenames:
      • [PiRO] Blue Lock 23 [][Multiple Subtitle][35 @MNTGX  → "Blue Lock", no season
      • Chained.Soldier.S02E01.Commanders.Meeting.1080p.AM   → "Chained Soldier", season=2
      • [SubsPlease] Demon Slayer S04E05 [1080p]             → "Demon Slayer",    season=4
      • Oppenheimer.2023.1080p.BluRay                        → "Oppenheimer",     year=2023
      • Plaha.S01E10.The.Jackals.1080p.10bit.NF.WEB-DL       → "Plaha",           season=1
    """
    file_name_orig = file_name  # preserve for anime-style detection

    # Step 1: strip file extension
    file_name = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", file_name)
    # Step 2: strip leading release-group tag [PiRO] / (HorribleSubs)
    file_name = re.sub(r"^\s*[\[\(][^\]\)]{1,40}[\]\)]\s*[-–]?\s*", "", file_name)
    # Step 3: strip all fully-closed bracket/paren blocks
    file_name = re.sub(r"[\[\(][^\]\)]*[\]\)]", "", file_name)
    # Step 4: strip unclosed bracket/paren to end-of-string
    file_name = re.sub(r"[\[\(][^\]\)]*$", "", file_name)
    # Step 5: strip @mentions
    file_name = re.sub(r"\s*@\S+", "", file_name)
    # Step 6: normalise separators
    clean = re.sub(r"[._\-]+", " ", file_name).strip()

    # Step 7: detect year
    year_match = re.search(r"\b((?:19|20)\d{2})\b", clean)
    # Step 8: detect season (lookahead handles S02E01 → season=2)
    season_match = re.search(r"\bS(\d{1,2})(?:E\d+|\b)", clean, re.I)
    if not season_match:
        season_match = re.search(r"\bseason\s*(\d{1,2})\b", clean, re.I)

    # Step 9: cut at earliest junk boundary (year or SxxExx marker)
    se_boundary = re.search(r"\bS\d{1,2}(?:E\d+)?\b", clean, re.I)
    cut_pos = len(clean)
    if year_match:
        cut_pos = min(cut_pos, clean.index(year_match.group(1)))
    if se_boundary:
        cut_pos = min(cut_pos, se_boundary.start())
    title = clean[:cut_pos].strip(" ._-")

    # Step 10: quality/codec safety strip
    title = re.sub(
        r"\b(2160p|1080p|720p|480p|x264|x265|h264|h265|hevc|webrip|hdrip|"
        r"web[-\s]?dl|blu[-\s]?ray|aac|ac3|dts|esub|mkv|mp4|avi|hdtv|hq|"
        r"dvdrip|bdrip|nf|amzn|hmax|proper|repack|multi|dual|subbed|dubbed|"
        r"10bit|8bit|ddp\d?[\.\d]*|dts[\-\w]*|hdr|sdr|atmos)\b",
        "", title, flags=re.I
    ).strip()
    # Step 11: residual season/ep tokens
    title = re.sub(
        r"\b(season\s*\d+|s\d{1,2}|ep\s*\d+|episode\s*\d+)\b",
        "", title, flags=re.I
    ).strip()
    # Step 12: normalise whitespace + acronym-join
    title = normalize_compact_title(re.sub(r"\s+", " ", title)).strip()

    # ── Step 13: anime episode-number strip ──────────────────────────────────
    # Pattern: [Group] Series Name 14 [][Quality] → "Series Name"
    # Detect anime-style: original had a leading [Group] tag OR multiple [] blocks
    _is_anime_style = (
        bool(re.match(r"^\s*\[", file_name_orig)) or
        bool(re.search(r"\]\s*\[", file_name_orig))
    )
    if _is_anime_style and not season_match:
        # Strip trailing standalone 1-4 digit number (episode number)
        ep_strip = re.search(r"\s+(\d{1,4})\s*$", title)
        if ep_strip:
            prefix = title[:ep_strip.start()].strip()
            if prefix:  # don't strip if nothing would remain
                title = prefix

    return (
        title or clean.strip(),
        year_match.group(1)   if year_match   else None,
        season_match.group(1) if season_match else None,
    )


def detect_language(file_name: str) -> str | None:
    low   = file_name.lower()
    found = [v for k, v in LANG_MAP.items() if re.search(rf"\b{k}\b", low)]
    return ", ".join(found) if found else None


def extract_quality(file_name: str) -> str | None:
    """Extract the best available quality tag from a raw filename."""
    m = re.search(r"\b(2160p|4K|1080p|720p|480p|HQ|HD)\b", file_name, re.I)
    return m.group(1).upper() if m else None


def _format_daily_entry(
    display_name: str,
    *,
    year: str | None    = None,
    lang: str | None    = None,
    quality: str | None = None,
    kind: str | None    = None,   # "movie" / "series" / None
) -> str:
    """
    Produce a /getlist line in the same style as /movies and /series:
      🎬 <b>Title (2024)</b> - Malayalam | 1080p
      📺 <b>Blue Lock S01</b> - Multiple Subtitle | 720p
    """
    icon = "📺" if (kind == "series" or re.search(r"\bS\d{2}\b", display_name)) else "🎬"
    # Append year in parentheses if not already present and it's a movie
    name = display_name
    if year and icon == "🎬" and str(year) not in name:
        name = f"{name} ({year})"

    extras: list[str] = []
    if lang:
        extras.append(lang)
    if quality:
        extras.append(quality)

    line = f"{icon} <b>{_esc(name)}</b>"
    if extras:
        line += f" — {' | '.join(extras)}"
    return line


def _esc(val) -> str:
    """HTML-escape for Telegram parse_mode='HTML'. Returns empty string for None."""
    if val is None:
        return ""
    return str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ══════════════════════════════════════════════════════════════════════════════
#  DEDUPLICATION KEY
# ══════════════════════════════════════════════════════════════════════════════

def _make_key(title: str, year: str | None, season: str | None) -> str:
    """S01 and S02 → different keys. Same season → duplicate → skip."""
    base = f"{title.strip().lower()}::{year or 'na'}"
    return f"{base}::s{int(season):02d}" if season else f"{base}::movie"


# ══════════════════════════════════════════════════════════════════════════════
#  IMDb MATCH CONFIDENCE  (prevents wrong-title announcements)
# ══════════════════════════════════════════════════════════════════════════════

def _title_confidence(parsed: str, imdb_title: str) -> float:
    """
    0.0–1.0: word-overlap score between the parsed title and the IMDb result.
    Short titles (≤2 words) use a higher bar via exact-prefix check.
    """
    p_words = set(re.sub(r"[^a-z0-9 ]", "", parsed.lower()).split())
    i_words = set(re.sub(r"[^a-z0-9 ]", "", imdb_title.lower()).split())
    # Remove very common stop-words that inflate false confidence
    stops = {"the", "a", "an", "of", "in", "and", "to", "is"}
    p_words -= stops
    i_words -= stops
    if not p_words or not i_words:
        return 0.0
    overlap = len(p_words & i_words)
    return overlap / max(len(p_words), len(i_words))


# ══════════════════════════════════════════════════════════════════════════════
#  SHARED MESSAGE BUILDER
#  Used by both the auto-update pipeline and the /getdlink manual flow
# ══════════════════════════════════════════════════════════════════════════════

async def _build_update_message(
    bot: Client,
    imdb: dict,
    season: str | None = None,
    lang: str | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Build the standard update message text + search button.
    imdb must be non-None (caller's responsibility).
    Returns (text, reply_markup).
    """
    base_name    = imdb.get("title") or ""
    display_name = f"{base_name} S{int(season):02d}" if season else base_name

    lines: list[str] = []
    if season:
        lines.append(f"📺 <b>{_esc(display_name)}</b>")
    else:
        lines.append(f"🎬 <b>{_esc(display_name)}</b>")
    lines.append("")

    if imdb.get("genres"):
        lines.append(f"• <b>Genre:</b> {_esc(imdb['genres'])}")
    if lang:
        lines.append(f"• <b>Language:</b> {_esc(lang)}")
    if season:
        lines.append(f"• <b>Season:</b> {int(season):02d}")

    rating_parts: list[str] = []
    if imdb.get("rating"):
        rating_parts.append(f"⭐ {_esc(imdb['rating'])}")
    if imdb.get("year"):
        rating_parts.append(f"📅 {_esc(imdb['year'])}")
    if imdb.get("kind"):
        rating_parts.append(f"🎭 {_esc(imdb['kind'])}")
    if rating_parts:
        lines.append(f"• <b>IMDb:</b> {' | '.join(rating_parts)}")

    # ── "More" as a clickable hyperlink instead of a raw URL ─────────────────
    if imdb.get("url"):
        lines.append(
            f'• <b>More:</b> <a href="{imdb["url"]}">🔗 Click here</a>'
        )

    text = "\n".join(lines)

    bot_me    = await bot.get_me()
    start_key = re.sub(r"[^a-zA-Z0-9_]+", "_", display_name).strip("_")[:50]
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🔍 Search in Bot",
            url=f"https://t.me/{bot_me.username}?start=mntgx_{start_key}"
        )
    ]])
    return text, markup


async def _send_to_channels(
    bot: Client,
    text: str,
    markup: InlineKeyboardMarkup,
    display_name: str,
    imdb_key: str,                   # dedup key
    list_entry: str | None = None,   # pre-formatted /getlist line
) -> int:
    """Send text+markup to all update channels. Returns count of successful sends."""
    channel_ids = await db.get_update_chat_ids()
    sent = 0
    for cid in channel_ids:
        try:
            await bot.send_message(
                cid, text,
                disable_web_page_preview=True,
                reply_markup=markup
            )
            sent += 1
        except Exception as exc:
            logger.warning("Failed sending update to channel %s: %s", cid, exc)
    if sent:
        await db.add_announced_key(imdb_key)
        # Store the rich formatted entry for /getlist; fall back to plain name
        await db.add_daily_added(list_entry or display_name)
        logger.info("✅ Announced: %s", display_name)
    return sent


# ══════════════════════════════════════════════════════════════════════════════
#  AUTO-UPDATE QUEUE CONSUMER
# ══════════════════════════════════════════════════════════════════════════════

async def _queue_consumer(bot: Client) -> None:
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
    """Parse → dedup → IMDb → confidence check → format → send → record."""
    title, year, season = parse_title_year_and_season(file_name)

    # Skip suspiciously short titles (likely parsing failure)
    if len(title) < 2:
        logger.debug("Title too short after parsing, skipping: '%s'", file_name)
        return

    key = _make_key(title, year, season)

    if await db.check_announced_key(key):
        logger.debug("Duplicate, skipping: %s", key)
        return

    # ── IMDb search with year-stripped fallback ───────────────────────────────
    imdb = await get_poster(title, file=file_name)
    if not imdb:
        fallback = re.sub(r"\b(?:19|20)\d{2}\b", "", title).strip()
        if fallback and fallback != title:
            imdb = await get_poster(fallback, file=file_name)
    if not imdb:
        imdb = await get_poster(title)

    if not imdb:
        logger.info("No IMDb data for '%s' (parsed: '%s') — skipping.", file_name, title)
        return

    # ── Confidence gate: reject obviously-wrong IMDb matches ─────────────────
    imdb_title = imdb.get("title", "")
    confidence = _title_confidence(title, imdb_title)
    if confidence < 0.25:
        logger.info(
            "Low-confidence IMDb match (%.0f%%) '%s' → '%s' — skipping.",
            confidence * 100, title, imdb_title,
        )
        return

    lang    = detect_language(file_name)
    quality = extract_quality(file_name)
    text, markup = await _build_update_message(bot, imdb, season=season, lang=lang)

    base_name    = imdb.get("title") or title
    display_name = f"{base_name} S{int(season):02d}" if season else base_name
    list_entry   = _format_daily_entry(
        display_name,
        year    = imdb.get("year") or year,
        lang    = lang,
        quality = quality,
        kind    = "series" if season else imdb.get("kind"),
    )

    await _send_to_channels(bot, text, markup, display_name, key, list_entry=list_entry)


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC ENTRY POINT  (called from file-indexer / media handler)
# ══════════════════════════════════════════════════════════════════════════════

async def post_new_content_update(bot: Client, file_name: str) -> None:
    """Non-blocking. Enqueues file_name for serial processing."""
    global _queue_consumer_started
    if not _queue_consumer_started:
        asyncio.get_event_loop().create_task(_queue_consumer(bot))
        _queue_consumer_started = True
    await _update_queue.put(file_name)


# ══════════════════════════════════════════════════════════════════════════════
#  /getdlink  –  manual post creator
#
#  Flow:
#    1. Admin sends: /getdlink kgf
#    2. Bot searches IMDb, collects all unique results and paginates them
#       (GETDLINK_PAGE_SIZE per page, Next ➡️ / ⬅️ Prev buttons)
#    3. Admin taps a result  →  season picker  →  post preview
#    4. Admin confirms  →  posted to all update channels
# ══════════════════════════════════════════════════════════════════════════════

def _build_picker_keyboard(
    results: list[dict],
    user_id: int,
    page: int,
) -> InlineKeyboardMarkup:
    """Build a paginated result-picker keyboard for /getdlink."""
    start        = page * GETDLINK_PAGE_SIZE
    end          = min(start + GETDLINK_PAGE_SIZE, len(results))
    total_pages  = max(1, -(-len(results) // GETDLINK_PAGE_SIZE))

    buttons: list[list[InlineKeyboardButton]] = []
    for real_idx in range(start, end):
        r        = results[real_idx]
        btn_text = r.get("title", "Unknown")
        if r.get("year"):
            btn_text += f"  ({r['year']})"
        if r.get("kind"):
            btn_text += f"  [{r['kind']}]"
        buttons.append([
            InlineKeyboardButton(
                btn_text,
                callback_data=f"gdl_pick:{user_id}:{real_idx}"
            )
        ])

    # Pagination row
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"gdl_page:{user_id}:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"gdl_page:{user_id}:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=f"gdl_cancel:{user_id}")])
    return InlineKeyboardMarkup(buttons)


@Client.on_message(filters.command("getdlink") & filters.user(ADMINS) & filters.private)
async def getdlink_cmd(bot: Client, message) -> None:
    if len(message.command) < 2:
        return await message.reply(
            "Usage: <code>/getdlink &lt;title&gt;</code>\n"
            "Example: <code>/getdlink kgf</code>"
        )

    query_str = " ".join(message.command[1:]).strip()
    wait      = await message.reply(f"🔍 Searching IMDb for <b>{_esc(query_str)}</b>…")

    results: list[dict] = []
    seen_ids: set[str]  = set()

    async def _try(q: str) -> None:
        try:
            r = await get_poster(q)
            if r and r.get("title"):
                rid = r.get("imdb_id") or r.get("url") or r["title"]
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    results.append(r)
        except Exception:
            pass

    # Cast a wide net – no cap; duplicates are filtered by seen_ids
    for variant in (
        query_str,
        f"{query_str} film",
        f"{query_str} series",
        f"{query_str} movie",
        f"{query_str} season 1",
        f"{query_str} season 2",
        f"{query_str} tv",
        f"{query_str} anime",
        f"the {query_str}",
        f"{query_str} 2",
    ):
        await _try(variant)

    # Deduplicate by title+year
    deduped: list[dict] = []
    seen_titles: set[str] = set()
    for r in results:
        tk = f"{(r.get('title') or '').lower()}::{r.get('year', '')}"
        if tk not in seen_titles:
            seen_titles.add(tk)
            deduped.append(r)

    results = deduped

    if not results:
        await wait.edit_text(
            f"❌ No IMDb results found for <b>{_esc(query_str)}</b>.\n"
            "Try a different title or check the spelling."
        )
        return

    _getdlink_sessions[message.from_user.id] = {
        "results": results,
        "query":   query_str,
        "page":    0,
    }

    total_pages = max(1, -(-len(results) // GETDLINK_PAGE_SIZE))
    markup      = _build_picker_keyboard(results, message.from_user.id, 0)

    await wait.edit_text(
        f"🎬 Found <b>{len(results)}</b> result(s) for <b>{_esc(query_str)}</b>.\n"
        f"Page <b>1/{total_pages}</b> — Choose the correct title:",
        reply_markup=markup
    )


@Client.on_callback_query(filters.regex(r"^gdl_page:(\d+):(\d+)$") & filters.user(ADMINS))
async def getdlink_page_callback(bot: Client, query) -> None:
    """Navigate pages in the /getdlink result picker."""
    user_id = int(query.matches[0].group(1))
    page    = int(query.matches[0].group(2))

    if query.from_user.id != user_id:
        return await query.answer("This picker belongs to another admin.", show_alert=True)

    session = _getdlink_sessions.get(user_id)
    if not session:
        return await query.answer("Session expired. Run /getdlink again.", show_alert=True)

    results     = session["results"]
    total_pages = max(1, -(-len(results) // GETDLINK_PAGE_SIZE))
    if page < 0 or page >= total_pages:
        return await query.answer("Invalid page.", show_alert=True)

    session["page"]   = page
    query_str         = session.get("query", "")
    start             = page * GETDLINK_PAGE_SIZE
    end               = min(start + GETDLINK_PAGE_SIZE, len(results))
    markup            = _build_picker_keyboard(results, user_id, page)

    await query.edit_message_text(
        f"🎬 Found <b>{len(results)}</b> result(s) for <b>{_esc(query_str)}</b>.\n"
        f"Page <b>{page + 1}/{total_pages}</b> — Choose the correct title:",
        reply_markup=markup
    )
    await query.answer()


@Client.on_callback_query(filters.regex(r"^gdl_pick:(\d+):(\d+)$") & filters.user(ADMINS))
async def getdlink_pick_callback(bot: Client, query) -> None:
    """Admin chose a search result — show the season picker."""
    user_id = int(query.matches[0].group(1))
    idx     = int(query.matches[0].group(2))

    if query.from_user.id != user_id:
        return await query.answer("This picker belongs to another admin.", show_alert=True)

    session = _getdlink_sessions.get(user_id)
    if not session:
        return await query.answer("Session expired. Run /getdlink again.", show_alert=True)

    results = session["results"]
    if idx >= len(results):
        return await query.answer("Invalid selection.", show_alert=True)

    imdb             = results[idx]
    session["chosen"] = imdb

    season_row_1 = [InlineKeyboardButton("🎬 Movie", callback_data=f"gdl_season:{user_id}:0")]
    season_rows  = [season_row_1]
    row: list[InlineKeyboardButton] = []
    for s in range(1, 11):
        row.append(InlineKeyboardButton(f"S{s:02d}", callback_data=f"gdl_season:{user_id}:{s}"))
        if len(row) == 5:
            season_rows.append(row)
            row = []
    if row:
        season_rows.append(row)
    season_rows.append([InlineKeyboardButton("❌ Cancel", callback_data=f"gdl_cancel:{user_id}")])

    title = imdb.get("title", "")
    year  = imdb.get("year", "")
    await query.edit_message_text(
        f"✅ Selected: <b>{_esc(title)}</b>"
        + (f" ({_esc(str(year))})" if year else "")
        + "\n\nIs this a movie or a series season?",
        reply_markup=InlineKeyboardMarkup(season_rows)
    )
    await query.answer()


@Client.on_callback_query(filters.regex(r"^gdl_season:(\d+):(\d+)$") & filters.user(ADMINS))
async def getdlink_season_callback(bot: Client, query) -> None:
    """Admin chose Movie or a season number — show the post preview."""
    user_id  = int(query.matches[0].group(1))
    season_n = int(query.matches[0].group(2))

    if query.from_user.id != user_id:
        return await query.answer("This picker belongs to another admin.", show_alert=True)

    session = _getdlink_sessions.get(user_id)
    if not session or "chosen" not in session:
        return await query.answer("Session expired. Run /getdlink again.", show_alert=True)

    imdb   = session["chosen"]
    season = str(season_n) if season_n > 0 else None

    text, search_btn_markup = await _build_update_message(bot, imdb, season=season, lang=None)

    session["preview_text"]   = text
    session["preview_season"] = season

    confirm_markup = InlineKeyboardMarkup(
        search_btn_markup.inline_keyboard + [[
            InlineKeyboardButton("✅ Send to Channels", callback_data=f"gdl_confirm:{user_id}"),
            InlineKeyboardButton("❌ Cancel",           callback_data=f"gdl_cancel:{user_id}"),
        ]]
    )

    await query.edit_message_text(
        "<b>📋 Preview — this is what will be posted:</b>\n\n" + text,
        reply_markup=confirm_markup,
        disable_web_page_preview=True
    )
    await query.answer()


@Client.on_callback_query(filters.regex(r"^gdl_confirm:(\d+)$") & filters.user(ADMINS))
async def getdlink_confirm_callback(bot: Client, query) -> None:
    """Admin confirmed — send to all update channels."""
    user_id = int(query.matches[0].group(1))

    if query.from_user.id != user_id:
        return await query.answer("This picker belongs to another admin.", show_alert=True)

    session = _getdlink_sessions.pop(user_id, None)
    if not session or "chosen" not in session:
        return await query.answer("Session expired. Run /getdlink again.", show_alert=True)

    imdb         = session["chosen"]
    season       = session.get("preview_season")
    preview_text = session.get("preview_text", "")

    base_name    = imdb.get("title") or ""
    display_name = f"{base_name} S{int(season):02d}" if season else base_name
    imdb_key     = _make_key(
        base_name,
        str(imdb.get("year")) if imdb.get("year") else None,
        season
    )

    if await db.check_announced_key(imdb_key):
        await query.edit_message_text(
            f"⚠️ <b>{_esc(display_name)}</b> was already announced. Nothing sent."
        )
        await query.answer()
        return

    _, clean_markup = await _build_update_message(bot, imdb, season=season, lang=None)
    list_entry = _format_daily_entry(
        display_name,
        year = str(imdb.get("year")) if imdb.get("year") else None,
        kind = "series" if season else imdb.get("kind"),
    )
    sent = await _send_to_channels(bot, preview_text, clean_markup, display_name, imdb_key, list_entry=list_entry)

    if sent:
        await query.edit_message_text(
            f"✅ <b>{_esc(display_name)}</b> posted to <b>{sent}</b> channel(s)."
        )
    else:
        await query.edit_message_text(
            "❌ No channels configured or all sends failed.\n"
            "Use /setupchat to configure update channels."
        )
    await query.answer()


@Client.on_callback_query(filters.regex(r"^gdl_cancel:(\d+)$") & filters.user(ADMINS))
async def getdlink_cancel_callback(bot: Client, query) -> None:
    """Admin cancelled the /getdlink flow."""
    user_id = int(query.matches[0].group(1))

    if query.from_user.id != user_id:
        return await query.answer("This picker belongs to another admin.", show_alert=True)

    _getdlink_sessions.pop(user_id, None)
    await query.edit_message_text("❌ Cancelled.")
    await query.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  /getlist  –  show today's daily summary to the admin in PM
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("getlist") & filters.user(ADMINS) & filters.private)
async def getlist_cmd(bot: Client, message) -> None:
    items = await db.get_daily_added()
    if not items:
        return await message.reply("📋 No movies/series added today yet.")

    total_pages  = max(1, -(-len(items) // PAGE_SIZE))
    today        = datetime.now(timezone.utc).date().isoformat()
    text, markup = _build_summary_page(items, 0, total_pages, today)
    await message.reply(text, parse_mode="html", reply_markup=markup)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGINATED DAILY SUMMARY  (20 items / page  •  Prev / Next buttons)
# ══════════════════════════════════════════════════════════════════════════════

def _build_summary_page(
    items: list[str],
    page: int,
    total_pages: int,
    today: str,
) -> tuple[str, InlineKeyboardMarkup]:
    start = page * PAGE_SIZE
    chunk = items[start : start + PAGE_SIZE]

    header = (
        f"<b>📋 Today's Added Movies/Series</b>  [{today}]\n"
        f"<i>Page {page + 1}/{total_pages}  •  {len(items)} total</i>\n\n"
    )
    # Items are already HTML-formatted by _format_daily_entry (✅ <b>Title</b> — lang | quality)
    # Raw strings from legacy entries are escaped and prefixed with a bullet as fallback
    body_lines: list[str] = []
    for x in chunk:
        if x.startswith(("🎬", "📺")):
            body_lines.append(x)          # already formatted HTML — use as-is
        else:
            body_lines.append(f"• {_esc(x)}")   # legacy plain string fallback
    body = "\n".join(body_lines)
    text = header + body

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"sumpage:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"sumpage:{page + 1}"))

    markup = InlineKeyboardMarkup([nav]) if nav else InlineKeyboardMarkup([[]])
    return text, markup


@Client.on_callback_query(filters.regex(r"^sumpage:(\d+)$"))
async def summary_page_callback(bot: Client, query) -> None:
    page  = int(query.matches[0].group(1))
    items = await db.get_daily_added()

    if not items:
        return await query.answer("No summary data available.", show_alert=True)

    total_pages = max(1, -(-len(items) // PAGE_SIZE))
    if page < 0 or page >= total_pages:
        return await query.answer("Invalid page.", show_alert=True)

    today        = datetime.now(timezone.utc).date().isoformat()
    text, markup = _build_summary_page(items, page, total_pages, today)

    try:
        await query.edit_message_text(text, parse_mode="html", reply_markup=markup)
    except Exception as exc:
        logger.warning("Failed editing summary page: %s", exc)

    await query.answer()


async def _send_paginated_summary(bot: Client, cid: int, items: list[str]) -> None:
    if not items:
        return
    total_pages  = max(1, -(-len(items) // PAGE_SIZE))
    today        = datetime.now(timezone.utc).date().isoformat()
    text, markup = _build_summary_page(items, 0, total_pages, today)
    try:
        await bot.send_message(cid, text, parse_mode="html", reply_markup=markup)
    except Exception as exc:
        logger.warning("Failed sending summary to %s: %s", cid, exc)


# ══════════════════════════════════════════════════════════════════════════════
#  BACKGROUND TASK: nightly summary
# ══════════════════════════════════════════════════════════════════════════════

async def run_daily_summary(bot: Client) -> None:
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
#  EXISTING ADMIN COMMANDS
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
