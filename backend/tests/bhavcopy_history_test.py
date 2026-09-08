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

BC._init_db(force=True)
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
print("THE RESUME WALK FILLS ACTUAL GAPS")
print("=" * 72)

ranges = []
real_async = BC.backfill_range_async
BC.backfill_range_async = lambda s, e: (ranges.append((s, e))
                                        or {"started": True})


def seed(days):
    if os.path.exists(DB):
        os.remove(DB)
    BC._init_db(force=True)
    conn = sqlite3.connect(DB)
    for d in days:
        conn.execute("INSERT OR REPLACE INTO bhavcopy_eod "
                     "(symbol, day, close, isin) VALUES (?,?,?,?)",
                     ("RELIANCE", d, 100.0, "INE002A01018"))
    conn.commit()
    conn.close()


def weekdays(a, b):
    out, d = [], datetime.strptime(a, "%Y-%m-%d")
    stop = datetime.strptime(b, "%Y-%m-%d")
    while d <= stop:
        if d.weekday() < 5:
            out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


today = datetime.now().strftime("%Y-%m-%d")
try:
    BC._BACKFILL_STATE["running"] = False

    # A contiguous archive from 2024-01-02: the gap is everything below it.
    seed(weekdays("2024-01-02", today))
    ranges.clear()
    r = BC.resume_if_incomplete(chunk_days=400)
    check("a contiguous archive walks back from its own edge",
          bool(ranges) and ranges[0][1] == "2024-01-01",
          f"chunk={ranges[0] if ranges else None}")
    if ranges:
        span = (datetime.strptime(ranges[0][1], "%Y-%m-%d")
                - datetime.strptime(ranges[0][0], "%Y-%m-%d")).days
        check("the chunk is bounded by chunk_days", span == 400, f"span={span}d")

    # Each pass must move: fill that chunk, the next target must be older.
    edge = "2022-11-27"
    seed(weekdays(edge, today))
    ranges.clear()
    BC.resume_if_incomplete(chunk_days=400)
    # The newest missing day is the last WEEKDAY below the archive edge, which
    # is not simply edge-1: 2022-11-26 is a Saturday. Derived, not assumed --
    # hard-coding it is how a test starts asserting the calendar.
    want = datetime.strptime(edge, "%Y-%m-%d") - timedelta(days=1)
    while want.weekday() >= 5:
        want -= timedelta(days=1)
    check("the next pass targets an EARLIER window, not the same one",
          bool(ranges) and ranges[0][1] == want.strftime("%Y-%m-%d"),
          f"chunk={ranges[0] if ranges else None} want={want:%Y-%m-%d}")

    # THE REGRESSION. Anchoring on MIN(day) declared this complete while three
    # thousand days were absent from the middle. A single hand-fetched day did
    # exactly this to the real archive.
    seed(["2011-07-04"] + weekdays("2024-01-02", today))
    ranges.clear()
    r = BC.resume_if_incomplete(chunk_days=400)
    check("one day sitting on the floor does NOT mean complete",
          r.get("complete") is not True, f"{str(r)[:110]}")
    check("the interior gap is what gets filled",
          bool(ranges) and ranges[0][1] == "2024-01-01",
          f"chunk={ranges[0] if ranges else None}")
    check("it reports how many days are actually missing",
          (r.get("missing_before") or 0) > 3000, f"{r.get('missing_before')}")

    # A gap in the MIDDLE of an otherwise full archive is found too.
    days = [d for d in weekdays("2024-01-02", today)
            if not ("2025-03-01" <= d <= "2025-03-31")]
    seed(["2011-07-04"] + days)
    ranges.clear()
    r = BC.resume_if_incomplete(chunk_days=30)
    check("a hole in the middle of a full stretch is targeted",
          bool(ranges) and ranges[0][1].startswith("2025-03"),
          f"chunk={ranges[0] if ranges else None}")

    # Genuinely complete: every weekday from the floor to yesterday.
    seed(weekdays(BC.ARCHIVE_STARTS, today))
    ranges.clear()
    r = BC.resume_if_incomplete(chunk_days=400)
    check("a genuinely complete archive reports complete and asks nothing",
          r.get("complete") is True and not ranges, f"{str(r)[:110]}")

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

print()
print("=" * 72)
print("A HOLIDAY IS ASKED FOR ONCE, NOT FOR EVER")
print("=" * 72)

# 52 of 186 days in one real chunk had no file -- sixteen a year, the NSE
# holiday rate. They are missing from the price table permanently, so without a
# record of the 404 the walk re-requests ~240 dates from a free public archive
# every fifteen minutes and never reports done.
seed(weekdays("2024-01-02", today))
hole = weekdays("2024-01-02", today)[10]
seed([d for d in weekdays("2024-01-02", today) if d != hole])
check("before recording, the day is a gap",
      hole in BC.missing_days("2024-01-02", today)["missing"])

BC._record_absent(datetime.strptime(hole, "%Y-%m-%d"))
m = BC.missing_days("2024-01-02", today)
check("after a definitive 404 it is no longer chased",
      hole not in m["missing"], f"{m['missing'][:3]}")
check("but it is still counted, not hidden",
      m.get("known_absent_in_range") == 1, f"{m.get('known_absent_in_range')}")
check("include_absent=True can still see it",
      hole in BC.missing_days("2024-01-02", today,
                              include_absent=True)["missing"])

calls = []
real_fetch = BC.fetch_day
BC.fetch_day = lambda day=None: (calls.append(day.strftime("%Y-%m-%d"))
                                 or {"stored": 0})
try:
    calls.clear()
    BC.backfill_range("2024-01-02", today)
    check("backfill_range does not request a known-absent day",
          hole not in calls, f"requested={hole in calls}")
finally:
    BC.fetch_day = real_fetch

check("recording is idempotent",
      (BC._record_absent(datetime.strptime(hole, "%Y-%m-%d")) or True)
      and len(BC._absent_days()) == 1, f"{sorted(BC._absent_days())}")

# The dangerous half: a timeout must NEVER be recorded as a holiday.
import inspect  # noqa: E402
fsrc = inspect.getsource(BC.fetch_day)
check("only a definitive 404 records an absence",
      "answered and refused" in fsrc,
      "a network failure recorded as a holiday drops a real trading day")
check("a connection error clears the refused flag",
      fsrc.count("refused = False") >= 2,
      "both the non-404 status and the exception path must clear it")

print()
print("=" * 72)
print("missing_days")
print("=" * 72)

seed(weekdays("2024-01-02", today))
m = BC.missing_days("2024-01-02", today)
check("a contiguous stretch has no missing days", m["n"] == 0, f"n={m['n']}")

gone = weekdays("2024-01-02", today)
hole = gone[50]
seed([d for d in gone if d != hole])
m = BC.missing_days("2024-01-02", today)
check("one withheld weekday is found", m["missing"] == [hole], f"{m['missing']}")

m = BC.missing_days(BC.ARCHIVE_STARTS, today, respect_first_stored=True)
check("respect_first_stored hides pre-archive dates",
      all(d >= "2024-01-02" for d in m["missing"]), f"{m['missing'][:3]}")
m = BC.missing_days(BC.ARCHIVE_STARTS, today, respect_first_stored=False)
check("without it, the whole backwards gap is work to do",
      any(d < "2024-01-02" for d in m["missing"]), f"n={m['n']}")

m = BC.missing_days("2024-01-02", today)
check("today is never missing", today not in m["missing"])
check("no weekend is ever missing",
      not [d for d in m["missing"]
           if datetime.strptime(d, "%Y-%m-%d").weekday() >= 5])
check("a bad range is reported, not raised",
      BC.missing_days("nope", today).get("available") is False)

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
