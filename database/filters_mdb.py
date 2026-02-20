import logging

import pymongo
from pyrogram import enums

from info import DATABASE_NAME, DATABASE_URI
from database.sqldb import db_execute, db_fetchall, db_fetchone, libsql_mode, sqldb_enabled, get_conn

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

USE_SQLDB = sqldb_enabled()
USE_LIBSQL = libsql_mode()

if not USE_SQLDB:
    myclient = pymongo.MongoClient(DATABASE_URI)
    mydb = myclient[DATABASE_NAME]
elif not USE_LIBSQL:
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS filters (group_id TEXT NOT NULL, text TEXT NOT NULL, reply TEXT, btn TEXT, file TEXT, alert TEXT, PRIMARY KEY(group_id, text))"
        )
        conn.commit()


async def _ensure_schema():
    if USE_SQLDB:
        await db_execute(
            "CREATE TABLE IF NOT EXISTS filters (group_id TEXT NOT NULL, text TEXT NOT NULL, reply TEXT, btn TEXT, file TEXT, alert TEXT, PRIMARY KEY(group_id, text))"
        )


async def add_filter(grp_id, text, reply_text, btn, file, alert):
    if not USE_SQLDB:
        mycol = mydb[str(grp_id)]
        data = {'text': str(text), 'reply': str(reply_text), 'btn': str(btn), 'file': str(file), 'alert': str(alert)}
        try:
            mycol.update_one({'text': str(text)}, {"$set": data}, upsert=True)
        except Exception:
            logger.exception('Some error occured!', exc_info=True)
        return

    await _ensure_schema()
    await db_execute(
        """
        INSERT INTO filters(group_id, text, reply, btn, file, alert)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(group_id, text) DO UPDATE SET
            reply=excluded.reply,
            btn=excluded.btn,
            file=excluded.file,
            alert=excluded.alert
        """,
        (str(grp_id), str(text), str(reply_text), str(btn), str(file), str(alert)),
    )


async def find_filter(group_id, name):
    if not USE_SQLDB:
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

    row = await db_fetchone("SELECT reply, btn, alert, file FROM filters WHERE group_id=? AND text=? LIMIT 1", (str(group_id), str(name)))
    if not row:
        return None, None, None, None
    return row['reply'], row['btn'], row['alert'], row['file']


async def get_filters(group_id):
    if not USE_SQLDB:
        mycol = mydb[str(group_id)]
        texts = []
        for file in mycol.find():
            texts.append(file['text'])
        return texts

    rows = await db_fetchall("SELECT text FROM filters WHERE group_id=?", (str(group_id),))
    return [r['text'] for r in rows]


async def delete_filter(message, text, group_id):
    if not USE_SQLDB:
        mycol = mydb[str(group_id)]
        myquery = {'text': text}
        query = mycol.count_documents(myquery)
        if query == 1:
            mycol.delete_one(myquery)
            await message.reply_text(f"'`{text}`'  deleted. I'll not respond to that filter anymore.", quote=True, parse_mode=enums.ParseMode.MARKDOWN)
        else:
            await message.reply_text("Couldn't find that filter!", quote=True)
        return

    row = await db_fetchone("SELECT 1 as ok FROM filters WHERE group_id=? AND text=?", (str(group_id), str(text)))
    if row:
        await db_execute("DELETE FROM filters WHERE group_id=? AND text=?", (str(group_id), str(text)))
        await message.reply_text(f"'`{text}`'  deleted. I'll not respond to that filter anymore.", quote=True, parse_mode=enums.ParseMode.MARKDOWN)
    else:
        await message.reply_text("Couldn't find that filter!", quote=True)


async def del_all(message, group_id, title):
    if not USE_SQLDB:
        if str(group_id) not in mydb.list_collection_names():
            await message.edit_text(f"Nothing to remove in {title}!")
            return
        try:
            mydb[str(group_id)].drop()
            await message.edit_text(f"All filters from {title} has been removed")
        except Exception:
            await message.edit_text("Couldn't remove all filters from group!")
        return

    await db_execute("DELETE FROM filters WHERE group_id=?", (str(group_id),))
    await message.edit_text(f"All filters from {title} has been removed")


async def count_filters(group_id):
    if not USE_SQLDB:
        count = mydb[str(group_id)].count()
        return False if count == 0 else count

    row = await db_fetchone("SELECT COUNT(*) as count FROM filters WHERE group_id=?", (str(group_id),))
    count = int(row['count']) if row else 0
    return False if count == 0 else count


async def filter_stats():
    if not USE_SQLDB:
        collections = mydb.list_collection_names()
        if "CONNECTION" in collections:
            collections.remove("CONNECTION")
        totalcount = 0
        for collection in collections:
            totalcount += mydb[collection].count()
        return len(collections), totalcount

    row = await db_fetchone("SELECT COUNT(DISTINCT group_id) as groups, COUNT(*) as total FROM filters")
    if not row:
        return 0, 0
    return int(row['groups']), int(row['total'])
