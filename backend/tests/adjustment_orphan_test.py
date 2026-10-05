"""
adjustment_orphan_test.py — actions filed under an ISIN with no prices (2026-10-05).

Kotak's 2026 split is filed under INE237A01010 and Britannia's 2018 split under
INE216A01014; neither ISIN appears in the price archive. Keyed by ISIN alone they
matched no row and were dropped, leaving fake crashes (Kotak -80%, Britannia -49%)
in every backtest. pit_validation._apply_adjustment now applies such an action to
the ISIN its symbol traded under just before the ex-date. Offline, on SQLite.
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

import pit_validation as PV  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


days = ["2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15"]
conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE bhavcopy_eod (symbol TEXT, day TEXT, close REAL, isin TEXT)")
conn.execute("CREATE TABLE corporate_actions (isin TEXT, symbol TEXT, ex_date TEXT, kind TEXT, num REAL, den REAL, "
             "amount REAL, subject TEXT, parsed INTEGER, sig TEXT)")
# Kotak as stored: 1,000 before the split, 200 after; the ISIN changes on the split day.
prices = [("KOTAKBANK.NS", days[0], 1000.0, "INE237A01028"), ("KOTAKBANK.NS", days[1], 1000.0, "INE237A01028"),
          ("KOTAKBANK.NS", days[2], 200.0, "INE237A01036"), ("KOTAKBANK.NS", days[3], 200.0, "INE237A01036")]
conn.executemany("INSERT INTO bhavcopy_eod VALUES (?,?,?,?)", prices)
canonical = {"INE237A01028": "INE237A01028", "INE237A01036": "INE237A01028"}
keys = ["INE237A01028"]
C = np.array([[1000.0, 1000.0, 200.0, 200.0]], dtype=np.float32)

print("\n1. A split filed under an ISIN with no prices")
conn.execute("INSERT INTO corporate_actions VALUES ('INE237A01010','KOTAKBANK','2026-01-14','split',5,1,NULL,"
             "'Face Value Split Rs 5 To Re 1',1,'s1')")
F, adj = PV._apply_adjustment(conn, keys, days, C, canonical)
adjusted = (C * F)[0]
ok(adj["actions_applied"] == 1 and adj["actions_applied_via_symbol"] == 1,
   f"applied through the symbol (applied {adj['actions_applied']}, via symbol {adj['actions_applied_via_symbol']})")
ok(np.allclose(adjusted, [200, 200, 200, 200]), f"the fake -80% crash is gone ({adjusted.tolist()})")

print("\n2. An action under a priced ISIN is applied as before, not through the symbol")
conn.execute("DELETE FROM corporate_actions")
conn.execute("INSERT INTO corporate_actions VALUES ('INE237A01028','KOTAKBANK','2026-01-14','split',5,1,NULL,'x',1,'s2')")
F, adj = PV._apply_adjustment(conn, keys, days, C, canonical)
ok(adj["actions_applied"] == 1 and adj["actions_applied_via_symbol"] == 0, "matched by ISIN directly")

print("\n3. No price history for the symbol either: skipped and counted, never guessed")
conn.execute("DELETE FROM corporate_actions")
conn.execute("INSERT INTO corporate_actions VALUES ('INE999X01010','NOSUCHCO','2026-01-14','split',5,1,NULL,'x',1,'s3')")
F, adj = PV._apply_adjustment(conn, keys, days, C, canonical)
ok(adj["actions_applied"] == 0 and adj["actions_unapplied"] == 1 and np.allclose(F, 1.0),
   "an action that matches nothing changes nothing")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
