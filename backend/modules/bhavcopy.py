"""
bhavcopy.py — NSE's own daily price file, as a real second data source.

Everything else in this app comes from Yahoo. Bhavcopy is published by the
exchange itself, so it is genuinely independent: when Yahoo throttles, is wrong,
or disappears, this still answers. That is the difference between redundancy and
decoration — a fallback reading the same upstream would be neither.

What it gives: official end-of-day open/high/low/close/volume for every listed
NSE equity, one file per trading day, free and without an API key.

What it does not give: intraday or live quotes. Bhavcopy is published after the
close, so it backs history, the universe scan and backtests — not the ticking
price on a stock page. Claiming otherwise would be the same overreach as the
stooq idea, which turned out to serve a bot challenge rather than data.
"""

import io
import zipfile
from datetime import datetime, timedelta

import pandas as pd
import requests

from db import get_conn, IS_POSTGRES

# NSE serves these to browsers, not to bare clients — without a UA and Referer
# the archive returns 403.
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}

_URLS = [
    "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d}_F_0000.csv.zip",
    "https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d}_F_0000.csv.zip",
]


def _init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bhavcopy_eod (
            symbol TEXT NOT NULL,
            day    TEXT NOT NULL,
            open   REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (symbol, day)
        )
    """)
    conn.commit()
    conn.close()


def fetch_day(day: datetime = None) -> dict:
    """
    Download and store one trading day. Weekends and holidays simply have no
    file, which is a 404 rather than an error worth alarming about.
    """
    _init_db()
    day = day or (datetime.now() - timedelta(days=1))
    d = day.strftime("%Y%m%d")

    raw = None
    for url in _URLS:
        try:
            r = requests.get(url.format(d=d), headers=_HEADERS, timeout=45)
            if r.status_code == 200 and r.content[:2] == b"PK":
                raw = r.content
                break
        except Exception:
            continue
    if not raw:
        return {"day": d, "stored": 0, "note": "no file — weekend, holiday, or not published yet"}

    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        df = pd.read_csv(z.open(z.namelist()[0]))
    except Exception as e:
        return {"day": d, "stored": 0, "error": f"unreadable: {type(e).__name__}"}

    cols = {c.strip().upper(): c for c in df.columns}
    def col(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    c_sym = col("TCKRSYMB", "SYMBOL")
    c_close = col("CLSPRIC", "CLOSE_PRICE", "CLOSE")
    if not c_sym or not c_close:
        return {"day": d, "stored": 0, "error": f"unexpected columns: {list(df.columns)[:8]}"}

    c_series = col("SCTYSRS", "SERIES")
    if c_series is not None:
        df = df[df[c_series].astype(str).str.strip().isin(["EQ", "BE"])]

    c_o, c_h, c_l = col("OPNPRIC", "OPEN_PRICE"), col("HGHPRIC", "HIGH_PRICE"), col("LWPRIC", "LOW_PRICE")
    c_v = col("TTLTRADGVOL", "TTL_TRD_QNTY", "VOLUME")

    rows = []
    iso = day.strftime("%Y-%m-%d")
    for _, r in df.iterrows():
        try:
            sym = str(r[c_sym]).strip().upper()
            if not sym:
                continue
            rows.append((f"{sym}.NS", iso,
                         float(r[c_o]) if c_o else None,
                         float(r[c_h]) if c_h else None,
                         float(r[c_l]) if c_l else None,
                         float(r[c_close]),
                         float(r[c_v]) if c_v else None))
        except Exception:
            continue

    conn = get_conn()
    stmt = ("INSERT INTO bhavcopy_eod (symbol, day, open, high, low, close, volume) "
            "VALUES (?,?,?,?,?,?,?)")
    stmt += (" ON CONFLICT (symbol, day) DO UPDATE SET close = EXCLUDED.close"
             if IS_POSTGRES else "")
    if not IS_POSTGRES:
        stmt = stmt.replace("INSERT INTO", "INSERT OR REPLACE INTO")
    for row in rows:
        try:
            conn.execute(stmt, row)
        except Exception:
            pass
    conn.commit()
    conn.close()
    return {"day": iso, "stored": len(rows), "source": "NSE bhavcopy"}


# NSE's archive at these URLs starts in early 2024 — measured, not assumed:
# 2024-02-21 returns a file, 2023-11-15 does not, and neither is a holiday.
# Asking for dates before this only produces 404s, so the depth of any
# point-in-time universe built from this source is bounded here.
ARCHIVE_STARTS = "2024-01-01"


def _already_stored() -> set:
    """Days already in the table, so a resumed backfill does not refetch them."""
    try:
        _init_db()
        from db import get_conn
        conn = get_conn()
        try:
            rows = conn.execute("SELECT DISTINCT day FROM bhavcopy_eod").fetchall()
        finally:
            conn.close()
        return {str(r[0])[:8].replace("-", "") for r in rows} | {str(r[0]) for r in rows}
    except Exception:
        return set()


def backfill(days: int = 10, workers: int = 4, skip_existing: bool = True) -> dict:
    """
    Pull the last N calendar days. Missing days are skipped, not retried.

    Downloads run in parallel because thirty sequential fetches take longer than
    any sensible request timeout — that is what made the first 7-day attempt die
    at 280 seconds. Concurrency is deliberately modest: NSE is a public archive
    being used politely, and hammering it to save a minute would be a good way
    to lose the source entirely.

    skip_existing matters once this is used to build real depth. A 900-day pull
    that refetches everything it already has on each restart never finishes, and
    it puts nine hundred pointless requests through a public archive to learn
    what one query of its own table would have said.
    """
    from concurrent.futures import ThreadPoolExecutor

    have = _already_stored() if skip_existing else set()
    floor = datetime.strptime(ARCHIVE_STARTS, "%Y-%m-%d")

    targets = []
    for i in range(1, days + 1):
        d = datetime.now() - timedelta(days=i)
        if d < floor:
            continue                      # nothing published before the archive starts
        if d.weekday() >= 5:
            continue                      # no file on a weekend; do not ask for one
        if d.strftime("%Y%m%d") in have or d.strftime("%Y-%m-%d") in have:
            continue
        targets.append(d)

    out = []
    if targets:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as ex:
            for r in ex.map(fetch_day, targets):
                out.append(r)
    return {"days_requested": days,
            "days_attempted": len(targets),
            "days_skipped_already_had": max(0, days - len(targets)),
            "days_stored": len([o for o in out if o.get("stored")]),
            "rows": sum(o.get("stored", 0) for o in out),
            "archive_starts": ARCHIVE_STARTS,
            "note": (f"Weekends and days already stored are not requested. "
                     f"Nothing before {ARCHIVE_STARTS} is requested either: the "
                     f"archive does not serve it.")}


_BACKFILL_STATE = {"running": False, "started": None, "result": None}


def backfill_async(days: int = 30) -> dict:
    """
    Kick off a backfill in the background and return immediately.

    A 30-day pull outlives any HTTP request, so the request starts the work and
    /bhavcopy/coverage reports progress — the same pattern the universe scan
    uses. Guards against a second run stacking on top of a first.
    """
    import threading
    if _BACKFILL_STATE["running"]:
        return {"started": False, "note": "A backfill is already running.",
                "since": _BACKFILL_STATE["started"]}

    def _run():
        _BACKFILL_STATE.update(running=True, started=datetime.now().isoformat(),
                               result=None)
        try:
            _BACKFILL_STATE["result"] = backfill(days)
        except Exception as e:
            _BACKFILL_STATE["result"] = {"error": f"{type(e).__name__}: {e}"}
        finally:
            _BACKFILL_STATE["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "days": days,
            "note": "Running in the background. Poll /bhavcopy/coverage for progress."}


def backfill_status() -> dict:
    return dict(_BACKFILL_STATE)


def close_from_bhavcopy(ticker: str, max_age_days: int = 7):
    """
    Latest official close for a ticker, or None. This is the actual fallback:
    when Yahoo fails, the price served comes from the exchange rather than from
    a stale copy of Yahoo.
    """
    try:
        _init_db()
        conn = get_conn()
        row = conn.execute(
            "SELECT close, day FROM bhavcopy_eod WHERE symbol = ? "
            "ORDER BY day DESC", (ticker.upper(),)).fetchone()
        conn.close()
        if not row:
            return None
        age = (datetime.now() - datetime.fromisoformat(row[1])).days
        if age > max_age_days:
            return None
        return {"price": row[0], "as_of": row[1], "age_days": age,
                "source": "NSE bhavcopy (official end-of-day)"}
    except Exception:
        return None


def coverage() -> dict:
    _init_db()
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM bhavcopy_eod").fetchone()[0]
    d = conn.execute("SELECT COUNT(DISTINCT day) FROM bhavcopy_eod").fetchone()[0]
    s = conn.execute("SELECT COUNT(DISTINCT symbol) FROM bhavcopy_eod").fetchone()[0]
    last = conn.execute("SELECT MAX(day) FROM bhavcopy_eod").fetchone()[0]
    conn.close()
    return {"rows": n, "days": d, "symbols": s, "latest_day": last,
            "note": "Official NSE end-of-day. Independent of Yahoo — this is the "
                    "fallback that still answers when Yahoo does not."}


def closes_for_latest_day() -> dict:
    """
    {symbol: close} for the most recent stored trading day.

    One query for the whole exchange. The prediction snapshot used to fetch a
    price per ticker from Yahoo, which is fine for thirty stocks and impossible
    for two thousand four hundred.
    """
    try:
        _init_db()
        conn = get_conn()
        rows = conn.execute(
            "SELECT symbol, close FROM bhavcopy_eod "
            "WHERE day = (SELECT MAX(day) FROM bhavcopy_eod) AND close IS NOT NULL"
        ).fetchall()
        conn.close()
        return {r[0]: float(r[1]) for r in rows if r and r[1]}
    except Exception:
        return {}


def closes_history(symbols=None) -> dict:
    """
    {symbol: {day: close}} across every stored day — the local substitute for
    per-ticker price downloads when grading a large record.
    """
    try:
        _init_db()
        conn = get_conn()
        rows = conn.execute(
            "SELECT symbol, day, close FROM bhavcopy_eod WHERE close IS NOT NULL"
        ).fetchall()
        conn.close()
    except Exception:
        return {}
    want = set(symbols) if symbols else None
    out: dict = {}
    for sym, day, close in rows:
        if want and sym not in want:
            continue
        out.setdefault(sym, {})[day] = float(close)
    return out
