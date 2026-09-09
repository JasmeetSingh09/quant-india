"""
corporate_action_audit_test.py — the taxonomy has to be right about real lines.

This module's whole job is to decide which of the 12,778 unparsed corporate
actions are inert and which are missed price events. That decision is a
classifier over free text, and a classifier nobody argued with is a guess.

So the fixtures below are real NSE subject-line shapes, and the ones that matter
most are the adversarial pairs: a line that mentions a meeting AND a dividend
must classify as the dividend, because the money is what moves the price and the
meeting is incidental. Getting that backwards would quietly file real events as
harmless.

Nothing here touches production.
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

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "ca_audit_test.db")
if os.path.exists(DB):
    os.remove(DB)
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import corporate_action_audit as CAA  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


print("=" * 74)
print("THE CLASSIFIER, ON REAL SUBJECT-LINE SHAPES")
print("=" * 74)

CASES = [
    # inert
    ("Annual General Meeting", "meeting"),
    ("Board Meeting Intimation", "meeting"),
    ("Postal Ballot / E-Voting", "meeting"),
    ("Extra-Ordinary General Meeting", "meeting"),
    ("Change In Name", "listing_admin"),
    ("Suspension Of Trading", "listing_admin"),
    ("Interest Payment On Debenture", "interest_debt"),
    # price-affecting
    ("Face Value Split From Rs 10/- To Rs 2/-", "split"),
    ("Sub-Division Of Equity Shares", "split"),
    ("Bonus Issue 1:1", "bonus"),
    ("Bonus 6:11", "bonus"),
    ("Dividend - Rs 16.25/- Per Share", "dividend"),
    ("Interim Dividend", "dividend"),
    ("Scheme Of Arrangement / Demerger", "demerger"),
    ("Rights Issue 1:4", "rights"),
    ("Buy-Back Of Equity Shares", "buyback"),
    ("Reduction Of Capital", "capital_reduction"),
    ("Consolidation Of Shares", "consolidation"),
    ("Amalgamation", "amalgamation"),
]
for subject, expect in CASES:
    got = CAA.classify(subject)
    check(f"{subject[:44]:<44} -> {expect}", got == expect, "" if got == expect else f"got {got}")

print()
print("  the adversarial pairs — money beats meeting:")
ADVERSARIAL = [
    ("Annual General Meeting/ Dividend - Re 1/- Per Share/ E-Voting", "dividend"),
    ("Board Meeting / Bonus Issue 1:2", "bonus"),
    ("AGM / Face Value Split From Rs 10/- To Rs 1/-", "split"),
]
for subject, expect in ADVERSARIAL:
    got = CAA.classify(subject)
    check(f"  {subject[:52]:<52} -> {expect}", got == expect,
          "" if got == expect else f"got {got} -- a real event filed as harmless")

check("an empty subject is its own bucket", CAA.classify("") == "empty_subject")
check("an unknown line is NOT silently called inert",
      CAA.classify("Zzz Qqq Unknown Thing") == "unrecognised",
      "unrecognised must not be pooled with meeting/admin")

print()
print("=" * 74)
print("RECONSTRUCTIBILITY — DID THE FEED TELL US, OR NOT?")
print("=" * 74)

RECON = [
    ("split", "Face Value Split From Rs 10/- To Rs 2/-", True),
    ("split", "Sub-Division Of Equity Shares", False),
    ("bonus", "Bonus Issue 1:1", True),
    ("bonus", "Bonus Issue", False),
    ("dividend", "Dividend - Rs 16.25/- Per Share", True),
    ("dividend", "Interim Dividend", False),
    ("demerger", "Scheme Of Arrangement", False),
    ("buyback", "Buy-Back Of Equity Shares", False),
]
for bucket, subject, expect in RECON:
    ok, why = CAA.reconstructible(bucket, subject)
    check(f"{bucket:<10} {subject[:40]:<40} -> {expect}", ok == expect, why[:44])

check("a demerger is never claimed to be a single multiplier",
      CAA.reconstructible("demerger", "Demerger 1:1")[0] is False,
      "a demerger splits value across two securities; one factor cannot say that")

print()
print("=" * 74)
print("THE TAXONOMY OVER A CONSTRUCTED POPULATION")
print("=" * 74)


def build(actions, prices):
    if os.path.exists(DB):
        os.remove(DB)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE corporate_actions (
        isin TEXT NOT NULL, symbol TEXT, ex_date TEXT NOT NULL, kind TEXT NOT NULL,
        num REAL, den REAL, amount REAL, subject TEXT, parsed INTEGER DEFAULT 0,
        sig TEXT NOT NULL, fetched_at TEXT, PRIMARY KEY (isin, ex_date, sig))""")
    c.executemany("INSERT INTO corporate_actions (isin, ex_date, kind, num, den,"
                  " amount, subject, parsed, sig) VALUES (?,?,?,?,?,?,?,?,?)",
                  [(i, d, k, n, dn, am, sub, p, f"{i}{d}{k}{sub[:8]}")
                   for i, d, k, n, dn, am, sub, p in actions])
    c.execute("""CREATE TABLE bhavcopy_eod (
        symbol TEXT, day TEXT, open REAL, high REAL, low REAL, close REAL,
        volume REAL, isin TEXT, PRIMARY KEY (symbol, day))""")
    c.executemany("INSERT INTO bhavcopy_eod (symbol, day, open, high, low, close,"
                  " volume, isin) VALUES (?,?,?,?,?,?,?,?)",
                  [(s, d, p, p, p, p, 1000.0, i) for s, d, p, i in prices])
    c.commit()
    c.close()


prices = [("X.NS", f"2020-01-{k:02d}", 100.0, "INE000000001") for k in range(1, 29)]
actions = [
    # inert, inside coverage
    ("INE000000001", "2020-01-10", "other", None, None, None,
     "Annual General Meeting", 0),
    # price-affecting, reconstructible, inside coverage, NOT redundant
    ("INE000000001", "2020-01-15", "other", None, None, None,
     "Bonus Issue 1:1", 0),
    # price-affecting but NOT reconstructible
    ("INE000000001", "2020-01-20", "other", None, None, None,
     "Buy-Back Of Equity Shares", 0),
    # unparsed sitting beside a PARSED action for the same event -> redundant
    ("INE000000001", "2020-01-25", "split", 10, 2, None,
     "Face Value Split From Rs 10/- To Rs 2/-", 1),
    ("INE000000001", "2020-01-25", "other", None, None, None,
     "Annual General Meeting/ Face Value Split", 0),
    # outside price coverage
    ("INE000000001", "2031-06-01", "other", None, None, None,
     "Bonus Issue 1:2", 0),
]
build(actions, prices)
t = CAA.taxonomy()
print(f"  examined: {t['examined']}")
print(f"  headline: {t['headline']}")

check("it reads every unparsed row", t["examined"]["unparsed_rows_read"] == 5,
      str(t["examined"]["unparsed_rows_read"]))
check("  ...and says so explicitly", t["examined"]["complete"] is True)
check("the inert one is not counted as price-affecting",
      t["headline"]["inert_bucket"] >= 1, str(t["headline"]["inert_bucket"]))
check("a reconstructible bonus is recognised",
      t["headline"]["reconstructible_from_stored_text"] >= 1,
      str(t["headline"]["reconstructible_from_stored_text"]))
check("a buyback is price-affecting but NOT reconstructible",
      t["headline"]["not_reconstructible"] >= 1,
      str(t["headline"]["not_reconstructible"]))
check("an unparsed row beside a parsed one is called redundant",
      t["headline"]["redundant_with_an_already_parsed_action"] == 1,
      str(t["headline"]["redundant_with_an_already_parsed_action"]))
check("an action outside price coverage is separated",
      t["headline"]["outside_price_coverage"] == 1,
      str(t["headline"]["outside_price_coverage"]))
check("the candidate list excludes redundant and out-of-coverage rows",
      t["headline"]["price_affecting_inside_coverage_and_not_redundant"] == 2,
      str(t["headline"]["price_affecting_inside_coverage_and_not_redundant"]))
check("real subject text is returned so the classification can be checked",
      any(v for v in t["sample_subjects"].values()))

print()
print("=" * 74)
print("EVENT RECONSTRUCTION — THE JBMA SHAPE")
print("=" * 74)

# A 1:1 bonus IS recorded (multiplier 0.5) but the prices imply 0.25, because a
# 10->5 split went ex the same day and is missing. The shortfall must be
# reported as a factor of 2 and named.
pr = ([("J.NS", f"2014-10-{k:02d}", 1000.0, "INE927D01010") for k in range(1, 8)]
      + [("J.NS", f"2014-10-{k:02d}", 250.0, "INE927D01010") for k in range(8, 15)])
build([("INE927D01010", "2014-10-08", "bonus", 1, 1, None, "Bonus Issue 1:1", 1)], pr)
r = CAA.event_reconstruction("J.NS", "2014-10-08")
print(f"  implied {r['implied_multiplier_from_prices']}  recorded "
      f"{r['recorded_multiplier']}  ratio {r['recorded_over_implied']}")
print(f"  verdict: {r['verdict']}")
check("the implied multiplier comes from the prices", r["implied_multiplier_from_prices"] == 0.25)
check("the recorded multiplier is the bonus alone", r["recorded_multiplier"] == 0.5)
check("the shortfall is reported as a factor of 2",
      abs(r["recorded_over_implied"] - 2.0) < 1e-6, str(r["recorded_over_implied"]))
check("  ...and the missing action is named",
      "halving" in r["verdict"], r["verdict"][:70])

# And the control: when the record IS complete, it must say so.
pr2 = ([("K.NS", f"2014-10-{k:02d}", 1000.0, "INE111111111") for k in range(1, 8)]
       + [("K.NS", f"2014-10-{k:02d}", 500.0, "INE111111111") for k in range(8, 15)])
build([("INE111111111", "2014-10-08", "bonus", 1, 1, None, "Bonus Issue 1:1", 1)], pr2)
r2 = CAA.event_reconstruction("K.NS", "2014-10-08")
check("a complete record is reported as explaining the move",
      r2["verdict"] == "record explains the move",
      f"ratio {r2['recorded_over_implied']}")

try:
    os.remove(DB)
except Exception:
    pass

print()
print("=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
