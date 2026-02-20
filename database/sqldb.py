import asyncio
import logging
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse

from info import SQLDB, TURSO_AUTH_TOKEN

logger = logging.getLogger(__name__)

_LIBSQL_CLIENT = None
_LIBSQL_LOCK = asyncio.Lock()
_FALLBACK_SQLITE = "data/turso_fallback.db"
_LAST_LIBSQL_WARNING = {"query": 0.0, "fetch": 0.0}
_WARNING_INTERVAL = 60.0
_LIBSQL_DISABLED_UNTIL = 0.0
_LIBSQL_COOLDOWN_SECONDS = 300.0


def _libsql_temporarily_disabled() -> bool:
    return time.monotonic() < _LIBSQL_DISABLED_UNTIL


def _disable_libsql_temporarily(error: Exception) -> None:
    global _LIBSQL_DISABLED_UNTIL
    _LIBSQL_DISABLED_UNTIL = time.monotonic() + _LIBSQL_COOLDOWN_SECONDS
    logger.warning(
        "libsql temporarily disabled for %.0fs after connection/query failure; using local fallback sqlite. error=%s",
        _LIBSQL_COOLDOWN_SECONDS,
        error,
    )


def _log_libsql_fallback(kind: str, error: Exception) -> None:
    now = time.monotonic()
    last = _LAST_LIBSQL_WARNING.get(kind, 0.0)
    if now - last >= _WARNING_INTERVAL:
        _LAST_LIBSQL_WARNING[kind] = now
        logger.warning(f"libsql {kind} failed, using local fallback sqlite. error={error}")
    else:
        logger.debug(f"libsql {kind} failed again, still using fallback sqlite. error={error}")


def _fallback_conn() -> sqlite3.Connection:
    path = Path(_FALLBACK_SQLITE)
    if path.parent and str(path.parent) != ".":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn




def get_fallback_db_path() -> str:
    return _FALLBACK_SQLITE


def get_fallback_db_size() -> int:
    with _fallback_conn() as conn:
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        return int(page_count) * int(page_size)


def sqldb_enabled() -> bool:
    return bool(SQLDB)


def libsql_mode() -> bool:
    db_url = (SQLDB or "").strip()
    return db_url.startswith("libsql://") or db_url.startswith("ws://") or db_url.startswith("wss://")


def libsql_fallback_active() -> bool:
    return libsql_mode() and _libsql_temporarily_disabled()


def _require_libsql_client_module():
    try:
        from libsql_client import create_client  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "libsql-client is required for Turso/libsql URLs. Install dependencies from requirements.txt."
        ) from e
    return create_client


async def _get_libsql_client():
    global _LIBSQL_CLIENT
    if _LIBSQL_CLIENT is not None:
        return _LIBSQL_CLIENT

    async with _LIBSQL_LOCK:
        if _LIBSQL_CLIENT is not None:
            return _LIBSQL_CLIENT

        if not TURSO_AUTH_TOKEN:
            raise RuntimeError("TURSO_AUTH_TOKEN is required when SQLDB uses libsql:// URL.")

        create_client = _require_libsql_client_module()
        _LIBSQL_CLIENT = create_client(url=SQLDB.strip(), auth_token=TURSO_AUTH_TOKEN)
        return _LIBSQL_CLIENT


async def _libsql_execute(query: str, params=()):
    client = await _get_libsql_client()
    params = tuple(params or ())

    # Try common call variants for libsql-client compatibility.
    try:
        return await client.execute(query, params)
    except TypeError:
        pass

    try:
        return await client.execute(query, args=list(params))
    except TypeError:
        pass

    stmt = {"sql": query, "args": list(params)}
    return await client.execute(stmt)


async def db_execute(query: str, params=()):
    if libsql_mode():
        if _libsql_temporarily_disabled():
            with _fallback_conn() as conn:
                cur = conn.execute(query, tuple(params or ()))
                conn.commit()
                return cur
        try:
            return await _libsql_execute(query, params)
        except Exception as e:
            if "Cannot connect to host" in str(e) or "Name or service not known" in str(e):
                _disable_libsql_temporarily(e)
            else:
                _log_libsql_fallback("query", e)
            with _fallback_conn() as conn:
                cur = conn.execute(query, tuple(params or ()))
                conn.commit()
                return cur

    with get_conn() as conn:
        cur = conn.execute(query, tuple(params or ()))
        conn.commit()
        return cur


async def db_fetchall(query: str, params=()):
    if libsql_mode():
        if _libsql_temporarily_disabled():
            with _fallback_conn() as conn:
                try:
                    cur = conn.execute(query, tuple(params or ()))
                    return [dict(r) for r in cur.fetchall()]
                except sqlite3.OperationalError as oe:
                    if "no such table" in str(oe).lower() and query.strip().lower().startswith("select"):
                        return []
                    raise
        try:
            result = await _libsql_execute(query, params)
            rows = getattr(result, "rows", []) or []
            normalized = []
            for row in rows:
                if isinstance(row, dict):
                    normalized.append(row)
                else:
                    normalized.append(dict(row)) if hasattr(row, "keys") else normalized.append({str(i): v for i, v in enumerate(row)})
            return normalized
        except Exception as e:
            if "Cannot connect to host" in str(e) or "Name or service not known" in str(e):
                _disable_libsql_temporarily(e)
            else:
                _log_libsql_fallback("fetch", e)
            with _fallback_conn() as conn:
                try:
                    cur = conn.execute(query, tuple(params or ()))
                    return [dict(r) for r in cur.fetchall()]
                except sqlite3.OperationalError as oe:
                    if "no such table" in str(oe).lower() and query.strip().lower().startswith("select"):
                        return []
                    raise

    with get_conn() as conn:
        try:
            cur = conn.execute(query, tuple(params or ()))
            return [dict(r) for r in cur.fetchall()]
        except sqlite3.OperationalError as oe:
            if "no such table" in str(oe).lower() and query.strip().lower().startswith("select"):
                return []
            raise


async def db_fetchone(query: str, params=()):
    rows = await db_fetchall(query, params)
    return rows[0] if rows else None


def get_sqldb_path() -> str:
    db_url = (SQLDB or "").strip()
    if not db_url:
        return ""

    if libsql_mode():
        return ""

    if db_url.startswith("sqlite:///"):
        return db_url.replace("sqlite:///", "", 1)
    if db_url.startswith("sqlite://"):
        return db_url.replace("sqlite://", "", 1)

    parsed = urlparse(db_url)
    if parsed.scheme and parsed.scheme != "file":
        raise RuntimeError(
            f"Unsupported SQLDB scheme '{parsed.scheme}'. Use sqlite file path or libsql:// URL."
        )
    return db_url


def get_conn() -> sqlite3.Connection:
    if libsql_mode():
        raise RuntimeError("get_conn() is not available in libsql mode. Use db_execute/db_fetch* helpers.")
    db_path = get_sqldb_path() or "bot.db"
    path = Path(db_path)
    if path.parent and str(path.parent) != ".":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
