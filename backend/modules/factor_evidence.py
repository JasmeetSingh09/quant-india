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
    "sentiment": SENTIMENT_REASON,
}

# low_risk was listed above as untestable, on the stated grounds that the
# shipped version is "blended with current fundamentals". That was wrong about
# our own code: alpha_v2._low_risk_factor takes a price series, computes
# annualised volatility and worst drawdown, and combines them 60/40. No
# fundamental touches it. With daily closes now stored for the whole archive it
# is reconstructible at any past date, and it is tested in pit_validation.
#
# Correcting this moves a fifth of the model's weight out of the untested
# column, which is a large enough change to the headline that it is written
# down here rather than quietly edited.
RECONSTRUCTIBLE_FROM_PRICES = {
    "momentum": ("12-1 return over the stock's own price history, "
                 "volatility-adjusted. Every input is a past price."),
    "low_risk": ("Annualised volatility and worst drawdown over a trailing "
                 "window. Every input is a past price — the earlier claim that "
                 "this factor was blended with current fundamentals was "
                 "incorrect about the shipped code."),
}

# Results of the pre-registered tests, as recorded in docs/. These are fixed
# records of runs that already happened, not recomputed here: each one was
# committed with its rules before it ran, and re-running it on every page load
# would take minutes. Update this table only from a new committed result.
#
# Until 2026-09-23 the default response (no walk-forward run) said momentum
# "did not demonstrate a statistically significant edge", which was true of an
# earlier Yahoo-price walk-forward and false after the point-in-time tests.
RECORDED = {
    "momentum": {
        "significant_at_5pct": True,
        "p_value": 0.0001,
        "mean_spread_pct": 1.54,
        "summary": ("Top fifth beat bottom fifth by 1.54% a month on point-in-time "
                    "prices, 2011-2026, delisted stocks included (p = 0.0001). Held "
                    "among stocks trading Rs 10 crore+ a month (+1.11%, p = 0.007), "
                    "held from 2019 on (+1.49%, p = 0.007), and tracked IIMA's "
                    "independent momentum factor (correlation 0.80)."),
        "caveat": ("Not shown among the largest, most liquid stocks: +0.07% a month "
                   "in the most liquid third (p = 0.82), and not significant at a "
                   "Rs 50 crore floor (p = 0.063). No trading costs; signal only."),
        "source": ["docs/FACTOR_TEST1_RESULT_2026-09-13.md",
                   "docs/MOMENTUM_ROBUSTNESS_RESULT_2026-09-18.md"],
    },
    "low_risk": {
        "significant_at_5pct": False,
        "p_value": 0.091,
        "mean_spread_pct": 0.96,
        "summary": ("Tested on point-in-time prices at four holding periods; no "
                    "period passed the pre-registered threshold (1-month spread "
                    "+0.96%, p = 0.091)."),
        "source": ["docs/FACTOR_TEST1_RESULT_2026-09-13.md"],
    },
}

# What independent academic data says about the IDEA behind a factor we
# cannot yet test as we compute it. Support for an idea is not a test of our
# score, and the rows say so.
IDEA_EVIDENCE = {
    "value": ("The idea is supported: a book-to-market value premium of +0.71% a "
              "month in India, 1993-2025 (IIMA factor library, p = 0.015), and "
              "+0.66% a month across emerging markets including India (Fama-French "
              "library). Our value score itself is untested."),
    "quality": ("The idea is supported: a profitability premium of +0.23% a month "
                "across emerging markets including India, 1991-2026 (Fama-French "
                "library, p = 0.012). Our quality score uses a different measure "
                "and is untested."),
    "sentiment": ("Being tested: seven years of dated headlines (GDELT) are being "
                  "collected so past news can be scored as it was published."),
}


def _v1_weights():
    try:
        from alpha_model import FACTOR_WEIGHTS
        return dict(FACTOR_WEIGHTS)
    except Exception:
        return {}


PLAIN = {
    "momentum":  "Recent price trend",
    "quality":   "Profitability and financial health",
    "growth":    "Revenue and earnings growth",
    "value":     "Cheapness against peers",
    "sentiment": "Tone of recent news",
    "low_risk":  "Volatility and drawdown",
}


def _momentum_row(run_walk_forward: bool):
    """Momentum's recorded point-in-time result, plus the walk-forward on request."""
    rec = RECORDED["momentum"]
    row = {
        "factor": "momentum",
        "plain": PLAIN["momentum"],
        "status": "tested",
        "why": ("Computed purely from prices, so a past ranking can be rebuilt "
                "exactly as it looked then. That is what makes it testable when "
                "the others are not."),
        "result": {k: rec[k] for k in ("significant_at_5pct", "p_value",
                                       "mean_spread_pct", "summary", "caveat",
                                       "source")},
    }
    if not run_walk_forward:
        return row
    # The older walk-forward runs on Yahoo prices, which carry survivorship
    # bias. Reported beside the point-in-time result, never instead of it.
    try:
        from walk_forward import run as wf
        r = wf()
        if "error" in r:
            row["walk_forward_note"] = f"Walk-forward could not run: {r['error']}"
            return row
        sig = r.get("significance") or {}
        row["walk_forward"] = {
            "windows": r.get("windows_tested"),
            "mean_spread_pct": r.get("mean_spread_pct"),
            "hit_rate_pct": r.get("hit_rate_pct"),
            "p_value": sig.get("p_value"),
            "significant_at_5pct": sig.get("significant_at_5pct"),
            "verdict": r.get("verdict"),
        }
    except Exception as e:
        row["walk_forward_note"] = f"Walk-forward could not run: {type(e).__name__}"
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

    lr = RECORDED["low_risk"]
    rows.append({
        "factor": "low_risk",
        "plain": PLAIN.get("low_risk", "low_risk"),
        "status": "tested",
        "why": RECONSTRUCTIBLE_FROM_PRICES["low_risk"],
        "where": ("Tested in the point-in-time validation at /validation/pit, "
                  "on the same archive and the same identity resolution as the "
                  "corrected backtest."),
        "result": {k: lr[k] for k in ("significant_at_5pct", "p_value",
                                      "mean_spread_pct", "summary", "source")},
    })

    for f in ("quality", "growth", "value", "sentiment"):
        row = {
            "factor": f,
            "plain": PLAIN.get(f, f),
            "status": "cannot_test_yet",
            "why": CANNOT_TEST[f],
            "result": None,
        }
        if f in IDEA_EVIDENCE:
            row["idea_evidence"] = IDEA_EVIDENCE[f]
        rows.append(row)

    # weight_pct is V2's weight (this table began as V2's). Every live score,
    # label and Top Pick comes from V1, so its weight travels beside it.
    v1 = _v1_weights()
    for r in rows:
        r["weight_pct"] = round(w.get(r["factor"], 0) * 100, 1) if w else None
        r["weight_v1_pct"] = round(v1.get(r["factor"], 0) * 100, 1) if v1 else None

    tested = [r for r in rows if r["status"] == "tested"]
    testable = [r for r in rows if r["status"] == "testable_now"]
    blocked = [r for r in rows if r["status"] == "cannot_test_yet"]
    weight_tested = sum(r["weight_pct"] or 0 for r in tested)
    weight_testable = sum(r["weight_pct"] or 0 for r in testable)
    weight_blocked = sum(r["weight_pct"] or 0 for r in blocked)

    passed = [r for r in tested
              if (r.get("result") or {}).get("significant_at_5pct") is True]
    failed = [r for r in tested
              if (r.get("result") or {}).get("significant_at_5pct") is False]

    def _v1(names):
        return sum(r["weight_v1_pct"] or 0 for r in rows if r["factor"] in names)

    v1_passed = _v1({r["factor"] for r in passed})
    v1_blocked = _v1({r["factor"] for r in blocked})

    return {
        "factors": rows,
        "counts": {"tested": len(tested), "testable_now": len(testable),
                   "cannot_test_yet": len(blocked), "passed": len(passed),
                   "failed": len(failed)},
        "weight_tested_pct": round(weight_tested, 1),
        "weight_testable_pct": round(weight_testable, 1),
        "weight_untested_pct": round(weight_blocked, 1),
        "weight_v1_passed_pct": round(v1_passed, 1),
        "weight_v1_untested_pct": round(v1_blocked, 1),
        # Built from the rows, so it cannot contradict them. Leads with the
        # live model (V1), because that is what every signal on screen is.
        "headline": (
            f"In the live model, momentum ({v1_passed:.0f}% of the score) has "
            f"passed pre-registered point-in-time tests, but its edge was not "
            f"shown among the largest, most liquid stocks. The other "
            f"{v1_blocked:.0f}% (quality, value, sentiment) cannot yet be tested "
            f"as we compute them; academic data supports the value and quality "
            f"ideas. The combined score and its labels have not been tested."
            + (" Low risk, used only in the six-factor model, was tested and "
               "did not pass." if failed else "")),
        "why_this_table_exists": (
            "A reader who sees one factor marked as tested reasonably assumes "
            "the silent ones were checked and passed. They were not. Saying "
            "nothing was the overclaim, so every factor now has a row, "
            "including the ones that failed or cannot be tested yet."),
        "unblocking": _earliest_testable(),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
