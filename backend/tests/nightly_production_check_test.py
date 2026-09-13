"""
nightly_production_check_test.py — the nightly check must go red on a bad night.

A monitor that has only ever seen good nights has not been tested. Each case
below is a night the check must refuse to call good, with the night of
2026-09-11 (failures 4 -> 72) among them, next to the nights it must NOT alarm
on, so it does not train everyone to ignore it.

Offline: the production responses are fixtures, and nothing is fetched.
"""
import copy
import os
import sys

os.environ.pop("GITHUB_STEP_SUMMARY", None)       # never write into a real CI summary
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import nightly_production_check as N  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""),
          flush=True)


TODAY = "2026-09-12"
GOOD_STATUS = {"running": False, "cycle": TODAY, "done": 2709, "total": 2709,
               "started_at": f"{TODAY}T00:02:41", "finished_at": f"{TODAY}T02:32:42",
               "excluded_no_market_data": 187,
               "progress_note": "2,709 of 2,709 attempted; 2,705 scored, 4 failed."}
GOOD_FAILURES = {
    "audit": "scan_failures", "cycle": TODAY,
    "stability_vs_previous_cycle": {"previous_cycle": "2026-09-11", "failed_then": 4,
                                    "failed_now": 5, "new_today": ["X.NS"]},
    "at_risk_of_exclusion": {"rule": "no market data on each of its last 2 attempts",
                             "at_risk": 1, "previously_scored": 0, "never_scored": 1,
                             "examples_previously_scored": [],
                             "examples_never_scored": ["DEAD.NS"]},
}


def night(status_changes=None, failure_changes=None):
    s, f = copy.deepcopy(GOOD_STATUS), copy.deepcopy(GOOD_FAILURES)
    for k, v in (status_changes or {}).items():
        s[k] = v
    for path, v in (failure_changes or {}).items():
        target = f
        *parents, leaf = path.split(".")
        for p in parents:
            target = target[p]
        target[leaf] = v
    return s, f


print("=" * 74 + "\nNIGHTS IT MUST CALL GOOD\n" + "=" * 74)
s, f = night()
check("a normal night: finished, 4 -> 5 failures, nothing at risk",
      not N.judge_scan(s, TODAY) and not N.judge_jump(f) and not N.judge_at_risk(f),
      str(N.judge_scan(s, TODAY) + N.judge_jump(f) + N.judge_at_risk(f)))
s, f = night(failure_changes={"stability_vs_previous_cycle.failed_then": 2,
                              "stability_vs_previous_cycle.failed_now": 7})
check("2 -> 7 failures is not a jump (x3.5, but only 5 more)", not N.judge_jump(f))
s, f = night(failure_changes={"stability_vs_previous_cycle.failed_then": 72,
                              "stability_vs_previous_cycle.failed_now": 72})
check("72 two nights running is not a jump", not N.judge_jump(f))
s, f = night(failure_changes={"at_risk_of_exclusion.previously_scored": 3})
check("3 previously-scoring stocks one night from exclusion is not an outage",
      not N.judge_at_risk(f))

print("\n" + "=" * 74 + "\nNIGHTS IT MUST CALL BAD, AND SAY WHY\n" + "=" * 74)
s, f = night(failure_changes={"stability_vs_previous_cycle.failed_then": 4,
                              "stability_vs_previous_cycle.failed_now": 72,
                              "stability_vs_previous_cycle.new_today": ["ABANSENT.NS", "BI.NS"]})
r = N.judge_jump(f)
check("the night of 2026-09-11: failures 4 -> 72", bool(r), str(r))
check("  ...names the jump and some of the new failures",
      bool(r) and "4 to 72" in r[0] and "ABANSENT" in r[0], str(r))

s, f = night(failure_changes={"at_risk_of_exclusion.previously_scored": 71,
                              "at_risk_of_exclusion.examples_previously_scored": ["ABANSENT.NS"]})
r = N.judge_at_risk(f)
check("71 stocks that were scoring, failing two nights running", bool(r), str(r))
check("  ...calls it a data problem on our side, not delisting, and names one", bool(r)
      and "scored in the last 60 days" in r[0] and "our side" in r[0]
      and "ABANSENT" in r[0], str(r))

s, f = night({"cycle": "2026-09-11"})
r = N.judge_scan(s, TODAY)
check("no cycle for tonight (the scan never started)", any("no scan cycle" in x for x in r), str(r))
s, f = night({"running": True})
check("the scan is still running at check time",
      any("still running" in x for x in N.judge_scan(s, TODAY)))
s, f = night({"done": 1500})
check("the scan stopped part-way",
      any("1,500 of 2,709" in x for x in N.judge_scan(s, TODAY)))
s, f = night({"finished_at": None})
check("not running, but never recorded a finish",
      any("no finish time" in x for x in N.judge_scan(s, TODAY)))

print("\n" + "=" * 74 + "\nMISSING EVIDENCE IS NOT GOOD NEWS\n" + "=" * 74)
check("the status endpoint unreachable", bool(N.judge_scan({"error": "timed out"}, TODAY)))
check("the failure audit unreachable",
      bool(N.judge_jump({"error": "HTTP 502"})) and bool(N.judge_at_risk({"error": "HTTP 502"})))
check("the failure audit UNMEASURED",
      bool(N.judge_jump({"status": "UNMEASURED", "reason": "no scan cycle recorded"})))
s, f = night()
del f["at_risk_of_exclusion"]
r = N.judge_at_risk(f)
check("the early warning absent (e.g. an older deploy)", bool(r) and "unavailable" in r[0], str(r))
s, f = night(failure_changes={"at_risk_of_exclusion": {"status": "UNMEASURED",
                                                       "reason": "no such table", "at_risk": None}})
check("the early warning UNMEASURED", bool(N.judge_at_risk(f)))
s, f = night(failure_changes={"stability_vs_previous_cycle": None})
check("no previous cycle to compare with", bool(N.judge_jump(f)))

print("\n" + "=" * 74 + "\nFUNDAMENTALS — SCORES BUILT ON MISSING INPUTS ARE NOT A GOOD NIGHT\n"
      + "=" * 74)

# On 2026-09-12 the value factor scored for 84 of 2,573 stocks, and every check
# above would have passed: the scan finished, failures did not jump, and each
# missing input carried a recorded reason. The numbers below are the real ones
# from /scan/provenance-gap for the nights either side of that.


def coverage(value_scored, total, roe_missing_pct):
    return {"available": True, "cycle": TODAY, "observations": {"total": total},
            "factors": {"value": {"scored": value_scored,
                                  "scored_pct": round(100.0 * value_scored / total, 2)},
                        "quality": {"missing_by_input": [
                            {"input": "roe", "stocks": 0, "pct_of_scored": roe_missing_pct}]}}}


has = hasattr(N, "judge_fundamentals")
check("the nightly check has a fundamentals test", has)
judge = N.judge_fundamentals if has else (lambda pg: ["no fundamentals test"])
r = judge(coverage(2577, 2706, 15.49))
check("2026-09-10 (value 2,577 of 2,706; ROE missing 15%) is a good night", r == [], str(r))
for day, args in (("2026-09-11", (1365, 2635, 53.13)), ("2026-09-12", (84, 2573, 97.75)),
                  ("2026-09-13", (1533, 2656, 47.89))):
    r = judge(coverage(*args))
    check(f"{day} (value {args[0]:,} of {args[1]:,}) is a bad night, and says why",
          has and bool(r) and "value" in " ".join(r).lower(), str(r)[:120])
r = judge(coverage(2577, 2706, 47.0))
check("value fine but ROE missing for 47% of stocks is still a bad night",
      has and bool(r) and "roe" in " ".join(r).lower(), str(r)[:120])
check("value 86% and ROE missing 24% is inside the line",
      has and judge(coverage(2327, 2706, 24.0)) == [])
for label, bad in (("unreachable", {"error": "HTTP 502"}),
                   ("UNMEASURED", {"status": "UNMEASURED", "reason": "no scan cycle"}),
                   ("not available", {"available": False, "reason": "no cycle"})):
    check(f"the coverage report {label} is not good news", has and bool(judge(bad)))

print("\n" + "=" * 74 + "\nTHE EXIT CODE THE WORKFLOW READS\n" + "=" * 74)

GOOD_COVERAGE = coverage(2577, 2706, 15.49)


def exit_for(s, f, lab_exit, pg=None):
    got = {"/alpha/universe/status": s, "/health/data-integrity?domain=scan_failures": f,
           f"/scan/provenance-gap?cycle={TODAY}": pg or GOOD_COVERAGE}
    return N.run_checks(get=lambda p: got[p], portfolio_lab=lambda: lab_exit,
                        today=TODAY, out=lambda *a: None)


s, f = night()
check("a good night with Portfolio Lab passing -> exit 0", exit_for(s, f, 0) == 0)
check("a good night with Portfolio Lab failing -> exit 1", exit_for(s, f, 1) == 1)
s, f = night(failure_changes={"stability_vs_previous_cycle.failed_now": 72})
check("a failure jump with everything else fine -> exit 1", exit_for(s, f, 0) == 1)
s, f = night()
check("collapsed fundamentals with everything else fine -> exit 1",
      exit_for(s, f, 0, coverage(84, 2573, 97.75)) == 1)
calls = []
s, f = night()
reads = {"/alpha/universe/status": s, "/health/data-integrity?domain=scan_failures": f,
         f"/scan/provenance-gap?cycle={TODAY}": GOOD_COVERAGE}
N.run_checks(get=lambda p: calls.append(p) or reads.get(p, {}),
             portfolio_lab=None, today=TODAY, out=lambda *a: None)
check("the scan checks are GET-only reads of three public endpoints",
      sorted(calls) == sorted(reads), str(calls))

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
