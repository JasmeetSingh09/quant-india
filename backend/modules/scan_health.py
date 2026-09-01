"""
scan_health.py — did the collector actually collect?

The factor history cannot be backfilled. The endpoint that serves it says so:
the per-factor scores were never stored before it shipped, so a day the scan
failed to complete is a day of research data that no later effort recovers.
That makes the scan's reliability a research question, not an ops question,
and it deserves measurement rather than a green tick.

This module measures. It changes nothing.

What it looks for
-----------------
COMPLETION      A cycle is marked complete the moment the worker pool drains,
                regardless of how many stocks actually scored. A pass where
                1,900 of 2,574 errored is recorded exactly like a clean one.
                So completion is recomputed here from the rows themselves.

CONTINUITY      Scan progress is written per stock with a timestamp. Long gaps
                between consecutive writes are the instance sleeping or being
                restarted, and they are visible in the data rather than needing
                a log.

CADENCE         Cycle ids are calendar days. A pass that cannot finish inside
                one day never finishes at all: at midnight the id changes and
                the next pass starts from zero, stranding everything before it.

Nothing here judges the model. It judges whether the model was asked.
"""

from datetime import datetime, timedelta

# A pass that scored fewer than this share of the universe it set out to scan
# is a partial observation, whatever the status column says. Not a tuning
# parameter — it is the line between "the market that day" and "whichever
# stocks happened to answer".
from model_config import SCAN_COMPLETE_FRACTION as COMPLETE_FRACTION
# Consecutive writes further apart than this mean the process was not running.
STALL_MINUTES = 20


def _conn():
    from db import get_conn
    return get_conn()


def cycles(limit: int = 30) -> dict:
    """Every scan cycle, and what it actually produced."""
    try:
        conn = _conn()
    except Exception as e:
        return {"available": False, "reason": type(e).__name__}

    try:
        rows = conn.execute(
            "SELECT cycle, COUNT(*), "
            "       SUM(CASE WHEN alpha_score IS NOT NULL THEN 1 ELSE 0 END), "
            "       SUM(CASE WHEN alpha_score IS NULL THEN 1 ELSE 0 END), "
            "       MIN(scanned_at), MAX(scanned_at) "
            "FROM alpha_scan2 GROUP BY cycle ORDER BY cycle DESC").fetchall()
        try:
            state = conn.execute(
                "SELECT cycle, status, last_complete_cycle, total "
                "FROM alpha_scan_state WHERE id = 1").fetchone()
        except Exception:
            state = None

        # The denominator is the universe as it stood THAT DAY, from the
        # exchange's own file. The first version measured every cycle against
        # the largest universe any cycle ever attempted, scoring August passes
        # at 83% when they had covered 2,389 of the 2,401 names that existed —
        # penalising them for a market that had not grown yet. Comparing a day
        # to a universe from a later date is the same error this project spent
        # a week removing from the backtest.
        #
        # Read here, inside the connection's life. Written after the finally
        # block first time round, where it silently failed and fell back to the
        # denominator it was meant to replace.
        pit = {}
        try:
            for day, n in conn.execute(
                    "SELECT day, COUNT(DISTINCT symbol) FROM bhavcopy_eod "
                    "GROUP BY day").fetchall():
                pit[str(day)[:10]] = int(n)
        except Exception:
            pit = {}
    except Exception as e:
        conn.close()
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    peak = max((r[1] for r in rows), default=0)

    out = []
    for cyc, total, scored, errored, first, last in rows[:limit]:
        # Nearest stored trading day at or before the cycle, so a Sunday cycle
        # is measured against Friday's universe rather than against nothing.
        denom = pit.get(cyc)
        if denom is None and pit:
            earlier = [d for d in pit if d <= str(cyc)]
            denom = pit[max(earlier)] if earlier else None
        denom = denom or peak
        span = None
        if first and last:
            try:
                span = round((datetime.fromisoformat(str(last))
                              - datetime.fromisoformat(str(first))
                              ).total_seconds() / 60.0, 1)
            except Exception:
                span = None
        frac = (scored or 0) / denom if denom else 0.0
        out.append({
            "cycle": cyc,
            "attempted": total,
            "scored": scored or 0,
            "errored": errored or 0,
            "universe_that_day": denom,
            "coverage_pct": round(frac * 100, 1),
            "complete_by_coverage": frac >= COMPLETE_FRACTION,
            "first_write": str(first)[:19] if first else None,
            "last_write": str(last)[:19] if last else None,
            "wall_clock_minutes": span,
        })

    good = [c for c in out if c["complete_by_coverage"]]
    days = _calendar_gaps(out)

    return {
        "available": True,
        "peak_universe": peak,
        "denominator": ("the exchange universe on each cycle's own day, "
                        "from bhavcopy" if pit else
                        "the largest universe any cycle attempted "
                        "(bhavcopy unavailable, so older cycles are "
                        "understated)"),
        "cycles_recorded": len(rows),
        "cycles_shown": len(out),
        "cycles_complete": len(good),
        "completion_rate_pct": round(len(good) / len(out) * 100, 1) if out else 0.0,
        "state": ({"cycle": state[0], "status": state[1],
                   "last_complete_cycle": state[2], "total": state[3]}
                  if state else None),
        "days_since_last_complete": days["since_last_complete"],
        "missing_days": days["missing"],
        "cycles": out,
        "threshold": (f"A cycle counts as complete when it scored at least "
                      f"{COMPLETE_FRACTION:.0%} of the securities the exchange "
                      f"listed that day. The status column is not used: it is "
                      f"set when the worker pool drains, whether the stocks "
                      f"scored or errored."),
    }


def _calendar_gaps(cycles_list):
    """Days with no complete cycle. Each one is unrecoverable."""
    complete = sorted(c["cycle"] for c in cycles_list if c["complete_by_coverage"])
    if not complete:
        return {"since_last_complete": None, "missing": []}
    try:
        last = datetime.strptime(complete[-1], "%Y-%m-%d").date()
        today = datetime.now().date()
        since = (today - last).days
        missing = [(last + timedelta(days=i)).isoformat()
                   for i in range(1, since + 1)]
        return {"since_last_complete": since, "missing": missing[:30]}
    except Exception:
        return {"since_last_complete": None, "missing": []}


def stalls(cycle: str = None, limit: int = 20) -> dict:
    """
    Gaps in the write stream — where the process stopped running.

    Progress is written per stock, so the interval between consecutive writes
    is how long the scanner was alive. A gap of hours in the middle of a pass
    is the instance sleeping, and it shows here without needing a log.
    """
    try:
        conn = _conn()
    except Exception as e:
        return {"available": False, "reason": type(e).__name__}
    try:
        if not cycle:
            row = conn.execute("SELECT MAX(cycle) FROM alpha_scan2").fetchone()
            cycle = row[0] if row else None
        if not cycle:
            return {"available": False, "reason": "No cycles recorded."}
        rows = conn.execute(
            "SELECT scanned_at FROM alpha_scan2 WHERE cycle = ? "
            "AND scanned_at IS NOT NULL ORDER BY scanned_at", (cycle,)).fetchall()
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    stamps = []
    for (s,) in rows:
        try:
            stamps.append(datetime.fromisoformat(str(s)))
        except Exception:
            continue

    gaps = []
    for a, b in zip(stamps, stamps[1:]):
        mins = (b - a).total_seconds() / 60.0
        if mins >= STALL_MINUTES:
            gaps.append({"from": a.isoformat()[:19], "to": b.isoformat()[:19],
                         "minutes": round(mins, 1)})
    gaps.sort(key=lambda g: -g["minutes"])

    alive = 0.0
    for a, b in zip(stamps, stamps[1:]):
        m = (b - a).total_seconds() / 60.0
        if m < STALL_MINUTES:
            alive += m

    return {
        "available": True,
        "cycle": cycle,
        "writes": len(stamps),
        "first": stamps[0].isoformat()[:19] if stamps else None,
        "last": stamps[-1].isoformat()[:19] if stamps else None,
        "elapsed_minutes": (round((stamps[-1] - stamps[0]).total_seconds() / 60, 1)
                            if len(stamps) > 1 else 0.0),
        "running_minutes": round(alive, 1),
        "stall_count": len(gaps),
        "stalled_minutes": round(sum(g["minutes"] for g in gaps), 1),
        "longest_stalls": gaps[:limit],
        "rate_per_minute": (round(len(stamps) / alive, 1) if alive > 0 else None),
        "note": (f"Writes more than {STALL_MINUTES} minutes apart are counted as "
                 f"a stall: the scanner writes per stock, so it was not running "
                 f"in between. running_minutes is the time it was actually "
                 f"working, which is what a completion estimate should use."),
    }


def errors(cycle: str = None, limit: int = 15) -> dict:
    """What the failures actually were, grouped."""
    try:
        conn = _conn()
    except Exception as e:
        return {"available": False, "reason": type(e).__name__}
    try:
        if not cycle:
            row = conn.execute("SELECT MAX(cycle) FROM alpha_scan2").fetchone()
            cycle = row[0] if row else None
        rows = conn.execute(
            "SELECT error, COUNT(*) FROM alpha_scan2 "
            "WHERE cycle = ? AND error IS NOT NULL "
            "GROUP BY error ORDER BY COUNT(*) DESC", (cycle,)).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM alpha_scan2 WHERE cycle = ?", (cycle,)).fetchone()[0]
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return {
        "available": True, "cycle": cycle, "rows_in_cycle": total,
        "distinct_errors": len(rows),
        "errors": [{"error": str(e)[:120], "count": n} for e, n in rows[:limit]],
        "total_errored": sum(n for _, n in rows),
    }


def report() -> dict:
    """Everything, with a verdict that does not flatter."""
    c = cycles()
    if not c.get("available"):
        return c
    s = stalls()
    e = errors()

    since = c.get("days_since_last_complete")
    rate = c.get("completion_rate_pct", 0.0)
    healthy = bool(since is not None and since <= 1 and rate >= 80)

    return {
        "healthy": healthy,
        "verdict": (
            "The collector is producing a complete daily observation."
            if healthy else
            f"The collector is NOT reliably producing daily observations. "
            f"{'No cycle has ever reached the completeness threshold. ' if since is None else f'The last complete pass was {since} day(s) ago. '}"
            f"{rate:.0f}% of recorded cycles reached it. Every day without one "
            f"is factor history that cannot be backfilled."),
        "cycles": c,
        "stalls": s,
        "errors": e,
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
