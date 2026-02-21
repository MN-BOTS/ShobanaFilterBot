import json
import logging
from sqlalchemy import create_engine, text

from info import POSTGRES_URI

logger = logging.getLogger(__name__)


def _resolve_db_url() -> str:
    if POSTGRES_URI:
        return POSTGRES_URI
    raise ValueError("POSTGRES_URI must be set when DATABASE_URI is not configured")


class SQLStore:
    def __init__(self):
        self.url = _resolve_db_url()
        self.engine = create_engine(self.url, future=True)
        self._ensure_tables()

    def _ensure_tables(self):
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                name TEXT,
                ban_is_banned BOOLEAN DEFAULT FALSE,
                ban_reason TEXT DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS groups_data (
                id BIGINT PRIMARY KEY,
                title TEXT,
                chat_is_disabled BOOLEAN DEFAULT FALSE,
                chat_reason TEXT DEFAULT '',
                settings TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS config_data (
                key_name TEXT PRIMARY KEY,
                value_json TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS connections (
                user_id BIGINT,
                group_id BIGINT,
                is_active BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (user_id, group_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS media (
                file_id TEXT PRIMARY KEY,
                file_ref TEXT,
                file_name TEXT NOT NULL,
                file_size BIGINT NOT NULL,
                file_type TEXT,
                mime_type TEXT,
                caption TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS filters (
                group_id BIGINT,
                text_key TEXT,
                reply_text TEXT,
                btn TEXT,
                file_id TEXT,
                alert TEXT,
                PRIMARY KEY (group_id, text_key)
            )
            """,
        ]
        with self.engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))

    def to_json(self, value):
        return json.dumps(value, ensure_ascii=False)

    def from_json(self, value, default):
        if not value:
            return default
        try:
            return json.loads(value)
        except Exception:
            return default


store = SQLStore()
