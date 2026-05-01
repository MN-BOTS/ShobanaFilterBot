from pyrogram import Client, filters
from info import CHANNELS
from database.ia_filterdb import save_file
from plugins.new_updates import post_new_content_update

media_filter = filters.document | filters.video | filters.audio


@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    """Media Handler"""
    for file_type in ("document", "video"):
        media = getattr(message, file_type, None)
        if media is not None:
            break
    else:
        return

    media.file_type = file_type
    media.caption = message.caption
    saved, _ = await save_file(media)
    if saved:
        await post_new_content_update(bot, getattr(media, "file_name", ""))
