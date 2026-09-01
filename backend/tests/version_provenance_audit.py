"""
version_provenance_audit.py — can the freeze actually miss a parameter?

v1.0 was frozen for a week with the string "ImportError" where four behavioural
parameters should have been, and the drift check reported no change the whole
time. That is the failure this audit exists to make impossible to repeat, so it
does not ask whether the current spec looks complete. It asks:

  1. Is every parameter that can change a result CLASSIFIED?
     An unclassified constant is the failure mode, because nobody decided
     about it.
  2. Is every BEHAVIOURAL parameter actually IN the frozen spec?
  3. Does changing each one actually move the hash?
     A field in the spec that does not affect the hash is decoration.
  4. Are there behavioural parameters that CANNOT be captured as written —
     inline literals with no name to import?

Question 4 is the one a coverage checklist cannot answer, because a magic
number inside a function is invisible to every check that works by importing
names. So this walks the syntax tree instead.

READ ONLY. This audit freezes nothing, retracts nothing and modifies no
version. It reports.
"""

import ast
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
MODDIR = os.path.join(os.path.dirname(__file__), "..", "modules")

import strategy_version as sv  # noqa: E402

FAIL, PASS, GAPS = [], [], []


def ok(cond, label, gap=None):
    (PASS if cond else FAIL).append(label)
    if not cond and gap:
        GAPS.append(gap)
    print(f"  [{'ok  ' if cond else 'GAP '}] {label}")


# ---------------------------------------------------------------------------
# The declared inventory. Every module-level constant in a critical module must
# appear here, classified. A constant that is not listed fails the audit — the
# point is that somebody decided, not that the list is long.
#
#   BEHAVIOURAL — changes a score, a selection, a weight or a result
#   METADATA    — documentation, labels, explanatory text
#   ENVIRONMENT — affects reproducibility but is not the strategy
#   OPERATIONAL — scheduling, concurrency, politeness; cannot change a result
# ---------------------------------------------------------------------------
INVENTORY = {
    "alpha_model": {
        "MODEL_VERSION": "METADATA",
        "FACTOR_WEIGHTS": "BEHAVIOURAL",
        "SENTIMENT_HALF_LIFE_DAYS": "BEHAVIOURAL",
        "TOP_PICKS_UNIVERSE": "BEHAVIOURAL",
    },
    "alpha_v2": {
        "WEIGHTS_V2": "BEHAVIOURAL",
        "WEIGHT_NOTES": "METADATA",
        "MODEL_VERSION_V2": "METADATA",
        "FACTOR_PLAIN": "METADATA",
    },
    "momentum_backtest": {
        "DEFAULT_UNIVERSE": "BEHAVIOURAL",
        "BROAD_UNIVERSE": "BEHAVIOURAL",
        "MIN_HOLDINGS": "BEHAVIOURAL",
    },
    "pit_backtest": {
        "COST_ROUNDTRIP_PCT": "BEHAVIOURAL",
        "LOOKBACK_MONTHS": "BEHAVIOURAL",
        "SKIP_MONTHS": "BEHAVIOURAL",
        "MIN_HOLDINGS": "BEHAVIOURAL",
        "MIN_MONTHLY_TURNOVER": "BEHAVIOURAL",
    },
    "pit_validation": {
        "MOM_LOOKBACK": "BEHAVIOURAL", "MOM_SKIP": "BEHAVIOURAL",
        "MOM_TANH_DIV": "BEHAVIOURAL", "LR_WINDOW": "BEHAVIOURAL",
        "LR_VOL_REF": "BEHAVIOURAL", "LR_DD_REF": "BEHAVIOURAL",
        "LR_VOL_W": "BEHAVIOURAL", "LR_DD_W": "BEHAVIOURAL",
        "MIN_MONTHLY_TURNOVER": "BEHAVIOURAL",
        "COST_ROUNDTRIP_PCT": "BEHAVIOURAL", "RISK_FREE": "BEHAVIOURAL",
        "N_BUCKETS": "BEHAVIOURAL", "HORIZONS": "BEHAVIOURAL",
        "MIN_NONOVERLAPPING": "BEHAVIOURAL",
        "REGIME_TREND_PCT": "BEHAVIOURAL", "REGIME_VOL_ANN": "BEHAVIOURAL",
        "FACTORS": "BEHAVIOURAL", "UNTESTABLE": "METADATA",
    },
    "strategy_compare": {"COST_PER_UNIT_TURNOVER": "BEHAVIOURAL"},
    "market_validation": {
        "BUCKET_ORDER": "BEHAVIOURAL",
        "MIN_INDEPENDENT_PER_STRATUM": "BEHAVIOURAL",
        "MIN_SECTORS": "BEHAVIOURAL", "MIN_CAP_BUCKETS": "BEHAVIOURAL",
        "MIN_INDEPENDENT_TOTAL": "BEHAVIOURAL",
        "MIN_DISTINCT_DATES": "BEHAVIOURAL",
    },
    "prediction_tracker": {
        "BENCHMARK": "BEHAVIOURAL",
        "MAX_CYCLE_AGE_DAYS": "BEHAVIOURAL",
        "MIN_EFFECTIVE_N": "BEHAVIOURAL",
    },
    "security_identity": {
        "LINK_MAX_GAP_DAYS": "BEHAVIOURAL",
        "LINK_MAX_OVERLAP_DAYS": "BEHAVIOURAL",
    },
    "bhavcopy": {"ARCHIVE_STARTS": "BEHAVIOURAL"},
    "portfolio_fix": {
        "MAX_SINGLE": "BEHAVIOURAL", "MAX_SECTOR": "BEHAVIOURAL",
        "MIN_HOLDINGS": "BEHAVIOURAL",
    },
    "portfolio_optimizer": {"RISK_FREE_RATE": "BEHAVIOURAL"},
    "risk_management": {"RISK_FREE": "BEHAVIOURAL"},
    "benchmark": {"BENCHMARK": "BEHAVIOURAL", "BENCHMARK_NAME": "METADATA"},
    "universe_scan": {
        "PAUSE_BETWEEN": "OPERATIONAL", "PAUSE_ON_ERROR": "OPERATIONAL",
        "CYCLE_HOURS": "OPERATIONAL", "MAX_WORKERS": "OPERATIONAL",
        "MODEL_VERSION": "METADATA",
        "LARGE_CAP_RANK_MAX": "BEHAVIOURAL", "MID_CAP_RANK_MAX": "BEHAVIOURAL",
        "LARGE_CAP_MIN": "BEHAVIOURAL", "MID_CAP_MIN": "BEHAVIOURAL",
    },
    "factor_evidence": {
        "LOOKAHEAD_REASON": "METADATA", "SENTIMENT_REASON": "METADATA",
        "CANNOT_TEST": "METADATA", "RECONSTRUCTIBLE_FROM_PRICES": "METADATA",
        "PLAIN": "METADATA",
    },
    "factor_strategies": {"CANNOT_BACKTEST": "METADATA", "PLAIN": "METADATA"},
    "backtest_integrity": {"SAFE_VALIDATED": "METADATA",
                           "SAFE_RESEARCH": "METADATA"},
    "screener": {"DB_PATH": "ENVIRONMENT"},
}


def module_constants(mod):
    """
    Every module-level constant, including the ones a naive scan misses.

    The first version of this walked only simple `NAME = value` targets and
    reported LR_VOL_W and LR_DD_W as deleted, because they are assigned as
    `LR_VOL_W, LR_DD_W = 0.6, 0.4`. That is a blind spot in the auditor, and an
    auditor with a blind spot is worse than none — it certifies the part it
    cannot see. Tuple, list and annotated targets are all handled now.
    """
    p = os.path.join(MODDIR, mod + ".py")
    if not os.path.exists(p):
        return {}
    tree = ast.parse(open(p, encoding="utf-8").read())
    found = {}

    def take(name):
        if name.isupper() and not name.startswith("_"):
            found[name] = True

    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    take(t.id)
                elif isinstance(t, (ast.Tuple, ast.List)):
                    for e in t.elts:
                        if isinstance(e, ast.Name):
                            take(e.id)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            take(n.target.id)
    return found


print("=" * 70)
print("SECTION 1 — is every constant classified?")
print("=" * 70)
unclassified = []
for mod, declared in INVENTORY.items():
    actual = module_constants(mod)
    for name in actual:
        if name not in declared:
            unclassified.append(f"{mod}.{name}")
    for name in declared:
        if name not in actual:
            unclassified.append(f"{mod}.{name} (declared but no longer exists)")
ok(not unclassified,
   f"every module-level constant is classified ({len(unclassified)} unclassified)",
   gap=("Unclassified constants: " + ", ".join(unclassified)) if unclassified else None)
for u in unclassified:
    print(f"         ! {u}")

behavioural = {(m, n) for m, d in INVENTORY.items()
               for n, k in d.items() if k == "BEHAVIOURAL"}
print(f"\n  classified: {sum(len(d) for d in INVENTORY.values())} constants")
for kind in ("BEHAVIOURAL", "METADATA", "ENVIRONMENT", "OPERATIONAL"):
    n = sum(1 for d in INVENTORY.values() for k in d.values() if k == kind)
    print(f"    {kind:<12} {n}")


print("\n" + "=" * 70)
print("SECTION 2 — are behavioural parameters actually IN the spec?")
print("=" * 70)
spec = sv.current_spec()
ok(not (spec.get("_capture_failures") or {}),
   "the live spec has no capture failures",
   gap=f"capture failures: {spec.get('_capture_failures')}")
ok("backtest_error" not in spec, "no swallowed error marker in the spec",
   gap="spec contains a swallowed error marker")

flat = {}


def flatten(d, prefix=""):
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and k not in ("factor_weights", "v1_factor_weights"):
            flatten(v, key + ".")
        else:
            flat[key] = v


flatten(spec)
spec_blob = repr(sorted(flat.items()))

# Each behavioural constant must be traceable into the spec. Matching on NAME
# alone is not enough and is wrong in both directions: WEIGHTS_V2 is captured
# faithfully under the key `factor_weights`, and a key that merely shares a word
# with a constant proves nothing about its value. So the value is what gets
# compared, with the name as a fallback.
def _norm(v):
    if isinstance(v, dict):
        return {str(k): _norm(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_norm(x) for x in v]
    if isinstance(v, float):
        return round(v, 6)
    return v


def _appears(value, node):
    """Does `value` appear anywhere inside the captured spec?"""
    n = _norm(value)
    if _norm(node) == n:
        return True
    if isinstance(node, dict):
        return any(_appears(value, v) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(_appears(value, v) for v in node)
    return False


# An explicit mapping, because both looser tests are wrong. Name matching
# misses WEIGHTS_V2, which is captured faithfully as `factor_weights`. Value
# matching passes MAX_SECTOR = 40.0 because default_universe_size happens to be
# 40 — a coincidence certifying a parameter nothing captures.
#
# So each covered constant declares WHERE it is captured, and the audit checks
# the value at that path. Anything without an entry is not covered, and nothing
# can drift into looking covered by accident.
SPEC_MAPPING = {
    ("alpha_v2", "WEIGHTS_V2"): ("factor_weights", None),
    ("alpha_model", "FACTOR_WEIGHTS"): ("v1_factor_weights", None),
    ("momentum_backtest", "MIN_HOLDINGS"): ("backtest.min_holdings", None),
    ("momentum_backtest", "DEFAULT_UNIVERSE"): ("backtest.default_universe_size", len),
    ("momentum_backtest", "BROAD_UNIVERSE"): ("backtest.broad_universe_size", len),
    ("bhavcopy", "ARCHIVE_STARTS"): ("backtest.archive_starts", None),
    ("pit_backtest", "COST_ROUNDTRIP_PCT"): ("pit_backtest.cost_roundtrip_pct", None),
    ("pit_backtest", "LOOKBACK_MONTHS"): ("pit_backtest.lookback_months", None),
    ("pit_backtest", "SKIP_MONTHS"): ("pit_backtest.skip_months", None),
    ("pit_backtest", "MIN_HOLDINGS"): ("pit_backtest.min_holdings", None),
    ("pit_backtest", "MIN_MONTHLY_TURNOVER"): ("pit_backtest.min_monthly_turnover", None),
    ("strategy_compare", "COST_PER_UNIT_TURNOVER"):
        ("costs.round_trip_cost_per_unit_turnover", None),
    ("market_validation", "MIN_INDEPENDENT_PER_STRATUM"):
        ("validation_thresholds.min_independent_per_stratum", None),
    ("market_validation", "MIN_SECTORS"): ("validation_thresholds.min_sectors", None),
    ("market_validation", "MIN_CAP_BUCKETS"):
        ("validation_thresholds.min_cap_buckets", None),
    ("market_validation", "MIN_INDEPENDENT_TOTAL"):
        ("validation_thresholds.min_independent_total", None),
    ("market_validation", "MIN_DISTINCT_DATES"):
        ("validation_thresholds.min_distinct_dates", None),
}


def at_path(node, path):
    for p in path.split("."):
        if not isinstance(node, dict) or p not in node:
            return ("__ABSENT__",)
        node = node[p]
    return node


covered, missing, wrong = [], [], []
for mod, name in sorted(behavioural):
    try:
        val = getattr(__import__(mod), name)
    except Exception as e:
        missing.append((mod, name, f"UNREADABLE: {type(e).__name__}"))
        continue
    entry = SPEC_MAPPING.get((mod, name))
    if entry is None:
        missing.append((mod, name, "no spec field captures this"))
        continue
    path, transform = entry
    got = at_path(spec, path)
    want = transform(val) if transform else val
    if got == ("__ABSENT__",):
        missing.append((mod, name, f"declared at {path}, which is absent"))
    elif _norm(got) != _norm(want):
        wrong.append((mod, name, f"{path} holds {got!r}, module holds {want!r}"))
    else:
        covered.append((mod, name, path))

ok(not wrong,
   f"every captured field matches the module it came from ({len(wrong)} mismatched)",
   gap=("Spec fields disagreeing with their source module: "
        + "; ".join(f"{m}.{n}: {w}" for m, n, w in wrong)) if wrong else None)
for m, n, w in wrong:
    print(f"         ! {m}.{n} — {w}")

ok(not missing,
   f"every behavioural constant appears in the spec "
   f"({len(covered)} covered, {len(missing)} missing)",
   gap=("Behavioural constants absent from the frozen spec: "
        + ", ".join(f"{m}.{n}" for m, n, _ in missing)) if missing else None)
for m, n, why in missing:
    print(f"         ! {m}.{n} — {why}")


print("\n" + "=" * 70)
print("SECTION 3 — behavioural parameters that CANNOT be captured as written")
print("=" * 70)
# A magic number inside a function has no name to import, so no coverage check
# can see it. These are found by walking the tree instead.
CRITICAL_FUNCS = {
    "alpha_model": ["_compute_momentum_factor", "compute_alpha_score"],
    "alpha_v2": ["_low_risk_factor", "_growth_factor", "compute_v2"],
}
inline = []
for mod, funcs in CRITICAL_FUNCS.items():
    p = os.path.join(MODDIR, mod + ".py")
    if not os.path.exists(p):
        continue
    tree = ast.parse(open(p, encoding="utf-8").read())
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name in funcs):
            continue
        for sub in ast.walk(node):
            # Numeric literals used in arithmetic or comparison are the ones
            # that move a score. Indices and 0/1 are excluded as noise.
            if isinstance(sub, (ast.BinOp, ast.Compare)):
                for c in ast.walk(sub):
                    if isinstance(c, ast.Constant) and isinstance(c.value, (int, float)) \
                            and not isinstance(c.value, bool) \
                            and c.value not in (0, 1, 2, 100, -1):
                        inline.append((mod, node.name, c.lineno, c.value))
uniq = sorted(set(inline))
ok(not uniq,
   f"no uncapturable inline constants in scoring functions ({len(uniq)} found)",
   gap=("Inline numeric constants inside scoring functions, unreachable by any "
        "import and therefore absent from every freeze: "
        + ", ".join(f"{m}.{f}:{ln}={v}" for m, f, ln, v in uniq[:20])) if uniq else None)
for m, f, ln, v in uniq[:24]:
    print(f"         ! {m}.{f}  line {ln}  literal {v}")


print("\n" + "=" * 70)
print("SECTION 4 — does changing a parameter actually move the hash?")
print("=" * 70)
base_hash = sv._hash(spec)


def mutate(path, newval):
    import copy
    s = copy.deepcopy(spec)
    cur = s
    parts = path.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = newval
    return sv._hash(s)


SENSITIVITY = [
    ("factor_weights.momentum", 0.99),
    ("v1_factor_weights.momentum", 0.99),
    ("backtest.min_holdings", 3),
    ("backtest.momentum_definition", "6-1"),
    ("backtest.archive_starts", "2019-01-01"),
    ("backtest.rebalance", "weekly"),
    ("backtest.default_universe_size", 41),
    ("pit_backtest.cost_roundtrip_pct", 0.1),
    ("pit_backtest.lookback_months", 6),
    ("pit_backtest.skip_months", 0),
    ("pit_backtest.min_holdings", 3),
    ("pit_backtest.min_monthly_turnover", 1.0),
    ("costs.round_trip_cost_per_unit_turnover", 0.001),
    ("validation_thresholds.min_independent_total", 10),
]
insensitive = []
for path, val in SENSITIVITY:
    h = mutate(path, val)
    moved = h != base_hash
    if not moved:
        insensitive.append(path)
    print(f"    {'moves ' if moved else 'INERT '} {path} -> {val}")
ok(not insensitive, f"every spec field moves the hash when changed",
   gap=f"fields present in the spec but not affecting the hash: {insensitive}"
       if insensitive else None)


print("\n" + "=" * 70)
print("SECTION 5 — drift classification behaves")
print("=" * 70)
_real_get, _real_cur = sv.get, sv.current_spec
frozen = dict(spec)

sv.get = lambda v: {"found": True, "version": v, "frozen_at": "x",
                    "spec": frozen, "spec_hash": sv._hash(frozen)}

import copy  # noqa: E402
mut = copy.deepcopy(spec)
mut["factor_weights"] = dict(mut["factor_weights"]); mut["factor_weights"]["momentum"] = 0.5
sv.current_spec = lambda: mut
d = sv.drift("v1.3")
ok(d["drifted"] and d["behavioural_drift"],
   "a changed factor weight raises BEHAVIOURAL drift",
   gap="a changed factor weight did not raise behavioural drift")

mut2 = copy.deepcopy(spec)
mut2["factors_not_historically_testable"] = ["everything"]
sv.current_spec = lambda: mut2
d2 = sv.drift("v1.3")
ok(d2["drifted"] and not d2["behavioural_drift"] and d2["metadata_drift"],
   "a metadata-only change raises drift but NOT behavioural drift",
   gap="metadata-only change was misclassified")

mut3 = copy.deepcopy(spec)
mut3["backtest"] = dict(mut3["backtest"]); mut3["backtest"]["min_holdings"] = 3
sv.current_spec = lambda: mut3
d3 = sv.drift("v1.3")
ok(d3["behavioural_drift"], "min_holdings 5 -> 3 raises behavioural drift",
   gap="min_holdings change did not raise behavioural drift")

sv.current_spec = lambda: copy.deepcopy(spec)
d4 = sv.drift("v1.3")
ok(not d4["drifted"], "an unchanged configuration reports no drift",
   gap="identical configuration reported drift")

sv.get, sv.current_spec = _real_get, _real_cur


print("\n" + "=" * 70)
print("SECTION 6 — environment and reproducibility")
print("=" * 70)
env_missing = []
for key in ("python_version", "numpy_version", "random_seed", "data_source",
            "archive_snapshot"):
    if not any(key in k for k in flat):
        env_missing.append(key)
ok(not env_missing,
   f"the spec records its execution environment ({len(env_missing)} missing)",
   gap=f"environment fields absent from the spec: {', '.join(env_missing)}")

# Randomness anywhere in the result path is a reproducibility hazard.
rand = []
for f in os.listdir(MODDIR):
    if not f.endswith(".py"):
        continue
    src = open(os.path.join(MODDIR, f), encoding="utf-8", errors="ignore").read()
    for marker in ("random.", "np.random", "default_rng", "shuffle("):
        if marker in src:
            rand.append(f"{f}:{marker}")
ok(not rand, f"no unseeded randomness in the modules ({len(rand)} sites)",
   gap=f"randomness present without a recorded seed: {', '.join(sorted(set(rand))[:10])}")
for r in sorted(set(rand))[:10]:
    print(f"         ! {r}")


print("\n" + "=" * 70)
print(f"RESULT: {len(PASS)} checks passed, {len(FAIL)} gaps")
print("=" * 70)
if GAPS:
    print("\nGAPS FOUND — v1.3 CANNOT be called a complete frozen specification:\n")
    for i, g in enumerate(GAPS, 1):
        print(f"  {i}. {g}\n")
else:
    print("\nNo gaps. v1.3 covers every classified behavioural parameter.\n")
sys.exit(1 if FAIL else 0)
