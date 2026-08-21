"""
portfolio_fix.py — a concrete allocation, and what changing to it would do.

The coach says what is wrong. That is most of the way there, and it stops one
step short: a reader who agrees the portfolio is too concentrated still has to
work out what to hold instead, which is the part they came for.

So this proposes an allocation and shows both portfolios side by side on the
same measurements. Two rules govern what it will and will not do:

It fixes STRUCTURE, not selection. It caps oversized positions, caps sector
overlap, and spreads the freed money across what is already held — it does not
tell anyone which company to buy, because that is a forecast and the track
record does not support making one.

It shows the cost of the change as readily as the benefit. Rebalancing means
selling, which means brokerage, STT and tax. A "suggested" portfolio that hides
its own switching cost is advice with a thumb on the scale.
"""

MAX_SINGLE = 25.0      # cap any one holding here when trimming
MAX_SECTOR = 40.0      # and any one sector here
MIN_HOLDINGS = 5       # below this, spreading is the first thing worth saying


def _normalise(w: dict) -> dict:
    tot = sum(v for v in w.values() if v and v > 0) or 1.0
    return {t: v * 100.0 / tot for t, v in w.items() if v and v > 0}


def _cap_and_spread(weights: dict, cap: float) -> dict:
    """
    Trim anything above `cap` and redistribute to the rest, proportionally.

    Iterative because one pass can push a previously-compliant holding over the
    cap: trimming a 60% position hands its excess to the others, and the second
    largest can breach as a result. Loops until stable rather than once.
    """
    w = dict(weights)
    for _ in range(20):
        over = {t: v for t, v in w.items() if v > cap + 1e-9}
        if not over:
            break
        excess = sum(v - cap for v in over.values())
        under = {t: v for t, v in w.items() if v <= cap + 1e-9}
        if not under:
            break
        room = sum(cap - v for v in under.values()) or 1.0
        for t in over:
            w[t] = cap
        for t, v in under.items():
            w[t] = v + excess * ((cap - v) / room)
    return _normalise(w)


def _cap_sectors(weights: dict, cap: float) -> dict:
    """Same idea applied to sectors: trim the sector, not just the stock."""
    try:
        from portfolio_advisor import _sector_of
    except Exception:
        return weights
    w = dict(weights)
    for _ in range(10):
        by_sector: dict = {}
        for t, v in w.items():
            s = _sector_of(t)
            if s:
                by_sector.setdefault(s, []).append(t)
        breach = {s: sum(w[t] for t in ts) for s, ts in by_sector.items()
                  if sum(w[t] for t in ts) > cap + 1e-9}
        if not breach:
            break
        for s, total in breach.items():
            members = by_sector[s]
            scale = cap / total
            freed = total - cap
            for t in members:
                w[t] *= scale
            outside = [t for t in w if t not in members]
            if not outside:
                continue
            out_tot = sum(w[t] for t in outside) or 1.0
            for t in outside:
                w[t] += freed * (w[t] / out_tot)
        w = _normalise(w)
    return w


def suggest(holdings: dict, initial_value: float = 100000,
            horizon_months: int = 12) -> dict:
    """
    A proposed allocation plus a like-for-like comparison with the current one.

    Both portfolios are measured the same way over the same horizon, so the
    difference is the change and not the method.
    """
    cur = _normalise({t: float(v) for t, v in (holdings or {}).items()})
    if len(cur) < 2:
        return {"error": "Need at least 2 holdings to propose a change."}

    steps = []
    prop = dict(cur)

    # The cap has to be achievable. With N holdings the most even split possible
    # puts 100/N in each, so asking for 25% across two names is arithmetically
    # impossible — the earlier version tried, renormalised, and silently changed
    # nothing while reporting that it had. Where the request is infeasible the
    # honest answer is that re-weighting cannot fix this portfolio.
    feasible_cap = max(MAX_SINGLE, 100.0 / len(prop))
    top_t = max(prop, key=prop.get)
    if prop[top_t] > feasible_cap + 0.5:
        before = prop[top_t]
        prop = _cap_and_spread(prop, feasible_cap)
        steps.append({
            "action": "cap_single",
            "detail": (f"{top_t.replace('.NS','')} trimmed from {before:.0f}% to "
                       f"{prop[top_t]:.0f}%, with the difference spread across the "
                       f"other holdings."),
        })
    if feasible_cap > MAX_SINGLE + 0.5:
        steps.append({
            "action": "cap_infeasible",
            "detail": (f"With {len(prop)} holdings, the most even split possible is "
                       f"{feasible_cap:.0f}% each — so no re-weighting can get any "
                       f"position under {MAX_SINGLE:.0f}%. This portfolio needs more "
                       f"names, not different weights."),
        })

    try:
        from portfolio_advisor import _sector_exposure
        sec_before = _sector_exposure(prop)
        _outside = None
        if sec_before:
            _worst = max(sec_before, key=sec_before.get)
            _outside = sum(v for k, v in sec_before.items() if k != _worst)
        if sec_before and max(sec_before.values()) > MAX_SECTOR and (_outside or 0) > 0.5:
            worst = max(sec_before, key=sec_before.get)
            b = sec_before[worst]
            prop = _cap_sectors(prop, MAX_SECTOR)
            sec_after = _sector_exposure(prop)
            steps.append({
                "action": "cap_sector",
                "detail": (f"{worst} exposure reduced from {b:.0f}% to "
                           f"{sec_after.get(worst, 0):.0f}%. Capping each stock does "
                           f"not do this — five banks at 15% each is still one bet."),
            })
        elif sec_before and max(sec_before.values()) > MAX_SECTOR:
            _w = max(sec_before, key=sec_before.get)
            steps.append({
                "action": "sector_infeasible",
                "detail": (f"Every holding is in {_w}, so no re-weighting can reduce "
                           f"that exposure below {sec_before[_w]:.0f}%. Only a holding "
                           f"from a different sector changes this."),
            })
    except Exception:
        pass

    if len(cur) < MIN_HOLDINGS:
        steps.append({
            "action": "add_holdings",
            "detail": (f"Only {len(cur)} holdings. Most of the benefit of "
                       f"diversifying arrives by 8-12 names, and almost none of it "
                       f"is present at {len(cur)}. Adding names from sectors you do "
                       f"not already hold does more than re-weighting these."),
            "note": "The app does not pick which — that would be a forecast.",
        })

    if not steps:
        return {"changed": False, "current_pct": {t: round(v, 2) for t, v in cur.items()},
                "note": ("No structural change to propose: no holding is above "
                         f"{MAX_SINGLE:.0f}%, no sector above {MAX_SECTOR:.0f}%, and "
                         f"there are enough holdings to spread risk.")}

    # Measure both the same way.
    def _measure(w):
        try:
            from monte_carlo import simulate
            sim = simulate(w, initial_value=initial_value,
                           horizon_days=max(21, horizon_months * 21),
                           n_simulations=4000, method="bootstrap", seed=11)
            if "error" in sim:
                return None
            return {
                "median_pct": round((sim["median_value"] / initial_value - 1) * 100, 2),
                "downside_pct": round((sim["percentiles"]["p5"] / initial_value - 1) * 100, 2),
                "loss_prob_pct": sim.get("probability_of_loss_pct"),
            }
        except Exception:
            return None

    def _health(w):
        try:
            from portfolio_score import score
            from portfolio_advisor import _sector_exposure
            return score(w, {"sector_exposure": _sector_exposure(w),
                             "downside_pct": (_measure(w) or {}).get("downside_pct"),
                             "suggestions": []})
        except Exception:
            return None

    before_m, after_m = _measure(cur), _measure(prop)
    before_h, after_h = _health(cur), _health(prop)

    # What the change would cost to execute — stated, not buried.
    turnover = sum(abs(prop.get(t, 0) - cur.get(t, 0)) for t in set(cur) | set(prop)) / 2
    switch_cost = round(initial_value * (turnover / 100) * 0.00265, 0)

    return {
        "changed": True,
        "current_pct": {t: round(v, 2) for t, v in cur.items()},
        "proposed_pct": {t: round(v, 2) for t, v in sorted(prop.items(), key=lambda kv: -kv[1])},
        "steps": steps,
        "before": {"risk": before_m, "health": before_h},
        "after": {"risk": after_m, "health": after_h},
        "turnover_pct": round(turnover, 1),
        "switching_cost_inr": switch_cost,
        "cost_note": (f"Moving to this allocation trades about {turnover:.0f}% of the "
                      f"portfolio, costing roughly Rs {switch_cost:,.0f} in brokerage, "
                      f"STT and stamp duty — before any capital gains tax on what you "
                      f"sell. A smaller change kept for longer often beats a perfect "
                      f"one rebalanced often."),
        "limits": ("Structure only. This caps concentration and sector overlap and "
                   "redistributes across what you already hold. It does not pick "
                   "stocks, because picking is a forecast and the track record does "
                   "not support making one."),
    }
