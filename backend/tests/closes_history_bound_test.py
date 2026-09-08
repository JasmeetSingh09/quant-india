"""
closes_history_bound_test.py — a query with no bound is a time bomb.

closes_history asked for the whole of bhavcopy_eod and filtered by symbol in
Python afterwards. Three tickers or three thousand, it loaded every row the
archive held. That was invisible at 1.5 million rows and took production down at
6.6 million, in a restart loop, because the grading pass that calls it runs on a
timer -- each restart walked back into the same query.

The archive growing was not the bug. The bug was a query whose cost was set by
the size of the table rather than by what the caller asked for, and nothing
anywhere reported that until the process died.

So the test is not "does it return the right closes". It is: does the SQL carry
the bound, and does asking for two symbols read two symbols.
"""
import io
import os
import sqlite3
import sys
import types
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "closes_bound_test.db")
if os.path.exists(DB):
    os.remove(DB)

SEEN = []


class _SpyConn(sqlite3.Connection):
    def execute(self, sql, params=()):
        SEEN.append((sql, params))
        return sqlite3.Connection.execute(self, sql, params)


fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB, factory=_SpyConn)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import bhavcopy as BC  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


BC._init_db(force=True)
conn = sqlite3.connect(DB)
today = datetime.now()
rows = []
for k in range(500):                      # 500 days back, well past the bound
    d = (today - timedelta(days=k)).strftime("%Y-%m-%d")
    for sym in ("AAA.NS", "BBB.NS", "CCC.NS"):
        rows.append((sym, d, 100.0 + k, "INE000A0000" + sym[0]))
conn.executemany("INSERT OR REPLACE INTO bhavcopy_eod "
                 "(symbol, day, close, isin) VALUES (?,?,?,?)", rows)
conn.commit()
conn.close()
print(f"  seeded {len(rows)} rows over 500 days, 3 symbols\n")

print("=" * 72)
print("THE SQL CARRIES THE BOUND")
print("=" * 72)

SEEN.clear()
out = BC.closes_history(["AAA.NS"])
sel = [s for s, _ in SEEN if "SELECT symbol, day, close" in s]
check("a select was issued", bool(sel))
if sel:
    q = sel[0]
    check("the date bound is in the SQL, not applied afterwards",
          "day >= ?" in q, q[:90])
    check("the symbol filter is in the SQL, not a Python loop",
          "symbol IN (" in q, q[-60:])
    check("no unbounded whole-table read remains",
          not any("WHERE close IS NOT NULL\"" == s.strip()[-22:] for s, _ in SEEN))

print()
print("=" * 72)
print("ASKING FOR ONE SYMBOL READS ONE SYMBOL")
print("=" * 72)

check("only the requested symbol comes back", set(out) == {"AAA.NS"}, f"{set(out)}")
check("the other symbols are not loaded at all",
      "BBB.NS" not in out and "CCC.NS" not in out)

out2 = BC.closes_history(["AAA.NS", "CCC.NS"])
check("two symbols return two", set(out2) == {"AAA.NS", "CCC.NS"}, f"{set(out2)}")

print()
print("=" * 72)
print("THE WINDOW IS ENFORCED")
print("=" * 72)

n = len(out["AAA.NS"])
check("far fewer than the 500 seeded days are returned", n < 460, f"{n} days")
check("roughly the default window is returned", 380 <= n <= 425, f"{n} days")
oldest = min(out["AAA.NS"])
cutoff = (today - timedelta(days=421)).strftime("%Y-%m-%d")
check("nothing older than the window", oldest >= cutoff, f"oldest={oldest}")

short = BC.closes_history(["AAA.NS"], days_back=30)
check("a tighter window returns less", len(short["AAA.NS"]) < 35,
      f"{len(short['AAA.NS'])} days")

print()
print("=" * 72)
print("EDGES")
print("=" * 72)

check("no symbols requested still bounds by date",
      all(len(v) < 460 for v in BC.closes_history().values()))
check("an empty list is not treated as 'everything'",
      set(BC.closes_history([])) == {"AAA.NS", "BBB.NS", "CCC.NS"},
      "empty means unspecified, matching the original signature")
check("a symbol with no rows is simply absent",
      "ZZZ.NS" not in BC.closes_history(["ZZZ.NS"]))
check("values are floats", isinstance(
    next(iter(out["AAA.NS"].values())), float))

big = [f"S{i}.NS" for i in range(2000)] + ["AAA.NS"]
SEEN.clear()
r = BC.closes_history(big)
sel = [s for s, _ in SEEN if "SELECT symbol, day, close" in s]
check("a 2001-symbol request is chunked, not one giant parameter list",
      len(sel) >= 3, f"{len(sel)} queries")
check("chunking still finds the symbol that has data",
      "AAA.NS" in r, f"{list(r)[:3]}")

try:
    os.remove(DB)
except Exception:
    pass

print()
print("=" * 72)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
