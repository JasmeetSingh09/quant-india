"""
momentum_backtest.py — an HONEST walk-forward backtest of the 12-1 momentum
factor on an NSE universe, benchmarked against the Nifty.

Why this is defensible (the point of the whole exercise):
  * NO LOOK-AHEAD. At each month-end t the signal uses only prices up to t
    (12-1 momentum = return from t-12 to t-1 months, the last month skipped for
    short-term reversal). The position is then held over month t+1. It is a
    genuine out-of-sample walk-forward — every trade is decided before the
    return it earns.
  * COSTS INCLUDED. Turnover at each rebalance is charged a round-trip cost
    (brokerage + slippage + STT), so results are net, not gross.
  * ONE FACTOR, honestly. This tests momentum alone — a pure price signal with
    no fundamentals/sentiment, so there is no point-in-time data problem. We do
    NOT dress it up as the full alpha model.
  * BENCHMARKED + significance. Reported against Nifty buy-and-hold with a
    t-stat on the monthly excess return, and the result is stated even if the
    edge is zero or negative.
"""

import numpy as np
import pandas as pd
from datetime import datetime

# A liquid large/mid-cap NSE universe (kept static — note the survivorship
# caveat in the output; today's listed names bias results slightly upward).
DEFAULT_UNIVERSE = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS","ITC.NS","SBIN.NS",
    "LT.NS","MARUTI.NS","SUNPHARMA.NS","TITAN.NS","TATASTEEL.NS","AXISBANK.NS",
    "KOTAKBANK.NS","BAJFINANCE.NS","HINDUNILVR.NS","ASIANPAINT.NS","WIPRO.NS",
    "HCLTECH.NS","ULTRACEMCO.NS","NESTLEIND.NS","POWERGRID.NS","NTPC.NS","ONGC.NS",
    "M&M.NS","TECHM.NS","BAJAJFINSV.NS","ADANIPORTS.NS","COALINDIA.NS","GRASIM.NS",
    "JSWSTEEL.NS","DRREDDY.NS","CIPLA.NS","EICHERMOT.NS","BRITANNIA.NS","DIVISLAB.NS",
    "HEROMOTOCO.NS","BPCL.NS","TATAMOTORS.NS","INDUSINDBK.NS",
]


def _annualised(monthly: pd.Series) -> dict:
    """Annualised performance stats from a series of MONTHLY returns."""
    if len(monthly) < 2:
        return {}
    mean_m = float(monthly.mean())
    std_m  = float(monthly.std(ddof=1))
    ann_ret = (1 + mean_m) ** 12 - 1
    ann_vol = std_m * np.sqrt(12)
    rf_m = 0.065 / 12
    sharpe = ((mean_m - rf_m) / std_m * np.sqrt(12)) if std_m > 0 else 0.0
    downside = monthly[monthly < 0]
    dstd = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sortino = ((mean_m - rf_m) / dstd * np.sqrt(12)) if dstd > 0 else 0.0
    cum = (1 + monthly).cumprod()
    peak = cum.cummax()
    max_dd = float(((cum - peak) / peak).min())
    return {
        "cagr_pct":      round(ann_ret * 100, 2),
        "vol_pct":       round(ann_vol * 100, 2),
        "sharpe":        round(sharpe, 3),
        "sortino":       round(sortino, 3),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "hit_rate_pct":  round(float((monthly > 0).mean()) * 100, 1),
        "n_months":      int(len(monthly)),
    }


def momentum_backtest(
    universe: list = None,
    start: str = "2019-01-01",
    end: str = None,
    top_fraction: float = 0.2,
    lookback_months: int = 12,
    skip_months: int = 1,
    cost_roundtrip_pct: float = 0.4,
) -> dict:
    """
    Walk-forward long-only 12-1 momentum, monthly rebalanced, vs Nifty.

    top_fraction        — hold the top X of the universe by momentum (0.2 = top 20%)
    cost_roundtrip_pct  — round-trip transaction cost per name traded (%)
    """
    import yfinance as yf
    universe = universe or DEFAULT_UNIVERSE
    end = end or datetime.now().strftime("%Y-%m-%d")

    # Download once, resample to month-end closes.
    try:
        raw = yf.download(universe + ["^NSEI"], start=start, end=end,
                          progress=False, auto_adjust=True, group_by="ticker",
                          threads=True)
    except Exception as e:
        return {"error": f"price download failed: {e}"}

    monthly = {}
    for t in universe + ["^NSEI"]:
        try:
            s = raw[t]["Close"].dropna()
            if len(s) > lookback_months * 21:
                monthly[t] = s.resample("ME").last()
        except Exception:
            pass
    if "^NSEI" not in monthly or len(monthly) < 6:
        return {"error": "insufficient price data for a backtest"}

    prices = pd.DataFrame(monthly).dropna(how="all")
    nifty  = prices["^NSEI"]
    stocks = prices.drop(columns=["^NSEI"])

    dates = stocks.index
    L, K = lookback_months, skip_months
    cost = cost_roundtrip_pct / 100.0

    strat_returns, bench_returns, eq_dates = [], [], []
    prev_basket = set()
    holdings_log = []

    # Need L months of history to form the first signal; hold the following month.
    for i in range(L, len(dates) - 1):
        t = dates[i]
        # 12-1 momentum: return from (i-L) to (i-K), skipping the last K months.
        past = stocks.iloc[i - L]
        recent = stocks.iloc[i - K]
        mom = (recent / past - 1).dropna()
        if len(mom) < 5:
            continue
        n_hold = max(1, int(round(len(mom) * top_fraction)))
        basket = list(mom.sort_values(ascending=False).head(n_hold).index)

        # Forward (held) month return, equal-weight.
        fwd = (stocks.iloc[i + 1][basket] / stocks.iloc[i][basket] - 1).dropna()
        if len(fwd) == 0:
            continue
        gross = float(fwd.mean())

        # Turnover cost: names entering or leaving the basket pay the round trip.
        turnover = len(set(basket).symmetric_difference(prev_basket)) / (2 * max(1, len(basket)))
        net = gross - turnover * cost
        prev_basket = set(basket)

        strat_returns.append(net)
        bench_returns.append(float(nifty.iloc[i + 1] / nifty.iloc[i] - 1))
        eq_dates.append(dates[i + 1].strftime("%Y-%m"))
        holdings_log.append([b.replace(".NS", "") for b in basket])

    if len(strat_returns) < 6:
        return {"error": "not enough rebalances to evaluate"}

    strat = pd.Series(strat_returns)
    bench = pd.Series(bench_returns)
    excess = strat - bench

    # t-stat on the mean monthly excess return (is the edge distinguishable from 0?)
    t_stat = float(excess.mean() / (excess.std(ddof=1) / np.sqrt(len(excess)))) if excess.std(ddof=1) > 0 else 0.0

    strat_curve = (1 + strat).cumprod()
    bench_curve = (1 + bench).cumprod()
    equity = [{"date": d, "strategy": round(float(s), 4), "nifty": round(float(b), 4)}
              for d, s, b in zip(eq_dates, strat_curve, bench_curve)]

    s_stats = _annualised(strat)
    b_stats = _annualised(bench)

    return {
        "strategy":  "12-1 momentum, long top {:.0%}, monthly rebalanced".format(top_fraction),
        "universe_size": len(stocks.columns),
        "period":    f"{eq_dates[0]} to {eq_dates[-1]}",
        "costs_included": True,
        "cost_roundtrip_pct": cost_roundtrip_pct,
        "strategy_stats":  s_stats,
        "benchmark_stats": b_stats,
        "excess_cagr_pct": round(s_stats["cagr_pct"] - b_stats["cagr_pct"], 2),
        "monthly_excess_mean_pct": round(float(excess.mean()) * 100, 3),
        "t_stat_excess":   round(t_stat, 2),
        "significant_5pct": bool(abs(t_stat) > 1.96),
        "equity_curve":    equity,
        "final_holdings":  holdings_log[-1],
        "verdict": _verdict(s_stats, b_stats, t_stat),
        "caveats": [
            "Survivorship bias: the universe is today's listed names, which biases returns up.",
            "Single factor (momentum only) — not the full alpha model.",
            "Costs are a turnover approximation, not a live fill simulation.",
            "Monthly rebalance; no intra-month risk management.",
        ],
    }


def _verdict(s: dict, b: dict, t: float) -> str:
    edge = s.get("cagr_pct", 0) - b.get("cagr_pct", 0)
    sig = abs(t) > 1.96
    if edge > 0 and sig:
        return (f"Momentum beat the Nifty by {edge:.1f}%/yr with a Sharpe of "
                f"{s.get('sharpe')} vs {b.get('sharpe')}, and the monthly excess is "
                f"statistically significant (t={t:.2f}). A real, if modest, edge.")
    if edge > 0:
        return (f"Momentum edged the Nifty by {edge:.1f}%/yr (Sharpe {s.get('sharpe')} "
                f"vs {b.get('sharpe')}), but the excess is NOT significant (t={t:.2f}) — "
                f"consistent with luck over this sample.")
    return (f"Momentum did NOT beat the Nifty here ({edge:.1f}%/yr, t={t:.2f}). "
            f"An honest negative result — the factor carried no net edge in this "
            f"universe/period after costs.")


if __name__ == "__main__":
    import json, warnings
    warnings.filterwarnings("ignore")
    r = momentum_backtest(start="2019-01-01")
    if "error" in r:
        print("ERROR:", r["error"])
    else:
        print(json.dumps({k: v for k, v in r.items()
                          if k not in ("equity_curve", "final_holdings")}, indent=2))
