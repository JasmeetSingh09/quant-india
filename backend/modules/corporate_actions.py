"""
corporate_actions.py — NSE splits, bonuses and dividends, and the price
adjustment factors they imply.

Why this exists
---------------
bhavcopy stores exchange closes UNADJUSTED. Nothing in the pipeline adjusts
them. Measured against split- and dividend-adjusted closes over long windows,
15 of 20 twelve-month returns were distorted by more than 10% and ITC's
2018-2026 return flipped sign: +36.6% adjusted against -1.4% raw. Momentum
computed on the raw series is therefore measuring corporate actions as much as
performance, and the distortion compounds the further back the window reaches —
so a deeper archive makes it worse, not better.

The other half of the problem is that the backtest reads bhavcopy while the
live momentum factor reads yfinance with auto_adjust=True. They are not the
same series, so the existing validation has never tested what production runs.

Design
------
Actions are stored as fetched and prices are NEVER rewritten. Adjustment is
applied at read time, so the archive stays a record of what the exchange
actually printed and any error in this module is a bug to fix rather than
damage already written into 9 million rows.

Everything is keyed on ISIN. Of 591 securities present in 2015 and gone today,
293 match the action feed by ticker and 372 by ISIN — tickers get renamed and
reassigned, ISINs do not. Keying on ticker would quietly drop the delisted
names the point-in-time archive exists to preserve.

Parsing policy
--------------
The feed carries free text: "Face Value Split (Sub-Division) - From Rs 10/- Per
Share To Rs 2/- Per Share", "Bonus 6:11", "Annual General Meeting/ Dividend -
Re 0.80/- Per Share". A subject that cannot be parsed with confidence is stored
with parsed=0 and contributes NO adjustment. It is not guessed at. An invented
ratio would silently corrupt every price before that date for that security,
which is worse than a known gap — the same rule the rest of this codebase
already applies to missing factor inputs.
"""

import hashlib
import re
import time
from datetime import datetime

try:
    from db import get_conn, IS_POSTGRES
except Exception:                                   # pragma: no cover
    from .db import get_conn, IS_POSTGRES

_READY = False

# Actions that move the price. Everything else (AGMs, e-voting, board meetings)
# is recorded for completeness and adjusts nothing.
SPLIT, BONUS, DIVIDEND, OTHER = "split", "bonus", "dividend", "other"

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-actions",
}
_API = ("https://www.nseindia.com/api/corporates-corporateActions?index=equities"
        "&from_date={frm}&to_date={to}")

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# "From Rs 10/- Per Share To Re 1/- Per Share" | "From Rs 10 To Rs 1"
_SPLIT_RE = re.compile(
    r"from\s+r[se]\.?\s*([0-9]+(?:\.[0-9]+)?)\s*/?-?\s*(?:per\s+share)?\s*"
    r"to\s+r[se]\.?\s*([0-9]+(?:\.[0-9]+)?)", re.I)
# "Bonus 1:1", "Bonus 6:11", "Bonus 1 : 1250"
_BONUS_RE = re.compile(r"bonus\s*(?:issue)?\s*([0-9]+)\s*:\s*([0-9]+)", re.I)
# "Dividend - Rs 16.25/- Per Share", "Dividend Re 0.20/- Per Share"
_DIV_RE = re.compile(
    r"dividend[^0-9r]*?r[se]\.?\s*([0-9]+(?:\.[0-9]+)?)", re.I)


def parse_subject(subject: str) -> list:
    """
    Every price-affecting action in one subject line.

    A line can carry more than one: "Annual General Meeting/ Dividend - Re 1/-
    Per Share/ E-Voting" is an AGM and a dividend. Returns a list of dicts with
    `kind` and the numbers that kind needs. An unrecognised line returns [],
    and the caller stores it with parsed=0 rather than assuming it is inert —
    "we did not understand this" and "this does nothing" are different claims.
    """
    s = (subject or "").strip()
    if not s:
        return []
    out = []

    m = _SPLIT_RE.search(s)
    if m and "split" in s.lower():
        old_fv, new_fv = float(m.group(1)), float(m.group(2))
        if old_fv > 0 and new_fv > 0 and old_fv != new_fv:
            out.append({"kind": SPLIT, "num": old_fv, "den": new_fv})

    m = _BONUS_RE.search(s)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a > 0 and b > 0:
            out.append({"kind": BONUS, "num": a, "den": b})

    # Only read a dividend when the word appears; "Rs" alone is not enough,
    # and a rights issue price must never be mistaken for a cash payout.
    if "dividend" in s.lower() and "rights" not in s.lower():
        m = _DIV_RE.search(s)
        if m:
            amt = float(m.group(1))
            if amt > 0:
                out.append({"kind": DIVIDEND, "amount": amt})
    return out


def price_multiplier(action: dict, prev_close: float = None):
    """
    What historical prices before this ex-date must be multiplied by so the
    series is continuous across it. Returns None when the action cannot be
    applied, which for a dividend means the prior close was unavailable.

      split  face value Rs X -> Rs Y : shares scale X/Y, so price scales Y/X
      bonus  A:B                     : shares scale (A+B)/B, price scales B/(A+B)
      cash dividend D                : price scales (P - D) / P
    """
    k = action.get("kind")
    if k == SPLIT:
        old_fv, new_fv = action.get("num"), action.get("den")
        if old_fv and new_fv and old_fv > 0:
            return float(new_fv) / float(old_fv)
        return None
    if k == BONUS:
        a, b = action.get("num"), action.get("den")
        if a is not None and b:
            return float(b) / (float(a) + float(b))
        return None
    if k == DIVIDEND:
        d = action.get("amount")
        if d is None or not prev_close or prev_close <= 0:
            return None
        if d >= prev_close:            # a payout at or above the price is not
            return None                # a dividend we can model; refuse it
        return (float(prev_close) - float(d)) / float(prev_close)
    return None


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _init():
    global _READY
    if _READY:
        return
    conn = get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS corporate_actions (
                isin      TEXT NOT NULL,
                symbol    TEXT,
                ex_date   TEXT NOT NULL,
                kind      TEXT NOT NULL,
                num       REAL,
                den       REAL,
                amount    REAL,
                subject   TEXT,
                parsed    INTEGER DEFAULT 0,
                sig       TEXT NOT NULL,
                fetched_at TEXT,
                PRIMARY KEY (isin, ex_date, sig)
            )
        """)
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

    # Index on its own connection: a failed statement aborts the whole
    # transaction on Postgres, so batching migrations lets one harmless
    # already-exists error take the rest down with it.
    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_ca_isin_date "
        "ON corporate_actions (isin, ex_date)",
        "CREATE INDEX IF NOT EXISTS idx_ca_month "
        "ON corporate_actions (ex_date)",
    ):
        conn = get_conn()
        try:
            conn.execute(stmt)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            conn.close()
    _READY = True


def _sig(subject: str, kind: str) -> str:
    """Stable id for one action within a security-date, so a refetch updates
    rather than duplicates. Two different actions on the same ex-date (a bonus
    and a dividend, say) keep separate rows."""
    return hashlib.sha1(f"{kind}|{(subject or '')[:180]}".encode()).hexdigest()[:16]


def _iso(ex: str) -> str:
    """NSE writes '07-Sep-2026'. Store ISO so date comparison is string-safe."""
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime((ex or "").strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return ""


def store(rows: list) -> dict:
    """Persist a batch of feed rows. Returns counts, never raises."""
    _init()
    now = datetime.now().isoformat()
    out = {"seen": len(rows), "stored": 0, "priced": 0, "unparsed": 0, "skipped": 0}
    conn = get_conn()
    try:
        for r in rows:
            isin = (r.get("isin") or "").strip()
            ex = _iso(r.get("exDate") or r.get("ExDate") or "")
            if not isin or not ex:
                out["skipped"] += 1
                continue
            subject = (r.get("subject") or r.get("ind") or "").strip()
            sym = (r.get("symbol") or "").strip()
            acts = parse_subject(subject)
            if not acts:
                acts = [{"kind": OTHER}]
                out["unparsed"] += 1
            for a in acts:
                if a["kind"] in (SPLIT, BONUS, DIVIDEND):
                    out["priced"] += 1
                vals = (isin, sym, ex, a["kind"], a.get("num"), a.get("den"),
                        a.get("amount"), subject[:400],
                        1 if a["kind"] != OTHER else 0,
                        _sig(subject, a["kind"]), now)
                try:
                    if IS_POSTGRES:
                        conn.execute(
                            "INSERT INTO corporate_actions (isin, symbol, ex_date,"
                            " kind, num, den, amount, subject, parsed, sig,"
                            " fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                            " ON CONFLICT (isin, ex_date, sig) DO UPDATE SET"
                            " symbol=EXCLUDED.symbol, num=EXCLUDED.num,"
                            " den=EXCLUDED.den, amount=EXCLUDED.amount,"
                            " parsed=EXCLUDED.parsed, fetched_at=EXCLUDED.fetched_at",
                            vals)
                    else:
                        conn.execute(
                            "INSERT OR REPLACE INTO corporate_actions (isin, symbol,"
                            " ex_date, kind, num, den, amount, subject, parsed, sig,"
                            " fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)", vals)
                    out["stored"] += 1
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
        conn.commit()
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        conn.close()
    return out


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_month(year: int, month: int, session=None) -> list:
    """
    One month of actions. The API caps a response regardless of the range
    asked for — a request spanning all of 2015 came back with July only — so
    history is walked a month at a time rather than in one call.
    """
    import requests
    s = session or requests.Session()
    if session is None:
        s.headers.update(_HEADERS)
        try:
            s.get("https://www.nseindia.com/", timeout=20)
        except Exception:
            pass
    last = 28 if month == 2 else (30 if month in (4, 6, 9, 11) else 31)
    url = _API.format(frm=f"01-{month:02d}-{year}", to=f"{last}-{month:02d}-{year}")
    try:
        r = s.get(url, timeout=45)
        j = r.json()
        return j if isinstance(j, list) else (j.get("data") or [])
    except Exception:
        return []


def backfill(start_year: int = 2011, start_month: int = 7,
             end_year: int = None, end_month: int = None,
             pause: float = 1.2, progress=None) -> dict:
    """
    Walk the feed month by month. Resumable: a month already stored is skipped
    unless force is wanted, so an interrupted run continues where it stopped.
    """
    import requests
    _init()
    now = datetime.now()
    end_year = end_year or now.year
    end_month = end_month or now.month
    s = requests.Session()
    s.headers.update(_HEADERS)
    try:
        s.get("https://www.nseindia.com/", timeout=20)
    except Exception:
        pass

    done = _months_present()
    total = {"months": 0, "skipped_months": 0, "rows": 0, "priced": 0,
             "unparsed": 0, "errors": 0}
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        key = f"{y:04d}-{m:02d}"
        if key in done:
            total["skipped_months"] += 1
        else:
            rows = fetch_month(y, m, session=s)
            if rows:
                res = store(rows)
                total["rows"] += res.get("stored", 0)
                total["priced"] += res.get("priced", 0)
                total["unparsed"] += res.get("unparsed", 0)
            else:
                total["errors"] += 1
            total["months"] += 1
            if progress:
                progress(key, len(rows))
            time.sleep(pause)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return total


_BACKFILL_STATE = {"running": False, "started": None, "at": None,
                   "result": None}


def backfill_async(start_year: int = 2011, start_month: int = 7) -> dict:
    """
    Start the walk in the background and return immediately.

    ~180 monthly requests paced at 1.2s outlives any HTTP request, so the call
    starts the work and /actions/coverage reports progress — the same pattern
    the bhavcopy backfill and the universe scan already use. A second start is
    refused rather than stacked, because two walkers would double the request
    rate against NSE for no benefit.
    """
    import threading
    if _BACKFILL_STATE["running"]:
        return {"started": False, "note": "A corporate-action backfill is "
                                          "already running.",
                "since": _BACKFILL_STATE["started"],
                "at": _BACKFILL_STATE["at"]}

    def _run():
        _BACKFILL_STATE.update(running=True, started=datetime.now().isoformat(),
                               at=None, result=None)
        try:
            _BACKFILL_STATE["result"] = backfill(
                start_year, start_month,
                progress=lambda key, n: _BACKFILL_STATE.update(
                    at=f"{key} ({n} rows)"))
        except Exception as e:
            _BACKFILL_STATE["result"] = {"error": f"{type(e).__name__}: {e}"}
        finally:
            _BACKFILL_STATE["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "from": f"{start_year}-{start_month:02d}",
            "note": "Running in the background. Poll /actions/coverage."}


def backfill_status() -> dict:
    return dict(_BACKFILL_STATE)


def _months_present() -> set:
    """Months already stored, so a resumed backfill does not refetch them."""
    try:
        _init()
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT DISTINCT substr(ex_date,1,7) FROM corporate_actions"
            ).fetchall()
            return {r[0] for r in rows if r and r[0]}
        finally:
            conn.close()
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def actions_for(isin: str, start: str = None, end: str = None) -> list:
    """Price-affecting actions for one security, oldest first."""
    _init()
    conn = get_conn()
    try:
        sql = ("SELECT ex_date, kind, num, den, amount, subject, symbol "
               "FROM corporate_actions WHERE isin=? AND parsed=1 "
               "AND kind IN ('split','bonus','dividend')")
        args = [isin]
        if start:
            sql += " AND ex_date >= ?"; args.append(start)
        if end:
            sql += " AND ex_date <= ?"; args.append(end)
        sql += " ORDER BY ex_date"
        rows = conn.execute(sql, tuple(args)).fetchall()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        rows = []
    finally:
        conn.close()
    return [{"ex_date": r[0], "kind": r[1], "num": r[2], "den": r[3],
             "amount": r[4], "subject": r[5], "symbol": r[6]} for r in rows]


def coverage() -> dict:
    """What the action archive holds. Read-only."""
    _init()
    conn = get_conn()
    out = {}
    try:
        for key, sql in (
            ("rows", "SELECT COUNT(*) FROM corporate_actions"),
            ("securities", "SELECT COUNT(DISTINCT isin) FROM corporate_actions"),
            ("first", "SELECT MIN(ex_date) FROM corporate_actions"),
            ("last", "SELECT MAX(ex_date) FROM corporate_actions"),
            ("splits", "SELECT COUNT(*) FROM corporate_actions WHERE kind='split'"),
            ("bonuses", "SELECT COUNT(*) FROM corporate_actions WHERE kind='bonus'"),
            ("dividends", "SELECT COUNT(*) FROM corporate_actions WHERE kind='dividend'"),
            ("unparsed", "SELECT COUNT(*) FROM corporate_actions WHERE parsed=0"),
        ):
            try:
                out[key] = conn.execute(sql).fetchone()[0]
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                out[key] = None
    finally:
        conn.close()
    out["months_present"] = len(_months_present())
    out["note"] = ("Actions are stored as fetched. Prices are never rewritten; "
                   "adjustment is applied at read time. A subject that could "
                   "not be parsed is kept with parsed=0 and adjusts nothing.")
    return out
