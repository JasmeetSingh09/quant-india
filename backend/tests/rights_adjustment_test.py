"""
rights_adjustment_test.py — rights issues in the price adjustment (2026-10-14).

322 stored exchange lines describe rights issues and none adjusted a price, so
every deep-discount issue left a fake fall in the backtest series. The feed
prints the ratio and the PREMIUM; the issue price is premium + face value, and
the face value comes from the exchange's own split lines where there is one,
else the assumed Rs 10 (which under-corrects rather than over-corrects).
Offline, on SQLite.
"""
import os
import sqlite3
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp()
open(os.path.join(TMP, "quant_platform.db"), "wb").close()
os.environ["QUANT_DATA_DIR"] = TMP
os.environ.pop("DATABASE_URL", None)

import corporate_actions as CA  # noqa: E402
import pit_validation as PV  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


days = ["2024-01-10", "2024-01-11", "2024-01-12", "2024-01-15"]
conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE bhavcopy_eod (symbol TEXT, day TEXT, close REAL, isin TEXT)")
conn.execute("CREATE TABLE corporate_actions (isin TEXT, symbol TEXT, ex_date TEXT, kind TEXT, num REAL, den REAL, "
             "amount REAL, subject TEXT, parsed INTEGER, sig TEXT)")
isin = "INE000R01011"
conn.executemany("INSERT INTO bhavcopy_eod VALUES (?,?,?,?)",
                 [("RCO.NS", d, c, isin) for d, c in zip(days, [100.0, 100.0, 70.0, 70.0])])
canonical = {isin: isin}
keys = [isin]
C = np.array([[100.0, 100.0, 70.0, 70.0]], dtype=np.float32)


def add(ex, kind, num, den, amount, subject, sig):
    conn.execute("INSERT INTO corporate_actions VALUES (?,?,?,?,?,?,?,?,1,?)",
                 (isin, "RCO", ex, kind, num, den, amount, subject, sig))


# Rights 1:1 at premium Rs 39. On a Rs 1 face value the issue price is 40, so
# the ex-rights price is (100 + 40) / 2 = 70: the raw -30% is not a return.
print("\n1. Face value from the exchange's split line")
add("2024-01-12", "rights", 1, 1, 39.0, "Rights 1:1 @ Premium Rs 39/-", "r1")
add("2020-05-05", "split", 10, 1, None, "Face Value Split From Rs 10/- To Re 1/-", "s1")
F, adj = PV._apply_adjustment(conn, keys, days, C, canonical)
adjusted = (C * F)[0]
ok(adj["applied_by_kind"].get("rights") == 1, f"the rights issue is applied ({adj['applied_by_kind']})")
ok(adj["rights_face_value"]["from split lines"] == 1, "face value Re 1 taken from the split line")
ok(np.allclose(adjusted, [70, 70, 70, 70]), f"the fake -30% fall is gone ({adjusted.tolist()})")

print("\n2. A split filed AFTER the rights issue gives the face value it split from")
conn.execute("DELETE FROM corporate_actions WHERE kind='split'")
add("2025-03-03", "split", 1, 0.5, None, "Face Value Split From Re 1/- To Re 0.50/-", "s2")
F, adj = PV._apply_adjustment(conn, keys, days, C, canonical)
adjusted = (C * F)[0]
# The later split scales every stored day equally, so continuity is the test.
ok(adj["rights_face_value"]["from split lines"] == 1 and np.allclose(adjusted / adjusted[-1], 1.0),
   f"face value Re 1 before the later split; series continuous ({adjusted.tolist()})")

print("\n3. No exchange split line: Rs 10 assumed, and the drop is under- not over-corrected")
conn.execute("DELETE FROM corporate_actions WHERE kind='split'")
add("2020-05-05", "split", 10, 1, None, "Yahoo split factor x10; verified against the price jump", "y1")
F, adj = PV._apply_adjustment(conn, keys, days, C, canonical)
m = float(F[0, 0])
want = CA.price_multiplier({"kind": "rights", "num": 1, "den": 1, "amount": 39.0}, prev_close=100.0)
ok(adj["rights_face_value"]["assumed"] == 1, "a Yahoo factor row is not read as face values")
ok(abs(want - 0.745) < 1e-12 and abs(m - want) < 1e-6,
   f"assumed issue price 49 gives (100 + 49) / 200 = 0.745 ({m:.6f})")

print("\n4. An issue priced above the market moves nothing")
conn.execute("DELETE FROM corporate_actions")
add("2024-01-12", "rights", 1, 1, 150.0, "Rights 1:1 @ Premium Rs 150/-", "r2")
F, adj = PV._apply_adjustment(conn, keys, days, C, canonical)
ok(np.allclose(F, 1.0), "no adjustment for an issue at Rs 160 when the price is 100")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
