"""
regime_weights.py — should the factor weights change with the market?

The idea is sound and widely used: quality and low-risk tend to matter more in a
drawdown, momentum more in a trending market. The implementation here is
deliberately cautious, because the evidence to set these weights does not exist
yet on this universe.

What the walk-forward test found: momentum did not demonstrate a
statistically significant edge across 42 non-overlapping 21-day windows —
mean spread 0.029%, win rate exactly 50%, p = 1.0. That is a statement about
this implementation on this universe, not about momentum in general. But if a
factor has not been shown to separate winners from losers here, tilting toward
it in a bull market is still a guess dressed as a rule.

So this ships as a PROPOSAL rather than a default. It computes what the weights
would become, shows them beside the fixed ones, and states plainly that the
tilts are conventional priors and not measured on this data. Turning it on
should follow evidence, not the other way round.
"""

# Multipliers applied to the base weights, by regime. Conventional priors, drawn
# from what the literature generally reports — NOT fitted to this universe, which
# is the entire caveat.
TILTS = {
    "Bull":     {"momentum": 1.30, "growth": 1.20, "value": 0.85,
                 "quality": 0.90, "low_risk": 0.70, "sentiment": 1.10},
    "Sideways": {"momentum": 1.00, "growth": 1.00, "value": 1.00,
                 "quality": 1.00, "low_risk": 1.00, "sentiment": 1.00},
    "Bear":     {"momentum": 0.70, "growth": 0.75, "value": 1.15,
                 "quality": 1.35, "low_risk": 1.50, "sentiment": 0.85},
}

RATIONALE = {
    "Bull": ("Trends persist longer in expansions, so momentum and growth are "
             "tilted up and defensive factors down."),
    "Sideways": "No tilt. Without a clear regime there is nothing to lean on.",
    "Bear": ("Balance-sheet strength and low volatility have historically held up "
             "better in drawdowns, so quality and low-risk are tilted up and "
             "momentum down — momentum reverses hardest at turning points."),
}


def current_regime():
    """The regime the HMM currently assigns, or None."""
    try:
        from regime_detector import detect_regime
        r = detect_regime()
        if isinstance(r, dict):
            return r.get("current_regime"), r.get("current_proba_display")
    except Exception:
        pass
    try:
        from regime_detector import analyze_regime
        r = analyze_regime()
        return (r or {}).get("current_regime"), (r or {}).get("current_proba_display")
    except Exception:
        return None, None


def proposed_weights(regime: str = None) -> dict:
    """
    What the weights would be under regime tilting, beside what they are now.

    Returned as a proposal. Nothing in the scoring path uses these unless someone
    deliberately switches them on, and the response says why that would be
    premature.
    """
    from alpha_v2 import WEIGHTS_V2

    detected, proba = (None, None)
    if regime is None:
        detected, proba = current_regime()
        regime = detected or "Sideways"

    tilt = TILTS.get(regime, TILTS["Sideways"])
    raw = {k: WEIGHTS_V2[k] * tilt.get(k, 1.0) for k in WEIGHTS_V2}
    tot = sum(raw.values()) or 1.0
    proposed = {k: round(v / tot, 4) for k, v in raw.items()}

    # Rounding six values to four places leaves the total slightly off 1.0.
    # Harmless while these are only displayed, and not harmless if they are ever
    # applied — every score would be scaled by that error. The remainder goes to
    # the largest weight, where it is proportionally smallest.
    drift = round(1.0 - sum(proposed.values()), 6)
    if abs(drift) > 1e-9:
        biggest_w = max(proposed, key=proposed.get)
        proposed[biggest_w] = round(proposed[biggest_w] + drift, 6)

    biggest = max(proposed, key=lambda k: proposed[k] - WEIGHTS_V2[k])
    smallest = min(proposed, key=lambda k: proposed[k] - WEIGHTS_V2[k])

    return {
        "regime": regime,
        "regime_detected": detected,
        "regime_probability": proba,
        "current_weights": WEIGHTS_V2,
        "proposed_weights": proposed,
        "biggest_increase": biggest,
        "biggest_decrease": smallest,
        "rationale": RATIONALE.get(regime),
        "active": False,
        "why_not_active": (
            "These tilts are conventional priors, not measured on this universe. "
            "The walk-forward test found momentum did not demonstrate a "
            "significant edge across 42 non-overlapping windows — mean spread "
            "0.03%, win rate exactly 50%. "
            "Tilting toward a factor that has not been shown to work would be a "
            "guess with extra steps, so this is shown and not applied."),
        "what_would_justify_it": (
            "Walk-forward results split by regime: if momentum's spread is "
            "reliably positive in bull windows and negative in bear ones, the "
            "tilt has earned its place. That test needs more history than is "
            "stored today."),
    }
