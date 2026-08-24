import os
"""
prediction_tracker.py — HONEST track record of the alpha model's picks.

We log every pick (ticker, date, alpha score, signal, price at that moment), then
later compare it against what actually happened to the price. This turns "does the
model work?" from an opinion into MEASURED data:

  - Do BUY-signalled stocks actually outperform SELL-signalled ones?
  - Does a higher alpha score correlate with higher forward return?
  - Do the picks beat the Nifty 50 benchmark?

Given that returns are largely unpredictable, this will most likely show little or
no edge — and reporting that honestly is the entire point. A real track record,
warts and all, is far more credible than a cherry-picked screenshot.
"""

import time
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
from db import IS_POSTGRES
import pandas as pd
import yfinance as yf

_DB_PATH = Path(os.environ.get("QUANT_DATA_DIR", str(Path(__file__).parent.parent))) / "quant_platform.db"
BENCHMARK = "^NSEI"


def _conn():
    from db import get_conn      # Postgres (Supabase) if DATABASE_URL set, else SQLite
    return get_conn()


def _add_horizon_column():
    """
    Record the horizon the signal itself claimed.

    Evaluation horizon is a read-time choice — that is why the scorecard takes
    min_days — but the horizon the MODEL advertised when it issued the call is a
    property of the call, and belongs on the row. Without it a signal logged
    under a 21-day model cannot be told apart from one logged under a different
    model later, and the record silently mixes them.

    On its own connection: a failed ALTER poisons the whole transaction on
    Postgres, which is what previously 500'd unrelated endpoints.
    """
    try:
        c = _conn()
        try:
            if IS_POSTGRES:
                c.execute("ALTER TABLE predictions ADD COLUMN IF NOT EXISTS "
                          "signal_horizon_days INTEGER")
            else:
                c.execute("ALTER TABLE predictions ADD COLUMN signal_horizon_days INTEGER")
            c.commit()
        except Exception:
            pass
        finally:
            c.close()
    except Exception:
        pass


def init_table():
    c = _conn()
    c.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            alpha_score REAL,
            signal TEXT,
            price_at_snapshot REAL,
            UNIQUE(ticker, snapshot_date)
        )
    """)
    c.commit()
    c.close()


# A scan older than this is not today's opinion. One day of slack covers a
# scan that finished after midnight.
MAX_CYCLE_AGE_DAYS = 1


def _add_cycle_column():
    """The scan cycle a prediction came from, so a snapshot can be traced back
    to the run that produced its scores. Own connection: on Postgres a failed
    statement aborts the whole transaction, so batching migrations means one
    already-exists error takes the rest down with it."""
    for ddl in ("ALTER TABLE predictions ADD COLUMN scan_cycle TEXT",
                "ALTER TABLE predictions ADD COLUMN universe_size INTEGER",
                "ALTER TABLE predictions ADD COLUMN source TEXT"):
        c = _conn()
        try:
            c.execute(ddl)
            c.commit()
        except Exception:
            pass
        finally:
            c.close()


def snapshot(universe: list = None, allow_fallback: bool = False) -> dict:
    """
    Log today's alpha picks. Call this daily (or on demand). Records each ticker's
    alpha score, signal, and current price, so we can grade it later.
    """
    init_table()
    _add_horizon_column()
    _add_cycle_column()
    from alpha_model import compute_alpha_score, TOP_PICKS_UNIVERSE
    today = datetime.now().strftime("%Y-%m-%d")

    # Default to everything the universe scan has already scored, not a curated
    # list of thirty. The track record measured 30 stocks while the model rated
    # 2,400 — so the evidence covered barely one percent of what the app shows,
    # and the thin sample the verdict keeps complaining about was largely
    # self-inflicted.
    #
    # Re-scoring is not needed: the scan stored a score for every stock today.
    # Reading those rows makes this a database pass instead of thousands of
    # model runs, which is the only way covering the full universe is feasible.
    scored, cycle, source = {}, None, "explicit"
    if universe is None:
        try:
            from universe_scan import stored_scores_for_today
            scored = stored_scores_for_today()
        except Exception:
            scored = {}
        try:
            from db import get_conn as _gc
            _c = _gc()
            row = _c.execute("SELECT last_complete_cycle FROM alpha_scan_state "
                             "WHERE id = 1").fetchone()
            cycle = row[0] if row else None
            _c.close()
        except Exception:
            cycle = None

    # The silent fallback is why the entire track record is 30 large caps. When
    # no completed scan exists this quietly logged TOP_PICKS_UNIVERSE instead,
    # and nothing downstream could tell a 30-stock day from a 2,573-stock day —
    # so months of narrow, unrepresentative observations accumulated looking
    # exactly like broad ones.
    #
    # It now refuses by default. A caller that genuinely wants the small list
    # has to ask for it, and the row records that it did.
    # A completed cycle is not the same as a CURRENT one. Locally this happily
    # paired scores from a scan eleven days old with today's closing price and
    # logged it as today's prediction — an observation where the signal and the
    # price come from different weeks measures neither.
    cycle_age = None
    if cycle:
        try:
            cycle_age = (datetime.strptime(today, "%Y-%m-%d")
                         - datetime.strptime(str(cycle)[:10], "%Y-%m-%d")).days
        except Exception:
            cycle_age = None

    if universe is not None:
        source = "explicit"
    elif scored and (cycle_age is None or cycle_age <= MAX_CYCLE_AGE_DAYS):
        universe, source = list(scored), "scan"
    elif scored and not allow_fallback:
        return {"snapshot_date": today, "logged": 0, "universe_size": 0,
                "skipped": True, "scan_cycle": cycle, "cycle_age_days": cycle_age,
                "reason": (f"The most recent completed scan is from {cycle}, "
                           f"{cycle_age} days old. Logging those scores against "
                           f"today's price would pair a signal and a price from "
                           f"different weeks, which measures neither. Run the "
                           f"scan first.")}
    elif allow_fallback:
        universe, source = TOP_PICKS_UNIVERSE, "fallback_30"
    else:
        return {"snapshot_date": today, "logged": 0, "universe_size": 0,
                "skipped": True,
                "reason": ("No completed scan cycle, so there are no scores to "
                           "log. Refusing to fall back to the 30-stock list: "
                           "that fallback is what made the existing track "
                           "record large-cap only, and a narrow day is "
                           "indistinguishable from a broad one once logged.")}

    # Prices from the exchange's own file. One query for every symbol, instead
    # of one throttled Yahoo round-trip per stock — at 2,400 stocks that
    # difference is the whole feature.
    bhav = {}
    try:
        from bhavcopy import closes_for_latest_day
        bhav = closes_for_latest_day()
    except Exception:
        bhav = {}

    logged = 0
    # Exclusions are counted with a reason. "2,573 logged" says nothing about
    # what was dropped or why, and a coverage figure that cannot be decomposed
    # is not a coverage figure.
    excluded = {"no_score": 0, "no_price": 0, "error": 0}
    c = _conn()
    for t in universe:
        try:
            stored = scored.get(t)
            r = stored if stored else compute_alpha_score(t)
            if not r or r.get("alpha_score") is None:
                excluded["no_score"] += 1
                continue
            px = bhav.get(t)
            if px is None:
                px = yf.Ticker(t).fast_info.last_price
            if px is None or not (px == px):
                excluded["no_price"] += 1
                continue
            c.execute(
                "INSERT OR IGNORE INTO predictions "
                "(ticker, snapshot_date, alpha_score, signal, price_at_snapshot, "
                "signal_horizon_days, scan_cycle, universe_size, source) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (t, today, r.get("alpha_score"), r.get("signal"), round(float(px), 2),
                 int(r.get("horizon_days") or 21), cycle, len(universe), source),
            )
            logged += 1
        except Exception:
            excluded["error"] += 1
            continue
    c.commit()
    c.close()
    return {"snapshot_date": today, "logged": logged,
            "universe_size": len(universe),
            "scan_cycle": cycle, "cycle_age_days": cycle_age, "source": source,
            "excluded": excluded,
            "excluded_total": sum(excluded.values()),
            "coverage_pct": (round(logged / len(universe) * 100, 1)
                             if universe else 0.0),
            "note": (f"{logged} of {len(universe)} stocks logged from the "
                     f"{source} source"
                     + (f" (scan cycle {cycle})" if cycle else "")
                     + f". Excluded: {excluded['no_score']} without a score, "
                     f"{excluded['no_price']} without a price, "
                     f"{excluded['error']} on error.")}


_CLOSE_CACHE: dict = {}          # ticker -> (timestamp, Series of closes)
_CLOSE_TTL = 30 * 60             # 30 min; these are daily bars


def _closes_for(tickers: list) -> dict:
    """
    Daily close series for many tickers using ONE batched yfinance request.

    Falls back to a single-ticker fetch only for names the batch didn't return,
    so one bad symbol can't cost a round-trip for every other ticker.
    """
    now = time.time()
    out, missing = {}, []
    for t in tickers:
        hit = _CLOSE_CACHE.get(t)
        if hit and now - hit[0] < _CLOSE_TTL:
            out[t] = hit[1]
        else:
            missing.append(t)

    # Serve from the exchange's own stored history first. Once the record covers
    # the whole universe this is not an optimisation but the only workable path:
    # grading 2,400 stocks through Yahoo is thousands of throttled round-trips,
    # while bhavcopy is one query against a table we already keep.
    if missing:
        try:
            from bhavcopy import closes_history
            hist = closes_history(missing)
            for t, by_day in hist.items():
                if len(by_day) < 2:
                    continue
                idx = pd.to_datetime(sorted(by_day))
                ser = pd.Series([by_day[d] for d in sorted(by_day)], index=idx)
                out[t] = ser
                _CLOSE_CACHE[t] = (now, ser)
            missing = [t for t in missing if t not in out]
        except Exception:
            pass

    if missing:
        try:
            raw = yf.download(missing, period="1y", auto_adjust=True,
                              progress=False, group_by="column", threads=True)
            closes = raw["Close"] if "Close" in raw else raw
            if isinstance(closes, pd.Series):          # single ticker comes back flat
                closes = closes.to_frame(missing[0])
            for t in missing:
                if t in closes.columns:
                    s = closes[t].dropna()
                    if len(s):
                        out[t] = s
                        _CLOSE_CACHE[t] = (now, s)
        except Exception:
            pass

    for t in missing:                                  # anything the batch skipped
        if t not in out:
            try:
                s = yf.Ticker(t).history(period="1y", auto_adjust=True)["Close"].dropna()
                if len(s):
                    out[t] = s
                    _CLOSE_CACHE[t] = (now, s)
            except Exception:
                pass
    return out


def evaluate(min_days: int = 7) -> dict:
    """
    Grade every logged pick that is at least `min_days` old: fetch the current
    price, compute the realised forward return, compare to the Nifty benchmark,
    and aggregate an honest scorecard.
    """
    init_table()
    c = _conn()
    rows = c.execute(
        "SELECT ticker, snapshot_date, alpha_score, signal, price_at_snapshot FROM predictions"
    ).fetchall()
    c.close()
    if not rows:
        return {"status": "no predictions logged yet — run /predictions/snapshot first"}

    cutoff = datetime.now() - timedelta(days=min_days)
    # benchmark prices (cache once)
    # Same series for every horizon, so cache it rather than refetching on each
    # 3d/7d/14d/21d switch.
    nifty = _closes_for([BENCHMARK]).get(BENCHMARK)

    # Measure each pick over a FIXED min_days window, not from its log date to
    # today. Previously every row was priced at today's close, so a pick logged
    # 11 days ago reported an 11-day return whichever horizon was selected —
    # the 3d/7d/14d buttons changed only which picks were included, never the
    # holding period being measured, so all three returned near-identical
    # numbers. A horizon comparison is only meaningful if the horizon is real.
    # One batched download for every ticker in the record, cached across
    # requests. Fetching per-ticker meant 13 sequential Yahoo round-trips per
    # call (5.7s locally, worse on a throttled cloud IP) and the 3d/7d/14d/21d
    # buttons each paid it again for identical price data.
    hist_cache = _closes_for(sorted({r[0] for r in rows}))

    def _price_after(tk, d_start, n_days):
        """Close n_days after d_start, or None if that date has not arrived."""
        s = hist_cache.get(tk)
        if s is None or not len(s):
            return None
        target = d_start + timedelta(days=n_days)
        if target > datetime.now():
            return None                      # not matured at this horizon yet
        after = s[s.index >= target]
        if not len(after):
            return None                      # target lands beyond available data
        return float(after.iloc[0])

    matured, records = [], []
    for ticker, sdate, alpha, signal, p0 in rows:
        d0 = datetime.strptime(sdate, "%Y-%m-%d")
        if d0 > cutoff or not p0:
            continue
        p1 = _price_after(ticker, d0, min_days)
        if not p1 or p1 != p1:
            continue
        fwd = (p1 / p0 - 1) * 100
        # benchmark measured over the SAME fixed window
        bench = None
        if nifty is not None and len(nifty):
            past = nifty[nifty.index <= (d0 + timedelta(days=2))]
            fut  = nifty[nifty.index >= (d0 + timedelta(days=min_days))]
            if len(past) and len(fut):
                bench = (float(fut.iloc[0]) / float(past.iloc[-1]) - 1) * 100
        rec = {"ticker": ticker, "date": sdate, "alpha_score": alpha, "signal": signal,
               "forward_return_pct": round(fwd, 2),
               "benchmark_return_pct": round(bench, 2) if bench is not None else None,
               "excess_pct": round(fwd - bench, 2) if bench is not None else None,
               # the horizon actually measured, not "days since logged"
               "days_held": min_days}
        records.append(rec)
        matured.append((alpha, fwd, bench, signal))

    if not matured:
        # Diagnostic: is the history actually accumulating, or does it reset every
        # deploy? total_logged not growing past one day's universe and
        # days_of_history staying ~0 means the database is NOT persisting across
        # redeploys (ephemeral disk / no DATABASE_URL) — the real reason the track
        # record never fills, not a maturity issue.
        try:
            from db import backend_name
            db = backend_name()
        except Exception:
            db = "unknown"
        dates = sorted({r[1] for r in rows})
        oldest = dates[0] if dates else None
        days_hist = (datetime.now() - datetime.strptime(oldest, "%Y-%m-%d")).days if oldest else 0
        durable = db == "postgres" or days_hist >= min_days
        return {
            "status": f"predictions logged, but none are {min_days}+ days old yet — "
                      "check back after the holding window matures",
            "total_logged":   len(rows),
            "distinct_days":  len(dates),
            "oldest_snapshot": oldest,
            "days_of_history": days_hist,
            "db_backend":     db,
            "persistence_ok": bool(durable),
            "diagnostic": (None if durable else
                "History isn't accumulating across deploys — the database is being "
                "wiped on each redeploy. Set DATABASE_URL (Supabase Postgres) on the "
                "backend, or attach a Render persistent disk, so the track record can build."),
        }

    alphas = np.array([m[0] for m in matured if m[0] is not None], dtype=float)
    fwds   = np.array([m[1] for m in matured if m[0] is not None], dtype=float)
    buys   = [m[1] for m in matured if m[3] and "BUY" in m[3]]
    sells  = [m[1] for m in matured if m[3] and "SELL" in m[3]]
    excess = [ (m[1]-m[2]) for m in matured if m[2] is not None]

    corr = float(np.corrcoef(alphas, fwds)[0, 1]) if len(alphas) > 2 else None
    scorecard = {
        "matured_predictions": len(matured),
        "avg_forward_return_pct": round(float(np.mean([m[1] for m in matured])), 2),
        "buy_avg_return_pct":  round(float(np.mean(buys)), 2)  if buys  else None,
        "sell_avg_return_pct": round(float(np.mean(sells)), 2) if sells else None,
        "buy_minus_sell_pct":  round(float(np.mean(buys) - np.mean(sells)), 2) if buys and sells else None,
        "alpha_vs_return_correlation": round(corr, 3) if corr is not None else None,
        "avg_excess_vs_nifty_pct": round(float(np.mean(excess)), 2) if excess else None,
    }
    scorecard["by_signal"] = _by_signal(records)
    scorecard["independence"] = _independence(records, min_days)

    # The same metrics on windows that share no days. Reported ALONGSIDE the
    # full set rather than replacing it: hiding the raw count would trade one
    # distortion for another, and the interesting thing is how far the two
    # disagree. When they diverge, the overlap was doing the work.
    indep_rows = _non_overlapping(records, min_days)
    scorecard["independent_sample"] = {
        "observations": len(indep_rows),
        "by_signal": _by_signal(indep_rows) if indep_rows else None,
        "note": ("Every window here is separated from the next by at least the "
                 "full horizon, so no two share a day. This is the sample a "
                 "statistical claim would have to rest on."),
    }
    # Judge on the non-overlapping sample. Using the full one would let
    # overlapping observations vote repeatedly for the same underlying outcome,
    # which is exactly how a coin flip starts looking like an edge.
    scorecard["verdict"] = _verdict(
        buys, sells, corr, excess,
        (scorecard["independent_sample"] or {}).get("by_signal") or scorecard["by_signal"],
        scorecard["independence"])
    return {"scorecard": scorecard, "predictions": sorted(records, key=lambda r: r["date"])}


def _significance(hits: int, n: int) -> dict | None:
    """
    Is this hit rate distinguishable from a coin flip?

    A hit rate without a test invites the reader to supply their own, and people
    are famously bad at it: 54% of 13 looks like an edge, and it is seven out of
    thirteen, which is what a fair coin does constantly.

    Two-sided binomial test against p=0.5, plus a Wilson interval — Wilson
    because the textbook normal interval misbehaves at small n and near the
    extremes, which is exactly the regime this record lives in.

    Reported so it can refute rather than support. The expected answer here is
    "not significant", and that is the useful finding, not a disappointing one.
    """
    if not n or n < 2 or hits is None:
        return None
    import math
    try:
        from scipy import stats
        p = float(stats.binomtest(hits, n, 0.5).pvalue)
    except Exception:
        # Normal approximation with continuity correction — adequate for a
        # figure we expect to report as "not significant" anyway.
        z0 = (abs(hits - n / 2) - 0.5) / (math.sqrt(n) / 2)
        p = max(0.0, min(1.0, math.erfc(max(z0, 0.0) / math.sqrt(2))))

    phat = hits / n
    z = 1.959963985
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    lo, hi = max(0.0, centre - half), min(1.0, centre + half)

    sig = p < 0.05
    return {
        "hits": hits,
        "n": n,
        "p_value": round(p, 4),
        "significant_at_5pct": sig,
        "ci95_low_pct": round(lo * 100, 1),
        "ci95_high_pct": round(hi * 100, 1),
        "test": "two-sided binomial vs 50%, Wilson 95% interval",
        "plain": (
            f"{hits} correct out of {n}. A fair coin produces a result this "
            f"extreme about {p * 100:.0f}% of the time, so this is not evidence "
            f"of skill — the true rate could plausibly be anywhere from "
            f"{lo * 100:.0f}% to {hi * 100:.0f}%."
            if not sig else
            f"{hits} of {n} correct (p = {p:.3f}), which is unlikely from chance "
            f"alone. One test on one sample is still not a validated edge."),
    }


def _side_stats(rows, wants_down):
    """
    Metrics for one side of the signal.

    wants_down says which direction counts as the model being RIGHT. For a SELL
    that is a fall, so a SELL followed by a rise is a miss no matter how the
    average looks. Reporting a SELL's average return without that framing is the
    single most misleading number a signal scorecard can print: a positive
    average next to the word SELL reads as success and means the opposite.
    """
    if not rows:
        return None
    r = [x["forward_return_pct"] for x in rows]
    ex = [x["excess_pct"] for x in rows if x.get("excess_pct") is not None]
    hits = sum(1 for v in r if (v < 0 if wants_down else v > 0))
    return {
        "signals": len(r),
        "significance": _significance(hits, len(r)),
        "avg_return_pct": round(float(np.mean(r)), 2),
        "median_return_pct": round(float(np.median(r)), 2),
        # "Right" means the direction the signal called, not "went up".
        "hit_rate_pct": round(100.0 * hits / len(r), 1),
        "hit_means": "fell" if wants_down else "rose",
        "avg_excess_vs_nifty_pct": round(float(np.mean(ex)), 2) if ex else None,
        "best_pct": round(max(r), 2),
        "worst_pct": round(min(r), 2),
    }


def _by_signal(records):
    """
    BUY and SELL scored on their own terms.

    An average alone cannot distinguish 51% wins from 90% wins, and those are
    completely different signals with the same mean. The hit rate is what tells
    them apart, so it is reported beside every average rather than left for the
    reader to wonder about.
    """
    buys  = [r for r in records if r.get("signal") and "BUY" in r["signal"]]
    sells = [r for r in records if r.get("signal") and "SELL" in r["signal"]]
    return {
        "buy":  _side_stats(buys,  wants_down=False),
        "sell": _side_stats(sells, wants_down=True),
        "note": ("A BUY is right when the stock rises; a SELL is right when it "
                 "FALLS. A SELL followed by a gain is a miss, even though its "
                 "average return looks positive."),
    }


def _non_overlapping(records, horizon_days):
    """
    The subset of observations that genuinely do not share a measurement window.

    Signals are logged daily, so at a 21-day horizon consecutive observations of
    one stock overlap by 20 days. Estimating how much independence survives that
    is guesswork; selecting a set that has no overlap at all is arithmetic.

    Per stock, walk its observations in date order and keep one, then skip
    forward until a date at least `horizon_days` later. Different stocks are
    treated as independent of each other, which is itself an assumption — two
    banks on the same day are not really independent — but it is a far weaker
    one than pretending daily observations of the SAME stock are separate trades.

    This is the honest sample. It is much smaller, and that is the finding.
    """
    from collections import defaultdict
    by_t = defaultdict(list)
    for r in records:
        by_t[r["ticker"]].append(r)

    keep = []
    for t, rows in by_t.items():
        rows = sorted(rows, key=lambda r: r["date"])
        last = None
        for r in rows:
            try:
                d = datetime.strptime(r["date"], "%Y-%m-%d")
            except Exception:
                continue
            if last is None or (d - last).days >= horizon_days:
                keep.append(r)
                last = d
    return keep


def _independence(records, horizon_days):
    """
    How many of these observations are actually independent.

    Picks are snapshotted daily, so the same stock produces a new observation
    every day. At a 21-day horizon two observations logged a day apart share 20
    of their 21 days — they are very nearly the same trade counted twice. Saying
    "450 matured picks" invites the reader to hear 450 independent bets, and the
    honest figure is far smaller.

    The estimate is deliberately crude and labelled as such: per stock, the
    number of non-overlapping windows its observations could span. Precision
    here would be false — the point is the order of magnitude, which is what
    changes how much weight the result deserves.
    """
    if not records:
        return None
    from collections import defaultdict
    by_t = defaultdict(list)
    for r in records:
        by_t[r["ticker"]].append(r["date"])

    # Counted, not estimated. Earlier this was span/horizon per stock, which is
    # a plausible-looking ratio and nothing more. Building the non-overlapping
    # set and counting it gives the actual number of windows that share no days,
    # which is a figure that can be defended rather than hedged.
    eff = len(_non_overlapping(records, horizon_days))

    all_dates = sorted(r["date"] for r in records)
    return {
        "observations": len(records),
        "distinct_stocks": len(by_t),
        "horizon_days": horizon_days,
        "period": f"{all_dates[0]} to {all_dates[-1]}",
        "effective_independent_estimate": eff,
        "independent_windows": eff,
        "method": "counted non-overlapping windows per stock",
        "overlapping": len(records) > eff,
        # Phrased as an approximation on purpose. `eff` is an estimate of
        # effective independence under a crude assumption, not a count of unique
        # trades, and stating it as though it were the true sample size would
        # replace one overstatement with another.
        "note": (f"{len(records)} observed prediction windows across {len(by_t)} "
                 f"stocks ({all_dates[0]} to {all_dates[-1]}). Because picks are "
                 f"logged daily and each is measured over {horizon_days} days, "
                 f"consecutive observations of the same stock overlap heavily. "
                 f"Selecting windows that share no days at all leaves {eff} — "
                 f"counted, not estimated. Read the evidence as closer to {eff} "
                 f"than to {len(records)}. (Two different stocks on the same day "
                 f"are still counted separately, which remains an assumption.)"),
    }


# Below this many effective independent windows, no hit rate means anything.
# A 55% rate on 20 windows is 11 correct calls — entirely ordinary luck. Naming
# the threshold rather than hiding it is the point: the verdict should say WHY it
# cannot conclude, not just that it cannot.
MIN_EFFECTIVE_N = 30


def _verdict(buys, sells, corr, excess, by_signal=None, independence=None):
    """
    Say what the evidence actually supports, and why.

    The old verdict keyed off the BUY-minus-SELL spread and the alpha/return
    correlation. Both can look encouraging on a handful of overlapping windows,
    and neither answers the question a reader is asking: is there enough here to
    conclude anything at all? So the sample comes first, then direction.

    "Not enough independent evidence" and "enough evidence, no edge found" are
    completely different findings and were previously reported with the same
    sentence.
    """
    bs = by_signal or {}
    b, s_ = bs.get("buy") or {}, bs.get("sell") or {}
    eff = (independence or {}).get("effective_independent_estimate")
    obs = (independence or {}).get("observations")

    # 1. Is there enough independent evidence to say anything?
    if eff is not None and eff < MIN_EFFECTIVE_N:
        return (f"Not enough independent evidence yet. The {obs} observations here "
                f"overlap heavily — they correspond to roughly {eff} independent "
                f"windows, and below about {MIN_EFFECTIVE_N} a hit rate near 50% is "
                f"indistinguishable from chance. This is a statement about the "
                f"sample, not about the model: it has not been tested enough to "
                f"pass or fail yet.")

    b_hit, s_hit = b.get("hit_rate_pct"), s_.get("hit_rate_pct")
    b_n, s_n = b.get("signals") or 0, s_.get("signals") or 0
    parts = []
    if b_hit is not None:
        parts.append(f"BUY {b_hit:.0f}% on {b_n} signals")
    if s_hit is not None:
        parts.append(f"SELL {s_hit:.0f}% on {s_n} signals")
    detail = "; ".join(parts) or "no matured signals"

    # 2. Enough evidence OVERALL is not enough evidence about each side.
    #
    # Production caught this: with 109 BUYs and 24 SELLs the first version
    # announced "enough evidence, no edge found" — a conclusion it had no
    # standing to draw about SELL. A side with a handful of signals supports no
    # verdict at all, in either direction, and lumping it in with a
    # better-sampled side launders its uncertainty.
    thin = [f"{name} ({n})" for name, n in (("BUY", b_n), ("SELL", s_n))
            if 0 < n < MIN_EFFECTIVE_N]
    if thin:
        many = len(thin) > 1
        return (f"Partly inconclusive. {detail}. {' and '.join(thin)} "
                f"{'have' if many else 'has'} too few signals to support any "
                f"verdict — below about {MIN_EFFECTIVE_N} a hit rate is dominated "
                f"by chance, so {'those sides are' if many else 'that side is'} "
                f"neither working nor failing yet, just untested.")

    edges = [h for h in (b_hit, s_hit) if h is not None]
    if edges and all(45 <= h <= 55 for h in edges):
        return (f"Enough evidence, and no edge found. {detail}. Hit rates sit around "
                f"a coin flip, which is the ordinary result for short-horizon "
                f"prediction and the one most models quietly avoid reporting.")

    if edges and all(h > 55 for h in edges) and (corr or 0) > 0.1:
        return (f"Some edge so far. {detail}, and higher alpha scores went with "
                f"higher returns. Treat it as provisional: {eff} independent windows "
                f"is a start, not a result.")

    return (f"Mixed. {detail}. One side looks better than chance and the other does "
            f"not, which on a sample this size is more likely to be noise than a "
            f"real asymmetry between BUY and SELL.")


def start_prediction_scheduler():
    """Auto-log a snapshot of picks once a day (after market close) so the track
    record accrues on its own. INSERT OR IGNORE prevents duplicate daily rows."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        sched = BackgroundScheduler(daemon=True)
        # A backstop, not the primary trigger: the scan fires a snapshot the
        # moment it completes. These runs are cheap no-ops once the day is
        # logged, because UNIQUE(ticker, snapshot_date) makes a repeat insert
        # do nothing. Several attempts, because a single fixed time cannot know
        # when the scan will finish and a skipped day is unrecoverable.
        for _h in (16, 18, 21):
            sched.add_job(snapshot, "cron", hour=_h, minute=30,
                          id=f"snapshot_{_h}", replace_existing=True)
        sched.start()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    print(snapshot())
    print(evaluate())
