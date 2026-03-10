import logging

import pymongo
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
    mycol = mydb['CONNECTION']


async def add_connection(group_id, user_id):
    if USE_MONGO:
        query = mycol.find_one({"_id": user_id}, {"_id": 0, "active_group": 0})
        if query is not None and group_id in [x["group_id"] for x in query["group_details"]]:
            return False
        group_details = {"group_id": group_id}
        data = {'_id': user_id, 'group_details': [group_details], 'active_group': group_id}
        if mycol.count_documents({"_id": user_id}) == 0:
            mycol.insert_one(data)
            return True
        mycol.update_one({'_id': user_id}, {"$push": {"group_details": group_details}, "$set": {"active_group": group_id}})
        return True

    with store.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM connections WHERE user_id=:u AND group_id=:g"), {"u": user_id, "g": group_id}).first()
        if exists:
            return False
        conn.execute(text("UPDATE connections SET is_active=FALSE WHERE user_id=:u"), {"u": user_id})
        conn.execute(text("INSERT INTO connections(user_id, group_id, is_active) VALUES (:u,:g,TRUE)"), {"u": user_id, "g": group_id})
    return True


async def active_connection(user_id):
    if USE_MONGO:
        query = mycol.find_one({"_id": user_id}, {"_id": 0, "group_details": 0})
        if not query:
            return None
        group_id = query['active_group']
        return int(group_id) if group_id is not None else None

    with store.begin() as conn:
        row = conn.execute(text("SELECT group_id FROM connections WHERE user_id=:u AND is_active=TRUE"), {"u": user_id}).first()
        return int(row[0]) if row else None


async def all_connections(user_id):
    if USE_MONGO:
        query = mycol.find_one({"_id": user_id}, {"_id": 0, "active_group": 0})
        return [x["group_id"] for x in query["group_details"]] if query is not None else None

    with store.begin() as conn:
        rows = conn.execute(text("SELECT group_id FROM connections WHERE user_id=:u"), {"u": user_id}).fetchall()
        return [r[0] for r in rows] if rows else None


async def if_active(user_id, group_id):
    if USE_MONGO:
        query = mycol.find_one({"_id": user_id}, {"_id": 0, "group_details": 0})
        return query is not None and query['active_group'] == group_id

    with store.begin() as conn:
        row = conn.execute(text("SELECT 1 FROM connections WHERE user_id=:u AND group_id=:g AND is_active=TRUE"), {"u": user_id, "g": group_id}).first()
        return bool(row)


async def make_active(user_id, group_id):
    if USE_MONGO:
        update = mycol.update_one({'_id': user_id}, {"$set": {"active_group": group_id}})
        return update.modified_count != 0

    with store.begin() as conn:
        conn.execute(text("UPDATE connections SET is_active=FALSE WHERE user_id=:u"), {"u": user_id})
        res = conn.execute(text("UPDATE connections SET is_active=TRUE WHERE user_id=:u AND group_id=:g"), {"u": user_id, "g": group_id})
        return res.rowcount != 0


async def make_inactive(user_id):
    if USE_MONGO:
        update = mycol.update_one({'_id': user_id}, {"$set": {"active_group": None}})
        return update.modified_count != 0

    with store.begin() as conn:
        res = conn.execute(text("UPDATE connections SET is_active=FALSE WHERE user_id=:u"), {"u": user_id})
        return res.rowcount != 0


async def delete_connection(user_id, group_id):
    if USE_MONGO:
        try:
            update = mycol.update_one({"_id": user_id}, {"$pull": {"group_details": {"group_id": group_id}}})
            if update.modified_count == 0:
                return False
            query = mycol.find_one({"_id": user_id}, {"_id": 0})
            if len(query["group_details"]) >= 1 and query['active_group'] == group_id:
                prvs_group_id = query["group_details"][-1]["group_id"]
                mycol.update_one({'_id': user_id}, {"$set": {"active_group": prvs_group_id}})
            elif len(query["group_details"]) == 0:
                mycol.update_one({'_id': user_id}, {"$set": {"active_group": None}})
            return True
        except Exception as e:
            logger.exception(f'Some error occurred! {e}', exc_info=True)
            return False

    with store.begin() as conn:
        res = conn.execute(text("DELETE FROM connections WHERE user_id=:u AND group_id=:g"), {"u": user_id, "g": group_id})
        if res.rowcount == 0:
            return False
        active = conn.execute(text("SELECT 1 FROM connections WHERE user_id=:u AND is_active=TRUE"), {"u": user_id}).first()
        if not active:
            latest = conn.execute(text("SELECT group_id FROM connections WHERE user_id=:u ORDER BY group_id DESC LIMIT 1"), {"u": user_id}).first()
            if latest:
                conn.execute(text("UPDATE connections SET is_active=TRUE WHERE user_id=:u AND group_id=:g"), {"u": user_id, "g": latest[0]})
        return True
