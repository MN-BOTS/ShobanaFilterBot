# https://github.com/odysseusmax/animated-lamp/blob/master/bot/database/database.py
import json
import shutil
from pathlib import Path
import motor.motor_asyncio

from info import (
    DATABASE_NAME,
    DATABASE_URI,
    IMDB,
    IMDB_TEMPLATE,
    MELCOW_NEW_USERS,
    P_TTI_SHOW_OFF,
    PROTECT_CONTENT,
    SINGLE_BUTTON,
    SPELL_CHECK_REPLY,
    TURSO_MAX_DB_BYTES,
)
from database.sqldb import (
    db_execute,
    db_fetchall,
    db_fetchone,
    get_conn,
    get_fallback_db_path,
    get_fallback_db_size,
    get_sqldb_path,
    libsql_fallback_active,
    libsql_mode,
    sqldb_enabled,
)

USE_SQLDB = sqldb_enabled()
USE_LIBSQL = libsql_mode()


class _AsyncRows:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        self._it = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class Database:
    def __init__(self, uri, database_name):
        self.use_sql = USE_SQLDB
        self.use_libsql = USE_LIBSQL
        self._schema_ready = False

        if not self.use_sql:
            self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
            self.db = self._client[database_name]
            self.col = self.db.users
            self.grp = self.db.groups
            self.config = self.db.config
        elif not self.use_libsql:
            with get_conn() as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, is_banned INTEGER DEFAULT 0, ban_reason TEXT DEFAULT '')")
                conn.execute("CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY, title TEXT, is_disabled INTEGER DEFAULT 0, reason TEXT DEFAULT '', settings TEXT)")
                conn.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
                conn.commit()

    async def _ensure_schema(self):
        if not self.use_sql or self._schema_ready:
            return
        await db_execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, is_banned INTEGER DEFAULT 0, ban_reason TEXT DEFAULT '')")
        await db_execute("CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY, title TEXT, is_disabled INTEGER DEFAULT 0, reason TEXT DEFAULT '', settings TEXT)")
        await db_execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
        self._schema_ready = True

    async def add_user(self, id, name):
        if not self.use_sql:
            await self.col.insert_one({'id': id, 'name': name, 'ban_status': {'is_banned': False, 'ban_reason': ''}})
            return
        await self._ensure_schema()
        await db_execute("INSERT OR IGNORE INTO users(id, name, is_banned, ban_reason) VALUES (?, ?, 0, '')", (int(id), str(name)))

    async def is_user_exist(self, id):
        if not self.use_sql:
            return bool(await self.col.find_one({'id': int(id)}))
        await self._ensure_schema()
        return bool(await db_fetchone("SELECT 1 as ok FROM users WHERE id=?", (int(id),)))

    async def total_users_count(self):
        if not self.use_sql:
            return await self.col.count_documents({})
        await self._ensure_schema()
        row = await db_fetchone("SELECT COUNT(*) as c FROM users")
        return int(row['c']) if row else 0

    async def remove_ban(self, id):
        if not self.use_sql:
            await self.col.update_one({'id': id}, {'$set': {'ban_status': {'is_banned': False, 'ban_reason': ''}}})
            return
        await self._ensure_schema()
        await db_execute("UPDATE users SET is_banned=0, ban_reason='' WHERE id=?", (int(id),))

    async def ban_user(self, user_id, ban_reason="No Reason"):
        if not self.use_sql:
            await self.col.update_one({'id': user_id}, {'$set': {'ban_status': {'is_banned': True, 'ban_reason': ban_reason}}})
            return
        await self._ensure_schema()
        await db_execute("UPDATE users SET is_banned=1, ban_reason=? WHERE id=?", (str(ban_reason), int(user_id)))

    async def get_ban_status(self, id):
        default = {'is_banned': False, 'ban_reason': ''}
        if not self.use_sql:
            user = await self.col.find_one({'id': int(id)})
            return default if not user else user.get('ban_status', default)
        await self._ensure_schema()
        row = await db_fetchone("SELECT is_banned, ban_reason FROM users WHERE id=?", (int(id),))
        return default if not row else {'is_banned': bool(row['is_banned']), 'ban_reason': row['ban_reason'] or ''}

    async def get_all_users(self):
        if not self.use_sql:
            return self.col.find({})
        await self._ensure_schema()
        rows = await db_fetchall("SELECT id FROM users")
        return _AsyncRows([{'id': r['id']} for r in rows])

    async def delete_user(self, user_id):
        if not self.use_sql:
            await self.col.delete_many({'id': int(user_id)})
            return
        await self._ensure_schema()
        await db_execute("DELETE FROM users WHERE id=?", (int(user_id),))

    async def get_banned(self):
        if not self.use_sql:
            users = self.col.find({'ban_status.is_banned': True})
            chats = self.grp.find({'chat_status.is_disabled': True})
            return [u['id'] async for u in users], [c['id'] async for c in chats]
        await self._ensure_schema()
        b_users = await db_fetchall("SELECT id FROM users WHERE is_banned=1")
        b_chats = await db_fetchall("SELECT id FROM groups WHERE is_disabled=1")
        return [r['id'] for r in b_users], [r['id'] for r in b_chats]

    async def add_chat(self, chat, title):
        if not self.use_sql:
            await self.grp.insert_one({'id': chat, 'title': title, 'chat_status': {'is_disabled': False, 'reason': ''}})
            return
        await self._ensure_schema()
        await db_execute("INSERT OR IGNORE INTO groups(id, title, is_disabled, reason, settings) VALUES (?, ?, 0, '', NULL)", (int(chat), str(title)))

    async def get_chat(self, chat):
        if not self.use_sql:
            v = await self.grp.find_one({'id': int(chat)})
            return False if not v else v.get('chat_status')
        await self._ensure_schema()
        row = await db_fetchone("SELECT is_disabled, reason FROM groups WHERE id=?", (int(chat),))
        return False if not row else {'is_disabled': bool(row['is_disabled']), 'reason': row['reason'] or ''}

    async def re_enable_chat(self, id):
        if not self.use_sql:
            await self.grp.update_one({'id': int(id)}, {'$set': {'chat_status': {'is_disabled': False, 'reason': ''}}})
            return
        await self._ensure_schema()
        await db_execute("UPDATE groups SET is_disabled=0, reason='' WHERE id=?", (int(id),))

    async def update_settings(self, id, settings):
        if not self.use_sql:
            await self.grp.update_one({'id': int(id)}, {'$set': {'settings': settings}})
            return
        await self._ensure_schema()
        await db_execute("UPDATE groups SET settings=? WHERE id=?", (json.dumps(settings), int(id)))

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
        if not self.use_sql:
            chat = await self.grp.find_one({'id': int(id)})
            return default if not chat else chat.get('settings', default)
        await self._ensure_schema()
        row = await db_fetchone("SELECT settings FROM groups WHERE id=?", (int(id),))
        if not row or not row.get('settings'):
            return default
        try:
            return json.loads(row['settings'])
        except Exception:
            return default

    async def disable_chat(self, chat, reason="No Reason"):
        if not self.use_sql:
            await self.grp.update_one({'id': int(chat)}, {'$set': {'chat_status': {'is_disabled': True, 'reason': reason}}})
            return
        await self._ensure_schema()
        await db_execute("UPDATE groups SET is_disabled=1, reason=? WHERE id=?", (str(reason), int(chat)))

    async def total_chat_count(self):
        if not self.use_sql:
            return await self.grp.count_documents({})
        await self._ensure_schema()
        row = await db_fetchone("SELECT COUNT(*) as c FROM groups")
        return int(row['c']) if row else 0

    async def get_all_chats(self):
        if not self.use_sql:
            return self.grp.find({})
        await self._ensure_schema()
        rows = await db_fetchall("SELECT id FROM groups")
        return _AsyncRows([{'id': r['id']} for r in rows])

    async def set_auth_channels(self, channels: list[int]):
        if not self.use_sql:
            await self.config.update_one({'_id': 'auth_channels'}, {'$set': {'channels': channels}}, upsert=True)
            return
        await self._ensure_schema()
        await db_execute("INSERT INTO config(key, value) VALUES('auth_channels', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(channels),))

    async def get_auth_channels(self) -> list[int]:
        if not self.use_sql:
            doc = await self.config.find_one({'_id': 'auth_channels'})
            return doc['channels'] if doc and 'channels' in doc else []
        await self._ensure_schema()
        row = await db_fetchone("SELECT value FROM config WHERE key='auth_channels'")
        if not row:
            return []
        try:
            return json.loads(row['value'])
        except Exception:
            return []

    async def get_db_backend(self):
        if not self.use_sql:
            return "MongoDB"
        if self.use_libsql:
            return "SQLite Fallback (Turso unreachable)" if libsql_fallback_active() else "Turso libsql"
        return "SQLite"

    async def get_db_size(self):
        if not self.use_sql:
            return (await self.db.command('dbstats'))['dataSize']
        if self.use_libsql:
            # When Turso is unreachable and fallback sqlite is active,
            # report the fallback sqlite usage so /stats remains useful.
            try:
                return get_fallback_db_size()
            except Exception:
                return None
        with get_conn() as conn:
            page_count = conn.execute("PRAGMA page_count").fetchone()[0]
            page_size = conn.execute("PRAGMA page_size").fetchone()[0]
            return int(page_count) * int(page_size)

    async def get_db_limit(self):
        if self.use_libsql and not libsql_fallback_active():
            return int(TURSO_MAX_DB_BYTES)

        sqlite_path = Path(get_fallback_db_path() if self.use_libsql else (get_sqldb_path() or "bot.db"))
        base_path = sqlite_path if sqlite_path.exists() else sqlite_path.parent
        usage = shutil.disk_usage(str(base_path))
        return int(usage.total)


db = Database(DATABASE_URI, DATABASE_NAME)
