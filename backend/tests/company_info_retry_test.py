"""
company_info_retry_test.py — inside the scan, an empty or truncated company-info
answer is asked for again; outside it, a person is not kept waiting.

From 2026-09-11 Yahoo's company-info lookups came back empty or truncated during
the nightly scan while the same lookups worked from the same server outside it.
On 2026-09-12 the value factor scored for 84 of 2,573 stocks. Two things let a
bad answer through:

  - alpha_model._ticker_info cached any non-empty payload for 24 hours, so a
    truncated one stayed for the rest of the day;
  - neither it nor data_fetcher.get_info tried again, however much time the
    scan had.

Offline: yfinance.Ticker is replaced by a fake that serves a scripted sequence
of answers per ticker and counts every request.
"""
import importlib
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import yfinance  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""),
          flush=True)


def banner(title):
    print("\n" + "=" * 74 + f"\n{title}\n" + "=" * 74, flush=True)


# A payload shaped like a healthy NSE answer: every completeness sentinel present.
FULL = {"marketCap": 1.0e10, "totalRevenue": 5.0e9, "profitMargins": 0.1,
        "totalDebt": 1.0e9, "totalCash": 2.0e9, "grossMargins": 0.3,
        "revenueGrowth": 0.05, "bookValue": 100.0, "trailingPE": 15.0,
        "priceToBook": 2.0, "returnOnEquity": 0.12, "freeCashflow": 4.0e8,
        **{f"field_{i}": i for i in range(20)}}
# What a throttled answer looks like: a handful of keys, no financials.
TRUNC = {"shortName": "Sample", "currency": "INR", "symbol": "X.NS"}
SLOW = "slow"


class FakeTicker:
    queues, calls = {}, {}

    def __init__(self, ticker):
        self.ticker = ticker

    @property
    def info(self):
        FakeTicker.calls[self.ticker] = FakeTicker.calls.get(self.ticker, 0) + 1
        q = FakeTicker.queues.get(self.ticker) or [TRUNC]
        item = q.pop(0) if len(q) > 1 else q[0]
        if item == SLOW:
            time.sleep(0.4)
            return dict(FULL)
        return dict(item)


def script(ticker, *answers):
    FakeTicker.queues[ticker] = list(answers)
    FakeTicker.calls[ticker] = 0


yfinance.Ticker = FakeTicker
import alpha_model as AM    # noqa: E402
import data_fetcher as DF   # noqa: E402

try:
    import lookup_context as LC
    LC.RETRY_WAITS = (0.01, 0.01)       # the real waits are seconds; the order is what matters
    scan = LC.scan_lookups
except ImportError:
    LC = None
    from contextlib import nullcontext as scan
AM.yf.Ticker = FakeTicker
DF.yf.Ticker = FakeTicker
AM._INFO_TIMEOUT = 0.1


def fresh():
    AM._INFO_CACHE.clear()
    DF._INFO_CACHE.clear()


banner("0. THE SWITCH EXISTS")
check("lookup_context.scan_lookups exists", LC is not None)

banner("1. alpha_model._ticker_info — A TRUNCATED ANSWER IS NOT KEPT FOR A DAY")
fresh()
script("T1.NS", TRUNC, FULL)
AM._ticker_info("T1.NS")
AM._INFO_CACHE["T1.NS"] = (time.time() - 11 * 60, dict(TRUNC))     # eleven minutes later
got = AM._ticker_info("T1.NS")
check("an 11-minute-old truncated answer is asked for again",
      got.get("marketCap") == FULL["marketCap"],
      f"requests={FakeTicker.calls['T1.NS']}, marketCap={got.get('marketCap')}")

fresh()
script("T2.NS", FULL, TRUNC)
AM._ticker_info("T2.NS")
AM._INFO_CACHE["T2.NS"] = (time.time() - 11 * 60, dict(FULL))
got = AM._ticker_info("T2.NS")
check("  ...but a complete answer of the same age is still served from the cache",
      FakeTicker.calls["T2.NS"] == 1 and got.get("marketCap") == FULL["marketCap"],
      f"requests={FakeTicker.calls['T2.NS']}")

banner("2. alpha_model._ticker_info — INSIDE THE SCAN IT ASKS AGAIN")
fresh()
script("S1.NS", TRUNC, TRUNC, FULL)
with scan():
    got = AM._ticker_info("S1.NS")
check("truncated, truncated, full: the scan gets the full answer",
      got.get("marketCap") == FULL["marketCap"],
      f"requests={FakeTicker.calls['S1.NS']}, keys={len(got)}")
check("  ...in exactly three requests", FakeTicker.calls["S1.NS"] == 3,
      f"requests={FakeTicker.calls['S1.NS']}")

fresh()
script("S2.NS", SLOW, FULL)
with scan():
    got = AM._ticker_info("S2.NS")
check("a lookup that times out is tried again inside the scan",
      got.get("marketCap") == FULL["marketCap"], f"keys={len(got)}")

fresh()
script("ETF.NS", TRUNC)
with scan():
    got = AM._ticker_info("ETF.NS")
    first = FakeTicker.calls["ETF.NS"]
    AM._ticker_info("ETF.NS")
check("a stock that never has full data is asked at most three times",
      first == 3 and got == TRUNC, f"requests={first}")
check("  ...and not asked again moments later for the same stock",
      FakeTicker.calls["ETF.NS"] == 3, f"requests={FakeTicker.calls['ETF.NS']}")

banner("3. OUTSIDE THE SCAN, NOBODY WAITS")
fresh()
script("U1.NS", TRUNC, FULL)
got = AM._ticker_info("U1.NS")
check("a page request asks once and answers with what it got",
      FakeTicker.calls["U1.NS"] == 1, f"requests={FakeTicker.calls['U1.NS']}")

fresh()
script("U2.NS", TRUNC, FULL)
with scan():
    pass
AM._ticker_info("U2.NS")
check("leaving the scan turns the retries off again", FakeTicker.calls["U2.NS"] == 1,
      f"requests={FakeTicker.calls['U2.NS']}")

fresh()
script("U3.NS", TRUNC, FULL)
inside, release = threading.Event(), threading.Event()


def scan_worker():
    with scan():
        inside.set()
        release.wait(5)


t = threading.Thread(target=scan_worker)
t.start()
inside.wait(5)
AM._ticker_info("U3.NS")
release.set()
t.join(5)
check("a scan running on another thread does not make a page request retry",
      FakeTicker.calls["U3.NS"] == 1, f"requests={FakeTicker.calls['U3.NS']}")

banner("4. data_fetcher.get_info — THE PEER AND METRICS LOOKUP")
fresh()
script("P1.NS", TRUNC, TRUNC, FULL)
with scan():
    got = DF.get_info("P1.NS")
check("inside the scan: truncated, truncated, full gets the full answer",
      got.get("marketCap") == FULL["marketCap"],
      f"requests={FakeTicker.calls['P1.NS']}, keys={len(got)}")

fresh()
script("P2.NS", TRUNC, FULL)
DF.get_info("P2.NS")
check("outside the scan it asks once", FakeTicker.calls["P2.NS"] == 1,
      f"requests={FakeTicker.calls['P2.NS']}")

fresh()
script("P3.NS", FULL, TRUNC)
DF.get_info("P3.NS")
with scan():
    got = DF.get_info("P3.NS")
check("a complete cached answer is served without asking, even inside the scan",
      FakeTicker.calls["P3.NS"] == 1 and got.get("marketCap") == FULL["marketCap"],
      f"requests={FakeTicker.calls['P3.NS']}")

banner("5. THE SCAN USES IT")
import inspect  # noqa: E402
import universe_scan as U  # noqa: E402
src = inspect.getsource(U)
check("the scan scores each stock inside scan_lookups()", "with scan_lookups():" in src,
      "the retries only help if the scan turns them on")

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
