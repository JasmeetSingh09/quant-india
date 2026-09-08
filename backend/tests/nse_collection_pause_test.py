"""
nse_collection_pause_test.py — a commitment made in writing must be enforced by code.

On 2026-09-08 a permission request went to NSE Data and Analytics stating, in
writing, that this project had paused collection pending their response. The
scheduler did not know that. A nightly cron, a six-hourly repair pass and a
fifteen-minute resume walk were all still pulling from nseindia.com, which made
the sentence false the moment it was sent.

So the switch is tested the way the sentence is load-bearing:

    the DEFAULT must be paused    — a deployment that configures nothing must
                                    honour the commitment, not break it;
    every entry point must stop   — one unguarded path is the whole promise;
    stored data must still serve  — the request was about collection, and
                                    degrading the product would not make the
                                    email any more true.

The default is the important one. Getting it wrong in the safe direction costs a
stale archive. Getting it wrong in the other direction means telling an exchange
you have stopped while your scheduler carries on.
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def reload_with(value):
    if value is None:
        os.environ.pop("NSE_COLLECTION", None)
    else:
        os.environ["NSE_COLLECTION"] = value
    import nse_access
    importlib.reload(nse_access)
    return nse_access


print("=" * 72)
print("THE DEFAULT IS PAUSED")
print("=" * 72)

na = reload_with(None)
check("unset means paused", na.collection_paused() is True)
check("the reason is carried, not just a boolean",
      "NSE Data" in na.REASON and "2026-09-08" in na.REASON)
check("status reports it", na.status()["nse_collection_paused"] is True)
check("status says stored data is still served",
      na.status()["stored_data_still_served"] is True)

for v in ("", "off", "paused", "0", "no", "false", "stop"):
    check(f"{v!r} means paused", reload_with(v).collection_paused() is True)

check("a typo means paused, not resumed",
      reload_with("onn").collection_paused() is True,
      "an unrecognised value must never silently resume collection")
check("and a typo is flagged as unrecognised",
      reload_with("onn").status()["recognised"] is False)

for v in ("on", "1", "yes", "true", "enabled", "ON", " on "):
    check(f"{v!r} enables collection", reload_with(v).collection_paused() is False)

print()
print("=" * 72)
print("EVERY COLLECTION ENTRY POINT STOPS")
print("=" * 72)

reload_with(None)
import nse_access  # noqa: E402
import bhavcopy  # noqa: E402
import corporate_actions  # noqa: E402

importlib.reload(bhavcopy)
importlib.reload(corporate_actions)

calls = []
import requests  # noqa: E402

real_get = requests.get


def _tripwire(*a, **k):
    calls.append(a[0] if a else k.get("url"))
    raise AssertionError("network call made while collection is paused")


requests.get = _tripwire
try:
    from datetime import datetime
    r1 = bhavcopy.fetch_day(datetime(2015, 6, 10))
    check("fetch_day is paused", r1.get("paused") is True and r1.get("stored") == 0, f"{r1}")
    r2 = bhavcopy.backfill_range("2015-01-01", "2015-02-01")
    check("backfill_range is paused", r2.get("paused") is True, f"{str(r2)[:80]}")
    r3 = bhavcopy.backfill(days=5)
    check("backfill is paused", r3.get("paused") is True)
    r4 = bhavcopy.backfill_recent(10)
    check("backfill_recent is paused", r4.get("paused") is True)
    r5 = bhavcopy.resume_if_incomplete()
    check("resume_if_incomplete is paused", r5.get("paused") is True)
    r6 = corporate_actions.fetch_month(2015, 6)
    check("corporate action fetch_month is paused", r6 == [], f"{r6}")
    check("NO network call was made by any of them", not calls, f"{calls[:2]}")
finally:
    requests.get = real_get

print()
print("=" * 72)
print("STORED DATA IS STILL SERVED")
print("=" * 72)

import inspect  # noqa: E402

for fn, label in ((bhavcopy.coverage, "coverage"),
                  (bhavcopy.closes_history, "closes_history"),
                  (bhavcopy.missing_days, "missing_days"),
                  (bhavcopy.recent_gaps, "recent_gaps")):
    src = inspect.getsource(fn)
    check(f"{label} is NOT gated by the pause",
          "collection_paused()" not in src,
          "reading the archive is not collection")

print()
print("=" * 72)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
