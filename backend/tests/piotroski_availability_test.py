"""
piotroski_availability_test.py — the reporter reads, and only reads.

Two properties matter and both are asserted rather than assumed:

  1. it never writes. A diagnostic that mutates the record it describes is
     worse than no diagnostic, and this one runs against the research dataset;
  2. it reports absence as absence. Cycles recorded before the presence set was
     captured have none, and the answer must say so rather than rendering an
     empty aggregate that looks like a measurement of zero.

The fixture is built to the shape production actually stores: the presence set
as its text form, the count as a number, the F-score alongside.
"""

import json
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


DB = os.path.join(os.environ.get("TEMP", "/tmp"), "pio_avail_test.db")
CYCLE, OLD = "2026-09-05", "2026-09-01"

PIO = ["returnOnAssets", "operatingCashflow", "currentRatio", "longTermDebt",
       "grossMargins", "revenueGrowth", "totalAssets", "totalStockholderEquity"]

# Deliberately uneven so a mean of 2.0 could not arise by accident:
#   60 stocks with the two reliable fields, 20 with three, 15 with five,
#    5 with none.  longTermDebt/totalAssets/totalStockholderEquity never appear.
SHAPES = [
    (60, ["grossMargins", "revenueGrowth"], 3),
    (20, ["grossMargins", "revenueGrowth", "returnOnAssets"], 4),
    (15, ["grossMargins", "revenueGrowth", "returnOnAssets",
          "currentRatio", "operatingCashflow"], 6),
    (5,  [], 1),
]
TOTAL = sum(n for n, _, _ in SHAPES)


def build():
    if os.path.exists(DB):
        os.remove(DB)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE factor_inputs (ticker TEXT, isin TEXT,
        cycle_id TEXT, observed_at TEXT, factor TEXT, input_name TEXT,
        value_num REAL, value_text TEXT, category TEXT, source TEXT,
        missing INTEGER DEFAULT 0)""")
    i = 0
    for n, present, f_score in SHAPES:
        for _ in range(n):
            tk = f"S{i:04d}.NS"
            i += 1
            c.execute("INSERT INTO factor_inputs (ticker, cycle_id, factor, "
                      "input_name, value_num, value_text, missing) "
                      "VALUES (?,?,?,?,?,?,0)",
                      (tk, CYCLE, "quality", "piotroski_inputs", None,
                       str(sorted(present))))
            c.execute("INSERT INTO factor_inputs (ticker, cycle_id, factor, "
                      "input_name, value_num, missing) VALUES (?,?,?,?,?,0)",
                      (tk, CYCLE, "quality", "piotroski_inputs_available",
                       len(present)))
            c.execute("INSERT INTO factor_inputs (ticker, cycle_id, factor, "
                      "input_name, value_num, missing) VALUES (?,?,?,?,?,0)",
                      (tk, CYCLE, "quality", "piotroski", f_score))
    # a pre-capture cycle: scores, but no presence set
    for j in range(40):
        c.execute("INSERT INTO factor_inputs (ticker, cycle_id, factor, "
                  "input_name, value_num, missing) VALUES (?,?,?,?,?,0)",
                  (f"O{j:04d}.NS", OLD, "quality", "piotroski", 4))
    c.commit()
    c.close()


def load():
    fake = types.ModuleType("db")
    fake.get_conn = lambda: sqlite3.connect(DB)
    fake.IS_POSTGRES = False
    sys.modules["db"] = fake
    sys.modules.pop("piotroski_availability", None)
    import piotroski_availability as pa
    return pa


build()
pa = load()
before = open(DB, "rb").read()
r = pa.availability(CYCLE)

print("\n1. It runs and finds the cycle")
ok(r.get("available") is True, f"available ({r.get('reason')})")
ok(r.get("observations") == TOTAL,
   f"{r.get('observations')} observations (expected {TOTAL})")
ok(r.get("cycle") == CYCLE, f"reporting on {r.get('cycle')}")

print("\n2. The distribution is the fixture's, not a plausible-looking average")
dist = {d["inputs_present"]: d["stocks"] for d in r["inputs_present_distribution"]}
for n, present, _ in SHAPES:
    ok(dist.get(len(present)) == n,
       f"{n} stocks with {len(present)} of 8 inputs (got {dist.get(len(present))})")
expected_mean = round(sum(n * len(p) for n, p, _ in SHAPES) / TOTAL, 3)
ok(abs(r["mean_inputs_present"] - expected_mean) < 1e-9,
   f"mean {r['mean_inputs_present']} == {expected_mean}")

print("\n3. Per-field availability, and absence reported as absence")
by = {b["input"]: b for b in r["by_input"]}
ok(by["grossMargins"]["present"] == 95,
   f"grossMargins present on 95 ({by['grossMargins']['present']})")
ok(by["returnOnAssets"]["present"] == 35,
   f"returnOnAssets on 35 ({by['returnOnAssets']['present']})")
ok(by["operatingCashflow"]["present"] == 15,
   f"operatingCashflow on 15 ({by['operatingCashflow']['present']})")
for f in ("longTermDebt", "totalAssets", "totalStockholderEquity"):
    ok(by[f]["present"] == 0, f"{f} never supplied (0)")
ok(sorted(r["never_supplied"]) == sorted(
    ["longTermDebt", "totalAssets", "totalStockholderEquity"]),
   f"never_supplied names exactly those three ({r['never_supplied']})")

print("\n4. Substring safety — returnOnAssets must not count as totalAssets")
ok(by["totalAssets"]["present"] == 0 and by["returnOnAssets"]["present"] == 35,
   "the two Assets fields are counted separately")

print("\n5. Each field says which legs it decides")
ok(by["returnOnAssets"]["decides_legs"] == ["roa_positive", "roa_above_5pct"],
   f"returnOnAssets decides two legs ({by['returnOnAssets']['decides_legs']})")
ok(by["grossMargins"]["decides_legs"] == ["gross_margin_above_20pct"],
   "grossMargins decides one")

print("\n6. F-score is cross-tabulated against the evidence behind it")
grid = {g["f_score"]: g for g in r["f_score_by_inputs_present"]}
ok(set(grid) == {1, 3, 4, 6}, f"four distinct F-scores ({sorted(grid)})")
ok(grid[3]["by_inputs"] == {2: 60},
   f"every F=3 had exactly 2 inputs ({grid[3]['by_inputs']})")
ok(grid[1]["by_inputs"] == {0: 5},
   f"every F=1 had zero inputs ({grid[1]['by_inputs']}) — a score from nothing")
ok(r.get("max_f_observed") == 6, f"max F observed {r.get('max_f_observed')}")

print("\n7. A pre-capture cycle is reported as such, not as zeros")
r2 = pa.availability(OLD)
ok(r2.get("available") is True, "it still answers")
ok(r2.get("observations", 0) == 0, "no presence set for that cycle")
ok("no presence set" in (r2.get("note") or "").lower(),
   f"and says so ({str(r2.get('note'))[:64]})")
ok(not r2.get("by_input"), "no per-field table invented for it")

print("\n8. The trend across cycles is available for the accumulate-over-time plan")
cyc = {c["cycle"]: c for c in r["by_cycle"]}
ok(CYCLE in cyc, f"the capturing cycle is listed ({list(cyc)})")
ok(OLD not in cyc, "the pre-capture cycle is not, having nothing to report")
ok(cyc[CYCLE]["observations"] == TOTAL, "with its observation count")

print("\n9. Nothing was written")
after = open(DB, "rb").read()
ok(before == after, f"the database is byte-identical ({len(before)} bytes)")
con = sqlite3.connect(DB)
n_rows = con.execute("SELECT COUNT(*) FROM factor_inputs").fetchone()[0]
con.close()
ok(n_rows == TOTAL * 3 + 40, f"row count unchanged ({n_rows})")
src = open(os.path.join(os.path.dirname(__file__), "..", "modules",
                        "piotroski_availability.py"), encoding="utf-8").read()
for verb in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "commit("):
    ok(verb not in src, f"the module contains no {verb.rstrip('(')}")

print("\n10. A missing table returns a failure, not a crash")
os.remove(DB)
sqlite3.connect(DB).close()
pa2 = load()
r3 = pa2.availability(CYCLE)
ok(isinstance(r3, dict), "still returns a dict")
ok(r3.get("available") is True and not r3.get("by_cycle"),
   f"and reports nothing recorded rather than raising ({str(r3.get('note'))[:48]})")

try:
    os.remove(DB)
except Exception:
    pass

print("\n" + "=" * 70)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
