"""
bhavcopy_gap_test.py — a missing trading day must be visible and repairable.

Production lost Monday 2026-09-07. It sat between a stored Friday and a stored
Tuesday, and nothing reported a problem: `fetch_day` runs once on a cron and
never retries, `resume_if_incomplete` only extends history BACKWARDS and calls
itself complete once it reaches the archive floor, and `coverage()` counted days
present rather than days expected. Three components, none of them responsible
for the recent end.

The hard part is not noticing a hole. It is not crying wolf at every weekend and
public holiday, which is what a naive "every date should be here" check does.
So these tests pin the exclusions as tightly as the detection:

    a weekday with no rows, between days we have          -> gap
    Saturday and Sunday                                   -> never a gap
    today (published after the close)                     -> never a gap
    dates before the first day ever stored                -> never a gap
    dates before ARCHIVE_STARTS                           -> never a gap

A holiday still shows up, and deliberately so: without an exchange calendar it
is indistinguishable from a failed fetch, and answering a 404 costs one polite
request while silently dropping a real trading day costs a day of history that
cannot be recovered later.
"""

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

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "bhavcopy_gap_test.db")
if os.path.exists(DB):
    os.remove(DB)
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import bhavcopy as BC  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def reset(days_present):
    """Rebuild the table holding exactly `days_present` (ISO strings)."""
    if os.path.exists(DB):
        os.remove(DB)
    BC._init_db(force=True)
    conn = sqlite3.connect(DB)
    for d in days_present:
        conn.execute("INSERT OR REPLACE INTO bhavcopy_eod "
                     "(symbol, day, close, isin) VALUES (?,?,?,?)",
                     ("RELIANCE", d, 100.0, "INE002A01018"))
    conn.commit()
    conn.close()


def weekdays_back(n, skip=()):
    """The last n weekdays before today, newest first, minus `skip`."""
    out, i = [], 1
    while len(out) < n:
        d = datetime.now() - timedelta(days=i)
        if d.weekday() < 5:
            iso = d.strftime("%Y-%m-%d")
            if iso not in skip:
                out.append(iso)
        i += 1
        if i > 120:
            break
    return out


print("=" * 72)
print("RECENT-GAP DETECTION")
print("=" * 72)

full = weekdays_back(12)
reset(full)
g = BC.recent_gaps(15)
check("intact window reports zero gaps", g["available"] and g["n"] == 0,
      f"gaps={g.get('candidate_gaps')}")

hole = full[5]
reset([d for d in full if d != hole])
g = BC.recent_gaps(15)
check("a withheld weekday is reported", hole in g["candidate_gaps"],
      f"missing={hole} found={g['candidate_gaps']}")
check("only that day is reported", g["n"] == 1, f"n={g['n']}")

# The exact production shape: Friday stored, Monday missing, Tuesday stored.
# Built from real calendar dates so the weekday logic is exercised, not mocked.
mon = None
for i in range(1, 40):
    d = datetime.now() - timedelta(days=i)
    if d.weekday() == 0:
        mon = d
        break
mon_iso = mon.strftime("%Y-%m-%d")
others = [d for d in weekdays_back(20) if d != mon_iso]
reset(sorted(set(others)))
g = BC.recent_gaps(25)
check("the Friday/Monday/Tuesday hole is caught", mon_iso in g["candidate_gaps"],
      f"monday={mon_iso}")

print()
print("=" * 72)
print("WHAT MUST NEVER BE CALLED A GAP")
print("=" * 72)

reset(weekdays_back(12))
g = BC.recent_gaps(15)
weekend = [d for d in g["candidate_gaps"]
           if datetime.strptime(d, "%Y-%m-%d").weekday() >= 5]
check("weekends are never reported", not weekend, f"found={weekend}")

today = datetime.now().strftime("%Y-%m-%d")
check("today is never reported (published after the close)",
      today not in g["candidate_gaps"])

recent = weekdays_back(3)
reset(recent)
g = BC.recent_gaps(30)
before_first = [d for d in g["candidate_gaps"] if d < min(recent)]
check("days before the first stored day are not gaps", not before_first,
      f"found={before_first[:4]}")

floor = BC.ARCHIVE_STARTS
g = BC.recent_gaps(30)
below = [d for d in g["candidate_gaps"] if d < floor]
check("days before ARCHIVE_STARTS are not gaps", not below, f"floor={floor}")

reset([])
g = BC.recent_gaps(20)
check("an empty archive reports unavailable, not 20 gaps",
      not g.get("available"), f"reason={g.get('reason')}")

print()
print("=" * 72)
print("COVERAGE SURFACES IT")
print("=" * 72)

full = weekdays_back(12)
hole = full[4]
reset([d for d in full if d != hole])
cov = BC.coverage()
check("coverage reports the gap count", cov.get("recent_gap_count") == 1,
      f"count={cov.get('recent_gap_count')}")
check("coverage names the missing day", hole in (cov.get("recent_gaps") or []),
      f"gaps={cov.get('recent_gaps')}")
check("coverage still reports its usual fields",
      all(k in cov for k in ("rows", "days", "symbols", "latest_day")))

reset(weekdays_back(12))
cov = BC.coverage()
check("a clean archive reports zero, not None", cov.get("recent_gap_count") == 0,
      f"count={cov.get('recent_gap_count')}")

print()
print("=" * 72)
print("THE REPAIR PASS")
print("=" * 72)

BC._BACKFILL_STATE["running"] = True
r = BC.backfill_recent(5)
check("defers while a deep backfill is running",
      r.get("filled") is False and "running" in (r.get("note") or ""), f"{r}")
BC._BACKFILL_STATE["running"] = False

reset(weekdays_back(12))
called = {"n": 0}
real_fetch = BC.fetch_day


def _counting_fetch(day=None):
    called["n"] += 1
    return {"stored": 0}


BC.fetch_day = _counting_fetch
try:
    r = BC.backfill_recent(8)
    check("an intact window makes zero fetches", called["n"] == 0,
          f"fetches={called['n']}")
    check("and reports nothing recovered", r.get("days_recovered") == 0, f"{r}")

    full = weekdays_back(8)
    hole = full[3]
    reset([d for d in full if d != hole])
    called["n"] = 0
    r = BC.backfill_recent(10)
    check("one missing day triggers one fetch", called["n"] == 1,
          f"fetches={called['n']}")
finally:
    BC.fetch_day = real_fetch

full = weekdays_back(8)
hole = full[3]
reset([d for d in full if d != hole])


def _fake_fetch(day=None):
    """Stand in for NSE: stores the requested day, as a real fetch would."""
    conn = sqlite3.connect(DB)
    conn.execute("INSERT OR REPLACE INTO bhavcopy_eod "
                 "(symbol, day, close, isin) VALUES (?,?,?,?)",
                 ("RELIANCE", day.strftime("%Y-%m-%d"), 100.0, "INE002A01018"))
    conn.commit()
    conn.close()
    return {"day": day.strftime("%Y%m%d"), "stored": 1}


real_fetch = BC.fetch_day
BC.fetch_day = _fake_fetch
try:
    r = BC.backfill_recent(10)
    check("a recovered day is reported", r.get("days_recovered") == 1, f"{r}")
    check("filled is True when something was recovered", r.get("filled") is True)
    g = BC.recent_gaps(12)
    check("the gap is gone after the repair", hole not in g["candidate_gaps"],
          f"remaining={g['candidate_gaps']}")
finally:
    BC.fetch_day = real_fetch

reset(weekdays_back(8)[1:])
real_fetch = BC.fetch_day


def _boom(day=None):
    raise RuntimeError("NSE returned nonsense")


BC.fetch_day = _boom
try:
    try:
        r = BC.backfill_recent(6)
        check("a failing fetch does not raise out of the repair", True,
              f"{str(r)[:60]}")
    except Exception as e:
        check("a failing fetch does not raise out of the repair", False,
              f"{type(e).__name__}: {e}")
finally:
    BC.fetch_day = real_fetch

import inspect  # noqa: E402

srcs = inspect.getsource(BC.recent_gaps)
check("recent_gaps contains no write statement",
      not any(w in srcs.upper() for w in ("INSERT", "UPDATE ", "DELETE", "DROP")))

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
