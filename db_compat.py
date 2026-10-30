"""
db_compat.py
------------
A thin compatibility layer so the rest of the app keeps writing exactly
the SQL it always has (sqlite-style `?` placeholders, `row["col"]` AND
`row[0]` access on results) while actually running against either:

  - SQLite (default — zero setup, used for local development), or
  - Postgres (production — set DATABASE_URL, e.g. a free Neon database)

Why a translation layer instead of just rewriting every query for
Postgres and dropping SQLite entirely? Local development with zero setup
(no database server to install) is worth keeping, and the two dialects
are close enough here that one shared layer is far less risk than
hand-porting ~40 hand-written queries scattered across 4 files.

What actually differs between the two dialects, in this codebase
specifically (checked directly, not assumed):
  - Placeholder syntax: `?` (SQLite) vs `%s` (psycopg2) — translated
    automatically in _translate_sql() below.
  - Auto-increment primary keys: `INTEGER PRIMARY KEY AUTOINCREMENT`
    (SQLite) vs `SERIAL PRIMARY KEY` (Postgres) — also translated
    automatically, so none of the 12 CREATE TABLE statements elsewhere
    needed to change.
  - Getting the id of a just-inserted row: sqlite3 gives you
    `cursor.lastrowid` for free; psycopg2 has no equivalent, so an
    INSERT that needs its new id back must add `RETURNING id` and fetch
    it — the one call site that needs this (register_user in auth.py)
    handles it explicitly rather than trying to fake lastrowid here.
  - Row access: sqlite3.Row supports both row["col"] and row[0].
    psycopg2.extras.DictCursor's DictRow does too — so no row-access
    code anywhere else needed to change.
  - TIMESTAMP columns come back as a string from SQLite but a native
    datetime object from Postgres — the couple of call sites that parse
    created_at/expires_at handle both explicitly (see auth.py,
    farm_records.py) rather than being papered over here, since silently
    stringifying every timestamp would hide real type information from
    callers that might want it.
"""

import os
import re

DATABASE_URL = os.getenv("DATABASE_URL")
USING_POSTGRES = bool(DATABASE_URL)

if USING_POSTGRES:
    import psycopg2
    import psycopg2.extras
    IntegrityError = psycopg2.IntegrityError
else:
    import sqlite3
    IntegrityError = sqlite3.IntegrityError

_PLACEHOLDER_RE = re.compile(r"\?")
_AUTOINCREMENT_RE = re.compile(r"INTEGER PRIMARY KEY AUTOINCREMENT", re.IGNORECASE)


def _translate_sql(sql):
    """SQLite-dialect SQL -> Postgres-dialect SQL. No-op when not using
    Postgres. Applied automatically inside the wrapper below, so query
    text everywhere else in the app never needs to know which database
    it's actually talking to."""
    if not USING_POSTGRES:
        return sql
    sql = _AUTOINCREMENT_RE.sub("SERIAL PRIMARY KEY", sql)
    sql = _PLACEHOLDER_RE.sub("%s", sql)
    return sql


class _PGCursorWrapper:
    """Wraps a real psycopg2 DictCursor so cur.execute(sql, params) reads
    exactly like sqlite3's — translating dialect differences on the way
    in, otherwise just delegating straight through."""

    def __init__(self, real_cursor):
        self._cur = real_cursor

    def execute(self, sql, params=()):
        self._cur.execute(_translate_sql(sql), params)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __getattr__(self, name):
        return getattr(self._cur, name)


class _PGConnWrapper:
    """Wraps a real psycopg2 connection so conn.execute(...) works the
    same convenience way sqlite3.Connection.execute() does — create a
    cursor, run the query, hand back something .fetchone()/.fetchall()
    -able, without every call site needing conn.cursor() first."""

    def __init__(self, real_conn):
        self._conn = real_conn

    def execute(self, sql, params=()):
        cur = _PGCursorWrapper(self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor))
        return cur.execute(sql, params)

    def cursor(self):
        return _PGCursorWrapper(self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor))

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def get_connection(sqlite_path=None):
    """Returns a connection usable exactly like sqlite3's:
    conn.execute(sql, params).fetchone() / .fetchall(), conn.commit(),
    conn.close(). Talks to Postgres if DATABASE_URL is set, otherwise
    SQLite at sqlite_path (or the caller's own default)."""
    if USING_POSTGRES:
        return _PGConnWrapper(psycopg2.connect(DATABASE_URL))
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn
