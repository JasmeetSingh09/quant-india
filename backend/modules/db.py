"""
db.py — one database layer for the whole app.

If the env var DATABASE_URL is set (e.g. a Supabase Postgres connection string),
the app uses Postgres. Otherwise it falls back to the local SQLite file. This means:
  * Production (Render + Supabase): durable Postgres, survives redeploys, no locks.
  * Local dev / no DATABASE_URL: works exactly as before on SQLite.

Modules keep writing normal SQL with '?' placeholders and SQLite-style DDL; this layer
translates to Postgres when needed. Use get_conn() the same way you'd use
sqlite3.connect(): conn.execute(sql, params).fetchall(), conn.commit(), conn.close().
"""

import os
import re
import sqlite3
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith("postgres")


def _resolve_sqlite_path() -> Path:
    """
    Where the SQLite file lives.

    main.py sets QUANT_DATA_DIR (from DATA_DIR) precisely so state can sit on a
    Render persistent disk — but this module used to hardcode
    backend/quant_platform.db and ignore it. That put the database INSIDE the
    container image, so every redeploy silently destroyed watchlists, portfolios,
    simulations and the prediction track record.

    Honour the data dir when set, and migrate an existing legacy file across once
    so nobody loses local data when the path moves.
    """
    legacy = Path(__file__).parent.parent / "quant_platform.db"
    data_dir = os.getenv("QUANT_DATA_DIR") or os.getenv("DATA_DIR")
    if not data_dir:
        return legacy
    try:
        target = Path(data_dir) / "quant_platform.db"
        target.parent.mkdir(parents=True, exist_ok=True)
        if legacy.exists() and not target.exists():
            import shutil
            shutil.copy2(legacy, target)      # one-time move to the durable dir
        return target
    except Exception:
        return legacy                          # never break startup over this


_SQLITE_PATH = _resolve_sqlite_path()

if IS_POSTGRES:
    import psycopg2  # noqa: E402  (only needed when Postgres is configured)
    IntegrityError = psycopg2.IntegrityError
    OperationalError = psycopg2.OperationalError
else:
    IntegrityError = sqlite3.IntegrityError
    OperationalError = sqlite3.OperationalError


# ---------------------------------------------------------------------------
# SQL translation (SQLite dialect -> Postgres), applied only when on Postgres
# ---------------------------------------------------------------------------
def _translate(sql: str) -> str:
    s = sql
    # autoincrement primary key
    s = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
               "BIGSERIAL PRIMARY KEY", s, flags=re.I)
    # INSERT OR IGNORE -> INSERT ... ON CONFLICT DO NOTHING
    had_ignore = bool(re.search(r"INSERT\s+OR\s+IGNORE", s, re.I))
    s = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", s, flags=re.I)
    if had_ignore and "on conflict" not in s.lower():
        s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    # SQL datetime('now') -> CURRENT_TIMESTAMP
    s = re.sub(r"datetime\(\s*'now'\s*\)", "CURRENT_TIMESTAMP", s, flags=re.I)
    # placeholder style (do last, so we don't touch the words above)
    s = s.replace("?", "%s")
    return s


class _PgCursor:
    """Wraps a psycopg2 cursor to expose the fetchone/fetchall/lastrowid the app expects."""
    def __init__(self, cur, raw):
        self._cur = cur
        self._raw = raw

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def lastrowid(self):
        # psycopg2 has no lastrowid; lastval() returns this session's most recent
        # auto-generated (BIGSERIAL) id, which is what the app uses it for.
        try:
            c = self._raw.cursor()
            c.execute("SELECT lastval()")
            return c.fetchone()[0]
        except Exception:
            return None


class _PgConn:
    """Makes a psycopg2 connection behave like the sqlite3.Connection usage in the app
    (conn.execute(...).fetchall(), conn.commit(), conn.close())."""
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        cur = self._raw.cursor()
        cur.execute(_translate(sql), params)
        return _PgCursor(cur, self._raw)

    def executemany(self, sql, seq):
        cur = self._raw.cursor()
        cur.executemany(_translate(sql), list(seq))
        return _PgCursor(cur, self._raw)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def get_conn():
    """Return a connection usable exactly like sqlite3.connect()."""
    if IS_POSTGRES:
        return _PgConn(psycopg2.connect(DATABASE_URL, connect_timeout=10))
    conn = sqlite3.connect(_SQLITE_PATH, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    return conn


def backend_name() -> str:
    return "postgres" if IS_POSTGRES else "sqlite"
