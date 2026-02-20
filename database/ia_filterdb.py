#  @MrMNTG @MusammilN
#please give credits https://github.com/MN-BOTS/ShobanaFilterBot
import base64
import logging
import re
from collections import defaultdict
from struct import pack

from marshmallow.exceptions import ValidationError
from pymongo.errors import DuplicateKeyError
from pyrogram.file_id import FileId

from info import COLLECTION_NAME, DATABASE_NAME, DATABASE_URI, USE_CAPTION_FILTER
from database.sqldb import db_execute, db_fetchall, libsql_mode, sqldb_enabled, get_conn

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

USE_SQLDB = sqldb_enabled()
USE_LIBSQL = libsql_mode()

if not USE_SQLDB:
    from motor.motor_asyncio import AsyncIOMotorClient
    from umongo import Document, Instance, fields

    client = AsyncIOMotorClient(DATABASE_URI)
    db = client[DATABASE_NAME]
    instance = Instance.from_db(db)

    @instance.register
    class Media(Document):
        file_id = fields.StrField(attribute="_id")
        file_ref = fields.StrField(allow_none=True)
        file_name = fields.StrField(required=True)
        file_size = fields.IntField(required=True)
        file_type = fields.StrField(allow_none=True)
        mime_type = fields.StrField(allow_none=True)
        caption = fields.StrField(allow_none=True)

        class Meta:
            indexes = ("$file_name",)
            collection_name = COLLECTION_NAME

else:
    _media_schema_ready = False

    async def _ensure_media_table():
        global _media_schema_ready
        if _media_schema_ready:
            return
        await db_execute(
            """
            CREATE TABLE IF NOT EXISTS media (
                file_id TEXT PRIMARY KEY,
                file_ref TEXT,
                file_name TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_type TEXT,
                mime_type TEXT,
                caption TEXT
            )
            """
        )
        _media_schema_ready = True

    class SqlMediaDoc(dict):
        def __getattr__(self, item):
            return self.get(item)

    class SqlDeleteResult:
        def __init__(self, deleted_count: int):
            self.deleted_count = deleted_count

    def _match_filter(row: dict, filter_: dict) -> bool:
        if not filter_:
            return True
        if "$or" in filter_:
            if not any(_match_filter(row, sub) for sub in filter_["$or"]):
                return False
            rest = {k: v for k, v in filter_.items() if k != "$or"}
            return _match_filter(row, rest)

        for key, val in filter_.items():
            field = "file_id" if key in ("_id", "file_id") else key
            row_val = row.get(field)
            if key == "_id" and isinstance(val, dict) and "$in" in val:
                if row_val not in set(val["$in"]):
                    return False
            elif hasattr(val, "search"):
                if row_val is None or not val.search(str(row_val)):
                    return False
            elif row_val != val:
                return False
        return True

    class SqlCursor:
        def __init__(self, filter_=None, projection=None, as_docs=False):
            self.filter = filter_ or {}
            self.projection = projection
            self.as_docs = as_docs
            self._skip = 0
            self._limit = None
            self._sort_key = None
            self._sort_order = 1

        def sort(self, key, order):
            self._sort_key = key
            self._sort_order = order
            return self

        def skip(self, n):
            self._skip = n
            return self

        def limit(self, n):
            self._limit = n
            return self

        async def to_list(self, length=None):
            await _ensure_media_table()
            rows = await db_fetchall(
                "SELECT rowid as _rowid, file_id, file_ref, file_name, file_size, file_type, mime_type, caption FROM media"
            )
            filtered = [r for r in rows if _match_filter(r, self.filter)]

            if self._sort_key == "$natural":
                filtered.sort(key=lambda x: x.get("_rowid", 0), reverse=self._sort_order == -1)
            elif self._sort_key:
                filtered.sort(key=lambda x: x.get(self._sort_key), reverse=self._sort_order == -1)

            filtered = filtered[self._skip :]
            lim = self._limit if self._limit is not None else length
            if lim is not None:
                filtered = filtered[:lim]

            out = []
            for r in filtered:
                item = {
                    "_id": r.get("file_id"),
                    "file_id": r.get("file_id"),
                    "file_ref": r.get("file_ref"),
                    "file_name": r.get("file_name"),
                    "file_size": r.get("file_size"),
                    "file_type": r.get("file_type"),
                    "mime_type": r.get("mime_type"),
                    "caption": r.get("caption"),
                }
                if self.projection and self.projection.get("_id") == 1:
                    item = {"_id": item["_id"]}
                out.append(SqlMediaDoc(item) if self.as_docs else item)
            return out

    class SqlCollection:
        def find(self, filter_, projection=None):
            return SqlCursor(filter_, projection, as_docs=False)

        async def delete_one(self, filter_):
            rows = await self.find(filter_, {"_id": 1}).limit(1).to_list(length=1)
            if not rows:
                return SqlDeleteResult(0)
            await db_execute("DELETE FROM media WHERE file_id=?", (rows[0]["_id"],))
            return SqlDeleteResult(1)

        async def delete_many(self, filter_):
            rows = await self.find(filter_, {"_id": 1}).to_list(length=100000)
            deleted = 0
            for r in rows:
                await db_execute("DELETE FROM media WHERE file_id=?", (r["_id"],))
                deleted += 1
            return SqlDeleteResult(deleted)

        async def drop(self):
            await db_execute("DROP TABLE IF EXISTS media")
            await _ensure_media_table()

    class Media:
        collection = SqlCollection()

        @staticmethod
        async def ensure_indexes():
            await _ensure_media_table()
            return True

        @staticmethod
        async def count_documents(filter_=None):
            rows = await SqlCursor(filter_ or {}, as_docs=False).to_list(length=1000000)
            return len(rows)

        @staticmethod
        def find(filter_=None):
            return SqlCursor(filter_ or {}, as_docs=True)


async def save_file(media):
    """Save file in database"""
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))

    if USE_SQLDB:
        try:
            await _ensure_media_table()
            await db_execute(
                "INSERT INTO media(file_id, file_ref, file_name, file_size, file_type, mime_type, caption) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    file_id,
                    file_ref,
                    file_name,
                    media.file_size,
                    media.file_type,
                    media.mime_type,
                    media.caption.html if media.caption else None,
                ),
            )
            logger.info(f'{getattr(media, "file_name", "NO_FILE")} is saved to database')
            return True, 1
        except Exception as e:
            if "UNIQUE constraint failed" in str(e) or "duplicate" in str(e).lower():
                logger.warning(f'{getattr(media, "file_name", "NO_FILE")} is already saved in database')
                return False, 0
            logger.exception("Error occurred while saving file in database")
            return False, 2

    try:
        file = Media(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type=media.mime_type,
            caption=media.caption.html if media.caption else None,
        )
    except ValidationError:
        logger.exception("Error occurred while saving file in database")
        return False, 2

    try:
        await file.commit()
    except DuplicateKeyError:
        logger.warning(f'{getattr(media, "file_name", "NO_FILE")} is already saved in database')
        return False, 0
    else:
        logger.info(f'{getattr(media, "file_name", "NO_FILE")} is saved to database')
        return True, 1


async def get_search_results(query, file_type=None, max_results=10, offset=0, filter=False):
    query = query.strip()
    if not query:
        raw_pattern = "."
    elif " " not in query:
        raw_pattern = r"(\b|[\.\+\-_])" + query + r"(\b|[\.\+\-_])"
    else:
        raw_pattern = query.replace(" ", r".*[\s\.\+\-_]")

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except Exception:
        return []

    if USE_CAPTION_FILTER:
        filter = {"$or": [{"file_name": regex}, {"caption": regex}]}
    else:
        filter = {"file_name": regex}

    if file_type:
        filter["file_type"] = file_type

    total_results = await Media.count_documents(filter)
    next_offset = offset + max_results
    if next_offset > total_results:
        next_offset = ""

    cursor = Media.find(filter)
    cursor.sort("$natural", -1)
    cursor.skip(offset).limit(max_results)
    files = await cursor.to_list(length=max_results)
    return files, next_offset, total_results


async def get_file_details(query):
    cursor = Media.find({"file_id": query})
    return await cursor.to_list(length=1)


def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0
    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0
            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")


def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")


def unpack_new_file_id(new_file_id):
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack("<iiqq", int(decoded.file_type), decoded.dc_id, decoded.media_id, decoded.access_hash)
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref


async def get_movie_list(limit=20):
    files = await Media.find().sort("$natural", -1).limit(100).to_list(length=100)
    results = []
    for file in files:
        name = getattr(file, "file_name", "")
        if not re.search(r"(s\d{1,2}|season\s*\d+).*?(e\d{1,2}|episode\s*\d+)", name, re.I):
            results.append(name)
        if len(results) >= limit:
            break
    return results


async def get_series_grouped(limit=30):
    files = await Media.find().sort("$natural", -1).limit(150).to_list(length=150)
    grouped = defaultdict(list)
    for file in files:
        name = getattr(file, "file_name", "")
        match = re.search(r"(.*?)(?:S\d{1,2}|Season\s*\d+).*?(?:E|Ep|Episode)?(\d{1,2})", name, re.I)
        if match:
            title = match.group(1).strip().title()
            grouped[title].append(int(match.group(2)))
    return {title: sorted(set(eps))[:10] for title, eps in grouped.items() if eps}
