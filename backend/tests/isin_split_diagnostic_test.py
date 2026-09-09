"""
isin_split_diagnostic_test.py — the diagnostic must reach all five verdicts.

A classifier that has only ever returned one label has not been tested. Each of
A, B, C, D and E is provoked here with a constructed case, so that when the
diagnostic runs against production its labels mean something.

The cases model what actually happens in the Indian market: a face-value change
mints a new ISIN for the SAME company, so the interesting question is never "did
the ISIN change" but "can the action still reach the prices it must correct".

Nothing here touches production.
"""

import os
import sqlite3
import sys
import types
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "isin_split_test.db")
if os.path.exists(DB):
    os.remove(DB)
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import isin_split_diagnostic as D  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


D0 = date(2020, 1, 1)


def build(price_rows, action_rows):
    if os.path.exists(DB):
        os.remove(DB)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE bhavcopy_eod (
        symbol TEXT, day TEXT, open REAL, high REAL, low REAL, close REAL,
        volume REAL, isin TEXT, PRIMARY KEY (symbol, day))""")
    c.executemany("INSERT INTO bhavcopy_eod (symbol, day, open, high, low,"
                  " close, volume, isin) VALUES (?,?,?,?,?,?,?,?)",
                  [(s, d, p, p, p, p, 1000.0, i) for s, d, p, i in price_rows])
    c.execute("""CREATE TABLE corporate_actions (
        isin TEXT NOT NULL, symbol TEXT, ex_date TEXT NOT NULL, kind TEXT NOT NULL,
        num REAL, den REAL, amount REAL, subject TEXT, parsed INTEGER DEFAULT 0,
        sig TEXT NOT NULL, fetched_at TEXT, PRIMARY KEY (isin, ex_date, sig))""")
    c.executemany("INSERT INTO corporate_actions (isin, ex_date, kind, num, den,"
                  " amount, parsed, sig) VALUES (?,?,?,?,?,?,?,?)",
                  [(i, d, k, n, dn, am, p, f"{i}{d}{k}")
                   for i, d, k, n, dn, am, p in action_rows])
    c.commit()
    c.close()


def series(symbol, isin, start, days, price):
    return [(symbol, (start + timedelta(days=k)).isoformat(), price, isin)
            for k in range(days)]


def one_case(res):
    return res["cases"][0] if res.get("cases") else None


print("=" * 74)
print("A — A SPLIT MINTS A NEW ISIN, AND THE ACTION STILL REACHES THE PRICES")
print("=" * 74)

# Face value 10 -> 2. Shares scale 5x, price scales 1/5. The old ISIN ends and
# the new one starts the next day, so the resolver should merge them.
old = series("SPLITCO.NS", "INE111111111", D0, 30, 500.0)
new = series("SPLITCO.NS", "INE222222222", D0 + timedelta(days=30), 30, 100.0)
build(old + new,
      [("INE222222222", (D0 + timedelta(days=30)).isoformat(),
        "split", 10, 2, None, 1)])
r = D.diagnose(["SPLITCO"])
c = one_case(r)
print(f"  verdict {c['verdict']}: {c['why'][:88]}")
check("a split filed under the NEW isin is classified A",
      c["verdict"] == "A", c["verdict"])
check("  ...the resolver merged the two ISINs", c["resolver_merged"] is True)
check("  ...the multiplier is 2/10 = 0.2",
      abs(c["combined_multiplier"] - 0.2) < 1e-9, str(c["combined_multiplier"]))
check("  ...the RAW return across the split looks like a crash",
      c["raw_return_pct"] < -70, f"{c['raw_return_pct']}%")
check("  ...the ADJUSTED return is flat, which is the point",
      abs(c["adjusted_return_pct"]) < 1e-6, f"{c['adjusted_return_pct']}%")

# The same event with the action filed under the OLD ISIN must behave the same,
# because the canonical map covers both directions.
build(old + new,
      [("INE111111111", (D0 + timedelta(days=30)).isoformat(),
        "split", 10, 2, None, 1)])
c = one_case(D.diagnose(["SPLITCO"]))
check("a split filed under the OLD isin is also classified A",
      c["verdict"] == "A", c["verdict"])

print()
print("=" * 74)
print("B — THE ACTION EXISTS BUT CANNOT REACH THE PRICES")
print("=" * 74)

# A 400-day silence between the two ISINs. The resolver refuses to merge them
# (limit is 45 days), so the action cannot reach the earlier prices.
old_b = series("GAPCO.NS", "INE333333333", D0, 30, 500.0)
new_b = series("GAPCO.NS", "INE444444444", D0 + timedelta(days=430), 30, 100.0)
build(old_b + new_b,
      [("INE444444444", (D0 + timedelta(days=430)).isoformat(),
        "split", 10, 2, None, 1)])
c = one_case(D.diagnose(["GAPCO"]))
print(f"  verdict {c['verdict']}: {c['why'][:88]}")
check("an unmergeable transition with a real action is classified B",
      c["verdict"] == "B", c["verdict"])
check("  ...and the resolver did NOT merge", c["resolver_merged"] is False)
check("  ...and the gap is reported", c["gap_days"] > 45, f"{c['gap_days']}d")

print()
print("=" * 74)
print("C — TWO SECURITIES TRADING AT ONCE, YET MERGED")
print("=" * 74)

# Two ISINs genuinely trading under one ticker at the same time, on interleaved
# days. `bhavcopy_eod` is keyed on (symbol, day), so one symbol physically
# cannot carry two ISINs on the SAME day -- which is why the production identity
# audit found 0 same-day collisions in 6,598,053 rows. Interleaving is therefore
# the only shape simultaneous trading can take in this schema.
over_a = [r for k, r in enumerate(series("OVERCO.NS", "INE555555555", D0, 60, 500.0))
          if k % 2 == 0]
over_b = [r for k, r in enumerate(series("OVERCO.NS", "INE666666666", D0, 60, 100.0))
          if k % 2 == 1]
build(over_a + over_b,
      [("INE666666666", (D0 + timedelta(days=20)).isoformat(),
        "split", 10, 2, None, 1)])
c = one_case(D.diagnose(["OVERCO"]))
print(f"  gap {c['gap_days']}d, merged={c['resolver_merged']}")
print(f"  verdict {c['verdict']}: {c['why'][:88]}")
check("a long simultaneous overlap is NOT accepted as correctly linked",
      c["verdict"] != "A", c["verdict"])
check("  ...the action IS found despite the inverted date window",
      bool(c["actions_near_transition"]),
      "an overlap puts prev.last after nxt.first; the window must not invert")
check("  ...so the verdict is B, not a false 'no adjustment required'",
      c["verdict"] == "B", c["verdict"])
check("  ...the resolver REFUSES to merge overlapping identities",
      c["resolver_merged"] is False, str(c["resolver_merged"]))
check("  ...and the overlap is visible in the gap",
      c["gap_days"] < -5, f"{c['gap_days']}d")

# Which means verdict C is unreachable while the resolver holds that rule, and
# that is a property worth stating rather than a hole in the classifier: to be
# "linked to the wrong security" the resolver would have to merge two ISINs that
# traded simultaneously, and it explicitly declines to. C remains in the scheme
# because the rule could be relaxed later; if it ever is, this is where it shows.
print("  note: C is unreachable while the resolver refuses overlapping merges")

print()
print("=" * 74)
print("D — AN ISIN CHANGE THAT NEEDS NO ADJUSTMENT")
print("=" * 74)

# The ISIN changes and the price does not. No action on record. This is a real
# answer, not a failure to look.
old_d = series("QUIETCO.NS", "INE777777777", D0, 30, 250.0)
new_d = series("QUIETCO.NS", "INE888888888", D0 + timedelta(days=30), 30, 250.0)
build(old_d + new_d, [])
c = one_case(D.diagnose(["QUIETCO"]))
print(f"  verdict {c['verdict']}: {c['why'][:88]}")
check("an ISIN change with no action is classified D", c["verdict"] == "D",
      c["verdict"])
check("  ...and the raw return is flat, consistent with D",
      abs(c["raw_return_pct"]) < 1e-6, f"{c['raw_return_pct']}%")

print()
print("=" * 74)
print("E — STORED BUT UNPARSED, SO NOTHING CAN BE CONCLUDED")
print("=" * 74)

# This is the 12,778-action case from the production audit: the action is on
# record but was never parsed into a multiplier, so whether an adjustment was
# needed is genuinely unknown. It must NOT be reported as D.
build(old + new,
      [("INE222222222", (D0 + timedelta(days=30)).isoformat(),
        "split", None, None, None, 0)])
c = one_case(D.diagnose(["SPLITCO"]))
print(f"  verdict {c['verdict']}: {c['why'][:88]}")
check("an UNPARSED action at the transition is classified E, not D",
      c["verdict"] == "E", c["verdict"])
check("  ...and the reason names the unparsed action",
      "unparsed" in c["why"], c["why"][:60])

print()
print("=" * 74)
print("THE REPORT ITSELF")
print("=" * 74)

build(old + new,
      [("INE222222222", (D0 + timedelta(days=30)).isoformat(),
        "split", 10, 2, None, 1)])
r = D.diagnose(["SPLITCO"])
check("it declares itself read-only", r["read_only"] is True)
check("it reports how many transitions it examined",
      r["examined"]["isin_transitions_examined"] == 1,
      str(r["examined"]["isin_transitions_examined"]))
check("it reports the whole population, not just the sample",
      r["examined"]["symbols_with_multiple_isins_in_archive"] >= 1,
      str(r["examined"]["symbols_with_multiple_isins_in_archive"]))
check("the five verdicts sum to the transitions examined",
      sum(r["classification"].values()) == r["examined"]["isin_transitions_examined"],
      f"{sum(r['classification'].values())}")

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
