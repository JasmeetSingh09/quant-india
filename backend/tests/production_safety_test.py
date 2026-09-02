"""
production_safety_test.py — the pre-deployment gate.

Three claims that were argued from reading the code rather than demonstrated,
which is the weaker kind of confidence:

  the scanner survives a provenance failure
  an incomplete cycle cannot enter the research dataset
  duplicate protections still hold

Each is exercised here against a database, with the failure actually injected
rather than assumed not to happen.
"""

import os
import sqlite3
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


DB = os.path.join(os.environ.get("TEMP", "/tmp"), "prod_safety_test.db")
if os.path.exists(DB):
    os.remove(DB)
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import factor_history as fh          # noqa: E402
import factor_provenance as fp       # noqa: E402
import universe_scan as us           # noqa: E402

CYCLE = "2026-09-02"
GOOD = {"momentum": {"score": 0.6, "mom_12_1_pct": 10.0, "ann_vol_pct": 30.0,
                     "risk_adj": 0.3}}

print("\n6. The scanner survives a provenance failure")
us._init_db()


def _result(alpha=5.0):
    return {"alpha_score": alpha, "signal": "NEUTRAL", "confidence": 0.5,
            "factors": GOOD, "price": 100.0}


# Provenance intact: the score is stored and flagged as having inputs.
us._save_result("OK.NS", CYCLE, _result())
con = sqlite3.connect(DB)
row = con.execute("SELECT alpha_score FROM alpha_scan2 WHERE ticker='OK.NS'").fetchone()
ok(row is not None and abs(row[0] - 5.0) < 1e-9,
   "a normal stock is scored and stored")
fh_row = con.execute("SELECT alpha_score, raw_inputs_available FROM factor_history "
                     "WHERE ticker='OK.NS'").fetchone()
ok(fh_row is not None, "and reaches factor history")
con.close()

# Now break provenance capture completely and rescan a different stock.
_real_capture = fp.capture


def _explode(*a, **k):
    raise RuntimeError("provenance layer is down")


fp.capture = _explode
try:
    us._save_result("BROKEN.NS", CYCLE, _result(7.5))
    survived = True
except Exception as e:
    survived = False
    print(f"        scanner raised: {type(e).__name__}: {e}")
finally:
    fp.capture = _real_capture

ok(survived, "a raising provenance layer does not raise into the scanner")
con = sqlite3.connect(DB)
row = con.execute("SELECT alpha_score FROM alpha_scan2 "
                  "WHERE ticker='BROKEN.NS'").fetchone()
ok(row is not None and abs(row[0] - 7.5) < 1e-9,
   "the SCORE is still stored when provenance fails — the score is the product")
row = con.execute("SELECT raw_inputs_available FROM factor_history "
                  "WHERE ticker='BROKEN.NS'").fetchone()
ok(row is not None and row[0] == 0,
   "and the observation is flagged as having no inputs, not silently as having them")
con.close()

# A provenance layer whose TABLES are gone must also not take the scan down.
con = sqlite3.connect(DB)
con.execute("DROP TABLE IF EXISTS factor_inputs")
con.commit()
con.close()
fp._READY = True                      # stop it recreating them
try:
    us._save_result("NOTABLE.NS", CYCLE, _result(3.0))
    survived2 = True
except Exception:
    survived2 = False
fp._READY = False
ok(survived2, "a missing provenance table does not raise into the scanner")
con = sqlite3.connect(DB)
ok(con.execute("SELECT COUNT(*) FROM alpha_scan2 "
               "WHERE ticker='NOTABLE.NS'").fetchone()[0] == 1,
   "and that stock's score survived too")
con.close()

print("\n7. An incomplete cycle cannot become a research observation")
# Rows ARE written during a pass — a three-hour scan has to be incremental to
# survive a restart, and buffering it in memory would lose everything on the
# first redeploy. So the rule is not "no rows appear". It is that no row COUNTS
# as an observation of the market until the pass that produced it covered the
# market. Enforced for publishing and for the prediction snapshot already; the
# research dataset itself was the one place it was not.
for i in range(5):
    us._save_result(f"PARTIAL{i}.NS", CYCLE, _result(1.0 + i))

con = sqlite3.connect(DB)
rows = con.execute("SELECT COUNT(*) FROM factor_history WHERE cycle_id = ?",
                   (CYCLE,)).fetchone()[0]
graded = con.execute("SELECT COUNT(*) FROM factor_history WHERE cycle_id = ? "
                     "AND cycle_complete = 1", (CYCLE,)).fetchone()[0]
con.close()
print(f"        {rows} rows written, {graded} marked research-grade")
ok(rows > 0, "rows are written during the pass, so a restart loses nothing")
ok(graded == 0,
   "NONE of them counts as a research observation while the cycle is unfinished")

promoted = fh.mark_cycle_complete(CYCLE)
con = sqlite3.connect(DB)
graded = con.execute("SELECT COUNT(*) FROM factor_history WHERE cycle_id = ? "
                     "AND cycle_complete = 1", (CYCLE,)).fetchone()[0]
con.close()
ok(promoted > 0 and graded == rows,
   f"completing the cycle promotes all {rows} of its rows (got {graded})")

us._save_result("PARTIAL0.NS", CYCLE, _result(9.9))
con = sqlite3.connect(DB)
still = con.execute("SELECT cycle_complete FROM factor_history "
                    "WHERE ticker='PARTIAL0.NS'").fetchone()[0]
con.close()
ok(still == 1, "a later provisional write cannot un-complete a finished day")

us._save_result("OTHER.NS", "2026-09-03", _result(2.0))
con = sqlite3.connect(DB)
oth = con.execute("SELECT cycle_complete FROM factor_history "
                  "WHERE ticker='OTHER.NS'").fetchone()[0]
con.close()
ok(oth == 0, "a different, unfinished cycle stays provisional")

print("\n8. Duplicate protections")
us._save_result("OK.NS", CYCLE, _result(5.0))
us._save_result("OK.NS", CYCLE, _result(5.0))
con = sqlite3.connect(DB)
n = con.execute("SELECT COUNT(*) FROM alpha_scan2 WHERE ticker='OK.NS' "
                "AND cycle=?", (CYCLE,)).fetchone()[0]
ok(n == 1, f"alpha_scan2 holds one row per (ticker, cycle) — got {n}")
n = con.execute("SELECT COUNT(*) FROM factor_history WHERE ticker='OK.NS' "
                "AND captured_at=?", (CYCLE,)).fetchone()[0]
ok(n == 1, f"factor_history holds one row per (ticker, day, model) — got {n}")
dupes = con.execute(
    "SELECT COUNT(*) FROM (SELECT ticker, cycle_id, factor, input_name, "
    "COUNT(*) c FROM factor_inputs GROUP BY 1,2,3,4 HAVING c > 1) t").fetchone()[0]
ok(dupes == 0, f"factor_inputs has no duplicates — got {dupes}")
con.close()

try:
    os.remove(DB)
except Exception:
    pass

print("\n" + "=" * 66)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
