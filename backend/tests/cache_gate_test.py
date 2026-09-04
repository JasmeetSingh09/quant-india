"""
cache_gate_test.py — the cache must not pin a payload blind to its own callers.

The old gate admitted a payload if ANY ONE of six fields was present, and none
of those six is read by Piotroski, value, liquidity or alpha_v2. Measured over
314 NSE names: 99% of payloads passed, and 87% of those carried two or fewer of
the eight fields Piotroski consumes. Such a payload was cached as good and
served for six hours.

The tests below encode the measurements the new gate was designed from, so a
later edit that quietly breaks the trade-off fails here rather than in
production six hours at a time.

The honest limit is asserted too: this gate does NOT make Piotroski stable, and
a test that claimed otherwise would be the same overclaiming this project keeps
finding in its own output.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import data_fetcher as DF  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


PIO = ("returnOnAssets", "operatingCashflow", "currentRatio", "longTermDebt",
       "grossMargins", "revenueGrowth", "totalAssets", "totalStockholderEquity")
NEVER = ("longTermDebt", "totalAssets", "totalStockholderEquity")


def payload(**over):
    """A healthy NSE payload: every sentinel present, plus filler keys."""
    base = {f"k{i}": i for i in range(60)}
    base.update({
        "totalRevenue": 4.2e11, "profitMargins": 0.18, "totalDebt": 9.0e10,
        "totalCash": 3.1e10, "grossMargins": 0.31, "revenueGrowth": 0.09,
        "marketCap": 7.4e11, "bookValue": 412.0,
        "ebitda": 1.1e11, "returnOnEquity": 0.152, "trailingPE": 18.4,
    })
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


print("\n1. A healthy payload is cached")
ok(DF._info_looks_complete(payload()), "all eight sentinels present -> admitted")
ok(DF._info_looks_complete(payload(returnOnEquity=None, ebitda=None)),
   "still admitted without returnOnEquity and ebitda "
   "(14.3% and 81.8% available — not sentinels)")
ok(DF._info_looks_complete(payload(**{f: None for f in NEVER})),
   "still admitted with longTermDebt/totalAssets/totalStockholderEquity absent "
   "— Yahoo returned those for 0 of 314 NSE names")

print("\n2. The failure this was written for")
blind = payload(**{f: None for f in PIO})
ok(len(blind) >= 20, f"the payload is not obviously short ({len(blind)} keys)")
ok(not DF._info_looks_complete(blind),
   "a payload carrying NONE of Piotroski's eight inputs is refused")
old_gate = ("totalRevenue", "ebitda", "returnOnEquity", "profitMargins",
            "totalDebt", "totalCash")
ok(any(blind.get(k) is not None for k in old_gate),
   "...and the OLD rule would have admitted it and pinned it for 6 hours")

print("\n3. Losing the financial block is refused")
fin = payload(totalRevenue=None, profitMargins=None, totalDebt=None,
              totalCash=None, grossMargins=None, revenueGrowth=None)
ok(not DF._info_looks_complete(fin), "six sentinels gone -> refused")

print("\n4. The threshold matches what was measured")
ok(DF._INFO_MIN_SENTINELS == 7,
   f"threshold is 7 of 8 ({DF._INFO_MIN_SENTINELS}) — 93.3% of healthy "
   f"payloads carry 8, 96.5% carry >=7")
ok(len(DF._INFO_SENTINELS) == 8, f"eight sentinels ({len(DF._INFO_SENTINELS)})")
one_short = payload(bookValue=None)
ok(DF._info_looks_complete(one_short),
   "losing ONE sentinel still caches — 3.2% of healthy payloads sit at 7/8")
two_short = payload(bookValue=None, totalCash=None)
ok(not DF._info_looks_complete(two_short), "losing two does not")

print("\n5. Every sentinel is read by a real consumer, and none is a dead field")
for f in NEVER:
    ok(f not in DF._INFO_SENTINELS,
       f"{f} is NOT a sentinel — requiring it would disable caching entirely")
ok("grossMargins" in DF._INFO_SENTINELS and "revenueGrowth" in DF._INFO_SENTINELS,
   "the two reliably-available Piotroski inputs ARE sentinels — the gate can "
   "now see the caller it was blind to")
covered = set(DF._INFO_SENTINELS) & set(PIO)
ok(len(covered) == 2, f"Piotroski coverage rose from 0/8 to {len(covered)}/8")

print("\n6. Degenerate input")
ok(not DF._info_looks_complete({}), "empty payload refused")
ok(not DF._info_looks_complete(None), "None refused")
ok(not DF._info_looks_complete({"totalRevenue": 1}), "a 1-key payload refused")

print("\n7. The limit, stated as a test so it cannot be forgotten")
# returnOnAssets is absent from 87% of HEALTHY payloads. A gate cannot
# distinguish that from a throttled loss, so the SBIN 3->1 shape still passes.
sbin_shape = payload(returnOnAssets=None)
ok(DF._info_looks_complete(sbin_shape),
   "a payload missing returnOnAssets is still cached — the gate CANNOT fix "
   "the Piotroski instability, and does not claim to")
ok("returnOnAssets" not in DF._INFO_SENTINELS,
   "because at 12.7% availability it signals nothing about payload health")

print("\n8. Nothing about the model moved")
import alpha_model  # noqa: E402
ok(alpha_model.FACTOR_WEIGHTS == {"sentiment": 0.25, "momentum": 0.35,
                                  "quality": 0.25, "value": 0.15},
   "V1.4 factor weights unchanged")
ok(DF._INFO_TTL == 6 * 3600, "cache TTL unchanged")
ok(DF._INFO_FIN_FIELDS is DF._INFO_SENTINELS,
   "the old constant name still resolves, so nothing referencing it breaks")

print("\n" + "=" * 70)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
