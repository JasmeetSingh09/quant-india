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

# The filter reads history relative to today. Pinned, so this suite gives the
# same answer next month as it does now.
U._current_cycle = lambda: "2026-09-10"

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
check("the report states the rule", "last 3 attempts" in r["rule"], r["rule"])
check("  ...counts what it excludes", r["excluded"] == 1, str(r["excluded"]))
check("  ...names them", r["examples"] == ["SMALL250.NS"], str(r["examples"]))
check("  ...and says it is recoverable", r["recoverable"] is True)

print()
print("=" * 74)
print("5. OVER TIME — EXCLUDING A TICKER MUST NOT UN-EXCLUDE IT")
print("=" * 74)

# The first version of this filter worked for exactly one cycle. An excluded
# ticker is not attempted, so it writes no row; the next cycle then held no
# failure for it, it dropped below three, and it was let back in -- excluded
# about one day in four. Every fixture above is a static history, which is why
# none of them caught it. These play the scan forward a day at a time, writing
# a row only for a ticker the filter actually let through.
from datetime import date as _date, timedelta as _td


def play(days, has_data):
    """Run `days` daily cycles. has_data(day) -> whether DEAD.NS can be priced."""
    build([])
    start = _date(2026, 7, 1)
    attempted, excluded_days = [], []
    for i in range(days):
        today = (start + _td(days=i)).isoformat()
        conn = sqlite3.connect(DB)
        try:
            if "DEAD.NS" in U._persistently_unscoreable(conn, today=today):
                excluded_days.append(i)
            else:
                attempted.append(i)
                ok = has_data(i)
                conn.execute("INSERT INTO alpha_scan2 (ticker, cycle, alpha_score, error)"
                             " VALUES (?,?,?,?)",
                             ("DEAD.NS", today, 5.0 if ok else None,
                              None if ok else NO_DATA))
            conn.execute("INSERT INTO alpha_scan2 (ticker, cycle, alpha_score, error)"
                         " VALUES (?,?,?,?)", ("GOOD.NS", today, 5.0, None))
            conn.commit()
        finally:
            conn.close()
    return attempted, excluded_days


att, exd = play(60, lambda day: False)
gaps = [b - a for a, b in zip(att, att[1:])]
check("a permanently dead ticker stays excluded most days",
      len(exd) / 60 >= 0.8,
      f"excluded {len(exd)} of 60 days; the first version managed about 1 in 4")
check("  ...and is never re-admitted the day after being excluded",
      len(gaps) > 2 and all(g >= 2 for g in gaps[2:]),
      f"days between attempts: {gaps}")
check("  ...but is still re-checked on a cadence, not abandoned",
      len(gaps) > 2 and max(gaps[2:]) <= U.UNSCOREABLE_RECHECK_DAYS + 1,
      f"{len(att)} attempts in 60 days")

att, exd = play(60, lambda day: day >= 20)
check("a ticker whose data returns is re-admitted within a re-check period",
      bool(exd) and max(exd) <= 20 + U.UNSCOREABLE_RECHECK_DAYS,
      f"last excluded on day {max(exd) if exd else '-'}; data returned on day 20")
check("  ...and stays in once it scores again",
      bool(exd) and all(d in att for d in range(max(exd) + 1, 60)))

print()
print("=" * 74)
print("6. THE FAILURE AUDIT MUST NOT CALL A SKIPPED TICKER RECOVERED")
print("=" * 74)

import data_integrity as DI  # noqa: E402

build([("SKIPPED.NS", "2026-09-09", None, NO_DATA),
       ("FIXED.NS", "2026-09-09", None, NO_DATA),
       ("FIXED.NS", "2026-09-10", 12.0, None),
       ("GOOD.NS", "2026-09-10", 5.0, None)])
st = (DI.scan_failures() or {}).get("stability_vs_previous_cycle") or {}
check("a ticker that was tried and scored is recovered",
      "FIXED.NS" in st.get("recovered_today", []), str(st.get("recovered_today")))
check("a ticker that was not attempted is not called recovered",
      "SKIPPED.NS" not in st.get("recovered_today", []), str(st.get("recovered_today")))
check("  ...it is counted as not attempted instead",
      st.get("not_attempted_today") == 1
      and "SKIPPED.NS" in st.get("not_attempted_examples", []),
      str(st.get("not_attempted_examples")))

print()
print("=" * 74)
print("7. ONE NIGHT SHORT — WHO THE FILTER WILL EXCLUDE TOMORROW")
print("=" * 74)

# On 2026-09-11, 71 stocks that had scored on four straight nights all failed
# with "no market data", and Yahoo priced them again that morning. Two more
# nights like that and the filter excludes all 71 for a week. The nightly check
# needs to see that coming one night early, and to tell a source outage (names
# that were scoring) from securities that were never priceable.
AT = "2026-09-10"


def at_risk():
    conn = sqlite3.connect(DB)
    try:
        return U.at_risk_of_exclusion(conn, today=AT)
    except AttributeError as e:
        return {"missing": str(e)}
    finally:
        conn.close()


build([("WASGOOD.NS", "2026-09-07", 12.0, None),
       ("WASGOOD.NS", "2026-09-08", 12.5, None),
       ("WASGOOD.NS", "2026-09-09", None, NO_DATA),
       ("WASGOOD.NS", "2026-09-10", None, NO_DATA),
       ("ONCE.NS", "2026-09-09", 7.0, None),
       ("ONCE.NS", "2026-09-10", None, NO_DATA),
       ("NEVER.NS", "2026-09-09", None, NO_DATA),
       ("NEVER.NS", "2026-09-10", None, NO_DATA),
       ("GONE.NS", "2026-09-08", None, NO_DATA),
       ("GONE.NS", "2026-09-09", None, NO_DATA),
       ("GONE.NS", "2026-09-10", None, NO_DATA),
       ("SLOW.NS", "2026-09-08", 3.0, None),
       ("SLOW.NS", "2026-09-09", None, NO_DATA),
       ("SLOW.NS", "2026-09-10", None, "HTTPError 429 Too Many Requests"),
       ("GOOD.NS", "2026-09-10", 5.0, None)])
r = at_risk()
check("the report exists", "missing" not in r and isinstance(r.get("at_risk"), int), str(r)[:90])
if "missing" not in r:
    both = set(r.get("examples_previously_scored", [])) | set(r.get("examples_never_scored", []))
    check("two no-data nights in a row, after scoring, is reported",
          "WASGOOD.NS" in r.get("examples_previously_scored", []), str(r))
    check("  ...and counted as a stock that was scoring",
          r.get("previously_scored") == 1, str(r.get("previously_scored")))
    check("one no-data night is not at risk", "ONCE.NS" not in both)
    check("never-scored with two no-data nights is at risk, listed apart",
          "NEVER.NS" in r.get("examples_never_scored", []), str(r))
    check("a ticker already excluded is not 'at risk'", "GONE.NS" not in both,
          "it is past the risk; it is excluded")
    check("a 429 on the latest attempt does not count toward exclusion",
          "SLOW.NS" not in both, "throttling is our problem, not the security's")
    check("a scoring ticker is not at risk", "GOOD.NS" not in both)
    check("only the never-scored ticker can actually be excluded tomorrow",
          r.get("at_risk") == 1, f"at_risk={r.get('at_risk')}")
    check("the rule is stated", "last 2 attempts" in str(r.get("rule", "")),
          str(r.get("rule")))

# The nightly production check reads it through the scan-failure audit.
sf_risk = (DI.scan_failures() or {}).get("at_risk_of_exclusion") or {}
check("the scan-failure audit carries the early warning",
      sf_risk.get("previously_scored") == 1
      and "WASGOOD.NS" in sf_risk.get("examples_previously_scored", []),
      str(sf_risk)[:90] or "field absent")

if os.path.exists(DB):
    os.remove(DB)
c = sqlite3.connect(DB)
c.execute("CREATE TABLE unrelated (x INTEGER)")
c.commit()
c.close()
r = at_risk()
check("with no scan table it reports UNMEASURED, never a count of zero",
      "missing" not in r and r.get("status") == "UNMEASURED" and r.get("at_risk") is None,
      str(r)[:90])

print()
print("=" * 74)
print("8. A STOCK THAT WAS SCORING IS NEVER EXCLUDED FOR A RUN OF FAILURES")
print("=" * 74)

# The nights of 2026-09-11 and 12. 71 stocks that had scored every night failed
# twice running with "No market data found", and a third night would have had
# the filter skip them for a week. Yahoo priced every one checked, from another
# machine, the same morning. alpha_model writes that message when momentum has
# too little price history AND Yahoo's info lookup returns no market cap, and
# that lookup was failing on the server, not for the stock. A failure of ours
# must never remove a security, so a ticker that scored at any point in the
# history window is not excluded, however long its run of failures.
build([("WASGOOD.NS", "2026-09-08", 12.5, None),
       ("WASGOOD.NS", "2026-09-09", None, NO_DATA),
       ("WASGOOD.NS", "2026-09-10", None, NO_DATA),
       ("WASGOOD.NS", "2026-09-11", None, NO_DATA)])
conn = sqlite3.connect(DB)
try:
    excluded_next = U._persistently_unscoreable(conn, today="2026-09-12")
finally:
    conn.close()
check("scored four days ago, then three no-data nights: NOT excluded",
      "WASGOOD.NS" not in excluded_next, str(sorted(excluded_next)))

# ...but a ticker whose last score has aged out of the window is fair game.
start = _date(2026, 7, 1)
rows = [("FADED.NS", start.isoformat(), 4.0, None)]
rows += [("FADED.NS", (start + _td(days=i)).isoformat(), None, NO_DATA)
         for i in range(1, 73)]
build(rows)
conn = sqlite3.connect(DB)
try:
    excluded_late = U._persistently_unscoreable(conn, today="2026-09-12")
finally:
    conn.close()
check("last scored more than 60 days ago, failing ever since: excluded",
      "FADED.NS" in excluded_late,
      "the guard protects recent scorers, not every ticker that ever scored")

# The incident played forward: it scores for 20 days, then the lookup fails
# every night for the rest of the run.
att, exd = play(60, lambda day: day < 20)
check("played forward 60 days, a stock that stopped scoring on day 20 is never skipped",
      not exd and len(att) == 60,
      f"excluded on {len(exd)} days (first {exd[:3]}); attempted {len(att)} of 60")

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
