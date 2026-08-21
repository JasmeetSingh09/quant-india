"""
optimizer_stability.py — would slightly different assumptions give a completely
different portfolio?

This is the sharpest question anyone can ask a mean-variance optimiser, and the
usual answer is yes. The method is famous for it: expected returns are estimated
with enormous error, the optimiser treats them as exact, and it "error-maximises"
— pushing weight toward whichever asset the noise happened to flatter. A
difference of a few basis points in an estimate nobody can measure to within
several percent can swing an allocation from nothing to a third of the book.

A single set of weights hides all of that. It arrives looking like an answer.

So this re-runs the optimisation many times with expected returns perturbed
inside their own estimation error, and reports how far the weights actually
move. A portfolio whose weights barely shift is telling you the solution is
driven by the covariance structure. One that swings wildly is telling you the
solution is driven by noise, and should be held loosely or constrained harder.

The perturbation is deliberately modest. It is not a stress test of the market;
it is a test of whether the optimiser's own inputs are precise enough to justify
the precision of its output.
"""

import numpy as np

DEFAULT_TRIALS = 60


def _weights_vector(res: dict, tickers: list):
    """Pull weights out of an optimiser result in whatever shape it used."""
    for key in ("optimal_pct", "weights_pct", "weights", "optimal_weights"):
        w = res.get(key)
        if isinstance(w, dict) and w:
            v = np.array([float(w.get(t, 0.0)) for t in tickers], dtype=float)
            s = v.sum()
            if s > 0:
                return v / s
    return None


def stability(tickers: list, target: str = "max_sharpe",
              max_weight: float = 1.0, period_months: int = 24,
              trials: int = DEFAULT_TRIALS, noise_scale: float = 1.0,
              seed: int = 7) -> dict:
    """
    Re-optimise with jittered expected returns and measure how far weights move.

    noise_scale is a fraction of each asset's own return standard error, so the
    perturbation is sized to how badly that asset's mean is actually estimated
    rather than being an arbitrary percentage. An asset whose returns are noisy
    gets jittered more, which is the honest treatment.
    """
    from portfolio_optimizer import mean_variance_optimize, _get_returns
    from datetime import datetime, timedelta

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")
    rets = _get_returns(tickers, start, end)
    if rets is None or rets.empty:
        return {"error": "No return data for these tickers."}
    valid = [t for t in tickers if t in rets.columns]
    if len(valid) < 2:
        return {"error": "Need at least 2 tickers with data."}
    rets = rets[valid]

    base = mean_variance_optimize(valid, target=target, max_weight=max_weight,
                                  period_months=period_months)
    if "error" in base:
        return {"error": base["error"]}
    w_base = _weights_vector(base, valid)
    if w_base is None:
        return {"error": "Could not read baseline weights."}

    # Standard error of each mean: sigma / sqrt(n), annualised the same way the
    # optimiser annualises. This is the size of the uncertainty already present
    # in the number the optimiser treats as exact.
    n_obs = max(2, len(rets))
    se = (rets.std().values * np.sqrt(252)) / np.sqrt(n_obs)

    rng = np.random.default_rng(seed)
    runs = []
    for _ in range(max(5, int(trials))):
        shift = rng.normal(0.0, noise_scale, size=len(valid)) * se
        r = mean_variance_optimize(valid, target=target, max_weight=max_weight,
                                   period_months=period_months,
                                   _mu_shift=shift.tolist())
        if isinstance(r, dict) and "error" not in r:
            w = _weights_vector(r, valid)
            if w is not None:
                runs.append(w)

    if len(runs) < 5:
        return {"error": "Could not complete enough trials to judge stability."}

    W = np.vstack(runs)
    per_asset_sd = W.std(axis=0) * 100
    # Mean absolute deviation from the baseline allocation, in percentage points.
    mad = float(np.abs(W - w_base).mean() * 100)
    worst_i = int(np.argmax(per_asset_sd))

    top_weight = float(w_base.max()) * 100

    # A corner solution does not move, and calling that "stable" is the most
    # dangerous thing this function could say. An unconstrained max-Sharpe
    # optimiser routinely puts everything in one name; the weights then sit
    # still under perturbation not because the answer is robust but because the
    # optimiser is pinned to a single estimate with nowhere else to go.
    if top_weight > 90:
        verdict = (f"Pinned to one holding. The optimiser puts {top_weight:.0f}% in "
                   f"a single stock and keeps it there under perturbation. That is "
                   f"not robustness — it is what mean-variance does when left "
                   f"unconstrained: it backs whichever asset the return estimate "
                   f"happened to favour and ignores the rest. Set a maximum weight "
                   f"per stock, or use HRP or risk parity, which do not depend on "
                   f"expected returns at all.")
    elif mad < 2:
        verdict = ("Stable. Weights barely move when expected returns are jittered "
                   "within their own estimation error, so this allocation is being "
                   "driven by the covariance structure rather than by return "
                   "estimates nobody can measure precisely.")
    elif mad < 6:
        verdict = ("Moderately sensitive. Weights shift noticeably under small, "
                   "realistic changes to the return estimates. Treat the exact "
                   "percentages as approximate.")
    else:
        verdict = ("Unstable. Small changes to inputs nobody can estimate "
                   "accurately produce large changes in the answer. The precision "
                   "of these weights is not real — cap position sizes or use a "
                   "method that does not depend on expected returns, such as HRP "
                   "or risk parity.")

    return {
        "trials": len(runs),
        "baseline_pct": {t: round(float(w) * 100, 2) for t, w in zip(valid, w_base)},
        "weight_sd_pct": {t: round(float(sd), 2) for t, sd in zip(valid, per_asset_sd)},
        "mean_abs_shift_pct": round(mad, 2),
        "top_weight_pct": round(top_weight, 2),
        "corner_solution": bool(top_weight > 90),
        "least_stable": valid[worst_i],
        "least_stable_sd_pct": round(float(per_asset_sd[worst_i]), 2),
        "verdict": verdict,
        "method": (f"{len(runs)} re-optimisations with expected returns perturbed by "
                   f"{noise_scale:.2f}x each asset's own standard error. Covariance "
                   f"is held fixed, so this isolates sensitivity to the return "
                   f"estimate — the input the method is most fragile to."),
        "why": ("Mean-variance optimisation error-maximises: it pushes weight toward "
                "whichever asset the estimation noise happened to flatter. A single "
                "set of weights hides that entirely."),
    }


def concentration_warning(weights_pct: dict) -> dict | None:
    """
    Flag an optimiser output that is concentrated regardless of how it got there.

    A mathematically optimal 48% in one name is still 48% in one name, and the
    number arriving from an optimiser makes it feel earned rather than risky.
    """
    if not weights_pct:
        return None
    items = sorted(weights_pct.items(), key=lambda kv: -float(kv[1] or 0))
    top_t, top_w = items[0][0], float(items[0][1] or 0)
    top3 = sum(float(v or 0) for _, v in items[:3])
    effective_n = 0.0
    tot = sum(float(v or 0) for _, v in items)
    if tot > 0:
        shares = [float(v or 0) / tot for _, v in items]
        hhi = sum(x * x for x in shares)
        effective_n = round(1 / hhi, 1) if hhi > 0 else 0.0

    msgs = []
    if top_w > 40:
        msgs.append(f"{top_t.replace('.NS','')} is {top_w:.0f}% of the portfolio")
    # The top-3 share is only meaningful against what equal weighting would give.
    # With four holdings, "top 3 = 75%" IS equal weighting, and flagging it as
    # concentration would warn about the most diversified portfolio available at
    # that size. Compare to 3/N plus a margin instead of a flat threshold.
    if len(items) > 3:
        equal_top3 = 3.0 / len(items) * 100
        if top3 > max(70.0, equal_top3 + 15):
            msgs.append(f"the top 3 holdings are {top3:.0f}%")
    if effective_n and effective_n < 3:
        msgs.append(f"this behaves like about {effective_n:.1f} independent positions")

    if not msgs:
        return None
    return {
        "concentrated": True,
        "effective_positions": effective_n,
        "top_holding": top_t,
        "top_weight_pct": round(top_w, 2),
        "message": ("Concentration warning: " + "; ".join(msgs) + ". "
                    "An optimiser produced this, which makes it feel earned — but a "
                    "large weight usually reflects confidence in a return estimate "
                    "that carries a wide margin of error. Cap position sizes if you "
                    "want the result to survive being wrong."),
    }
