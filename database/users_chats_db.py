# https://github.com/odysseusmax/animated-lamp/blob/master/bot/database/database.py
#  @MrMNTG @MusammilN
#please give credits https://github.com/MN-BOTS/ShobanaFilterBot
import asyncio
import motor.motor_asyncio
from sqlalchemy import text

from info import (
    DATABASE_NAME,
    DATABASE_URI,
    DATABASE_URI2,
    DATABASE_URI3,
    DATABASE_URI4,
    DATABASE_URI5,
    DATABASE_NAME2,
    DATABASE_NAME3,
    DATABASE_NAME4,
    DATABASE_NAME5,
    IMDB,
    IMDB_TEMPLATE,
    MELCOW_NEW_USERS,
    P_TTI_SHOW_OFF,
    PROTECT_CONTENT,
    SINGLE_BUTTON,
    SPELL_CHECK_REPLY,
)

USE_MONGO = bool(DATABASE_URI)

if not USE_MONGO:
    from database.sql_store import store


class Database:
    def __init__(self, uri, database_name):
        self.use_mongo = USE_MONGO
        if self.use_mongo:
            self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
            self.db = self._client[database_name]
            self.col = self.db.users
            self.grp = self.db.groups
            self.config = self.db.config

            # Optional media shards can use additional DBs; /stats should include
            # size usage across configured Mongo databases.
            mongo_defs = [
                (DATABASE_URI, DATABASE_NAME),
                (DATABASE_URI2, DATABASE_NAME2),
                (DATABASE_URI3, DATABASE_NAME3),
                (DATABASE_URI4, DATABASE_NAME4),
                (DATABASE_URI5, DATABASE_NAME5),
            ]
            seen = set()
            self._mongo_dbs = []
            for db_uri, db_name in mongo_defs:
                if not db_uri:
                    continue
                key = (db_uri.strip(), (db_name or database_name).strip())
                if key in seen:
                    continue
                seen.add(key)
                client = self._client if key[0] == uri else motor.motor_asyncio.AsyncIOMotorClient(key[0])
                self._mongo_dbs.append(client[key[1]])


    async def ensure_indexes(self):
        if not self.use_mongo:
            return
        await asyncio.gather(
            self.col.create_index('id'),
            self.col.create_index('ban_status.is_banned'),
            self.grp.create_index('id'),
            self.grp.create_index('chat_status.is_disabled'),
            return_exceptions=True,
        )

    def new_user(self, id, name):
        return dict(id=id, name=name, ban_status=dict(is_banned=False, ban_reason=""))

    def new_group(self, id, title):
        return dict(id=id, title=title, chat_status=dict(is_disabled=False, reason=""))

    async def add_user(self, id, name):
        if self.use_mongo:
            await self.col.update_one(
                {'id': int(id)},
                {'$setOnInsert': self.new_user(int(id), name)},
                upsert=True,
            )
            return
        with store.begin() as conn:
            exists = conn.execute(text("SELECT 1 FROM users WHERE id=:id"), {"id": int(id)}).first()
            if not exists:
                conn.execute(text("INSERT INTO users(id, name) VALUES (:id, :name)"), {"id": int(id), "name": name})

    async def is_user_exist(self, id):
        if self.use_mongo:
            return bool(await self.col.find_one({'id': int(id)}))
        with store.begin() as conn:
            row = conn.execute(text("SELECT 1 FROM users WHERE id=:id"), {"id": int(id)}).first()
            return bool(row)

    async def total_users_count(self):
        if self.use_mongo:
            return await self.col.count_documents({})
        with store.begin() as conn:
            return int(conn.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0)

    async def remove_ban(self, id):
        if self.use_mongo:
            await self.col.update_one({'id': id}, {'$set': {'ban_status': {'is_banned': False, 'ban_reason': ''}}})
            return
        with store.begin() as conn:
            conn.execute(text("UPDATE users SET ban_is_banned=FALSE, ban_reason='' WHERE id=:id"), {"id": int(id)})

    async def ban_user(self, user_id, ban_reason="No Reason"):
        if self.use_mongo:
            await self.col.update_one({'id': user_id}, {'$set': {'ban_status': {'is_banned': True, 'ban_reason': ban_reason}}})
            return
        with store.begin() as conn:
            conn.execute(text("UPDATE users SET ban_is_banned=TRUE, ban_reason=:reason WHERE id=:id"), {"id": int(user_id), "reason": ban_reason})

    async def get_ban_status(self, id):
        default = dict(is_banned=False, ban_reason='')
        if self.use_mongo:
            user = await self.col.find_one({'id': int(id)})
            return user.get('ban_status', default) if user else default
        with store.begin() as conn:
            row = conn.execute(text("SELECT ban_is_banned, ban_reason FROM users WHERE id=:id"), {"id": int(id)}).first()
            return dict(is_banned=bool(row[0]), ban_reason=row[1] or '') if row else default

    async def get_all_users(self):
        if self.use_mongo:
            return self.col.find({})

        class AsyncRows:
            def __aiter__(self_inner):
                with store.begin() as conn:
                    self_inner.rows = conn.execute(text("SELECT id FROM users")).fetchall()
                self_inner.idx = 0
                return self_inner

            async def __anext__(self_inner):
                if self_inner.idx >= len(self_inner.rows):
                    raise StopAsyncIteration
                row = self_inner.rows[self_inner.idx]
                self_inner.idx += 1
                return {"id": row[0]}

        return AsyncRows()

    async def delete_user(self, user_id):
        if self.use_mongo:
            await self.col.delete_many({'id': int(user_id)})
            return
        with store.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id=:id"), {"id": int(user_id)})

    async def get_banned(self):
        if self.use_mongo:
            users = self.col.find({'ban_status.is_banned': True}, {'_id': 0, 'id': 1})
            chats = self.grp.find({'chat_status.is_disabled': True}, {'_id': 0, 'id': 1})
            user_docs, chat_docs = await asyncio.gather(
                users.to_list(length=None),
                chats.to_list(length=None),
            )
            return [user['id'] for user in user_docs], [chat['id'] for chat in chat_docs]
        with store.begin() as conn:
            b_users = [r[0] for r in conn.execute(text("SELECT id FROM users WHERE ban_is_banned=TRUE")).fetchall()]
            b_chats = [r[0] for r in conn.execute(text("SELECT id FROM groups_data WHERE chat_is_disabled=TRUE")).fetchall()]
            return b_users, b_chats

    async def add_chat(self, chat, title):
        if self.use_mongo:
            await self.grp.update_one(
                {'id': int(chat)},
                {'$setOnInsert': self.new_group(int(chat), title)},
                upsert=True,
            )
            return
        with store.begin() as conn:
            exists = conn.execute(text("SELECT 1 FROM groups_data WHERE id=:id"), {"id": int(chat)}).first()
            if not exists:
                conn.execute(text("INSERT INTO groups_data(id, title) VALUES (:id,:title)"), {"id": int(chat), "title": title})

    async def get_chat(self, chat):
        if self.use_mongo:
            found = await self.grp.find_one({'id': int(chat)})
            return False if not found else found.get('chat_status')
        with store.begin() as conn:
            row = conn.execute(text("SELECT chat_is_disabled, chat_reason FROM groups_data WHERE id=:id"), {"id": int(chat)}).first()
            return False if not row else dict(is_disabled=bool(row[0]), reason=row[1] or '')

    async def re_enable_chat(self, id):
        if self.use_mongo:
            await self.grp.update_one({'id': int(id)}, {'$set': {'chat_status': {'is_disabled': False, 'reason': ''}}})
            return
        with store.begin() as conn:
            conn.execute(text("UPDATE groups_data SET chat_is_disabled=FALSE, chat_reason='' WHERE id=:id"), {"id": int(id)})

    async def update_settings(self, id, settings):
        if self.use_mongo:
            await self.grp.update_one({'id': int(id)}, {'$set': {'settings': settings}})
            return
        with store.begin() as conn:
            conn.execute(text("UPDATE groups_data SET settings=:settings WHERE id=:id"), {"id": int(id), "settings": store.to_json(settings)})

    async def get_settings(self, id):
        default = {
            'button': SINGLE_BUTTON,
            'botpm': P_TTI_SHOW_OFF,
            'file_secure': PROTECT_CONTENT,
            'imdb': IMDB,
            'spell_check': SPELL_CHECK_REPLY,
            'welcome': MELCOW_NEW_USERS,
            'template': IMDB_TEMPLATE,
        }
        if self.use_mongo:
            chat = await self.grp.find_one({'id': int(id)})
            return chat.get('settings', default) if chat else default
        with store.begin() as conn:
            row = conn.execute(text("SELECT settings FROM groups_data WHERE id=:id"), {"id": int(id)}).first()
            return store.from_json(row[0], default) if row else default

    async def disable_chat(self, chat, reason="No Reason"):
        if self.use_mongo:
            await self.grp.update_one({'id': int(chat)}, {'$set': {'chat_status': {'is_disabled': True, 'reason': reason}}})
            return
        with store.begin() as conn:
            conn.execute(text("UPDATE groups_data SET chat_is_disabled=TRUE, chat_reason=:reason WHERE id=:id"), {"id": int(chat), "reason": reason})

    async def total_chat_count(self):
        if self.use_mongo:
            return await self.grp.count_documents({})
        with store.begin() as conn:
            return int(conn.execute(text("SELECT COUNT(*) FROM groups_data")).scalar() or 0)

    async def get_all_chats(self):
        if self.use_mongo:
            return self.grp.find({})

        class AsyncRows:
            def __aiter__(self_inner):
                with store.begin() as conn:
                    self_inner.rows = conn.execute(text("SELECT id, title FROM groups_data")).fetchall()
                self_inner.idx = 0
                return self_inner

            async def __anext__(self_inner):
                if self_inner.idx >= len(self_inner.rows):
                    raise StopAsyncIteration
                row = self_inner.rows[self_inner.idx]
                self_inner.idx += 1
                return {"id": row[0], "title": row[1]}

        return AsyncRows()

    async def set_auth_channels(self, channels: list[int]):
        if self.use_mongo:
            await self.config.update_one({"_id": "auth_channels"}, {"$set": {"channels": channels}}, upsert=True)
            return
        with store.begin() as conn:
            exists = conn.execute(text("SELECT 1 FROM config_data WHERE key_name='auth_channels'"), {}).first()
            if exists:
                conn.execute(text("UPDATE config_data SET value_json=:value WHERE key_name='auth_channels'"), {"value": store.to_json(channels)})
            else:
                conn.execute(text("INSERT INTO config_data(key_name, value_json) VALUES ('auth_channels', :value)"), {"value": store.to_json(channels)})

    async def get_auth_channels(self) -> list[int]:
        if self.use_mongo:
            doc = await self.config.find_one({"_id": "auth_channels"})
            return doc["channels"] if doc and "channels" in doc else []
        with store.begin() as conn:
            row = conn.execute(text("SELECT value_json FROM config_data WHERE key_name='auth_channels'"))
            value = row.scalar()
            return store.from_json(value, [])

    async def get_db_size(self):
        if self.use_mongo:
            if not getattr(self, '_mongo_dbs', None):
                return int((await self.db.command("dbstats")).get('dataSize', 0))
            stats = await asyncio.gather(*[db.command("dbstats") for db in self._mongo_dbs])
            return int(sum(s.get('dataSize', 0) for s in stats))
        with store.begin() as conn:
            size = conn.execute(text("SELECT pg_database_size(current_database())")).scalar()
            return int(size or 0)

    async def set_update_chat_ids(self, chat_ids: list[int]):
        if self.use_mongo:
            await self.config.update_one({"_id": "update_chat_ids"}, {"$set": {"value": chat_ids}}, upsert=True)
            return
        with store.begin() as conn:
            exists = conn.execute(text("SELECT 1 FROM config_data WHERE key_name='update_chat_ids'"), {}).first()
            if exists:
                conn.execute(text("UPDATE config_data SET value_json=:value WHERE key_name='update_chat_ids'"), {"value": store.to_json(chat_ids)})
            else:
                conn.execute(text("INSERT INTO config_data(key_name, value_json) VALUES ('update_chat_ids', :value)"), {"value": store.to_json(chat_ids)})

    async def get_update_chat_ids(self) -> list[int]:
        if self.use_mongo:
            doc = await self.config.find_one({"_id": "update_chat_ids"})
            return doc.get("value", []) if doc else []
        with store.begin() as conn:
            row = conn.execute(text("SELECT value_json FROM config_data WHERE key_name='update_chat_ids'"))
            return store.from_json(row.scalar(), [])

    async def set_new_updates_enabled(self, enabled: bool):
        if self.use_mongo:
            await self.config.update_one({"_id": "new_updates_enabled"}, {"$set": {"value": bool(enabled)}}, upsert=True)
            return
        with store.begin() as conn:
            exists = conn.execute(text("SELECT 1 FROM config_data WHERE key_name='new_updates_enabled'"), {}).first()
            if exists:
                conn.execute(text("UPDATE config_data SET value_json=:value WHERE key_name='new_updates_enabled'"), {"value": store.to_json(bool(enabled))})
            else:
                conn.execute(text("INSERT INTO config_data(key_name, value_json) VALUES ('new_updates_enabled', :value)"), {"value": store.to_json(bool(enabled))})

    async def get_new_updates_enabled(self) -> bool:
        if self.use_mongo:
            doc = await self.config.find_one({"_id": "new_updates_enabled"})
            return bool(doc.get("value", True)) if doc else True
        with store.begin() as conn:
            row = conn.execute(text("SELECT value_json FROM config_data WHERE key_name='new_updates_enabled'"))
            return bool(store.from_json(row.scalar(), True))

    async def add_announced_key(self, key: str):
        if self.use_mongo:
            await self.config.update_one({"_id": "announced_keys"}, {"$addToSet": {"keys": key}}, upsert=True)
            return

    async def check_announced_key(self, key: str) -> bool:
        if self.use_mongo:
            doc = await self.config.find_one({"_id": "announced_keys", "keys": key})
            return bool(doc)
        return False

    async def add_daily_added(self, title: str):
        if self.use_mongo:
            await self.config.update_one({"_id": "daily_added"}, {"$push": {"items": title}}, upsert=True)
            return

    async def get_daily_added(self):
        if self.use_mongo:
            doc = await self.config.find_one({"_id": "daily_added"})
            return doc.get("items", []) if doc else []
        return []

    async def clear_daily_added(self):
        if self.use_mongo:
            await self.config.update_one({"_id": "daily_added"}, {"$set": {"items": []}}, upsert=True)

    async def mark_daily_summary_done(self, day_key: str):
        if self.use_mongo:
            await self.config.update_one({"_id": "daily_summary"}, {"$set": {"day": day_key}}, upsert=True)

    async def is_daily_summary_done(self, day_key: str) -> bool:
        if self.use_mongo:
            doc = await self.config.find_one({"_id": "daily_summary"})
            return bool(doc and doc.get("day") == day_key)
        return False


db = Database(DATABASE_URI, DATABASE_NAME)
