"""
commodity_units_test.py — every commodity is shown in the unit its quote is in.

Aluminium (ALI=F) quotes per metric ton but was catalogued per pound, so the
dashboard showed about Rs 7.3 lakh per kg, some 1,000 times too high. These
checks pin each conversion to a hand-worked figure. No network.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import commodities as cm  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


def close(a, b, tol=1e-3):
    return a is not None and abs(a - b) <= tol * max(1.0, abs(b))


print("\n1. Aluminium is a per-tonne quote, shown per kg")
ok(cm.COMMODITIES["aluminium"]["unit"] == "USD/tonne", "aluminium catalogued as USD/tonne")
out, unit = cm._to_indian_units({"price": 3469.0, "prev_close": 3459.0, "change": 10.0,
                                 "change_pct": 0.29}, "USD/tonne")
ok(unit == "USD/kg", f"displayed per kg ({unit})")
ok(close(out["price"], 3.469), f"$3,469/t -> $3.469/kg ({out['price']})")
ok(close(out["change"], 0.010), "the change is scaled by the same factor")
ok(out["change_pct"] == 0.29, "the percentage change is untouched")

print("\n2. The other conversions are unchanged")
out, unit = cm._to_indian_units({"price": 5.0}, "USD/lb")
ok(unit == "USD/kg" and close(out["price"], 5.0 / 0.45359237), "copper: per lb -> per kg")
out, unit = cm._to_indian_units({"price": 3110.34768}, "USD/troy oz")
ok(unit == "USD/10g" and close(out["price"], 1000.0), "gold: per troy oz -> per 10 g")
out, unit = cm._to_indian_units({"price": 96.2}, "USD/barrel")
ok(unit == "USD/barrel" and out["price"] == 96.2, "crude passes through unchanged")
out, unit = cm._to_indian_units({"error": "no data"}, "USD/tonne")
ok(unit == "USD/tonne" and "error" in out, "an error result passes through unconverted")

print("\n3. No catalogued unit is left without a rule")
known = ("troy oz", "/lb", "/tonne", "/barrel", "/MMBtu", "/bushel", "INR/unit")
odd = [k for k, m in cm.COMMODITIES.items() if not any(u in m["unit"] for u in known)]
ok(not odd, f"every unit is one the converter knows ({odd})")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
