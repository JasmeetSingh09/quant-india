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
import pandas as pd
import yfinance as yf

_DB_PATH = Path(os.environ.get("QUANT_DATA_DIR", str(Path(__file__).parent.parent))) / "quant_platform.db"
BENCHMARK = "^NSEI"


def _conn():
    from db import get_conn      # Postgres (Supabase) if DATABASE_URL set, else SQLite
    return get_conn()


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


def snapshot(universe: list = None) -> dict:
    """
    Log today's alpha picks. Call this daily (or on demand). Records each ticker's
    alpha score, signal, and current price, so we can grade it later.
    """
    init_table()
    from alpha_model import compute_alpha_score, TOP_PICKS_UNIVERSE
    universe = universe or TOP_PICKS_UNIVERSE
    today = datetime.now().strftime("%Y-%m-%d")

    logged = 0
    c = _conn()
    for t in universe:
        try:
            r = compute_alpha_score(t)
            price = r.get("factors", {})  # price fetched separately below
            px = yf.Ticker(t).fast_info.last_price
            if px is None or not (px == px):
                continue
            c.execute(
                "INSERT OR IGNORE INTO predictions "
                "(ticker, snapshot_date, alpha_score, signal, price_at_snapshot) "
                "VALUES (?,?,?,?,?)",
                (t, today, r.get("alpha_score"), r.get("signal"), round(float(px), 2)),
            )
            logged += 1
        except Exception:
            continue
    c.commit()
    c.close()
    return {"snapshot_date": today, "logged": logged, "universe_size": len(universe)}


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
        "verdict": _verdict(buys, sells, corr, excess),
    }
    scorecard["by_signal"] = _by_signal(records)
    scorecard["independence"] = _independence(records, min_days)
    return {"scorecard": scorecard, "predictions": sorted(records, key=lambda r: r["date"])}


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

    eff = 0
    for t, dates in by_t.items():
        ds = sorted(datetime.strptime(d, "%Y-%m-%d") for d in dates)
        span = (ds[-1] - ds[0]).days
        eff += max(1, int(span / max(1, horizon_days)) + 1) if len(ds) > 1 else 1
    eff = min(eff, len(records))

    all_dates = sorted(r["date"] for r in records)
    return {
        "observations": len(records),
        "distinct_stocks": len(by_t),
        "horizon_days": horizon_days,
        "period": f"{all_dates[0]} to {all_dates[-1]}",
        "effective_independent_estimate": eff,
        "overlapping": len(records) > eff,
        # Phrased as an approximation on purpose. `eff` is an estimate of
        # effective independence under a crude assumption, not a count of unique
        # trades, and stating it as though it were the true sample size would
        # replace one overstatement with another.
        "note": (f"{len(records)} observed prediction windows across {len(by_t)} "
                 f"stocks ({all_dates[0]} to {all_dates[-1]}). Because picks are "
                 f"logged daily and each is measured over {horizon_days} days, "
                 f"consecutive observations of the same stock overlap heavily — "
                 f"they correspond to roughly {eff} independent windows under this "
                 f"approximation. Read the evidence as closer to {eff} than to "
                 f"{len(records)}."),
    }


def _verdict(buys, sells, corr, excess):
    if buys and sells and np.mean(buys) > np.mean(sells) and (corr or 0) > 0.1:
        return ("Signal shows some edge so far: BUYs outperformed SELLs and higher "
                "alpha correlated with higher return. Keep collecting data — small "
                "samples are noisy.")
    return ("No reliable edge yet: the signal is not clearly separating winners from "
            "losers (consistent with returns being hard to predict). This is the "
            "honest, expected result on a small/short sample.")


def start_prediction_scheduler():
    """Auto-log a snapshot of picks once a day (after market close) so the track
    record accrues on its own. INSERT OR IGNORE prevents duplicate daily rows."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        sched = BackgroundScheduler(daemon=True)
        sched.add_job(snapshot, "cron", hour=16, minute=30)  # ~after NSE close
        sched.start()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    print(snapshot())
    print(evaluate())
