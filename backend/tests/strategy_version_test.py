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

print("\n3b. The hash is stable against environment churn")
# The environment block records the archive's row count, which grows every
# trading day. If that were hashed, the hash of a frozen version would change
# every evening — and a specification whose hash changes daily is not frozen.
import copy  # noqa: E402
env_churn = copy.deepcopy(spec)
if env_churn.get("environment", {}).get("archive"):
    env_churn["environment"]["archive"]["rows"] += 2400
    env_churn["environment"]["archive"]["last_day"] = "2099-01-01"
env_churn.setdefault("environment", {})["numpy_version"] = "99.0.0"
ok(sv._hash(env_churn) == h_before,
   "a grown archive and a numpy upgrade do not move the hash")

no_env = {k: v for k, v in spec.items() if k != "environment"}
ok(sv._hash(no_env) == h_before,
   "a spec with no environment key hashes the same, so v1.0-v1.3 are unaffected")

both = copy.deepcopy(env_churn)
both["signal_thresholds"] = dict(both["signal_thresholds"])
both["signal_thresholds"]["signal_strong_buy"] = 25
ok(sv._hash(both) != h_before,
   "but a Strong Buy threshold change still moves it, environment churn or not")

print("\n4. An incomplete specification is refused, not stored")
holed = {k: v for k, v in spec.items()}
holed["_capture_failures"] = {"min_holdings": "ImportError: nope"}
res = sv.freeze("test-should-not-exist", spec=holed)
ok(res.get("frozen") is False, "freeze refuses a spec with capture failures")
ok("min_holdings" in str(res.get("capture_failures")),
   "the refusal names the field it could not read")
ok("allow_incomplete" in res.get("reason", ""),
   "the refusal explains how to override it deliberately")

print("\n4b. Commit provenance, in all three environments")
# The gap this closes: git answers on a laptop and not in the container, so the
# audit passed locally while the production record carried a null commit —
# exactly where provenance matters.
g = sv._code_commit(run=lambda: "abc1234", environ={})
ok(g["code_commit"] == "abc1234" and g["code_commit_source"] == "git",
   "git available -> commit captured from git")
ok(g["provenance_warning"] is None, "and no warning is raised")


def _no_git():
    raise FileNotFoundError("git not installed")


d = sv._code_commit(run=_no_git,
                    environ={"RENDER_GIT_COMMIT": "deadbeefcafe1234"})
ok(d["code_commit"] == "deadbee",
   f"git unavailable + RENDER_GIT_COMMIT -> deployment commit ({d['code_commit']})")
ok(d["code_commit_source"] == "RENDER_GIT_COMMIT",
   "and the record says where it came from")
ok(d["provenance_warning"] is None, "and no warning is raised")

n = sv._code_commit(run=_no_git, environ={})
ok(n["code_commit"] is None, "neither available -> commit is explicitly null")
ok("PROVENANCE GAP" in (n["provenance_warning"] or ""),
   "and a documented warning travels with the null")

# An empty variable is not an answer.
e = sv._code_commit(run=_no_git, environ={"RENDER_GIT_COMMIT": "   "})
ok(e["code_commit"] is None, "a blank deployment variable is not treated as a commit")

# Order matters: git wins when both are present, because it describes the
# working tree that actually ran rather than what was built.
b = sv._code_commit(run=lambda: "local99", environ={"RENDER_GIT_COMMIT": "remote11"})
ok(b["code_commit"] == "local99", "git takes precedence over the deployment variable")

# And none of it may touch the hash.
h_env = sv._hash(spec)
for variant in ({"code_commit": "aaaaaaa", "code_commit_source": "git",
                 "provenance_warning": None},
                {"code_commit": None, "code_commit_source": None,
                 "provenance_warning": sv.NO_COMMIT_WARNING}):
    s2 = copy.deepcopy(spec)
    s2.setdefault("environment", {}).update(variant)
    ok(sv._hash(s2) == h_env,
       f"commit provenance ({variant['code_commit_source'] or 'absent'}) "
       f"does not move the hash")

print("\n5. Field classification")
ok("factors_not_historically_testable" in sv.METADATA_FIELDS,
   "the testability list is metadata")
for f in ("factor_weights", "costs", "backtest", "pit_backtest",
          "validation_thresholds"):
    ok(f not in sv.METADATA_FIELDS, f"{f} is behavioural")
b, m, e = sv._classify({"anything_new"})
ok(b == ["anything_new"],
   "an unrecognised field defaults to behavioural, which is the safe direction")
ok(m == [] and e == [], "and is claimed by neither metadata nor environment")

# Environment is its own category: a numpy upgrade is not a model change, and
# reporting it as one would retire every prior result on a dependency bump.
b2, m2, e2 = sv._classify({"environment"})
ok(e2 == ["environment"] and b2 == [],
   "environment is classified as environment, not as behaviour")
ok(sv._kind_of("environment") == "environment", "_kind_of agrees")
ok(sv._kind_of("factor_weights") == "behavioural", "_kind_of on a weight")
ok(sv._kind_of("factors_not_historically_testable") == "metadata",
   "_kind_of on metadata")

print("\n" + "=" * 64)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
