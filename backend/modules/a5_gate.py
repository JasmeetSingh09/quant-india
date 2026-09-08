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

Read-only. Nothing here writes, and nothing here is allowed to change what the
model does.
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
