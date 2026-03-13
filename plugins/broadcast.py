#  @MrMNTG @MusammilN
#please give credits https://github.com/MN-BOTS/ShobanaFilterBot

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
import datetime
import time
import random
from database.users_chats_db import db
from info import ADMINS
from utils import broadcast_messages
import asyncio

BROADCAST_BATCH_SIZE = 500  # Now processes 500 users at a time
BROADCAST_SLEEP_MIN = 1  # Minimum sleep time in seconds
BROADCAST_SLEEP_MAX = 3  # Maximum sleep time in seconds

@Client.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast(bot, message):
    users = await db.get_all_users()
    b_msg = message.reply_to_message
    sts = await message.reply_text("Broadcasting your messages...")
    
    start_time = time.time()
    total_users = await db.total_users_count()
    done, blocked, deleted, failed, success = 0, 0, 0, 0, 0

    async def send_message(user):
        nonlocal success, blocked, deleted, failed
        user_id = int(user['id'])
        pti, sh = await broadcast_messages(user_id, b_msg)

        if pti:
            success += 1
        else:
            if sh == "Blocked":
                blocked += 1
                await db.delete_user(user_id)  # Remove blocked user
            elif sh == "Deleted":
                deleted += 1
                await db.delete_user(user_id)  # Remove deleted user
            elif sh == "Error":
                failed += 1

    tasks = []
    async for user in users:
        tasks.append(send_message(user))
        done += 1

        # Process messages in batches of 500
        if len(tasks) >= BROADCAST_BATCH_SIZE:
            try:
                await asyncio.gather(*tasks)
                tasks = []
                await sts.edit(
                    f"Broadcast in progress:\n\nTotal Users: {total_users}\nCompleted: {done} / {total_users}\n"
                    f"Success: {success} | Blocked: {blocked} | Deleted: {deleted} | Failed: {failed}"
                )
                # Random sleep between batches if no FloodWait
                sleep_time = random.uniform(BROADCAST_SLEEP_MIN, BROADCAST_SLEEP_MAX)
                await asyncio.sleep(sleep_time)
            except FloodWait as e:
                # If FloodWait occurs, wait for the specified time
                await sts.edit(
                    f"FloodWait: Waiting {e.value} seconds...\n\n"
                    f"Completed: {done} / {total_users}\n"
                    f"Success: {success} | Blocked: {blocked} | Deleted: {deleted} | Failed: {failed}"
                )
                await asyncio.sleep(e.value)
                tasks = []

    # Process remaining messages (if any)
    if tasks:
        try:
            await asyncio.gather(*tasks)
        except FloodWait as e:
            await sts.edit(
                f"FloodWait: Waiting {e.value} seconds...\n\n"
                f"Completed: {done} / {total_users}\n"
                f"Success: {success} | Blocked: {blocked} | Deleted: {deleted} | Failed: {failed}"
            )
            await asyncio.sleep(e.value)

    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
    await sts.edit(
        f"Broadcast Completed in {time_taken}.\n\nTotal Users: {total_users}\n"
        f"Success: {success} | Blocked: {blocked} | Deleted: {deleted} | Failed: {failed}"
    )


@Client.on_message(filters.command("grpbroadcast") & filters.user(ADMINS) & filters.reply)
async def grpbroadcast(bot, message):
    chats = await db.get_all_chats()
    b_msg = message.reply_to_message
    sts = await message.reply_text("Broadcasting your message to all groups...")

    start_time = time.time()
    total_chats = await db.total_chat_count()
    done, failed, success = 0, 0, 0

    async def send_group_message(chat):
        nonlocal success, failed
        chat_id = int(chat['id'])
        try:
            await b_msg.copy(chat_id=chat_id)
            success += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await b_msg.copy(chat_id=chat_id)
                success += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1

    tasks = []
    async for chat in chats:
        tasks.append(send_group_message(chat))
        done += 1

        if len(tasks) >= BROADCAST_BATCH_SIZE:
            await asyncio.gather(*tasks)
            tasks = []
            await sts.edit(
                f"Group broadcast in progress:\n\nTotal Groups: {total_chats}\nCompleted: {done} / {total_chats}\n"
                f"Success: {success} | Failed: {failed}"
            )
            sleep_time = random.uniform(BROADCAST_SLEEP_MIN, BROADCAST_SLEEP_MAX)
            await asyncio.sleep(sleep_time)

    if tasks:
        await asyncio.gather(*tasks)

    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
    await sts.edit(
        f"Group Broadcast Completed in {time_taken}.\n\nTotal Groups: {total_chats}\n"
        f"Success: {success} | Failed: {failed}"
    )

#  @MrMNTG @MusammilN
#please give credits https://github.com/MN-BOTS/ShobanaFilterBot
