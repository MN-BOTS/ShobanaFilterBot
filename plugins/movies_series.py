from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.types import Message
from database.ia_filterdb import get_movie_list, get_series_grouped
import re

LANGS = {
    "mal": "malayalam", "tam": "tamil", "hin": "hindi", "eng": "english", "kan": "kannada", "tel": "telugu", "multi": "multi"
}

def cleaned_movie_title(name: str):
    clean = re.sub(r"[._\-]+", " ", name)
    year = re.search(r"\b(19\d{2}|20\d{2})\b", clean)
    title = clean
    if year:
        title = clean.split(year.group(1))[0].strip()
        title = f"{title} ({year.group(1)})"
    title = re.sub(r"\b(1080p|720p|x264|x265|webrip|hdrip|blu ?ray|aac|esub|mkv|mp4)\b", "", title, flags=re.I)
    return re.sub(r"\s+", " ", title).strip(" -._")

def extract_lang(name: str):
    low = name.lower()
    found = [v for k, v in LANGS.items() if re.search(rf"\b{k}\b", low)]
    return ", ".join(sorted(set(found))) if found else None

@Client.on_message(filters.private & filters.command("movies"))
async def list_movies(bot: Client, message: Message):
    movies = await get_movie_list(limit=60)
    if not movies:
        return await message.reply("❌ No recent movies found.")

    movie_dict = {}
    for raw in movies:
        title = cleaned_movie_title(raw)
        if not title:
            continue
        if title not in movie_dict:
            movie_dict[title] = set()
        lang = extract_lang(raw)
        if lang:
            movie_dict[title].update(lang.split(", "))

    msg = "<b>🎬 Latest Movies:</b>\n\n"
    for title, langs in list(movie_dict.items())[:25]:
        msg += f"✅ <b>{title}</b>"
        if langs:
            msg += f" - {', '.join(sorted(langs))}"
        msg += "\n"

    await message.reply(msg[:4096], parse_mode=ParseMode.HTML)

@Client.on_message(filters.private & filters.command("series"))
async def list_series(bot: Client, message: Message):
    series_data = await get_series_grouped(limit=40)
    if not series_data:
        return await message.reply("❌ No recent series episodes found.")

    msg = "<b>📺 Latest Series:</b>\n\n"
    for title, episodes in series_data.items():
        ep_list = ", ".join(f"E{e:02d}" for e in episodes)
        msg += f"✅ <b>{title}</b> - {ep_list}\n"

    await message.reply(msg[:4096], parse_mode=ParseMode.HTML)
