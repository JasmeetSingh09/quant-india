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
PAUSE_BETWEEN  = 0.4      # seconds a worker waits after finishing a stock
PAUSE_ON_ERROR = 3.0      # back off harder after a failure (usually throttling)
CYCLE_HOURS    = 24       # start a fresh pass once results are this old

# Each stock is ~200s of WAITING on throttled Yahoo round-trips, not computing,
# so the scan is I/O-bound and parallelises well. Serially it managed 18
# stocks/hour — 5.5 days for the universe. Kept modest: more workers means
# heavier throttling, and the point is to finish in a day without degrading the
# live app that shares this connection.
MAX_WORKERS    = 6

# Bump when the alpha model changes in a way that invalidates stored scores.
# Rows carrying an older version are treated as NOT done and get re-scored, so a
# model fix reaches already-scanned stocks instead of waiting for tomorrow's
# cycle. IDEA.NS sat at +55.95 STRONG BUY for hours after the distress fix
# landed purely because its row already existed for the current cycle.
MODEL_VERSION  = "distress-v3-coverage"

_LOCK    = threading.Lock()
_THREAD  = None
_STOP    = threading.Event()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# Scan order is shuffled so a throttled run does not always starve the same
# tail of the universe. Fixed seed: the order must be identical across
# restarts or a partial scan is not reproducible.
SHUFFLE_SEED = 20260813

def _init_db():
    conn = get_conn()
    # Keyed on (ticker, cycle), not ticker alone. With ticker as the sole key a
    # new pass overwrote the previous one row by row, so the dashboard showed a
    # half-old/half-new mixture while scanning, and signal history could never
    # hold more than one reading per stock. Keeping cycles side by side lets the
    # display stay pinned to the last COMPLETE pass while the next one fills in
    # behind it, and lets history actually accumulate day over day.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alpha_scan2 (
            ticker      TEXT NOT NULL,
            alpha_score REAL,
            signal      TEXT,
            confidence  REAL,
            market_cap  REAL,
            momentum    REAL,
            quality     REAL,
            value       REAL,
            sentiment   REAL,
            error       TEXT,
            cycle       TEXT NOT NULL,
            scanned_at  TEXT,
            PRIMARY KEY (ticker, cycle)
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
            status      TEXT,
            last_complete_cycle TEXT
        )
    """)
    conn.commit()
    conn.close()

    # last_complete_cycle was added after the table shipped, and CREATE TABLE
    # IF NOT EXISTS will not add a column to an existing table. Run the ALTER on
    # its OWN connection: on Postgres a failing statement poisons every
    # subsequent one in the same transaction, which is exactly what 500'd the
    # watchlist and simulator endpoints after the Supabase switch.
    conn = get_conn()
    try:
        if IS_POSTGRES:
            conn.execute("ALTER TABLE alpha_scan_state "
                         "ADD COLUMN IF NOT EXISTS last_complete_cycle TEXT")
        else:
            conn.execute("ALTER TABLE alpha_scan_state ADD COLUMN last_complete_cycle TEXT")
    except Exception:
        pass
    finally:
        conn.close()

    conn = get_conn()
    try:
        if IS_POSTGRES:
            conn.execute("ALTER TABLE alpha_scan2 ADD COLUMN IF NOT EXISTS model_version TEXT")
        else:
            conn.execute("ALTER TABLE alpha_scan2 ADD COLUMN model_version TEXT")
        conn.commit()
    except Exception:
        pass          # already present
    finally:
        conn.close()

    # Somewhere for a crash to be recorded. Without it the failure handler
    # writes to a column that does not exist, fails, gets swallowed by its own
    # guard, and the diagnostic disappears exactly when it is needed.
    conn = get_conn()
    try:
        if IS_POSTGRES:
            conn.execute("ALTER TABLE alpha_scan_state "
                         "ADD COLUMN IF NOT EXISTS last_error TEXT")
        else:
            conn.execute("ALTER TABLE alpha_scan_state ADD COLUMN last_error TEXT")
        conn.commit()
    except Exception:
        pass
    finally:
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
        "SELECT cycle, started_at, finished_at, done, total, status, "
        "last_complete_cycle, last_error FROM alpha_scan_state WHERE id = 1"
    ).fetchone()
    scanned = conn.execute("SELECT COUNT(*) FROM alpha_scan2 WHERE alpha_score IS NOT NULL").fetchone()[0]
    # Attempted is not the same as succeeded. Errors are stored so a bad ticker
    # is not retried forever, which means they also count toward "done" — so a
    # progress bar built on `done` alone can read 100% while a large share of
    # the universe failed. That is the shape of the bug that let a 130-stock
    # scan report itself complete.
    # The CURRENT cycle, not the last complete one — progress is about the scan
    # running now, and preferring last_complete would report yesterday's counts
    # against today's total.
    _cyc = (row[0] if row else None) or (row[6] if row and len(row) > 6 else None)
    ok_n = err_n = 0
    if _cyc:
        try:
            ok_n = conn.execute(
                "SELECT COUNT(*) FROM alpha_scan2 WHERE cycle = ? AND alpha_score IS NOT NULL",
                (_cyc,)).fetchone()[0]
            err_n = conn.execute(
                "SELECT COUNT(*) FROM alpha_scan2 WHERE cycle = ? AND alpha_score IS NULL",
                (_cyc,)).fetchone()[0]
        except Exception:
            ok_n = err_n = 0
    conn.close()
    if not row:
        return {"status": "never_run", "done": 0, "total": 0, "scored_total": scanned}
    cycle, started, finished, done, total, status, last_complete = row[:7]
    last_error = row[7] if len(row) > 7 else None
    return {
        "status": status, "cycle": cycle, "started_at": started,
        "finished_at": finished, "done": done, "total": total,
        "last_complete_cycle": last_complete,
        "last_error": last_error,
        "scored_total": scanned,
        "succeeded": ok_n,
        "failed": err_n,
        "progress_note": (f"{done} of {total} attempted; {ok_n} scored, {err_n} failed."
                          if total else f"{done} attempted; {ok_n} scored, {err_n} failed."),
        # The universe grows between a scan starting and finishing — bhavcopy
        # adds symbols nightly — so `done` can exceed the `total` captured at
        # the start, and the bar reads over 100%. Clamped for display; the raw
        # counts above are left untouched because they are the honest record.
        "pct": round(min(done / total * 100, 100.0), 1) if total else 0.0,
        "running": _THREAD is not None and _THREAD.is_alive(),
    }


def _set_state(**kw):
    conn = get_conn()
    row = conn.execute("SELECT id FROM alpha_scan_state WHERE id = 1").fetchone()
    if not row:
        # Seed a bare row, then fall through to the UPDATE below. The INSERT
        # used to spell out its columns, so any key it did not name was
        # silently dropped — last_complete_cycle vanished on first write, and
        # the display then served a half-finished scan.
        conn.execute("INSERT INTO alpha_scan_state (id, status) VALUES (1, ?)",
                     (kw.get("status", "idle"),))
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
        r.get("error"), cycle, now, MODEL_VERSION,
    )
    conn = get_conn()
    if IS_POSTGRES:
        conn.execute(
            "INSERT INTO alpha_scan2 (ticker, alpha_score, signal, confidence, market_cap,"
            " momentum, quality, value, sentiment, error, cycle, scanned_at, model_version)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT (ticker, cycle) DO UPDATE SET"
            " alpha_score=EXCLUDED.alpha_score, signal=EXCLUDED.signal,"
            " confidence=EXCLUDED.confidence, market_cap=EXCLUDED.market_cap,"
            " momentum=EXCLUDED.momentum, quality=EXCLUDED.quality,"
            " value=EXCLUDED.value, sentiment=EXCLUDED.sentiment,"
            " error=EXCLUDED.error, cycle=EXCLUDED.cycle, scanned_at=EXCLUDED.scanned_at,"
            " model_version=EXCLUDED.model_version",
            vals)
    else:
        conn.execute(
            "INSERT OR REPLACE INTO alpha_scan2 (ticker, alpha_score, signal, confidence,"
            " market_cap, momentum, quality, value, sentiment, error, cycle, scanned_at, model_version)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", vals)
    conn.commit()
    conn.close()

    # Write the same scores to the history table, so "what changed" has a
    # factual answer later. Never allowed to break a scan: a lost observation
    # is a gap in history, not a broken product.
    try:
        from factor_history import record as _fh_record
        if not r.get("error"):
            _fh_record(ticker, "v1", alpha_score=r.get("alpha_score"),
                       factors=f, price=(r.get("price") or r.get("current_price")))
    except Exception:
        pass


# A pass has to cover this much of the universe to count as an observation of
# the market. Below it, the sample is "whichever stocks answered today", which
# is not the same thing and cannot be told apart from the real thing once it is
# in the record.
from model_config import SCAN_COMPLETE_FRACTION as MIN_COMPLETE_FRACTION


def _scored_count(cycle: str) -> int:
    """Stocks that actually produced a score this cycle. Errors do not count —
    they are rows, and rows were what completion used to be measured by."""
    try:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM alpha_scan2 WHERE cycle = ? "
                "AND model_version = ? AND alpha_score IS NOT NULL",
                (cycle, MODEL_VERSION)).fetchone()
            return int(row[0] or 0)
        finally:
            conn.close()
    except Exception:
        return 0


def _already_done(cycle: str) -> set:
    """Tickers finished in THIS cycle — the basis for resuming after a restart."""
    conn = get_conn()
    rows = conn.execute("SELECT ticker FROM alpha_scan2 WHERE cycle = ? "
                        "AND model_version = ?", (cycle, MODEL_VERSION)).fetchall()
    conn.close()
    return {r[0] for r in rows}


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def _bhavcopy_symbols() -> list:
    """
    Every symbol the exchange itself published, from our own database.

    The scan was covering ~130 stocks out of 2,400. The cause was the universe
    source: it fetches the listing over the network, and when that fetch degrades
    it silently falls back to a short built-in list. The scan then completed
    honestly against a universe that was almost empty — status "complete", 130
    stocks, and nobody the wiser.

    Bhavcopy already holds 2,700+ NSE symbols locally, straight from the
    exchange's own daily file. It needs no network, cannot be throttled, and is
    authoritative about what is actually listed. So it is now the primary source
    and the network listing is the fallback, which is the correct way round.
    """
    try:
        from db import get_conn
        conn = get_conn()
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM bhavcopy_eod "
            "WHERE day >= (SELECT MAX(day) FROM bhavcopy_eod)").fetchall()
        conn.close()
        return [r[0] for r in rows if r and r[0]]
    except Exception:
        return []


def _universe() -> list:
    from stock_universe import get_all_symbols, ensure_universe_loaded

    syms = _bhavcopy_symbols()
    if len(syms) >= 500:
        pass                       # the exchange's own list; nothing to add
    else:
        try:
            ensure_universe_loaded()
        except Exception:
            pass
        syms = list(syms) + list(get_all_symbols("NSE") or [])
    out = []
    for s in syms:
        t = (s if isinstance(s, str) else (s.get("symbol") or "")).strip().upper()
        if not t:
            continue
        if not t.endswith(".NS"):
            t += ".NS"
        out.append(t)
    out = sorted(set(out))

    # Order matters while the scan is incomplete. Alphabetical meant every
    # partial result was an A — the large and mid tiers showed nothing but
    # ADANI* and A-names for hours, which reads as a broken product rather than
    # a running scan. So: the known liquid names first (they populate the large
    # and mid tiers immediately), then everything else in a deterministic
    # shuffle so partial coverage is spread across the whole alphabet instead of
    # clustered at the front.
    try:
        from data_fetcher import NSE_SECTORS
        priority = [t for v in NSE_SECTORS.values() for t in v]
    except Exception:
        priority = []
    pri_set = set(priority)
    head = [t for t in priority if t in set(out)]
    tail = [t for t in out if t not in pri_set]
    import random as _r
    _r.Random(SHUFFLE_SEED).shuffle(tail)     # fixed seed: same order across restarts
    return head + tail


def _scan_loop():
    """
    Wrapper that makes a crash visible.

    The body used to run unguarded, so an exception anywhere in it killed the
    thread silently: the state kept saying "running" with done=0 and
    finished_at=None forever, the traceback went to stderr where nobody reads
    it, and from the outside a scan that died on its first stock was
    indistinguishable from one still working. Production sat in exactly that
    state — started, zero rows, thread gone — and the API had no way to say so.
    """
    try:
        _scan_loop_inner()
    except BaseException as e:
        import traceback
        detail = f"{type(e).__name__}: {e}"
        print(f"[scan] CRASHED: {detail}\n{traceback.format_exc()}")
        try:
            _set_state(status="failed", finished_at=datetime.now().isoformat(),
                       last_error=detail[:500])
        except Exception:
            pass
        raise


def _scan_loop_inner():
    from alpha_model import compute_alpha_score, _ticker_info

    cycle = _current_cycle()
    universe = _universe()
    done = _already_done(cycle)
    todo = [t for t in universe if t not in done]

    # last_error is cleared here, not left to age. A pass that is running now
    # while the state still displays the crash that killed the previous one
    # reports a failure that is no longer true, which is worse than reporting
    # nothing — the whole point of recording it was to say what is happening.
    _set_state(cycle=cycle, started_at=datetime.now().isoformat(), finished_at=None,
               done=len(done), total=len(universe), status="running",
               last_error=None)

    from concurrent.futures import ThreadPoolExecutor

    counter = {"n": len(done)}
    clock   = threading.Lock()

    def _one(ticker):
        """Score and persist a single stock. Never raises — a bad ticker must
        not take down the pool, and its error is stored so the cycle does not
        retry it forever."""
        if _STOP.is_set():
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
        # Progress is still written per stock, so a restart resumes accurately
        # regardless of which workers were mid-flight.
        with clock:
            counter["n"] += 1
            if counter["n"] % 10 == 0:
                try:
                    _set_state(done=counter["n"])
                except Exception:
                    pass

    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="scan") as pool:
        list(pool.map(_one, todo))

    if _STOP.is_set():
        _set_state(done=counter["n"], status="stopped")
        return

    # Completion is now a measurement, not the fact that the loop ended.
    #
    # This used to mark the cycle complete the moment the pool drained, whether
    # the stocks had scored or errored, and publish it as the serving cycle. A
    # pass where most of the universe failed was recorded exactly like a clean
    # one, and — because factor history cannot be backfilled — an incomplete
    # pass logged as a research observation is a permanently wrong row.
    #
    # So a pass has to have actually covered the market to count. If it did
    # not, the cycle stays incomplete, the display keeps serving the last good
    # pass, and the next run resumes this one instead of starting over.
    scored = _scored_count(cycle)
    universe_n = len(universe)
    frac = (scored / universe_n) if universe_n else 0.0
    if frac >= MIN_COMPLETE_FRACTION:
        # Publishing happens HERE and only here: the display swaps to this pass
        # atomically once it is finished, never partway through.
        _set_state(done=counter["n"], finished_at=datetime.now().isoformat(),
                   status="complete", last_complete_cycle=cycle)
    else:
        _set_state(done=counter["n"], finished_at=datetime.now().isoformat(),
                   status="incomplete")
        print(f"[scan] cycle {cycle} INCOMPLETE: {scored} of {universe_n} "
              f"scored ({frac:.1%}, need {MIN_COMPLETE_FRACTION:.0%}). Not "
              f"published, no snapshot logged. A partial pass is not an "
              f"observation of the market.")
        return

    # Log the track-record snapshot the moment fresh scores exist, rather than
    # hoping a 16:30 cron lands after the scan. It used to be timed, and the
    # snapshot now REFUSES a stale or missing cycle — correctly — which means a
    # scan that finishes late would have produced no observation for that day at
    # all. Evidence accrues one day at a time and a skipped day cannot be
    # recovered, so the trigger belongs here where completion is known.
    #
    # Never allowed to break the scan: a failed snapshot loses one day of
    # record, a raised exception would lose the whole pass.
    try:
        # No `import threading` here. The module already imports it at the top,
        # and re-importing it inside this function made `threading` a LOCAL
        # name for the whole function — so `clock = threading.Lock()`, nearly
        # two hundred lines earlier, raised UnboundLocalError before a single
        # stock was scored. Every scan died on its first statement, the state
        # sat at "running" with done=0, and the last completed cycle receded
        # further into the past for nine days.
        from prediction_tracker import snapshot as _snap

        def _log_snapshot():
            try:
                r = _snap()
                print(f"  snapshot after scan: {r.get('logged')} logged "
                      f"of {r.get('universe_size')}"
                      + (f" (skipped: {r.get('reason', '')[:60]})"
                         if r.get("skipped") else ""))
            except Exception as e:
                print(f"  snapshot after scan failed: {type(e).__name__}")

        threading.Thread(target=_log_snapshot, daemon=True).start()
    except Exception:
        pass


def start_scan(force: bool = False) -> dict:
    """Kick off the background scan if one is not already running."""
    global _THREAD
    _init_db()
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return {"action": "already_running", **get_state()}
        st = get_state()
        if not force and st.get("status") == "complete" and st.get("cycle") == _current_cycle():
            return {"action": "already_complete_today", **st}
        _STOP.clear()
        _THREAD = threading.Thread(target=_scan_loop, name="alpha-universe-scan", daemon=True)
        _THREAD.start()
    # `action` is what THIS call did; `status` comes from get_state and is
    # what the scan is. They used to share the key, so the spread silently
    # overwrote the literal and start_scan reported "complete" immediately
    # after starting a thread — the same collision class as bl_pct.
    return {"action": "started", **get_state()}


def resume_if_incomplete() -> dict:
    """
    Restart the scan whenever today's pass is not finished.

    start_scan runs once, at application startup. That was the whole cadence,
    and it is why production went nine days without a completed cycle: the
    instance sleeps or redeploys, the daemon thread dies mid-pass, and nothing
    starts another one until something happens to restart the process. A pass
    takes two to five hours of wall clock, so it rarely survives to the end.

    This is the same recurring guard the archive fetch and the screener cache
    already have, for the same reason and after the same failure. Progress is
    written per stock, so a resumed pass continues from where it stopped rather
    than starting over.

    Cheap to call: it does nothing when a scan is alive or today's pass is
    already complete.
    """
    try:
        if _THREAD is not None and _THREAD.is_alive():
            return {"action": "none", "reason": "a scan is already running"}
        st = get_state()
        today = _current_cycle()
        if st.get("status") == "complete" and st.get("cycle") == today:
            return {"action": "none", "reason": "today's pass is complete"}
        scored = _scored_count(today)
        r = start_scan()
        return {"action": "started", "cycle": today,
                "already_scored": scored, "result": r.get("action"),
                "note": ("Resuming an unfinished pass. Factor history cannot be "
                         "backfilled, so a day without a completed scan is "
                         "research data that no later run recovers.")}
    except Exception as e:
        return {"action": "failed", "error": f"{type(e).__name__}: {e}"}


def stop_scan() -> dict:
    _STOP.set()
    return {"status": "stopping"}


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

# AMFI/SEBI cap bands expressed in RUPEES rather than as ranks.
#
# Ranking was the original approach, but ranks can only be computed against the
# stocks scanned SO FAR. Mid-scan that meant ranking ~180 alphabetically-early
# names, which labelled AFIL — a ₹416 Cr company — as "mid cap" because it
# happened to sit 101st in that partial list. Absolute thresholds are correct
# from the very first stock scanned and do not lie while the scan is running.
#
# Cut-offs track the AMFI bands: large ≈ top 100 (> ₹1,00,000 Cr),
# mid ≈ ranks 101-250 (₹33,000-1,00,000 Cr), small below that.
# SEBI's actual definition is positional, not monetary.
LARGE_CAP_RANK_MAX = 100   # ranks 1-100    -> large cap
MID_CAP_RANK_MAX   = 250   # ranks 101-250  -> mid cap; 251+ -> small cap

# Kept only so older stored rows and any caller still importing them resolve.
# Nothing classifies on these any more.
LARGE_CAP_MIN = 1.00e12   # ₹1,00,000 Cr
MID_CAP_MIN   = 3.30e11   # ₹33,000 Cr


def top_by_tier(n: int = 10, min_confidence: float = 0.3) -> dict:
    """
    Top `n` BUY-side names in each cap tier, plus the weakest names overall.

    Tiers are derived by RANKING stored market caps rather than applying fixed
    rupee thresholds, so they track the SEBI definition and stay correct as the
    market moves.
    """
    _init_db()
    st = get_state()
    # Serve the last COMPLETE pass. While the next one runs its rows accumulate
    # under a different cycle and stay invisible, so the dashboard never shows a
    # half-updated mixture — it keeps yesterday's answer until today's is whole.
    # On the very first run there is no complete pass yet, so fall back to
    # whatever the in-progress cycle has rather than showing an empty app.
    serve_cycle = st.get("last_complete_cycle") or st.get("cycle")
    conn = get_conn()
    rows = conn.execute(
        "SELECT ticker, alpha_score, signal, confidence, market_cap, "
        "       momentum, quality, value, sentiment, scanned_at "
        "FROM alpha_scan2 WHERE alpha_score IS NOT NULL AND error IS NULL "
        "  AND cycle = ?", (serve_cycle,)
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

    # SEBI defines the tiers by RANK, not by rupee thresholds: the 1st-100th
    # company by full market cap is large cap, 101st-250th is mid, 251st onward
    # is small. We were using fixed rupee cut-offs while the interface told users
    # the opposite — a claim about our own methodology that was simply untrue.
    #
    # Rank is also the more durable definition. Fixed thresholds drift with the
    # market: a rupee band set today silently reclassifies half the exchange
    # after a big year, whereas "top 100" means the same thing in every market.
    ranked = sorted([r for r in recs if r.get("market_cap")],
                    key=lambda r: -(r["market_cap"] or 0))
    for i, r in enumerate(ranked):
        r["cap_rank"] = i + 1
        r["cap_tier"] = ("large" if i < LARGE_CAP_RANK_MAX else
                         "mid"   if i < MID_CAP_RANK_MAX else "small")
    for r in recs:
        if not r.get("market_cap"):
            r["cap_tier"], r["cap_rank"] = "unknown", None

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
        # A score means nothing on a stock that trades Rs 241 a day. Annotated
        # rather than filtered out: silently dropping a name leaves the user
        # wondering where it went, whereas showing it marked "barely trades"
        # teaches them why it was never an opportunity.
        try:
            from liquidity import annotate
            annotate(buys)
            annotate(avoids)
        except Exception:
            pass
        return {"buys": buys, "avoids": avoids, "scored": len(pool)}

    return {
        "serving_cycle": serve_cycle,
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
        "SELECT scanned_at, alpha_score, signal, confidence FROM alpha_scan2 "
        "WHERE ticker = ? ORDER BY scanned_at DESC", (ticker,)
    ).fetchall()
    conn.close()
    out = [{"date": r[0], "alpha_score": r[1], "signal": r[2], "confidence": r[3]}
           for r in rows[:limit]]
    if not out:
        return out

    # Attach the closing price on each reading's date, so a past call can be
    # read against what the stock actually did: "BUY at 2,188 five days ago,
    # 2,364 now". Fetched from history rather than stored at scan time, which
    # means it also fills in for readings taken before this existed.
    try:
        import yfinance as yf
        from datetime import timedelta
        dates = sorted({d["date"][:10] for d in out})
        start = (datetime.fromisoformat(dates[0]) - timedelta(days=7)).strftime("%Y-%m-%d")
        end   = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        px = yf.download(ticker, start=start, end=end, progress=False,
                         auto_adjust=True)["Close"].squeeze().dropna()
        if len(px):
            closes = {str(i.date()): float(v) for i, v in px.items()}
            days   = sorted(closes)
            for row in out:
                d = row["date"][:10]
                # Markets close on weekends and holidays: fall back to the most
                # recent trading day at or before the reading.
                prior = [x for x in days if x <= d]
                row["close"] = round(closes[prior[-1]], 2) if prior else None
            latest = round(float(px.iloc[-1]), 2)
            for row in out:
                if row.get("close"):
                    row["price_now"] = latest
                    row["since_pct"] = round((latest / row["close"] - 1) * 100, 2)
    except Exception:
        pass          # price history is a nice-to-have; never fail the history
    return out


def stored_scores_for_today() -> dict:
    """
    {ticker: {alpha_score, signal, confidence}} from the newest complete cycle.

    Lets the prediction tracker log the whole universe without re-running the
    model on 2,400 stocks — the scan already did that work today, and re-doing
    it would make full coverage impossible rather than merely slow.
    """
    _init_db()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT last_complete_cycle, cycle FROM alpha_scan_state WHERE id = 1"
        ).fetchone()
        cycle = (row[0] or row[1]) if row else None
        if not cycle:
            return {}
        rows = conn.execute(
            "SELECT ticker, alpha_score, signal, confidence FROM alpha_scan2 "
            "WHERE cycle = ? AND alpha_score IS NOT NULL", (cycle,)).fetchall()
    except Exception:
        return {}
    finally:
        conn.close()
    return {r[0]: {"alpha_score": r[1], "signal": r[2], "confidence": r[3]}
            for r in rows}
