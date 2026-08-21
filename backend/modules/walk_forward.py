"""
walk_forward.py — does momentum actually work on this universe, out of sample?

Rolling windows: rank stocks on data available at each date, hold for a fixed
horizon, measure what happened next, then step forward and repeat. No date ever
sees data from after itself.

Only MOMENTUM is tested here, and that limitation is the point rather than an
omission. Momentum is computed purely from prices, so a 2022 ranking can be
rebuilt from 2022 prices exactly as it would have looked then. Quality, value
and sentiment all read CURRENT fundamentals and CURRENT news — there is no
point-in-time history for them, so walk-forward testing those would mean ranking
2022 using 2026 balance sheets. That is textbook look-ahead bias, and it is the
one thing leak_test.py currently proves this app does not do.

A real out-of-sample result on one factor is worth more than a fabricated one on
four. Testing the other three needs a point-in-time fundamentals database, and
until that exists this file will keep saying so.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def _prices(tickers, start, end):
    from portfolio_optimizer import _get_returns
    try:
        rets = _get_returns(list(tickers), start, end)
        if rets is None or rets.empty:
            return None
        return (1 + rets).cumprod()
    except Exception:
        return None


def _momentum_at(prices: pd.DataFrame, asof, lookback_days=252, skip_days=21):
    """
    12-1 momentum as it would have been computed on `asof`.

    Skips the most recent month because stocks reverse over one month and
    continue over twelve; including it blends two opposite effects. Divided by
    volatility so a wildly swinging stock does not outrank a steady one that
    gained the same amount.
    """
    window = prices.loc[:asof]
    if len(window) < lookback_days // 2:
        return {}
    end_i = max(0, len(window) - skip_days)
    start_i = max(0, end_i - lookback_days)
    if end_i - start_i < 60:
        return {}
    seg = window.iloc[start_i:end_i]
    out = {}
    for col in seg.columns:
        s = seg[col].dropna()
        if len(s) < 60 or s.iloc[0] <= 0:
            continue
        ret = float(s.iloc[-1] / s.iloc[0] - 1)
        vol = float(s.pct_change().std() * np.sqrt(252))
        if vol and vol == vol and vol > 0:
            out[col] = ret / vol
    return out


def run(tickers: list = None, start: str = "2022-01-01", horizon_days: int = 21,
        step_days: int = 21, top_n: int = 5) -> dict:
    """
    Walk forward through history, ranking on momentum and measuring what follows.

    Windows step by the full horizon, so no two test periods overlap — the same
    discipline the track record applies to live signals, for the same reason.
    """
    tickers = tickers or [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
        "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LT.NS", "KOTAKBANK.NS",
        "AXISBANK.NS", "SUNPHARMA.NS", "MARUTI.NS", "TITAN.NS", "WIPRO.NS",
    ]
    end = datetime.now().strftime("%Y-%m-%d")
    px = _prices(tickers, start, end)
    if px is None or px.empty:
        return {"error": "No price history for this universe."}

    dates = list(px.index)
    if len(dates) < 300:
        return {"error": "Not enough history to walk forward."}

    windows, first_test, last_test = [], None, None
    i = 252
    while i + horizon_days < len(dates):
        asof = dates[i]
        scores = _momentum_at(px, asof)
        if len(scores) >= 5:
            ranked = sorted(scores, key=scores.get, reverse=True)
            longs = ranked[:top_n]
            shorts = ranked[-top_n:]

            fwd = {}
            for t in set(longs + shorts):
                try:
                    a = float(px[t].iloc[i]); b = float(px[t].iloc[i + horizon_days])
                    if a > 0:
                        fwd[t] = (b / a - 1) * 100
                except Exception:
                    continue
            l = [fwd[t] for t in longs if t in fwd]
            s_ = [fwd[t] for t in shorts if t in fwd]
            if l and s_:
                windows.append({
                    "date": str(asof)[:10],
                    "top_return_pct": round(float(np.mean(l)), 3),
                    "bottom_return_pct": round(float(np.mean(s_)), 3),
                    "spread_pct": round(float(np.mean(l) - np.mean(s_)), 3),
                })
                first_test = first_test or str(asof)[:10]
                last_test = str(asof)[:10]
        i += step_days

    if len(windows) < 5:
        return {"error": f"Only {len(windows)} usable windows — too few to report."}

    spreads = np.array([w["spread_pct"] for w in windows], dtype=float)
    wins = int((spreads > 0).sum())
    n = len(spreads)

    # Significance on the spread, using the same test the track record uses.
    try:
        from prediction_tracker import _significance
        sig = _significance(wins, n)
    except Exception:
        sig = None

    mean_sp = float(spreads.mean())
    # Information ratio: mean spread per unit of its own variability, annualised
    # by the number of non-overlapping periods in a year.
    ir = None
    if spreads.std() > 0:
        per_year = 252 / max(1, horizon_days)
        ir = round(float(mean_sp / spreads.std() * np.sqrt(per_year)), 2)

    if sig and sig.get("significant_at_5pct") and mean_sp > 0:
        verdict = (f"Momentum separated winners from losers on this universe: the "
                   f"top {top_n} beat the bottom {top_n} by {mean_sp:.2f}% per "
                   f"{horizon_days}-day window across {n} non-overlapping tests "
                   f"(p = {sig['p_value']:.3f}). One universe and one factor — not "
                   f"a validated strategy.")
    else:
        verdict = (f"No demonstrated edge. The top {top_n} beat the bottom {top_n} "
                   f"by {mean_sp:.2f}% per window across {n} tests, which "
                   f"{'a coin flip produces about ' + format(sig['p_value']*100, '.0f') + '% of the time' if sig else 'is not statistically distinguishable from chance'}. "
                   f"That is the ordinary result for short-horizon prediction.")

    return {
        "factor": "momentum",
        "universe_size": len(tickers),
        "horizon_days": horizon_days,
        "windows": n,
        "period": f"{first_test} to {last_test}",
        "mean_spread_pct": round(mean_sp, 3),
        "median_spread_pct": round(float(np.median(spreads)), 3),
        "win_rate_pct": round(100 * wins / n, 1),
        "information_ratio": ir,
        "best_window_pct": round(float(spreads.max()), 2),
        "worst_window_pct": round(float(spreads.min()), 2),
        "significance": sig,
        "verdict": verdict,
        "detail": windows[-12:],
        "why_only_momentum": (
            "Momentum is computed purely from prices, so a past ranking can be "
            "rebuilt exactly as it looked then. Quality, value and sentiment read "
            "CURRENT fundamentals and news — testing them this way would rank 2022 "
            "using 2026 balance sheets, which is the look-ahead bias this app is "
            "otherwise verified not to have."),
        "limits": ("No transaction costs, no liquidity limit, and a fixed universe "
                   "of currently-listed large caps — so survivorship applies here "
                   "too. Treat the spread as an upper bound."),
    }
