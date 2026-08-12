"""
portfolio_builder.py — turn a beginner's five answers into a concrete portfolio.

Input:  how much, for how long, worst loss they can stomach, how many stocks,
        and a risk appetite.
Output: named stocks with weights, the expected outcome over their horizon, and
        the downside — plus an explicit verdict on whether that downside fits
        the loss limit they stated.

The point is the last part. Anyone can hand back a portfolio; the useful thing
is telling someone their aggressive 5-stock idea has a 1-in-20 chance of losing
more than they said they could take, BEFORE they act on it.
"""

from datetime import datetime

RISK_PROFILES = {
    "conservative": {
        "tiers": ["large"],
        "optimizer": "risk_parity",
        "label": "Conservative",
        "why": "Large caps only, weighted so no single stock dominates the risk.",
    },
    "balanced": {
        "tiers": ["large", "mid"],
        "optimizer": "markowitz",
        "label": "Balanced",
        "why": "Large and mid caps, weighted for the best return per unit of risk.",
    },
    "aggressive": {
        "tiers": ["mid", "small"],
        "optimizer": "markowitz",
        "label": "Aggressive",
        "why": "Mid and small caps — higher potential return, materially higher risk.",
    },
}


def _candidates(tiers, n_stocks, min_conf=0.4):
    """Highest-alpha names in the requested tiers, from the last complete scan."""
    from universe_scan import top_by_tier
    data = top_by_tier(n=max(n_stocks * 3, 30), min_confidence=min_conf)
    pool = []
    for t in tiers:
        pool.extend(data.get(f"{t}_cap", {}).get("buys", []))
    # Only names the model actually likes; a "top pick" that scores negative is
    # the best of a bad tier, not a buy.
    pool = [p for p in pool if (p.get("alpha_score") or 0) > 0]
    pool.sort(key=lambda p: -(p.get("alpha_score") or 0))
    seen, out = set(), []
    for p in pool:
        if p["ticker"] in seen:
            continue
        seen.add(p["ticker"])
        out.append(p)
        if len(out) >= n_stocks:
            break
    return out, data.get("serving_cycle")


def build_portfolio(amount: float = 100000, horizon_months: int = 12,
                    max_loss_pct: float = 20.0, n_stocks: int = 5,
                    risk: str = "balanced") -> dict:
    # ---- validate -------------------------------------------------------
    try:
        amount = float(amount); horizon_months = int(horizon_months)
        max_loss_pct = float(max_loss_pct); n_stocks = int(n_stocks)
    except (TypeError, ValueError):
        return {"error": "Amount, horizon, max loss and stock count must be numbers."}
    if amount < 1000:
        return {"error": "Enter at least ₹1,000."}
    if not 1 <= horizon_months <= 120:
        return {"error": "Horizon must be between 1 and 120 months."}
    if not 1 <= max_loss_pct <= 90:
        return {"error": "Max loss must be between 1% and 90%."}
    if not 2 <= n_stocks <= 20:
        return {"error": "Pick between 2 and 20 stocks."}
    risk = (risk or "balanced").strip().lower()
    if risk not in RISK_PROFILES:
        return {"error": f"Risk must be one of: {', '.join(RISK_PROFILES)}"}

    profile = RISK_PROFILES[risk]
    picks, cycle = _candidates(profile["tiers"], n_stocks)
    if len(picks) < 2:
        return {"error": "Not enough stocks scored yet in this risk band. "
                         "The universe scan is still running — try again shortly."}

    tickers = [p["ticker"] for p in picks]

    # ---- weights --------------------------------------------------------
    weights, method_note = {}, ""
    try:
        import portfolio_optimizer as PO
        # equal_risk_contribution is the risk-parity engine; mean_variance is
        # Markowitz. Both return weights under "optimal_weights".
        if profile["optimizer"] == "risk_parity":
            r = PO.equal_risk_contribution(tickers)
        else:
            # Unconstrained mean-variance returns a corner solution: asked for
            # 5 stocks it put 100% into one and 0% into the rest, which is not
            # the diversified portfolio the user requested. Cap any single
            # holding so the answer actually contains the number of stocks
            # they asked for, with a floor so tiny portfolios stay feasible.
            cap = max(0.35, min(1.0, 2.0 / len(tickers)))
            r = PO.mean_variance_optimize(tickers, max_weight=cap, min_weight=0.02)
        weights = (r.get("optimal_weights") or r.get("weights") or {}) if isinstance(r, dict) else {}
        method_note = profile["optimizer"]
    except Exception:
        weights = {}
    if not weights or abs(sum(weights.values()) - 1.0) > 0.05:
        # Equal weight is a defensible fallback, not a silent failure — say so.
        weights = {t: 1.0 / len(tickers) for t in tickers}
        method_note = "equal weight (optimiser unavailable for these names)"

    holdings = []
    for p in picks:
        w = weights.get(p["ticker"], 0.0)
        holdings.append({
            "ticker": p["ticker"],
            "name": p["ticker"].replace(".NS", ""),
            "weight_pct": round(w * 100, 2),
            "amount": round(amount * w, 2),
            "alpha_score": p.get("alpha_score"),
            "signal": p.get("signal"),
            "market_cap": p.get("market_cap"),
        })
    holdings.sort(key=lambda h: -h["weight_pct"])

    # ---- what could happen ----------------------------------------------
    horizon_days = max(21, int(horizon_months * 21))
    outcome, downside_pct, meets = None, None, None
    try:
        from monte_carlo import simulate
        alloc = {h["ticker"]: h["weight_pct"] for h in holdings}
        total = sum(alloc.values())
        if total:                      # normalise to exactly 100 for the simulator
            alloc = {k: v * 100.0 / total for k, v in alloc.items()}
        sim = simulate(alloc, initial_value=amount, horizon_days=horizon_days,
                       n_simulations=5000, method="bootstrap", seed=7)
        if "error" not in sim:
            p5 = sim["percentiles"]["p5"]
            downside_pct = round((p5 / amount - 1) * 100, 2)
            outcome = {
                "median_value": sim["median_value"],
                "p5_value": p5,
                "p95_value": sim["percentiles"]["p95"],
                "probability_of_loss_pct": sim["probability_of_loss_pct"],
                "horizon_days": horizon_days,
            }
            # The verdict the whole flow exists for.
            meets = abs(downside_pct) <= max_loss_pct
    except Exception:
        pass

    if meets is None:
        verdict = ("Could not simulate this portfolio's downside, so we cannot "
                   "confirm it fits your loss limit.")
    elif meets:
        verdict = (f"In the worst 5% of outcomes you would be down about "
                   f"{abs(downside_pct):.1f}% — within the {max_loss_pct:.0f}% "
                   f"you said you could accept.")
    else:
        verdict = (f"In the worst 5% of outcomes you would be down about "
                   f"{abs(downside_pct):.1f}%, MORE than the {max_loss_pct:.0f}% "
                   f"you said you could accept. Consider a lower-risk profile, "
                   f"more stocks, or a longer horizon.")

    return {
        "inputs": {"amount": amount, "horizon_months": horizon_months,
                   "max_loss_pct": max_loss_pct, "n_stocks": n_stocks, "risk": risk},
        "profile": {"label": profile["label"], "why": profile["why"],
                    "tiers": profile["tiers"], "weighting": method_note},
        "holdings": holdings,
        "outcome": outcome,
        "downside_pct": downside_pct,
        "meets_loss_limit": meets,
        "verdict": verdict,
        "based_on_scan": cycle,
        "disclaimer": "A model-generated starting point, not financial advice. "
                      "Past patterns do not guarantee future results.",
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
