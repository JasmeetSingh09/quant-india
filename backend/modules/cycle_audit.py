"""
cycle_audit.py — did one scan cycle produce a trustworthy observation?

Run after a pass completes. It answers, for that single cycle, whether what
landed in the database is what the collector claims it collected: the coverage,
the provenance, the grading, and whether any of it contradicts itself.

Read-only. It computes nothing that feeds a model and writes nothing at all.

Why this is a module and not a checklist someone works through
--------------------------------------------------------------
Every hand-assembled version of these checks in this project has been wrong at
least once — a denominator taken from the wrong day, a p-value computed on
pooled observations, a completeness count inflated by constants. Each was found
by writing the check down as code and running it, not by reasoning carefully.
Eighteen checks re-derived by hand each morning will drift; the same eighteen
run identically every cycle will not.

The check that earns its place
------------------------------
REPRODUCTION. Momentum's score is tanh(risk_adj / divisor), and both sides are
stored: risk_adj in factor_inputs, the score in factor_history. If they
disagree, the provenance describes a calculation that did not happen — which is
worse than no provenance, because it looks like evidence. Nothing else here
catches that.
"""

import time
from datetime import datetime

try:
    from db import get_conn
except Exception:                                   # pragma: no cover
    from .db import get_conn


def _q(conn, sql, args=(), one=True):
    """Run a query and time it, so latency is measured rather than guessed."""
    t0 = time.time()
    cur = conn.execute(sql, args)
    rows = cur.fetchall()
    ms = round((time.time() - t0) * 1000, 1)
    val = (rows[0][0] if rows and one else (rows if not one else 0))
    return val, ms


def audit(cycle: str = None) -> dict:
    """Public entry point. Never raises: an audit that dies with a 500 tells the
    reader nothing about the cycle AND nothing about itself."""
    try:
        return _audit(cycle)
    except Exception as e:
        import traceback
        return {"available": False,
                "reason": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[-1200:],
                "note": ("The audit failed, which is a fault in the audit and "
                         "not a verdict on the cycle. The cycle is unjudged.")}


def _audit(cycle: str = None) -> dict:
    """
    Everything measurable about one cycle, with a verdict per check.

    `cycle` defaults to the most recent COMPLETED pass, because auditing a scan
    that is still running measures a moving target and reports its incompleteness
    as a fault.
    """
    checks, anomalies, timings = [], [], {}

    def check(name, passed, detail="", severity="fail"):
        # Three outcomes, not two. An observation that is merely NOTED —
        # a cycle predating the provenance deployment has no input rows, and
        # that is a fact about when it ran, not a defect — must not count
        # toward the verdict. Recording it as FAIL and keeping it out of the
        # anomaly list only hid it from the reader while still failing the
        # cycle, which is the worst of both.
        result = "PASS" if passed else ("FAIL" if severity == "fail" else "INFO")
        checks.append({"check": name, "result": result, "detail": detail})
        if result == "FAIL":
            anomalies.append(f"{name}: {detail}")
        return passed

    try:
        conn = get_conn()
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}

    try:
        # ---------------------------------------------------- 1. identify it
        state, _ = _q(conn, "SELECT cycle, status, last_complete_cycle, "
                            "started_at, finished_at FROM alpha_scan_state "
                            "WHERE id = 1", one=False)
        st = state[0] if state else (None,) * 5
        if not cycle:
            cycle = st[2] or st[0]
        if not cycle:
            return {"available": False, "reason": "No cycle recorded."}

        started, finished = st[3], st[4]
        marked_complete = (st[2] == cycle)

        # ------------------------------------------- 2-5. what it attempted
        attempted, t = _q(conn, "SELECT COUNT(*) FROM alpha_scan2 WHERE cycle = ?",
                          (cycle,)); timings["attempted"] = t
        scored, t = _q(conn, "SELECT COUNT(*) FROM alpha_scan2 WHERE cycle = ? "
                             "AND alpha_score IS NOT NULL", (cycle,))
        timings["scored"] = t
        failed, _ = _q(conn, "SELECT COUNT(*) FROM alpha_scan2 WHERE cycle = ? "
                             "AND alpha_score IS NULL", (cycle,))
        first_w, _ = _q(conn, "SELECT MIN(scanned_at) FROM alpha_scan2 WHERE cycle = ?",
                        (cycle,))
        last_w, _ = _q(conn, "SELECT MAX(scanned_at) FROM alpha_scan2 WHERE cycle = ?",
                       (cycle,))

        # The universe as the exchange listed it THAT DAY, not today's.
        universe, _ = _q(conn, "SELECT COUNT(DISTINCT symbol) FROM bhavcopy_eod "
                               "WHERE day = (SELECT MAX(day) FROM bhavcopy_eod "
                               "WHERE day <= ?)", (cycle,))
        universe = universe or attempted or 1
        coverage = round(scored / universe * 100, 2) if universe else 0.0

        try:
            from model_config import SCAN_COMPLETE_FRACTION as BAR
        except Exception:
            BAR = 0.90

        # failure taxonomy, grouped rather than listed
        errs, _ = _q(conn, "SELECT error, COUNT(*) FROM alpha_scan2 WHERE cycle = ? "
                           "AND error IS NOT NULL GROUP BY error", (cycle,), one=False)
        buckets = {}
        for e, n in errs:
            s = str(e)
            key = ("no market data" if "No market data" in s
                   else "timeout" if "imeout" in s
                   else "rate limited" if "429" in s or "too many" in s.lower()
                   else s.split(":")[0][:48])
            buckets[key] = buckets.get(key, 0) + n

        check("coverage meets the completeness bar",
              coverage >= BAR * 100,
              f"{scored}/{universe} = {coverage}% (bar {BAR:.0%})")
        check("cycle marked complete matches measured coverage",
              marked_complete == (coverage >= BAR * 100),
              f"marked={marked_complete}, measured={coverage >= BAR * 100}")

        # ------------------------------------------ 7-11. factor history
        fh_rows, t = _q(conn, "SELECT COUNT(*) FROM factor_history WHERE cycle_id = ?",
                        (cycle,)); timings["factor_history"] = t
        fh_graded, _ = _q(conn, "SELECT COUNT(*) FROM factor_history WHERE cycle_id = ? "
                                "AND cycle_complete = 1", (cycle,))
        fh_prov = fh_rows - fh_graded
        fh_inputs, _ = _q(conn, "SELECT COUNT(*) FROM factor_history WHERE cycle_id = ? "
                                "AND raw_inputs_available = 1", (cycle,))
        fh_noinputs = fh_rows - fh_inputs

        check("every factor-history row for this cycle is graded consistently",
              (fh_graded == fh_rows) if marked_complete else (fh_graded == 0),
              f"{fh_graded} graded of {fh_rows} (cycle complete={marked_complete})")

        # -------------------------------------------- 12-14. provenance rows
        try:
            fi, t = _q(conn, "SELECT COUNT(*) FROM factor_inputs WHERE cycle_id = ?",
                       (cycle,)); timings["factor_inputs"] = t
            fi_stocks, _ = _q(conn, "SELECT COUNT(DISTINCT ticker) FROM factor_inputs "
                                    "WHERE cycle_id = ?", (cycle,))
            fi_missing, _ = _q(conn, "SELECT COUNT(*) FROM factor_inputs "
                                     "WHERE cycle_id = ? AND missing = 1", (cycle,))
            peers, _ = _q(conn, "SELECT COUNT(*) FROM factor_input_peers "
                                "WHERE cycle_id = ?", (cycle,))
            arts, _ = _q(conn, "SELECT COUNT(*) FROM factor_input_articles "
                               "WHERE cycle_id = ?", (cycle,))
            prov_exists = True
        except Exception as e:
            fi = fi_stocks = fi_missing = peers = arts = 0
            prov_exists = False
            anomalies.append(f"provenance tables unreadable: {type(e).__name__}")

        # A cycle that ran entirely before provenance shipped legitimately has
        # none. Say so rather than failing it.
        pre_provenance = prov_exists and fi == 0
        check("provenance captured for this cycle", not pre_provenance,
              (f"{fi} input rows across {fi_stocks} stocks"
               if not pre_provenance else
               "0 rows — this cycle predates the provenance deployment, which "
               "is expected for any pass that finished before it shipped"),
              severity="info" if pre_provenance else "fail")

        # ------------------------------------------------ 15. duplicates
        dupes = {}
        for label, sql in (
            ("alpha_scan2", "SELECT COUNT(*) FROM (SELECT ticker, cycle, COUNT(*) c "
                            "FROM alpha_scan2 WHERE cycle = ? GROUP BY 1,2 HAVING c>1) t"),
            ("factor_history", "SELECT COUNT(*) FROM (SELECT ticker, captured_at, model, "
                               "COUNT(*) c FROM factor_history WHERE cycle_id = ? "
                               "GROUP BY 1,2,3 HAVING c>1) t"),
            ("factor_inputs", "SELECT COUNT(*) FROM (SELECT ticker, cycle_id, factor, "
                              "input_name, COUNT(*) c FROM factor_inputs WHERE cycle_id = ? "
                              "GROUP BY 1,2,3,4 HAVING c>1) t"),
            ("factor_input_peers", "SELECT COUNT(*) FROM (SELECT ticker, cycle_id, "
                                   "peer_ticker, COUNT(*) c FROM factor_input_peers "
                                   "WHERE cycle_id = ? GROUP BY 1,2,3 HAVING c>1) t"),
            ("factor_input_articles", "SELECT COUNT(*) FROM (SELECT ticker, cycle_id, "
                                      "title_hash, COUNT(*) c FROM factor_input_articles "
                                      "WHERE cycle_id = ? GROUP BY 1,2,3 HAVING c>1) t"),
        ):
            try:
                n, _ = _q(conn, sql, (cycle,))
                dupes[label] = n
            except Exception:
                dupes[label] = None
        check("no duplicate rows in any table",
              all(v == 0 for v in dupes.values() if v is not None), str(dupes))

        # ---------------------------- 16. graded rows have their provenance
        orphans = 0
        if prov_exists and not pre_provenance:
            orphans, t = _q(conn,
                "SELECT COUNT(*) FROM factor_history fh WHERE fh.cycle_id = ? "
                "AND fh.raw_inputs_available = 1 AND NOT EXISTS "
                "(SELECT 1 FROM factor_inputs fi WHERE fi.ticker = fh.ticker "
                "AND fi.cycle_id = fh.cycle_id)", (cycle,))
            timings["orphan_join"] = t
            check("every row claiming inputs actually has them",
                  orphans == 0, f"{orphans} rows claim provenance with none stored")

        # ------------------ 17. the stored inputs REPRODUCE the stored score
        repro = {"checked": 0, "mismatched": 0, "worst": None}
        if prov_exists and not pre_provenance:
            try:
                import math
                from alpha_model import MOMENTUM_TANH_DIVISOR as DIV
                rows, t = _q(conn,
                    "SELECT fi.ticker, fi.value_num, fh.momentum FROM factor_inputs fi "
                    "JOIN factor_history fh ON fh.ticker = fi.ticker "
                    "AND fh.cycle_id = fi.cycle_id "
                    "WHERE fi.cycle_id = ? AND fi.factor = 'momentum' "
                    "AND fi.input_name = 'risk_adj' AND fi.value_num IS NOT NULL "
                    "AND fh.momentum IS NOT NULL LIMIT 500", (cycle,), one=False)
                timings["reproduction"] = t
                worst = 0.0
                for tk, ra, score in rows:
                    got = math.tanh(float(ra) / DIV)
                    diff = abs(got - float(score))
                    if diff > worst:
                        worst, repro["worst"] = diff, tk
                    if diff > 1e-3:
                        repro["mismatched"] += 1
                    repro["checked"] += 1
                repro["max_abs_diff"] = round(worst, 6)
                check("stored inputs reproduce the stored factor score",
                      repro["mismatched"] == 0,
                      f"{repro['checked']} momentum scores rechecked, "
                      f"{repro['mismatched']} mismatched, "
                      f"max |diff| {repro.get('max_abs_diff')}")
            except Exception as e:
                anomalies.append(f"reproduction check unavailable: {type(e).__name__}")

        # -------------------- 18. failed stocks were not promoted regardless
        promoted_failures, _ = _q(conn,
            "SELECT COUNT(*) FROM factor_history fh JOIN alpha_scan2 a "
            "ON a.ticker = fh.ticker AND a.cycle = fh.cycle_id "
            "WHERE fh.cycle_id = ? AND a.alpha_score IS NULL", (cycle,))
        check("no failed stock reached factor history",
              promoted_failures == 0,
              f"{promoted_failures} rows for stocks that never scored")

        # ------------------ 19. snapshot universe vs research-grade universe
        snap_n, snap_note = None, ""
        try:
            snap_n, _ = _q(conn, "SELECT COUNT(*) FROM predictions "
                                 "WHERE snapshot_date = ?", (cycle,))
            if snap_n and fh_graded:
                drift_pct = abs(snap_n - fh_graded) / max(fh_graded, 1) * 100
                check("snapshot and research-grade universes agree",
                      drift_pct <= 5.0,
                      f"snapshot {snap_n} vs graded {fh_graded} "
                      f"({drift_pct:.1f}% apart)")
            else:
                snap_note = ("no prediction snapshot for this cycle" if not snap_n
                             else "no graded rows to compare")
        except Exception as e:
            snap_note = f"unavailable: {type(e).__name__}"

        # ------------------------------------------- 21. previous two cycles
        prev, _ = _q(conn,
            "SELECT cycle, COUNT(*), "
            "SUM(CASE WHEN alpha_score IS NOT NULL THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN alpha_score IS NULL THEN 1 ELSE 0 END) "
            "FROM alpha_scan2 WHERE cycle < ? GROUP BY cycle "
            "ORDER BY cycle DESC LIMIT 2", (cycle,), one=False)
        comparison = [{"cycle": c, "attempted": a, "scored": s, "failed": f}
                      for c, a, s, f in prev]
        for p in comparison:
            if p["scored"]:
                delta = (scored - p["scored"]) / p["scored"] * 100
                p["scored_delta_pct"] = round(delta, 1)
                if abs(delta) > 10:
                    anomalies.append(
                        f"scored count moved {delta:+.1f}% vs {p['cycle']}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    failed_checks = [c for c in checks if c["result"] == "FAIL"]
    return {
        "available": True,
        "cycle": cycle,
        "verdict": "PASS" if not failed_checks else "FAIL",
        "checks_passed": len(checks) - len(failed_checks),
        "checks_failed": len(failed_checks),
        "scan": {
            "started_at": started, "finished_at": finished,
            "attempted": attempted, "scored": scored, "failed": failed,
            "universe_that_day": universe, "coverage_pct": coverage,
            "completeness_bar_pct": round(BAR * 100, 1),
            "marked_complete": marked_complete,
            "first_write": str(first_w)[:19] if first_w else None,
            "last_write": str(last_w)[:19] if last_w else None,
        },
        "failure_taxonomy": dict(sorted(buckets.items(), key=lambda x: -x[1])),
        "factor_history": {
            "rows": fh_rows, "research_grade": fh_graded,
            "provisional": fh_prov, "with_raw_inputs": fh_inputs,
            "missing_provenance": fh_noinputs,
        },
        "provenance": {
            "input_rows": fi, "stocks_with_inputs": fi_stocks,
            "inputs_marked_missing": fi_missing,
            "peer_rows": peers, "article_rows": arts,
            "pre_provenance_cycle": pre_provenance,
        },
        "duplicates": dupes,
        "reproduction": repro,
        "snapshot": {"rows": snap_n, "note": snap_note},
        "previous_cycles": comparison,
        "query_latency_ms": timings,
        "checks": checks,
        "anomalies": anomalies,
        "note": ("Read-only. Coverage is measured against the exchange universe "
                 "of the cycle's own day, not today's. A cycle that finished "
                 "before provenance shipped legitimately has no input rows and "
                 "is reported as such rather than failed."),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
