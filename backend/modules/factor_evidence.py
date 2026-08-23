"""
factor_evidence.py — what we actually know about each factor, one row each.

The app has been telling users that momentum has not demonstrated a
statistically significant edge in our tested configurations. That sentence is
careful and true, and next to it sat five other factors the app said nothing
about at all. A reader who sees one factor honestly marked as unproven
reasonably concludes the silent ones were checked and passed. They were not.
Saying nothing was the overclaim.

So every factor gets a row, and the row says which of three things is true:

  tested          a walk-forward test ran, and this is what it found
  cannot_test_yet the test cannot be run with the data we hold, for a stated
                  reason that is about data rather than effort
  untested        it could be tested and has not been

The middle state is the interesting one and applies to five of the six.
Quality, growth, value and low_risk read the CURRENT balance sheet, and
sentiment reads current news. Ranking 2022 by a 2026 balance sheet is exactly
the look-ahead bias this app is independently verified not to have, so running
that test would produce a number that looks like evidence and is not.

That is a data problem with a fix already in motion: factor_history records
point-in-time scores from now on. It cannot backfill, so the earliest any of
these five can be tested honestly is one horizon after recording began. This
module computes that date rather than promising it vaguely.
"""

from datetime import datetime, timedelta


# Weights live in alpha_v2; duplicating them here would let the two drift.
def _weights():
    try:
        from alpha_v2 import WEIGHTS_V2
        return dict(WEIGHTS_V2)
    except Exception:
        return {}


LOOKAHEAD_REASON = (
    "Reads the CURRENT balance sheet. A historical test would rank 2022 using "
    "2026 fundamentals, which is the look-ahead bias this app is independently "
    "verified not to have — so the test would produce a number that looks like "
    "evidence and is not one."
)

SENTIMENT_REASON = (
    "Reads current news. Historical headlines for the whole universe are not "
    "stored, so a past ranking cannot be rebuilt as it actually looked at the "
    "time — only as it looks now, which is not the same thing."
)

CANNOT_TEST = {
    "quality":  LOOKAHEAD_REASON,
    "growth":   LOOKAHEAD_REASON,
    "value":    LOOKAHEAD_REASON,
    "low_risk": ("Built from realised volatility and drawdown, which ARE "
                 "reconstructible from prices — but the version scored here is "
                 "blended with current fundamentals, so the same look-ahead "
                 "problem applies to the score as shipped."),
    "sentiment": SENTIMENT_REASON,
}

PLAIN = {
    "momentum":  "Recent price trend",
    "quality":   "Profitability and financial health",
    "growth":    "Revenue and earnings growth",
    "value":     "Cheapness against peers",
    "sentiment": "Tone of recent news",
    "low_risk":  "Volatility and drawdown",
}


def _momentum_row(run_walk_forward: bool):
    """The one factor with a real result. Cached upstream; slow when cold."""
    row = {
        "factor": "momentum",
        "plain": PLAIN["momentum"],
        "status": "tested",
        "why": ("Computed purely from prices, so a past ranking can be rebuilt "
                "exactly as it looked then. That is what makes it testable when "
                "the others are not."),
    }
    if not run_walk_forward:
        row["result"] = None
        return row
    try:
        from walk_forward import run as wf
        r = wf()
        if "error" in r:
            row["result"] = None
            row["note"] = f"Test could not run: {r['error']}"
            return row
        sig = r.get("significance") or {}
        row["result"] = {
            "windows": r.get("windows_tested"),
            "mean_spread_pct": r.get("mean_spread_pct"),
            "hit_rate_pct": r.get("hit_rate_pct"),
            "p_value": sig.get("p_value"),
            "significant_at_5pct": sig.get("significant_at_5pct"),
            "verdict": r.get("verdict"),
        }
    except Exception as e:
        row["result"] = None
        row["note"] = f"Test could not run: {type(e).__name__}"
    return row


def _earliest_testable():
    """
    When the blocked factors could first be tested honestly.

    Point-in-time scores only exist from the day recording started, and a
    forward test needs at least one horizon after that. Returning a computed
    date rather than "soon" keeps this a commitment instead of a hope.
    """
    try:
        from factor_history import coverage
        c = coverage()
        first = c.get("first")
        if not first:
            return {"recording_started": None, "observations": 0,
                    "note": ("Nothing recorded yet, so the clock has not "
                             "started. It starts with the first scan.")}
        start = datetime.fromisoformat(first[:10])
        # A 21-day horizon is what the alpha model advertises, and a handful of
        # non-overlapping windows is the minimum worth calling a test.
        earliest = start + timedelta(days=21 * 6)
        return {
            "recording_started": first,
            "observations": c.get("observations", 0),
            "tickers": c.get("tickers", 0),
            "earliest_meaningful_test": earliest.strftime("%Y-%m-%d"),
            "note": (f"Point-in-time factor scores have been recorded since "
                     f"{first}. Six non-overlapping 21-day windows is the least "
                     f"that is worth calling a test, so the earliest honest "
                     f"answer for these factors is around "
                     f"{earliest.strftime('%d %b %Y')}. It cannot be brought "
                     f"forward by backfilling, because the scores were never "
                     f"stored before."),
        }
    except Exception:
        return {"recording_started": None, "observations": 0}


def evidence(run_walk_forward: bool = True) -> dict:
    """One row per factor, and an honest overall summary."""
    w = _weights()
    rows = [_momentum_row(run_walk_forward)]

    for f in ("quality", "growth", "value", "sentiment", "low_risk"):
        rows.append({
            "factor": f,
            "plain": PLAIN.get(f, f),
            "status": "cannot_test_yet",
            "why": CANNOT_TEST[f],
            "result": None,
        })

    for r in rows:
        r["weight_pct"] = round(w.get(r["factor"], 0) * 100, 1) if w else None

    tested = [r for r in rows if r["status"] == "tested"]
    blocked = [r for r in rows if r["status"] == "cannot_test_yet"]
    weight_tested = sum(r["weight_pct"] or 0 for r in tested)
    weight_blocked = sum(r["weight_pct"] or 0 for r in blocked)

    passed = [r for r in tested
              if (r.get("result") or {}).get("significant_at_5pct") is True]

    return {
        "factors": rows,
        "counts": {"tested": len(tested), "cannot_test_yet": len(blocked),
                   "passed": len(passed)},
        "weight_tested_pct": round(weight_tested, 1),
        "weight_untested_pct": round(weight_blocked, 1),
        # The single most important number on this page, and the one a reader
        # would never guess: most of the score is carried by factors that have
        # never been tested at all.
        "headline": (
            f"{weight_blocked:.0f}% of the model's weight sits in factors that "
            f"have never been tested, because the data needed to test them "
            f"honestly does not exist yet. The {weight_tested:.0f}% that HAS "
            f"been tested — momentum — did not demonstrate a statistically "
            f"significant edge in our tested configurations."
            if not passed else
            f"{weight_tested:.0f}% of the model's weight has been tested; "
            f"{weight_blocked:.0f}% has not."),
        "why_this_table_exists": (
            "The app said momentum was unproven and said nothing about the "
            "other five. A reader who sees one factor honestly marked unproven "
            "reasonably assumes the silent ones were checked and passed. They "
            "were not. Saying nothing was the overclaim, so every factor now "
            "has a row."),
        "unblocking": _earliest_testable(),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
