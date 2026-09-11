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
check("71 stocks that were scoring, one night from exclusion", bool(r), str(r))
check("  ...says they are one night away and names one", bool(r)
      and "one night" in r[0] and "ABANSENT" in r[0], str(r))

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

print("\n" + "=" * 74 + "\nTHE EXIT CODE THE WORKFLOW READS\n" + "=" * 74)


def exit_for(s, f, lab_exit):
    got = {"/alpha/universe/status": s, "/health/data-integrity?domain=scan_failures": f}
    return N.run_checks(get=lambda p: got[p], portfolio_lab=lambda: lab_exit,
                        today=TODAY, out=lambda *a: None)


s, f = night()
check("a good night with Portfolio Lab passing -> exit 0", exit_for(s, f, 0) == 0)
check("a good night with Portfolio Lab failing -> exit 1", exit_for(s, f, 1) == 1)
s, f = night(failure_changes={"stability_vs_previous_cycle.failed_now": 72})
check("a failure jump with everything else fine -> exit 1", exit_for(s, f, 0) == 1)
calls = []
s, f = night()
N.run_checks(get=lambda p: calls.append(p) or {"/alpha/universe/status": s}.get(p, f),
             portfolio_lab=None, today=TODAY, out=lambda *a: None)
check("the scan checks are GET-only reads of the two public endpoints",
      sorted(calls) == ["/alpha/universe/status", "/health/data-integrity?domain=scan_failures"],
      str(calls))

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
