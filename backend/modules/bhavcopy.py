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

# Before 2024 the exchange published a different filename, a different layout
# and a different directory tree. Both were probed against the live archive
# rather than assumed: the old pattern serves 2011-07-04 through at least
# 2023-06, the new one from 2024-01-02, and every file in both eras carries a
# fully populated ISIN column -- which is the only reason this backfill is worth
# running, since identity is what the corporate-action join is keyed on.
_OLD_URLS = [
    "https://nsearchives.nseindia.com/content/historical/EQUITIES/{Y}/{MON}/cm{D}{MON}{Y}bhav.csv.zip",
    "https://archives.nseindia.com/content/historical/EQUITIES/{Y}/{MON}/cm{D}{MON}{Y}bhav.csv.zip",
]
_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
# Where the exchange changed format. Not a cliff worth trusting -- both eras are
# always attempted -- but trying the likely one first halves the requests.
_FORMAT_SWITCH = "2024-01-01"


def _urls_for(day: datetime) -> list:
    """Every URL that might serve this date, likeliest first.

    Both eras are always tried. The switch date orders the attempts rather than
    gating them, so a file sitting on the other side of it is still found
    instead of being reported as a holiday.
    """
    d = day.strftime("%Y%m%d")
    new = [u.format(d=d) for u in _URLS]
    old = [u.format(Y=day.strftime("%Y"), MON=_MONTHS[day.month - 1],
                    D=day.strftime("%d")) for u in _OLD_URLS]
    return (new + old) if day.strftime("%Y-%m-%d") >= _FORMAT_SWITCH else (old + new)


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
    _add_isin_column()
    _add_day_index()


def _add_day_index():
    """
    An index on `day` alone.

    The primary key is (symbol, day), which cannot serve `WHERE day >= ?` --
    every gap scan and every MIN/MAX over the column was a full table scan.
    That cost nothing at 1.5 million rows and made /bhavcopy/coverage take 38
    seconds at 7.6 million, on an endpoint the stocks page calls.

    On its own connection: a failed statement poisons the whole transaction on
    Postgres, and an index that already exists must not take the caller's work
    down with it.
    """
    try:
        conn = get_conn()
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bhavcopy_day "
                         "ON bhavcopy_eod (day)")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _add_isin_column():
    """
    ISIN is the security's permanent identity; the ticker is only its current
    label. Without it a rename is indistinguishable from a delisting — the
    symbol simply stops appearing — and the point-in-time backtest booked
    ZOMATO as a -100% loss when it had merely become ETERNAL.

    The raw NSE file has carried this column all along and the parser discarded
    it.
    """
    conn = get_conn()
    try:
        conn.execute("ALTER TABLE bhavcopy_eod ADD COLUMN isin TEXT")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
    conn = get_conn()
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bhav_isin "
                     "ON bhavcopy_eod (isin, day)")
        conn.commit()
    except Exception:
        pass
    finally:
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
    for url in _urls_for(day):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=45)
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

    # The pre-2024 file names these OPEN/HIGH/LOW/TOTTRDQTY. Without the older
    # spellings every historical day would parse, store, and silently carry a
    # null OHLC -- a day present in the table and useless to anything reading it.
    c_o = col("OPNPRIC", "OPEN_PRICE", "OPEN")
    c_h = col("HGHPRIC", "HIGH_PRICE", "HIGH")
    c_l = col("LWPRIC", "LOW_PRICE", "LOW")
    c_v = col("TTLTRADGVOL", "TTL_TRD_QNTY", "VOLUME", "TOTTRDQTY")
    # The permanent identity. Present in the file since the start and discarded
    # until a backtest booked a ticker rename as a total loss.
    c_isin = col("ISIN")

    rows = []
    iso = day.strftime("%Y-%m-%d")
    for _, r in df.iterrows():
        try:
            sym = str(r[c_sym]).strip().upper()
            if not sym:
                continue
            isin = None
            if c_isin is not None:
                iv = str(r[c_isin]).strip().upper()
                # A blank or literal 'NAN' is absent, not an identifier.
                if iv and iv not in ("NAN", "NONE", "-"):
                    isin = iv
            rows.append((f"{sym}.NS", iso,
                         float(r[c_o]) if c_o else None,
                         float(r[c_h]) if c_h else None,
                         float(r[c_l]) if c_l else None,
                         float(r[c_close]),
                         float(r[c_v]) if c_v else None,
                         isin))
        except Exception:
            continue

    conn = get_conn()
    stmt = ("INSERT INTO bhavcopy_eod (symbol, day, open, high, low, close, "
            "volume, isin) VALUES (?,?,?,?,?,?,?,?)")
    # A re-fetch of a day already stored exists to fill in the ISIN, so the
    # conflict path has to actually write it.
    stmt += (" ON CONFLICT (symbol, day) DO UPDATE SET close = EXCLUDED.close, "
             "isin = COALESCE(EXCLUDED.isin, bhavcopy_eod.isin)"
             if IS_POSTGRES else "")
    if not IS_POSTGRES:
        stmt = stmt.replace("INSERT INTO", "INSERT OR REPLACE INTO")
    # One statement per row meant ~2,400 round-trips per day and 1.5 million
    # across the archive, which turned the ISIN re-fetch into a 16-to-40 hour
    # job. The data and the conflict rules are identical; only the number of
    # round-trips changes.
    #
    # The per-row loop survives as a fallback because executemany is
    # all-or-nothing: one malformed row would lose the whole day, and losing a
    # day silently is exactly the failure this project keeps finding. On
    # Postgres a failed statement poisons the transaction, so the rollback
    # before retrying is required rather than tidy.
    stored = len(rows)
    try:
        conn.executemany(stmt, rows)
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        stored = 0
        for row in rows:
            try:
                conn.execute(stmt, row)
                stored += 1
            except Exception:
                pass
        conn.commit()
    conn.close()
    # Report what was actually written, not what was parsed. If the batch fell
    # back and some rows failed, a caller counting len(rows) would be told the
    # day is complete when it is not.
    return {"day": iso, "stored": stored, "parsed": len(rows),
            "source": "NSE bhavcopy"}


# The floor was 2024-01-01 because that is where the MODERN filename starts —
# 2024-02-21 returns a file and 2023-11-15 does not. That was a fact about one
# URL pattern, not about the archive. The pre-2024 pattern serves 2011-07-04
# onward, with a fully populated ISIN column in every file, both verified
# against the live archive.
#
# 2011-07 rather than deeper: it is where the corporate-action archive begins,
# and a price with no actions to adjust it by is a price this app cannot use
# honestly. Extending one without the other would buy history that the
# adjustment layer has to refuse.
ARCHIVE_STARTS = "2011-07-04"


def _already_stored() -> set:
    """Days already in the table, so a resumed backfill does not refetch them."""
    try:
        _init_db()
        from db import get_conn
        conn = get_conn()
        try:
            # Only days whose rows carry an ISIN count as done. Otherwise the
            # resume guard would see 652 stored days, conclude there is nothing
            # left, and leave every historical row without the identity the
            # rename fix depends on.
            rows = conn.execute(
                "SELECT day FROM bhavcopy_eod GROUP BY day "
                "HAVING COUNT(isin) > 0").fetchall()
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


def backfill_range(start: str, end: str, workers: int = 4,
                   skip_existing: bool = True) -> dict:
    """
    Fetch every weekday in [start, end] that is not already stored.

    backfill() counts days back from TODAY, which cannot express "the stretch
    before what we already have". Reaching a floor thirteen years deep that way
    means asking for five thousand days back and re-walking the entire archive
    on every pass just to skip it -- and worse, a chunked resume can then never
    get deeper than one chunk, because every chunk starts from today again. A
    range is walked once and moves.

    Weekends are skipped. Holidays are not knowable without an exchange
    calendar, so they are requested, answered with a 404, and counted as days
    with no file rather than as errors.
    """
    from concurrent.futures import ThreadPoolExecutor

    try:
        d0 = datetime.strptime(start[:10], "%Y-%m-%d")
        d1 = datetime.strptime(end[:10], "%Y-%m-%d")
    except Exception as e:
        return {"error": f"bad date range: {type(e).__name__}: {e}"}
    floor = datetime.strptime(ARCHIVE_STARTS, "%Y-%m-%d")
    if d0 < floor:
        d0 = floor
    if d1 < d0:
        return {"days_attempted": 0, "days_stored": 0, "rows": 0,
                "range": [start, end], "note": "empty range"}

    have = _already_stored() if skip_existing else set()
    targets = []
    d = d0
    while d <= d1:
        if d.weekday() < 5 and d.strftime("%Y%m%d") not in have                 and d.strftime("%Y-%m-%d") not in have:
            targets.append(d)
        d += timedelta(days=1)

    out = []
    if targets:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as ex:
            for r in ex.map(fetch_day, targets):
                out.append(r)
    stored = [o for o in out if o.get("stored")]
    return {"range": [d0.strftime("%Y-%m-%d"), d1.strftime("%Y-%m-%d")],
            "days_attempted": len(targets),
            "days_stored": len(stored),
            "days_with_no_file": len(targets) - len(stored),
            "rows": sum(o.get("stored", 0) for o in out)}


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


def backfill_range_async(start: str, end: str) -> dict:
    """backfill_range in the background, sharing the same running-guard."""
    import threading
    if _BACKFILL_STATE["running"]:
        return {"started": False, "note": "A backfill is already running.",
                "since": _BACKFILL_STATE["started"]}

    def _run():
        _BACKFILL_STATE.update(running=True, started=datetime.now().isoformat(),
                               result=None)
        try:
            _BACKFILL_STATE["result"] = backfill_range(start, end)
        except Exception as e:
            _BACKFILL_STATE["result"] = {"error": f"{type(e).__name__}: {e}"}
        finally:
            _BACKFILL_STATE["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "range": [start, end],
            "note": "Running in the background. Poll /bhavcopy/coverage for progress."}


def resume_if_incomplete(chunk_days: int = 1200) -> dict:
    """
    Keep filling the archive until nothing is missing, across any restarts.

    A deep backfill takes hours and a deploy takes seconds. Every push kills the
    daemon thread and loses the job -- the days already written survive, but
    nothing resumes them, so the build stalls wherever it happened to be and
    only a human noticing restarts it. That is how a 640-day target quietly
    stopped at 69. So this polls rather than running once at startup.

    It asks what is MISSING rather than where the archive begins. Two earlier
    versions of that question were both wrong:

      backfill(chunk_days) counted days back from TODAY. At a 2024 floor one
      chunk covered the whole gap, so it worked by accident; at a 2011 floor
      every pass re-walks the same window from today, stores nothing new, and
      fires again in fifteen minutes, for ever.

      Anchoring on MIN(day) fixed that and introduced a quieter failure: it is
      only correct if the stored days are contiguous. Fetch one day from 2011 by
      hand and MIN(day) sits on the floor, so the walk declares itself complete
      while three thousand days are absent from the middle. That is exactly what
      a single-day probe did to this archive.

    Missing days are filled newest-first, because recent history is what the
    backtests reach for soonest.
    """
    if _BACKFILL_STATE.get("running"):
        return {"resumed": False, "note": "A backfill is already running."}

    today = datetime.now().strftime("%Y-%m-%d")
    # respect_first_stored=False on purpose: here a date before the oldest row
    # IS work to do, which is the whole point of a backwards walk.
    miss = missing_days(ARCHIVE_STARTS, today, respect_first_stored=False)
    if not miss.get("available"):
        return {"resumed": False, "reason": miss.get("reason")}

    gaps = miss["missing"]
    if not gaps:
        return {"resumed": False, "complete": True,
                "oldest_stored": miss.get("oldest_stored"),
                "latest_stored": miss.get("latest_stored"),
                "note": "Every trading day between the floor and today is stored."}

    newest_missing = gaps[-1]
    chunk_end = datetime.strptime(newest_missing, "%Y-%m-%d")
    chunk_start = max(datetime.strptime(ARCHIVE_STARTS, "%Y-%m-%d"),
                      chunk_end - timedelta(days=chunk_days))

    started = backfill_range_async(chunk_start.strftime("%Y-%m-%d"),
                                   chunk_end.strftime("%Y-%m-%d"))
    return {**started, "resumed": True,
            "missing_before": len(gaps),
            "oldest_missing": gaps[0], "newest_missing": newest_missing,
            "filling": [chunk_start.strftime("%Y-%m-%d"), newest_missing],
            "floor": ARCHIVE_STARTS}


def backfill_recent(days: int = 10) -> dict:
    """
    Repair holes at the RECENT end of the archive.

    Nothing else did this. `fetch_day` runs once a night on a cron and does not
    retry, so a single attempt that loses a race with a restart, a network blip
    or a slow publish loses that day for good. `resume_if_incomplete` does not
    cover it either: it compares MIN(day) against the archive floor and extends
    BACKWARDS, so once history reaches ARCHIVE_STARTS it reports "complete" and
    stops looking — however many gaps sit behind the latest date. Coverage still
    reads healthy because it counts days present, not days expected.

    That combination is how Monday 2026-09-07 went missing between a stored
    Friday and a stored Tuesday with nothing reporting a problem.

    Holidays cost one 404 per pass. Without an exchange calendar a day with no
    file is indistinguishable from a day whose fetch failed, and that is the
    deliberate trade: a handful of wasted polite requests against silently
    dropping real trading days. The window is short, so a holiday stops being
    retried once it falls out of it.

    Cheap when there is nothing to do — `backfill` skips weekends, days already
    stored and anything before the floor, so a clean archive costs one query.
    """
    if _BACKFILL_STATE.get("running"):
        return {"filled": False, "note": "A deep backfill is running; leaving "
                                         "the archive to it."}
    try:
        before = coverage().get("days", 0)
        res = backfill(days=days, skip_existing=True)
        after = coverage().get("days", 0)
    except Exception as e:
        return {"filled": False, "error": f"{type(e).__name__}: {e}"}
    gained = max(0, after - before)
    if gained:
        print(f"[bhavcopy] recent-gap repair stored {gained} missing day(s), "
              f"{res.get('rows', 0)} rows")
    return {"filled": bool(gained), "days_recovered": gained,
            "days_attempted": res.get("days_attempted", 0),
            "rows": res.get("rows", 0), "window_days": days,
            "coverage_days": after}


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


def missing_days(start: str, end: str,
                 respect_first_stored: bool = True) -> dict:
    """
    Weekdays in [start, end] with no rows. The general form of a gap.

    Everything that asks "what is missing" asks it of a range: the recent
    window for the repair pass, the whole archive for the resume walk. Both used
    to answer it their own way, and the resume's way -- compare MIN(day) to the
    floor -- is only correct if the stored days are contiguous. They are not.
    One old day fetched by hand puts MIN(day) at the floor and the walk reports
    itself complete with three thousand days absent from the middle. That is not
    hypothetical; it is what a single-day probe did to this archive.

    Scoped to the range and served by idx_bhavcopy_day, so asking is cheap.

    respect_first_stored keeps dates before the first day ever stored out of the
    answer: those were never claimed, and counting them would make an archive
    that has just started look catastrophically broken.
    """
    try:
        d0 = datetime.strptime(start[:10], "%Y-%m-%d")
        d1 = datetime.strptime(end[:10], "%Y-%m-%d")
    except Exception as e:
        return {"available": False, "reason": f"bad range: {type(e).__name__}"}

    try:
        _init_db()
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT DISTINCT day FROM bhavcopy_eod "
                "WHERE day >= ? AND day <= ?",
                (d0.strftime("%Y-%m-%d"), d1.strftime("%Y-%m-%d"))).fetchall()
            edge = conn.execute(
                "SELECT MIN(day), MAX(day) FROM bhavcopy_eod").fetchone()
        finally:
            conn.close()
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}"}

    have = {str(r[0])[:10] for r in rows if r and r[0]}
    oldest = str(edge[0])[:10] if edge and edge[0] else None
    newest = str(edge[1])[:10] if edge and edge[1] else None
    if not oldest:
        return {"available": False, "reason": "no bhavcopy rows stored"}

    floor = datetime.strptime(ARCHIVE_STARTS, "%Y-%m-%d")
    lower = max(d0, floor)
    if respect_first_stored:
        lower = max(lower, datetime.strptime(oldest, "%Y-%m-%d"))
    # Today is never a gap: NSE publishes after the close.
    upper = min(d1, datetime.now() - timedelta(days=1))

    missing, d = [], lower
    while d <= upper:
        if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in have:
            missing.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return {"available": True, "missing": missing, "n": len(missing),
            "range": [lower.strftime("%Y-%m-%d"), upper.strftime("%Y-%m-%d")],
            "oldest_stored": oldest, "latest_stored": newest}


def recent_gaps(days: int = 30) -> dict:
    """
    Which weekdays in the recent window have no rows?

    Coverage counted days PRESENT, never days EXPECTED, so an archive missing a
    Monday between a stored Friday and a stored Tuesday still reported a healthy
    row count and a fresh latest_day. Nothing in the response could have told
    anyone a day was gone. This is the number that would have said so.

    Holidays land in this list too — without an exchange calendar a closed
    market and a failed fetch look identical from the table. So these are
    CANDIDATE gaps: the repair pass asks NSE for each one, and a 404 is the
    answer that it was a holiday. Persisting across many passes is the signal
    worth reading, not a single appearance here.
    """
    since = (datetime.now() - timedelta(days=days + 1)).strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    miss = missing_days(since, yesterday, respect_first_stored=True)
    if not miss.get("available"):
        return miss
    return {"available": True, "window_days": days,
            "candidate_gaps": miss["missing"], "n": len(miss["missing"]),
            "latest_stored": miss.get("latest_stored"),
            "note": ("Weekdays in the window with no rows. Holidays appear here "
                     "too and cannot be told apart without an exchange calendar; "
                     "a gap that survives several repair passes is a real loss.")}


def coverage() -> dict:
    _init_db()
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM bhavcopy_eod").fetchone()[0]
    d = conn.execute("SELECT COUNT(DISTINCT day) FROM bhavcopy_eod").fetchone()[0]
    s = conn.execute("SELECT COUNT(DISTINCT symbol) FROM bhavcopy_eod").fetchone()[0]
    last = conn.execute("SELECT MAX(day) FROM bhavcopy_eod").fetchone()[0]
    conn.close()
    try:
        gaps = recent_gaps(30)
    except Exception:
        gaps = {"available": False, "reason": "gap scan failed"}
    return {"rows": n, "days": d, "symbols": s, "latest_day": last,
            "recent_gaps": gaps.get("candidate_gaps") if gaps.get("available") else None,
            "recent_gap_count": gaps.get("n") if gaps.get("available") else None,
            "note": "Official NSE end-of-day. Independent of Yahoo — this is the "
                    "fallback that still answers when Yahoo does not.",
            "gap_note": gaps.get("note")}


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
