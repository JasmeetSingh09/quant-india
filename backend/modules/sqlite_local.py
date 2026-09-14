"""
sqlite_local.py — how modules that keep their own SQLite file connect to it.

stock_universe, screener and alerts keep tables in a local SQLite file rather
than the main database. They opened it with plain sqlite3.connect, which waits
5 seconds for a lock. On 2026-09-13 production's stock list refresh failed with
"database is locked" five seconds after startup, while the screener cache build
was holding the write lock (docs/PHASE2_FINDINGS_2026-09-14.md, section 1).

db.get_conn and news.py already wait 30 seconds and use WAL, in which reading
never blocks writing. This gives the other modules the same.
"""

import sqlite3

_WAIT_SECONDS = 30


def connect(path):
    """A connection that waits up to 30 seconds for a lock, in WAL mode."""
    conn = sqlite3.connect(path, timeout=_WAIT_SECONDS)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass    # a file that cannot switch keeps its mode; the wait still applies
    return conn
