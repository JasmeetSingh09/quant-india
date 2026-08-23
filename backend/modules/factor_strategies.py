"""
factor_strategies.py — the factor strategies that can honestly be backtested,
and an explicit list of the ones that cannot.

A strategy lab comparing Value, Quality, Growth, Momentum and Low Risk would be
the natural thing to build. Four of those five cannot be built here without
lying. Quality, growth and value read the CURRENT balance sheet, and sentiment
reads current news, so ranking 2019 by them would rank 2019 using 2026
fundamentals — the look-ahead bias this app is independently verified not to
have. The resulting equity curve would look like evidence and be an artefact.

Momentum and low volatility are different: both are computed purely from
prices, so a past ranking can be rebuilt exactly as it looked at the time.
Those two get real walk-forward backtests with costs. The other four get a row
saying why they are absent.

Leaving them out silently would have been the easy version, and it would have
implied the lab tested everything worth testing. Naming the gap is the point.

No winner is named. The two strategies here have different risk, different
turnover and different cost, and picking the higher number would be picking
whichever took more risk in this particular window.
"""

from datetime import datetime


CANNOT_BACKTEST = {
    "quality": ("Reads the current balance sheet. Ranking 2019 by it would use "
                "2026 fundamentals, which is look-ahead bias."),
    "growth": ("Reads current revenue and earnings. Same problem: the 2019 "
               "ranking would be built from figures published years later."),
    "value": ("Compares current price to current fundamentals. The fundamentals "
              "half cannot be rewound, so a historical ranking is not "
              "reconstructible."),
    "sentiment": ("Reads current news. Historical headlines for the whole "
                  "universe were never archived, so a past ranking can only be "
                  "rebuilt as it looks now, which is not the same thing."),
}

PLAIN = {
    "momentum": "Hold the strongest recent performers",
    "low_risk": "Hold the calmest stocks",
    "quality": "Hold the most profitable, financially healthy companies",
    "growth": "Hold the fastest-growing companies",
    "value": "Hold the cheapest stocks against peers",
    "sentiment": "Hold the stocks with the most positive news",
}


def _stats_from(res: dict, name: str, plain: str, note: str = None) -> dict:
    """Pull the shared shape out of whichever backtest produced it."""
    s = res.get("strategy_stats") or {}
    b = res.get("benchmark_stats") or {}
    return {
        "factor": name,
        "plain": plain,
        "testable": True,
        "cagr_pct": s.get("cagr_pct"),
        "volatility_pct": s.get("volatility_pct") or s.get("vol_pct"),
        "sharpe": s.get("sharpe"),
        "max_drawdown_pct": s.get("max_drawdown_pct"),
        "months": s.get("n_months"),
        "excess_vs_benchmark_pct": res.get("excess_cagr_pct"),
        "benchmark_cagr_pct": b.get("cagr_pct"),
        "note": note or res.get("verdict") or res.get("interpretation"),
    }


def compare(start: str = "2019-01-01", fraction: float = 0.2,
            universe: list = None) -> dict:
    """
    Run every factor strategy that can be tested without look-ahead, and list
    the ones that cannot alongside the reason.
    """
    rows, errors = [], {}

    try:
        from momentum_backtest import momentum_backtest
        m = momentum_backtest(universe=universe, start=start,
                              top_fraction=fraction)
        if "error" in m:
            errors["momentum"] = m["error"]
        else:
            rows.append(_stats_from(m, "momentum", PLAIN["momentum"]))
    except Exception as e:
        errors["momentum"] = f"{type(e).__name__}"

    try:
        from momentum_backtest import low_vol_backtest
        lv = low_vol_backtest(universe=universe, start=start,
                              bottom_fraction=fraction)
        if "error" in lv:
            errors["low_risk"] = lv["error"]
        else:
            rows.append(_stats_from(lv, "low_risk", PLAIN["low_risk"]))
    except Exception as e:
        errors["low_risk"] = f"{type(e).__name__}"

    blocked = [{"factor": f, "plain": PLAIN.get(f, f), "testable": False,
                "why": why} for f, why in CANNOT_BACKTEST.items()]

    benchmark = None
    for r in rows:
        if r.get("benchmark_cagr_pct") is not None:
            benchmark = {"name": "Nifty 50", "cagr_pct": r["benchmark_cagr_pct"]}
            break

    # An excess of 0.01 points over seven years is not beating anything, and
    # counting it as a win would let a strategy that matched the index be
    # reported as having outperformed. A full point of annual CAGR is the least
    # that survives rounding, cost assumptions and a different start date.
    MEANINGFUL_EXCESS_PCT = 1.0
    beat = [r for r in rows
            if (r.get("excess_vs_benchmark_pct") or 0) >= MEANINGFUL_EXCESS_PCT]
    matched = [r for r in rows
               if abs(r.get("excess_vs_benchmark_pct") or 0) < MEANINGFUL_EXCESS_PCT]
    for r in rows:
        ex = r.get("excess_vs_benchmark_pct")
        r["vs_benchmark"] = (
            "matched" if ex is None or abs(ex) < MEANINGFUL_EXCESS_PCT
            else ("ahead" if ex > 0 else "behind"))

    return {
        "period_start": start,
        "fraction": fraction,
        "tested": rows,
        "cannot_backtest": blocked,
        "errors": errors,
        "benchmark": benchmark,
        "counts": {"tested": len(rows), "blocked": len(blocked),
                   "beat_benchmark": len(beat), "matched_benchmark": len(matched)},
        "meaningful_excess_pct": MEANINGFUL_EXCESS_PCT,
        "why_matched": (
            f"A strategy within {MEANINGFUL_EXCESS_PCT:.0f} point of annual CAGR "
            f"of the index is reported as having matched it, not beaten it. An "
            f"excess of a hundredth of a point does not survive rounding, a "
            f"different cost assumption or a different start date."),
        "no_winner_named": (
            "No best strategy is named. These two carry different risk, "
            "different turnover and different cost, so the higher number "
            "belongs to whichever took more risk in this particular window "
            "rather than to whichever is better."),
        "why_only_two": (
            f"Only {len(rows)} of the six factors can be backtested honestly. "
            f"The other {len(blocked)} read current fundamentals or current "
            f"news, so a historical ranking would be built from information "
            f"that did not exist at the time. Their curves would look like "
            f"evidence and be artefacts, so they are named here rather than "
            f"quietly left out — leaving them out would imply the lab tested "
            f"everything worth testing."),
        "limits": (
            "Costs are charged at a flat round-trip rate and slippage is not "
            "modelled separately. Survivorship applies: the universe is "
            "currently-listed names, so companies that failed are missing and "
            "every strategy here looks better than it would have been. One "
            "period, one universe."),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
