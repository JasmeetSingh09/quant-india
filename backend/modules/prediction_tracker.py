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

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import yfinance as yf

_DB_PATH = Path(os.environ.get("QUANT_DATA_DIR", str(Path(__file__).parent.parent))) / "quant_platform.db"
BENCHMARK = "^NSEI"


def _conn():
    return sqlite3.connect(_DB_PATH)


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
    try:
        nifty = yf.download(BENCHMARK, period="6mo", auto_adjust=True,
                            progress=False)["Close"].squeeze().dropna()
    except Exception:
        nifty = None

    matured, records = [], []
    for ticker, sdate, alpha, signal, p0 in rows:
        d0 = datetime.strptime(sdate, "%Y-%m-%d")
        if d0 > cutoff or not p0:
            continue
        try:
            p1 = float(yf.Ticker(ticker).fast_info.last_price)
        except Exception:
            continue
        if not p1 or p1 != p1:
            continue
        fwd = (p1 / p0 - 1) * 100
        # benchmark return over the same window
        bench = None
        if nifty is not None and len(nifty):
            past = nifty[nifty.index <= (d0 + timedelta(days=2))]
            if len(past):
                bench = (float(nifty.iloc[-1]) / float(past.iloc[-1]) - 1) * 100
        rec = {"ticker": ticker, "date": sdate, "alpha_score": alpha, "signal": signal,
               "forward_return_pct": round(fwd, 2),
               "benchmark_return_pct": round(bench, 2) if bench is not None else None,
               "excess_pct": round(fwd - bench, 2) if bench is not None else None,
               "days_held": (datetime.now() - d0).days}
        records.append(rec)
        matured.append((alpha, fwd, bench, signal))

    if not matured:
        return {"status": f"predictions logged, but none are {min_days}+ days old yet — "
                          "check back after the holding window matures",
                "total_logged": len(rows)}

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
    return {"scorecard": scorecard, "predictions": sorted(records, key=lambda r: r["date"])}


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
