"""
scan_collection_test.py — a partial pass must never become an observation.

Factor history cannot be backfilled. That makes two failures permanent rather
than annoying:

  A day with no completed scan is a day of research data that no later run
  recovers. Production went nine days without one because start_scan ran only
  at application startup and a pass takes hours.

  A day where 1,900 of 2,574 stocks errored, recorded as though it were a
  full sweep, is a wrong row that stays wrong. Completion used to be set the
  moment the worker pool drained, whether the stocks had scored or not.

These test both, on a database whose contents are known in advance.
"""

import os
import sqlite3
import sys
import types
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


# --------------------------------------------------------------- fixture db
DB = os.path.join(os.environ.get("TEMP", "/tmp"), "scan_collection_test.db")
if os.path.exists(DB):
    os.remove(DB)
_c = sqlite3.connect(DB)
_c.execute("""CREATE TABLE alpha_scan2 (
    ticker TEXT, alpha_score REAL, signal TEXT, confidence REAL,
    market_cap REAL, momentum REAL, quality REAL, value REAL, sentiment REAL,
    error TEXT, cycle TEXT, scanned_at TEXT, model_version TEXT,
    PRIMARY KEY (ticker, cycle))""")
_c.execute("""CREATE TABLE alpha_scan_state (
    id INTEGER PRIMARY KEY, cycle TEXT, started_at TEXT, finished_at TEXT,
    done INTEGER, total INTEGER, status TEXT, last_complete_cycle TEXT)""")
_c.execute("""CREATE TABLE bhavcopy_eod (
    symbol TEXT, day TEXT, close REAL, PRIMARY KEY (symbol, day))""")


def add_cycle(cycle, scored, errored, universe, start_hour=9, gap_at=None):
    """One scan pass, written the way the scanner writes it."""
    t = datetime.fromisoformat(f"{cycle}T{start_hour:02d}:00:00")
    for i in range(scored + errored):
        if gap_at is not None and i == gap_at:
            t += timedelta(minutes=180)          # instance slept
        t += timedelta(seconds=20)
        is_err = i >= scored
        _c.execute("INSERT INTO alpha_scan2 (ticker, alpha_score, error, cycle, "
                   "scanned_at, model_version) VALUES (?,?,?,?,?,?)",
                   (f"S{i:05d}.NS", None if is_err else 10.0,
                    "Timeout" if is_err else None, cycle,
                    t.isoformat(), "test-model"))
    for i in range(universe):
        _c.execute("INSERT OR IGNORE INTO bhavcopy_eod VALUES (?,?,?)",
                   (f"S{i:05d}.NS", cycle, 100.0))


# A clean pass, a badly degraded one, and an early cycle on a smaller market.
add_cycle("2026-08-12", scored=2380, errored=12, universe=2401)
add_cycle("2026-08-20", scored=900, errored=1600, universe=2500)
add_cycle("2026-08-24", scored=2500, errored=60, universe=2600,
          gap_at=1200)
_c.execute("INSERT INTO alpha_scan_state VALUES (1,'2026-08-24','x',NULL,2560,"
           "2600,'running','2026-08-24')")
_c.commit()
_c.close()

fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import scan_health as sh  # noqa: E402

print("\n1. Completion is measured from the rows, not from the status column")
r = sh.cycles()
by = {c["cycle"]: c for c in r["cycles"]}
ok(r["available"], "the report ran")
ok(by["2026-08-12"]["complete_by_coverage"] is True,
   f"2,380 of 2,401 on a smaller market counts as complete "
   f"({by['2026-08-12']['coverage_pct']}%)")
ok(by["2026-08-20"]["complete_by_coverage"] is False,
   f"900 of 2,500 does NOT count as complete "
   f"({by['2026-08-20']['coverage_pct']}%)")
ok(by["2026-08-24"]["complete_by_coverage"] is True,
   f"2,500 of 2,600 counts as complete ({by['2026-08-24']['coverage_pct']}%)")

print("\n2. Each cycle is measured against the universe of its own day")
ok(by["2026-08-12"]["universe_that_day"] == 2401,
   "the August 12 pass is measured against 2,401, not against a later market")
ok(by["2026-08-24"]["universe_that_day"] == 2600,
   "the August 24 pass is measured against 2,600")
ok(r["denominator"].startswith("the exchange universe"),
   "and the report says which denominator it used")

print("\n3. A degraded pass drags the completion rate down")
ok(r["cycles_complete"] == 2 and r["cycles_recorded"] == 3,
   f"2 of 3 cycles complete (got {r['cycles_complete']}/{r['cycles_recorded']})")

print("\n4. Stalls are visible in the write stream")
s = sh.stalls("2026-08-24")
ok(s["stall_count"] == 1, f"the 3-hour sleep is detected ({s['stall_count']})")
ok(s["stalled_minutes"] > 170, f"and measured ({s['stalled_minutes']} min)")
ok(s["running_minutes"] < s["elapsed_minutes"],
   "time actually working is less than wall clock, which is the point")

print("\n5. Error taxonomy")
e = sh.errors("2026-08-20")
ok(e["total_errored"] == 1600, f"all 1,600 failures counted ({e['total_errored']})")
ok(e["errors"][0]["error"] == "Timeout", "grouped by what actually went wrong")

print("\n6. The completeness rule the scanner enforces")
import universe_scan as us  # noqa: E402
ok(0 < us.MIN_COMPLETE_FRACTION <= 1.0,
   f"a completeness threshold exists ({us.MIN_COMPLETE_FRACTION:.0%})")
ok(us._scored_count("2026-08-20") == 0,
   "scored_count ignores rows from another model version")

# The rule itself, stated as arithmetic so a future edit to the constant is
# still checked against the intent rather than against itself.
for scored, universe, expect in ((2500, 2600, True), (900, 2500, False),
                                 (2340, 2600, True), (2000, 2600, False),
                                 (0, 2600, False)):
    got = (scored / universe) >= us.MIN_COMPLETE_FRACTION
    ok(got is expect,
       f"{scored} of {universe} -> {'complete' if expect else 'INCOMPLETE'}")

print("\n7. The resume guard does nothing when it should do nothing")
us._THREAD = None
us.get_state = lambda: {"status": "complete", "cycle": us._current_cycle()}
ok(us.resume_if_incomplete()["action"] == "none",
   "no restart when today's pass is already complete")

us.get_state = lambda: {"status": "incomplete", "cycle": "2020-01-01"}
started = {"n": 0}
us.start_scan = lambda *a, **k: (started.__setitem__("n", started["n"] + 1)
                                 or {"status": "started"})
ok(us.resume_if_incomplete()["action"] == "started" and started["n"] == 1,
   "restarts when the pass is unfinished")


class _Alive:
    @staticmethod
    def is_alive():
        return True


us._THREAD = _Alive()
before = started["n"]
ok(us.resume_if_incomplete()["action"] == "none" and started["n"] == before,
   "never starts a second scan on top of a live one")

print("\n8. Research snapshots refuse a small fallback universe")
import inspect  # noqa: E402
import prediction_tracker as pt  # noqa: E402
sig = inspect.signature(pt.snapshot)
ok(sig.parameters["allow_fallback"].default is False,
   "the 30-stock fallback is off unless a caller explicitly asks")
src = inspect.getsource(pt.snapshot)
ok("fallback_30" in src and "refus" in src.lower(),
   "and the refusal is recorded in the row's source, not silent")

try:
    os.remove(DB)
except Exception:
    pass

print("\n" + "=" * 66)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
