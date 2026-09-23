"""
bse_collection_pause_test.py: while paused, nothing contacts BSE.

BSE's terms forbid automated collection without its written consent. Until
2026-09-23 stock_universe.refresh_bse_stocks reached bseindia.com and
api.bseindia.com at every server start. The tripwire sits under every requests
call, Session or not. No network.
"""

import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL = [], []


def check(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}  {detail if not cond else ''}")


os.environ["QUANT_DATA_DIR"] = tempfile.mkdtemp()      # empty store: always stale
os.environ.pop("BSE_COLLECTION", None)

import requests  # noqa: E402
import bse_access  # noqa: E402
import stock_universe  # noqa: E402

importlib.reload(stock_universe)

calls = []
real_request, real_get = requests.Session.request, requests.get


def _tripwire(self, method, url, *a, **k):
    calls.append(str(url))
    raise requests.ConnectionError("offline test: nothing is fetched")


def _get_tripwire(url, *a, **k):
    calls.append(str(url))
    raise requests.ConnectionError("offline test: nothing is fetched")


requests.Session.request = _tripwire
requests.get = _get_tripwire
try:
    print("\n1. The switch defaults to paused, and only an explicit 'on' resumes")
    check("unset means paused", bse_access.collection_paused() is True)
    for v in ("off", "paused", "no", "", "typo", "0"):
        os.environ["BSE_COLLECTION"] = v
        check(f"BSE_COLLECTION={v!r} is paused", bse_access.collection_paused() is True)
    os.environ["BSE_COLLECTION"] = "on"
    check("BSE_COLLECTION='on' resumes", bse_access.collection_paused() is False)
    os.environ.pop("BSE_COLLECTION")

    print("\n2. Refreshing the BSE list contacts nothing while paused")
    for force in (False, True):
        calls.clear()
        r = stock_universe.refresh_bse_stocks(force=force)
        label = "forced, as /stock/universe/refresh does" if force else "stale list, as at startup"
        check(f"refresh_bse_stocks reports paused ({label})",
              r.get("paused") is True and r.get("status") == "paused", f"{r}")
        check(f"  ...and made no request at all ({label})", not calls, f"{calls[:3]}")
    check("the built-in list still serves BSE search (count > 0)",
          (r.get("count") or 0) > 0, f"{r.get('count')}")
    check("the response says why", "written consent" in (r.get("reason") or ""))

    print("\n3. The tripwire can catch a real attempt (the test is not vacuous)")
    os.environ["BSE_COLLECTION"] = "on"
    calls.clear()
    stock_universe.refresh_bse_stocks(force=True)
    check("with collection on, BSE is contacted and the tripwire sees it",
          any("bseindia.com" in u for u in calls), f"{calls[:2]}")
    os.environ.pop("BSE_COLLECTION")
finally:
    requests.Session.request, requests.get = real_request, real_get

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
