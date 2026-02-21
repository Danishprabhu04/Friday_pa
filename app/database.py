"""
database.py — SQLite persistence layer for Friday (Phase 3).

Uses aiosqlite for non-blocking database access.
All tables are auto-created on init_db().
"""

import json
import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_db_path: str = "data/friday.db"
_connection: aiosqlite.Connection | None = None

# ── Schema ───────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    role        TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    timestamp   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    instruction TEXT    NOT NULL,
    command     TEXT,
    status      TEXT    NOT NULL,
    cost        TEXT,
    timestamp   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS resource_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    details     TEXT,
    timestamp   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS patterns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT   NOT NULL,
    key         TEXT    NOT NULL,
    count       INTEGER NOT NULL DEFAULT 1,
    last_seen   REAL    NOT NULL,
    UNIQUE(pattern_type, key)
);

CREATE TABLE IF NOT EXISTS preferences (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS optimization_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    action    TEXT NOT NULL,
    reason    TEXT,
    timestamp REAL NOT NULL
);
"""


# ── Lifecycle ────────────────────────────────────────────────────────────────

async def init_db(db_path: str) -> None:
    """Initialise the database: create dir, open connection, run schema."""
    global _db_path, _connection

    _db_path = db_path
    db_file = Path(_db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    _connection = await aiosqlite.connect(_db_path)
    _connection.row_factory = aiosqlite.Row
    await _connection.executescript(_SCHEMA)
    await _connection.commit()
    logger.info("Database initialised at %s", _db_path)


async def close_db() -> None:
    """Close the database connection."""
    global _connection
    if _connection:
        await _connection.close()
        _connection = None
        logger.info("Database connection closed")


def _conn() -> aiosqlite.Connection:
    """Return the active connection (raises if not initialised)."""
    if _connection is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _connection


# ── Generic helpers ──────────────────────────────────────────────────────────

async def insert(table: str, **kwargs) -> int:
    """Insert a row and return the new row id."""
    cols = ", ".join(kwargs.keys())
    placeholders = ", ".join("?" for _ in kwargs)
    values = list(kwargs.values())

    async with _conn().cursor() as cur:
        await cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", values)
        await _conn().commit()
        return cur.lastrowid  # type: ignore


async def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SELECT and return rows as dicts."""
    async with _conn().execute(sql, params) as cur:
        rows = await cur.fetchall()
        return [dict(row) for row in rows]


async def execute(sql: str, params: tuple = ()) -> None:
    """Run a non-SELECT statement."""
    await _conn().execute(sql, params)
    await _conn().commit()


async def count(table: str) -> int:
    """Return the row count of a table."""
    rows = await query(f"SELECT COUNT(*) as c FROM {table}")
    return rows[0]["c"] if rows else 0
