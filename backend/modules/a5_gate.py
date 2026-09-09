"""
a5_gate.py — can the archive support the pre-registered momentum validation?

A5 has a stopping rule, and the rule has to be evaluated before any performance
number is computed. Once a mean return is on the screen it is too late to decide
the sample was too small; the number is already anchoring the reading of it. So
this module counts and refuses to score. It contains no return, no Sharpe, no
p-value, and nothing that could be mistaken for a result.

What "independent" means here
-----------------------------
The pre-registered test forms portfolios at month ends and asks whether the top
bucket beats the bottom over a horizon. Consecutive monthly formations share
eleven twelfths of their lookback, so they are not independent draws in the
lookback; what makes two observations independent is that their RETURN periods
do not overlap. For a horizon of h months, that is one usable window every h
months -- which is exactly the arithmetic pit_validation._grade already applies
as `len(months) // horizon`, restated here so the gate and the test agree.

Four counts that get conflated, and must not be
-----------------------------------------------
    raw observations      one security at one formation date
    unique securities     how many distinct companies appear at all
    unique dates          how many formation months exist
    effective sample      how many INDEPENDENT experiments were run

Two thousand stocks scored in the same month are not two thousand experiments.
They mostly measure whether that month was kind to momentum. The primary
hypothesis is tested on the monthly spread series, so the effective sample size
for it is the number of non-overlapping months -- not the number of rows.

No performance number is computed here: no return, no Sharpe, no p-value, and
nothing that could be mistaken for a result. The single exception to "reads
only" is confirmatory_status, which ensures the one-row table recording whether
the confirmatory run has happened -- schema, never data, and never a score.
Nothing here is allowed to change what the model does.
"""

from datetime import datetime

try:
    from db import get_conn
except Exception:                                   # pragma: no cover
    from .db import get_conn

# Read from the frozen validation rather than restated, so the gate cannot
# drift away from the test it is gating.
try:
    from pit_validation import MOM_LOOKBACK, MOM_SKIP, HORIZONS
except Exception:                                   # pragma: no cover
    MOM_LOOKBACK, MOM_SKIP, HORIZONS = 252, 21, (1, 3, 6, 12)

# Pre-registered power requirement. n = ((z_a + z_b) * sd / effect)^2 with
# a two-sided alpha of 0.05 and 80% power gives (1.96 + 0.84) = 2.80, and an
# assumed effect of about 0.2 standard deviations -- a small effect, chosen
# before any result was seen. That is 199 monthly windows for the gross test.
# The net-of-cost effect is roughly half the size, which quadruples the
# requirement to 686 windows, or about 57 years.
REQUIRED_WINDOWS_GROSS = 199
REQUIRED_WINDOWS_NET = 686

# ---------------------------------------------------------------- stopping rule
#
# The 199 threshold protects against testing EARLY. On its own it does nothing
# about testing REPEATEDLY once the count is past it, and that is the way this
# particular gate would most plausibly be broken.
#
# The failure needs no bad intent. The count crosses 199 in early 2029, the test
# runs and returns p = 0.09. Nobody publishes a null. Six months later the
# archive holds 205 windows, so it is run again -- more data, surely better --
# and again at 211, and the first p < 0.05 is the one that gets written down.
# Every individual step looks disciplined. The real false-positive rate is far
# above 5%, and the 199 bar ends up certifying a guarantee it never delivered.
#
# This is the same error as moving 199 to 172, only harder to see, because it is
# distributed across several defensible-looking decisions instead of one
# indefensible one.
#
# So the rule is fixed now, while there is no result to be tempted by:
#
#   The confirmatory test runs ONCE, on the first scan cycle at which the
#   independent-window count reaches REQUIRED_WINDOWS_GROSS, and reports
#   whatever it returns. Any later run is exploratory, is labelled exploratory,
#   and cannot replace the confirmatory result.
#
# The alternative, a sequential design with alpha-spending, legitimately permits
# interim looks by making the early thresholds much stricter. It is a fine
# choice and it is NOT what is adopted here, because it has to be specified in
# advance too and the simpler rule fits what is already built. Recording the
# rejected option matters: choosing it later, after seeing a null at 199, would
# be optional stopping wearing a better suit.
ANALYSIS_RULE = (
    "The confirmatory momentum test runs exactly once, on the first scan cycle "
    "at which independent windows >= 199, and reports whatever it returns. Any "
    "subsequent run is exploratory and cannot replace it. Adopted 2026-09-09, "
    "while the count stood at 171 and no result existed."
)
ANALYSIS_RULE_ADOPTED = "2026-09-09"
ANALYSIS_RULE_ADOPTED_AT_WINDOWS = 171


def _trading_days(conn):
    rows = conn.execute(
        "SELECT DISTINCT day FROM bhavcopy_eod ORDER BY day").fetchall()
    return [str(r[0])[:10] for r in rows if r and r[0]]


def _month_ends(days):
    """(month, index) for the last stored trading day of each month."""
    last = {}
    for i, d in enumerate(days):
        last[d[:7]] = i
    return sorted(last.items())


def confirmatory_status(windows: int = None) -> dict:
    """
    Has the one confirmatory run happened, and is it due?

    Enforcement rather than memory. In 2029 nobody will recall that the rule
    said once; the table will.
    """
    ran = None
    try:
        conn = get_conn()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS a5_confirmatory_run ("
                         "id INTEGER PRIMARY KEY CHECK (id = 1), "
                         "ran_at TEXT NOT NULL, cycle TEXT, windows INTEGER, "
                         "result TEXT)")
            conn.commit()
            row = conn.execute("SELECT ran_at, cycle, windows FROM "
                               "a5_confirmatory_run WHERE id = 1").fetchone()
            ran = {"ran_at": row[0], "cycle": row[1], "windows": row[2]} if row else None
        finally:
            conn.close()
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}"}

    due = windows is not None and windows >= REQUIRED_WINDOWS_GROSS
    return {
        "available": True,
        "rule": ANALYSIS_RULE,
        "adopted": ANALYSIS_RULE_ADOPTED,
        "adopted_at_windows": ANALYSIS_RULE_ADOPTED_AT_WINDOWS,
        "rejected_alternative": ("sequential design with alpha-spending "
                                 "(O'Brien-Fleming); viable, but adopting it "
                                 "later after seeing a null would itself be "
                                 "optional stopping"),
        "already_run": bool(ran),
        "run_record": ran,
        "due_now": bool(due and not ran),
        "status": ("already run — any further run is exploratory" if ran
                   else "due" if due
                   else "not yet due"),
    }


def gate(required: int = REQUIRED_WINDOWS_GROSS) -> dict:
    """
    The counts A5 must clear, and nothing else.

    Returns `proceed: False` with a reason whenever the archive cannot support
    the pre-registered test, so the caller stops rather than reporting an
    underpowered result as a finding.
    """
    conn = get_conn()
    try:
        days = _trading_days(conn)
        if not days:
            return {"available": False, "reason": "no trading days stored"}

        n_secs = conn.execute(
            "SELECT COUNT(DISTINCT isin) FROM bhavcopy_eod "
            "WHERE isin IS NOT NULL").fetchone()[0]

        me = _month_ends(days)
        # A formation date needs MOM_LOOKBACK columns strictly to its left --
        # the same condition _momentum_scores enforces with `a = col - LOOKBACK`.
        formations = [(m, i) for m, i in me if i - MOM_LOOKBACK >= 0]

        # Raw observations: securities priced at BOTH ends of the lookback, per
        # formation date. Counted, not estimated -- the distinction between raw
        # rows and independent windows is the whole point of this gate.
        raw_obs = 0
        per_month = []
        for m, col in formations:
            d_now, d_then = days[col], days[col - MOM_LOOKBACK]
            n = conn.execute(
                "SELECT COUNT(*) FROM ("
                "  SELECT a.isin FROM bhavcopy_eod a "
                "  JOIN bhavcopy_eod b ON a.isin = b.isin "
                "  WHERE a.day = ? AND b.day = ? "
                "    AND a.close IS NOT NULL AND b.close IS NOT NULL "
                "    AND a.isin IS NOT NULL"
                ") t", (d_now, d_then)).fetchone()[0]
            raw_obs += int(n or 0)
            per_month.append({"month": m, "securities": int(n or 0)})
    finally:
        conn.close()

    n_formations = len(formations)
    windows = {h: n_formations // max(h, 1) for h in HORIZONS}
    best_h = min(HORIZONS)
    best = windows[best_h]

    return {
        "available": True,
        "read_only": True,
        "computed_at": datetime.now().isoformat(),

        "archive": {
            "first_day": days[0], "last_day": days[-1],
            "trading_days": len(days),
            "months_spanned": len(me),
            "unique_securities_by_isin": int(n_secs or 0),
        },
        "specification": {
            "lookback_days": MOM_LOOKBACK, "skip_days": MOM_SKIP,
            "horizons_months": list(HORIZONS),
            "formation": "last stored trading day of each month",
            "independence": ("return periods must not overlap; one usable "
                             "window every h months"),
        },

        # -- the four counts, kept apart on purpose ---------------------------
        "counts": {
            "raw_observations": raw_obs,
            "unique_securities": int(n_secs or 0),
            "unique_formation_dates": n_formations,
            "effective_sample_size": best,
            "note": ("raw_observations counts one security at one formation "
                     "date. It is NOT a count of experiments: the stocks in a "
                     "given month share that month's market and mostly measure "
                     "it. The primary hypothesis is tested on the monthly "
                     "spread series, so its effective sample size is the "
                     "number of non-overlapping months."),
        },

        "independent_windows": {str(h): windows[h] for h in HORIZONS},
        "overlapping_excluded": {
            str(h): n_formations - windows[h] for h in HORIZONS},

        "requirement": {
            "gross_windows_required": required,
            "net_of_cost_windows_required": REQUIRED_WINDOWS_NET,
            "basis": ("two-sided alpha 0.05, power 0.80, effect ~0.2 sd for "
                      "gross; the net-of-cost effect is about half that, which "
                      "quadruples the requirement"),
        },

        "stopping_rule": confirmatory_status(best),
        "verdict": {
            "best_horizon_months": best_h,
            "best_horizon_windows": best,
            "clears_gross": best >= required,
            "clears_net_of_cost": best >= REQUIRED_WINDOWS_NET,
            "shortfall_gross": max(0, required - best),
            "years_of_further_history_needed":
                round(max(0, required - best) / 12.0, 1),
        },
        "per_formation_month": per_month[:6] + (
            [{"...": f"{max(0, len(per_month) - 12)} more"}] if len(per_month) > 12 else []
        ) + per_month[-6:],
    }
