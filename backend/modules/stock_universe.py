"""
stock_universe.py — Complete NSE + BSE stock universe with search.

Sources:
  NSE equity list CSV  — archives.nseindia.com (all ~2000 NSE-listed stocks)
  BSE equity list CSV  — bseindia.com         (all ~5000 BSE-listed stocks)

Both lists are cached in SQLite and refreshed daily.
yfinance tickers:
  NSE stocks → SYMBOL.NS   e.g. RELIANCE.NS
  BSE stocks → ISINCODE.BO or BSECODE.BO e.g. 500325.BO

Key functions:
  refresh_nse_stocks()          — download and cache full NSE list
  refresh_bse_stocks()          — download and cache full BSE list
  search_stocks(query, exchange) — fuzzy search by name or symbol
  get_stock_by_symbol(symbol)    — exact symbol lookup
  get_stocks_by_sector(sector)   — filter by sector
  get_all_symbols(exchange)      — list all symbols for a given exchange
"""

import sqlite3
import requests
import pandas as pd
import io
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

DB_PATH = Path(__file__).parent.parent / "quant_platform.db"

# Official NSE equity list (updated every trading day by NSE)
NSE_EQUITY_CSV_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"

# BSE equity list (all listed scrips)
BSE_EQUITY_CSV_URL = "https://www.bseindia.com/corporates/List_Scrips.aspx"

# Backup: NSE bhavcopy for any given date gives all traded stocks
NSE_BHAVCOPY_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"

# HTTP headers to mimic a browser (NSE blocks plain requests)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com",
}


# ---------------------------------------------------------------------------
# Database schema
# ---------------------------------------------------------------------------

def _init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nse_stocks (
            symbol          TEXT PRIMARY KEY,
            company_name    TEXT NOT NULL,
            series          TEXT,
            isin            TEXT,
            face_value      REAL,
            date_of_listing TEXT,
            sector          TEXT,
            yf_ticker       TEXT,
            last_updated    TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bse_stocks (
            bse_code        TEXT PRIMARY KEY,
            company_name    TEXT NOT NULL,
            status          TEXT,
            group_name      TEXT,
            face_value      REAL,
            isin            TEXT,
            industry        TEXT,
            sector          TEXT,
            yf_ticker       TEXT,
            last_updated    TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nse_name ON nse_stocks(company_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bse_name ON bse_stocks(company_name)")
    conn.commit()
    conn.close()


def _is_stale(exchange: str, max_hours: int = 24) -> bool:
    """Return True if the stock list hasn't been refreshed in max_hours."""
    table = "nse_stocks" if exchange == "NSE" else "bse_stocks"
    conn  = sqlite3.connect(DB_PATH)
    row   = conn.execute(f"SELECT last_updated FROM {table} LIMIT 1").fetchone()
    conn.close()
    if not row or not row[0]:
        return True
    last = datetime.fromisoformat(row[0])
    return (datetime.now() - last).total_seconds() > max_hours * 3600


# ---------------------------------------------------------------------------
# NSE download
# ---------------------------------------------------------------------------

def refresh_nse_stocks(force: bool = False) -> dict:
    """
    Download the complete NSE equity list from NSE archives and cache in SQLite.

    NSE updates this file every trading day. We refresh once per 24 hours.
    Returns {"status": "refreshed", "count": N} or {"status": "cached"}.
    """
    _init_db()
    if not force and not _is_stale("NSE"):
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM nse_stocks").fetchone()[0]
        conn.close()
        return {"status": "cached", "count": count, "exchange": "NSE"}

    # Start a session to get NSE cookies first
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        # Visit homepage to get session cookies
        session.get("https://www.nseindia.com", timeout=10)
    except Exception:
        pass

    # Download the equity list CSV
    urls_to_try = [NSE_EQUITY_CSV_URL, NSE_BHAVCOPY_URL]
    df = None
    for url in urls_to_try:
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text))
            break
        except Exception as e:
            print(f"  NSE URL {url} failed: {e}")
            continue

    if df is None or df.empty:
        return {"status": "error", "message": "Could not download NSE equity list"}

    # Normalise column names (NSE CSV has leading/trailing spaces)
    df.columns = [c.strip() for c in df.columns]

    # Expected columns: SYMBOL, NAME OF COMPANY, SERIES, DATE OF LISTING,
    #                   PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE
    now = datetime.now().isoformat()
    rows = []
    for _, row in df.iterrows():
        symbol = str(row.get("SYMBOL", "")).strip().upper()
        name   = str(row.get("NAME OF COMPANY", "")).strip()
        series = str(row.get("SERIES", "")).strip()
        isin   = str(row.get("ISIN NUMBER", "")).strip()
        face_v = row.get("FACE VALUE", row.get("PAID UP VALUE", None))
        dol    = str(row.get("DATE OF LISTING", "")).strip()

        if not symbol or not name:
            continue
        # Only keep EQ series (common equity) — skip bonds, ETFs, SME stocks
        # Comment this out if you want ETFs and bonds too
        # if series not in ("EQ", "BE", "BZ", ""):
        #     continue

        rows.append((
            symbol, name, series, isin,
            float(face_v) if face_v and str(face_v) != "nan" else None,
            dol, None, f"{symbol}.NS", now
        ))

    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM nse_stocks")
    conn.executemany("""
        INSERT OR REPLACE INTO nse_stocks
          (symbol, company_name, series, isin, face_value,
           date_of_listing, sector, yf_ticker, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    conn.close()

    print(f"NSE stock universe refreshed: {len(rows)} stocks")
    return {"status": "refreshed", "count": len(rows), "exchange": "NSE"}


# ---------------------------------------------------------------------------
# BSE download
# ---------------------------------------------------------------------------

def refresh_bse_stocks(force: bool = False) -> dict:
    """
    Download the complete BSE equity list and cache in SQLite.

    BSE's main scrip list is available as a downloadable file.
    yfinance uses BSE code + .BO suffix e.g. 500325.BO for Reliance.
    """
    _init_db()
    if not force and not _is_stale("BSE"):
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM bse_stocks").fetchone()[0]
        conn.close()
        return {"status": "cached", "count": count, "exchange": "BSE"}

    # BSE provides a downloadable list at this URL
    bse_url = (
        "https://www.bseindia.com/corporates/List_Scrips.aspx"
        "?Industry=&segment=Equity&status=Active"
    )
    session = requests.Session()
    session.headers.update({**HEADERS, "Referer": "https://www.bseindia.com"})
    try:
        session.get("https://www.bseindia.com", timeout=10)
    except Exception:
        pass

    # BSE also has a direct CSV download endpoint
    bse_csv_url = "https://www.bseindia.com/corporates/List_Scrips.aspx"
    bse_download_url = (
        "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"
        "?Group=&Scripcode=&industry=&segment=Equity&status=Active"
    )

    df = None
    for url in [bse_download_url, bse_csv_url]:
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            content = resp.text
            if "<table" in content.lower():
                # Parse HTML table
                tables = pd.read_html(io.StringIO(content))
                if tables:
                    df = tables[0]
                    break
            else:
                # Try JSON
                import json
                data = json.loads(resp.text)
                if isinstance(data, list) and data:
                    df = pd.DataFrame(data)
                    break
        except Exception as e:
            print(f"  BSE URL {url} failed: {e}")
            continue

    if df is None or df.empty:
        # Fallback: insert well-known BSE stocks manually
        print("BSE download failed — inserting major BSE stocks as fallback")
        return _insert_bse_fallback()

    df.columns = [str(c).strip() for c in df.columns]
    now = datetime.now().isoformat()
    rows = []
    for _, row in df.iterrows():
        code = str(row.get("Security Code", row.get("Scripcode", row.get("SECURITY CODE", "")))).strip()
        name = str(row.get("Security Name", row.get("ScripName", row.get("SECURITY NAME", "")))).strip()
        if not code or not name or code == "nan":
            continue
        rows.append((
            code, name,
            str(row.get("Status", "")).strip(),
            str(row.get("Group", "")).strip(),
            None, None, None, None,
            f"{code}.BO", now
        ))

    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM bse_stocks")
    conn.executemany("""
        INSERT OR REPLACE INTO bse_stocks
          (bse_code, company_name, status, group_name, face_value,
           isin, industry, sector, yf_ticker, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    conn.close()

    print(f"BSE stock universe refreshed: {len(rows)} stocks")
    return {"status": "refreshed", "count": len(rows), "exchange": "BSE"}


def _insert_bse_fallback() -> dict:
    """Insert the top 200 BSE stocks when live download fails."""
    bse_major = [
        ("500325", "Reliance Industries Ltd"),
        ("532540", "Tata Consultancy Services Ltd"),
        ("500180", "HDFC Bank Ltd"),
        ("500209", "Infosys Ltd"),
        ("500696", "Hindustan Unilever Ltd"),
        ("500010", "Housing Development Finance Corp"),
        ("532174", "ICICI Bank Ltd"),
        ("500875", "ITC Ltd"),
        ("532234", "Kotak Mahindra Bank Ltd"),
        ("500112", "State Bank of India"),
        ("500520", "Mahindra & Mahindra Ltd"),
        ("532500", "Maruti Suzuki India Ltd"),
        ("500570", "Titan Company Ltd"),
        ("532648", "Bajaj Finance Ltd"),
        ("500400", "Tata Motors Ltd"),
        ("500483", "Bajaj Auto Ltd"),
        ("500010", "HDFC Ltd"),
        ("500087", "Cipla Ltd"),
        ("500124", "Dr Reddys Laboratories Ltd"),
        ("524715", "Sun Pharmaceutical Industries Ltd"),
        ("532454", "Bharti Airtel Ltd"),
        ("500440", "Hindalco Industries Ltd"),
        ("500470", "Tata Steel Ltd"),
        ("500312", "ONGC Ltd"),
        ("500696", "HUL"),
        ("500550", "Wipro Ltd"),
        ("532281", "HCL Technologies Ltd"),
        ("532755", "Tech Mahindra Ltd"),
        ("500002", "ABB India Ltd"),
        ("500408", "Larsen & Toubro Ltd"),
        ("500790", "Nestle India Ltd"),
        ("507685", "Hero MotoCorp Ltd"),
        ("532977", "Bajaj Finserv Ltd"),
        ("500150", "Eicher Motors Ltd"),
        ("500820", "Asian Paints Ltd"),
        ("500010", "HDFC Bank Ltd"),
        ("532978", "DLF Ltd"),
        ("533278", "Coal India Ltd"),
        ("532555", "NTPC Ltd"),
        ("532187", "Power Grid Corporation of India Ltd"),
        ("500390", "Ultratech Cement Ltd"),
        ("500397", "Shree Cement Ltd"),
        ("500380", "Ambuja Cements Ltd"),
        ("500425", "Ambuja Cements"),
        ("500103", "BPCL"),
        ("500696", "Hindustan Lever"),
    ]
    now = datetime.now().isoformat()
    rows = [(code, name, "Active", "A", None, None, None, None, f"{code}.BO", now)
            for code, name in bse_major]
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM bse_stocks")
    conn.executemany("""
        INSERT OR REPLACE INTO bse_stocks
          (bse_code, company_name, status, group_name, face_value,
           isin, industry, sector, yf_ticker, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    conn.close()
    return {"status": "fallback", "count": len(rows), "exchange": "BSE"}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_stocks(query: str, exchange: str = "NSE", limit: int = 30) -> list:
    """
    Search for stocks by company name or symbol.

    query    — partial name or symbol e.g. "reliance", "tcs", "hdfc"
    exchange — "NSE", "BSE", or "ALL"
    limit    — max results to return (default 30)

    Returns list of dicts with symbol, company_name, yf_ticker, exchange.
    """
    _init_db()
    query = query.strip()
    q_upper = query.upper()
    results = []

    def _search_nse():
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT symbol, company_name, series, isin, yf_ticker
            FROM nse_stocks
            WHERE UPPER(symbol) LIKE ?
               OR UPPER(company_name) LIKE ?
            ORDER BY
              CASE WHEN UPPER(symbol) = ? THEN 0
                   WHEN UPPER(symbol) LIKE ? THEN 1
                   ELSE 2 END,
              company_name
            LIMIT ?
        """, (f"%{q_upper}%", f"%{q_upper}%", q_upper, f"{q_upper}%", limit)).fetchall()
        conn.close()
        return [
            {
                "symbol":       r[0],
                "company_name": r[1],
                "series":       r[2],
                "isin":         r[3],
                "yf_ticker":    r[4],
                "exchange":     "NSE",
            }
            for r in rows
        ]

    def _search_bse():
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT bse_code, company_name, group_name, isin, yf_ticker
            FROM bse_stocks
            WHERE UPPER(bse_code) LIKE ?
               OR UPPER(company_name) LIKE ?
            ORDER BY
              CASE WHEN UPPER(bse_code) = ? THEN 0
                   WHEN UPPER(company_name) LIKE ? THEN 1
                   ELSE 2 END,
              company_name
            LIMIT ?
        """, (f"%{q_upper}%", f"%{q_upper}%", q_upper, f"{q_upper}%", limit)).fetchall()
        conn.close()
        return [
            {
                "symbol":       r[0],
                "company_name": r[1],
                "group":        r[2],
                "isin":         r[3],
                "yf_ticker":    r[4],
                "exchange":     "BSE",
            }
            for r in rows
        ]

    if exchange.upper() in ("NSE", "ALL"):
        results.extend(_search_nse())
    if exchange.upper() in ("BSE", "ALL"):
        results.extend(_search_bse())

    return results[:limit]


def get_stock_by_symbol(symbol: str, exchange: str = "NSE") -> dict | None:
    """Exact symbol lookup. Returns None if not found."""
    _init_db()
    symbol = symbol.upper().replace(".NS", "").replace(".BO", "")
    conn = sqlite3.connect(DB_PATH)
    if exchange.upper() == "NSE":
        row = conn.execute(
            "SELECT symbol, company_name, series, isin, yf_ticker FROM nse_stocks WHERE symbol = ?",
            (symbol,)
        ).fetchone()
        conn.close()
        if row:
            return {"symbol": row[0], "company_name": row[1], "series": row[2],
                    "isin": row[3], "yf_ticker": row[4], "exchange": "NSE"}
    else:
        row = conn.execute(
            "SELECT bse_code, company_name, group_name, isin, yf_ticker FROM bse_stocks WHERE bse_code = ?",
            (symbol,)
        ).fetchone()
        conn.close()
        if row:
            return {"symbol": row[0], "company_name": row[1], "group": row[2],
                    "isin": row[3], "yf_ticker": row[4], "exchange": "BSE"}
    return None


def get_all_symbols(exchange: str = "NSE") -> list:
    """Return all cached symbols for an exchange as a flat list."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    if exchange.upper() == "NSE":
        rows = conn.execute(
            "SELECT symbol, company_name, yf_ticker FROM nse_stocks ORDER BY symbol"
        ).fetchall()
        conn.close()
        return [{"symbol": r[0], "company_name": r[1], "yf_ticker": r[2]} for r in rows]
    else:
        rows = conn.execute(
            "SELECT bse_code, company_name, yf_ticker FROM bse_stocks ORDER BY bse_code"
        ).fetchall()
        conn.close()
        return [{"symbol": r[0], "company_name": r[1], "yf_ticker": r[2]} for r in rows]


def get_universe_stats() -> dict:
    """Return count of cached stocks per exchange and when they were last refreshed."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    nse_count    = conn.execute("SELECT COUNT(*) FROM nse_stocks").fetchone()[0]
    bse_count    = conn.execute("SELECT COUNT(*) FROM bse_stocks").fetchone()[0]
    nse_updated  = conn.execute("SELECT MAX(last_updated) FROM nse_stocks").fetchone()[0]
    bse_updated  = conn.execute("SELECT MAX(last_updated) FROM bse_stocks").fetchone()[0]
    conn.close()
    return {
        "nse": {"count": nse_count, "last_updated": nse_updated},
        "bse": {"count": bse_count, "last_updated": bse_updated},
        "total": nse_count + bse_count,
    }


def ensure_universe_loaded():
    """
    Called on app startup — loads both NSE and BSE lists if not already cached.
    Runs once on first startup, then refreshes daily in the background.
    """
    _init_db()
    print("Checking stock universe cache...")
    nse_result = refresh_nse_stocks()
    bse_result = refresh_bse_stocks()
    print(f"  NSE: {nse_result}")
    print(f"  BSE: {bse_result}")


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Testing stock_universe.py")
    print("=" * 60)

    print("\n1. Refreshing NSE stock list (downloading from NSE archives)...")
    result = refresh_nse_stocks(force=True)
    print(f"   {result}")

    print("\n2. Universe stats:")
    stats = get_universe_stats()
    print(f"   NSE  : {stats['nse']['count']} stocks  (updated: {stats['nse']['last_updated']})")
    print(f"   BSE  : {stats['bse']['count']} stocks  (updated: {stats['bse']['last_updated']})")
    print(f"   Total: {stats['total']}")

    print("\n3. Search 'reliance':")
    results = search_stocks("reliance", exchange="NSE")
    for r in results[:5]:
        print(f"   {r['symbol']:15s}  {r['company_name']}")

    print("\n4. Search 'hdfc' across all exchanges:")
    results = search_stocks("hdfc", exchange="ALL", limit=10)
    for r in results:
        print(f"   [{r['exchange']}] {r['symbol']:10s}  {r['company_name']}")

    print("\n5. Exact lookup 'TCS':")
    stock = get_stock_by_symbol("TCS", exchange="NSE")
    print(f"   {stock}")

    print("\n6. First 10 NSE symbols:")
    all_syms = get_all_symbols("NSE")
    for s in all_syms[:10]:
        print(f"   {s['symbol']:15s}  {s['company_name']}")

    print("\n" + "=" * 60)
    print("stock_universe.py test complete")
    print("=" * 60)
