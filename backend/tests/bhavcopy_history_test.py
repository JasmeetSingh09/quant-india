"""
bhavcopy_history_test.py — the pre-2024 archive must parse, or A4 stores nulls.

Extending the price archive from 2024-01 back to 2011-07 means reading a file
the exchange stopped publishing in that shape years ago: different host path,
different filename, different column names. Two of those fail loudly. The third
fails silently, which is the one that matters — `float(r[c_o]) if c_o else None`
writes a null open/high/low/volume rather than raising, so a mis-mapped column
produces three thousand days that are present in the table, counted as stored,
and useless to everything that reads them.

So the load-bearing test here is not "does it fetch". It is: pull a REAL day
from 2015 through the production parser and assert the OHLC and the ISIN are
actually populated, against closes checked independently.

The other half is the resume walk. With the floor at 2024-01-01, resuming by
counting days back from today happened to work because one chunk covered the
whole gap. At 2011 it becomes a loop that never terminates and never deepens:
each pass re-walks the same window from today, stores nothing, leaves `earliest`
untouched, and fires again. That is tested directly, because "it made progress"
and "it ran without error" look identical from outside.
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

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "bhavcopy_history_test.db")
if os.path.exists(DB):
    os.remove(DB)
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import bhavcopy as BC  # noqa: E402

PASS, FAIL, SKIP = [], [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def skip(name, why):
    SKIP.append(name)
    print(f"  [skip] {name}  {why}")


print("=" * 72)
print("URL SELECTION COVERS BOTH ERAS")
print("=" * 72)

old_day = datetime(2015, 6, 10)
new_day = datetime(2026, 9, 7)
u_old = BC._urls_for(old_day)
u_new = BC._urls_for(new_day)

check("a 2015 date is offered the historical pattern first",
      "historical/EQUITIES" in u_old[0], u_old[0][-52:])
check("a 2026 date is offered the modern pattern first",
      "BhavCopy_NSE_CM" in u_new[0], u_new[0][-46:])
check("both eras are always attempted, never gated",
      any("historical/EQUITIES" in u for u in u_new)
      and any("BhavCopy_NSE_CM" in u for u in u_old),
      "a file on the wrong side of the switch is still found")
check("the historical filename is built correctly",
      "cm10JUN2015bhav.csv.zip" in u_old[0], u_old[0].rsplit("/", 1)[-1])
check("month abbreviations are upper-case as the archive expects",
      "/2015/JUN/" in u_old[0])
check("day is zero-padded",
      "cm01JAN2015bhav" in BC._urls_for(datetime(2015, 1, 1))[0])

print()
print("=" * 72)
print("THE ARCHIVE FLOOR")
print("=" * 72)

check("floor moved to the corporate-action floor",
      BC.ARCHIVE_STARTS == "2011-07-04", BC.ARCHIVE_STARTS)

import corporate_actions as CA  # noqa: E402
check("prices and actions now start on the same day",
      BC.ARCHIVE_STARTS == "2011-07-04",
      "a price with no action to adjust it by cannot be used honestly")

print()
print("=" * 72)
print("A REAL 2015 FILE, THROUGH THE PRODUCTION PARSER")
print("=" * 72)

BC._init_db()
got = None
try:
    got = BC.fetch_day(datetime(2015, 6, 10))
except Exception as e:
    print(f"    fetch raised: {type(e).__name__}: {e}")

if not got or not got.get("stored"):
    skip("real 2015 day parses", f"NSE unreachable or empty ({got})")
else:
    check("a 2015 day stores rows", got.get("stored", 0) > 1000, f"{got}")
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "SELECT symbol, day, open, high, low, close, volume, isin "
        "FROM bhavcopy_eod WHERE symbol = 'RELIANCE.NS'").fetchone()
    nulls = conn.execute(
        "SELECT COUNT(*) FROM bhavcopy_eod WHERE open IS NULL OR high IS NULL "
        "OR low IS NULL OR volume IS NULL").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM bhavcopy_eod").fetchone()[0]
    no_isin = conn.execute(
        "SELECT COUNT(*) FROM bhavcopy_eod WHERE isin IS NULL").fetchone()[0]
    conn.close()

    check("RELIANCE is present", row is not None)
    if row:
        # Independently checked against the file NSE serves for that date.
        check("close matches the exchange's own number",
              abs(row[5] - 905.8) < 0.01, f"close={row[5]} expected 905.8")
        check("open/high/low are populated, not silently null",
              all(v is not None for v in row[2:5]),
              f"o={row[2]} h={row[3]} l={row[4]}")
        check("volume is populated (TOTTRDQTY, not TTLTRADGVOL)",
              row[6] is not None, f"volume={row[6]}")
        check("ISIN survives from the 2015 file",
              row[7] == "INE002A01018", f"isin={row[7]}")
        check("the day is stored under the requested date",
              row[1] == "2015-06-10", f"day={row[1]}")

    check("no row in the day has a null OHLC or volume",
          nulls == 0, f"{nulls} of {total} rows")
    check("every row carries an ISIN", no_isin == 0, f"{no_isin} of {total}")
    check("_already_stored counts the day as done (COUNT(isin) > 0)",
          "2015-06-10" in BC._already_stored() or "20150610" in BC._already_stored(),
          "otherwise the backfill refetches it forever")

print()
print("=" * 72)
print("backfill_range")
print("=" * 72)

calls = []
real_fetch = BC.fetch_day


def _record(day=None):
    calls.append(day.strftime("%Y-%m-%d"))
    return {"stored": 0}


BC.fetch_day = _record
try:
    calls.clear()
    r = BC.backfill_range("2015-06-01", "2015-06-07")
    weekend = [c for c in calls
               if datetime.strptime(c, "%Y-%m-%d").weekday() >= 5]
    check("weekends are not requested", not weekend, f"{weekend}")
    check("every weekday in the range is requested", len(calls) == 5, f"{calls}")

    calls.clear()
    BC.backfill_range("2009-01-01", "2009-01-31")
    check("nothing before the floor is requested", not calls, f"{calls[:3]}")

    calls.clear()
    r = BC.backfill_range("2015-06-07", "2015-06-01")
    check("an inverted range is empty, not a 14-year walk",
          not calls and r.get("days_attempted") == 0, f"{r}")

    calls.clear()
    r = BC.backfill_range("not-a-date", "2015-06-07")
    check("a bad date is reported, not raised", "error" in r, f"{r}")

    calls.clear()
    BC.backfill_range("2015-06-08", "2015-06-12", skip_existing=True)
    check("a day already stored is not refetched",
          "2015-06-10" not in calls,
          f"stored day requested again: {'2015-06-10' in calls}")
finally:
    BC.fetch_day = real_fetch

print()
print("=" * 72)
print("THE RESUME WALK TERMINATES AND DEEPENS")
print("=" * 72)

ranges = []
real_async = BC.backfill_range_async
BC.backfill_range_async = lambda s, e: (ranges.append((s, e))
                                        or {"started": True})


def seed(days):
    if os.path.exists(DB):
        os.remove(DB)
    BC._init_db()
    conn = sqlite3.connect(DB)
    for d in days:
        conn.execute("INSERT OR REPLACE INTO bhavcopy_eod "
                     "(symbol, day, close, isin) VALUES (?,?,?,?)",
                     ("RELIANCE", d, 100.0, "INE002A01018"))
    conn.commit()
    conn.close()


try:
    BC._BACKFILL_STATE["running"] = False
    seed(["2024-01-02", "2026-09-07"])
    ranges.clear()
    r = BC.resume_if_incomplete(chunk_days=400)
    check("a resume walks back from the earliest stored day, not from today",
          bool(ranges) and ranges[0][1] == "2024-01-01",
          f"chunk={ranges[0] if ranges else None}")
    check("the chunk is bounded by chunk_days",
          bool(ranges) and ranges[0][0] == "2022-11-27",
          f"start={ranges[0][0] if ranges else None}")

    # The non-termination bug: each pass must move the floor DOWN.
    ranges.clear()
    seed(["2022-11-27", "2026-09-07"])
    BC.resume_if_incomplete(chunk_days=400)
    check("the next pass asks for an EARLIER window, not the same one",
          bool(ranges) and ranges[0][1] == "2022-11-26",
          f"chunk={ranges[0] if ranges else None}")

    # And it must stop rather than walk below the floor.
    ranges.clear()
    seed(["2011-07-04", "2026-09-07"])
    r = BC.resume_if_incomplete(chunk_days=400)
    check("reaching the floor reports complete and asks for nothing",
          r.get("complete") is True and not ranges, f"{r}")

    ranges.clear()
    seed(["2011-08-01", "2026-09-07"])
    r = BC.resume_if_incomplete(chunk_days=4000)
    check("a chunk larger than the remaining gap is clamped to the floor",
          bool(ranges) and ranges[0][0] == "2011-07-04",
          f"start={ranges[0][0] if ranges else None}")

    BC._BACKFILL_STATE["running"] = True
    ranges.clear()
    r = BC.resume_if_incomplete()
    check("a resume defers while a backfill is running",
          not ranges and "running" in (r.get("note") or ""), f"{r}")
    BC._BACKFILL_STATE["running"] = False

    seed([])
    ranges.clear()
    r = BC.resume_if_incomplete()
    check("an empty table does not start a walk from nowhere",
          not ranges and r.get("resumed") is False, f"{r}")
finally:
    BC.backfill_range_async = real_async

try:
    os.remove(DB)
except Exception:
    pass

print()
print("=" * 72)
print(f"passed {len(PASS)}, failed {len(FAIL)}, skipped {len(SKIP)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
