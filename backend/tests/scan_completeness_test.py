"""
scan_completeness_test.py — one count of the universe, everywhere (2026-11-16).

/scan/health and /scan/cycle-audit divided by every bhavcopy symbol, funds
included, while the scan has left funds and rights lines out since v1.5.0
(2026-10-05). So every cycle since read about 87% "complete" (2,509 of 2,892)
while the scan scored 2,509 of 2,514. docs/PROPOSAL_SCAN_HEALTH_DENOMINATOR_
2026-11-16.md (owner-approved) moves both onto universe_scan.
scannable_universe_size. This checks:

  1. funds (INF ISINs) and -RE rights lines are left out from 2026-10-05,
     and counted before it, when the scan still scored them;
  2. the latest stored day at or before the cycle is used, and reported;
  3. scan_health and cycle_audit report the same coverage for the same cycle;
  4. a cycle like 16 Nov counts as complete, and the 90% bar is unchanged.

Offline: temporary SQLite.

    cd backend && python tests/scan_completeness_test.py
"""
import os
import sqlite3
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="scan_completeness_")
os.environ["QUANT_DATA_DIR"] = TMP
os.environ.pop("DATABASE_URL", None)
DB = os.path.join(TMP, "t.db")

PASS = FAIL = 0


def ok(cond, label, detail=""):
    global PASS, FAIL
    PASS += bool(cond)
    FAIL += not cond
    print(f"  {'PASS' if cond else 'FAIL'}  {label}  {'' if cond else detail}")


c = sqlite3.connect(DB)
c.execute("""CREATE TABLE alpha_scan2 (
    ticker TEXT, alpha_score REAL, signal TEXT, confidence REAL,
    market_cap REAL, momentum REAL, quality REAL, value REAL, sentiment REAL,
    error TEXT, cycle TEXT, scanned_at TEXT, model_version TEXT,
    PRIMARY KEY (ticker, cycle))""")
c.execute("""CREATE TABLE alpha_scan_state (
    id INTEGER PRIMARY KEY, cycle TEXT, started_at TEXT, finished_at TEXT,
    done INTEGER, total INTEGER, status TEXT, last_complete_cycle TEXT)""")
c.execute("CREATE TABLE bhavcopy_eod (symbol TEXT, day TEXT, close REAL, isin TEXT)")

# The archive stops on 2026-09-07, as in production: 1,000 companies,
# 150 funds and 10 rights lines.
for i in range(1000):
    c.execute("INSERT INTO bhavcopy_eod VALUES (?,?,?,?)", (f"CO{i:04d}", "2026-09-07", 1.0, f"INE{i:09d}"))
for i in range(150):
    c.execute("INSERT INTO bhavcopy_eod VALUES (?,?,?,?)", (f"FUND{i:03d}", "2026-09-07", 1.0, f"INF{i:09d}"))
for i in range(10):
    c.execute("INSERT INTO bhavcopy_eod VALUES (?,?,?,?)", (f"CO{i:04d}-RE", "2026-09-07", 1.0, f"INE{i:09d}"))


def add_cycle(cycle, scored, errored):
    for i in range(scored + errored):
        c.execute("INSERT INTO alpha_scan2 (ticker, alpha_score, error, cycle, scanned_at) "
                  "VALUES (?,?,?,?,?)",
                  (f"CO{i:04d}.NS", None if i >= scored else 1.0,
                   "Timeout" if i >= scored else None, cycle, f"{cycle}T01:{i % 60:02d}:00"))


add_cycle("2026-11-16", scored=998, errored=2)        # like 16 Nov: 99.8% of the companies
add_cycle("2026-10-01", scored=1100, errored=60)      # before v1.5.0: funds were scored too
c.execute("INSERT INTO alpha_scan_state VALUES (1,'2026-11-16','x','y',1000,1000,"
          "'complete','2026-11-16')")
c.commit()
c.close()

fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import universe_scan as us                                    # noqa: E402
import scan_health as sh                                      # noqa: E402
import cycle_audit as ca                                      # noqa: E402
from model_config import SCAN_COMPLETE_FRACTION               # noqa: E402

print("\n1. WHAT IS COUNTED")
conn = sqlite3.connect(DB)
after = us.scannable_universe_size(conn, "2026-11-16")
before = us.scannable_universe_size(conn, "2026-10-01")
edge = us.scannable_universe_size(conn, us.EXCLUSIONS_FROM_CYCLE)
conn.close()
ok(after["n"] == 1000, "from 2026-10-05: companies only, no funds, no rights lines", str(after))
ok(before["n"] == 1160, "before it: everything the exchange listed", str(before))
ok(edge["exclusions_applied"] is True, "2026-10-05 itself is the first filtered cycle", str(edge))

print("\n2. WHICH DAY")
ok(after["day"] == "2026-09-07", "the latest stored day at or before the cycle is used and reported", str(after))

print("\n3. HEALTH AND AUDIT AGREE")
h = {x["cycle"]: x for x in sh.cycles()["cycles"]}
a = ca.audit(cycle="2026-11-16")
cov_check = next((x for x in a.get("checks", []) if x["check"] == "coverage meets the completeness bar"), {})
ok(h["2026-11-16"]["universe_that_day"] == 1000, "scan_health measures against 1,000", str(h["2026-11-16"]))
ok("998/1000" in str(cov_check.get("detail")), "cycle_audit measures against 1,000 too", str(cov_check))
ok(h["2026-11-16"]["funds_excluded"] is True and h["2026-10-01"]["funds_excluded"] is False,
   "each cycle says whether funds were left out")

print("\n4. THE BAR")
ok(SCAN_COMPLETE_FRACTION == 0.90, "the bar is still 90%")
ok(h["2026-11-16"]["complete_by_coverage"] is True, "a 99.8% cycle counts as complete", str(h["2026-11-16"]))
ok(cov_check.get("result") == "PASS", "and the audit agrees", str(cov_check))
ok(h["2026-10-01"]["complete_by_coverage"] is True and h["2026-10-01"]["universe_that_day"] == 1160,
   "an older cycle is judged by the rules of its time (1,100 of 1,160)", str(h["2026-10-01"]))

print(f"\nTOTAL: {PASS + FAIL}  FAILURES: {FAIL}")
sys.exit(1 if FAIL else 0)
