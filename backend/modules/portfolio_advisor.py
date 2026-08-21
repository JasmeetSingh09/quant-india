"""
portfolio_advisor.py — "what to fix" for a portfolio, grounded in numbers.

Every suggestion carries the figure that triggered it. Nothing here generates
prose about "considering diversification"; a suggestion that cannot cite a
number it measured does not get emitted. That constraint is the point — the
whole platform's credibility rests on its outputs being checkable.

Three inputs feed it:
  alpha       — the model's current score and distress flags per holding
  performance — how each position is actually doing right now
  risk        — concentration of money, concentration of RISK, correlation,
                and the simulated downside
"""

from datetime import datetime

SEV = {"high": 3, "medium": 2, "low": 1}


# The transferable principle behind each finding. The advisor's job is not
# only to fix THIS portfolio — a user who understands why concentration hurts
# can spot it in the next one without being told. Findings are specific to the
# holdings; lessons are general and identical every time, which is what makes
# them learnable.
LESSONS = {
    "weak_alpha": (
        "Why it matters: every rupee has an opportunity cost. Money sitting in a "
        "name the model rates poorly is money not working in one it rates well. "
        "The size of a position should reflect how much conviction you have."),
    "underweight_strong": (
        "Why it matters: conviction and position size should agree. A tiny "
        "position in your best idea barely moves your result even when you are "
        "right — being correct only pays if you owned enough of it."),
    "concentration": (
        "Why it matters: with one stock above 40%, your outcome IS that "
        "company's outcome. Everything you know about it can be true and one "
        "surprise — a bad quarter, a regulator, a fire — still decides your "
        "year. Diversification is the only free lunch in investing."),
    "too_few": (
        "Why it matters: risk falls fast as you add holdings, then flattens. "
        "Going from 3 stocks to 8 removes most single-company risk; going from "
        "20 to 40 removes very little and makes the portfolio harder to follow."),
    "risk_concentration": (
        "Why it matters: money and risk are different things. A volatile stock "
        "at 10% can drive more of your ups and downs than a stable one at 30%. "
        "Professionals size positions by RISK contributed, not rupees spent."),
    "correlated": (
        "Why it matters: diversification comes from holdings that move "
        "differently, not from counting names. Two banks are one bet on banking. "
        "Real spread means different sectors, sizes and business drivers."),
    "downside_breach": (
        "Why it matters: the loss you can live with should drive the portfolio, "
        "not the other way round. Deciding this BEFORE you invest is what stops "
        "you selling at the bottom — the single most expensive mistake there is."),
    "sector_concentration": (
        "Why it matters: owning five banks is not owning five stocks — it is one "
        "bet on banking, placed five times. Whatever hits the sector hits all of "
        "them the same week: an RBI rule, a rate move, a credit cycle. Counting "
        "names tells you nothing; counting the things that can go wrong at once "
        "tells you everything."),
    "behind_index": (
        "Why it matters: the index is the free alternative, available to anyone "
        "in one click. Beating it is the only reason to pick individual stocks. "
        "If you cannot, buying the index is the rational choice — and finding "
        "that out early is worth far more than a flattering number."),
    "illiquid": (
        "Why it matters: a price you cannot trade at is not a price. Thinly "
        "traded stocks are easy to buy and hard to sell — the spread widens "
        "exactly when you want out, because everyone else wants out too. "
        "Liquidity is invisible until the day it is the only thing that matters."),
    "tax_boundary": (
        "Why it matters: in India a gain held under a year is taxed at 20% and "
        "one held over a year at 12.5%. The same profit is worth more for having "
        "waited, and frequent trading costs tax as well as brokerage — usually "
        "the larger of the two."),
}


# Each module asks a different question, so it gets a different subset. The
# optimizer designs a portfolio that has not returned anything yet, so telling
# it that it "trails the index" would be comparing a simulation to reality and
# calling the difference performance. Monte Carlo is about the shape of the
# downside, not about which stock the model dislikes.
FOCUS = {
    "live":   None,      # a real portfolio with real money and real time: everything
    "design": {"weak_alpha", "underweight_strong", "concentration", "too_few",
               "sector_concentration", "risk_concentration", "correlated", "illiquid"},
    "risk":   {"concentration", "too_few", "sector_concentration",
               "risk_concentration", "correlated", "downside_breach"},
}


# Pairwise correlation catches two names that move together. It does NOT catch
# five banks each correlating 0.65 with the others — no pair trips the 0.8 test,
# yet the portfolio is one sector-sized bet. That is the most common real mistake
# in Indian retail portfolios, so it gets its own rule rather than relying on
# correlation to imply it.
def _sector_of(ticker: str) -> str | None:
    try:
        from data_fetcher import NSE_SECTORS
        t = ticker.strip().upper()
        for sector, members in NSE_SECTORS.items():
            if t in members:
                return sector
    except Exception:
        pass
    # Fall back to the company metadata we already cache. Deliberately no live
    # fetch loop here — the advisor runs on page load.
    try:
        from data_fetcher import get_company_info
        s = (get_company_info(ticker) or {}).get("sector")
        if s and s != "Unknown":
            return s
    except Exception:
        pass
    return None


def _sector_exposure(weights: dict) -> dict:
    """{sector: total weight %} for holdings whose sector we can identify."""
    out: dict[str, float] = {}
    for t, pct in weights.items():
        s = _sector_of(t)
        if s:
            out[s] = out.get(s, 0.0) + pct
    return out


def _cap_payoff(weights: dict, initial_value: float, horizon_months: int,
                cap_pct: float, current_downside):
    """
    What capping the biggest holding actually buys you, in points of downside.

    A tip that says "trimming frees capital" is a lecture. A tip that says the
    worst case improves from -34% to -26% shows the size of the prize, which is
    what turns advice into a decision. Returns None when the numbers are not
    available rather than inventing an improvement.
    """
    if current_downside is None:
        return None
    try:
        from portfolio_scenarios import what_if
        r = what_if(weights, initial_value=initial_value,
                    horizon_months=horizon_months, max_weight_pct=cap_pct)
        after = (r or {}).get("after", {}).get("downside_pct")
        if after is None:
            return None
        gain = round(abs(current_downside) - abs(after), 1)
        if gain <= 0.5:      # not worth claiming an improvement this small
            return None
        return {"cap_pct": cap_pct, "downside_before": current_downside,
                "downside_after": after, "improvement_pts": gain}
    except Exception:
        return None


def _tip(severity, kind, title, detail, tickers=None):
    return {"severity": severity, "kind": kind, "title": title,
            "detail": detail, "lesson": LESSONS.get(kind), "tickers": tickers or []}


def _alpha_for(tickers):
    """Latest stored alpha per ticker from the universe scan (no live refetch —
    this must stay fast enough to run on page load)."""
    out = {}
    try:
        from universe_scan import get_signal_history
        for t in tickers:
            h = get_signal_history(t, limit=1)
            if h:
                out[t] = h[0]
    except Exception:
        pass
    return out


def advise(holdings: dict, initial_value: float = 100000,
           horizon_months: int = 12, max_loss_pct: float = None,
           current_return_pct: float = None, user_id: str = None,
           portfolio_id: str = None, focus: str = "live",
           days_held: int = None) -> dict:
    """
    holdings: {ticker: weight_pct} summing to ~100.
    current_return_pct: the portfolio's actual return so far, when the caller
        knows it — enables the index comparison, which is skipped without it.
    focus: which module is asking — "live" (real portfolio), "design" (building
        one), or "risk" (studying the downside). Controls which findings apply.
    Returns suggestions ordered by severity, each citing its own evidence.
    """
    allowed = FOCUS.get(focus, None)
    def wanted(kind):
        return allowed is None or kind in allowed
    if not holdings:
        return {"error": "No holdings to analyse."}
    tickers = list(holdings)
    total_w = sum(holdings.values()) or 1.0
    w = {t: holdings[t] * 100.0 / total_w for t in tickers}     # normalise to %

    tips = []
    alpha = _alpha_for(tickers)

    # ---- 1. the model's own opinion of what you hold ---------------------
    weak = [(t, a["alpha_score"], a["signal"]) for t, a in alpha.items()
            if a.get("alpha_score") is not None and a["alpha_score"] < -15]
    for t, sc, sig in (sorted(weak, key=lambda x: x[1])[:3] if wanted("weak_alpha") else []):
        tips.append(_tip("high", "weak_alpha",
            f"{t.replace('.NS','')} scores {sc:+.0f} ({sig})",
            f"It is {w.get(t,0):.0f}% of your money while the model rates it a {sig}. "
            f"Trimming it frees capital for names the model actually likes.", [t]))

    strong_missing = [t for t, a in alpha.items()
                      if (a.get("alpha_score") or 0) > 40 and w.get(t, 0) < 10]
    for t in (strong_missing[:2] if wanted("underweight_strong") else []):
        a = alpha[t]
        tips.append(_tip("low", "underweight_strong",
            f"{t.replace('.NS','')} scores {a['alpha_score']:+.0f} but is only {w[t]:.0f}%",
            "One of your strongest-rated holdings is one of your smallest positions.", [t]))

    # ---- 2. concentration of MONEY --------------------------------------
    biggest = max(w, key=w.get)
    if w[biggest] > 40:
        tips.append(_tip("high", "concentration",
            f"{biggest.replace('.NS','')} is {w[biggest]:.0f}% of the portfolio",
            f"A single stock above 40% means your result is mostly that one company's "
            f"result. Capping it near {max(20, 100//max(len(tickers),1)):.0f}% spreads the outcome.",
            [biggest]))
    if len(tickers) < 5:
        tips.append(_tip("medium", "too_few",
            f"Only {len(tickers)} stocks",
            "Below about 5 holdings, one company's bad news dominates the portfolio. "
            "Most of the diversification benefit arrives by 8-12 names."))

    # ---- 2b. concentration of SECTOR ------------------------------------
    # Runs before the correlation check on purpose: it catches the case
    # correlation misses, and it is the finding users most often need.
    sectors = _sector_exposure(w)
    if sectors:
        top_sector, top_pct = max(sectors.items(), key=lambda kv: kv[1])
        names = [t.replace(".NS", "") for t in w if _sector_of(t) == top_sector]
        if top_pct > 40 and len(names) > 1:
            tips.append(_tip("high", "sector_concentration",
                f"{top_pct:.0f}% of your money is in {top_sector}",
                f"You hold {len(names)} {top_sector.lower()} names "
                f"({', '.join(names[:4])}{'…' if len(names) > 4 else ''}). "
                f"They may look like {len(names)} separate decisions, but one piece "
                f"of sector news moves all of them the same way on the same day. "
                f"Adding a holding from a different sector does more for your risk "
                f"than adding a sixth name in this one.",
                [t for t in w if _sector_of(t) == top_sector]))
        elif len(sectors) >= 4 and top_pct < 35:
            tips.append(_tip("low", "sector_concentration",
                f"Spread across {len(sectors)} sectors — no single one dominates",
                f"Your largest sector exposure is {top_sector} at {top_pct:.0f}%. "
                f"This is what real diversification looks like: the things that can "
                f"go wrong are genuinely different from each other."))

    # ---- 3. concentration of RISK (different from money) ----------------
    try:
        from portfolio_optimizer import risk_decomposition
        rd = risk_decomposition({t: w[t] for t in tickers})
        # risk_decomposition returns a sorted `components` list, each already
        # carrying risk_contribution_pct and weight_pct as percentages.
        for comp in (rd.get("components") or []):
            t = comp.get("ticker")
            rc_pct = comp.get("risk_contribution_pct") or 0
            money = comp.get("weight_pct") or w.get(t, 0)
            if rc_pct - money > 15:
                tips.append(_tip("medium", "risk_concentration",
                    f"{t.replace('.NS','')} drives {rc_pct:.0f}% of risk on {money:.0f}% of money",
                    "This holding contributes far more volatility than its size suggests — "
                    "usually a sign it is the most volatile name you own.", [t]))
    except Exception:
        pass

    # ---- 4. holdings that are really one bet ----------------------------
    try:
        import numpy as np
        from portfolio_optimizer import _get_returns
        from datetime import timedelta
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
        rets = _get_returns(tickers, start, end)
        if rets is not None and len(rets) > 30:
            c = rets.corr()
            seen = set()
            for a in c.columns:
                for b in c.columns:
                    if a >= b or (a, b) in seen:
                        continue
                    seen.add((a, b))
                    v = float(c.loc[a, b])
                    if v > 0.8:
                        tips.append(_tip("medium", "correlated",
                            f"{a.replace('.NS','')} and {b.replace('.NS','')} move together ({v:.2f})",
                            "They rise and fall almost as one, so holding both is closer to "
                            "one position than two. Swapping one for a different sector adds "
                            "real diversification.", [a, b]))
    except Exception:
        pass

    # ---- 5. downside against the stated limit ---------------------------
    downside = None
    try:
        from monte_carlo import simulate
        sim = simulate({t: w[t] for t in tickers}, initial_value=initial_value,
                       horizon_days=max(21, horizon_months * 21),
                       n_simulations=4000, method="bootstrap", seed=11)
        if "error" not in sim:
            downside = round((sim["percentiles"]["p5"] / initial_value - 1) * 100, 1)
            if max_loss_pct is not None and abs(downside) > max_loss_pct:
                tips.append(_tip("high", "downside_breach",
                    f"Worst-case {downside:.0f}% exceeds your {max_loss_pct:.0f}% limit",
                    "In the worst 5% of simulated outcomes this portfolio loses more than "
                    "you said you could accept. More holdings, larger companies, or a "
                    "longer horizon all reduce it."))
    except Exception:
        pass

    # ---- 6. attach the SIZE of each fix, not just the fix ----------------
    # Done here rather than inline because it needs the simulated downside from
    # step 5. "Trim this" is a lecture; "trim this and the worst case improves
    # by 8 points" is a decision the user can actually weigh.
    for tip in tips:
        if tip["kind"] in ("concentration", "sector_concentration") and tip["tickers"]:
            cap = float(max(20, 100 // max(len(tickers), 1)))
            payoff = _cap_payoff({t: w[t] for t in tickers}, initial_value,
                                 horizon_months, cap, downside)
            if payoff:
                tip["payoff"] = payoff
                tip["detail"] += (
                    f" Concretely: capping every holding at {cap:.0f}% moves your "
                    f"worst case from {payoff['downside_before']:.0f}% to "
                    f"{payoff['downside_after']:.0f}% — {payoff['improvement_pts']:.1f} "
                    f"points of downside removed without predicting anything.")
            break     # one simulation is enough; they share the same fix

    # ---- 6b. can you actually trade what you hold? -----------------------
    if wanted("illiquid"):
        try:
            from liquidity import assess, label
            bad = []
            for t in tickers:
                a = assess(t)
                if a.get("tier") in ("thin", "illiquid"):
                    bad.append((t, a))
            if bad:
                worst = min(bad, key=lambda x: x[1].get("daily_value") or 0)
                pct = sum(w.get(t, 0) for t, _ in bad)
                tips.append(_tip("high" if pct > 20 else "medium", "illiquid",
                    f"{len(bad)} holding(s) barely trade — {pct:.0f}% of your money",
                    f"{worst[0].replace('.NS','')} turns over "
                    f"{label(worst[1].get('daily_value'))}. At that size an order "
                    f"moves the price against you, and selling in a hurry is worse "
                    f"than buying. A score on a stock you cannot exit is not an "
                    f"opportunity.",
                    [t for t, _ in bad]))
        except Exception:
            pass

    # ---- 6c. the tax boundary, when there is a real gain and a real clock --
    tax_view = None
    if wanted("tax_boundary") and current_return_pct is not None and days_held:
        try:
            from tax import after_tax
            tax_view = after_tax(initial_value,
                                 initial_value * (1 + current_return_pct / 100.0),
                                 days_held=days_held)
            if tax_view.get("boundary_note") and (tax_view.get("long_term_in_days") or 999) <= 90:
                tips.append(_tip("low", "tax_boundary",
                    f"{tax_view['long_term_in_days']} days from long-term treatment",
                    tax_view["boundary_note"]))
        except Exception:
            tax_view = None

    # ---- 7. the comparison nobody volunteers ------------------------------
    bench = None
    if wanted("behind_index"):
        try:
            from benchmark import compare, index_return
            window = max(30, horizon_months * 30)
            bench = index_return(window)
            if bench and current_return_pct is not None:
                c = compare(current_return_pct, window)
                if c:
                    bench = c
                    if c["verdict"] == "behind":
                        tips.append(_tip("high", "behind_index",
                            f"You are {abs(c['difference_pct']):.1f} points behind "
                            f"{c['benchmark']}",
                            c["plain"]))
        except Exception:
            bench = None

    tips.sort(key=lambda t: -SEV.get(t["severity"], 0))

    # Write down what we claimed, so it can be checked against reality later.
    # Never allowed to break the advice itself.
    try:
        from advice_log import record
        record(tips, w, downside_pct=downside, user_id=user_id)
    except Exception:
        pass

    # A headline the reader can act on, built from findings already measured.
    try:
        from portfolio_score import score as _score
        _hs = _score(w, {"sector_exposure": {k: round(v, 1) for k, v in sectors.items()} if sectors else {},
                         "downside_pct": downside, "suggestions": tips})
    except Exception:
        _hs = None

    # Per-holding risk share, so a reader can see WHICH position drives the
    # portfolio's swings. Money and risk are different quantities and the gap
    # between them is the point.
    _risk_rows = None
    try:
        from portfolio_optimizer import risk_decomposition
        _rd = risk_decomposition({t: w[t] for t in tickers})
        _risk_rows = [{
            "ticker": c.get("ticker"),
            "weight_pct": round(c.get("weight_pct") or 0, 1),
            "risk_pct": round(c.get("risk_contribution_pct") or 0, 1),
            "gap_pts": round((c.get("risk_contribution_pct") or 0)
                             - (c.get("weight_pct") or 0), 1),
        } for c in (_rd.get("components") or [])]
    except Exception:
        _risk_rows = None

    return {
        "health": _hs,
        "risk_contributions": _risk_rows,
        "suggestions": tips,
        "n_suggestions": len(tips),
        "downside_pct": downside,
        "benchmark": bench,
        "focus": focus,
        "tax": tax_view,
        "sector_exposure": {k: round(v, 1) for k, v in
                            sorted(sectors.items(), key=lambda kv: -kv[1])} if sectors else {},
        "holdings_analysed": len(tickers),
        "headline": (tips[0]["title"] if tips else
                     "No obvious problems found — the model has no specific fix to suggest."),
        "teaches": "Each finding comes with the principle behind it, so the same "
                   "mistake is recognisable next time without being told.",
        "basis": "Alpha scores from the latest universe scan, risk decomposition and "
                 "correlation from 400 days of returns, downside from 4,000 simulations.",
        "disclaimer": "Model output, not financial advice.",
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
