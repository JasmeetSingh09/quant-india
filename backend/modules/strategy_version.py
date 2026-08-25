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
from datetime import datetime

try:
    from db import get_conn, IS_POSTGRES
except Exception:                                   # pragma: no cover
    from .db import get_conn, IS_POSTGRES

_READY = False


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
    _READY = True


def _hash(spec: dict) -> str:
    """Stable hash of the specification. sort_keys so a reordered dict is the
    same strategy, which it is."""
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":"))
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

    try:
        from momentum_backtest import (MIN_HOLDINGS, ARCHIVE_STARTS,
                                       DEFAULT_UNIVERSE, BROAD_UNIVERSE)
        spec["backtest"] = {
            "min_holdings": MIN_HOLDINGS,
            "archive_starts": ARCHIVE_STARTS,
            "default_universe_size": len(DEFAULT_UNIVERSE),
            "broad_universe_size": len(BROAD_UNIVERSE),
            "rebalance": "monthly",
            "momentum_definition": "12-1 (12-month lookback, most recent month skipped)",
        }
    except Exception as e:
        spec["backtest_error"] = type(e).__name__

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

    return spec


def freeze(version: str, notes: str = None, spec: dict = None) -> dict:
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


def get(version: str) -> dict:
    _init()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT version, frozen_at, spec_json, spec_hash, notes "
            "FROM strategy_versions WHERE version = ?", (version,)).fetchone()
    finally:
        conn.close()
    if not row:
        return {"found": False, "version": version}
    return {"found": True, "version": row[0], "frozen_at": row[1],
            "spec": json.loads(row[2]), "spec_hash": row[3], "notes": row[4]}


def listing() -> dict:
    _init()
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT version, frozen_at, spec_hash, notes FROM strategy_versions "
            "ORDER BY frozen_at").fetchall()
    finally:
        conn.close()
    return {"versions": [{"version": r[0], "frozen_at": r[1],
                          "spec_hash": r[2], "notes": r[3]} for r in rows],
            "count": len(rows)}


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
    changed = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            changed.append({"field": k, "frozen": a.get(k), "live": b.get(k)})
    return {
        "found": True, "version": version, "frozen_at": rec["frozen_at"],
        "drifted": bool(changed), "changes": changed,
        "verdict": ("The live configuration still matches this version."
                    if not changed else
                    f"{len(changed)} field(s) differ from the frozen spec. Any "
                    f"result produced now cannot be attributed to {version} — "
                    f"mint a new version instead."),
    }
