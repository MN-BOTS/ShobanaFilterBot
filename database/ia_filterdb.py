#  @MrMNTG @MusammilN
#please give credits https://github.com/MN-BOTS/ShobanaFilterBot
import logging
from struct import pack
import re
import base64
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from sqlalchemy import text

from info import DATABASE_URI, DATABASE_NAME, COLLECTION_NAME, USE_CAPTION_FILTER

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

USE_MONGO = bool(DATABASE_URI)

if not USE_MONGO:
    from database.sql_store import store


class SQLMediaDoc(dict):
    def __getattr__(self, item):
        return self.get(item)


class SQLDeleteResult:
    def __init__(self, deleted_count=0):
        self.deleted_count = deleted_count


class SQLCursor:
    def __init__(self, docs, projection=None):
        self.docs = docs
        self._skip = 0
        self._limit = None
        self.projection = projection

    def sort(self, field, direction):
        reverse = direction == -1
        key = 'created_at' if field == '$natural' else field
        self.docs.sort(key=lambda d: d.get(key), reverse=reverse)
        return self

    def skip(self, value):
        self._skip = value
        return self

    def limit(self, value):
        self._limit = value
        return self

    async def to_list(self, length=None):
        docs = self.docs[self._skip:]
        if self._limit is not None:
            docs = docs[: self._limit]
        if length is not None:
            docs = docs[:length]
        if self.projection is not None:
            keys = [k for k, v in self.projection.items() if v]
            projected = []
            for d in docs:
                item = SQLMediaDoc()
                for k in keys:
                    if k == '_id':
                        item['_id'] = d.get('file_id')
                    elif k in d:
                        item[k] = d[k]
                projected.append(item)
            return projected
        return [SQLMediaDoc(d) for d in docs]


def _match_filter(doc, query):
    if not query:
        return True
    for key, val in query.items():
        if key == '$or':
            if not any(_match_filter(doc, cond) for cond in val):
                return False
            continue
        if key == '_id':
            if isinstance(val, dict) and '$in' in val:
                if doc.get('file_id') not in val['$in']:
                    return False
            elif doc.get('file_id') != val:
                return False
            continue

        target = doc.get(key)
        if isinstance(val, re.Pattern):
            if not val.search(str(target or '')):
                return False
        else:
            if target != val:
                return False
    return True


class SQLMediaCollection:
    async def _all_docs(self):
        with store.begin() as conn:
            rows = conn.execute(text("SELECT file_id, file_ref, file_name, file_size, file_type, mime_type, caption, created_at FROM media")).fetchall()
        docs = []
        for r in rows:
            docs.append(
                dict(
                    file_id=r[0],
                    _id=r[0],
                    file_ref=r[1],
                    file_name=r[2],
                    file_size=r[3],
                    file_type=r[4],
                    mime_type=r[5],
                    caption=r[6],
                    created_at=r[7],
                )
            )
        return docs

    async def find(self, query=None, projection=None):
        docs = [d for d in await self._all_docs() if _match_filter(d, query or {})]
        return SQLCursor(docs, projection=projection)

    async def delete_many(self, query):
        docs = [d for d in await self._all_docs() if _match_filter(d, query)]
        ids = [d['file_id'] for d in docs]
        if not ids:
            return SQLDeleteResult(0)
        with store.begin() as conn:
            for fid in ids:
                conn.execute(text("DELETE FROM media WHERE file_id=:fid"), {"fid": fid})
        return SQLDeleteResult(len(ids))

    async def delete_one(self, query):
        docs = [d for d in await self._all_docs() if _match_filter(d, query)]
        if not docs:
            return SQLDeleteResult(0)
        fid = docs[0]['file_id']
        with store.begin() as conn:
            conn.execute(text("DELETE FROM media WHERE file_id=:fid"), {"fid": fid})
        return SQLDeleteResult(1)

    async def drop(self):
        with store.begin() as conn:
            conn.execute(text("DELETE FROM media"))


if USE_MONGO:
    client = AsyncIOMotorClient(DATABASE_URI)
    db = client[DATABASE_NAME]
    instance = Instance.from_db(db)

    @instance.register
    class Media(Document):
        file_id = fields.StrField(attribute='_id')
        file_ref = fields.StrField(allow_none=True)
        file_name = fields.StrField(required=True)
        file_size = fields.IntField(required=True)
        file_type = fields.StrField(allow_none=True)
        mime_type = fields.StrField(allow_none=True)
        caption = fields.StrField(allow_none=True)

        class Meta:
            indexes = ('$file_name', )
            collection_name = COLLECTION_NAME

else:
    def _load_docs_sync(query=None):
        with store.begin() as conn:
            rows = conn.execute(text("SELECT file_id, file_ref, file_name, file_size, file_type, mime_type, caption, created_at FROM media")).fetchall()
        docs = []
        for r in rows:
            d = dict(file_id=r[0], _id=r[0], file_ref=r[1], file_name=r[2], file_size=r[3], file_type=r[4], mime_type=r[5], caption=r[6], created_at=r[7])
            if _match_filter(d, query or {}):
                docs.append(d)
        return docs

    class Media:
        collection = SQLMediaCollection()

        @staticmethod
        async def ensure_indexes():
            return

        @staticmethod
        async def count_documents(query=None):
            return len(_load_docs_sync(query))

        @staticmethod
        def find(query=None):
            return SQLCursor(_load_docs_sync(query))


async def save_file(media):
    """Save file in database"""

    # TODO: Find better way to get same file_id for same media to avoid duplicates
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))

    if USE_MONGO:
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
            logger.exception('Error occurred while saving file in database')
            return False, 2
        else:
            try:
                await file.commit()
            except DuplicateKeyError:
                logger.warning(f'{getattr(media, "file_name", "NO_FILE")} is already saved in database')
                return False, 0
            else:
                logger.info(f'{getattr(media, "file_name", "NO_FILE")} is saved to database')
                return True, 1

    with store.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM media WHERE file_id=:fid"), {"fid": file_id}).first()
        if exists:
            return False, 0
        conn.execute(
            text(
                "INSERT INTO media(file_id,file_ref,file_name,file_size,file_type,mime_type,caption) "
                "VALUES (:fid,:fref,:fname,:fsize,:ftype,:mtype,:caption)"
            ),
            {
                "fid": file_id,
                "fref": file_ref,
                "fname": file_name,
                "fsize": media.file_size,
                "ftype": media.file_type,
                "mtype": media.mime_type,
                "caption": media.caption.html if media.caption else None,
            },
        )
    return True, 1


async def get_search_results(query, file_type=None, max_results=10, offset=0, filter=False):
    """For given query return (results, next_offset)"""

    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]')

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except Exception:
        return []

    if USE_CAPTION_FILTER:
        filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter = {'file_name': regex}

    if file_type:
        filter['file_type'] = file_type

    total_results = await Media.count_documents(filter)
    next_offset = offset + max_results

    if next_offset > total_results:
        next_offset = ''

    cursor = Media.find(filter)
    cursor.sort('$natural', -1)
    cursor.skip(offset).limit(max_results)
    files = await cursor.to_list(length=max_results)

    return files, next_offset, total_results


async def get_file_details(query):
    filter = {'file_id': query}
    cursor = Media.find(filter)
    filedetails = await cursor.to_list(length=1)
    return filedetails


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
    """Return file_id, file_ref"""
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash
        )
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref

from collections import defaultdict

async def get_movie_list(limit=20):
    cursor = Media.find().sort("$natural", -1).limit(100)
    files = await cursor.to_list(length=100)
    results = []

    for file in files:
        name = getattr(file, "file_name", "")
        if not re.search(r"(s\d{1,2}|season\s*\d+).*?(e\d{1,2}|episode\s*\d+)", name, re.I):
            results.append(name)
        if len(results) >= limit:
            break
    return results


async def get_series_grouped(limit=30):
    cursor = Media.find().sort("$natural", -1).limit(150)
    files = await cursor.to_list(length=150)
    grouped = defaultdict(list)

    for file in files:
        name = getattr(file, "file_name", "")
        match = re.search(r"(.*?)(?:S\d{1,2}|Season\s*\d+).*?(?:E|Ep|Episode)?(\d{1,2})", name, re.I)
        if match:
            title = match.group(1).strip().title()
            episode = int(match.group(2))
            grouped[title].append(episode)

    return {
        title: sorted(set(eps))[:10]
        for title, eps in grouped.items() if eps
    }
