"""
model_comparison.py — the four-factor model, the six-factor model, and the
portfolio-aware view, compared on what can actually be measured.

The obvious table here has a return column. This one cannot have a return
column, and the reason is the point of the module.

Both alpha models read current fundamentals. Ranking a 2019 universe by them
would use balance sheets published years later, which is look-ahead bias, so
neither has a walk-forward record and neither can be given a CAGR, a Sharpe or
a hit rate. Printing those columns as blanks would suggest the numbers exist
and are merely missing; printing them filled in would be fabrication. So they
are absent and the absence is explained.

What CAN be measured without any forward-looking data:

  agreement   how often the two models reach the same call on the same stock
  coverage    how much of each score rests on data that was actually available
  evidence    what has been tested, which for both models is nothing

Disagreement between two unvalidated models is not evidence that either is
right. It is a measure of how much the extra two factors change the answer,
which is worth knowing before deciding whether they earn their place.
"""

from datetime import datetime


MODELS = {
    "v1": {
        "name": "Four-factor",
        "factors": ["momentum", "quality", "value", "sentiment"],
        "where": "The nightly universe scan",
    },
    "v2": {
        "name": "Six-factor",
        "factors": ["momentum", "quality", "growth", "value", "sentiment", "low_risk"],
        "where": "On demand, per stock",
    },
    "fit": {
        "name": "Portfolio-aware",
        "factors": ["correlation", "sector overlap", "concentration", "liquidity"],
        "where": "Portfolio Fit, per holding against the rest of the book",
    },
}

# One label per model, and every one of them is the same. Saying so plainly is
# more useful than three different shades of hedging.
EVIDENCE = {
    "v1": ("NOT VALIDATED",
           "No walk-forward record. Three of its four factors read current "
           "fundamentals or current news, so a historical test would use "
           "information that did not exist at the time."),
    "v2": ("NOT VALIDATED",
           "Same limitation, plus two more factors with the same problem. Its "
           "one testable factor, momentum, was tested on its own and did not "
           "demonstrate a statistically significant edge in the configurations "
           "tried."),
    "fit": ("NOT VALIDATED",
            "Measures relationships between holdings — correlation, overlap, "
            "concentration — rather than predicting returns. There is no "
            "return claim here to validate, which is different from having a "
            "claim that failed."),
}


def _call(score):
    if score is None:
        return None
    if score >= 10:
        return "BUY"
    if score <= -10:
        return "SELL"
    return "HOLD"


def compare(tickers: list = None, sample: int = 12) -> dict:
    """
    Run both alpha models over a sample and report where they agree.

    Deliberately returns no performance metric for either, because neither has
    one that could be produced without look-ahead.
    """
    tickers = [t.strip().upper() for t in (tickers or []) if t][:max(1, int(sample))]
    if not tickers:
        return {"error": "No tickers supplied."}

    rows, errors = [], {}
    for t in tickers:
        try:
            from alpha_v2 import compute_v2
            r2 = compute_v2(t)
            if "error" in r2:
                errors[t] = r2["error"]
                continue
            s2 = r2.get("alpha_score")
            s1 = r2.get("v1_score")
            rows.append({
                "ticker": t,
                "v1_score": s1,
                "v2_score": s2,
                "v1_call": _call(s1),
                "v2_call": _call(s2),
                "gap": (None if (s1 is None or s2 is None) else round(s2 - s1, 2)),
                "coverage_pct": r2.get("factor_coverage"),
            })
        except Exception as e:
            errors[t] = type(e).__name__

    scored = [r for r in rows if r["v1_call"] and r["v2_call"]]
    same = [r for r in scored if r["v1_call"] == r["v2_call"]]
    flips = [r for r in scored
             if {r["v1_call"], r["v2_call"]} == {"BUY", "SELL"}]
    gaps = [abs(r["gap"]) for r in scored if r["gap"] is not None]

    agreement_pct = round(len(same) / len(scored) * 100, 1) if scored else None
    mean_gap = round(sum(gaps) / len(gaps), 2) if gaps else None

    models = []
    for key, meta in MODELS.items():
        status, why = EVIDENCE[key]
        models.append({
            "key": key, "name": meta["name"], "factors": meta["factors"],
            "n_factors": len(meta["factors"]), "where": meta["where"],
            "evidence_status": status, "evidence_note": why,
            # Explicitly absent, with a reason, rather than blank.
            "return_pct": None, "sharpe": None, "hit_rate_pct": None,
            "metrics_absent_because": (
                "No walk-forward record exists for this model, so a return, a "
                "Sharpe or a hit rate would have to be invented. A blank column "
                "would imply the number exists and is merely missing."),
        })

    return {
        "models": models,
        "sample": {
            "requested": len(tickers),
            "scored": len(scored),
            "errors": errors,
            "rows": rows,
        },
        "agreement": {
            "same_call_pct": agreement_pct,
            "n_same": len(same),
            "n_compared": len(scored),
            "opposite_calls": len(flips),
            "mean_absolute_gap": mean_gap,
            "methodology": (
                f"Both models scored on the same {len(scored)} stocks at the "
                f"same moment, using the same data. A call is BUY above +10, "
                f"SELL below -10, HOLD between. Agreement counts identical "
                f"calls; opposite counts BUY against SELL."),
            "means": (
                "Agreement says how much the two extra factors change the "
                "answer. It says nothing about which model is right — two "
                "unvalidated models agreeing are not more likely to be correct, "
                "they are more likely to share an assumption."),
        },
        "no_performance_columns": (
            "This comparison has no return, Sharpe or hit-rate column. Both "
            "alpha models read current fundamentals, so ranking a past universe "
            "by them would use information published years later. Any "
            "performance figure here would be an artefact of that, so none is "
            "shown and the reason is stated rather than left as an empty cell."),
        "labels_used": ["VALIDATED", "NOT VALIDATED", "INSUFFICIENT DATA",
                        "EXPERIMENTAL"],
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
