"""
provenance_gap_test.py — the diagnostic separates honest gaps from defects.

The whole point of this module is that a 70% completeness rate might be fine or
might be a bug, and a percentage cannot tell you which. So the fixture builds
all four situations at once, with counts chosen to be distinguishable, and the
test checks that each lands in its own bucket rather than being lumped into one
"incomplete" number.
"""

import os
import sqlite3
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


DB = os.path.join(os.environ.get("TEMP", "/tmp"), "provenance_gap_test.db")
CYCLE = "2026-09-03"

CAPTURE_MAP = {
    "momentum": ["mom_12_1_pct", "ann_vol_pct", "risk_adj"],
    "quality": ["piotroski", "roe", "fcf_yield", "inputs_used", "distress_flags"],
    "value": ["pe_ratio", "pb_ratio", "sector_pe", "sector_pb", "pe_z_score",
              "pb_z_score", "legs_used", "valued_on", "peer_count"],
    "sentiment": ["n_articles", "undated_articles", "days_back"],
}

# clean, one missing value input, sentiment did not score, capture failure,
# every value input missing
N_CLEAN, N_MISSING_VALUE, N_NO_SENTIMENT, N_CAPTURE_FAIL, N_MISMATCH = 60, 25, 10, 3, 2


def build():
    if os.path.exists(DB):
        os.remove(DB)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE factor_history (ticker TEXT, captured_at TEXT,
        model TEXT, momentum REAL, quality REAL, value REAL, sentiment REAL,
        raw_inputs_available INTEGER DEFAULT 0, cycle_id TEXT)""")
    c.execute("""CREATE TABLE factor_inputs (ticker TEXT, cycle_id TEXT,
        factor TEXT, input_name TEXT, value_num REAL, missing INTEGER)""")
    c.execute("""CREATE TABLE factor_input_peers (ticker TEXT, cycle_id TEXT)""")
    c.execute("""CREATE TABLE factor_input_articles (ticker TEXT, cycle_id TEXT)""")

    def hist(tk, complete, sentiment=1.0):
        c.execute("INSERT INTO factor_history (ticker, captured_at, model, "
                  "momentum, quality, value, sentiment, raw_inputs_available, "
                  "cycle_id) VALUES (?,?,?,?,?,?,?,?,?)",
                  (tk, CYCLE, "v1", 0.3, 0.5, 0.2, sentiment,
                   1 if complete else 0, CYCLE))

    def inputs(tk, factors, missing_names=()):
        for f in factors:
            for k in CAPTURE_MAP[f]:
                c.execute("INSERT INTO factor_inputs VALUES (?,?,?,?,?,?)",
                          (tk, CYCLE, f, k, None if k in missing_names else 1.0,
                           1 if k in missing_names else 0))

    every = list(CAPTURE_MAP)
    for i in range(N_CLEAN):
        tk = f"C{i:04d}.NS"
        hist(tk, True)
        inputs(tk, every)
        c.execute("INSERT INTO factor_input_peers VALUES (?,?)", (tk, CYCLE))
        c.execute("INSERT INTO factor_input_articles VALUES (?,?)", (tk, CYCLE))
    for i in range(N_MISSING_VALUE):                # honest gap: no peers found
        tk = f"V{i:04d}.NS"
        hist(tk, False)
        inputs(tk, every, missing_names=("sector_pe", "peer_count"))
    for i in range(N_NO_SENTIMENT):                 # factor never scored
        tk = f"N{i:04d}.NS"
        hist(tk, True, sentiment=None)
        inputs(tk, ["momentum", "quality", "value"])
    for i in range(N_CAPTURE_FAIL):                 # scored, nothing written
        tk = f"X{i:04d}.NS"
        hist(tk, False)
        inputs(tk, ["momentum", "value", "sentiment"])   # quality absent
    for i in range(N_MISMATCH):                     # scored from nothing
        tk = f"M{i:04d}.NS"
        hist(tk, False)
        inputs(tk, ["momentum", "quality", "sentiment"])
        inputs(tk, ["value"], missing_names=CAPTURE_MAP["value"])
    c.commit()
    c.close()


def run():
    fake = types.ModuleType("db")
    fake.get_conn = lambda: sqlite3.connect(DB)
    fake.IS_POSTGRES = False
    sys.modules["db"] = fake
    fp = types.ModuleType("factor_provenance")
    fp.CAPTURE_MAP = CAPTURE_MAP
    sys.modules["factor_provenance"] = fp
    sys.modules.pop("provenance_gap", None)
    import provenance_gap
    return provenance_gap.report(CYCLE)


build()
r = run()
total = N_CLEAN + N_MISSING_VALUE + N_NO_SENTIMENT + N_CAPTURE_FAIL + N_MISMATCH
incomplete = N_MISSING_VALUE + N_CAPTURE_FAIL + N_MISMATCH

print("\n1. The headline counts are right")
ok(r.get("available") is True, f"it ran ({r.get('reason')})")
ok(r["observations"]["total"] == total,
   f"total observations {r['observations']['total']} == {total}")
ok(r["observations"]["incomplete"] == incomplete,
   f"incomplete {r['observations']['incomplete']} == {incomplete}")

print("\n2. An honest missing input is attributed to the right factor and input")
v = r["factors"]["value"]
ok(v["blocking_completeness"] == N_MISSING_VALUE + N_MISMATCH,
   f"value blocks {v['blocking_completeness']} stocks "
   f"(expected {N_MISSING_VALUE + N_MISMATCH})")
names = {m["input"]: m["stocks"] for m in v["missing_by_input"]}
ok(names.get("sector_pe") == N_MISSING_VALUE + N_MISMATCH,
   f"and names sector_pe ({names.get('sector_pe')})")
ok(len(v["examples"]) > 0, f"with example tickers ({v['examples'][:3]})")

print("\n3. A factor that never scored is NOT held against the observation")
s = r["factors"]["sentiment"]
ok(s["did_not_score"] == N_NO_SENTIMENT,
   f"{s['did_not_score']} stocks had no sentiment score")
ok(s["blocking_completeness"] == 0,
   f"and none of them count as blocking ({s['blocking_completeness']})")
ok(s["capture_failure"] == 0,
   f"nor as a capture failure ({s['capture_failure']})")

print("\n4. A real capture failure is caught and NOT called an honest gap")
q = r["factors"]["quality"]
ok(q["capture_failure"] == N_CAPTURE_FAIL,
   f"quality wrote nothing for {q['capture_failure']} scored stocks "
   f"(expected {N_CAPTURE_FAIL})")
ok(q["blocking_completeness"] == 0,
   "and it is not double-counted as a missing input")

print("\n5. A score computed from nothing is caught")
ok(v["scoring_mismatch"] == N_MISMATCH,
   f"{v['scoring_mismatch']} stocks scored value with every input missing "
   f"(expected {N_MISMATCH})")

print("\n6. The verdict distinguishes defects from honest gaps")
ok(r["verdict"] == "DEFECT", f"defects present -> DEFECT (got {r['verdict']})")
ok(r["defects_found"] == N_CAPTURE_FAIL + N_MISMATCH,
   f"defect count {r['defects_found']} == {N_CAPTURE_FAIL + N_MISMATCH}")

print("\n7. With only honest gaps, the verdict is CLEAN")
N_CAPTURE_FAIL, N_MISMATCH = 0, 0
build()
r2 = run()
ok(r2["verdict"] == "CLEAN",
   f"missing peers alone is not a defect (got {r2['verdict']}, "
   f"{r2['defects_found']} defects)")
ok(r2["observations"]["incomplete"] == N_MISSING_VALUE,
   f"and the honest gaps are still counted ({r2['observations']['incomplete']})")
ok(r2["attribution"]["unexplained"] == 0,
   f"every incomplete row is explained ({r2['attribution']})")

print("\n8. Nothing was written")
c = sqlite3.connect(DB)
n = c.execute("SELECT COUNT(*) FROM factor_inputs").fetchone()[0]
c.close()
expected_rows = ((N_CLEAN + N_MISSING_VALUE) * sum(len(v) for v in CAPTURE_MAP.values())
                 + N_NO_SENTIMENT * sum(len(CAPTURE_MAP[f])
                                        for f in ("momentum", "quality", "value")))
ok(n == expected_rows, f"factor_inputs row count unchanged ({n} == {expected_rows})")

try:
    os.remove(DB)
except Exception:
    pass

print("\n" + "=" * 66)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
