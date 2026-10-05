"""
reparse_external_test.py — the re-parse dry run and rows from another source (2026-10-05).

Fourteen splits were added from Yahoo, verified against the price jump. Their subject
("Yahoo split factor x5; ...") is not an exchange line, so the parser cannot reproduce
it, and the dry run counted them as DROP, blocking every re-parse. The apply step only
inserts, so they are not at risk. They are now counted as EXTERNAL; a real drop still
blocks. Offline, on a SQLite file this test creates.
"""
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp()
DB = os.path.join(TMP, "quant_platform.db")
open(DB, "wb").close()
os.environ["QUANT_DATA_DIR"] = TMP
os.environ.pop("DATABASE_URL", None)

import corporate_action_audit as CAA  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


def seed(extra=()):
    c = sqlite3.connect(DB)
    c.execute("DROP TABLE IF EXISTS corporate_actions")
    c.execute("DROP TABLE IF EXISTS bhavcopy_eod")
    c.execute("CREATE TABLE bhavcopy_eod (symbol TEXT, day TEXT, close REAL, isin TEXT)")
    c.execute("CREATE TABLE corporate_actions (isin TEXT, symbol TEXT, ex_date TEXT, kind TEXT, num REAL, den REAL, "
              "amount REAL, subject TEXT, parsed INTEGER, sig TEXT, fetched_at TEXT, PRIMARY KEY (isin, ex_date, sig))")
    c.executemany("INSERT INTO bhavcopy_eod VALUES (?,?,?,?)",
                  [("JSWSTEEL.NS", "2017-01-03", 1644.0, "INE019A01020"), ("JSWSTEEL.NS", "2017-01-04", 163.0, "INE019A01020")])
    rows = [
        # a stored exchange split the parser reads the same way: no change
        ("INE001", "AAA", "2016-01-01", "split", 10, 1, None, "Face Value Split Rs 10 To Re 1", 1, "s1"),
        # the Yahoo-verified row: unreadable by the parser by design
        ("INE019A01020", "JSWSTEEL", "2017-01-04", "split", 10, 1, None,
         "Yahoo split factor x10; verified against the price jump x10.086 on 2017-01-04 (within 10%).", 1, "y1"),
        # an unparsed consolidation the new parser can read: an ADD
        ("INE188Y01015", "VERTOZ", "2025-06-25", "other", None, None, None,
         "Consolidation Of Equity Shares From Re 1 Per Share To Rs 10 Per Share", 0, "o1"),
    ] + list(extra)
    c.executemany("INSERT INTO corporate_actions (isin, symbol, ex_date, kind, num, den, amount, subject, parsed, sig) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit(); c.close()


print("\n1. Yahoo-sourced rows are external, not drops")
seed()
d = CAA.reparse_dry_run()
ok(d["diff"]["EXTERNAL_rows_not_from_the_parser"] == 1, "the Yahoo row is counted as external")
ok(d["diff"]["DROP_would_lose_a_stored_action"] == 0 and d["diff"]["CONFLICT_would_change_a_stored_action"] == 0,
   "no drop and no conflict")
ok(d["diff"]["ADD_new_actions"] == 1 and d["safe_to_write"], "the consolidation is the one addition, and it is safe to write")

print("\n1b. Hand-verified rows are external too")
seed(extra=[("INE023M01019", "PRAKASHCON", "2012-12-13", "split", 10, 1, None,
             "Hand-verified 2026-10-05: split, 10-for-1 split (face values not confirmed). Price jump x9.61.", 1, "h1")])
d = CAA.reparse_dry_run()
ok(d["diff"]["EXTERNAL_rows_not_from_the_parser"] == 2 and d["diff"]["DROP_would_lose_a_stored_action"] == 0,
   "a hand-verified row the parser cannot read is external, not a drop")

print("\n2. A real drop still blocks the write")
seed(extra=[("INE002", "BBB", "2016-02-01", "bonus", 1, 1, None, "Something the parser cannot read", 1, "b1")])
d = CAA.reparse_dry_run()
ok(d["diff"]["DROP_would_lose_a_stored_action"] == 1 and not d["safe_to_write"],
   "a stored exchange action the parser no longer finds is still a DROP")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
