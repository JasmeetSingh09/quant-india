"""
corporate_actions_test.py — the parser must be right, or every price before an
ex-date is wrong.

An adjustment factor is cumulative. One misread ratio does not corrupt one day;
it corrupts every price for that security before that date, and it does so
silently, because an adjusted series has no obvious tell when it is wrong. So
the parser is held to two rules and both are tested:

  1. it reads the real strings NSE writes, not an idealised format;
  2. when it cannot read one, it returns nothing and the caller records
     parsed=0. It never guesses a ratio.

Every subject line below was taken from the live feed across 2015, 2018, 2021
and 2024 — including the awkward ones, where a dividend hides inside an AGM
notice and the rupee symbol alternates between "Rs" and "Re".
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

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "corp_actions_test.db")
if os.path.exists(DB):
    os.remove(DB)
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import corporate_actions as CA  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}" + (f"   {detail}" if detail else ""))


def one(subject, kind):
    return next((a for a in CA.parse_subject(subject) if a["kind"] == kind), None)


print("\n1. SPLITS — real strings, all four shapes the feed uses")
SPLITS = [
    ("Face Value Split From Rs 10 To Rs 1", 10, 1),
    ("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share", 10, 2),
    ("Face Value Split (Sub-Division) - From Rs 5/- Per Share To Re 1/- Per Share", 5, 1),
    ("Face Value Split (Sub-Division) - From Rs 2/- Per Share To Re 1/- Per Share", 2, 1),
]
for s, a, b in SPLITS:
    got = one(s, CA.SPLIT)
    ok(got and got["num"] == a and got["den"] == b,
       f"Rs {a:g} -> Rs {b:g}", f"{s[:58]}")
    mult = CA.price_multiplier(got or {})
    ok(mult is not None and abs(mult - b / a) < 1e-12,
       f"   price multiplier {b/a:g}",
       f"a 10-to-1 split divides historical prices by 10" if a == 10 and b == 1 else "")

print("\n2. BONUSES — A:B means A new shares for every B held")
for s, a, b in [("Bonus 1:1", 1, 1), ("Bonus 2:1", 2, 1), ("Bonus 1:2", 1, 2),
                ("Bonus 6:11", 6, 11), ("Bonus 1 : 1250", 1, 1250)]:
    got = one(s, CA.BONUS)
    ok(got and got["num"] == a and got["den"] == b, f"{s}", f"{a}:{b}")
    mult = CA.price_multiplier(got or {})
    ok(mult is not None and abs(mult - b / (a + b)) < 1e-12,
       f"   price multiplier {b/(a+b):.6f}")
ok(abs(CA.price_multiplier({"kind": CA.BONUS, "num": 1, "den": 1}) - 0.5) < 1e-12,
   "a 1:1 bonus halves the historical price — shares double")

print("\n3. DIVIDENDS — buried inside AGM notices, Rs and Re both used")
for s, amt in [
    ("Annual General Meeting/ Dividend - Re 0.80/- Per Share", 0.80),
    ("Annual General Meeting/ Dividend - Rs 16.25/- Per Share", 16.25),
    ("Annual General Meeting /Dividend - Rs 1.50/- Per Share", 1.50),
    ("Annual General Meeting/ Dividend -  Re 1/- Per Share", 1.0),
    ("Annual General Meeting / Dividend Re 0.20/- Per Share", 0.20),
    ("Annual General Meeting/ Dividend - Re 1/- Per Share/ E-Voting", 1.0),
    ("Dividend - Rs 20 Per Share", 20.0),
]:
    got = one(s, CA.DIVIDEND)
    ok(got and abs(got["amount"] - amt) < 1e-9, f"Rs {amt}", s[:62])

print("\n4. DIVIDEND ADJUSTMENT NEEDS THE PRICE, AND SAYS SO WHEN IT LACKS IT")
d = {"kind": CA.DIVIDEND, "amount": 5.0}
ok(abs(CA.price_multiplier(d, prev_close=100.0) - 0.95) < 1e-12,
   "Rs 5 on a Rs 100 close -> 0.95")
ok(CA.price_multiplier(d, prev_close=None) is None,
   "with no prior close it refuses rather than assuming one")
ok(CA.price_multiplier(d, prev_close=0) is None, "a zero close is refused")
ok(CA.price_multiplier({"kind": CA.DIVIDEND, "amount": 150.0},
                       prev_close=100.0) is None,
   "a payout larger than the price is refused, not applied")

print("\n5. IT REFUSES WHAT IT CANNOT READ")
for s in ["Annual General Meeting",
          "Annual General Meeting/ E-Voting",
          "Scheme of Arrangement",
          "Buy Back of Shares",
          "Demerger",
          "Capital Reduction",
          "Rights Issue 1:4 @ Premium Rs 50 Per Share",
          "",
          "Face Value Split"]:
    acts = CA.parse_subject(s)
    priced = [a for a in acts if a["kind"] in (CA.SPLIT, CA.BONUS, CA.DIVIDEND)]
    ok(not priced, f"no adjustment invented for: {s[:52] or '(empty)'}")
ok(CA.parse_subject("Rights Issue 1:4 @ Premium Rs 50 Per Share") == [],
   "a rights price is not mistaken for a dividend")

print("\n5b. THE KNOWN GAPS, MEASURED ON THE LIVE FEED")
# Across 1,958 real rows spanning 2012-2026 the parser extracted 774 dividends,
# 37 bonuses and 17 splits. Exactly three unparsed rows contained the words
# split, bonus or dividend, and all three are correct refusals. Pinned here so
# the gap stays a documented fact rather than something rediscovered later.
ok(CA.parse_subject("Dividend") == [],
   "a bare 'Dividend' with no amount is refused — the payout size is unknown")
ok(CA.parse_subject(
    "Distribution - Rs 3.6078 Per Unit Consists Of Rs 3.6078 Per Unit As Dividend") == [],
   "a REIT/InvIT per-UNIT distribution is not read as a per-share dividend")
ok(CA.parse_subject("Rights 1:2 @ Premium Rs.1.75 Per Share") == [],
   "a rights premium is not read as a dividend")
print("       consequence: a bare 'Dividend' row is a real price drop we do not")
print("       adjust for. It is recorded with parsed=0 and counted, not guessed.")

print("\n6. ONE LINE CAN CARRY TWO ACTIONS")
both = CA.parse_subject(
    "Annual General Meeting/ Dividend - Rs 3.60 Per Share/ Bonus 1:1")
kinds = sorted(a["kind"] for a in both)
ok(kinds == [CA.BONUS, CA.DIVIDEND], f"dividend and bonus both read ({kinds})")

print("\n7. STORAGE — parsed and unparsed both recorded, only parsed adjusts")
rows = [
    {"isin": "INE001A01036", "symbol": "AAA", "exDate": "15-Jul-2015",
     "subject": "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share"},
    {"isin": "INE001A01036", "symbol": "AAA", "exDate": "20-Aug-2016",
     "subject": "Annual General Meeting/ Dividend - Rs 4/- Per Share"},
    {"isin": "INE001A01036", "symbol": "AAA", "exDate": "01-Sep-2017",
     "subject": "Annual General Meeting"},
    {"isin": "INE002B01012", "symbol": "BBB", "exDate": "10-Mar-2018",
     "subject": "Bonus 1:1"},
    {"isin": "", "symbol": "NOISIN", "exDate": "10-Mar-2018", "subject": "Bonus 1:1"},
]
res = CA.store(rows)
ok(res.get("skipped") == 1, f"a row with no ISIN is skipped ({res.get('skipped')})")
ok(res.get("priced") == 3, f"three price-affecting actions ({res.get('priced')})")
ok(res.get("unparsed") == 1, f"one unparseable subject recorded ({res.get('unparsed')})")

acts = CA.actions_for("INE001A01036")
ok(len(acts) == 2, f"only price-affecting actions come back ({len(acts)})")
ok([a["kind"] for a in acts] == [CA.SPLIT, CA.DIVIDEND],
   "in ex-date order, oldest first")
ok(acts[0]["ex_date"] == "2015-07-15",
   f"NSE's 15-Jul-2015 stored as ISO ({acts[0]['ex_date']})")

print("\n8. RE-FETCHING THE SAME MONTH DOES NOT DUPLICATE")
before = len(CA.actions_for("INE001A01036"))
CA.store(rows)
CA.store(rows)
after = len(CA.actions_for("INE001A01036"))
ok(before == after, f"still {after} rows after two refetches (was {before})")

print("\n9. COVERAGE REPORTS WHAT IS THERE")
cov = CA.coverage()
ok(cov.get("securities") == 2, f"two securities ({cov.get('securities')})")
ok(cov.get("splits") == 1 and cov.get("bonuses") == 1 and cov.get("dividends") == 1,
   f"one of each priced kind (s={cov.get('splits')} b={cov.get('bonuses')} "
   f"d={cov.get('dividends')})")
ok(cov.get("unparsed") == 1, f"the AGM is kept, flagged unparsed ({cov.get('unparsed')})")
ok(cov.get("first") == "2015-07-15" and cov.get("last") == "2018-03-10",
   f"date span {cov.get('first')} .. {cov.get('last')}")

try:
    os.remove(DB)
except Exception:
    pass

print("\n" + "=" * 72)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
