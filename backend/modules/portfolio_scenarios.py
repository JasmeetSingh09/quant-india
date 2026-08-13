"""
portfolio_scenarios.py — concrete "what if I changed this?" options.

The advisor says what is wrong. This says what to DO about it, hands back the
exact weights to apply, and shows what each change does to BOTH return and risk
so the user can re-run the optimiser or simulator on the tweaked version.

Deliberate framing: scenarios are never sold as "this makes more money". Each
one reports the change in expected return AND the change in downside, because
most real improvements are trades, not free wins — usually a little expected
return given up for a large cut in the worst case. Presenting only the upside
would make this a slot machine, and the platform's whole claim is honesty about
what the numbers actually say.
"""

from datetime import datetime

N_SIMS = 3000          # per scenario; enough for stable p5, cheap enough for ~6 runs


def _norm(h):
    tot = sum(h.values()) or 1.0
    return {k: v * 100.0 / tot for k, v in h.items() if v > 0}


def _measure(holdings, initial_value, horizon_days):
    """Median outcome and worst-5% for one candidate portfolio."""
    from monte_carlo import simulate
    sim = simulate(_norm(holdings), initial_value=initial_value,
                   horizon_days=horizon_days, n_simulations=N_SIMS,
                   method="bootstrap", seed=13)
    if "error" in sim:
        return None
    return {
        "median_value":  sim["median_value"],
        "p5_value":      sim["percentiles"]["p5"],
        "return_pct":    round((sim["median_value"] / initial_value - 1) * 100, 2),
        "downside_pct":  round((sim["percentiles"]["p5"] / initial_value - 1) * 100, 2),
        "loss_prob_pct": sim["probability_of_loss_pct"],
    }


def _alpha_map(tickers):
    out = {}
    try:
        from universe_scan import get_signal_history
        for t in tickers:
            h = get_signal_history(t, limit=1)
            if h and h[0].get("alpha_score") is not None:
                out[t] = h[0]["alpha_score"]
    except Exception:
        pass
    return out


def _candidates_not_held(held, n=1):
    """Highest-alpha names from the scan that the user does not already own."""
    try:
        from universe_scan import top_by_tier
        d = top_by_tier(n=25, min_confidence=0.4)
        pool = []
        for k in ("large_cap", "mid_cap", "small_cap"):
            pool.extend(d.get(k, {}).get("buys", []))
        pool = [p for p in pool
                if p["ticker"] not in held and (p.get("alpha_score") or 0) > 20]
        pool.sort(key=lambda p: -(p["alpha_score"] or 0))
        return pool[:n]
    except Exception:
        return []


def scenarios(holdings: dict, initial_value: float = 100000,
              horizon_months: int = 12) -> dict:
    if not holdings or len(holdings) < 2:
        return {"error": "Need at least 2 holdings to suggest changes."}

    base_w = _norm(holdings)
    horizon_days = max(21, horizon_months * 21)
    base = _measure(base_w, initial_value, horizon_days)
    if not base:
        return {"error": "Could not simulate this portfolio."}

    alphas = _alpha_map(list(base_w))
    out = []

    def add(name, why, new_w):
        new_w = _norm({k: v for k, v in new_w.items() if v > 0.01})
        if not new_w or new_w == base_w:
            return
        m = _measure(new_w, initial_value, horizon_days)
        if not m:
            return
        out.append({
            "name": name, "why": why, "weights": {k: round(v, 2) for k, v in new_w.items()},
            "after": m,
            "delta_return_pct":   round(m["return_pct"] - base["return_pct"], 2),
            "delta_downside_pct": round(m["downside_pct"] - base["downside_pct"], 2),
        })

    # 1. cap the largest position
    top = max(base_w, key=base_w.get)
    if base_w[top] > 25:
        cap = 25.0
        w = dict(base_w); excess = w[top] - cap; w[top] = cap
        others = [k for k in w if k != top]
        for k in others:
            w[k] += excess / len(others)
        add(f"Cap {top.replace('.NS','')} at 25%",
            f"It is {base_w[top]:.0f}% of the portfolio, so your result is mostly its result. "
            f"The excess is spread across your other holdings.", w)

    # 2. equal weight
    add("Equal-weight everything",
        "Removes every sizing judgement. A useful baseline — if a clever weighting "
        "cannot beat this, the cleverness is not earning its keep.",
        {k: 1.0 for k in base_w})

    # 3. drop the weakest-rated holding
    if alphas:
        worst = min(alphas, key=alphas.get)
        if alphas[worst] < 0 and len(base_w) > 2:
            w = {k: v for k, v in base_w.items() if k != worst}
            freed = base_w[worst]
            for k in w:
                w[k] += freed / len(w)
            add(f"Drop {worst.replace('.NS','')} (alpha {alphas[worst]:+.0f})",
                "The model rates this the weakest name you hold. Its money is "
                "redistributed across the rest.", w)

    # 4. add the strongest name you do not own
    for c in _candidates_not_held(set(base_w), n=1):
        w = {k: v * 0.85 for k, v in base_w.items()}
        w[c["ticker"]] = 15.0
        add(f"Add {c['ticker'].replace('.NS','')} at 15% (alpha {c['alpha_score']:+.0f})",
            "A high-scoring name you do not currently hold, funded by trimming "
            "everything else proportionally.", w)

    # 5. spread wider
    if len(base_w) < 8:
        extra = _candidates_not_held(set(base_w), n=3)
        if len(extra) >= 2:
            w = {k: v * 0.7 for k, v in base_w.items()}
            for c in extra:
                w[c["ticker"]] = 30.0 / len(extra)
            add(f"Diversify to {len(base_w) + len(extra)} stocks",
                "More holdings means one company's bad news matters less. Most of "
                "the benefit arrives by 8-12 names.", w)

    # Rank by downside improvement, then return — risk reduction is the more
    # reliable of the two, and ordering by return alone would quietly turn this
    # into a leaderboard for the riskiest option.
    out.sort(key=lambda s: (s["delta_downside_pct"], s["delta_return_pct"]), reverse=True)

    return {
        "base": base,
        "base_weights": {k: round(v, 2) for k, v in base_w.items()},
        "scenarios": out,
        "n_scenarios": len(out),
        "how_to_read": ("Each option shows the change in BOTH typical outcome and worst "
                        "case. Most improvements are trades — a little expected return "
                        "given up for a smaller loss when things go wrong."),
        "horizon_months": horizon_months,
        "disclaimer": "Simulated from past returns. Not a prediction, not financial advice.",
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def what_if(holdings: dict, initial_value: float = 100000,
            horizon_months: int = 12, max_weight_pct: float = None) -> dict:
    """
    Measure a user's OWN tweak rather than a preset one.

    Presets answer "what could I change?"; this answers "what if I change it
    like THIS?" — cap any holding at max_weight_pct, and/or run a different
    horizon. Both the original and the tweaked portfolio are simulated over the
    SAME horizon so the comparison is like for like; changing only the horizon
    still moves both numbers, which is the honest way to show that a longer
    holding period changes the range of outcomes rather than the portfolio.
    """
    if not holdings or len(holdings) < 2:
        return {"error": "Need at least 2 holdings."}
    try:
        horizon_months = int(horizon_months)
        initial_value = float(initial_value)
    except (TypeError, ValueError):
        return {"error": "Horizon and amount must be numbers."}
    if not 1 <= horizon_months <= 120:
        return {"error": "Horizon must be between 1 and 120 months."}

    base_w = _norm(holdings)
    horizon_days = max(21, horizon_months * 21)
    base = _measure(base_w, initial_value, horizon_days)
    if not base:
        return {"error": "Could not simulate this portfolio."}

    new_w, applied = dict(base_w), []
    if max_weight_pct:
        cap = float(max_weight_pct)
        if cap < 100.0 / len(base_w):
            return {"error": f"With {len(base_w)} stocks the cap must be at least "
                             f"{100.0/len(base_w):.0f}%."}
        # Redistribute whatever exceeds the cap across the holdings still under
        # it, repeating until nothing breaches — capping once can push another
        # holding over the line.
        for _ in range(20):
            over = {k: v for k, v in new_w.items() if v > cap + 1e-9}
            if not over:
                break
            excess = sum(v - cap for v in over.values())
            for k in over:
                new_w[k] = cap
            room = [k for k, v in new_w.items() if v < cap - 1e-9]
            if not room:
                break
            for k in room:
                new_w[k] += excess / len(room)
        applied.append(f"no holding above {cap:.0f}%")

    new_w = _norm(new_w)
    changed = any(abs(new_w[k] - base_w[k]) > 0.01 for k in base_w)
    after = _measure(new_w, initial_value, horizon_days) if changed else base

    return {
        "base": base,
        "after": after,
        "weights": {k: round(v, 2) for k, v in new_w.items()},
        "changed": changed,
        "applied": applied,
        "horizon_months": horizon_months,
        "delta_return_pct":   round(after["return_pct"] - base["return_pct"], 2),
        "delta_downside_pct": round(after["downside_pct"] - base["downside_pct"], 2),
        "disclaimer": "Simulated from past returns. Not a prediction.",
    }
