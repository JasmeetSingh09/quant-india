"""
portfolio_score.py — one number, and the five that produced it.

The coach already measures everything needed to judge a portfolio, but it says
so in paragraphs. A reader has to assemble the verdict themselves, and most
will not. This produces the headline they can act on immediately, with the
components visible underneath so the number is never a black box.

Two deliberate choices about what this is NOT:

It is not a quality score. A concentrated portfolio is not a bad portfolio — it
is an aggressive one, and calling that "bad" imports a risk preference the app
does not know. So the label describes the portfolio's character (defensive,
balanced, aggressive, very aggressive) rather than grading it.

It is not personalised. The app does not know anyone's horizon, income, or what
they would do in a 40% drawdown. It can say a portfolio is concentrated and
volatile. It cannot say whether that is appropriate, and the wording keeps that
line intact.
"""

BANDS = [
    (80, "defensive", "Well spread, with no single holding or sector dominating."),
    (60, "balanced", "Reasonably diversified, with some concentration worth watching."),
    (40, "aggressive", "Concentrated. Outcomes will be driven by a few positions."),
    (0, "very aggressive", "Highly concentrated. A small number of holdings decide the result."),
]


def _band(score):
    for cut, label, note in BANDS:
        if score >= cut:
            return label, note
    return BANDS[-1][1], BANDS[-1][2]


def _rate(value, good, bad, invert=False):
    """
    Map a measurement onto 0-100, where 100 means low risk.

    Linear between the two anchors and clamped outside them, so a portfolio that
    is far past 'bad' does not produce a negative component that then drags the
    total into nonsense.
    """
    if value is None:
        return None
    v = float(value)
    if invert:
        good, bad = bad, good
        v = -v
        good, bad = -good, -bad
    if bad == good:
        return 50.0
    pct = (v - bad) / (good - bad)
    return max(0.0, min(1.0, pct)) * 100


def score(holdings: dict, advice: dict = None) -> dict:
    """
    holdings: {ticker: weight_pct}
    advice:   an existing advise() result, reused rather than recomputed.

    Every component is a fact the coach already measured. Nothing new is
    estimated here — this is presentation of existing evidence, which is why it
    can be trusted exactly as much as the evidence is.
    """
    if not holdings:
        return {"error": "No holdings to score."}

    w = {t: float(v) for t, v in holdings.items() if v}
    tot = sum(w.values()) or 1.0
    w = {t: v * 100.0 / tot for t, v in w.items()}
    n = len(w)
    top = max(w.values()) if w else 100.0

    # Effective positions via Herfindahl: 4 equal holdings behave like 4, while
    # 99/1 behaves like 1 however many names are listed.
    shares = [v / 100.0 for v in w.values()]
    hhi = sum(s * s for s in shares) or 1.0
    eff_n = 1.0 / hhi

    adv = advice or {}
    sectors = adv.get("sector_exposure") or {}
    top_sector = max(sectors.values()) if sectors else None
    downside = adv.get("downside_pct")
    kinds = {s.get("kind") for s in (adv.get("suggestions") or [])}
    illiquid = "illiquid" in kinds

    components = {
        "stock_concentration": {
            "value": round(top, 1), "unit": "% in largest holding",
            "score": _rate(top, good=15, bad=50),
            "note": f"Largest holding is {top:.0f}% of the portfolio.",
        },
        "diversification": {
            "value": round(eff_n, 1), "unit": "effective positions",
            "score": _rate(eff_n, good=10, bad=1),
            "note": (f"{n} holdings behave like about {eff_n:.1f} independent "
                     f"positions once weights are accounted for."),
        },
        "sector_concentration": {
            "value": round(top_sector, 1) if top_sector is not None else None,
            "unit": "% in largest sector",
            "score": _rate(top_sector, good=25, bad=60) if top_sector is not None else None,
            "note": (f"Largest sector exposure is {top_sector:.0f}%."
                     if top_sector is not None else "Sector data unavailable."),
        },
        "downside": {
            "value": round(downside, 1) if downside is not None else None,
            "unit": "% simulated worst 5%",
            "score": _rate(abs(downside), good=10, bad=45) if downside is not None else None,
            "note": (f"In the worst 5% of simulations this portfolio falls {abs(downside):.0f}%."
                     if downside is not None else "Downside not simulated."),
        },
        "liquidity": {
            "value": "flagged" if illiquid else "clear",
            "unit": "",
            "score": 40.0 if illiquid else 100.0,
            "note": ("One or more holdings barely trade, so exiting could be hard."
                     if illiquid else "All holdings trade freely enough to exit."),
        },
    }

    scored = [c["score"] for c in components.values() if c["score"] is not None]
    total = round(sum(scored) / len(scored), 1) if scored else None
    label, band_note = _band(total if total is not None else 0)

    # The single most improvable component, named — a score with no lever is a
    # grade, and a grade is not actionable.
    worst_key, worst = None, None
    for k, c in components.items():
        if c["score"] is not None and (worst is None or c["score"] < worst["score"]):
            worst_key, worst = k, c

    return {
        "score": total,
        "label": label,
        "band_note": band_note,
        "components": components,
        "biggest_lever": {"factor": worst_key, "note": worst["note"]} if worst else None,
        "means": ("Describes how concentrated and volatile this portfolio is — not "
                  "whether it is good, and not whether it suits you. The app does "
                  "not know your horizon, your income, or what you would do in a "
                  "40% drawdown."),
    }
