"""
universe_filter_test.py — what the filter must NOT exclude matters more.

Dropping a security from the scan universe is a quiet decision. Nobody sees a
stock that was never attempted, so the dangerous failure here is not "we kept
something useless" — it is "we silently stopped scoring something real".

The suite is ordered accordingly: everything the filter must refuse to exclude
comes first, and the thing it is actually for comes last.

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

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "universe_filter_test.db")
if os.path.exists(DB):
    os.remove(DB)
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import universe_scan as U  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


NO_DATA = "No market data found for 'X.NS'. Check the symbol (NSE tickers end in .NS)."


def build(rows):
    """rows: (ticker, cycle, alpha_score, error)"""
    if os.path.exists(DB):
        os.remove(DB)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE alpha_scan2 (
        ticker TEXT NOT NULL, alpha_score REAL, signal TEXT, confidence REAL,
        market_cap REAL, momentum REAL, quality REAL, value REAL,
        sentiment REAL, error TEXT, cycle TEXT NOT NULL, scanned_at TEXT,
        PRIMARY KEY (ticker, cycle))""")
    c.executemany("INSERT INTO alpha_scan2 (ticker, cycle, alpha_score, error)"
                  " VALUES (?,?,?,?)", rows)
    c.commit()
    c.close()


def excluded():
    conn = sqlite3.connect(DB)
    try:
        return U._persistently_unscoreable(conn)
    finally:
        conn.close()


CYCLES = ["2026-09-07", "2026-09-08", "2026-09-09"]

print("=" * 74)
print("1. WHAT IT MUST NEVER EXCLUDE")
print("=" * 74)

# A stock that scores. The obvious case, and the one that would be a disaster.
build([("GOOD.NS", c, 12.5, None) for c in CYCLES])
check("a security that scores is never excluded", "GOOD.NS" not in excluded())

# Throttling. A 429 is our problem, not the security's. If rate limiting could
# evict tickers, a bad afternoon would permanently shrink the universe.
build([("THROTTLED.NS", c, None, "HTTPError 429 Too Many Requests") for c in CYCLES])
check("a rate-limited security is never excluded",
      "THROTTLED.NS" not in excluded(),
      "a 429 is our failure; evicting on it would let a bad day shrink the universe")

# Timeouts, likewise.
build([("SLOW.NS", c, None, "ReadTimeout: timed out") for c in CYCLES])
check("a timing-out security is never excluded", "SLOW.NS" not in excluded())

# An unexplained failure must NOT be silently dropped either — an error we do
# not understand is a reason to look, not a reason to stop looking.
build([("MYSTERY.NS", c, None, None) for c in CYCLES])
check("a failure with no recorded reason is never excluded",
      "MYSTERY.NS" not in excluded(),
      "an error nobody understood is a reason to look, not to stop looking")

# One bad cycle is not evidence. Eight real tickers recovered between the
# 2026-09-08 and 09-09 cycles, so a snapshot rule would have dropped them.
build([("BLIP.NS", CYCLES[0], 10.0, None),
       ("BLIP.NS", CYCLES[1], 11.0, None),
       ("BLIP.NS", CYCLES[2], None, NO_DATA)])
check("one bad cycle is not enough to exclude", "BLIP.NS" not in excluded(),
      "eight securities recovered between two real cycles")

build([("TWICE.NS", CYCLES[0], 10.0, None),
       ("TWICE.NS", CYCLES[1], None, NO_DATA),
       ("TWICE.NS", CYCLES[2], None, NO_DATA)])
check("two of three is still not enough", "TWICE.NS" not in excluded(),
      "the rule is 3 of 3, deliberately")

print()
print("=" * 74)
print("2. WHAT IT IS FOR")
print("=" * 74)

build([("DEAD.NS", c, None, NO_DATA) for c in CYCLES])
check("no market data in all three cycles IS excluded", "DEAD.NS" in excluded())

# The real shape: a mixed universe.
rows = []
for c in CYCLES:
    rows += [("GOOD.NS", c, 5.0, None),
             ("SMALL250.NS", c, None, NO_DATA),      # an index, not an equity
             ("SWARNSAR.NS", c, None, NO_DATA),      # illiquid microcap
             ("THROTTLED.NS", c, None, "HTTPError 429")]
build(rows)
ex = excluded()
check("a realistic mix excludes exactly the two with no data",
      ex == {"SMALL250.NS", "SWARNSAR.NS"}, str(sorted(ex)))

print()
print("=" * 74)
print("3. RECOVERABILITY — IT MUST LET THEM BACK IN")
print("=" * 74)

# Excluded on three failures...
build([("BACK.NS", c, None, NO_DATA) for c in CYCLES])
check("excluded while it has no data", "BACK.NS" in excluded())

# ...and back the moment data returns and ages through the window.
build([("BACK.NS", CYCLES[0], None, NO_DATA),
       ("BACK.NS", CYCLES[1], 7.0, None),
       ("BACK.NS", CYCLES[2], 7.5, None)])
check("  ...and returns once it starts scoring again",
      "BACK.NS" not in excluded(),
      "the rule reads recent history, so it is not a one-way door")

print()
print("=" * 74)
print("4. SAFETY — IT MUST NEVER BREAK A SCAN")
print("=" * 74)

# Too little history to judge.
build([("X.NS", CYCLES[0], None, NO_DATA)])
check("with only one cycle of history it excludes nothing", excluded() == set(),
      "not enough evidence to judge anything")

# A missing table must not raise into the scan loop.
if os.path.exists(DB):
    os.remove(DB)
c = sqlite3.connect(DB)
c.execute("CREATE TABLE unrelated (x INTEGER)")
c.commit()
c.close()
try:
    ex = excluded()
    ok = ex == set()
except Exception as e:
    ok = False
    ex = f"raised {type(e).__name__}"
check("a broken/absent table yields an empty set, never an exception", ok, str(ex))

# And the report is honest about what it is doing.
build([("SMALL250.NS", c, None, NO_DATA) for c in CYCLES])
r = U.unscoreable_report()
check("the report states the rule", "3 of the last 3" in r["rule"], r["rule"])
check("  ...counts what it excludes", r["excluded"] == 1, str(r["excluded"]))
check("  ...names them", r["examples"] == ["SMALL250.NS"], str(r["examples"]))
check("  ...and says it is recoverable", r["recoverable"] is True)

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
