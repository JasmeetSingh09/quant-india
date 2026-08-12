"""
universe_scan.py — score the ENTIRE NSE universe with the alpha model.

Design constraints this exists to satisfy:

  * ~2,400 stocks against a Yahoo endpoint that already throttles this IP, so
    the scan is slow by design (a full pass is expected to take many hours).
  * Render restarts the service on every deploy, and did so repeatedly during
    development. Progress is therefore written to the database after EVERY
    stock, and a restarted scan resumes from where it stopped rather than
    beginning again.
  * The app must stay responsive while it runs. The worker is a single
    background thread that sleeps between stocks; it never competes for the
    request path and is deliberately not fast.
  * Users should not see a "scanning" state. Reads always serve the last
    completed results; a scan in progress is invisible until it has something
    better to show.

Cap tiers follow the SEBI convention — rank by market cap, top 100 large,
next 150 mid, remainder small — which is why tiers are computed at READ time
from stored market caps rather than baked in per row.
"""

import json
import threading
import time
from datetime import datetime

from db import get_conn, IS_POSTGRES

# Deliberately gentle: this is a background crawl competing with live traffic
# for the same throttled connection. Raising these speeds the scan up and
# makes the app slower.
PAUSE_BETWEEN  = 1.2      # seconds between stocks
PAUSE_ON_ERROR = 4.0      # back off harder after a failure (usually throttling)
CYCLE_HOURS    = 24       # start a fresh pass once results are this old

_LOCK    = threading.Lock()
_THREAD  = None
_STOP    = threading.Event()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alpha_scan (
            ticker      TEXT PRIMARY KEY,
            alpha_score REAL,
            signal      TEXT,
            confidence  REAL,
            market_cap  REAL,
            momentum    REAL,
            quality     REAL,
            value       REAL,
            sentiment   REAL,
            error       TEXT,
            cycle       TEXT,
            scanned_at  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alpha_scan_state (
            id          INTEGER PRIMARY KEY,
            cycle       TEXT,
            started_at  TEXT,
            finished_at TEXT,
            done        INTEGER DEFAULT 0,
            total       INTEGER DEFAULT 0,
            status      TEXT
        )
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def _current_cycle() -> str:
    """Cycle id = the day the pass began. One full sweep per CYCLE_HOURS."""
    return datetime.now().strftime("%Y-%m-%d")


def get_state() -> dict:
    _init_db()
    conn = get_conn()
    row = conn.execute(
        "SELECT cycle, started_at, finished_at, done, total, status "
        "FROM alpha_scan_state WHERE id = 1"
    ).fetchone()
    scanned = conn.execute("SELECT COUNT(*) FROM alpha_scan WHERE alpha_score IS NOT NULL").fetchone()[0]
    conn.close()
    if not row:
        return {"status": "never_run", "done": 0, "total": 0, "scored_total": scanned}
    cycle, started, finished, done, total, status = row
    return {
        "status": status, "cycle": cycle, "started_at": started,
        "finished_at": finished, "done": done, "total": total,
        "scored_total": scanned,
        "pct": round(done / total * 100, 1) if total else 0.0,
        "running": _THREAD is not None and _THREAD.is_alive(),
    }


def _set_state(**kw):
    conn = get_conn()
    row = conn.execute("SELECT id FROM alpha_scan_state WHERE id = 1").fetchone()
    if not row:
        conn.execute(
            "INSERT INTO alpha_scan_state (id, cycle, started_at, finished_at, done, total, status) "
            "VALUES (1,?,?,?,?,?,?)",
            (kw.get("cycle"), kw.get("started_at"), kw.get("finished_at"),
             kw.get("done", 0), kw.get("total", 0), kw.get("status", "idle")))
    else:
        sets, vals = [], []
        for k, v in kw.items():
            sets.append(f"{k} = ?"); vals.append(v)
        if sets:
            conn.execute(f"UPDATE alpha_scan_state SET {', '.join(sets)} WHERE id = 1", vals)
    conn.commit()
    conn.close()


def _save_result(ticker: str, cycle: str, r: dict):
    """Upsert one stock's result. Errors are stored too, so a failing ticker is
    not retried forever within the same cycle."""
    now = datetime.now().isoformat()
    f = (r.get("factors") or {})
    vals = (
        ticker,
        r.get("alpha_score"), r.get("signal"), r.get("confidence"),
        (r.get("market_cap")),
        (f.get("momentum")  or {}).get("score"),
        (f.get("quality")   or {}).get("score"),
        (f.get("value")     or {}).get("score"),
        (f.get("sentiment") or {}).get("score"),
        r.get("error"), cycle, now,
    )
    conn = get_conn()
    if IS_POSTGRES:
        conn.execute(
            "INSERT INTO alpha_scan (ticker, alpha_score, signal, confidence, market_cap,"
            " momentum, quality, value, sentiment, error, cycle, scanned_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT (ticker) DO UPDATE SET"
            " alpha_score=EXCLUDED.alpha_score, signal=EXCLUDED.signal,"
            " confidence=EXCLUDED.confidence, market_cap=EXCLUDED.market_cap,"
            " momentum=EXCLUDED.momentum, quality=EXCLUDED.quality,"
            " value=EXCLUDED.value, sentiment=EXCLUDED.sentiment,"
            " error=EXCLUDED.error, cycle=EXCLUDED.cycle, scanned_at=EXCLUDED.scanned_at",
            vals)
    else:
        conn.execute(
            "INSERT OR REPLACE INTO alpha_scan (ticker, alpha_score, signal, confidence,"
            " market_cap, momentum, quality, value, sentiment, error, cycle, scanned_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", vals)
    conn.commit()
    conn.close()


def _already_done(cycle: str) -> set:
    """Tickers finished in THIS cycle — the basis for resuming after a restart."""
    conn = get_conn()
    rows = conn.execute("SELECT ticker FROM alpha_scan WHERE cycle = ?", (cycle,)).fetchall()
    conn.close()
    return {r[0] for r in rows}


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def _universe() -> list:
    from stock_universe import get_all_symbols, ensure_universe_loaded
    try:
        ensure_universe_loaded()
    except Exception:
        pass
    syms = get_all_symbols("NSE") or []
    out = []
    for s in syms:
        t = (s if isinstance(s, str) else (s.get("symbol") or "")).strip().upper()
        if not t:
            continue
        if not t.endswith(".NS"):
            t += ".NS"
        out.append(t)
    return sorted(set(out))


def _scan_loop():
    from alpha_model import compute_alpha_score, _ticker_info

    cycle = _current_cycle()
    universe = _universe()
    done = _already_done(cycle)
    todo = [t for t in universe if t not in done]

    _set_state(cycle=cycle, started_at=datetime.now().isoformat(), finished_at=None,
               done=len(done), total=len(universe), status="running")

    n = len(done)
    for ticker in todo:
        if _STOP.is_set():
            _set_state(status="stopped")
            return
        try:
            r = compute_alpha_score(ticker)
            if "error" not in r:
                try:
                    r["market_cap"] = (_ticker_info(ticker) or {}).get("marketCap")
                except Exception:
                    r["market_cap"] = None
            _save_result(ticker, cycle, r)
            time.sleep(PAUSE_BETWEEN)
        except Exception as e:
            try:
                _save_result(ticker, cycle, {"error": f"{type(e).__name__}: {e}"})
            except Exception:
                pass
            time.sleep(PAUSE_ON_ERROR)
        n += 1
        if n % 10 == 0:
            _set_state(done=n)

    _set_state(done=n, finished_at=datetime.now().isoformat(), status="complete")


def start_scan(force: bool = False) -> dict:
    """Kick off the background scan if one is not already running."""
    global _THREAD
    _init_db()
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return {"status": "already_running", **get_state()}
        st = get_state()
        if not force and st.get("status") == "complete" and st.get("cycle") == _current_cycle():
            return {"status": "already_complete_today", **st}
        _STOP.clear()
        _THREAD = threading.Thread(target=_scan_loop, name="alpha-universe-scan", daemon=True)
        _THREAD.start()
    return {"status": "started", **get_state()}


def stop_scan() -> dict:
    _STOP.set()
    return {"status": "stopping"}


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

# SEBI convention: rank all listed companies by market cap.
LARGE_CAP_RANK = 100      # ranks 1-100
MID_CAP_RANK   = 250      # ranks 101-250; everything after is small cap


def top_by_tier(n: int = 10, min_confidence: float = 0.3) -> dict:
    """
    Top `n` BUY-side names in each cap tier, plus the weakest names overall.

    Tiers are derived by RANKING stored market caps rather than applying fixed
    rupee thresholds, so they track the SEBI definition and stay correct as the
    market moves.
    """
    _init_db()
    conn = get_conn()
    rows = conn.execute(
        "SELECT ticker, alpha_score, signal, confidence, market_cap, "
        "       momentum, quality, value, sentiment, scanned_at "
        "FROM alpha_scan WHERE alpha_score IS NOT NULL AND error IS NULL"
    ).fetchall()
    conn.close()

    # Contributions are returned in POINTS (weight x factor score x 100), not as
    # raw factor scores, so the tier cards can reuse the existing pick-card UI
    # unchanged — it already renders contributions on that scale.
    from alpha_model import FACTOR_WEIGHTS as W

    def _pts(name, v):
        return round(W.get(name, 0) * (v or 0) * 100, 2)

    recs = [{
        "ticker": r[0], "alpha_score": r[1], "signal": r[2], "confidence": r[3],
        "market_cap": r[4],
        "contributions": {"momentum": _pts("momentum", r[5]),
                          "quality":  _pts("quality",  r[6]),
                          "value":    _pts("value",    r[7]),
                          "sentiment": _pts("sentiment", r[8])},
        "scanned_at": r[9],
    } for r in rows if (r[3] or 0) >= min_confidence]

    ranked_by_cap = sorted([r for r in recs if r["market_cap"]],
                           key=lambda r: -r["market_cap"])
    for i, r in enumerate(ranked_by_cap, 1):
        r["cap_rank"] = i
        r["cap_tier"] = ("large" if i <= LARGE_CAP_RANK else
                         "mid"   if i <= MID_CAP_RANK else "small")
    for r in recs:
        r.setdefault("cap_tier", "unknown")

    def tier_block(tier):
        """Best and worst n within a tier — ranked inside the tier, so a small
        cap is never judged against a large cap's score."""
        pool = sorted([r for r in recs if r.get("cap_tier") == tier],
                      key=lambda r: -(r["alpha_score"] or 0))
        buys   = pool[:n]
        avoids = list(reversed(pool[-n:])) if len(pool) > n else pool[len(buys):]
        # With a small pool the two lists could otherwise overlap.
        picked = {r["ticker"] for r in buys}
        avoids = [r for r in avoids if r["ticker"] not in picked]
        return {"buys": buys, "avoids": avoids, "scored": len(pool)}

    st = get_state()
    return {
        "large_cap": tier_block("large"),
        "mid_cap":   tier_block("mid"),
        "small_cap": tier_block("small"),
        "universe_scored": len(recs),
        "scan": {"status": st.get("status"), "cycle": st.get("cycle"),
                 "done": st.get("done"), "total": st.get("total"),
                 "finished_at": st.get("finished_at")},
    }


def get_signal_history(ticker: str, limit: int = 30) -> list:
    """Latest stored signal for a ticker (one row per cycle is kept)."""
    _init_db()
    ticker = (ticker or "").strip().upper()
    conn = get_conn()
    rows = conn.execute(
        "SELECT scanned_at, alpha_score, signal, confidence FROM alpha_scan "
        "WHERE ticker = ? ORDER BY scanned_at DESC", (ticker,)
    ).fetchall()
    conn.close()
    return [{"date": r[0], "alpha_score": r[1], "signal": r[2], "confidence": r[3]}
            for r in rows[:limit]]
