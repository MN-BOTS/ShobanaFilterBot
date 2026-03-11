import logging

import pymongo
from pyrogram import enums
from sqlalchemy import text

from info import DATABASE_NAME, DATABASE_URI

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

USE_MONGO = bool(DATABASE_URI)

if not USE_MONGO:
    from database.sql_store import store

if USE_MONGO:
    myclient = pymongo.MongoClient(DATABASE_URI)
    mydb = myclient[DATABASE_NAME]


async def add_filter(grp_id, text_key, reply_text, btn, file, alert):
    if USE_MONGO:
        mycol = mydb[str(grp_id)]
        data = {'text': str(text_key), 'reply': str(reply_text), 'btn': str(btn), 'file': str(file), 'alert': str(alert)}
        mycol.update_one({'text': str(text_key)}, {"$set": data}, upsert=True)
        return

    with store.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM filters WHERE group_id=:g AND text_key=:t"), {"g": grp_id, "t": str(text_key)}).first()
        params = {"g": grp_id, "t": str(text_key), "r": str(reply_text), "b": str(btn), "f": str(file), "a": str(alert)}
        if exists:
            conn.execute(text("UPDATE filters SET reply_text=:r, btn=:b, file_id=:f, alert=:a WHERE group_id=:g AND text_key=:t"), params)
        else:
            conn.execute(text("INSERT INTO filters(group_id, text_key, reply_text, btn, file_id, alert) VALUES (:g,:t,:r,:b,:f,:a)"), params)


async def find_filter(group_id, name):
    if USE_MONGO:
        mycol = mydb[str(group_id)]
        query = mycol.find({"text": name})
        try:
            for file in query:
                reply_text = file['reply']
                btn = file['btn']
                fileid = file['file']
                alert = file.get('alert')
            return reply_text, btn, alert, fileid
        except Exception:
            return None, None, None, None

    with store.begin() as conn:
        row = conn.execute(text("SELECT reply_text, btn, alert, file_id FROM filters WHERE group_id=:g AND text_key=:t"), {"g": group_id, "t": name}).first()
        return (row[0], row[1], row[2], row[3]) if row else (None, None, None, None)


async def get_filters(group_id):
    if USE_MONGO:
        mycol = mydb[str(group_id)]
        return [file['text'] for file in mycol.find()]

    with store.begin() as conn:
        return [r[0] for r in conn.execute(text("SELECT text_key FROM filters WHERE group_id=:g"), {"g": group_id}).fetchall()]


async def delete_filter(message, text_key, group_id):
    if USE_MONGO:
        mycol = mydb[str(group_id)]
        myquery = {'text': text_key}
        if mycol.count_documents(myquery) == 1:
            mycol.delete_one(myquery)
            await message.reply_text(f"'`{text_key}`'  deleted. I'll not respond to that filter anymore.", quote=True, parse_mode=enums.ParseMode.MARKDOWN)
        else:
            await message.reply_text("Couldn't find that filter!", quote=True)
        return

    with store.begin() as conn:
        res = conn.execute(text("DELETE FROM filters WHERE group_id=:g AND text_key=:t"), {"g": group_id, "t": text_key})
    if res.rowcount:
        await message.reply_text(f"'`{text_key}`'  deleted. I'll not respond to that filter anymore.", quote=True, parse_mode=enums.ParseMode.MARKDOWN)
    else:
        await message.reply_text("Couldn't find that filter!", quote=True)


async def del_all(message, group_id, title):
    if USE_MONGO:
        if str(group_id) not in mydb.list_collection_names():
            await message.edit_text(f"Nothing to remove in {title}!")
            return
        mydb[str(group_id)].drop()
        await message.edit_text(f"All filters from {title} has been removed")
        return

    with store.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM filters WHERE group_id=:g"), {"g": group_id}).scalar() or 0
        if count == 0:
            await message.edit_text(f"Nothing to remove in {title}!")
            return
        conn.execute(text("DELETE FROM filters WHERE group_id=:g"), {"g": group_id})
        await message.edit_text(f"All filters from {title} has been removed")


async def count_filters(group_id):
    if USE_MONGO:
        mycol = mydb[str(group_id)]
        count = mycol.count()
        return False if count == 0 else count

    with store.begin() as conn:
        count = int(conn.execute(text("SELECT COUNT(*) FROM filters WHERE group_id=:g"), {"g": group_id}).scalar() or 0)
        return False if count == 0 else count


async def filter_stats():
    if USE_MONGO:
        collections = mydb.list_collection_names()
        if "CONNECTION" in collections:
            collections.remove("CONNECTION")
        totalcount = 0
        for collection in collections:
            totalcount += mydb[collection].count()
        return len(collections), totalcount

    with store.begin() as conn:
        totalcollections = int(conn.execute(text("SELECT COUNT(DISTINCT group_id) FROM filters")).scalar() or 0)
        totalcount = int(conn.execute(text("SELECT COUNT(*) FROM filters")).scalar() or 0)
        return totalcollections, totalcount
