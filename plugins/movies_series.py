#  @MrMNTG @MusammilN
#please give credits https://github.com/MN-BOTS/ShobanaFilterBot
from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.types import Message
from database.ia_filterdb import get_movie_list, get_series_grouped
import re

@Client.on_message(filters.private & filters.command("movies"))
async def list_movies(bot: Client, message: Message):
    movies = await get_movie_list()
    if not movies:
        return await message.reply("❌ No recent movies found.")
    
    # Group movies by name and collect all languages
    movie_dict = {}
    for movie_name in movies:
        # Extract movie name and year using regex
        match = re.search(r'^(.*?)\s*\((\d{4})\)', movie_name)
        if match:
            name = match.group(1).strip()
            year = match.group(2)
            key = f"{name} ({year})"
            
            # Extract language
            lang_match = re.search(r'(mal|tam|hin|eng|multi)', movie_name.lower())
            if lang_match:
                lang = lang_match.group(1)
                if lang == 'mal':
                    lang_display = 'malayalam'
                elif lang == 'tam':
                    lang_display = 'tamil'
                elif lang == 'hin':
                    lang_display = 'hindi'
                elif lang == 'eng':
                    lang_display = 'english'
                else:
                    lang_display = 'multi'
                
                if key not in movie_dict:
                    movie_dict[key] = set()
                movie_dict[key].add(lang_display)
    
    # Format the message
    msg = "<b>🎬 Latest Movies:</b>\n\n"
    for movie_name, languages in movie_dict.items():
        if languages:
            languages_str = ", ".join(sorted(languages))
            msg += f"✅ <b>{movie_name}</b> - {languages_str}\n"
        else:
            msg += f"✅ <b>{movie_name}</b>\n"
    
    await message.reply(msg[:4096], parse_mode=ParseMode.HTML)

#  @MrMNTG @MusammilN
#please give credits https://github.com/MN-BOTS/ShobanaFilterBot
@Client.on_message(filters.private & filters.command("series"))
async def list_series(bot: Client, message: Message):
    series_data = await get_series_grouped()
    if not series_data:
        return await message.reply("❌ No recent series episodes found.")
    
    msg = "<b>📺 Latest Series:</b>\n\n"
    for title, episodes in series_data.items():
        ep_list = ", ".join(str(e) for e in episodes)
        msg += f"✅ <b>{title}</b> - Episodes {ep_list}\n"

    await message.reply(msg[:4096], parse_mode=ParseMode.HTML)

#  @MrMNTG @MusammilN
#please give credits https://github.com/MN-BOTS/ShobanaFilterBot
