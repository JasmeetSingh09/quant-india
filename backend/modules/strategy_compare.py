"""
strategy_compare.py — three construction methods on the same portfolio, same
period, same costs.

The comparison exists to make a choice harder, not easier. Ranking three
strategies by historical return is the single most reliable way to pick the one
that will disappoint you next: the highest past return is usually the one that
took the most risk, traded the most, or got luckiest, and none of those repeat
on demand.

So the table reports return alongside the things that explain it — volatility,
drawdown, turnover, the cost of that turnover — and refuses to name a winner.
The "best" column is deliberately absent.

Every method is measured over the SAME window with the SAME cost model, because
a comparison where the methods differ in more than one respect measures nothing.
"""

from model_config import RISK_FREE_RATE as _RF

from datetime import datetime, timedelta

import numpy as np


# Round-trip cost of moving 100% of the book, Indian delivery rates.
COST_PER_UNIT_TURNOVER = (2 * 0.001) + (2 * 0.0005) + 0.001 + 0.00015


def _metrics(daily, initial_value: float, turnover: float, periods_per_year: int = 252):
    """Standard risk-adjusted measures from a daily return series."""
    if daily is None or len(daily) < 30:
        return None
    r = np.asarray(daily, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 30:
        return None

    total = float(np.prod(1 + r) - 1)
    years = len(r) / periods_per_year
    cagr = float((1 + total) ** (1 / years) - 1) if years > 0 and total > -1 else None
    vol = float(r.std() * np.sqrt(periods_per_year))
    downside = r[r < 0]
    dvol = float(downside.std() * np.sqrt(periods_per_year)) if len(downside) > 1 else None

    # Prepend the starting value so a fall in the FIRST period counts. Without
    # it the opening point is its own peak and a first-period loss vanishes.
    curve = np.concatenate([[1.0], np.cumprod(1 + r)])
    max_dd = float((curve / np.maximum.accumulate(curve) - 1).min())

    # 6.5% is the RBI repo proxy used elsewhere in the app.
    rf = _RF
    sharpe = round((cagr - rf) / vol, 3) if (cagr is not None and vol > 0) else None
    sortino = round((cagr - rf) / dvol, 3) if (cagr is not None and dvol) else None
    calmar = round(cagr / abs(max_dd), 3) if (cagr is not None and max_dd < 0) else None

    cost = turnover * COST_PER_UNIT_TURNOVER
    return {
        "total_return_pct": round(total * 100, 2),
        "cagr_pct": round(cagr * 100, 2) if cagr is not None else None,
        "volatility_pct": round(vol * 100, 2),
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_drawdown_pct": round(max_dd * 100, 2),
        "hit_rate_pct": round(float((r > 0).mean()) * 100, 1),
        "turnover_pct": round(turnover * 100, 1),
        "cost_of_turnover_pct": round(cost * 100, 3),
        "days": len(r),
    }


def _weighted_daily(returns, weights: dict, cols: list):
    w = np.array([weights.get(c, 0.0) for c in cols], dtype=float)
    if w.sum() <= 0:
        return None
    w = w / w.sum()
    return (returns[cols].values * w).sum(axis=1)


def compare(tickers: list, start: str = None, end: str = None,
            initial_value: float = 100000, current_weights: dict = None) -> dict:
    """
    Equal-weight vs mean-variance vs Black-Litterman, plus the user's own
    weights when supplied, measured identically.
    """
    tickers = [t.strip().upper() for t in (tickers or []) if t]
    if len(tickers) < 3:
        return {"error": "Need at least 3 tickers to compare construction methods."}

    end = end or datetime.now().strftime("%Y-%m-%d")
    start = start or (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    try:
        from portfolio_optimizer import _get_returns
        rets = _get_returns(tickers, start, end)
    except Exception as e:
        return {"error": f"Could not load returns: {type(e).__name__}"}
    if rets is None or rets.empty:
        return {"error": "No return history for this universe."}

    cols = [t for t in tickers if t in rets.columns]
    if len(cols) < 3:
        return {"error": f"Only {len(cols)} tickers had data."}
    rets = rets[cols].dropna()
    if len(rets) < 60:
        return {"error": "Not enough overlapping history."}

    n = len(cols)
    strategies = {}

    # 1. Equal weight — the benchmark any method has to beat to justify itself.
    eq = {c: 100.0 / n for c in cols}
    strategies["Equal weight"] = {
        "weights": eq,
        "turnover": 0.0,
        "why": ("The honest baseline. It needs no estimates at all, which is "
                "exactly why it is hard to beat — every other method here is "
                "betting that its estimates are good enough to pay for "
                "themselves."),
    }

    # 2. Mean-variance, capped so it cannot produce a corner solution.
    try:
        from portfolio_optimizer import mean_variance_optimize
        mv = mean_variance_optimize(cols, target="max_sharpe", max_weight=0.35,
                                    period_months=24)
        if "error" not in mv and mv.get("optimal_pct"):
            w = mv["optimal_pct"]
            turn = sum(abs(w.get(c, 0) - eq[c]) for c in cols) / 200
            strategies["Mean-variance"] = {
                "weights": w, "turnover": turn,
                "why": ("Maximises Sharpe using historical returns and a "
                        "Ledoit-Wolf covariance. Capped at 35% per holding, "
                        "because uncapped it puts everything in one stock."),
            }
    except Exception:
        pass

    # 3. Black-Litterman from market equilibrium, no user views.
    try:
        from portfolio_optimizer import black_litterman_optimize
        bl = black_litterman_optimize(cols, sentiment_views={})
        # This optimiser names its weights bl_pct, not optimal_pct — checking
        # only the common names silently dropped Black-Litterman from the
        # comparison, which looked like the method failing rather than a key
        # mismatch.
        w = bl.get("bl_pct") or bl.get("optimal_pct") or bl.get("weights_pct")
        if isinstance(w, dict) and w:
            turn = sum(abs(w.get(c, 0) - eq[c]) for c in cols) / 200
            strategies["Black-Litterman"] = {
                "weights": w, "turnover": turn,
                "why": ("Starts from the returns the market's own weights imply, "
                        "then shifts toward any views supplied. With no views it "
                        "stays near the market portfolio — which is the point: it "
                        "only moves as far as your conviction justifies."),
            }
    except Exception:
        pass

    # 4. The user's own weights, if they have any.
    if current_weights:
        cw = {c: float(current_weights.get(c, 0)) for c in cols}
        if sum(cw.values()) > 0:
            turn = sum(abs(cw.get(c, 0) - eq[c]) for c in cols) / 200
            strategies["Your portfolio"] = {
                "weights": cw, "turnover": turn,
                "why": "What you currently hold, measured the same way.",
            }

    rows = []
    for name, spec in strategies.items():
        daily = _weighted_daily(rets, spec["weights"], cols)
        m = _metrics(daily, initial_value, spec["turnover"])
        if not m:
            continue
        rows.append({"strategy": name, "why": spec["why"],
                     "weights_pct": {k: round(v, 2) for k, v in spec["weights"].items()},
                     **m})

    if not rows:
        return {"error": "No strategy could be measured on this data."}

    # Benchmark excess, against the same window.
    bench = None
    try:
        from portfolio_optimizer import _get_returns as _gr
        nifty = _gr(["^NSEI"], start, end)
        if nifty is not None and "^NSEI" in nifty.columns and len(nifty) > 30:
            nb = _metrics(nifty["^NSEI"].values, initial_value, 0.0)
            if nb:
                bench = nb
                for r in rows:
                    if r.get("cagr_pct") is not None and nb.get("cagr_pct") is not None:
                        r["excess_vs_nifty_pct"] = round(r["cagr_pct"] - nb["cagr_pct"], 2)
    except Exception:
        bench = None

    best_ret = max(rows, key=lambda r: r.get("cagr_pct") or -1e9)
    best_sharpe = max(rows, key=lambda r: r.get("sharpe") or -1e9)
    disagree = best_ret["strategy"] != best_sharpe["strategy"]

    return {
        "period": f"{start} to {end}",
        "universe_size": len(cols),
        "strategies": rows,
        "benchmark": bench,
        "highest_return": best_ret["strategy"],
        "highest_sharpe": best_sharpe["strategy"],
        "return_and_risk_disagree": disagree,
        "no_winner_named": (
            "This table deliberately does not pick a best strategy. The highest "
            "past return is usually the one that took the most risk, traded the "
            "most, or was luckiest — none of which repeat on demand."
            + (f" Here they already disagree: {best_ret['strategy']} returned most "
               f"while {best_sharpe['strategy']} earned it with less risk."
               if disagree else "")),
        "limits": (
            "One period, one universe, one set of estimates. Every method is "
            "measured over the same window with the same cost model, so the "
            "differences are the method — but a different window can reorder "
            "them, and frequently does. Survivorship applies: these are all "
            "companies that still exist."),
    }
