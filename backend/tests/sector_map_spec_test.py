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
base = SV._hash(spec)

original = copy.deepcopy(DF.NSE_SECTORS)
try:
    print("\n2. ANY EDIT MOVES THE HASH")
    DF.NSE_SECTORS["Steel_Metal"] = [t for t in original["Steel_Metal"] if t != "KALYANKJIL.NS"]
    ok(SV._hash(SV.current_spec()) != base, "removing one member changes the hash")
    DF.NSE_SECTORS.clear(); DF.NSE_SECTORS.update(copy.deepcopy(original))
    DF.NSE_SECTORS["Infra"] = list(reversed(original["Infra"]))
    ok(SV._hash(SV.current_spec()) != base, "reordering a sector's members changes the hash")
    DF.NSE_SECTORS.clear()
    for k in reversed(list(original)):
        DF.NSE_SECTORS[k] = list(original[k])
    ok(SV._hash(SV.current_spec()) != base, "reordering the sectors (first match wins) changes the hash")
finally:
    DF.NSE_SECTORS.clear(); DF.NSE_SECTORS.update(original)

print("\n3. RESTORED, THE HASH RETURNS")
ok(SV._hash(SV.current_spec()) == base, "the unchanged map gives the same hash")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
