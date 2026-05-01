from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.types import Message
from database.ia_filterdb import get_movie_list, get_series_grouped
import re

LANGS = {
    'mal': 'malayalam', 'tam': 'tamil', 'hin': 'hindi', 'eng': 'english', 'kan': 'kannada', 'tel': 'telugu', 'multi': 'multi'
}

def extract_lang(name: str):
    low = name.lower()
    found = [v for k, v in LANGS.items() if re.search(rf'\b{k}\b', low)]
    return ', '.join(sorted(set(found))) if found else None

@Client.on_message(filters.private & filters.command("movies"))
async def list_movies(bot: Client, message: Message):
    movies = await get_movie_list(limit=40)
    if not movies:
        return await message.reply("❌ No recent movies found.")

    lines = ["<b>🎬 Latest Movies:</b>"]
    for movie_name in movies[:25]:
        clean = re.sub(r'[._\-]+', ' ', movie_name)
        title = re.sub(r'\s+', ' ', clean).strip()
        lang = extract_lang(title)
        lines.append(f"✅ <b>{title}</b>{' - ' + lang if lang else ''}")

    await message.reply('\n'.join(lines)[:4096], parse_mode=ParseMode.HTML)

@Client.on_message(filters.private & filters.command("series"))
async def list_series(bot: Client, message: Message):
    series_data = await get_series_grouped(limit=40)
    if not series_data:
        return await message.reply("❌ No recent series episodes found.")

    msg = ["<b>📺 Latest Series:</b>"]
    for title, episodes in series_data.items():
        ep_list = ", ".join(f"E{e:02d}" for e in episodes)
        msg.append(f"✅ <b>{title}</b> - {ep_list}")

    await message.reply("\n".join(msg)[:4096], parse_mode=ParseMode.HTML)
