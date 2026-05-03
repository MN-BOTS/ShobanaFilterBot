import asyncio
import logging
import re
from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.users_chats_db import db
from info import ADMINS
from utils import get_poster

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
PAGE_SIZE          = 20   # items per page in the daily summary
SEND_DELAY         = 0.5  # seconds between channel sends (flood-wait safety)
GETDLINK_PAGE_SIZE = 10    # results per page in /getdlink picker (no hard cap)
GROUP_SIZE         = 10   # number of titles per grouped channel message

# ─── Channel send mode ────────────────────────────────────────────────────────
# "individual" → send each title as its own IMDb card message (with button)
# "grouped"    → accumulate, auto-flush every GROUP_SIZE titles as a plain list
# "manual"     → accumulate forever; admin triggers send with /sendupnow
CHANNEL_SEND_MODE: str = "manual"

# ─── Grouped message footer ───────────────────────────────────────────────────
# Shown at the bottom of every grouped channel post. Edit to match your bot/channel.
GROUP_SEARCH_TEXT: str = "🔍 Search movies → @malayalam_2022"

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

# ─── Pending group buffer (used only when CHANNEL_SEND_MODE == "grouped") ─────
# Accumulates formatted list_entry strings; flushed every GROUP_SIZE items.
_pending_group: list[str] = []



# Runtime config helpers for admin panel
def get_runtime_update_config() -> dict:
    return {
        "PAGE_SIZE": PAGE_SIZE,
        "SEND_DELAY": SEND_DELAY,
        "GETDLINK_PAGE_SIZE": GETDLINK_PAGE_SIZE,
        "GROUP_SIZE": GROUP_SIZE,
        "CHANNEL_SEND_MODE": CHANNEL_SEND_MODE,
        "GROUP_SEARCH_TEXT": GROUP_SEARCH_TEXT,
    }


def set_runtime_update_config(key: str, value):
    global PAGE_SIZE, SEND_DELAY, GETDLINK_PAGE_SIZE, GROUP_SIZE, CHANNEL_SEND_MODE, GROUP_SEARCH_TEXT
    if key == "PAGE_SIZE":
        PAGE_SIZE = max(1, int(value))
    elif key == "SEND_DELAY":
        SEND_DELAY = max(0.0, float(value))
    elif key == "GETDLINK_PAGE_SIZE":
        GETDLINK_PAGE_SIZE = max(1, int(value))
    elif key == "GROUP_SIZE":
        GROUP_SIZE = max(1, int(value))
    elif key == "CHANNEL_SEND_MODE":
        if value not in {"individual", "grouped", "manual"}:
            raise ValueError("Invalid CHANNEL_SEND_MODE")
        CHANNEL_SEND_MODE = value
    elif key == "GROUP_SEARCH_TEXT":
        GROUP_SEARCH_TEXT = str(value)
    else:
        raise KeyError(key)

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


def parse_title_year_and_season(
    file_name: str,
) -> tuple[str, str | None, str | None, int | None]:
    """
    Returns (clean_title, year | None, season_number | None, episode_number | None).

    Handles messy real-world filenames:
      • [PiRO] Blue Lock 23 [][Multiple Subtitle][35 @MNTGX  → "Blue Lock", ep=23
      • Chained.Soldier.S02E01.Commanders.Meeting.1080p.AM   → "Chained Soldier", s=2, ep=1
      • [SubsPlease] Demon Slayer S04E05 [1080p]             → "Demon Slayer",    s=4, ep=5
      • Oppenheimer.2023.1080p.BluRay                        → "Oppenheimer",     year=2023
      • Plaha.S01E10.The.Jackals.1080p.10bit.NF.WEB-DL       → "Plaha",           s=1, ep=10
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
    # Step 8: detect season AND episode — SxxExx gives both
    sxxexx_match  = re.search(r"\bS(\d{1,2})E(\d{1,3})\b", clean, re.I)
    season_match  = sxxexx_match
    ep_from_sxxexx: int | None = int(sxxexx_match.group(2)) if sxxexx_match else None
    if not season_match:
        season_match = re.search(r"\bS(\d{1,2})\b", clean, re.I)
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
    # Pattern: [Group] Series Name 14 [][Quality] → "Series Name", ep=14
    _is_anime_style = (
        bool(re.match(r"^\s*\[", file_name_orig)) or
        bool(re.search(r"\]\s*\[", file_name_orig))
    )
    anime_ep: int | None = None
    if _is_anime_style and not season_match:
        ep_strip = re.search(r"\s+(\d{1,4})\s*$", title)
        if ep_strip:
            prefix = title[:ep_strip.start()].strip()
            if prefix:
                anime_ep = int(ep_strip.group(1))
                title    = prefix

    episode_number: int | None = ep_from_sxxexx if ep_from_sxxexx is not None else anime_ep

    return (
        title or clean.strip(),
        year_match.group(1)   if year_match   else None,
        season_match.group(1) if season_match else None,
        episode_number,
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
    kind: str | None    = None,    # "movie" / "series" / None
    episode: int | None = None,    # episode number, for series grouping
) -> str:
    """
    Produce a /getlist line:
      🎬 KGF Chapter 2 (2022) — Malayalam, Tamil | 1080P
      📺 Blue Lock — Ep 14, 15, 16  (episodes merged in _build_summary_page)

    For series, a hidden metadata prefix is embedded so _build_summary_page can
    group all episodes of the same show into one line:
      ##SERIES##<key>##EP##<n>##LANG##<lang>##QUAL##<quality>##TITLE##<display>
    """
    is_series = kind == "series" or re.search(r"\bS\d{2}\b", display_name)

    # Strip S01/S02 suffix to get bare series title
    base_title = re.sub(r"\s+S\d{2}$", "", display_name, flags=re.I).strip()

    if not is_series:
        # ── MOVIE ────────────────────────────────────────────────────────────
        name = base_title
        if year and str(year) not in name:
            name = f"{name} ({year})"
        extras: list[str] = []
        if lang:
            extras.append(lang)
        if quality:
            extras.append(quality)
        line = f"🎬 <b>{_esc(name)}</b>"
        if extras:
            line += f" — {' | '.join(extras)}"
        return line

    # ── SERIES ───────────────────────────────────────────────────────────────
    # Embed structured metadata so _build_summary_page can group episodes
    series_key = re.sub(r"[^a-z0-9 ]", "", base_title.lower()).strip()
    ep_num     = episode if episode is not None else 0
    lang_val   = lang    or ""
    qual_val   = quality or ""
    return (
        f"##SERIES##{series_key}"
        f"##EP##{ep_num}"
        f"##LANG##{lang_val}"
        f"##QUAL##{qual_val}"
        f"##TITLE##{_esc(base_title)}"
    )


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


def _resolve_group_entry(entry: str) -> tuple[str, str, str, str]:
    """
    Parse any entry format → (emoji, title, lang, qual).
    Handles ##SERIES## metadata, already-formatted 🎬/📺 lines, and raw names.
    """
    if entry.startswith("##SERIES##"):
        try:
            rest         = entry[len("##SERIES##"):]
            _key,  rest  = rest.split("##EP##",    1)
            _ep,   rest  = rest.split("##LANG##",  1)
            lang,  rest  = rest.split("##QUAL##",  1)
            qual,  title = rest.split("##TITLE##", 1)
            return "📺", title.strip(), lang.strip(), qual.strip()
        except (ValueError, AttributeError):
            pass

    # Already-formatted line: strip emoji prefix for clean re-render
    for emoji in ("🎬", "📺"):
        if entry.startswith(emoji):
            # e.g. "🎬 <b>KGF Chapter 2 (2022)</b> — Malayalam | 1080P"
            # Just return the whole line as title; no extras to split cleanly
            return emoji, entry[2:].strip(), "", ""

    return "🎬", entry.strip(), "", ""


async def _flush_group_to_channels(bot: Client, entries: list[str]) -> None:
    """
    Send a beautifully formatted numbered list of up to GROUP_SIZE titles
    to every update channel. No inline keyboard, no callbacks.

    Layout:
    ╔══════════════════════════════╗
       🎬 New Additions  [date]
       25 movies & series
    ══════════════════════════════
     1. 🎬 KGF Chapter 2 (2022)
           Malayalam | 1080P
     2. 📺 Blue Lock
    ...
    ══════════════════════════════
       🔍 Search movies → @bot
    ╚══════════════════════════════╝
    """
    if not entries:
        return

    channel_ids = await db.get_update_chat_ids()
    now         = datetime.now(timezone.utc)
    today       = now.strftime("%d %b %Y")          # e.g. "02 May 2026"

    # Count movies vs series for the subtitle
    movies  = sum(1 for e in entries if not e.startswith("##SERIES##") and not e.startswith("📺"))
    series  = len(entries) - movies
    if movies and series:
        subtitle = f"<i>{movies} movie{'s' if movies > 1 else ''} · {series} series</i>"
    elif movies:
        subtitle = f"<i>{movies} movie{'s' if movies > 1 else ''}</i>"
    else:
        subtitle = f"<i>{series} series</i>"

    divider = "─" * 28

    lines: list[str] = [
        f"<b>🎬  New Additions</b>  <code>[{today}]</code>",
        subtitle,
        f"<code>{divider}</code>",
        "",
    ]

    for i, entry in enumerate(entries, 1):
        emoji, title, lang, qual = _resolve_group_entry(entry)

        # Build extras tag line (lang / quality)
        extras_parts: list[str] = []
        if lang:
            extras_parts.append(lang)
        if qual:
            extras_parts.append(qual)
        extras = "  <i>" + " · ".join(extras_parts) + "</i>" if extras_parts else ""

        index_str = f"{i:>2}."
        lines.append(f"<code>{index_str}</code> {emoji} {title}{extras}")

    lines += [
        "",
        f"<code>{divider}</code>",
        f"<b>{GROUP_SEARCH_TEXT}</b>",
    ]

    text = "\n".join(lines)

    for cid in channel_ids:
        try:
            await bot.send_message(
                cid, text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as exc:
            logger.warning("Failed sending group update to channel %s: %s", cid, exc)


async def _send_to_channels(
    bot: Client,
    text: str,
    markup: InlineKeyboardMarkup,
    display_name: str,
    imdb_key: str,                   # dedup key
    list_entry: str | None = None,   # pre-formatted /getlist line
) -> int:
    """
    Route to the correct send strategy based on CHANNEL_SEND_MODE.

    • "individual" — send each title as its own IMDb card message (original behaviour).
    • "grouped"    — accumulate entries in _pending_group; flush as a plain numbered
                     list to channels every GROUP_SIZE items (no callbacks).

    Returns 1 when the item was accepted/recorded, 0 on dedup skip.
    """
    global _pending_group

    # ── Always record the announced key and daily-added entry first ───────────
    await db.add_announced_key(imdb_key)
    await db.add_daily_added(list_entry or display_name)
    logger.info("✅ Recorded: %s", display_name)

    if CHANNEL_SEND_MODE == "individual":
        # ── Original behaviour: one IMDb card per title ───────────────────────
        channel_ids = await db.get_update_chat_ids()
        sent = 0
        for cid in channel_ids:
            try:
                await bot.send_message(
                    cid, text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=markup,
                )
                sent += 1
            except Exception as exc:
                logger.warning("Failed sending update to channel %s: %s", cid, exc)
        return sent

    else:
        # ── Grouped / Manual mode: accumulate entries ─────────────────────────
        _pending_group.append(list_entry or display_name)
        logger.debug("Group buffer: %d/%d", len(_pending_group), GROUP_SIZE)

        # In "manual" mode we never auto-flush — admin uses /sendupnow
        if CHANNEL_SEND_MODE == "grouped" and len(_pending_group) >= GROUP_SIZE:
            batch          = _pending_group[:GROUP_SIZE]
            _pending_group = _pending_group[GROUP_SIZE:]
            await _flush_group_to_channels(bot, batch)

        return 1


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
    title, year, season, episode = parse_title_year_and_season(file_name)

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
        episode = episode,
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

@Client.on_message(filters.command(["latest", "getlist"]) & filters.private)
async def latest_cmd(bot: Client, message) -> None:
    items = await db.get_daily_added()
    if not items:
        return await message.reply("📋 No movies/series added today yet.")

    total_pages  = max(1, -(-len(items) // PAGE_SIZE))
    today        = datetime.now(timezone.utc).date().isoformat()
    text, markup = _build_summary_page(items, 0, total_pages, today)
    await message.reply(text, parse_mode=ParseMode.HTML, reply_markup=markup)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGINATED DAILY SUMMARY  (20 items / page  •  Prev / Next buttons)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_raw_entry(raw: str) -> str:
    """
    Convert any raw/legacy stored string into a clean formatted line.
    Handles:
      • New metadata:  ##SERIES##...
      • Old formatted: 🎬 / 📺 already HTML
      • Raw filenames: [PiRO] Blue Lock 14 [][...] @MNTGX   → 📺 Blue Lock — Ep 14
                       KGF Chapter 2 2022 mal tam 1080p      → 🎬 KGF Chapter 2 (2022) — Malayalam, Tamil | 1080P
    """
    # Already-formatted HTML emoji lines — return as-is
    if raw.startswith(("🎬", "📺")):
        return raw

    # New metadata lines — caller handles these separately for grouping
    if raw.startswith("##SERIES##"):
        return raw  # pass through; grouped by _build_summary_page

    # ── Raw/legacy filename → parse on the fly ────────────────────────────
    title, year, season, episode = parse_title_year_and_season(raw)
    lang    = detect_language(raw)
    quality = extract_quality(raw)

    # Decide movie vs series:
    # series if has SxxExx, or has leading [Group] tag / multiple [] blocks (anime), or explicit season
    is_anime = bool(re.match(r"^\s*\[", raw)) or bool(re.search(r"\]\s*\[", raw))
    is_series = bool(season) or is_anime

    if is_series:
        # Return metadata string so caller can group episodes
        series_key = re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()
        ep_num     = episode if episode is not None else 0
        return (
            f"##SERIES##{series_key}"
            f"##EP##{ep_num}"
            f"##LANG##{lang or ''}"
            f"##QUAL##{quality or ''}"
            f"##TITLE##{_esc(title)}"
        )
    else:
        name = title
        if year and str(year) not in name:
            name = f"{name} ({year})"
        extras: list[str] = []
        if lang:
            extras.append(lang)
        if quality:
            extras.append(quality)
        line = f"🎬 <b>{_esc(name)}</b>"
        if extras:
            line += f" — {' | '.join(extras)}"
        return line


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

    # ── Pass 1: normalise every item (raw filenames → metadata or formatted) ─
    normalised = [_parse_raw_entry(x) for x in chunk]

    # ── Pass 2: build body, grouping series episodes ──────────────────────────
    # Use a list for insertion-order and a dict for per-series state.
    # Non-series lines are appended directly; first occurrence of a series key
    # inserts a placeholder; subsequent occurrences just add their episode number.

    body_lines: list[str | None] = []   # None = placeholder for a series slot
    series_slots: dict[str, dict] = {}  # key → {slot_index, lang, qual, title, episodes}

    for item in normalised:
        if item.startswith("##SERIES##"):
            try:
                rest        = item[len("##SERIES##"):]
                key,  rest  = rest.split("##EP##",    1)
                ep,   rest  = rest.split("##LANG##",  1)
                lang, rest  = rest.split("##QUAL##",  1)
                qual, title = rest.split("##TITLE##", 1)
                key   = key.strip()
                ep    = int(ep.strip())
                lang  = lang.strip()
                qual  = qual.strip()
                title = title.strip()
            except (ValueError, AttributeError):
                body_lines.append(f"• {_esc(item)}")
                continue

            if key not in series_slots:
                series_slots[key] = {
                    "slot":     len(body_lines),
                    "lang":     lang,
                    "qual":     qual,
                    "title":    title,
                    "episodes": set(),
                }
                body_lines.append(None)          # placeholder
            if ep > 0:
                series_slots[key]["episodes"].add(ep)

        elif item.startswith(("🎬", "📺")):
            body_lines.append(item)
        else:
            body_lines.append(f"• {_esc(item)}")

    # ── Pass 3: fill series placeholders ─────────────────────────────────────
    for data in series_slots.values():
        eps   = sorted(data["episodes"])
        title = data["title"]
        lang  = data["lang"]
        qual  = data["qual"]

        line = f"📺 <b>{title}</b>"
        parts: list[str] = []
        if eps:
            parts.append(f"Ep {', '.join(str(e) for e in eps)}")
        if lang:
            parts.append(lang)
        if qual:
            parts.append(qual)
        if parts:
            line += f" — {' | '.join(parts)}"

        body_lines[data["slot"]] = line

    body = "\n".join(ln for ln in body_lines if ln is not None)
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
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
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
        await bot.send_message(cid, text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except Exception as exc:
        logger.warning("Failed sending summary to %s: %s", cid, exc)


# ══════════════════════════════════════════════════════════════════════════════
#  BACKGROUND TASK: nightly summary
# ══════════════════════════════════════════════════════════════════════════════

async def run_daily_summary(bot: Client) -> None:
    """
    Background task that runs forever.

    • In "individual" mode  → sends the paginated /getlist summary to channels
      at 23:55 UTC (original nightly-summary behaviour).
    • In "grouped" mode     → flushes any leftover titles that did not fill a
      full GROUP_SIZE batch, once per day at 23:55 UTC, so nothing is lost.
    """
    last_summary_date: str | None = None

    while True:
        now   = datetime.now(timezone.utc)
        today = now.date().isoformat()

        if now.hour == 23 and now.minute >= 55:
            if last_summary_date != today and not await db.is_daily_summary_done(today):

                if CHANNEL_SEND_MODE == "individual":
                    # Original: send paginated summary to channels
                    items = await db.get_daily_added()
                    for cid in await db.get_update_chat_ids():
                        await _send_paginated_summary(bot, cid, items)

                else:
                    # Grouped: flush any partial batch that never hit GROUP_SIZE
                    global _pending_group
                    if _pending_group:
                        leftover       = _pending_group[:]
                        _pending_group = []
                        await _flush_group_to_channels(bot, leftover)
                        logger.info("Flushed %d leftover grouped entries at end of day.", len(leftover))

                await db.mark_daily_summary_done(today)
                await db.clear_daily_added()
                last_summary_date = today

        await asyncio.sleep(60)


# ══════════════════════════════════════════════════════════════════════════════
#  /sendupnow  –  manually flush the grouped buffer to channels
#
#  Works in all modes:
#   • "grouped" / "manual" → flushes _pending_group now, in batches of GROUP_SIZE
#   • "individual"         → tells the admin nothing is pending (nothing to flush)
#
#  Flow:
#   1. Admin sends /sendupnow
#   2. Bot shows how many titles are buffered + a confirm/cancel keyboard
#   3. Admin taps ✅ Confirm → all pending titles are sent as grouped message(s)
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("sendupnow") & filters.user(ADMINS) & filters.private)
async def sendupnow_cmd(bot: Client, message) -> None:
    global _pending_group

    if CHANNEL_SEND_MODE == "individual":
        return await message.reply(
            "ℹ️ Bot is in <b>individual</b> mode — titles are sent instantly as they arrive.\n"
            "Switch <code>CHANNEL_SEND_MODE</code> to <code>grouped</code> or <code>manual</code> to use this command.",
            parse_mode=ParseMode.HTML,
        )

    count = len(_pending_group)
    if count == 0:
        return await message.reply(
            "📭 The buffer is empty — no pending titles to send.",
            parse_mode=ParseMode.HTML,
        )

    # Build a short preview of what's in the buffer (up to 10 titles)
    preview_lines = []
    for i, entry in enumerate(_pending_group[:10], 1):
        emoji, title, lang, qual = _resolve_group_entry(entry)
        preview_lines.append(f"  {i:>2}. {emoji} {title}")
    if count > 10:
        preview_lines.append(f"  … and {count - 10} more")

    batches = -(-count // GROUP_SIZE)   # ceiling division
    preview = "\n".join(preview_lines)

    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Send Now", callback_data="sendupnow:confirm"),
        InlineKeyboardButton("❌ Cancel",   callback_data="sendupnow:cancel"),
    ]])

    await message.reply(
        f"<b>📤 Ready to send {count} title(s) to channels</b>\n"
        f"Will be split into <b>{batches}</b> message(s) of up to {GROUP_SIZE} each.\n\n"
        f"<b>Pending titles:</b>\n{preview}\n\n"
        f"Tap <b>Send Now</b> to flush immediately.",
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )


@Client.on_callback_query(filters.regex(r"^sendupnow:(confirm|cancel)$") & filters.user(ADMINS))
async def sendupnow_callback(bot: Client, query) -> None:
    global _pending_group

    action = query.matches[0].group(1)

    if action == "cancel":
        await query.edit_message_text("❌ Cancelled. Buffer still has the pending titles.")
        await query.answer()
        return

    # ── Confirm: flush all pending entries in GROUP_SIZE batches ─────────────
    count = len(_pending_group)
    if count == 0:
        await query.edit_message_text("📭 Nothing in the buffer anymore.")
        await query.answer()
        return

    to_send        = _pending_group[:]
    _pending_group = []

    sent_batches = 0
    while to_send:
        batch    = to_send[:GROUP_SIZE]
        to_send  = to_send[GROUP_SIZE:]
        await _flush_group_to_channels(bot, batch)
        sent_batches += 1

    await query.edit_message_text(
        f"✅ Sent <b>{count}</b> title(s) across <b>{sent_batches}</b> message(s) to all update channels.",
        parse_mode=ParseMode.HTML,
    )
    await query.answer("Sent!", show_alert=False)


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
