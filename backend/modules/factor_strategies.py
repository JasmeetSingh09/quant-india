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


def universe_sensitivity(start: str = "2019-01-01",
                         fraction: float = 0.2) -> dict:
    """
    How much of momentum's apparent edge is a choice rather than a finding.

    This is the most important number the backtest can produce, and it is not
    a return. Run the same 12-1 momentum strategy over the same period and the
    excess return against the Nifty ranges from roughly nothing to more than
    twenty points a year, depending entirely on two decisions that have nothing
    to do with momentum:

      which universe you trade
      whether the universe is chosen with information from the future

    Widening from 40 large caps to ~200 names multiplies the apparent edge.
    Applying a point-in-time liquidity screen — so 2019 is traded using who was
    liquid in 2019 rather than who is liquid now — roughly halves it, then
    halves it again as the screen tightens. The drawdown gets WORSE at every
    step, which is the tell: the flattering configurations were quietly picking
    survivors.

    None of the remaining excess can be called an edge. Every configuration
    here still holds only companies that exist today; the ones that went to
    zero are absent from the data source entirely, and that cannot be corrected
    with the data this project has.
    """
    from momentum_backtest import (momentum_backtest, DEFAULT_UNIVERSE,
                                   BROAD_UNIVERSE)
    rows = []
    configs = [
        ("40 large caps, no screen", DEFAULT_UNIVERSE, None),
        ("~200 names, no screen", BROAD_UNIVERSE, None),
        ("~200 names, point-in-time top 100", BROAD_UNIVERSE, 100),
        ("~200 names, point-in-time top 50", BROAD_UNIVERSE, 50),
    ]
    for label, uni, pit in configs:
        try:
            r = momentum_backtest(universe=uni, start=start,
                                  top_fraction=fraction, pit_universe_size=pit)
        except Exception as e:
            rows.append({"config": label, "error": type(e).__name__})
            continue
        if "error" in r:
            rows.append({"config": label, "error": r["error"]})
            continue
        st = r["strategy_stats"]
        rows.append({
            "config": label,
            "universe_size": r.get("universe_size"),
            "point_in_time": bool(r.get("point_in_time_universe")),
            "cagr_pct": st["cagr_pct"],
            "sharpe": st["sharpe"],
            "max_drawdown_pct": st["max_drawdown_pct"],
            "hit_rate_pct": st["hit_rate_pct"],
            "excess_vs_nifty_pct": r.get("excess_cagr_pct"),
        })

    good = [x for x in rows if "excess_vs_nifty_pct" in x
            and x["excess_vs_nifty_pct"] is not None]
    lo = min((x["excess_vs_nifty_pct"] for x in good), default=None)
    hi = max((x["excess_vs_nifty_pct"] for x in good), default=None)

    return {
        "configurations": rows,
        "excess_range_pct": ([lo, hi] if lo is not None else None),
        "headline": (
            f"The same momentum strategy over the same years produces anywhere "
            f"from {lo:+.1f} to {hi:+.1f} points of annual excess return, "
            f"depending only on which universe is traded and whether that "
            f"universe was chosen using information from the future. The spread "
            f"between those numbers is larger than any edge being claimed, so "
            f"the configuration is doing more work than the factor."
            if lo is not None else
            "Sensitivity could not be computed."),
        "what_it_means": (
            "A backtest result that moves this much with a methodology choice "
            "is a measurement of the choice. The apparent edge is largest "
            "exactly where survivorship bias is worst — a broad list of "
            "mid-caps that all still exist in 2026 — and smallest among large "
            "caps, which rarely delist. That pattern is what an artefact looks "
            "like."),
        "still_not_clean": (
            "Even the most conservative row here is contaminated. A "
            "point-in-time liquidity screen fixes look-ahead in universe "
            "SELECTION, but every company in the data source is one that "
            "survived to today. The ones that went to zero are missing, and "
            "momentum strategies buy recent winners, which is precisely the "
            "population that survivorship flatters. Fixing that needs "
            "point-in-time constituent data this project does not have."),
        "verdict": "NOT VALIDATED — the range is the result, not the best number in it.",
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
