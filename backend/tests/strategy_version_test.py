"""
strategy_version_test.py — the freeze has to actually cover what it claims.

v1.0 was frozen on 2026-08-25 with the string "ImportError" where its backtest
parameters should have been. current_spec asked momentum_backtest for
ARCHIVE_STARTS, which lives in bhavcopy, and the failed tuple import took
min_holdings, both universe sizes, the rebalance frequency and the momentum
definition down with it. The hash covered none of them for a week, and the
drift check reported no change the whole time.

So these tests check the two things that failure needed:

  1. Every field the spec claims to record is actually readable.
  2. A specification that could not be fully read is REFUSED, not stored.

The second matters more. A missing field is a bug; a missing field inside
something called a frozen specification is a bug wearing a guarantee.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import strategy_version as sv  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


print("\n1. Every advertised field is readable from the live configuration")
spec = sv.current_spec()
fails = spec.get("_capture_failures") or {}
ok(not fails, f"no capture failures (got {fails})")
ok("backtest_error" not in spec,
   "no swallowed error marker standing in for a block")

for block, fields in (
        ("backtest", ("min_holdings", "archive_starts", "default_universe_size",
                      "broad_universe_size", "rebalance", "momentum_definition")),
        ("pit_backtest", ("cost_roundtrip_pct", "lookback_months", "skip_months",
                          "min_holdings", "min_monthly_turnover")),
):
    got = spec.get(block) or {}
    for f in fields:
        ok(f in got, f"{block}.{f} is captured")

print("\n2. The captured values match the modules they came from")
import momentum_backtest as mb  # noqa: E402
import pit_backtest as pb  # noqa: E402
import bhavcopy as bc  # noqa: E402

ok(spec["backtest"]["min_holdings"] == mb.MIN_HOLDINGS,
   "min_holdings matches momentum_backtest")
ok(spec["backtest"]["archive_starts"] == bc.ARCHIVE_STARTS,
   "archive_starts matches bhavcopy (the module it actually lives in)")
ok(spec["pit_backtest"]["cost_roundtrip_pct"] == pb.COST_ROUNDTRIP_PCT,
   "cost assumption matches pit_backtest")
ok(spec["pit_backtest"]["min_monthly_turnover"] == pb.MIN_MONTHLY_TURNOVER,
   "liquidity floor matches pit_backtest")

print("\n3. A change to a behavioural constant must change the hash")
# The whole purpose of the hash. Before the fix, altering MIN_HOLDINGS moved
# nothing, because the field was not in the spec at all.
h_before = sv._hash(spec)
tampered = {k: v for k, v in spec.items()}
tampered["backtest"] = dict(tampered["backtest"])
tampered["backtest"]["min_holdings"] = 3
ok(sv._hash(tampered) != h_before,
   "changing min_holdings from 5 to 3 changes the hash")

tampered2 = {k: v for k, v in spec.items()}
tampered2["pit_backtest"] = dict(tampered2["pit_backtest"])
tampered2["pit_backtest"]["cost_roundtrip_pct"] = 0.1
ok(sv._hash(tampered2) != h_before,
   "changing the cost assumption changes the hash")

print("\n4. An incomplete specification is refused, not stored")
holed = {k: v for k, v in spec.items()}
holed["_capture_failures"] = {"min_holdings": "ImportError: nope"}
res = sv.freeze("test-should-not-exist", spec=holed)
ok(res.get("frozen") is False, "freeze refuses a spec with capture failures")
ok("min_holdings" in str(res.get("capture_failures")),
   "the refusal names the field it could not read")
ok("allow_incomplete" in res.get("reason", ""),
   "the refusal explains how to override it deliberately")

print("\n5. Field classification")
ok("factors_not_historically_testable" in sv.METADATA_FIELDS,
   "the testability list is metadata")
for f in ("factor_weights", "costs", "backtest", "pit_backtest",
          "validation_thresholds"):
    ok(f not in sv.METADATA_FIELDS, f"{f} is behavioural")
b, m = sv._classify({"anything_new"})
ok(b == ["anything_new"],
   "an unrecognised field defaults to behavioural, which is the safe direction")

print("\n" + "=" * 64)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
