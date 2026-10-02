"""
thesis_records.py — write down WHY you hold a view on a stock, so a later
review can say which part was wrong.

Approved in docs/PROPOSAL_PRODUCT_ADDITIONS_2026-09-23.md (#4).

A thesis is the user's own reasoning: a stance, the reasons, the evidence, the
bear case, the risks and at least one "what would make me wrong" trigger.
Changing the view never edits the record: it appends a revision that must say
what changed, so the history shows what was believed when. Each revision stores
the price, score and rank at the time it was written.

Measurable triggers (a price close below a level, or the model's rank falling to
a level) are checked against stored prices and nightly scans and shown as
"met on <date>". The app flags; it never closes a thesis or acts by itself, and
it never suggests or grades one. Each user sees only their own theses.
"""

import json
from datetime import datetime, timedelta

from db import get_conn, IS_POSTGRES

STANCES = ("expect to outperform", "expect to underperform", "watching")
# The model's signal values, lowest to highest, and the rank words people read.
RANK_ORDER = {"STRONG SELL": 1, "SELL": 2, "NEUTRAL": 3, "HOLD": 3, "BUY": 4, "STRONG BUY": 5}
RANK_WORDS = {"Bottom ranked": 1, "Ranked low": 2, "Middle": 3, "Ranked high": 4, "Top ranked": 5}
TRIGGER_KINDS = ("price_below", "rank_at_or_below")
MAX_TEXT = 5000
MAX_TRIGGERS = 10
MAX_THESES_PER_USER = 200
CLOSE_REASONS_EXAMPLES = ("trigger met", "horizon reached", "changed my mind")


class ThesisError(ValueError):
    """A request the rules refuse; the message says why."""


class NotFound(LookupError):
    """No such thesis for this user (another user's thesis is also 'not found')."""


_SQLITE_DDL = (
    """CREATE TABLE IF NOT EXISTS theses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL, ticker TEXT NOT NULL, created_at TEXT NOT NULL,
        status TEXT NOT NULL, closed_at TEXT, close_reason TEXT,
        stance TEXT NOT NULL, horizon_months INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS thesis_revisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thesis_id INTEGER NOT NULL, created_at TEXT NOT NULL,
        reasons TEXT NOT NULL, evidence TEXT, bear_case TEXT NOT NULL, risks TEXT,
        invalidation TEXT NOT NULL, what_changed TEXT,
        snapshot TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS theses_user ON theses (user_id)",
    "CREATE INDEX IF NOT EXISTS thesis_revisions_thesis ON thesis_revisions (thesis_id)",
)
# Postgres has no AUTOINCREMENT; otherwise identical, so the two create alike.
_PG_DDL = tuple(s.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY") for s in _SQLITE_DDL)
_READY = [False]


def _init_db():
    if _READY[0]:
        return
    for stmt in (_PG_DDL if IS_POSTGRES else _SQLITE_DDL):
        # One statement per connection: a failed DDL aborts a Postgres transaction.
        conn = get_conn()
        try:
            conn.execute(stmt)
            conn.commit()
        except Exception:
            pass
        conn.close()
    _READY[0] = True


# ---------------------------------------------------------------------------
# What was known at the time: replaceable in tests, so no network is needed.
# ---------------------------------------------------------------------------

def _latest_scan(ticker):
    try:
        from stock_compare import _model_view
        return _model_view(ticker)
    except Exception:
        return None


def _snapshot(ticker):
    out = {"taken_at": datetime.now().isoformat(timespec="seconds")}
    try:
        from data_fetcher import download_close
        s = download_close(ticker, (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d"))
        s = s.dropna()
        if len(s):
            out["price"] = round(float(s.iloc[-1]), 2)
            out["price_date"] = str(s.index[-1])[:10]
    except Exception:
        pass
    scan = _latest_scan(ticker)
    if scan:
        out.update(alpha_score=scan.get("alpha_score"), signal=scan.get("signal"),
                   scanned_at=scan.get("scanned_at"))
    return out


def _price_history(ticker, since_iso):
    """Daily closes from the given date: [(date, close), ...].

    Asks for a week more than needed: download_close squeezes a one-row frame
    into a bare number, which happened for a thesis opened that same day.
    """
    import pandas as pd
    from data_fetcher import download_close
    start = (datetime.fromisoformat(since_iso[:10]) - timedelta(days=7)).strftime("%Y-%m-%d")
    s = download_close(ticker, start)
    if not isinstance(s, pd.Series):
        return []
    return [(str(d)[:10], float(v)) for d, v in s.dropna().items() if str(d)[:10] >= since_iso[:10]]


def _scan_history(ticker, since_iso):
    """Nightly scan signals from the given date: [(scanned_at, signal), ...]."""
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT scanned_at, signal FROM alpha_scan2 WHERE ticker = ? AND scanned_at >= ? "
            "AND error IS NULL ORDER BY scanned_at", (ticker, since_iso)).fetchall()
        conn.close()
        return [(r[0], r[1]) for r in rows]
    except Exception:
        return []


SNAPSHOT = _snapshot
PRICE_HISTORY = _price_history
SCAN_HISTORY = _scan_history


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _text(v, field, required):
    v = (v or "").strip() if isinstance(v, str) or v is None else None
    if v is None:
        raise ThesisError(f"{field} must be text.")
    if required and not v:
        raise ThesisError(f"{field} is required.")
    if len(v) > MAX_TEXT:
        raise ThesisError(f"{field} is longer than {MAX_TEXT} characters.")
    return v


def _triggers(raw):
    if not isinstance(raw, list) or not raw:
        raise ThesisError("At least one 'what would make me wrong' trigger is required.")
    if len(raw) > MAX_TRIGGERS:
        raise ThesisError(f"At most {MAX_TRIGGERS} triggers.")
    out = []
    for t in raw:
        if isinstance(t, str):
            t = {"text": t}
        if not isinstance(t, dict):
            raise ThesisError("Each trigger is a statement, optionally with a measurable part.")
        item = {"text": _text(t.get("text"), "Trigger text", True)}
        kind = t.get("kind")
        if kind:
            if kind not in TRIGGER_KINDS:
                raise ThesisError(f"A measurable trigger is one of {', '.join(TRIGGER_KINDS)}.")
            level = t.get("level")
            if kind == "price_below":
                try:
                    level = float(level)
                except (TypeError, ValueError):
                    raise ThesisError("A price trigger needs a price level.")
                if level <= 0:
                    raise ThesisError("A price level must be above zero.")
            elif level not in RANK_WORDS:
                raise ThesisError(f"A rank trigger needs one of: {', '.join(RANK_WORDS)}.")
            item.update(kind=kind, level=level)
        out.append(item)
    return out


def _content(body, first):
    c = {
        "reasons": _text(body.get("reasons"), "Reasons", True),
        "evidence": _text(body.get("evidence"), "Evidence", False),
        "bear_case": _text(body.get("bear_case"), "The bear case", True),
        "risks": _text(body.get("risks"), "Risks", False),
        "invalidation": _triggers(body.get("invalidation")),
        "what_changed": _text(body.get("what_changed"), "What changed", not first),
    }
    return c


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _own(conn, user_id, thesis_id):
    row = conn.execute(
        "SELECT id, user_id, ticker, created_at, status, closed_at, close_reason, stance, horizon_months "
        "FROM theses WHERE id = ? AND user_id = ?", (int(thesis_id), user_id)).fetchone()
    if not row:
        raise NotFound("No such thesis.")
    keys = ("id", "user_id", "ticker", "created_at", "status", "closed_at", "close_reason",
            "stance", "horizon_months")
    return dict(zip(keys, row))


def _revisions(conn, thesis_id):
    rows = conn.execute(
        "SELECT id, created_at, reasons, evidence, bear_case, risks, invalidation, what_changed, snapshot "
        "FROM thesis_revisions WHERE thesis_id = ? ORDER BY id", (int(thesis_id),)).fetchall()
    keys = ("id", "created_at", "reasons", "evidence", "bear_case", "risks", "invalidation",
            "what_changed", "snapshot")
    out = []
    for r in rows:
        d = dict(zip(keys, r))
        d["invalidation"] = json.loads(d["invalidation"])
        d["snapshot"] = json.loads(d["snapshot"])
        out.append(d)
    return out


def trigger_status(ticker, trigger, since_iso):
    """When a measurable trigger was first met after `since_iso`, or None.
    A flag only: nothing here changes a thesis."""
    kind = trigger.get("kind")
    if kind == "price_below":
        for day, close in PRICE_HISTORY(ticker, since_iso):
            if day >= since_iso[:10] and close < float(trigger["level"]):
                return {"met": True, "met_on": day, "detail": f"closed at {close:.2f}, below {float(trigger['level']):.2f}"}
        return {"met": False}
    if kind == "rank_at_or_below":
        target = RANK_WORDS[trigger["level"]]
        for at, signal in SCAN_HISTORY(ticker, since_iso):
            if RANK_ORDER.get(str(signal or "").upper(), 99) <= target:
                return {"met": True, "met_on": str(at)[:10], "detail": f"rank fell to {trigger['level']} or below"}
        return {"met": False}
    return None


def _safe_status(ticker, trig, since_iso):
    """A trigger that cannot be checked says so; it never stops the thesis
    from being read."""
    if not trig.get("kind"):
        return None
    try:
        return trigger_status(ticker, trig, since_iso)
    except Exception:
        return {"met": None, "detail": "could not be checked right now"}


def get(user_id, thesis_id, with_triggers=True):
    _init_db()
    conn = get_conn()
    try:
        t = _own(conn, user_id, thesis_id)
        t["revisions"] = _revisions(conn, thesis_id)
    finally:
        conn.close()
    if with_triggers and t["revisions"]:
        latest = t["revisions"][-1]
        t["trigger_status"] = [_safe_status(t["ticker"], trig, latest["created_at"])
                               for trig in latest["invalidation"]]
    return t


def list_for(user_id):
    _init_db()
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, ticker, created_at, status, stance, horizon_months, closed_at "
            "FROM theses WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    finally:
        conn.close()
    keys = ("id", "ticker", "created_at", "status", "stance", "horizon_months", "closed_at")
    return [dict(zip(keys, r)) for r in rows]


# ---------------------------------------------------------------------------
# Writing: the user's own data only
# ---------------------------------------------------------------------------

def _insert_revision(conn, thesis_id, c, snapshot):
    conn.execute(
        "INSERT INTO thesis_revisions (thesis_id, created_at, reasons, evidence, bear_case, risks, "
        "invalidation, what_changed, snapshot) VALUES (?,?,?,?,?,?,?,?,?)",
        (int(thesis_id), datetime.now().isoformat(timespec="seconds"), c["reasons"], c["evidence"],
         c["bear_case"], c["risks"], json.dumps(c["invalidation"]), c["what_changed"] or None,
         json.dumps(snapshot)))


def create(user_id, body):
    _init_db()
    ticker = (body.get("ticker") or "").strip().upper()
    if not ticker:
        raise ThesisError("A ticker is required.")
    if "." not in ticker and not ticker.startswith("^"):
        ticker += ".NS"
    stance = (body.get("stance") or "").strip().lower()
    if stance not in STANCES:
        raise ThesisError(f"Stance is one of: {', '.join(STANCES)}.")
    try:
        horizon = int(body.get("horizon_months"))
    except (TypeError, ValueError):
        raise ThesisError("Horizon is a whole number of months.")
    if not 1 <= horizon <= 60:
        raise ThesisError("Horizon is 1 to 60 months.")
    c = _content(body, first=True)
    # Taken BEFORE the write connection opens: the snapshot reads the scan
    # tables, and on SQLite a second connection inside an open write
    # transaction waits on the lock until it times out (found in the preview).
    snapshot = SNAPSHOT(ticker)
    conn = get_conn()
    try:
        n = conn.execute("SELECT COUNT(*) FROM theses WHERE user_id = ?", (user_id,)).fetchone()[0]
        if n >= MAX_THESES_PER_USER:
            raise ThesisError(f"At most {MAX_THESES_PER_USER} theses per person.")
        cur = conn.execute(
            "INSERT INTO theses (user_id, ticker, created_at, status, stance, horizon_months) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, ticker, datetime.now().isoformat(timespec="seconds"), "open", stance, horizon))
        thesis_id = cur.lastrowid
        _insert_revision(conn, thesis_id, c, snapshot)
        conn.commit()
    finally:
        conn.close()
    return get(user_id, thesis_id, with_triggers=False)


def revise(user_id, thesis_id, body):
    _init_db()
    c = _content(body, first=False)
    conn = get_conn()
    try:
        t = _own(conn, user_id, thesis_id)
        if t["status"] != "open":
            raise ThesisError("A closed thesis cannot be revised; open a new one.")
    finally:
        conn.close()
    snapshot = SNAPSHOT(t["ticker"])              # outside any write transaction
    conn = get_conn()
    try:
        _insert_revision(conn, thesis_id, c, snapshot)
        conn.commit()
    finally:
        conn.close()
    return get(user_id, thesis_id, with_triggers=False)


def close(user_id, thesis_id, reason):
    _init_db()
    reason = _text(reason, "A reason for closing", True)
    conn = get_conn()
    try:
        t = _own(conn, user_id, thesis_id)
        if t["status"] != "open":
            raise ThesisError("This thesis is already closed.")
        conn.execute("UPDATE theses SET status = ?, closed_at = ?, close_reason = ? WHERE id = ? AND user_id = ?",
                     ("closed", datetime.now().isoformat(timespec="seconds"), reason, int(thesis_id), user_id))
        conn.commit()
    finally:
        conn.close()
    return get(user_id, thesis_id, with_triggers=False)


def delete(user_id, thesis_id):
    """The user's own data: deletes the thesis and all its revisions."""
    _init_db()
    conn = get_conn()
    try:
        _own(conn, user_id, thesis_id)
        conn.execute("DELETE FROM thesis_revisions WHERE thesis_id = ?", (int(thesis_id),))
        conn.execute("DELETE FROM theses WHERE id = ? AND user_id = ?", (int(thesis_id), user_id))
        conn.commit()
    finally:
        conn.close()
    return {"deleted": int(thesis_id)}
