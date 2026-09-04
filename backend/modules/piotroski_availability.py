"""
piotroski_availability.py — what the source actually supplied, per cycle.

Read-only. It writes nothing, re-fetches nothing, and scores nothing. Every
number comes from rows already in `factor_inputs`.

Why this exists
---------------
An F-score of 3 is not self-explaining. It might mean six conditions were
tested and failed, or that six could not be tested at all. For the 13,256
observations recorded before the presence set was captured, nothing in the
record distinguishes those, and no backfill can recover it — today's Yahoo
response is not what a past cycle saw.

From the cycle of 2026-09-05 onward each observation carries the set of inputs
that were present. This aggregates them so availability becomes something the
application measures about itself, on its own universe, over time — rather than
a one-off survey run from somebody's laptop.

What it deliberately does not do
--------------------------------
It does not judge. A low availability count is a fact about the source on that
date, not a verdict on the company or on the Piotroski definition. Whether the
implementation should consume different inputs is a model-policy question and
nothing here answers it.
"""

import time

from db import get_conn, IS_POSTGRES

# Kept local rather than imported from metrics, which pulls yfinance and the
# whole fetch stack. A read-only reporter should not drag a network client in.
PIOTROSKI_INPUTS = ("returnOnAssets", "operatingCashflow", "currentRatio",
                    "longTermDebt", "grossMargins", "revenueGrowth",
                    "totalAssets", "totalStockholderEquity")

# The two legs each input can decide, for reading the distribution against what
# it costs. no_dilution is absent because it depends on no input at all.
DECIDES = {
    "returnOnAssets": ("roa_positive", "roa_above_5pct"),
    "operatingCashflow": ("cfo_positive", "cfo_beats_roa"),
    "currentRatio": ("current_ratio_above_1",),
    "longTermDebt": ("low_leverage",),
    "grossMargins": ("gross_margin_above_20pct",),
    "revenueGrowth": ("positive_revenue_growth",),
    "totalAssets": ("cfo_beats_roa",),
    "totalStockholderEquity": ("low_leverage",),
}

MAX_CYCLES = 60


def _q(conn, sql, args=(), one=True, default=0):
    """Query, and leave the connection usable if it fails.

    On Postgres a failed statement aborts the whole transaction, so without the
    rollback one missing table makes every later query report an error about
    tables that are perfectly fine. Learned the hard way in cycle_audit.
    """
    try:
        rows = conn.execute(sql, args).fetchall()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return default if one else []
    if not one:
        return rows
    return rows[0][0] if rows else default


def _per_cycle(conn):
    """One row per cycle that carries presence data at all."""
    rows = _q(conn,
              "SELECT cycle_id, COUNT(*), AVG(value_num), MIN(value_num), "
              "MAX(value_num) FROM factor_inputs "
              "WHERE factor='quality' AND input_name='piotroski_inputs_available' "
              "GROUP BY cycle_id ORDER BY cycle_id DESC",
              (), one=False)
    out = []
    for r in rows[:MAX_CYCLES]:
        out.append({
            "cycle": r[0], "observations": int(r[1] or 0),
            "mean_inputs": round(float(r[2] or 0), 2),
            "min_inputs": int(r[3] or 0), "max_inputs": int(r[4] or 0),
        })
    return out


def report(cycle: str = None) -> dict:
    """Availability for one cycle, plus the trend across every cycle recorded."""
    t0 = time.time()
    out = {"available": True, "read_only": True,
           "declared_inputs": list(PIOTROSKI_INPUTS)}
    conn = get_conn()
    try:
        cycles = _per_cycle(conn)
        out["by_cycle"] = cycles
        if not cycles:
            out["cycle"] = cycle
            out["note"] = (
                "No cycle carries a Piotroski presence set yet. It is recorded "
                "from the first scan after the capture shipped; earlier "
                "observations have none and cannot be given any, because "
                "today's source response is not what those cycles saw.")
            out["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
            out["dialect"] = "postgres" if IS_POSTGRES else "sqlite"
            return out

        cycle = cycle or cycles[0]["cycle"]
        out["cycle"] = cycle

        n = _q(conn, "SELECT COUNT(*) FROM factor_inputs WHERE factor='quality' "
                     "AND input_name='piotroski_inputs_available' AND cycle_id=?",
               (cycle,))
        out["observations"] = n
        if not n:
            out["note"] = (f"Cycle {cycle} carries no presence set. Cycles that "
                           f"do: {[c['cycle'] for c in cycles][:6]}")
            out["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
            return out

        # How many of the eight were present, per stock.
        dist = _q(conn,
                  "SELECT value_num, COUNT(*) FROM factor_inputs "
                  "WHERE factor='quality' AND input_name='piotroski_inputs_available' "
                  "AND cycle_id=? GROUP BY value_num ORDER BY value_num",
                  (cycle,), one=False)
        counts = {int(r[0] or 0): int(r[1]) for r in dist}
        out["inputs_present_distribution"] = [
            {"inputs_present": k, "stocks": counts.get(k, 0),
             "pct": round(100.0 * counts.get(k, 0) / n, 2)} for k in range(9)]
        tot = sum(k * v for k, v in counts.items())
        out["mean_inputs_present"] = round(tot / n, 3)

        # Per field. The presence set is stored as its text form, and no field
        # name is a substring of another, so containment is exact here.
        per = []
        for f in PIOTROSKI_INPUTS:
            c = _q(conn,
                   "SELECT COUNT(*) FROM factor_inputs WHERE factor='quality' "
                   "AND input_name='piotroski_inputs' AND cycle_id=? "
                   "AND value_text LIKE ?", (cycle, f"%{f}%"))
            per.append({"input": f, "present": c,
                        "missing": n - c,
                        "available_pct": round(100.0 * c / n, 2),
                        "decides_legs": list(DECIDES.get(f, ()))})
        per.sort(key=lambda x: -x["available_pct"])
        out["by_input"] = per
        out["never_supplied"] = [p["input"] for p in per if p["present"] == 0]

        # F-score against how much evidence stood behind it.
        pairs = _q(conn,
                   "SELECT a.value_num, b.value_num FROM factor_inputs a "
                   "JOIN factor_inputs b ON a.ticker=b.ticker "
                   "AND a.cycle_id=b.cycle_id "
                   "WHERE a.cycle_id=? AND a.factor='quality' "
                   "AND a.input_name='piotroski' AND b.factor='quality' "
                   "AND b.input_name='piotroski_inputs_available'",
                   (cycle,), one=False)
        grid = {}
        for f_score, avail in pairs:
            if f_score is None or avail is None:
                continue
            grid.setdefault(int(f_score), {}).setdefault(int(avail), 0)
            grid[int(f_score)][int(avail)] += 1
        out["f_score_by_inputs_present"] = [
            {"f_score": f, "by_inputs": dict(sorted(v.items())),
             "stocks": sum(v.values())}
            for f, v in sorted(grid.items())]
        if grid:
            out["max_f_observed"] = max(grid)

        out["interpretation"] = (
            "available_pct is what the source supplied on this date, nothing "
            "more. A leg whose inputs were absent was scored 0 by the frozen "
            "V1.4 rule, which is why a low count and a low F-score travel "
            "together — that is the recorded behaviour, not a judgement of the "
            "company.")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    out["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
    out["dialect"] = "postgres" if IS_POSTGRES else "sqlite"
    return out


def availability(cycle: str = None) -> dict:
    """Public entry point. Returns its own failure instead of raising one."""
    try:
        return report(cycle)
    except Exception as e:
        import traceback
        return {"available": False, "cycle": cycle,
                "reason": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[-1500:]}
