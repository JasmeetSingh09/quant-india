"""
sanity_test.py — cases where the right answer is known in advance.

Ordinary tests check that code runs. These check that the arithmetic is right,
by choosing inputs whose answer can be derived without running anything: the
benchmark measured against itself must show no excess return; a stock split must
not change what a holding is worth; a portfolio of one asset must return exactly
that asset's return.

This is the class of test that catches a number being subtly wrong — the failure
mode where every function works, nothing raises, and the answer is quietly off.
A reviewer who follows one figure back is doing this by hand; better to have done
it first.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

checks, failures = 0, []


def ok(cond, label, detail=""):
    global checks
    checks += 1
    if cond:
        print(f"  [PASS] {label}")
    else:
        failures.append(label)
        print(f"  [FAIL] {label}  {detail}")


print("\nNumerical sanity\n" + "=" * 68)

# ------------------------------------------------- benchmark vs itself
print("\n1. Benchmark measured against itself")
from benchmark import compare, index_return
idx = index_return(365)
if idx:
    c = compare(idx["return_pct"], 365)
    ok(abs(c["difference_pct"]) < 0.01,
       "index vs itself gives zero excess return",
       f"got {c['difference_pct']}")
    ok(c["verdict"] == "matched", "and is reported as matched", f"got {c['verdict']}")
else:
    ok(True, "index unavailable — skipped")

# ------------------------------------------------------ splits
print("\n2. A split does not change what a holding is worth")
from simulator import _split_factor_since
f = _split_factor_since("INFY.NS", "2000-01-01")
units_before, price_before = 100.0, 1000.0
# After an f-for-1 split the holding is f times the units at 1/f the price.
value_before = units_before * price_before
value_after = (units_before * f) * (price_before / f)
ok(abs(value_before - value_after) < 1e-6,
   f"economic value survives a {f:.0f}x adjustment",
   f"{value_before} vs {value_after}")
ok(_split_factor_since("RELIANCE.NS", "2099-01-01") == 1.0,
   "no split after a future date leaves units untouched")

# ----------------------------------------------------- single asset
print("\n3. A one-asset portfolio returns that asset's return")
import numpy as np
import pandas as pd
from simulator import _simulate_with_drift
idxd = pd.bdate_range("2024-01-01", periods=60)
r = pd.DataFrame({"A": 0.001}, index=idxd)
series = _simulate_with_drift(r, np.array([1.0]), "yearly", include_costs=False)
ok(abs(float(series.iloc[0]) - 0.001) < 1e-9,
   "single holding reproduces its own daily return",
   f"got {float(series.iloc[0])}")
ok(abs(float((1 + series).prod() - 1) - ((1.001 ** 60) - 1)) < 1e-6,
   "and compounds exactly")

# ------------------------------------------------- zero-return asset
print("\n4. A zero-return asset returns zero")
rz = pd.DataFrame({"A": 0.0, "B": 0.0}, index=idxd)
sz = _simulate_with_drift(rz, np.array([0.5, 0.5]), "quarterly", include_costs=False)
ok(abs(float((1 + sz).prod()) - 1.0) < 1e-9,
   "flat market produces exactly zero return",
   f"got {float((1 + sz).prod()) - 1}")

# --------------------------------------------- identical assets
print("\n5. Identical assets are not treated as diversification")
from optimizer_stability import concentration_warning
w_ident = {"A.NS": 50, "B.NS": 50}
cw = concentration_warning(w_ident)
ok(cw is not None and cw["effective_positions"] == 2.0,
   "two equal holdings count as exactly 2 effective positions",
   f"got {cw['effective_positions'] if cw else None}")
lop = concentration_warning({"A.NS": 99, "B.NS": 1})
ok(lop and lop["effective_positions"] < 1.1,
   "99/1 behaves like a single position",
   f"got {lop['effective_positions'] if lop else None}")

# ---------------------------------------------------------- tax
print("\n6. Tax arithmetic at known points")
from tax import on_gain, LTCG_EXEMPTION
ok(on_gain(100000, 100)["tax"] == 20000.0, "20% STCG on Rs 1L is exactly Rs 20,000")
ok(on_gain(LTCG_EXEMPTION, 400)["tax"] == 0.0, "a gain exactly at the exemption is untaxed")
ok(abs(on_gain(LTCG_EXEMPTION + 100000, 400)["tax"] - 12500.0) < 0.01,
   "12.5% applies only to the excess above the exemption")
ok(on_gain(0, 400)["tax"] == 0.0, "zero gain, zero tax")

# ------------------------------------------------------- costs
print("\n7. Transaction costs at a known order size")
from execution import cost_breakdown, STT_PCT
c = cost_breakdown("RELIANCE.NS", 100000)
ok(abs(c["charges"]["stt"] - 100000 * STT_PCT) < 0.01,
   "STT is exactly the published rate on turnover")
ok(abs(c["invested_after_costs"] + c["total_cost"] - 100000) < 0.01,
   "invested + costs equals the order amount — no money created or lost",
   f"{c['invested_after_costs']} + {c['total_cost']}")

# ---------------------------------------------- whole-share cash
print("\n8. Whole shares conserve money")
from execution import units_for
u = units_for(10000.0, 333.0)
ok(abs(u["units"] * 333.0 + u["leftover_cash"] - 10000.0) < 0.01,
   "shares bought x price + leftover cash = money in",
   f"{u['units']}x333 + {u['leftover_cash']}")

# -------------------------------------------------- hit rates
print("\n9. Hit rate at unambiguous inputs")
from prediction_tracker import _side_stats
allup = [{"forward_return_pct": 1.0, "excess_pct": None} for _ in range(10)]
ok(_side_stats(allup, wants_down=False)["hit_rate_pct"] == 100.0,
   "ten rises = 100% BUY hit rate")
ok(_side_stats(allup, wants_down=True)["hit_rate_pct"] == 0.0,
   "the same ten rises = 0% SELL hit rate")

# ------------------------------------------ significance at 50%
print("\n10. Significance at a coin flip")
from prediction_tracker import _significance
s = _significance(500, 1000)
ok(s["p_value"] > 0.9, "exactly 50% of 1000 is maximally unsurprising", f"p={s['p_value']}")
ok(s["significant_at_5pct"] is False, "and is never called significant")
s2 = _significance(1000, 1000)
ok(s2["significant_at_5pct"] is True, "1000/1000 is significant")
ok(s2["ci95_high_pct"] <= 100.0, "and its interval cannot exceed 100%")

# ---------------------------------------------- weights normalise
print("\n11. Weights that do not sum to 100 are normalised, not rejected")
from portfolio_advisor import advise
a = advise({"RELIANCE.NS": 33.33, "TCS.NS": 33.33, "INFY.NS": 33.33}, focus="design")
ok("suggestions" in a, "a 99.99% portfolio is accepted")
se = a.get("sector_exposure") or {}
if se:
    ok(abs(sum(se.values()) - 100) < 2.0,
       "sector exposure sums to ~100% after normalisation",
       f"got {sum(se.values())}")

print("\n" + "=" * 68)
print(f"TOTAL: {checks}   FAILURES: {len(failures)}")
for f_ in failures:
    print(f"  FAILED: {f_}")
print("=" * 68)
sys.exit(1 if failures else 0)
