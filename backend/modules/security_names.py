"""
security_names.py — company names in the SHARED database, for search and checks.

`stock_universe` keeps its NSE list in a local SQLite file (`sqlite_local`). On
production that file is empty: the list is refreshed from NSE, and NSE collection
is paused. So production knew symbols (from bhavcopy) but no names. Searching
"20 microns" found nothing, "reliance" found only RELIANCE, and the news
integrity check tested headlines against bare tickers and reported 52% of
articles as off-topic when 98.7% name their company (2026-10-05 review).

This table holds names in the database every process shares, Postgres on
production and SQLite locally. It is loaded once from a stored list
(`seed_from_file`, backend/data/security_names_nse_2026-08-21.json), the NSE list saved on 2026-08-21. Nothing is fetched
from NSE. `stock_universe` falls back to it whenever its own list is empty.
"""

import json
from datetime import datetime
from pathlib import Path

from db import get_conn, IS_POSTGRES

_READY = False
# The stored list shipped with the app. Loaded into an EMPTY table on first use,
# so production gets names without anyone handling database credentials.
SEED_FILE = Path(__file__).parent.parent / "data" / "security_names_nse_2026-08-21.json"


def _init():
    global _READY
    if _READY:
        return
    conn = get_conn()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS security_names ("
            " yf_ticker TEXT PRIMARY KEY,"
            " symbol TEXT NOT NULL,"
            " company_name TEXT NOT NULL,"
            " isin TEXT,"
            " series TEXT,"
            " source TEXT NOT NULL,"
            " loaded_at TEXT NOT NULL)")
        conn.commit()
        _READY = True
        empty = int(conn.execute("SELECT COUNT(*) FROM security_names").fetchone()[0] or 0) == 0
    finally:
        conn.close()
    if empty:
        seed_from_file()


def seed_from_file(path=None) -> dict:
    """Load the shipped list (see SEED_FILE). Safe to repeat: existing rows are refreshed, not duplicated."""
    p = Path(path) if path else SEED_FILE
    if not p.exists():
        return {"loaded": 0, "reason": f"{p.name} not found"}
    data = json.loads(p.read_text(encoding="utf-8"))
    fields = data["fields"]
    rows = [dict(zip(fields, r)) for r in data["rows"]]
    return load(rows, source=data.get("source", p.name)[:200])


def load(rows: list, source: str) -> dict:
    """Insert or refresh names. rows: dicts with yf_ticker, symbol, company_name, isin, series."""
    _init()
    now = datetime.now().isoformat(timespec="seconds")
    sql = ("INSERT INTO security_names (yf_ticker, symbol, company_name, isin, series, source, loaded_at) "
           "VALUES (?,?,?,?,?,?,?) "
           + ("ON CONFLICT (yf_ticker) DO UPDATE SET company_name=EXCLUDED.company_name, isin=EXCLUDED.isin, "
              "series=EXCLUDED.series, source=EXCLUDED.source, loaded_at=EXCLUDED.loaded_at"
              if IS_POSTGRES else "ON CONFLICT (yf_ticker) DO UPDATE SET company_name=excluded.company_name, "
              "isin=excluded.isin, series=excluded.series, source=excluded.source, loaded_at=excluded.loaded_at"))
    vals = [(r["yf_ticker"], r["symbol"], r["company_name"], r.get("isin"), r.get("series"), source, now)
            for r in rows if r.get("yf_ticker") and r.get("company_name")]
    conn = get_conn()
    try:
        conn.executemany(sql, vals)
        conn.commit()
    finally:
        conn.close()
    return {"loaded": len(vals), "source": source}


def lookup(symbol_or_ticker: str):
    """The stored record for NSE symbol 'SBIN' or ticker 'SBIN.NS', or None."""
    _init()
    t = (symbol_or_ticker or "").strip().upper()
    if not t:
        return None
    if not t.endswith(".NS"):
        t += ".NS"
    conn = get_conn()
    try:
        r = conn.execute("SELECT symbol, company_name, series, isin, yf_ticker FROM security_names "
                         "WHERE yf_ticker = ?", (t,)).fetchone()
    finally:
        conn.close()
    return None if not r else {"symbol": r[0], "company_name": r[1], "series": r[2],
                               "isin": r[3], "yf_ticker": r[4], "exchange": "NSE"}


def search(query: str, limit: int = 30) -> list:
    """Symbol or name contains the query; exact symbol first, then prefix, then the rest."""
    _init()
    q = (query or "").strip().upper()
    if not q:
        return []
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT symbol, company_name, series, isin, yf_ticker FROM security_names "
            "WHERE UPPER(symbol) LIKE ? OR UPPER(company_name) LIKE ? "
            "ORDER BY CASE WHEN UPPER(symbol) = ? THEN 0 WHEN UPPER(symbol) LIKE ? THEN 1 "
            "WHEN UPPER(company_name) LIKE ? THEN 2 ELSE 3 END, company_name LIMIT ?",
            (f"%{q}%", f"%{q}%", q, f"{q}%", f"{q}%", int(limit))).fetchall()
    finally:
        conn.close()
    return [{"symbol": r[0], "company_name": r[1], "series": r[2], "isin": r[3],
             "yf_ticker": r[4], "exchange": "NSE"} for r in rows]


def count() -> int:
    _init()
    conn = get_conn()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM security_names").fetchone()[0] or 0)
    finally:
        conn.close()
