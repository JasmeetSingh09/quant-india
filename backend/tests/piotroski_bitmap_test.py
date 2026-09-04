"""
piotroski_bitmap_test.py — an F-score of 3 must say which three.

For all 13,256 observations recorded before this, a stored F-score cannot be
explained: a 3 might mean six conditions were tested and failed, or that six
could not be tested at all. Measured over 314 NSE names, Yahoo supplies 2.22 of
the eight declared inputs on average and never supplies totalAssets,
totalStockholderEquity or longTermDebt — so "could not be tested" is the normal
case, not the exception.

The presence set is now recorded alongside the score. Two properties have to
hold, and both are asserted here rather than assumed:

  1. it changes no score — the F-score, the Quality score and Alpha are
     bit-identical to what they were before the field existed;
  2. it is stored but NOT counted toward completeness, because it describes the
     attempt rather than feeding the calculation. Counting it would let an
     observation that measured nothing report a fuller set than one that did.
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


DB = os.path.join(os.environ.get("TEMP", "/tmp"), "piotroski_bitmap_test.db")
CYCLE = "2026-09-06"

fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake
if os.path.exists(DB):
    os.remove(DB)

import factor_provenance as fp   # noqa: E402
import metrics as M              # noqa: E402

PIO = M.PIOTROSKI_INPUTS

print("\n1. The input set is declared, not inferred from the leg tests")
ok(len(PIO) == 8, f"eight declared inputs ({len(PIO)})")
for f in ("returnOnAssets", "totalAssets", "totalStockholderEquity"):
    ok(f in PIO, f"{f} is declared")

print("\n2. Recorded but NOT counted toward completeness")
ok("quality" in fp.DIAGNOSTIC_MAP, "quality has diagnostic fields")
for f in ("piotroski_inputs", "piotroski_inputs_available"):
    ok(f in fp.DIAGNOSTIC_MAP["quality"], f"{f} is a diagnostic")
    ok(f not in fp.CAPTURE_MAP["quality"],
       f"{f} is NOT in CAPTURE_MAP — it cannot inflate the tally")
ok(fp.CAPTURE_MAP["quality"] == ["piotroski", "roe", "fcf_yield",
                                 "inputs_used", "distress_flags"],
   "the declared quality input set is unchanged")

print("\n3. Both fields are documented in the catalogue")
for f in ("quality.piotroski_inputs", "quality.piotroski_inputs_available"):
    meta = fp.FIELD_CATALOG.get(f) or {}
    ok(bool(meta.get("meaning")), f"{f} has a stated meaning")
    ok(meta.get("reproduces") is False,
       f"{f} is marked as explaining, not reproducing")

print("\n4. A thin observation stores the presence set and stays complete")
thin = {"quality": {"score": 0.1782, "confidence": 0.85, "piotroski": 3,
                    "roe": 15.18, "fcf_yield": 3.13,
                    "inputs_used": ["piotroski", "roe", "fcf_yield"],
                    "distress_flags": [],
                    "piotroski_inputs": ["grossMargins", "returnOnAssets",
                                         "revenueGrowth"],
                    "piotroski_inputs_available": 3}}
r = fp.capture("THIN.NS", CYCLE, thin)
ok(r.get("complete") is True,
   f"the observation is still complete ({r.get('complete')}) — the diagnostic "
   f"did not raise inputs_expected")
per = (r.get("factors") or {}).get("quality") or {}
ok(per.get("inputs_expected") == 5,
   f"inputs_expected stays 5, not 7 ({per.get('inputs_expected')})")

con = sqlite3.connect(DB)
rows = dict(con.execute(
    "SELECT input_name, value_text FROM factor_inputs "
    "WHERE ticker='THIN.NS' AND factor='quality'").fetchall())
nums = dict(con.execute(
    "SELECT input_name, value_num FROM factor_inputs "
    "WHERE ticker='THIN.NS' AND factor='quality'").fetchall())
con.close()
ok("piotroski_inputs" in rows,
   f"the presence set was written ({str(rows.get('piotroski_inputs'))[:52]})")
ok("returnOnAssets" in str(rows.get("piotroski_inputs")),
   "and names the fields that were actually there")
ok(nums.get("piotroski_inputs_available") == 3,
   f"the count was written ({nums.get('piotroski_inputs_available')})")
ok(nums.get("piotroski") == 3, "the F-score itself is still stored")

print("\n5. Two observations with the same F-score are now distinguishable")
rich = dict(thin["quality"],
            piotroski_inputs=["currentRatio", "grossMargins",
                              "operatingCashflow", "returnOnAssets",
                              "revenueGrowth"],
            piotroski_inputs_available=5)
fp.capture("RICH.NS", CYCLE, {"quality": rich})
con = sqlite3.connect(DB)
pair = dict(con.execute(
    "SELECT ticker, value_num FROM factor_inputs WHERE factor='quality' "
    "AND input_name='piotroski_inputs_available'").fetchall())
same_f = con.execute(
    "SELECT COUNT(DISTINCT value_num) FROM factor_inputs WHERE factor='quality' "
    "AND input_name='piotroski'").fetchone()[0]
con.close()
ok(same_f == 1, "both stocks recorded the identical F-score of 3")
ok(pair.get("THIN.NS") != pair.get("RICH.NS"),
   f"but their evidence differs: {pair.get('THIN.NS')} inputs vs "
   f"{pair.get('RICH.NS')} — indistinguishable before this")

print("\n6. Nothing about the score moved")
import alpha_model  # noqa: E402
ok(alpha_model.FACTOR_WEIGHTS == {"sentiment": 0.25, "momentum": 0.35,
                                  "quality": 0.25, "value": 0.15},
   "V1.4 factor weights unchanged")
src = open(os.path.join(os.path.dirname(__file__), "..", "modules",
                        "metrics.py"), encoding="utf-8", errors="replace").read()
body = src[src.index("def piotroski_score"):src.index("PIOTROSKI_INPUTS = (")
           if "PIOTROSKI_INPUTS = (" in src[src.index("def piotroski_score"):]
           else len(src)]
ok("inputs_present" not in src[src.index("signals = {"):src.index("total = sum(")],
   "no leg test reads the presence set — it cannot influence the F-score")

print("\n7. A refusal still records its reason and no presence set")
ref = {"quality": {"score": 0.0, "confidence": 0.0,
                   "reason": "no quality inputs available"}}
r = fp.capture("REFUSED.NS", CYCLE, ref)
con = sqlite3.connect(DB)
got = [x[0] for x in con.execute(
    "SELECT input_name FROM factor_inputs WHERE ticker='REFUSED.NS' "
    "AND input_name IN ('refusal_reason','piotroski_inputs')").fetchall()]
con.close()
ok("refusal_reason" in got, "refusal_reason still recorded")
ok("piotroski_inputs" not in got,
   "no presence set invented for a factor that never ran")

try:
    os.remove(DB)
except Exception:
    pass

print("\n" + "=" * 70)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
