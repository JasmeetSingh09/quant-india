"""
sector_map_spec_test.py — the sector map behind valuation peers is part of the frozen spec.

Audit D-01 (2026-10-14): data_fetcher.NSE_SECTORS decides every value
factor's peers, but strategy_version.current_spec() never captured it, so a
peer-map edit changed scores without moving the spec hash. This checks the
capture exists, matches the module, and that any edit, including a reorder
(first match wins), moves the hash. The map itself is not changed here.
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("QUANT_DATA_DIR", os.environ.get("TEMP", "/tmp"))
os.environ.pop("DATABASE_URL", None)

import data_fetcher as DF       # noqa: E402
import strategy_version as SV   # noqa: E402

PASS, FAIL = [], []


# The spec hash includes captured_at, stamped to the minute, so two captures a
# minute boundary apart hash differently with nothing changed (this suite failed
# that way once, 2026-10-15). Every comparison here fixes it, so only the map counts.
def _h(spec):
    return SV._hash({**spec, "captured_at": "fixed for comparison"})


def ok(cond, label, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))


print("\n1. THE MAP IS CAPTURED")
spec = SV.current_spec()
sm = spec.get("sector_map") or {}
ok("sector_map" in spec, "the spec has a sector_map field",
   (spec.get("_capture_failures") or {}).get("sector_map", ""))
ok(sm.get("sector_order") == list(DF.NSE_SECTORS), "sector order matches the module")
ok(sm.get("members") == {k: list(v) for k, v in DF.NSE_SECTORS.items()},
   "every sector's members match the module, in order")
ok(sm.get("peer_fetch_limit") == DF.SECTOR_PEER_FETCH_LIMIT == 5, "peers fetched per stock (5) is captured")
import alpha_model as AM  # noqa: E402
ok(sm.get("value_peers_used") == AM.VALUE_PEERS_USED == 3, "peers compared in value (3) is captured")
ok(sm.get("yahoo_sector_fallback") == DF.YAHOO_SECTOR_FALLBACK and len(DF.YAHOO_SECTOR_FALLBACK) == 11,
   "the Yahoo-sector fallback table is captured (11 entries)")
base = _h(spec)

original = copy.deepcopy(DF.NSE_SECTORS)
try:
    print("\n2. ANY EDIT MOVES THE HASH")
    DF.NSE_SECTORS["Steel_Metal"] = [t for t in original["Steel_Metal"] if t != "KALYANKJIL.NS"]
    ok(_h(SV.current_spec()) != base, "removing one member changes the hash")
    DF.NSE_SECTORS.clear(); DF.NSE_SECTORS.update(copy.deepcopy(original))
    DF.NSE_SECTORS["Infra"] = list(reversed(original["Infra"]))
    ok(_h(SV.current_spec()) != base, "reordering a sector's members changes the hash")
    DF.NSE_SECTORS.clear()
    for k in reversed(list(original)):
        DF.NSE_SECTORS[k] = list(original[k])
    ok(_h(SV.current_spec()) != base, "reordering the sectors (first match wins) changes the hash")
    DF.NSE_SECTORS.clear(); DF.NSE_SECTORS.update(copy.deepcopy(original))
    DF.SECTOR_PEER_FETCH_LIMIT = 4
    ok(_h(SV.current_spec()) != base, "changing the peer fetch limit changes the hash")
    DF.SECTOR_PEER_FETCH_LIMIT = 5
    AM.VALUE_PEERS_USED = 2
    ok(_h(SV.current_spec()) != base, "changing the peers compared changes the hash")
    AM.VALUE_PEERS_USED = 3
    DF.YAHOO_SECTOR_FALLBACK["Financial Services"] = "NBFC"
    ok(_h(SV.current_spec()) != base, "changing one fallback entry changes the hash")
    DF.YAHOO_SECTOR_FALLBACK["Financial Services"] = "Banking"
finally:
    DF.NSE_SECTORS.clear(); DF.NSE_SECTORS.update(original)
    DF.SECTOR_PEER_FETCH_LIMIT, AM.VALUE_PEERS_USED = 5, 3
    DF.YAHOO_SECTOR_FALLBACK["Financial Services"] = "Banking"

print("\n2b. THE PROMOTION CHANGED NO PEER SET")
ok(DF.get_sector_peers("KALYANKJIL.NS") == ["TATASTEEL.NS", "JSWSTEEL.NS", "SAIL.NS", "HINDALCO.NS", "VEDL.NS"],
   "a mapped stock still gets the first five other members, in order")
_gi = DF.get_info
DF.get_info = lambda t: {"sector": "Financial Services"}
ok(DF.get_sector_peers("NOTMAPPED.NS") == ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"],
   "an unmapped 'Financial Services' stock still falls back to the first five banks")
DF.get_info = _gi

print("\n3. RESTORED, THE HASH RETURNS")
ok(_h(SV.current_spec()) == base, "the unchanged map gives the same hash")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
