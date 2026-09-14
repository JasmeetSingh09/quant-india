"""
sqlite_local_test.py — the local SQLite file must not refuse a write because
another part of the app is busy with it.

On 2026-09-13 production's stock list refresh failed with "database is locked"
five seconds after startup. The screener cache build, started at the same
moment, held the write lock while it waited on Yahoo, and the refresh gave up
after SQLite's default five seconds (docs/PHASE2_FINDINGS_2026-09-14.md,
section 1).

Offline. Yahoo is a fake and every database is a temporary file.
"""
import os
import sqlite3
import sys
import tempfile
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""),
          flush=True)


TMP = tempfile.mkdtemp(prefix="sqlite_local_test_")


def hold_write_lock(path, seconds, started):
    c = sqlite3.connect(path, timeout=10)
    c.execute("BEGIN IMMEDIATE")
    started.set()
    time.sleep(seconds)
    c.rollback()
    c.close()


print("=" * 74 + "\n1. A WRITE WAITS FOR A BUSY FILE INSTEAD OF FAILING\n" + "=" * 74)
try:
    import sqlite_local  # noqa: F401
    have_helper = True
except ImportError:
    have_helper = False
check("sqlite_local exists", have_helper)

import stock_universe as SU  # noqa: E402

SU.DB_PATH = os.path.join(TMP, "universe.db")
SU._init_db()
started = threading.Event()
holder = threading.Thread(target=hold_write_lock, args=(SU.DB_PATH, 6.5, started))
holder.start()
started.wait(5)
t0 = time.time()
try:
    res, err = SU._insert_bse_fallback(), None
except sqlite3.OperationalError as e:
    res, err = None, str(e)
waited = time.time() - t0
holder.join()
check("a stock list write held up for 6.5 s waits and succeeds (the old limit was 5 s)",
      err is None and bool(res) and res.get("count", 0) > 0,
      f"waited {waited:.1f} s, error: {err}")
check("  ...because it really waited for the lock", waited >= 5.5, f"{waited:.1f} s")

print("\n" + "=" * 74 + "\n2. THE SCREENER HOLDS NO LOCK WHILE IT WAITS ON YAHOO\n" + "=" * 74)
fake_fetcher = types.ModuleType("data_fetcher")
fake_fetcher.NSE_SECTORS = {"IT": ["AAA.NS", "BBB.NS", "CCC.NS"]}
sys.modules["data_fetcher"] = fake_fetcher

import screener as SC  # noqa: E402

SC.DB_PATH = os.path.join(TMP, "screener.db")
_p = sqlite3.connect(SC.DB_PATH)
_p.execute("CREATE TABLE probe (x INTEGER)")
_p.commit()
_p.close()

in_second_fetch, release = threading.Event(), threading.Event()


class FakeTicker:
    calls = 0

    def __init__(self, ticker):
        self.ticker = ticker

    @property
    def info(self):
        FakeTicker.calls += 1
        if FakeTicker.calls == 2:        # a slow Yahoo answer, mid-build
            in_second_fetch.set()
            release.wait(5)
        return {"shortName": self.ticker, "currentPrice": 100.0,
                "marketCap": 1e11, "trailingPE": 20.0}


SC.yf = types.SimpleNamespace(Ticker=FakeTicker)
result = {}
builder = threading.Thread(target=lambda: result.update(SC.build_screener_cache()))
builder.start()
in_second_fetch.wait(5)
try:
    c = sqlite3.connect(SC.DB_PATH, timeout=0.5)
    c.execute("INSERT INTO probe VALUES (1)")
    c.commit()
    c.close()
    probe_err = None
except sqlite3.OperationalError as e:
    probe_err = str(e)
release.set()
builder.join(10)
check("while the screener waits on Yahoo, another part of the app can still write",
      probe_err is None, f"error: {probe_err}")
n = sqlite3.connect(SC.DB_PATH).execute("SELECT COUNT(*) FROM screener_metrics").fetchone()[0]
check("  ...and every fetched stock is still saved",
      result.get("count") == 3 and n == 3, f"count={result.get('count')}, rows={n}")

print("\n" + "=" * 74 + "\n3. STARTUP RUNS ONE WRITER, NOT TWO AT ONCE\n" + "=" * 74)
main_src = open(os.path.join(HERE, "..", "main.py"), encoding="utf-8").read()
check("the screener cache is not started as its own background task",
      "run_in_executor(None, ensure_screener_cache)" not in main_src
      and "run_in_executor(None, ensure_universe_loaded)" not in main_src)
check("the stock lists, then the screener cache, run in one task",
      "for step in (ensure_universe_loaded, ensure_screener_cache)" in main_src
      and "run_in_executor(None, _load_local_caches)" in main_src)

print("\n" + "=" * 74 + "\n4. NO MODULE WITH ITS OWN SQLITE FILE BYPASSES THE HELPER\n" + "=" * 74)
for mod in ("stock_universe", "screener", "alerts"):
    src = open(os.path.join(HERE, "..", "modules", f"{mod}.py"), encoding="utf-8").read()
    check(f"{mod} opens its file only through sqlite_local",
          "sqlite3.connect(" not in src and "sqlite_local.connect(" in src)

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
