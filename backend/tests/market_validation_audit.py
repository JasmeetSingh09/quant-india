"""
market_validation_audit.py — the framework must not be foolable.

The whole point of this module is to resist inflated evidence, so the tests are
mostly attacks: duplicate the data, overlap the windows, feed it one sector,
feed it one stock, and check it does not reward any of them.

Synthetic records throughout, because on constructed data the correct answer is
known exactly and cannot hide behind plausible market noise.
"""

import math
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import market_validation as mv

checks = 0
failures = []


def ok(cond, label, evidence=""):
    global checks
    checks += 1
    if not cond:
        failures.append(label + (f" — {evidence}" if evidence else ""))


def rec(ticker, day_offset, signal, excess, score=None):
    d = (datetime(2026, 1, 1) + timedelta(days=day_offset)).strftime("%Y-%m-%d")
    return {"ticker": ticker, "date": d, "signal": signal,
            "alpha_score": score if score is not None else (20 if signal == "BUY" else -20),
            "forward_return_pct": excess, "benchmark_return_pct": 0.0,
            "excess_pct": excess, "days_held": 21}


# ============================ overlap must not count =====================
print("=== overlapping windows ===")

# One stock, 60 consecutive daily observations, 21-day horizon. Consecutive
# days overlap by 20, so only about three windows are genuinely separate.
daily = [rec("AAA.NS", i, "BUY", 1.0) for i in range(60)]
r = mv.validate(min_days=21, records=daily)
ok(r["available"], "validates a synthetic set")
s = r["sample"]
ok(s["raw_observations"] == 60, "raw count is reported honestly", str(s["raw_observations"]))
ok(s["independent_windows"] <= 4,
   "60 daily observations at a 21-day horizon give at most ~3 independent windows",
   str(s["independent_windows"]))
ok(s["independent_windows"] < s["raw_observations"],
   "independent count is strictly below the raw count")

# ============================ duplication must not help ==================
print("=== duplicated evidence ===")

base = [rec(f"T{i}.NS", i * 30, "BUY", 1.5) for i in range(12)]
r1 = mv.validate(min_days=21, records=list(base))
# Exactly the same observations, each present twice.
r2 = mv.validate(min_days=21, records=list(base) + list(base))

ok(r2["sample"]["raw_observations"] == 2 * r1["sample"]["raw_observations"],
   "duplicating doubles the RAW count, as it should")
ok(r2["sample"]["independent_windows"] == r1["sample"]["independent_windows"],
   "duplicating does NOT increase the independent count",
   f"{r1['sample']['independent_windows']} -> {r2['sample']['independent_windows']}")

p1 = r1["overall"].get("p_value")
p2 = r2["overall"].get("p_value")
if p1 is not None and p2 is not None:
    ok(abs(p1 - p2) < 1e-9,
       "duplicating does not strengthen the p-value", f"{p1} vs {p2}")

# ============================ hit definition =============================
print("=== hit means beating the benchmark ===")

# A BUY that rose while the index rose more is NOT a hit.
loser = [rec("BBB.NS", i * 30, "BUY", -0.5) for i in range(10)]
r = mv.validate(min_days=21, records=loser)
ok(r["overall"]["hit_rate_pct"] == 0.0,
   "a BUY with negative excess never counts as a hit",
   str(r["overall"]["hit_rate_pct"]))

winner = [rec("CCC.NS", i * 30, "SELL", -2.0) for i in range(10)]
r = mv.validate(min_days=21, records=winner)
ok(r["overall"]["hit_rate_pct"] == 100.0,
   "a SELL that underperformed counts as a hit", str(r["overall"]["hit_rate_pct"]))

# NEUTRAL has no direction to be right about and must be excluded.
neutral = [rec("DDD.NS", i * 30, "NEUTRAL", 5.0, score=0) for i in range(10)]
r = mv.validate(min_days=21, records=neutral)
ok(r["overall"].get("n_independent", 0) == 0,
   "NEUTRAL calls are not graded as hits or misses",
   str(r["overall"].get("n_independent")))

# ============================ design effect ==============================
print("=== same-day clustering ===")

# 40 stocks, all on the SAME day, all with the same outcome. That is one
# market move, not 40 independent draws, so rho should be high and the
# effective sample far below the raw count.
same_day = [rec(f"S{i}.NS", 0, "BUY", 2.0) for i in range(40)]
r = mv.validate(min_days=21, records=same_day)
d = r["sample"]["design_effect"]
ok(r["sample"]["independent_windows"] == 40,
   "different stocks on one day are 40 non-overlapping windows")
ok(r["sample"]["effective_sample_size"] <= 40,
   "effective sample never exceeds the independent count",
   str(r["sample"]["effective_sample_size"]))
ok(d["deff"] >= 1.0, "design effect is at least 1", str(d["deff"]))
if d.get("rho") is not None:
    ok(0.0 <= d["rho"] <= 1.0, "rho is a correlation in [0,1]", str(d["rho"]))

# Spread across many dates with mixed outcomes: clustering should be mild.
spread = []
for day in range(30):
    for i in range(4):
        spread.append(rec(f"M{i}.NS", day * 25, "BUY", 1.0 if (day + i) % 2 else -1.0))
r = mv.validate(min_days=21, records=spread)
ok(r["sample"]["effective_sample_size"] <= r["sample"]["graded_independent"],
   "effective sample never exceeds graded independent count")
ok(r["sample"]["design_effect"]["deff"] >= 1.0, "deff stays >= 1 on spread data")

# ============================ ordering ===================================
print("=== sample size ordering ===")

for records in (daily, base, same_day, spread):
    rr = mv.validate(min_days=21, records=list(records))
    ss = rr["sample"]
    ok(ss["raw_observations"] >= ss["independent_windows"],
       "raw >= independent, always",
       f"{ss['raw_observations']} vs {ss['independent_windows']}")
    ok(ss["independent_windows"] >= ss["effective_sample_size"],
       "independent >= effective, always",
       f"{ss['independent_windows']} vs {ss['effective_sample_size']}")

# ============================ verdict gating =============================
print("=== verdict cannot be earned cheaply ===")

r = mv.validate(min_days=21, records=daily)
ok(r["verdict"]["label"] == "INSUFFICIENT EVIDENCE",
   "one stock over two months cannot earn anything better",
   r["verdict"]["label"])

# A large but single-sector, single-cap sample must still not be ROBUST.
many = [rec(f"X{i}.NS", (i % 40) * 25, "BUY", 2.0) for i in range(600)]
r = mv.validate(min_days=21, records=many)
ok(r["verdict"]["label"] != "ROBUST OUT-OF-SAMPLE EVIDENCE",
   "size alone does not earn a robust label without coverage",
   f"{r['verdict']['label']} on {r['sample']['graded_independent']} windows")

cov = r["coverage"]
ok(cov["sectors_needed"] >= 5, "a sector floor exists")
ok(cov["independent_needed"] >= 200, "an independent-sample floor exists")

# Every checklist row must be checkable, not a vibe.
for c in r["checklist"]:
    ok(isinstance(c["passed"], bool), f"checklist '{c['criterion']}' is boolean")
    ok(bool(c["detail"]), f"checklist '{c['criterion']}' shows its evidence")
ok(not any("score" in c["criterion"].lower() and "/100" in str(c.get("detail", ""))
           for c in r["checklist"]),
   "the checklist is not a disguised numeric score")

# ============================ monotonicity ===============================
print("=== score monotonicity ===")

# Deliberately INVERTED: Strong Buy does worst. The framework must notice.
inverted = []
for i, (bucket_score, exc) in enumerate([(-40, 3.0), (-20, 2.0), (0, 1.0),
                                         (20, 0.0), (40, -3.0)]):
    for j in range(40):
        sig = "BUY" if bucket_score >= 0 else "SELL"
        inverted.append(rec(f"B{i}_{j}.NS", j * 25, sig, exc, score=bucket_score))
r = mv.validate(min_days=21, records=inverted)
m = r["monotonicity"]
if m.get("testable"):
    ok(m["monotonic"] is False,
       "an inverted score ordering is flagged, not passed",
       str(m.get("sequence"))[:80])
    ok("does NOT rise" in m["verdict"], "the verdict says the ordering failed")
else:
    ok(bool(m.get("reason")), "untestable monotonicity explains itself")

# ============================ empty and degenerate =======================
print("=== degenerate inputs ===")

r = mv.validate(min_days=21, records=[])
ok(r["available"] is False, "no records reports unavailable, not a zero hit rate")
ok("speed of the market" in r.get("reason", ""),
   "the empty case explains that evidence takes real time")

r = mv.validate(min_days=21, records=[rec("ZZZ.NS", 0, "BUY", 1.0)])
ok(r["verdict"]["label"] == "INSUFFICIENT EVIDENCE",
   "a single observation is insufficient", r["verdict"]["label"])

# Bad rows must not crash it.
messy = [rec("QQQ.NS", 0, "BUY", 1.0)]
messy.append({"ticker": "RRR.NS", "date": "not-a-date", "signal": "BUY",
              "alpha_score": None, "excess_pct": None,
              "forward_return_pct": None, "days_held": 21})
try:
    r = mv.validate(min_days=21, records=messy)
    ok(isinstance(r, dict), "malformed rows are tolerated")
    ok(r["sample"]["effective_sample_size"] >= 0, "no negative sample sizes")
except Exception as e:
    ok(False, "malformed rows crashed the validator", type(e).__name__)

# ============================ bucket helpers =============================
print("=== bucket boundaries ===")

for score, expected in ((-100, "Strong Sell"), (-30, "Strong Sell"),
                        (-29, "Sell"), (-10, "Sell"), (-9, "Neutral"),
                        (0, "Neutral"), (9, "Neutral"), (10, "Buy"),
                        (29, "Buy"), (30, "Strong Buy"), (100, "Strong Buy")):
    got = mv._bucket_for_score(score)
    ok(got == expected, f"score {score} -> {expected}", str(got))
ok(mv._bucket_for_score(None) is None, "a missing score has no bucket")

for cap_cr, expected in ((100000, "Large"), (50000, "Large"), (49999, "Mid"),
                         (15000, "Mid"), (14999, "Small"), (100, "Small")):
    got = mv._cap_bucket(cap_cr * 1e7)
    ok(got == expected, f"{cap_cr} crore -> {expected}", str(got))
ok(mv._cap_bucket(None) is None, "a missing market cap has no bucket")
ok(mv._cap_bucket(0) is None, "a zero market cap has no bucket")

# Wilson interval sanity.
ok(mv._wilson(0, 0) is None, "no interval on an empty sample")
lo, hi = mv._wilson(5, 10)
ok(lo < 50 < hi, "a 5/10 interval brackets 50%", f"[{lo}, {hi}]")
lo2, hi2 = mv._wilson(50, 100)
ok((hi2 - lo2) < (hi - lo), "a larger sample gives a tighter interval",
   f"{hi-lo:.1f} vs {hi2-lo2:.1f}")
lo3, hi3 = mv._wilson(10, 10)
ok(hi3 <= 100.0 and lo3 >= 0.0, "intervals stay inside [0,100]", f"[{lo3},{hi3}]")

# ============================ tracker wiring =============================
# The validator reads the tracker's output. Reading a key the tracker never
# returns produced an empty list and reported "no graded predictions yet",
# which is indistinguishable from a genuinely empty record - the same silent
# mismatch that once dropped Black-Litterman from the strategy comparison.
print("=== tracker key contract ===")
import inspect as _insp
_src = _insp.getsource(mv.validate)
ok("predictions" in _src,
   "the validator reads the key the tracker actually returns")

import prediction_tracker as _pt
_tsrc = _insp.getsource(_pt.evaluate)
ok("predictions" in _tsrc,
   "the tracker really does return predictions under that name")

# An unrecognised shape must announce itself rather than look empty.
_orig = _pt.evaluate
try:
    _pt.evaluate = lambda min_days=21: {"something_else": []}
    _r = mv.validate(min_days=21)
    ok(_r.get("available") is False, "an unknown shape is not treated as success")
    ok("does not recognise" in _r.get("reason", ""),
       "an unknown shape says so instead of reporting an empty sample",
       str(_r.get("reason"))[:60])
finally:
    _pt.evaluate = _orig


# ============================ snapshot integrity =========================
# The silent 30-stock fallback is why the whole track record is large-cap only.
# A narrow day and a broad day looked identical once logged.
print("=== snapshot integrity ===")
import prediction_tracker as _pt
import inspect as _pi
_ssrc = _pi.getsource(_pt.snapshot)

ok("allow_fallback" in _ssrc,
   "the 30-stock fallback must be asked for explicitly")
ok("skipped" in _ssrc, "a snapshot that cannot run says it was skipped")
ok("MAX_CYCLE_AGE_DAYS" in _ssrc or "cycle_age" in _ssrc,
   "snapshot checks how old the scan cycle is")
ok(_pt.MAX_CYCLE_AGE_DAYS <= 2,
   "a scan more than a couple of days old is not today's opinion",
   str(_pt.MAX_CYCLE_AGE_DAYS))

# Provenance: a logged row must record where it came from.
for field in ("scan_cycle", "universe_size", "source"):
    ok(field in _ssrc, f"snapshot records {field} with each prediction")

# Coverage must decompose. "2,573 logged" says nothing about what was dropped.
for reason in ("no_score", "no_price", "error"):
    ok(reason in _ssrc, f"exclusions are counted by reason: {reason}")
ok("coverage_pct" in _ssrc, "snapshot reports coverage as a percentage")

# Duplicate protection is a schema guarantee, not a hope.
_isrc = _pi.getsource(_pt.init_table)
ok("UNIQUE(ticker, snapshot_date)" in _isrc,
   "one row per ticker per day is enforced by the schema")


# ============================ scan -> snapshot wiring ====================
# A skipped day of evidence cannot be recovered, and the snapshot now refuses a
# stale or missing scan - correctly - which means a fixed 16:30 cron would lose
# any day the scan finished late. The trigger belongs where completion is known.
print("=== scan completion triggers the snapshot ===")
import universe_scan as _us
import inspect as _ui
_scan_src = _ui.getsource(_us)

ok("from prediction_tracker import snapshot" in _scan_src,
   "the scan triggers a snapshot when it completes")
_after_publish = _scan_src.split('last_complete_cycle=cycle')[-1]
ok("snapshot" in _after_publish,
   "the snapshot fires AFTER the cycle is published, not before")
ok("daemon=True" in _after_publish or "Thread" in _after_publish,
   "the snapshot runs off the scan thread so it cannot delay publishing")
ok("except Exception" in _after_publish,
   "a failed snapshot loses one day, never the whole scan pass")

# Reads must serve the last COMPLETE cycle so a scan in progress never shows
# a half-updated mixture of two passes.
ok("last_complete_cycle" in _scan_src,
   "reads are served from the last complete cycle")
_serve = [l for l in _scan_src.split(chr(10)) if "serve_cycle =" in l]
ok(_serve and "last_complete_cycle" in _serve[0],
   "the serving cycle prefers the completed pass over the running one",
   str(_serve[:1]))

# The backstop cron must attempt more than once.
_pt_src = _ui.getsource(_pt.start_prediction_scheduler)
ok(_pt_src.count("add_job") >= 1 and "for _h in" in _pt_src,
   "the timed backstop retries rather than getting one chance")
ok("no-op" in _pt_src or "UNIQUE" in _pt_src,
   "repeat runs are documented as harmless")


print("\n" + "=" * 66)
print(f"MARKET-VALIDATION CHECKS: {checks}")
print(f"FAILURES:                 {len(failures)}")
for f in failures:
    print(f"   FAIL: {f}")
print("=" * 66)
sys.exit(1 if failures else 0)
