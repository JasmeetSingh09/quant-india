import os
"""
screener.py — NSE stock screener.

Filter the NSE universe by fundamentals (P/E, ROE, market cap, sector, etc.).

Design: fetching metrics live for hundreds of stocks would be far too slow
(~1s each), so we maintain a CACHED metrics table in SQLite, refreshed in the
background. The screen() query then filters that cache instantly.

The screenable universe is the ~200 major NSE stocks grouped in
data_fetcher.NSE_SECTORS (large + mid caps across every sector).
"""

import sys
import sqlite3
import yfinance as yf
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

DB_PATH = Path(os.environ.get("QUANT_DATA_DIR", str(Path(__file__).parent.parent))) / "quant_platform.db"
sys.path.insert(0, str(Path(__file__).parent))


def _init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS screener_metrics (
            ticker        TEXT PRIMARY KEY,
            company_name  TEXT,
            sector        TEXT,
            price         REAL,
            market_cap    REAL,
            pe_ratio      REAL,
            roe           REAL,
            profit_margin REAL,
            debt_to_equity REAL,
            revenue_growth REAL,
            dividend_yield REAL,
            updated_at    TEXT
        )
    """)
    conn.commit()
    conn.close()


def build_screener_cache(limit: int = None) -> dict:
    """
    Fetch fundamentals for the NSE universe and cache them. Slow (~5-10 min for
    ~200 stocks) — run in the background or on a daily schedule.
    """
    _init_db()
    from data_fetcher import NSE_SECTORS

    # Flatten the sector map into (ticker, sector) pairs
    pairs = []
    for sector, tickers in NSE_SECTORS.items():
        for t in tickers:
            pairs.append((t, sector))
    # Deduplicate (some tickers appear in multiple sectors)
    seen = set(); uniq = []
    for t, s in pairs:
        if t not in seen:
            seen.add(t); uniq.append((t, s))
    if limit:
        uniq = uniq[:limit]

    conn = sqlite3.connect(DB_PATH)
    count = 0
    for ticker, sector in uniq:
        try:
            info = yf.Ticker(ticker).info
            conn.execute("""
                INSERT OR REPLACE INTO screener_metrics
                  (ticker, company_name, sector, price, market_cap, pe_ratio, roe,
                   profit_margin, debt_to_equity, revenue_growth, dividend_yield, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ticker,
                info.get("shortName", ticker.replace(".NS", "")),
                sector,
                info.get("currentPrice") or info.get("regularMarketPrice"),
                info.get("marketCap"),
                info.get("trailingPE"),
                (info.get("returnOnEquity") or 0) * 100 if info.get("returnOnEquity") is not None else None,
                (info.get("profitMargins") or 0) * 100 if info.get("profitMargins") is not None else None,
                round(info.get("debtToEquity") / 100, 2) if info.get("debtToEquity") is not None else None,
                (info.get("revenueGrowth") or 0) * 100 if info.get("revenueGrowth") is not None else None,
                (info.get("dividendYield") or 0) if info.get("dividendYield") is not None else None,
                datetime.now().isoformat(),
            ))
            count += 1
            if count % 25 == 0:
                conn.commit()
                print(f"  screener cache: {count}/{len(uniq)}")
        except Exception:
            pass
    conn.commit()
    conn.close()
    print(f"Screener cache built: {count} stocks")
    return {"status": "built", "count": count}


def get_screener_status() -> dict:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    n = conn.execute("SELECT COUNT(*) FROM screener_metrics").fetchone()[0]
    last = conn.execute("SELECT MAX(updated_at) FROM screener_metrics").fetchone()[0]
    conn.close()
    return {"cached_stocks": n, "last_updated": last}


def ensure_screener_cache():
    """Build the cache on first run if empty (called on startup)."""
    if get_screener_status()["cached_stocks"] == 0:
        print("Screener cache empty — building in background...")
        build_screener_cache()


# Sortable / filterable numeric columns
_NUMERIC = {"market_cap", "pe_ratio", "roe", "profit_margin",
            "debt_to_equity", "revenue_growth", "dividend_yield", "price"}


def screen(filters: dict = None, sort_by: str = "market_cap",
           descending: bool = True, limit: int = 50) -> dict:
    """
    Filter the cached universe.

    filters example:
      {"pe_max": 20, "roe_min": 15, "market_cap_min": 1e11, "sector": "IT"}
    Supported: <col>_min / <col>_max for any numeric column, and "sector".
    """
    _init_db()
    filters = filters or {}
    where, params = [], []

    # Map short filter names to actual columns (e.g. "pe" -> "pe_ratio")
    ALIAS = {"pe": "pe_ratio", "mktcap": "market_cap", "div": "dividend_yield"}

    for key, val in filters.items():
        if val in (None, ""):
            continue
        if key == "sector":
            where.append("sector = ?"); params.append(val)
        elif key.endswith("_min"):
            col = key[:-4]; col = ALIAS.get(col, col)
            if col in _NUMERIC:
                where.append(f"{col} >= ? AND {col} IS NOT NULL"); params.append(val)
        elif key.endswith("_max"):
            col = key[:-4]; col = ALIAS.get(col, col)
            if col in _NUMERIC:
                where.append(f"{col} <= ? AND {col} IS NOT NULL"); params.append(val)

    sort_col = sort_by if sort_by in _NUMERIC else "market_cap"
    order = "DESC" if descending else "ASC"
    sql = "SELECT ticker, company_name, sector, price, market_cap, pe_ratio, roe, " \
          "profit_margin, debt_to_equity, revenue_growth, dividend_yield FROM screener_metrics"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {sort_col} {order} NULLS LAST LIMIT ?"
    params.append(limit)

    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        # SQLite without NULLS LAST support — retry simpler
        sql = sql.replace(" NULLS LAST", "")
        rows = conn.execute(sql, params).fetchall()
    conn.close()

    cols = ["ticker", "company_name", "sector", "price", "market_cap", "pe_ratio",
            "roe", "profit_margin", "debt_to_equity", "revenue_growth", "dividend_yield"]
    results = [dict(zip(cols, r)) for r in rows]
    return {"count": len(results), "filters": filters, "sort_by": sort_col, "results": results}


def get_sectors() -> list:
    from data_fetcher import NSE_SECTORS
    return sorted(NSE_SECTORS.keys())


if __name__ == "__main__":
    print("Building screener cache (this takes several minutes)...")
    build_screener_cache(limit=40)   # small sample for a quick test
    print("\nStatus:", get_screener_status())
    print("\nScreen: P/E < 30, ROE > 10%, sorted by market cap:")
    r = screen({"pe_max": 30, "roe_min": 10}, sort_by="market_cap", limit=10)
    print(f"  {r['count']} matches")
    for s in r["results"][:8]:
        print(f"   {s['ticker']:14s} PE={s['pe_ratio']}  ROE={s['roe']}  {s['sector']}")
