import random
import re, asyncio, time, shutil, psutil, os, sys
from pyrogram import Client, filters, enums
from pyrogram.types import *
from info import BOT_START_TIME, ADMINS
from utils import humanbytes  

CMD = ["/", "."]

@Client.on_message(filters.command("ping", CMD) & filters.user(ADMINS))
async def ping(_, message):
    start_t = time.time()
    rm = await message.reply_text("...........")
    end_t = time.time()
    time_taken_s = (end_t - start_t) * 1000
    await rm.edit(f"Ping!\n{time_taken_s:.3f} ms")

@Client.on_message(filters.command("usage") & filters.user(ADMINS))          
async def stats(bot, update):
    currentTime = time.strftime("%Hh%Mm%Ss", time.gmtime(time.time() - BOT_START_TIME))
    total, used, free = shutil.disk_usage(".")
    total = humanbytes(total)
    used = humanbytes(used)
    free = humanbytes(free)
    cpu_usage = psutil.cpu_percent()
    ram_usage = psutil.virtual_memory().percent
    disk_usage = psutil.disk_usage('/').percent

    ms_g = f"""<b>⚙️ Bot Status</b>

🕔 Uptime: <code>{currentTime}</code>
🛠 CPU Usage: <code>{cpu_usage}%</code>
🗜 RAM Usage: <code>{ram_usage}%</code>
🗂 Total Disk Space: <code>{total}</code>
🗳 Used Space: <code>{used} ({disk_usage}%)</code>
📝 Free Space: <code>{free}</code> """

    msg = await bot.send_message(chat_id=update.chat.id, text="__Processing...__", parse_mode=enums.ParseMode.MARKDOWN)
    await msg.edit_text(text=ms_g, parse_mode=enums.ParseMode.HTML)

@Client.on_message(filters.command("restart") & filters.user(ADMINS))
async def stop_button(bot, message):
    msg = await bot.send_message(text="**Bot is restarting...**", chat_id=message.chat.id)
    await asyncio.sleep(3)
    await msg.edit("**Bot restarted successfully. Ready to go.**")
    os.execl(sys.executable, sys.executable, *sys.argv)
