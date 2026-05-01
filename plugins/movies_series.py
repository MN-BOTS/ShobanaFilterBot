from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database.ia_filterdb import get_movie_list, get_series_grouped
import re

PAGE_SIZE = 10
MOVIE_CACHE = {}
SERIES_CACHE = {}
LANGS = {"mal":"malayalam","tam":"tamil","hin":"hindi","eng":"english","kan":"kannada","tel":"telugu"}


def cleaned_movie_title(name: str):
    clean = re.sub(r"[._\-]+", " ", name)
    year = re.search(r"\b(19\d{2}|20\d{2})\b", clean)
    title = clean.split(year.group(1))[0].strip() if year else clean
    title = re.sub(r"\b(1080p|720p|480p|x264|x265|webrip|hdrip|web-dl|blu ?ray|aac|esub|mkv|mp4)\b", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" -._")
    return f"{title} ({year.group(1)})" if year else title


def extract_lang_quality(raw: str):
    low = raw.lower()
    langs = sorted({v for k, v in LANGS.items() if re.search(rf"\b{k}\b", low)})
    q = re.search(r"\b(2160p|1080p|720p|480p|hq|hd)\b", low)
    return langs, (q.group(1).upper() if q else None)


def build_page(items, page, head, kind):
    start = page * PAGE_SIZE
    chunk = items[start:start+PAGE_SIZE]
    text = f"<b>{head}</b>\n\n" + "\n".join(chunk)
    buttons = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"{kind}_pg#{page-1}"))
    if start + PAGE_SIZE < len(items):
        row.append(InlineKeyboardButton("Next ▶️", callback_data=f"{kind}_pg#{page+1}"))
    if row:
        buttons.append(row)
    return text, InlineKeyboardMarkup(buttons) if buttons else None


@Client.on_message(filters.private & filters.command("movies"))
async def list_movies(bot: Client, message: Message):
    movies = await get_movie_list(limit=120)
    if not movies:
        return await message.reply("❌ No recent movies found.")

    grouped = {}
    for raw in movies:
        low = raw.lower()
        if not re.search(r"\b(19\d{2}|20\d{2})\b", raw):
            continue
        if re.search(r"\b(episode|ep\s*\d+|e\d{1,3}|s\d{1,2}|season\s*\d+)\b", low):
            continue
        year = re.search(r"\b(19\d{2}|20\d{2})\b", raw)
        before_year = re.split(rf"\b{year.group(1)}\b", re.sub(r"[._\-]+", " ", raw), maxsplit=1)[0].strip() if year else cleaned_movie_title(raw)
        title = f"{before_year} {year.group(1)}".strip() if year else cleaned_movie_title(raw)
        langs, quality = extract_lang_quality(raw)
        data = grouped.setdefault(title, {"langs": set(), "qualities": set()})
        data["langs"].update(langs)
        if quality:
            data["qualities"].add(quality)

    lines = []
    for title, data in grouped.items():
        ln = f"✅ <b>{title}</b>"
        extras = []
        if data["langs"]:
            extras.append(", ".join(sorted(data["langs"])))
        if data["qualities"]:
            extras.append(", ".join(sorted(data["qualities"])))
        if extras:
            ln += f" - {' | '.join(extras)}"
        lines.append(ln)

    MOVIE_CACHE[message.from_user.id] = lines
    text, markup = build_page(lines, 0, "🎬 Latest Movies", "mv")
    await message.reply(text[:4096], parse_mode=ParseMode.HTML, reply_markup=markup)


@Client.on_message(filters.private & filters.command("series"))
async def list_series(bot: Client, message: Message):
    series_data = await get_series_grouped(limit=80)
    if not series_data:
        return await message.reply("❌ No recent series episodes found.")

    lines = [f"✅ <b>{title}</b> - Episodes {', '.join(f'E{e:02d}' for e in episodes)}" for title, episodes in series_data.items()]
    SERIES_CACHE[message.from_user.id] = lines
    text, markup = build_page(lines, 0, "📺 Latest Series", "sr")
    await message.reply(text[:4096], parse_mode=ParseMode.HTML, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^(mv|sr)_pg#"))
async def movies_series_pages(bot: Client, query: CallbackQuery):
    kind, page = query.data.split("#")
    page = int(page)
    items = MOVIE_CACHE.get(query.from_user.id, []) if kind == "mv_pg" else SERIES_CACHE.get(query.from_user.id, [])
    if not items:
        return await query.answer("No cached list. Use /movies or /series again.", show_alert=True)
    head = "🎬 Latest Movies" if kind == "mv_pg" else "📺 Latest Series"
    prefix = "mv" if kind == "mv_pg" else "sr"
    text, markup = build_page(items, page, head, prefix)
    await query.message.edit_text(text[:4096], parse_mode=ParseMode.HTML, reply_markup=markup)
    await query.answer()
