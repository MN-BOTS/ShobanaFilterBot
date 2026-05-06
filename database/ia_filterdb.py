#  @MrMNTG @MusammilN
#please give credits https://github.com/MN-BOTS/ShobanaFilterBot
import logging
from struct import pack
import re
import base64
import asyncio
import time
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError, OperationFailure
from motor.motor_asyncio import AsyncIOMotorClient
import hashlib
from collections import OrderedDict, defaultdict
from sqlalchemy import text

from info import (
    DATABASE_URI, DATABASE_NAME, COLLECTION_NAME, USE_CAPTION_FILTER,
    DATABASE_URI2, DATABASE_URI3, DATABASE_URI4, DATABASE_URI5,
    DATABASE_NAME2, DATABASE_NAME3, DATABASE_NAME4, DATABASE_NAME5,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SEARCH_CACHE_TTL = 30
SEARCH_CACHE_MAX = 256
_SEARCH_CACHE = OrderedDict()


def _cache_get(key):
    cached = _SEARCH_CACHE.get(key)
    if not cached:
        return None
    created_at, value = cached
    if time.monotonic() - created_at > SEARCH_CACHE_TTL:
        _SEARCH_CACHE.pop(key, None)
        return None
    _SEARCH_CACHE.move_to_end(key)
    return value


def _cache_set(key, value):
    _SEARCH_CACHE[key] = (time.monotonic(), value)
    _SEARCH_CACHE.move_to_end(key)
    while len(_SEARCH_CACHE) > SEARCH_CACHE_MAX:
        _SEARCH_CACHE.popitem(last=False)


def _finish_search(files, next_offset, total_results, started_at, return_time):
    elapsed = round(time.perf_counter() - started_at, 3)
    if return_time:
        return files, next_offset, total_results, elapsed
    return files, next_offset, total_results

USE_MONGO = bool(DATABASE_URI)

if not USE_MONGO:
    from database.sql_store import store


class SQLMediaDoc(dict):
    def __getattr__(self, item):
        if item == 'file_id':
            return self.get('file_id') or self.get('_id')
        if item == '_id':
            return self.get('_id') or self.get('file_id')
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
        return [_as_media_doc(d) for d in docs]


def _as_media_doc(doc):
    if doc is None:
        return SQLMediaDoc()
    d = SQLMediaDoc(doc)
    if d.get('file_id') is None and d.get('_id') is not None:
        d['file_id'] = d.get('_id')
    if d.get('_id') is None and d.get('file_id') is not None:
        d['_id'] = d.get('file_id')
    return d


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
                if (doc.get('file_id') or doc.get('_id')) not in val['$in']:
                    return False
            elif (doc.get('file_id') or doc.get('_id')) != val:
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
        _SEARCH_CACHE.clear()
        return SQLDeleteResult(len(ids))

    async def delete_one(self, query):
        docs = [d for d in await self._all_docs() if _match_filter(d, query)]
        if not docs:
            return SQLDeleteResult(0)
        fid = docs[0]['file_id']
        with store.begin() as conn:
            conn.execute(text("DELETE FROM media WHERE file_id=:fid"), {"fid": fid})
        _SEARCH_CACHE.clear()
        return SQLDeleteResult(1)

    async def drop(self):
        with store.begin() as conn:
            conn.execute(text("DELETE FROM media"))
        _SEARCH_CACHE.clear()


if USE_MONGO:
    _mongo_defs = [
        (DATABASE_URI, DATABASE_NAME),
        (DATABASE_URI2, DATABASE_NAME2),
        (DATABASE_URI3, DATABASE_NAME3),
        (DATABASE_URI4, DATABASE_NAME4),
        (DATABASE_URI5, DATABASE_NAME5),
    ]
    _seen = set()
    _mongo_collections = []
    for uri, db_name in _mongo_defs:
        if not uri:
            continue
        key = (uri.strip(), (db_name or DATABASE_NAME).strip())
        if key in _seen:
            continue
        _seen.add(key)
        client = AsyncIOMotorClient(key[0])
        _mongo_collections.append(client[key[1]][COLLECTION_NAME])

    if not _mongo_collections:
        raise RuntimeError("At least one MongoDB URI is required when DATABASE_URI mode is enabled")

    MONGO_SHARD_COUNT = len(_mongo_collections)
    logger.info("Media DB shards enabled: %d", MONGO_SHARD_COUNT)

    class MongoUnionCursor:
        def __init__(self, query=None, projection=None):
            self.query = query or {}
            self.projection = projection
            self._sort = None
            self._skip = 0
            self._limit = None

        def sort(self, field, direction):
            self._sort = (field, direction)
            return self

        def skip(self, value):
            self._skip = value
            return self

        def limit(self, value):
            self._limit = value
            return self

        async def to_list(self, length=None):
            requested = self._limit if self._limit is not None else length
            per_shard_limit = self._skip + requested if requested is not None else None

            if MONGO_SHARD_COUNT == 1:
                cursor = _mongo_collections[0].find(self.query, self.projection)
                if self._sort:
                    field, direction = self._sort
                    sort_field = 'created_at' if field == '$natural' else field
                    cursor = cursor.sort(sort_field, direction)
                if self._skip:
                    cursor = cursor.skip(self._skip)
                if requested is not None:
                    cursor = cursor.limit(requested)
                docs = await cursor.to_list(length=requested)
                return [_as_media_doc(d) for d in docs]

            async def _fetch(col):
                cursor = col.find(self.query, self.projection)
                if self._sort:
                    field, direction = self._sort
                    sort_field = 'created_at' if field == '$natural' else field
                    cursor = cursor.sort(sort_field, direction)
                if per_shard_limit is not None:
                    cursor = cursor.limit(per_shard_limit)
                docs = await cursor.to_list(length=per_shard_limit)
                return [_as_media_doc(d) for d in docs]

            parts = await asyncio.gather(*[_fetch(c) for c in _mongo_collections])
            docs = [d for part in parts for d in part]

            if self._sort:
                field, direction = self._sort
                reverse = direction == -1
                key = 'created_at' if field in ('$natural', '_id') else field
                docs.sort(key=lambda d: d.get(key, 0), reverse=reverse)

            docs = docs[self._skip:]
            cap = requested
            if cap is not None:
                docs = docs[:cap]
            if length is not None:
                docs = docs[:length]
            return docs

    class MongoMergedCollection:
        async def find(self, query=None, projection=None):
            return MongoUnionCursor(query=query, projection=projection)

        async def delete_many(self, query):
            results = await asyncio.gather(*[col.delete_many(query) for col in _mongo_collections])
            deleted_count = sum(r.deleted_count for r in results)
            if deleted_count:
                _SEARCH_CACHE.clear()
            return SQLDeleteResult(deleted_count)

        async def delete_one(self, query):
            deleted = 0
            for col in _mongo_collections:
                if deleted:
                    break
                res = await col.delete_one(query)
                deleted += res.deleted_count
            if deleted:
                _SEARCH_CACHE.clear()
            return SQLDeleteResult(deleted)

        async def drop(self):
            await asyncio.gather(*[col.drop() for col in _mongo_collections])
            _SEARCH_CACHE.clear()

    class Media:
        collection = MongoMergedCollection()

        @staticmethod
        async def ensure_indexes():
            async def _create_idx(col, spec):
                try:
                    await col.create_index(spec)
                except OperationFailure as exc:
                    # Some providers can return stale/invalid options for existing
                    # indexes (especially around implicit _id index metadata).
                    # Do not crash bot startup for non-fatal index option issues.
                    if getattr(exc, 'code', None) == 197 or 'InvalidIndexSpecificationOption' in str(exc):
                        logger.warning("Skipping incompatible index option on %s: %s", col.name, exc)
                        return
                    raise

            tasks = []
            for col in _mongo_collections:
                tasks.append(_create_idx(col, [('file_name', 1)]))
                tasks.append(_create_idx(col, [('created_at', -1)]))
            await asyncio.gather(*tasks)

        @staticmethod
        async def count_documents(query=None):
            q = query or {}
            if MONGO_SHARD_COUNT == 1:
                return await _mongo_collections[0].count_documents(q)
            counts = await asyncio.gather(*[col.count_documents(q) for col in _mongo_collections])
            return sum(counts)

        @staticmethod
        def find(query=None):
            return MongoUnionCursor(query=query)

    def _target_collection(file_id: str):
        idx = int(hashlib.md5(file_id.encode('utf-8')).hexdigest(), 16) % len(_mongo_collections)
        return _mongo_collections[idx]

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
        doc = {
            '_id': file_id,
            'file_ref': file_ref,
            'file_name': file_name,
            'file_size': media.file_size,
            'file_type': media.file_type,
            'mime_type': media.mime_type,
            'caption': media.caption.html if media.caption else None,
            'created_at': time.time(),
        }
        try:
            await _target_collection(file_id).insert_one(doc)
            _SEARCH_CACHE.clear()
        except DuplicateKeyError:
            logger.warning(f'{getattr(media, "file_name", "NO_FILE")} is already saved in database')
            return False, 0
        except Exception:
            logger.exception('Error occurred while saving file in database')
            return False, 2
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
    _SEARCH_CACHE.clear()
    return True, 1


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

# SQL fast-path overrides

def _sql_row_to_doc(row):
    return SQLMediaDoc(
        dict(
            file_id=row[0],
            _id=row[0],
            file_ref=row[1],
            file_name=row[2],
            file_size=row[3],
            file_type=row[4],
            mime_type=row[5],
            caption=row[6],
            created_at=row[7],
        )
    )


def _build_mongo_search_filter(query, file_type=None):
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        boundary = r'[\.\+\-_\(\)\[\]\{\}\s]'
        raw_pattern = rf'(\b|{boundary}){re.escape(query)}(\b|{boundary})'
    else:
        raw_pattern = r'.*'.join(map(re.escape, query.split()))

    regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    if USE_CAPTION_FILTER:
        search_filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        search_filter = {'file_name': regex}

    if file_type:
        search_filter['file_type'] = file_type
    return search_filter


async def get_search_results(
    query,
    file_type=None,
    max_results=10,
    offset=0,
    filter=False,
    fast=False,
    return_time=False,
):
    """Return matching media files, next offset, total result count, and optionally elapsed time."""

    started_at = time.perf_counter()
    query = (query or '').strip()
    offset = max(int(offset or 0), 0)
    max_results = max(int(max_results or 0), 0)

    if max_results == 0:
        return _finish_search([], '', 0, started_at, return_time)

    cache_key = (query.lower(), file_type, max_results, offset, bool(USE_CAPTION_FILTER), bool(USE_MONGO), fast)
    cached = _cache_get(cache_key)
    if cached is not None:
        files, next_offset, total_results = cached
        return _finish_search(files, next_offset, total_results, started_at, return_time)

    if not USE_MONGO:
        terms = [t for t in query.split() if t]
        where = []
        params = {"offset": offset, "limit": max_results}

        if file_type:
            where.append("file_type = :file_type")
            params["file_type"] = file_type

        if terms:
            term_sql = []
            for idx, term in enumerate(terms):
                key = f"term_{idx}"
                params[key] = f"%{term}%"
                if USE_CAPTION_FILTER:
                    term_sql.append(f"(file_name ILIKE :{key} OR COALESCE(caption, '') ILIKE :{key})")
                else:
                    term_sql.append(f"file_name ILIKE :{key}")
            where.append(" AND ".join(term_sql))

        where_clause = " AND ".join(where) if where else "TRUE"

        with store.begin() as conn:
            if fast:
                total_results = None
                params["limit"] = max_results + 1
            else:
                total_results = int(conn.execute(text(f"SELECT COUNT(*) FROM media WHERE {where_clause}"), params).scalar() or 0)
            rows = conn.execute(
                text(
                    f"""
                    SELECT file_id, file_ref, file_name, file_size, file_type, mime_type, caption, created_at
                    FROM media
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    OFFSET :offset LIMIT :limit
                    """
                ),
                params,
            ).fetchall()

        files = [_sql_row_to_doc(row) for row in rows]
        has_more = fast and len(files) > max_results
        if has_more:
            files = files[:max_results]

        next_offset = offset + max_results
        if fast:
            total_results = offset + len(files) + (1 if has_more else 0)
            if not has_more:
                next_offset = ''
        elif next_offset >= total_results:
            next_offset = ''
        result = (files, next_offset, total_results)
        _cache_set(cache_key, result)
        return _finish_search(*result, started_at, return_time)

    try:
        search_filter = _build_mongo_search_filter(query, file_type=file_type)
    except Exception:
        return _finish_search([], '', 0, started_at, return_time)

    projection = {
        'file_ref': 1,
        'file_name': 1,
        'file_size': 1,
        'file_type': 1,
        'mime_type': 1,
        'caption': 1,
        'created_at': 1,
    }

    if MONGO_SHARD_COUNT == 1:
        col = _mongo_collections[0]
        docs_limit = max_results + 1 if fast else max_results
        docs_task = (
            col.find(search_filter, projection)
            .sort('created_at', -1)
            .skip(offset)
            .limit(docs_limit)
            .to_list(length=docs_limit)
        )
        if fast:
            docs = await docs_task
            has_more = len(docs) > max_results
            files = [_as_media_doc(d) for d in docs[:max_results]]
            total_results = offset + len(files) + (1 if has_more else 0)
            next_offset = offset + max_results if has_more else ''
        else:
            count_task = col.count_documents(search_filter)
            total_results, docs = await asyncio.gather(count_task, docs_task)
            next_offset = offset + max_results
            if next_offset >= total_results:
                next_offset = ''
            files = [_as_media_doc(d) for d in docs]
        result = (files, next_offset, total_results)
        _cache_set(cache_key, result)
        return _finish_search(*result, started_at, return_time)

    fetch_limit = offset + max_results + (1 if fast else 0)

    async def _fetch(col):
        docs = await (
            col.find(search_filter, projection)
            .sort('created_at', -1)
            .limit(fetch_limit)
            .to_list(length=fetch_limit)
        )
        return [_as_media_doc(d) for d in docs]

    fetch_task = asyncio.gather(*[_fetch(col) for col in _mongo_collections])
    if fast:
        parts = await fetch_task
        total_results = None
    else:
        count_task = asyncio.gather(*[col.count_documents(search_filter) for col in _mongo_collections])
        counts, parts = await asyncio.gather(count_task, fetch_task)
        total_results = sum(counts)

    files = [d for part in parts for d in part]
    files.sort(key=lambda d: d.get('created_at', 0), reverse=True)
    page_files = files[offset: offset + max_results + (1 if fast else 0)]
    has_more = fast and len(page_files) > max_results
    files = page_files[:max_results]

    next_offset = offset + max_results
    if fast:
        total_results = offset + len(files) + (1 if has_more else 0)
        if not has_more:
            next_offset = ''
    elif next_offset >= total_results:
        next_offset = ''

    result = (files, next_offset, total_results)
    _cache_set(cache_key, result)
    return _finish_search(*result, started_at, return_time)


async def get_file_details(query):
    if not USE_MONGO:
        with store.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT file_id, file_ref, file_name, file_size, file_type, mime_type, caption, created_at "
                    "FROM media WHERE file_id=:file_id LIMIT 1"
                ),
                {"file_id": query},
            ).first()
        return [_sql_row_to_doc(row)] if row else []

    search_filter = {'_id': query}
    if MONGO_SHARD_COUNT == 1:
        filedetails = await _mongo_collections[0].find(search_filter).limit(1).to_list(length=1)
        return [_as_media_doc(filedetails[0])] if filedetails else []

    primary_col = _target_collection(query)
    filedetails = await primary_col.find(search_filter).limit(1).to_list(length=1)
    if filedetails:
        return [_as_media_doc(filedetails[0])]

    fallback_cols = [col for col in _mongo_collections if col is not primary_col]
    fallback_results = await asyncio.gather(
        *[col.find(search_filter).limit(1).to_list(length=1) for col in fallback_cols]
    )
    for filedetails in fallback_results:
        if filedetails:
            return [_as_media_doc(filedetails[0])]
    return []


async def get_movie_list(limit=20):
    if not USE_MONGO:
        with store.begin() as conn:
            rows = conn.execute(text("SELECT file_name FROM media ORDER BY created_at DESC LIMIT 300")).fetchall()
        results = []
        for row in rows:
            name = row[0] or ""
            if not re.search(r"(s\d{1,2}|season\s*\d+).*?(e\d{1,2}|episode\s*\d+)", name, re.I):
                results.append(name)
            if len(results) >= limit:
                break
        return results

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
    if not USE_MONGO:
        with store.begin() as conn:
            rows = conn.execute(text("SELECT file_name FROM media ORDER BY created_at DESC LIMIT 500")).fetchall()
        grouped = defaultdict(list)

        for row in rows:
            name = row[0] or ""
            match = re.search(r"(.*?)(?:S\d{1,2}|Season\s*\d+).*?(?:E|Ep|Episode)?(\d{1,2})", name, re.I)
            if match:
                title = match.group(1).strip().title()
                episode = int(match.group(2))
                grouped[title].append(episode)
            if len(grouped) >= limit:
                break

        return {
            title: sorted(set(eps))[:10]
            for title, eps in grouped.items() if eps
        }

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
