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
}


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
           horizon_months: int = 12, max_loss_pct: float = None) -> dict:
    """
    holdings: {ticker: weight_pct} summing to ~100.
    Returns suggestions ordered by severity, each citing its own evidence.
    """
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
    for t, sc, sig in sorted(weak, key=lambda x: x[1])[:3]:
        tips.append(_tip("high", "weak_alpha",
            f"{t.replace('.NS','')} scores {sc:+.0f} ({sig})",
            f"It is {w.get(t,0):.0f}% of your money while the model rates it a {sig}. "
            f"Trimming it frees capital for names the model actually likes.", [t]))

    strong_missing = [t for t, a in alpha.items()
                      if (a.get("alpha_score") or 0) > 40 and w.get(t, 0) < 10]
    for t in strong_missing[:2]:
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

    tips.sort(key=lambda t: -SEV.get(t["severity"], 0))
    return {
        "suggestions": tips,
        "n_suggestions": len(tips),
        "downside_pct": downside,
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
