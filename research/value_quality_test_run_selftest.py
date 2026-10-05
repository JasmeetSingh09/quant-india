"""
Self-test for value_quality_test_run.py on synthetic data only (no real returns are read).

    python research/value_quality_test_run_selftest.py
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import value_quality_test_run as V  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


print("\n1. Formulas, by hand")
a = {"profit": 100.0, "total_equity": 500.0, "share_capital": 10.0, "face_value": 1.0,
     "total_assets": 1000.0, "cfo": 150.0, "revenue": 900.0, "revenue_prev": 800.0}
# shares 10 crore, close 200 -> mcap 2000; PE 20, PB 4
raw = -0.6 * (20 - 22) / 8 - 0.4 * (4 - 3.2) / 1.5
ok(abs(V.value_score(a, 200.0, 1.0) - math.tanh(raw / 2)) < 1e-12, "value: PE 20, PB 4")
ok(abs(V.value_score(a, 100.0, 2.0) - math.tanh(raw / 2)) < 1e-12, "a 1:1 bonus doubles the shares, halves the price: same score")
ok(V.value_score(dict(a, profit=-5.0, total_equity=-1.0), 200.0, 1.0) == -0.5, "both multiples negative: -0.5")
raw_pe_dropped = -0.4 * (4 - 3.2) / 1.5
ok(abs(V.value_score(dict(a, profit=-5.0), 200.0, 1.0) - math.tanh(raw_pe_dropped / 2)) < 1e-12,
   "a dropped P/E sits at its constant")
ok(V.value_score(dict(a, profit=None), 200.0, 1.0) is None, "a missing input gives no score, never a guess")
roa, roe = 0.1, 0.2
f = 1 + 1 + 1 + 1 + 1 + 1          # ROA>0, CFO>0, ROA>5%, CFO/TA 15% > 10%, point 7, revenue up
qraw = (0.4 * f / 9 + 0.4 * ((roe - 0.12) / 0.08) / 3) / 0.8
ok(abs(V.quality_score(a) - math.tanh(qraw)) < 1e-12, "quality: F = 6 of 6 computable, ROE 20%")
# Loss of 50: ROA -5%, F = 0+1+0+1+1+1 = 4, ROE -10%; raw = (0.4*4/9 + 0.4*(-0.22/0.08)/3)/0.8; penalty 0.25.
loss_raw = min(0.0, (0.4 * 4 / 9 + 0.4 * ((-0.1 - 0.12) / 0.08) / 3) / 0.8) - 0.25
ok(abs(V.quality_score(dict(a, profit=-50.0)) - math.tanh(loss_raw)) < 1e-12,
   f"a loss-maker: raw {loss_raw:.4f}, penalty 0.25")
# Negative equity: no ROE, raw = F/9 = 6/9 > 0, so min(raw, 0) = 0, minus penalty 0.5.
ok(abs(V.quality_score(dict(a, total_equity=-10.0)) - math.tanh(-0.5)) < 1e-12,
   "negative equity: score tanh(-0.5), whatever the other points")

print("\n2. Timing")
ok(V.formation_months("2012-03-31")[0] == "2013-01" and V.formation_months("2012-03-31")[-1] == "2013-12",
   "March 2012 accounts are used January to December 2013")
ok(V.formation_months("2014-12-31")[0] == "2015-09", "December 2014 accounts from September 2015 (nine months)")

print("\n3. A planted effect is found; the placebo finds nothing")
rng = random.Random(1)
months = [V.add_months("2013-01", i) for i in range(120)]
by_month = {}
for ym in months:
    rows = []
    for i in range(80):
        sc = rng.uniform(-1, 1)
        fwd = {str(h): 0.004 * h * sc + rng.gauss(0, 0.06 * math.sqrt(h)) for h in V.HORIZONS}
        rows.append((f"S{i}", sc, fwd))
    by_month[ym] = rows
scores = {"value": by_month, "quality": {ym: [(s, -sc, f) for s, sc, f in rows] for ym, rows in by_month.items()}}
res = V.test(scores)
ok(res["value_12m"]["verdict"] == "demonstrated edge", f"value, planted: {res['value_12m']}")
ok(res["quality_12m"]["verdict"] == "reversed", "quality scored backwards is reported as reversed")
pl = V.placebo(scores, draws=20)
ok(all(abs(v["mean_of_means_pct"]) < 0.3 for v in pl.values()), f"placebo means near zero ({ {k: v['mean_of_means_pct'] for k, v in pl.items()} })")

print("\n4. Fewer than 50 scored stocks: the month is skipped")
thin = {ym: rows[:40] for ym, rows in by_month.items()}
ok(V.monthly_spreads(thin, 1) == [], "no month with 40 stocks is used")

print("\n5. The coverage gate")
acc = {f"A|{y}": dict(a, accepted=True, year_end=f"{y}-03-31") for y in range(2012, 2016)}
uni = {str(y): ["A", "B"] for y in range(2012, 2016)}
_, cov = V.build_scores({k.replace("|", "|"): v for k, v in acc.items()}, {int(k): v for k, v in uni.items()}, {})
ok(abs(cov["coverage"] - 0.5) < 1e-9, f"half the company-years accepted -> coverage 50% ({cov})")
ok(cov["coverage"] < V.COVERAGE_GATE, "below 80%: run mode reports insufficient data instead of testing")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print("  FAILED:", x)
sys.exit(1 if FAIL else 0)
