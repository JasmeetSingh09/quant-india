"""
portfolio_fit.py — is this stock attractive, and does it belong in YOUR portfolio?

Those are different questions and the app has only ever answered the first. A
stock can score 91 on its own merits and still be the worst thing you could add,
because you already hold four of its neighbours.

The distinction matters more than it sounds. Attractiveness is a prediction, and
the track record says the model has not yet shown it can make one. Fit is
arithmetic: whether adding a stock raises concentration, whether it moves with
what you already own, whether it puts more weight into a sector that already
dominates. Those answers are true regardless of whether the alpha model works —
which makes fit the more defensible half of the pair.

So the two are scored separately and never blended. A blended number would let a
strong opinion hide a weak one.
"""

import numpy as np


def _correlation_with(ticker: str, holdings: list, days: int = 400):
    """Average correlation of this stock with what is already held."""
    try:
        from datetime import datetime, timedelta
        from portfolio_optimizer import _get_returns
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        universe = list(dict.fromkeys([ticker] + list(holdings)))
        rets = _get_returns(universe, start, end)
        if rets is None or ticker not in rets.columns or len(rets) < 40:
            return None, None
        others = [h for h in holdings if h in rets.columns and h != ticker]
        if not others:
            return None, None
        corrs = {h: float(rets[ticker].corr(rets[h])) for h in others}
        corrs = {h: c for h, c in corrs.items() if c == c}      # drop NaN
        if not corrs:
            return None, None
        return float(np.mean(list(corrs.values()))), corrs
    except Exception:
        return None, None


def fit(ticker: str, holdings: dict, add_pct: float = 10.0) -> dict:
    """
    How well this stock fits a portfolio you already hold.

    holdings: {ticker: weight_pct} of the CURRENT portfolio.
    add_pct:  the weight you are considering giving it.

    Returns a 0-100 fit score with its components, and never mixes it with the
    stock's own alpha score.
    """
    ticker = (ticker or "").strip().upper()
    cur = {t.strip().upper(): float(v) for t, v in (holdings or {}).items() if v}
    if not cur:
        return {"error": "No current holdings to fit against."}
    if ticker in cur:
        return {"held": True, "current_weight_pct": round(cur[ticker], 2),
                "note": f"You already hold {ticker.replace('.NS','')} at "
                        f"{cur[ticker]:.0f}%. Adding more raises concentration "
                        f"rather than diversifying."}

    parts = {}

    # 1. Sector overlap — the single biggest driver of fit in practice.
    try:
        from portfolio_advisor import _sector_of, _sector_exposure
        sec = _sector_of(ticker)
        exposure = _sector_exposure(cur)
        cur_sec = exposure.get(sec, 0.0) if sec else None
        if sec and cur_sec is not None:
            after = (cur_sec + add_pct) / (100 + add_pct) * 100
            # 0% in the sector is a perfect fit; 50% already there is a poor one.
            score = max(0.0, min(1.0, 1 - cur_sec / 50.0)) * 100
            parts["sector"] = {
                "score": round(score, 1),
                "detail": (f"You hold {cur_sec:.0f}% in {sec}. Adding "
                           f"{add_pct:.0f}% here would make it {after:.0f}%."),
            }
        elif sec:
            parts["sector"] = {"score": 100.0,
                               "detail": f"{sec} is a sector you do not currently hold."}
    except Exception:
        pass

    # 2. Correlation with what is already owned.
    avg_c, per = _correlation_with(ticker, list(cur))
    if avg_c is not None:
        # 0.0 average correlation is ideal diversification; 0.8 is nearly a duplicate.
        score = max(0.0, min(1.0, (0.8 - avg_c) / 0.8)) * 100
        worst = max(per, key=per.get) if per else None
        parts["correlation"] = {
            "score": round(score, 1),
            "avg_correlation": round(avg_c, 2),
            "closest_holding": worst.replace(".NS", "") if worst else None,
            "closest_correlation": round(per[worst], 2) if worst else None,
            "detail": (f"Average correlation {avg_c:.2f} with what you hold"
                       + (f"; closest is {worst.replace('.NS','')} at {per[worst]:.2f}."
                          if worst else ".")),
        }

    # 3. What it does to concentration.
    try:
        from portfolio_score import score as _pscore
        after_w = {t: v * 100 / (100 + add_pct) for t, v in cur.items()}
        after_w[ticker] = add_pct * 100 / (100 + add_pct)
        before = _pscore(cur) or {}
        after = _pscore(after_w) or {}
        b, a = before.get("score"), after.get("score")
        if b is not None and a is not None:
            # Improving the portfolio's health is a good fit; worsening it is not.
            delta = a - b
            parts["concentration"] = {
                "score": round(max(0.0, min(100.0, 50 + delta * 2.5)), 1),
                "health_before": b, "health_after": a,
                "detail": (f"Portfolio health {b:.0f} → {a:.0f} "
                           f"({'+' if delta >= 0 else ''}{delta:.0f})."),
            }
    except Exception:
        pass

    scored = [p["score"] for p in parts.values() if p.get("score") is not None]
    total = round(sum(scored) / len(scored), 1) if scored else None

    if total is None:
        verdict = "Not enough data to judge fit."
    elif total >= 70:
        verdict = ("Fits well. It brings something your portfolio does not already "
                   "have.")
    elif total >= 45:
        verdict = ("Adds little diversification. It overlaps with what you hold, "
                   "so it mostly increases an existing bet.")
    else:
        verdict = ("Poor fit. This is close to doubling a position you already "
                   "have, whatever the stock's own merits.")

    weakest = min(parts.items(), key=lambda kv: kv[1].get("score", 100)) if parts else None

    return {
        "ticker": ticker,
        "fit_score": total,
        "components": parts,
        "verdict": verdict,
        "main_reason": weakest[1]["detail"] if weakest else None,
        "means": ("Fit is about YOUR portfolio, not about the stock. A stock can "
                  "score highly on its own merits and still fit badly here, and "
                  "the two numbers are kept separate for that reason."),
        "why_this_is_the_reliable_half": (
            "Whether this stock beats the market is a prediction, and the track "
            "record has not shown the model can make one. Whether it raises your "
            "concentration is arithmetic, and it is true either way."),
    }
