"""
integrity_evidence_test.py — the second axis must be earned, not asserted.

The evidence layer had one axis: does the factor predict returns? For all six
the answer is "not established", and stays that way until at least 2029. A badge
that is the same colour on every stock every day is wallpaper; people stop
seeing it inside a week, and then the amber that matters is invisible too.

The second axis asks whether the machinery computes what it claims. That has
answers today. But an axis added to make the page look better would be worse
than no axis at all, so the rules are strict and tested:

    every claim is MEASURED from stored rows at request time;
    a check that could not run reports `unknown`, never `verified`;
    a failure reports `failed` and is counted, never quietly dropped;
    nothing here says anything about prediction.

The last one is the point of the separation. If this axis were allowed to imply
predictive evidence, it would launder "our arithmetic is reproducible" into
"our signal works", which is the specific confusion the whole evidence layer
exists to prevent.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import integrity_evidence as IE  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


HEALTHY = {
    "available": True, "cycle": "2026-09-09", "verdict": "PASS",
    "checks_passed": 9, "checks_failed": 0,
    "scan": {"attempted": 2895, "scored": 2704, "failed": 191,
             "coverage_pct": 93.4, "completeness_bar_pct": 90.0},
    "reproduction": {"checked": 500, "mismatched": 0, "worst": "GAIL.NS",
                     "max_abs_diff": 0.000371},
    "duplicates": {"alpha_scan2": 0, "factor_history": 0, "factor_inputs": 0},
    "provenance": {"input_rows": 70096},
    "factor_history": {"rows": 2682, "with_raw_inputs": 1960,
                       "missing_provenance": 722},
}


def with_audit(payload):
    """Swap in a fixed audit result and rebuild."""
    fake = types.ModuleType("cycle_audit")
    fake.audit = lambda cycle=None: payload
    sys.modules["cycle_audit"] = fake
    IE._CACHE.clear()
    return IE.integrity(refresh=True)


print("=" * 72)
print("A HEALTHY CYCLE")
print("=" * 72)

r = with_audit(HEALTHY)
by_id = {c["id"]: c for c in r["claims"]}
print(f"  {r['summary']}")
for c in r["claims"]:
    print(f"    [{c['status']:<8}] {c['id']:<22} {c['measured']}")

check("the axis is named", r["axis"] == "machinery")
check("all five claims are verified", r["verified"] == 5, f"{r['summary']}")
check("none failed", r["failed"] == 0)
check("reproducibility cites the real numbers",
      "500" in by_id["reproducible"]["measured"]
      and "0 mismatched" in by_id["reproducible"]["measured"])
check("coverage is judged against the declared bar",
      by_id["coverage_meets_bar"]["status"] == "verified",
      by_id["coverage_meets_bar"]["measured"])

print()
print("=" * 72)
print("A FAILURE MUST READ AS A FAILURE")
print("=" * 72)

bad = {**HEALTHY, "reproduction": {"checked": 500, "mismatched": 7,
                                   "worst": "X.NS", "max_abs_diff": 0.9}}
r2 = with_audit(bad)
b2 = {c["id"]: c for c in r2["claims"]}
check("a reproduction mismatch is FAILED, not unknown",
      b2["reproducible"]["status"] == "failed", b2["reproducible"]["measured"])
check("and it is counted", r2["failed"] == 1, f"{r2['summary']}")
check("and the summary says so loudly", "FAILED" in r2["summary"], r2["summary"])

dup = {**HEALTHY, "duplicates": {"alpha_scan2": 3, "factor_history": 0}}
r3 = with_audit(dup)
check("duplicates are a failure",
      {c["id"]: c for c in r3["claims"]}["no_duplicates"]["status"] == "failed")

thin = {**HEALTHY, "scan": {**HEALTHY["scan"], "coverage_pct": 71.0}}
r4 = with_audit(thin)
check("a thin pass fails the coverage bar",
      {c["id"]: c for c in r4["claims"]}["coverage_meets_bar"]["status"] == "failed",
      "71% against a 90% bar")

print()
print("=" * 72)
print("A CHECK THAT DID NOT RUN IS NOT A CHECK THAT PASSED")
print("=" * 72)

missing = {**HEALTHY, "reproduction": {"checked": 0, "mismatched": None},
           "duplicates": {}}
r5 = with_audit(missing)
b5 = {c["id"]: c for c in r5["claims"]}
check("an unmeasured reproduction is unknown, not verified",
      b5["reproducible"]["status"] == "unknown", b5["reproducible"]["measured"])
check("an unmeasured duplicate check is unknown",
      b5["no_duplicates"]["status"] == "unknown")
check("unknowns are counted separately from verified",
      r5["unknown"] >= 2 and r5["verified"] < 5,
      f"verified={r5['verified']} unknown={r5['unknown']}")

broken = with_audit({"available": False, "reason": "OperationalError"})
check("a failed audit claims nothing at all",
      broken.get("available") is False and "claims" not in broken,
      "a fault in the audit is not a verdict on the machinery")

print()
print("=" * 72)
print("IT SAYS NOTHING ABOUT PREDICTION")
print("=" * 72)

r = with_audit(HEALTHY)
blob = str(r).lower()
for word in ("predict", "alpha is", "outperform", "significant", "p_value",
             "sharpe", "returns are"):
    check(f"no claim mentions {word!r}",
          word not in " ".join(c["claim"].lower() for c in r["claims"]))
check("and it says explicitly which axis it is NOT",
      "predicts returns" in r["not_this_axis"], r["not_this_axis"][:60])
check("the question it answers is stated",
      "computing what it claims" in r["question"])

print()
print("=" * 72)
print("CACHING")
print("=" * 72)

IE._CACHE.clear()
first = with_audit(HEALTHY)
second = IE.integrity()
check("a second call is served from cache", second.get("cached") is True)
check("and reports its age", "age_seconds" in second)
check("the cache is bounded", IE._CACHE.stats()["maxsize"] == 4)
check("the TTL is 6 hours", IE._TTL == 6 * 3600, f"{IE._TTL}s")
check("warm() reports whether it worked", "warmed" in IE.warm())

print()
print("=" * 72)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
