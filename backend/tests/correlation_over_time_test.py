"""
correlation_over_time_test.py: rolling and calm-versus-falling correlation,
checked against hand-computed values on synthetic prices. No network.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import correlation_time as ct  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}  {'' if cond else detail}")


def prices_from_monthly(rets, start="2020-01-31"):
    """Month-end price series whose monthly pct_change reproduces rets exactly."""
    idx = pd.date_range(start, periods=len(rets) + 1, freq="ME")
    return pd.Series(100 * np.cumprod(np.r_[1.0, 1 + np.asarray(rets)]), index=idx)


rng = np.random.default_rng(20260923)
N = 60
# Index: calm months +1%, eight falling months at -8%.
fall_pos = [15, 22, 30, 36, 41, 47, 52, 57]
idx_r = np.full(N, 0.01)
idx_r[fall_pos] = -0.08
common = rng.normal(0, 0.03, N)
a = common + rng.normal(0, 0.02, N)
b = common + rng.normal(0, 0.02, N)
c = rng.normal(0, 0.03, N)
series = {"AAA.NS": a, "BBB.NS": b, "CCC.NS": c, "^NSEI": idx_r}


def loader(t, start):
    if t not in series:
        return pd.Series(dtype=float)
    return prices_from_monthly(series[t])


res = ct.correlation_over_time(["AAA.NS", "BBB.NS", "CCC.NS"], months=36, loader=loader)
print("\n1. Runs and reports the window asked for")
ok("error" not in res, f"ran ({res.get('error')})")
ok(res["months_reported"] == 36, f"36 months reported ({res['months_reported']})")

print("\n2. Rolling average pairwise correlation matches a hand computation")
m = pd.DataFrame({k: series[k] for k in ("AAA.NS", "BBB.NS", "CCC.NS")},
                 index=pd.date_range("2020-02-29", periods=N, freq="ME"))
last = m.iloc[-12:].corr().values
want = np.mean([last[0, 1], last[0, 2], last[1, 2]])
got = res["rolling_avg_correlation"][-1]["avg_correlation"]
ok(abs(got - round(want, 3)) < 1e-9, f"last month {got} = hand-worked {want:.3f}")
ok(len(res["rolling_avg_correlation"]) == 36, "one rolling value per reported month")

print("\n3. The most correlated pair comes first")
ok(set(res["top_pairs"][0]["pair"]) == {"AAA.NS", "BBB.NS"},
   f"AAA/BBB share a common driver ({res['top_pairs'][0]['pair']})")

print("\n4. Calm versus falling months use the Nifty rule, not the holdings")
s = res["calm_vs_falling"]
reported = set(m.index[-36:].strftime("%Y-%m"))
want_fall = [m.index[p].strftime("%Y-%m") for p in fall_pos if m.index[p].strftime("%Y-%m") in reported]
ok(s["available"] and s["falling"]["month_list"] == want_fall,
   f"falling months are exactly the index's -5% months ({s['falling']['month_list']})")
fm = m.loc[pd.to_datetime([f"{x}" for x in want_fall]) + pd.offsets.MonthEnd(0)]
fc = fm.corr().values
want_f = np.mean([fc[0, 1], fc[0, 2], fc[1, 2]])
ok(abs(s["falling"]["avg_correlation"] - round(want_f, 3)) < 1e-9,
   f"falling-month correlation {s['falling']['avg_correlation']} = hand-worked {want_f:.3f}")
ok(s["calm"]["months"] + s["falling"]["months"] == 36, "every reported month is in one group")

print("\n5. Too few falling months gives no number")
series["^NSEI"] = np.full(N, 0.01)
series["^NSEI"][[50, 55]] = -0.09
r2 = ct.correlation_over_time(["AAA.NS", "BBB.NS", "CCC.NS"], months=36, loader=loader)
f2 = r2["calm_vs_falling"]["falling"]
ok(f2["avg_correlation"] is None and "Too few" in f2["note"], f"2 falling months: {f2}")
ok(r2["calm_vs_falling"]["rise_in_falling_months"] is None, "and no rise is reported")
series["^NSEI"] = idx_r

print("\n6. Missing history excludes, never fills")
series["SHORT.NS"] = rng.normal(0, 0.03, 8)
r3 = ct.correlation_over_time(["AAA.NS", "BBB.NS", "SHORT.NS", "NONE.NS"], months=36, loader=loader)
ex = {e["ticker"] for e in r3["excluded"]}
ok(ex == {"SHORT.NS", "NONE.NS"} and r3["tickers"] == ["AAA.NS", "BBB.NS"],
   f"short and empty histories excluded ({r3['excluded']})")

print("\n7. Edge cases and notes")
series["DUP.NS"] = a.copy()
r4 = ct.correlation_over_time(["AAA.NS", "DUP.NS"], months=24, loader=loader)
ok(r4["rolling_avg_correlation"][-1]["avg_correlation"] == 1.0, "identical series give 1, diagonal ignored")
ok("error" in ct.correlation_over_time(["AAA.NS"], loader=loader), "one ticker is refused")
ok("error" in ct.correlation_over_time([f"T{i}.NS" for i in range(16)], loader=loader), "16 tickers are refused")
ok(any("Forbes and Rigobon" in n for n in res["notes"]), "the Forbes-Rigobon note is always present")
series["^NSEI"] = np.array([])
r5 = ct.correlation_over_time(["AAA.NS", "BBB.NS"], months=24, loader=loader)
ok(r5["calm_vs_falling"]["available"] is False, "no index data: the split says so instead of guessing")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
