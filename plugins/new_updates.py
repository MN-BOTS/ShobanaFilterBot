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

LANG_MAP = {
    "mal": "Malayalam",
    "eng": "English",
    "tam": "Tamil",
    "hin": "Hindi",
    "kan": "Kannada",
    "tel": "Telugu",
}



def normalize_compact_title(title: str) -> str:
    parts = title.split()
    compact = []
    i = 0
    while i < len(parts):
        if len(parts[i]) == 1 and parts[i].isalpha():
            letters = [parts[i]]
            j = i + 1
            while j < len(parts) and len(parts[j]) == 1 and parts[j].isalpha():
                letters.append(parts[j])
                j += 1
            if len(letters) >= 2:
                compact.append(''.join(letters))
                i = j
                continue
        compact.append(parts[i])
        i += 1
    return ' '.join(compact)

def parse_title_year_and_season(file_name: str):
    clean = re.sub(r"[._\-]+", " ", file_name)
    year_match = re.search(r"\b((?:19|20)\d{2})\b", clean)
    season_match = re.search(r"\b(?:s(?:eason)?\s*0?(\d{1,2}))\b", clean, re.I)
    title = clean
    if year_match:
        title = clean.split(year_match.group(1))[0].strip(" -._")
    title = re.sub(r"\b(s\d{1,2}e\d{1,3}|season\s*\d+|episode\s*\d+|ep\s*\d+|e\d{1,3})\b", "", title, flags=re.I).strip()
    title = re.sub(r"\b(1080p|720p|480p|x264|x265|webrip|hdrip|web-dl|blu ?ray|aac|esub|mkv|mp4|hdtv|hq)\b", "", title, flags=re.I).strip()
    title = normalize_compact_title(re.sub(r"\s+", " ", title)).strip()
    return title.strip() or clean.strip(), year_match.group(1) if year_match else None, season_match.group(1) if season_match else None


def detect_language(file_name: str):
    low = file_name.lower()
    found = [v for k, v in LANG_MAP.items() if re.search(rf"\b{k}\b", low)]
    return ", ".join(found) if found else None


async def should_post_update(file_name: str):
    title, year, season = parse_title_year_and_season(file_name)
    key = f"{title.lower()}::{year or 'na'}::s{season or '0'}"
    already = await db.check_announced_key(key)
    return not already, key, title, year


async def post_new_content_update(bot: Client, file_name: str):
    enabled = await db.get_new_updates_enabled()
    if not enabled:
        return

    should_send, key, title, _ = await should_post_update(file_name)
    if not should_send:
        return

    imdb = await get_poster(title, file=file_name)
    if not imdb:
        fallback = re.sub(r"\b(19\d{2}|20\d{2})\b", "", title).strip()
        imdb = await get_poster(fallback or title, file=file_name)
    if not imdb:
        return

    season = parse_title_year_and_season(file_name)[2]
    name = imdb.get("title") or title
    if season:
        name = f"{name} S{int(season):02d}"

    lang = detect_language(file_name)
    genre = imdb.get("genres") or "N/A"
    text = (
        f"🎬 <b>{name}</b>\n\n"
        f"• <b>Genre:</b> {genre}\n"
        + (f"• <b>Language:</b> {lang}\n" if lang else "") +
        f"• <b>IMDb:</b> ⭐ {imdb.get('rating', 'N/A')} | 📅 {imdb.get('year', 'N/A')} | 🎭 {imdb.get('kind', 'N/A')}\n"
        f"• <b>More:</b> {imdb.get('url', '')}"
    )
    bot_username = (await bot.get_me()).username
    start_key = re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_")
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Search in Bot", url=f"https://t.me/{bot_username}?start=mntgx_{start_key}")]])

    channel_ids = await db.get_update_chat_ids()
    for cid in channel_ids:
        try:
            await bot.send_message(cid, text, disable_web_page_preview=True, reply_markup=btn)
        except Exception as e:
            logger.warning("Failed sending new update to %s: %s", cid, e)

    await db.add_announced_key(key)
    await db.add_daily_added(name)


async def run_daily_summary(bot: Client):
    while True:
        await asyncio.sleep(600)
        now = datetime.now(timezone.utc)
        if now.hour == 23 and now.minute >= 55:
            if await db.is_daily_summary_done(now.date().isoformat()):
                continue
            items = await db.get_daily_added()
            if items:
                text = "<b>Today's Added Movies/Series</b>\n\n" + "\n".join(f"• {x}" for x in items)
                for cid in await db.get_update_chat_ids():
                    try:
                        await bot.send_message(cid, text)
                    except Exception:
                        pass
            await db.mark_daily_summary_done(now.date().isoformat())
            await db.clear_daily_added()


@Client.on_message(filters.command("setupchat") & filters.user(ADMINS))
async def setupchat_cmd(bot: Client, message):
    if len(message.command) < 2:
        chats = await db.get_update_chat_ids()
        return await message.reply(f"Current update chats: {', '.join(map(str, chats)) if chats else 'None'}")
    raw = " ".join(message.command[1:]).replace(" ", "")
    ids = [int(x) for x in raw.split(",") if x]
    await db.set_update_chat_ids(ids)
    await message.reply(f"✅ Update chats saved: {ids}")


@Client.on_message(filters.command("movieupdates") & filters.user(ADMINS))
async def toggle_updates(bot: Client, message):
    if len(message.command) < 2 or message.command[1].lower() not in {"on", "off"}:
        status = await db.get_new_updates_enabled()
        return await message.reply(f"Current status: {'ON' if status else 'OFF'}\nUsage: /movieupdates on|off")
    enabled = message.command[1].lower() == "on"
    await db.set_new_updates_enabled(enabled)
    await message.reply(f"✅ New movie/series updater {'enabled' if enabled else 'disabled'}")
