"""
strategy_version.py — write the strategy down before the data arrives.

The clean point-in-time backtest is worth something only if the strategy it
tests was specified before the clean data existed. Otherwise the result is not
out-of-sample in any meaningful sense: weights chosen after seeing what the
period rewards are fitted to that period, whether or not anyone intended it.

So this records a complete, hashed specification — factors, weights, universe
rules, rebalance frequency, costs, constraints, optimiser — with a timestamp,
and refuses to overwrite an existing version. Changing anything means minting
v1.1, which leaves v1.0 sitting there to be compared against.

The hash matters more than it looks. A frozen spec that can be edited is not
frozen; it is a document with a date on it. Hashing the parameters means a
later run can prove it used the same ones rather than asserting it.

Nothing here evaluates a strategy. It only records what one was.
"""

import hashlib
import json
import os
from datetime import datetime

try:
    from db import get_conn, IS_POSTGRES
except Exception:                                   # pragma: no cover
    from .db import get_conn, IS_POSTGRES

_READY = False

# Which parts of a specification decide what the strategy DOES, and which only
# record what we understood about it.
#
# The distinction earns its keep the first time a version increments for a
# reason that is not a model change. A corrected note about which factors can
# be tested historically moves no weight and changes no threshold, but it does
# change the hash — and without this split, the drift report says "any result
# produced now cannot be attributed to this version", which for a metadata
# correction is false and would retire a perfectly good backtest.
#
# Everything not listed as metadata is treated as behavioural. That default is
# deliberate: a new field added later is assumed to matter until someone says
# otherwise, which is the safe direction for a check whose whole job is to
# refuse to let a change pass unnoticed.
METADATA_FIELDS = {
    "factors_not_historically_testable",
    "factors_not_backtestable_as_strategies",
    "captured_at",
}

# The stack and the data a run happened on. It affects whether a number can be
# REPRODUCED, but it is not the strategy: upgrading numpy is not a model
# change, and reporting it as one would retire every prior result on a routine
# dependency bump. Kept separate so both facts stay sayable.
ENVIRONMENT_FIELDS = {"environment"}


def _classify(fields):
    """Split changed field names into behavioural, metadata and environment."""
    behavioural = sorted(f for f in fields
                         if f not in METADATA_FIELDS
                         and f not in ENVIRONMENT_FIELDS)
    metadata = sorted(f for f in fields if f in METADATA_FIELDS)
    environment = sorted(f for f in fields if f in ENVIRONMENT_FIELDS)
    return behavioural, metadata, environment


def _kind_of(field):
    if field in METADATA_FIELDS:
        return "metadata"
    if field in ENVIRONMENT_FIELDS:
        return "environment"
    return "behavioural"


def _init():
    global _READY
    if _READY:
        return
    conn = get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_versions (
                version     TEXT PRIMARY KEY,
                frozen_at   TEXT NOT NULL,
                spec_json   TEXT NOT NULL,
                spec_hash   TEXT NOT NULL,
                notes       TEXT
            )
        """)
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

    # Retraction columns, each on its own connection: on Postgres a failed
    # statement aborts the whole transaction, so a second ALTER in the same
    # one would fail for the wrong reason.
    for col in ("retracted_at TEXT", "retracted_reason TEXT"):
        c = get_conn()
        try:
            c.execute(f"ALTER TABLE strategy_versions ADD COLUMN {col}")
            c.commit()
        except Exception:
            try:
                c.rollback()
            except Exception:
                pass
        finally:
            c.close()
    _READY = True


def _strategy_only(spec: dict) -> dict:
    """
    The spec minus the environment it happened to run in.

    The hash answers "is this the same strategy". The environment block answers
    "could this run be reproduced", and it includes the archive's row count,
    which grows every trading day. Hashing it would mean the hash of a frozen
    version changed every evening — and a specification whose hash changes
    daily is not frozen, it is a timestamp with extra steps.

    So the environment is RECORDED with the version and compared by drift, but
    it is not part of the identity of the strategy. Versions frozen before this
    block existed are unaffected: removing a key they never had cannot change
    their hash, so v1.0 through v1.3 keep the hashes they were minted with.
    """
    return {k: v for k, v in (spec or {}).items()
            if k not in ENVIRONMENT_FIELDS}


def _hash(spec: dict) -> str:
    """Stable hash of the STRATEGY. sort_keys so a reordered dict is the same
    strategy, which it is."""
    blob = json.dumps(_strategy_only(spec), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def current_spec() -> dict:
    """
    Read the live configuration out of the modules that define it, rather than
    restating it here. A spec typed by hand drifts from the code it claims to
    describe, and the drift is invisible until someone checks.
    """
    spec = {"captured_at": datetime.now().strftime("%Y-%m-%d %H:%M")}

    try:
        from alpha_v2 import WEIGHTS_V2, MODEL_VERSION_V2
        spec["model"] = "six-factor"
        spec["model_version"] = MODEL_VERSION_V2
        spec["factor_weights"] = {k: round(v, 6) for k, v in sorted(WEIGHTS_V2.items())}
    except Exception as e:
        spec["model_error"] = type(e).__name__

    try:
        from alpha_model import FACTOR_WEIGHTS
        spec["v1_factor_weights"] = {k: round(v, 6)
                                     for k, v in sorted(FACTOR_WEIGHTS.items())}
    except Exception:
        pass

    # Captured field by field. This block used to be one tuple import, and it
    # named ARCHIVE_STARTS — which lives in bhavcopy, not momentum_backtest. The
    # ImportError took the other three constants down with it and the whole
    # block was replaced by the string "ImportError", so v1.0 was frozen on
    # 2026-08-25 without min_holdings, without the universe sizes, without the
    # rebalance frequency and without the momentum definition. The hash covered
    # none of them. MIN_HOLDINGS could have gone from 5 to 3 and the drift check
    # would have reported no change.
    #
    # One failure must not be able to empty a block again, so each field is
    # captured on its own and anything that fails is recorded by name.
    def _cap(target, key, fn):
        try:
            target[key] = fn()
        except Exception as e:
            spec.setdefault("_capture_failures", {})[key] = \
                f"{type(e).__name__}: {e}"

    bt = {}
    _cap(bt, "min_holdings",
         lambda: __import__("momentum_backtest").MIN_HOLDINGS)
    _cap(bt, "default_universe_size",
         lambda: len(__import__("momentum_backtest").DEFAULT_UNIVERSE))
    _cap(bt, "broad_universe_size",
         lambda: len(__import__("momentum_backtest").BROAD_UNIVERSE))
    _cap(bt, "archive_starts",
         lambda: __import__("bhavcopy").ARCHIVE_STARTS)
    bt["rebalance"] = "monthly"
    bt["momentum_definition"] = ("12-1 (12-month lookback, most recent month "
                                 "skipped)")
    spec["backtest"] = bt

    # The point-in-time backtest is the one that produced the headline result,
    # so its parameters belong in the frozen record too. Freezing a strategy
    # while leaving out the cost assumption and the liquidity floor of the test
    # that evaluates it is most of the way to not freezing it at all.
    pit = {}
    _cap(pit, "cost_roundtrip_pct",
         lambda: __import__("pit_backtest").COST_ROUNDTRIP_PCT)
    _cap(pit, "lookback_months",
         lambda: __import__("pit_backtest").LOOKBACK_MONTHS)
    _cap(pit, "skip_months",
         lambda: __import__("pit_backtest").SKIP_MONTHS)
    _cap(pit, "min_holdings",
         lambda: __import__("pit_backtest").MIN_HOLDINGS)
    _cap(pit, "min_monthly_turnover",
         lambda: __import__("pit_backtest").MIN_MONTHLY_TURNOVER)
    spec["pit_backtest"] = pit

    # Factor internals. These were inline literals until the provenance audit
    # found them: a number with no name cannot be imported, so no specification
    # could capture it and no drift check could see it move. The signal
    # thresholds are the sharpest case — they decide every Strong Buy and
    # Strong Sell the platform displays, and 40 could have become 25 without
    # changing a single hash.
    def _block(target, mod, names):
        for n in names:
            _cap(target, n.lower(), lambda m=mod, k=n: getattr(__import__(m), k))

    sig = {}
    _block(sig, "alpha_model", ["SIGNAL_STRONG_BUY", "SIGNAL_BUY",
                                "SIGNAL_SELL", "SIGNAL_STRONG_SELL"])
    spec["signal_thresholds"] = sig

    mom = {}
    _block(mom, "alpha_model",
           ["MOMENTUM_LOOKBACK_DAYS", "MOMENTUM_SKIP_DAYS",
            "MOMENTUM_TANH_DIVISOR", "MOMENTUM_HISTORY_BUFFER_DAYS",
            "MOMENTUM_MIN_OBSERVATIONS", "MOMENTUM_MIN_RETURNS",
            "MOMENTUM_VOL_EPSILON", "MOMENTUM_CONFIDENCE_BASE",
            "MOMENTUM_CONFIDENCE_SPAN", "SENTIMENT_HALF_LIFE_DAYS",
            "MOMENTUM_INTERP_STRONG", "MOMENTUM_INTERP_MILD"])
    _cap(mom, "top_picks_universe_size",
         lambda: len(__import__("alpha_model").TOP_PICKS_UNIVERSE))
    spec["momentum_factor"] = mom

    v2f = {}
    _block(v2f, "alpha_v2",
           ["GROWTH_REVENUE_DIVISOR", "GROWTH_EARNINGS_DIVISOR",
            "GROWTH_PART_WEIGHT", "GROWTH_CONFIDENCE_SCALE",
            "LOW_RISK_WINDOW_DAYS", "LOW_RISK_MIN_RETURNS",
            "LOW_RISK_VOL_REF", "LOW_RISK_DD_REF", "LOW_RISK_VOL_WEIGHT",
            "LOW_RISK_DD_WEIGHT", "LOW_RISK_CONFIDENCE_BASE",
            "LOW_RISK_CONFIDENCE_DIVISOR"])
    spec["v2_factors"] = v2f

    shared = {}
    _block(shared, "model_config",
           ["RISK_FREE_RATE", "TRADING_DAYS_PER_YEAR", "MONTHS_PER_YEAR",
            "COST_BROKERAGE_PCT", "COST_STT_PCT", "COST_STAMP_DUTY_PCT",
            "COST_EXCHANGE_PCT", "COST_GST_PCT", "BENCHMARK_INDEX"])
    spec["shared_config"] = shared

    # Research tooling. Its parameters change reported research numbers, so
    # they are frozen alongside the model's own.
    res = {}
    _cap(res, "stability_trials",
         lambda: __import__("optimizer_stability").DEFAULT_TRIALS)
    _cap(res, "euler_gamma", lambda: __import__("overfitting").EULER_GAMMA)
    _cap(res, "fama_french_universe_size",
         lambda: len(__import__("fama_french").DEFAULT_UNIVERSE))
    spec["research_tools"] = res

    val = {}
    _block(val, "pit_validation",
           ["MOM_LOOKBACK", "MOM_SKIP", "MOM_TANH_DIV", "LR_WINDOW",
            "LR_VOL_REF", "LR_DD_REF", "LR_VOL_W", "LR_DD_W",
            "MIN_MONTHLY_TURNOVER", "COST_ROUNDTRIP_PCT", "RISK_FREE",
            "N_BUCKETS", "MIN_NONOVERLAPPING", "REGIME_TREND_PCT",
            "REGIME_VOL_ANN"])
    _cap(val, "horizons", lambda: list(__import__("pit_validation").HORIZONS))
    _cap(val, "factors", lambda: list(__import__("pit_validation").FACTORS))
    _cap(val, "bucket_order",
         lambda: list(__import__("market_validation").BUCKET_ORDER))
    spec["pit_validation"] = val

    ident = {}
    _block(ident, "security_identity",
           ["LINK_MAX_GAP_DAYS", "LINK_MAX_OVERLAP_DAYS"])
    spec["identity_resolution"] = ident

    port = {}
    _block(port, "portfolio_fix", ["MAX_SINGLE", "MAX_SECTOR", "MIN_HOLDINGS"])
    _cap(port, "risk_free_rate",
         lambda: __import__("portfolio_optimizer").RISK_FREE_RATE)
    spec["portfolio_construction"] = port

    uni = {}
    _block(uni, "universe_scan",
           ["LARGE_CAP_RANK_MAX", "MID_CAP_RANK_MAX", "LARGE_CAP_MIN",
            "MID_CAP_MIN"])
    spec["universe_rules"] = uni

    bm = {}
    _cap(bm, "index", lambda: __import__("benchmark").BENCHMARK)
    _cap(bm, "tracker_index",
         lambda: __import__("prediction_tracker").BENCHMARK)
    _cap(bm, "max_cycle_age_days",
         lambda: __import__("prediction_tracker").MAX_CYCLE_AGE_DAYS)
    _cap(bm, "min_effective_n",
         lambda: __import__("prediction_tracker").MIN_EFFECTIVE_N)
    spec["benchmark_and_tracking"] = bm

    try:
        from strategy_compare import COST_PER_UNIT_TURNOVER
        spec["costs"] = {
            "round_trip_cost_per_unit_turnover": round(COST_PER_UNIT_TURNOVER, 8),
            "components": ("brokerage 0.03%, STT 0.1%, stamp duty 0.015%, "
                           "exchange 0.00345%, GST 18% on brokerage+exchange"),
        }
    except Exception:
        pass

    try:
        from market_validation import (MIN_INDEPENDENT_PER_STRATUM, MIN_SECTORS,
                                       MIN_CAP_BUCKETS, MIN_INDEPENDENT_TOTAL,
                                       MIN_DISTINCT_DATES)
        # The bar for calling something validated is part of the strategy. If it
        # can be lowered after seeing a result, it is not a bar.
        spec["validation_thresholds"] = {
            "min_independent_per_stratum": MIN_INDEPENDENT_PER_STRATUM,
            "min_sectors": MIN_SECTORS,
            "min_cap_buckets": MIN_CAP_BUCKETS,
            "min_independent_total": MIN_INDEPENDENT_TOTAL,
            "min_distinct_dates": MIN_DISTINCT_DATES,
        }
    except Exception:
        pass

    # Which factors cannot be validated is part of the specification: a later
    # version that quietly starts claiming one of them is validated should show
    # as drift, not pass unnoticed.
    try:
        from factor_evidence import CANNOT_TEST
        spec["factors_not_historically_testable"] = sorted(CANNOT_TEST)
    except Exception:
        pass
    try:
        from factor_strategies import CANNOT_BACKTEST
        spec["factors_not_backtestable_as_strategies"] = sorted(CANNOT_BACKTEST)
    except Exception:
        pass

    # Environment. A version-controlled model is not a reproducible one: the
    # same code on a different numpy can return a different last decimal, and a
    # result attributed to a strategy is really attributed to a strategy AND
    # the stack that ran it. Recorded under its own key so a library upgrade
    # shows as environment drift rather than as the model changing.
    spec["environment"] = _environment()

    return spec


# Where a deployment publishes the commit it built from, when git itself is not
# in the image. Render sets the first; the others cost nothing to check and
# cover the platforms this could plausibly move to.
COMMIT_ENV_VARS = ("RENDER_GIT_COMMIT", "GIT_COMMIT", "SOURCE_VERSION",
                   "VERCEL_GIT_COMMIT_SHA", "HEROKU_SLUG_COMMIT")

NO_COMMIT_WARNING = (
    "PROVENANCE GAP: the commit that produced this run could not be "
    "determined. Git is not available and no deployment commit variable is "
    "set, so this record cannot identify the code it describes. Results "
    "produced here are reproducible only as far as the parameter values above "
    "— which is not the same as reproducible."
)


def _git_head(cwd=None):
    import subprocess
    return subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=cwd or os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stderr=subprocess.DEVNULL, timeout=5).decode().strip()


def _code_commit(run=None, environ=None) -> dict:
    """
    Which commit produced this run, and how we know.

    Locally git answers. In the deployed container it does not — the image has
    no .git directory — so the audit passed on a laptop and the production
    record carried a null commit, which is the one place provenance actually
    matters. The platform publishes the commit it built from as an environment
    variable, so that is the fallback.

    When neither is available the field stays null and a warning goes with it.
    A null that explains itself is a known gap; a bare null reads like nobody
    looked.
    """
    run = _git_head if run is None else run
    environ = os.environ if environ is None else environ
    try:
        c = (run() or "").strip()
        if c:
            return {"code_commit": c, "code_commit_source": "git",
                    "provenance_warning": None}
    except Exception:
        pass
    for var in COMMIT_ENV_VARS:
        v = (environ.get(var) or "").strip()
        if v:
            # Short form, so a git answer and a deployment answer look alike.
            return {"code_commit": v[:7], "code_commit_source": var,
                    "provenance_warning": None}
    return {"code_commit": None, "code_commit_source": None,
            "provenance_warning": NO_COMMIT_WARNING}


def _environment() -> dict:
    """What ran this, and on what data."""
    import platform

    env = {
        "python_version": platform.python_version(),
        "platform": platform.system(),
    }
    for lib in ("numpy", "pandas", "scipy", "statsmodels", "yfinance"):
        try:
            env[f"{lib}_version"] = __import__(lib).__version__
        except Exception:
            env[f"{lib}_version"] = None

    env.update(_code_commit())

    # The archive is data, and a result depends on which rows existed when it
    # ran. Recorded as a boundary and a row count rather than a hash of 1.5
    # million rows, which would change on every daily append.
    try:
        from db import get_conn
        c = get_conn()
        try:
            row = c.execute("SELECT MIN(day), MAX(day), COUNT(*) "
                            "FROM bhavcopy_eod").fetchone()
            env["archive"] = {"first_day": str(row[0])[:10],
                              "last_day": str(row[1])[:10],
                              "rows": int(row[2] or 0)}
        finally:
            c.close()
    except Exception:
        env["archive"] = None

    env["random_seeds"] = _random_seeds()
    return env


def _random_seeds() -> dict:
    """
    Seeds for every module whose randomness reaches a reported number.

    Recorded rather than removed. Monte Carlo, the optimiser stability check and
    the overfitting test are sampling methods — randomness is the method, not an
    accident — so the reproducible version of them is a fixed seed that travels
    with the result, not a deterministic rewrite that would change what they
    measure.
    """
    out = {}
    for mod, attr in (("monte_carlo", "RANDOM_SEED"),
                      ("optimizer_stability", "RANDOM_SEED"),
                      ("overfitting", "RANDOM_SEED")):
        try:
            out[mod] = getattr(__import__(mod), attr)
        except Exception:
            out[mod] = None
    return out


def freeze(version: str, notes: str = None, spec: dict = None,
           allow_incomplete: bool = False) -> dict:
    """
    Record a version. Refuses to overwrite an existing one.

    The refusal is the feature. A frozen spec that can be silently replaced
    after a disappointing result is not a record, it is a draft.
    """
    _init()
    version = (version or "").strip()
    if not version:
        return {"frozen": False, "reason": "A version name is required."}

    spec = spec or current_spec()

    # A freeze with holes in it is worse than no freeze, because it looks like
    # a complete record and is treated as one. v1.0 was frozen missing four
    # behavioural parameters and nobody noticed for a week, so this now refuses
    # rather than recording a specification it could not fully read.
    failures = spec.get("_capture_failures") or {}
    if failures and not allow_incomplete:
        return {
            "frozen": False, "version": version,
            "capture_failures": failures,
            "reason": (
                f"Refusing to freeze: {len(failures)} field(s) could not be "
                f"read from the live configuration "
                f"({', '.join(sorted(failures))}). A hash over a partial "
                f"specification silently fails to protect the fields it is "
                f"missing — exactly what happened to v1.0, which was frozen "
                f"without min_holdings or the momentum definition and reported "
                f"no drift when they were absent. Fix the capture, or pass "
                f"allow_incomplete if a permanently unavailable field is "
                f"genuinely acceptable."),
        }

    h = _hash(spec)
    now = datetime.now().isoformat()

    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT frozen_at, spec_hash FROM strategy_versions WHERE version = ?",
            (version,)).fetchone()
        if existing:
            same = existing[1] == h
            return {
                "frozen": False,
                "version": version,
                "already_frozen_at": existing[0],
                "identical": same,
                "reason": (
                    f"Version {version} was frozen on {existing[0]} and will not "
                    f"be overwritten. "
                    + ("The current configuration hashes identically, so nothing "
                       "has drifted."
                       if same else
                       "The current configuration hashes DIFFERENTLY, which means "
                       "something changed since it was frozen. Mint a new version "
                       "rather than editing this one.")),
            }
        conn.execute(
            "INSERT INTO strategy_versions (version, frozen_at, spec_json, "
            "spec_hash, notes) VALUES (?,?,?,?,?)",
            (version, now, json.dumps(spec, sort_keys=True), h, notes or ""))
        conn.commit()
    finally:
        conn.close()

    return {"frozen": True, "version": version, "frozen_at": now,
            "spec_hash": h, "spec": spec,
            "note": ("Recorded. Any later run can prove it used this exact "
                     "configuration by comparing the hash, rather than "
                     "asserting it.")}


def retract(version: str, reason: str) -> dict:
    """
    Mark a version as withdrawn, without deleting it.

    A version record can be wrong in a way that overwriting will not fix and
    deleting would hide. v1.2 was frozen against a stale deployment: its notes
    claimed to be the first complete specification while the spec it stored was
    byte-identical to v1.1, missing the same four parameters. Removing it would
    leave a gap in the numbering and no explanation; leaving it alone would
    leave a false claim standing.

    So the record stays, the reason stays with it, and anything that reads a
    version has to see both.
    """
    _init()
    if not (reason or "").strip():
        return {"retracted": False,
                "reason": "A retraction must say why, or it is just a deletion."}
    conn = get_conn()
    try:
        row = conn.execute("SELECT version FROM strategy_versions "
                           "WHERE version = ?", (version,)).fetchone()
        if not row:
            return {"retracted": False, "version": version,
                    "reason": f"No frozen version named {version}."}
        conn.execute("UPDATE strategy_versions SET retracted_at = ?, "
                     "retracted_reason = ? WHERE version = ?",
                     (datetime.now().isoformat(), reason.strip(), version))
        conn.commit()
    finally:
        conn.close()
    return {"retracted": True, "version": version, "reason": reason.strip(),
            "note": ("The record and its hash are kept. A retracted version is "
                     "part of the research trail, not an embarrassment to be "
                     "deleted from it.")}


def get(version: str) -> dict:
    _init()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT version, frozen_at, spec_json, spec_hash, notes, "
            "retracted_at, retracted_reason "
            "FROM strategy_versions WHERE version = ?", (version,)).fetchone()
    finally:
        conn.close()
    if not row:
        return {"found": False, "version": version}
    out = {"found": True, "version": row[0], "frozen_at": row[1],
           "spec": json.loads(row[2]), "spec_hash": row[3], "notes": row[4]}
    if len(row) > 5 and row[5]:
        out["retracted"] = True
        out["retracted_at"] = row[5]
        out["retracted_reason"] = row[6]
        out["warning"] = (f"This version was RETRACTED on {str(row[5])[:10]}. "
                          f"Do not attribute results to it.")
    else:
        out["retracted"] = False
    return out


def listing() -> dict:
    _init()
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT version, frozen_at, spec_hash, notes, retracted_at, "
            "retracted_reason FROM strategy_versions "
            "ORDER BY frozen_at").fetchall()
    finally:
        conn.close()
    versions = []
    for r in rows:
        v = {"version": r[0], "frozen_at": r[1], "spec_hash": r[2],
             "notes": r[3], "retracted": bool(len(r) > 4 and r[4])}
        if v["retracted"]:
            v["retracted_at"] = r[4]
            v["retracted_reason"] = r[5]
        versions.append(v)
    return {"versions": versions, "count": len(versions),
            "active": sum(1 for v in versions if not v["retracted"]),
            "retracted": sum(1 for v in versions if v["retracted"])}


def drift(version: str) -> dict:
    """
    Has the live configuration moved away from a frozen version?

    This is the question that decides whether a result can still be attributed
    to that version. Answering it by eye across five modules is how drift goes
    unnoticed.
    """
    rec = get(version)
    if not rec.get("found"):
        return {"found": False, "version": version}
    live = current_spec()
    # captured_at always differs; it is metadata, not configuration.
    a = {k: v for k, v in rec["spec"].items() if k != "captured_at"}
    b = {k: v for k, v in live.items() if k != "captured_at"}
    # Same three-way split compare_versions uses. A field the frozen spec never
    # recorded has not "changed" — the record simply never covered it, and the
    # hash cannot speak to a value it never saw. Reporting that as behavioural
    # drift would retire a sound result; reporting it as no drift at all would
    # hide a gap in what the hash protects.
    entries, changed, uncovered = [], [], []
    for k in sorted(set(a) | set(b)):
        if a.get(k) == b.get(k):
            continue
        if k not in a:
            why = "never captured by this version"
            uncovered.append(k)
        elif k not in b:
            why = "no longer present in the live configuration"
            uncovered.append(k)
        else:
            why = "value differs"
            changed.append(k)
        entries.append({
            "field": k,
            "kind": _kind_of(k),
            "difference": why,
            "frozen": a.get(k), "live": b.get(k)})

    behavioural, metadata, environment = _classify(set(changed))
    unc_behavioural = [k for k in uncovered
                       if k not in METADATA_FIELDS and k not in ENVIRONMENT_FIELDS]

    if not entries:
        verdict = "The live configuration still matches this version."
    elif behavioural:
        verdict = (f"{len(behavioural)} behavioural field(s) hold different "
                   f"values from the frozen spec ({', '.join(behavioural)}). A "
                   f"result produced now cannot be attributed to {version} — "
                   f"mint a new version instead.")
    elif unc_behavioural:
        verdict = (f"No field recorded by {version} differs in value. "
                   f"{len(unc_behavioural)} behavioural field(s) appear in the "
                   f"live specification that {version} never captured "
                   f"({', '.join(unc_behavioural)}). The strategy behaves as it "
                   f"did; what changed is that the record now covers more of "
                   f"it. Note the corollary: {version}'s hash never protected "
                   f"those fields, so it cannot prove what they held when it "
                   f"was frozen."
                   + (f" Metadata also differs: {', '.join(metadata)}."
                      if metadata else ""))
    elif environment and not metadata:
        verdict = (f"Environment only: the stack or the archive this ran on "
                   f"differs from when {version} was frozen. No strategy "
                   f"parameter moved, so the model behaves identically — but a "
                   f"number reproduced now may differ in its last decimal, and "
                   f"that is a reproducibility fact rather than a model one.")
    else:
        verdict = (f"Metadata only: {', '.join(metadata)}. No factor weight, "
                   f"threshold, cost or rule differs, so the strategy behaves "
                   f"exactly as it did when {version} was frozen and results "
                   f"remain attributable to it. The hash differs because the "
                   f"hash covers the whole record, which is the point of "
                   f"hashing it.")

    return {
        "found": True, "version": version, "frozen_at": rec["frozen_at"],
        "drifted": bool(entries),
        "behavioural_drift": bool(behavioural),
        "metadata_drift": bool(metadata),
        "environment_drift": bool(environment),
        "coverage_gap": sorted(uncovered),
        "changes": entries,
        "verdict": verdict,
    }


def compare_versions(a: str, b: str) -> dict:
    """
    What actually differs between two frozen versions.

    Exists so that "V1.1 is behaviourally identical to V1.0" is something a
    reader can check rather than something the notes field claims.
    """
    ra, rb = get(a), get(b)
    if not ra.get("found"):
        return {"found": False, "missing": a}
    if not rb.get("found"):
        return {"found": False, "missing": b}

    sa = {k: v for k, v in ra["spec"].items() if k != "captured_at"}
    sb = {k: v for k, v in rb["spec"].items() if k != "captured_at"}
    # A field ABSENT from one side is not evidence its value changed — it is
    # evidence that side never recorded it. Conflating the two would let a
    # capture defect masquerade as a strategy change, or worse, let a real
    # change hide behind the excuse of one.
    entries, changed, coverage = [], [], []
    for k in sorted(set(sa) | set(sb)):
        if sa.get(k) == sb.get(k):
            continue
        if k not in sa:
            why = f"not captured by {a}"
            coverage.append(k)
        elif k not in sb:
            why = f"not captured by {b}"
            coverage.append(k)
        else:
            why = "value differs"
            changed.append(k)
        entries.append({
            "field": k,
            "kind": _kind_of(k),
            "difference": why,
            a: sa.get(k), b: sb.get(k)})

    behavioural, metadata, environment = _classify(set(changed))

    if behavioural:
        verdict = (f"{len(behavioural)} behavioural field(s) hold DIFFERENT "
                   f"values: {', '.join(behavioural)}. These are different "
                   f"strategies and their results are not interchangeable.")
    elif metadata and not coverage:
        verdict = (f"{a} and {b} are behaviourally identical. The only "
                   f"difference is {', '.join(metadata)}, which records what "
                   f"was understood about the strategy rather than what it "
                   f"does. A backtest of one is a backtest of the other.")
    elif coverage:
        verdict = (f"No field recorded by both versions differs. "
                   f"{len(coverage)} field(s) are present in one record and "
                   f"absent from the other ({', '.join(coverage)}), which is a "
                   f"difference in what was CAPTURED, not in what the strategy "
                   f"does. Behaviour is unchanged; the coverage of the hash is "
                   f"not."
                   + (f" Metadata also differs: {', '.join(metadata)}."
                      if metadata else ""))
    else:
        verdict = f"{a} and {b} are identical in every recorded field."

    return {
        "found": True,
        "a": {"version": a, "frozen_at": ra["frozen_at"], "spec_hash": ra["spec_hash"]},
        "b": {"version": b, "frozen_at": rb["frozen_at"], "spec_hash": rb["spec_hash"]},
        "behaviourally_identical": not behavioural,
        "behavioural_changes": behavioural,
        "metadata_changes": metadata,
        "environment_changes": environment,
        "coverage_differences": coverage,
        "changes": entries,
        "verdict": verdict,
    }
