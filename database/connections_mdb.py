import logging

import pymongo

from info import DATABASE_NAME, DATABASE_URI
from database.sqldb import db_execute, db_fetchall, db_fetchone, libsql_mode, sqldb_enabled, get_conn

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

USE_SQLDB = sqldb_enabled()
USE_LIBSQL = libsql_mode()

if not USE_SQLDB:
    myclient = pymongo.MongoClient(DATABASE_URI)
    mydb = myclient[DATABASE_NAME]
    mycol = mydb['CONNECTION']
elif not USE_LIBSQL:
    with get_conn() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS connections (user_id TEXT NOT NULL, group_id TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, group_id))")
        conn.commit()


async def _ensure_schema():
    if not USE_SQLDB:
        return
    await db_execute("CREATE TABLE IF NOT EXISTS connections (user_id TEXT NOT NULL, group_id TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, group_id))")


async def add_connection(group_id, user_id):
    if not USE_SQLDB:
        query = mycol.find_one({"_id": user_id}, {"_id": 0, "active_group": 0})
        if query is not None and group_id in [x["group_id"] for x in query["group_details"]]:
            return False
        data = {'_id': user_id, 'group_details': [{'group_id': group_id}], 'active_group': group_id}
        if mycol.count_documents({"_id": user_id}) == 0:
            mycol.insert_one(data)
        else:
            mycol.update_one({'_id': user_id}, {"$push": {"group_details": {"group_id": group_id}}, "$set": {"active_group": group_id}})
        return True

    await _ensure_schema()
    exists = await db_fetchone("SELECT 1 as ok FROM connections WHERE user_id=? AND group_id=?", (str(user_id), str(group_id)))
    if exists:
        return False
    await db_execute("UPDATE connections SET is_active=0 WHERE user_id=?", (str(user_id),))
    await db_execute("INSERT INTO connections(user_id, group_id, is_active) VALUES (?, ?, 1)", (str(user_id), str(group_id)))
    return True


async def active_connection(user_id):
    if not USE_SQLDB:
        query = mycol.find_one({"_id": user_id}, {"_id": 0, "group_details": 0})
        if not query:
            return None
        group_id = query['active_group']
        return int(group_id) if group_id is not None else None

    row = await db_fetchone("SELECT group_id FROM connections WHERE user_id=? AND is_active=1 LIMIT 1", (str(user_id),))
    if not row:
        return None
    try:
        return int(row['group_id'])
    except Exception:
        return row['group_id']


async def all_connections(user_id):
    if not USE_SQLDB:
        query = mycol.find_one({"_id": user_id}, {"_id": 0, "active_group": 0})
        return [x["group_id"] for x in query["group_details"]] if query is not None else None

    rows = await db_fetchall("SELECT group_id FROM connections WHERE user_id=?", (str(user_id),))
    return [r['group_id'] for r in rows] if rows else None


async def if_active(user_id, group_id):
    if not USE_SQLDB:
        query = mycol.find_one({"_id": user_id}, {"_id": 0, "group_details": 0})
        return query is not None and query['active_group'] == group_id

    row = await db_fetchone("SELECT 1 as ok FROM connections WHERE user_id=? AND group_id=? AND is_active=1", (str(user_id), str(group_id)))
    return row is not None


async def make_active(user_id, group_id):
    if not USE_SQLDB:
        update = mycol.update_one({'_id': user_id}, {"$set": {"active_group": group_id}})
        return update.modified_count != 0

    await db_execute("UPDATE connections SET is_active=0 WHERE user_id=?", (str(user_id),))
    await db_execute("UPDATE connections SET is_active=1 WHERE user_id=? AND group_id=?", (str(user_id), str(group_id)))
    return True


async def make_inactive(user_id):
    if not USE_SQLDB:
        update = mycol.update_one({'_id': user_id}, {"$set": {"active_group": None}})
        return update.modified_count != 0

    await db_execute("UPDATE connections SET is_active=0 WHERE user_id=?", (str(user_id),))
    return True


async def delete_connection(user_id, group_id):
    if not USE_SQLDB:
        try:
            update = mycol.update_one({"_id": user_id}, {"$pull": {"group_details": {"group_id": group_id}}})
            if update.modified_count == 0:
                return False
            query = mycol.find_one({"_id": user_id}, {"_id": 0})
            if len(query["group_details"]) >= 1 and query['active_group'] == group_id:
                prev = query["group_details"][-1]["group_id"]
                mycol.update_one({'_id': user_id}, {"$set": {"active_group": prev}})
            elif len(query["group_details"]) == 0:
                mycol.update_one({'_id': user_id}, {"$set": {"active_group": None}})
            return True
        except Exception as e:
            logger.exception(f'Some error occurred! {e}', exc_info=True)
            return False

    active = await db_fetchone("SELECT is_active FROM connections WHERE user_id=? AND group_id=?", (str(user_id), str(group_id)))
    await db_execute("DELETE FROM connections WHERE user_id=? AND group_id=?", (str(user_id), str(group_id)))
    if active and int(active.get('is_active', 0)) == 1:
        last = await db_fetchone("SELECT group_id FROM connections WHERE user_id=? ORDER BY rowid DESC LIMIT 1", (str(user_id),))
        if last:
            await db_execute("UPDATE connections SET is_active=1 WHERE user_id=? AND group_id=?", (str(user_id), last['group_id']))
    return True
