"""
version_provenance_audit.py — can the freeze still miss a parameter?

v1.0 was frozen for a week with the string "ImportError" where four behavioural
parameters should have been, and the drift check reported no change the whole
time. The first run of this audit then found 35 more uncaptured parameters and
33 numeric literals sitting inside scoring functions with no name to import —
including the four cut-points that decide every Strong Buy and Strong Sell the
platform displays.

This is the gate. It fails if:

  - a behavioural parameter is missing from the freeze
  - a behavioural constant is unclassified
  - a scoring literal is uncaptured
  - a new behavioural constant appears without registration
  - a capture operation fails
  - an import failure removes a specification block
  - a required environment field is missing
  - a research randomness source has no reproducibility treatment

Coverage is established by an explicit mapping from constant to spec path, and
the value at that path is compared to the module. Not by name matching, which
misses WEIGHTS_V2 because it is captured as `factor_weights`. Not by value
matching, which passed MAX_SECTOR = 40.0 because default_universe_size happens
to be 40 — a coincidence certifying a parameter nothing captured.

Section 0 audits the auditor. Every detection mechanism here is tested against
a fixture containing the construct it is supposed to find, because a checker
that cannot see a construct silently certifies it — which is exactly what
happened when the first version walked only simple NAME = value assignments and
reported two tuple-assigned constants as deleted.

READ ONLY. Freezes nothing, retracts nothing, modifies no version.
"""

import ast
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
MODDIR = os.path.join(os.path.dirname(__file__), "..", "modules")

import strategy_version as sv  # noqa: E402

FAIL, PASS, GAPS = [], [], []


def ok(cond, label, gap=None):
    (PASS if cond else FAIL).append(label)
    if not cond and gap:
        GAPS.append(gap)
    print(f"  [{'ok  ' if cond else 'GAP '}] {label}")


# ---------------------------------------------------------------- inventory
# ALIAS is a fifth category, not a fourth-and-a-half. A constant imported from
# a shared module is a REFERENCE to a decision made elsewhere, not a decision
# of its own: it needs no separate spec field, because freezing it twice would
# record the same value under two names and invite them to diverge on paper.
# What it does need is proof that it still equals what it points at.
BEHAVIOURAL, METADATA, ENVIRONMENT, OPERATIONAL, ALIAS = (
    "BEHAVIOURAL", "METADATA", "ENVIRONMENT", "OPERATIONAL", "ALIAS")

INVENTORY = {
    "alpha_model": {
        "MODEL_VERSION": METADATA, "FACTOR_WEIGHTS": BEHAVIOURAL,
        "SENTIMENT_HALF_LIFE_DAYS": BEHAVIOURAL,
        "TOP_PICKS_UNIVERSE": BEHAVIOURAL,
        "MOMENTUM_LOOKBACK_DAYS": BEHAVIOURAL,
        "MOMENTUM_SKIP_DAYS": BEHAVIOURAL,
        "MOMENTUM_HISTORY_BUFFER_DAYS": BEHAVIOURAL,
        "MOMENTUM_MIN_OBSERVATIONS": BEHAVIOURAL,
        "MOMENTUM_MIN_RETURNS": BEHAVIOURAL,
        "MOMENTUM_VOL_EPSILON": BEHAVIOURAL,
        "MOMENTUM_TANH_DIVISOR": BEHAVIOURAL,
        "MOMENTUM_CONFIDENCE_BASE": BEHAVIOURAL,
        "MOMENTUM_CONFIDENCE_SPAN": BEHAVIOURAL,
        "SIGNAL_STRONG_BUY": BEHAVIOURAL, "SIGNAL_BUY": BEHAVIOURAL,
        "SIGNAL_SELL": BEHAVIOURAL, "SIGNAL_STRONG_SELL": BEHAVIOURAL,
        "SIGNAL_COLOURS": METADATA,
        "MOMENTUM_INTERP_STRONG": BEHAVIOURAL,
        "MOMENTUM_INTERP_MILD": BEHAVIOURAL,
    },
    "alpha_v2": {
        "WEIGHTS_V2": BEHAVIOURAL, "WEIGHT_NOTES": METADATA,
        "MODEL_VERSION_V2": METADATA, "FACTOR_PLAIN": METADATA,
        "GROWTH_REVENUE_DIVISOR": BEHAVIOURAL,
        "GROWTH_EARNINGS_DIVISOR": BEHAVIOURAL,
        "GROWTH_PART_WEIGHT": BEHAVIOURAL,
        "GROWTH_CONFIDENCE_SCALE": BEHAVIOURAL,
        "LOW_RISK_WINDOW_DAYS": BEHAVIOURAL,
        "LOW_RISK_MIN_RETURNS": BEHAVIOURAL,
        "LOW_RISK_VOL_REF": BEHAVIOURAL, "LOW_RISK_DD_REF": BEHAVIOURAL,
        "LOW_RISK_VOL_WEIGHT": BEHAVIOURAL, "LOW_RISK_DD_WEIGHT": BEHAVIOURAL,
        "LOW_RISK_CONFIDENCE_BASE": BEHAVIOURAL,
        "LOW_RISK_CONFIDENCE_DIVISOR": BEHAVIOURAL,
    },
    "model_config": {
        "RISK_FREE_RATE": BEHAVIOURAL, "TRADING_DAYS_PER_YEAR": BEHAVIOURAL,
        "MONTHS_PER_YEAR": BEHAVIOURAL, "COST_BROKERAGE_PCT": BEHAVIOURAL,
        "COST_STT_PCT": BEHAVIOURAL, "COST_STAMP_DUTY_PCT": BEHAVIOURAL,
        "COST_EXCHANGE_PCT": BEHAVIOURAL, "COST_GST_PCT": BEHAVIOURAL,
        "BENCHMARK_INDEX": BEHAVIOURAL, "BENCHMARK_NAME": METADATA,
        "SCAN_COMPLETE_FRACTION": BEHAVIOURAL, "MUST_AGREE": METADATA,
    },
    "momentum_backtest": {
        "DEFAULT_UNIVERSE": BEHAVIOURAL, "BROAD_UNIVERSE": BEHAVIOURAL,
        "MIN_HOLDINGS": BEHAVIOURAL,
    },
    "pit_backtest": {
        "COST_ROUNDTRIP_PCT": BEHAVIOURAL, "LOOKBACK_MONTHS": BEHAVIOURAL,
        "SKIP_MONTHS": BEHAVIOURAL, "MIN_HOLDINGS": BEHAVIOURAL,
        "MIN_MONTHLY_TURNOVER": BEHAVIOURAL,
    },
    "pit_validation": {
        "MOM_LOOKBACK": BEHAVIOURAL, "MOM_SKIP": BEHAVIOURAL,
        "MOM_TANH_DIV": BEHAVIOURAL, "LR_WINDOW": BEHAVIOURAL,
        "LR_VOL_REF": BEHAVIOURAL, "LR_DD_REF": BEHAVIOURAL,
        "LR_VOL_W": BEHAVIOURAL, "LR_DD_W": BEHAVIOURAL,
        "MIN_MONTHLY_TURNOVER": BEHAVIOURAL, "COST_ROUNDTRIP_PCT": BEHAVIOURAL,
        "RISK_FREE": BEHAVIOURAL, "N_BUCKETS": BEHAVIOURAL,
        "HORIZONS": BEHAVIOURAL, "MIN_NONOVERLAPPING": BEHAVIOURAL,
        "REGIME_TREND_PCT": BEHAVIOURAL, "REGIME_VOL_ANN": BEHAVIOURAL,
        "FACTORS": BEHAVIOURAL, "UNTESTABLE": METADATA,
    },
    "strategy_compare": {"COST_PER_UNIT_TURNOVER": BEHAVIOURAL},
    "market_validation": {
        "BUCKET_ORDER": BEHAVIOURAL,
        "MIN_INDEPENDENT_PER_STRATUM": BEHAVIOURAL,
        "MIN_SECTORS": BEHAVIOURAL, "MIN_CAP_BUCKETS": BEHAVIOURAL,
        "MIN_INDEPENDENT_TOTAL": BEHAVIOURAL, "MIN_DISTINCT_DATES": BEHAVIOURAL,
    },
    "prediction_tracker": {
        "BENCHMARK": BEHAVIOURAL, "MAX_CYCLE_AGE_DAYS": BEHAVIOURAL,
        "MIN_EFFECTIVE_N": BEHAVIOURAL, "IS_POSTGRES": ALIAS,
    },
    "security_identity": {
        "LINK_MAX_GAP_DAYS": BEHAVIOURAL, "LINK_MAX_OVERLAP_DAYS": BEHAVIOURAL,
    },
    "bhavcopy": {"ARCHIVE_STARTS": BEHAVIOURAL,
                 "IS_POSTGRES": ALIAS},
    "portfolio_fix": {
        "MAX_SINGLE": BEHAVIOURAL, "MAX_SECTOR": BEHAVIOURAL,
        "MIN_HOLDINGS": BEHAVIOURAL,
    },
    "portfolio_optimizer": {"RISK_FREE_RATE": BEHAVIOURAL},
    "risk_management": {"RISK_FREE": BEHAVIOURAL},
    "benchmark": {"BENCHMARK": BEHAVIOURAL, "BENCHMARK_NAME": METADATA},
    "universe_scan": {
        "PAUSE_BETWEEN": OPERATIONAL, "PAUSE_ON_ERROR": OPERATIONAL,
        "CYCLE_HOURS": OPERATIONAL, "MAX_WORKERS": OPERATIONAL,
        "MODEL_VERSION": METADATA, "SHUFFLE_SEED": ENVIRONMENT,
        "LARGE_CAP_RANK_MAX": BEHAVIOURAL, "MID_CAP_RANK_MAX": BEHAVIOURAL,
        "LARGE_CAP_MIN": BEHAVIOURAL, "MID_CAP_MIN": BEHAVIOURAL,
        "MIN_COMPLETE_FRACTION": ALIAS, "IS_POSTGRES": ALIAS,
    },
    "monte_carlo": {"RANDOM_SEED": ENVIRONMENT},
    "optimizer_stability": {"RANDOM_SEED": ENVIRONMENT,
                            "DEFAULT_TRIALS": BEHAVIOURAL},
    "overfitting": {"RANDOM_SEED": ENVIRONMENT, "EULER_GAMMA": BEHAVIOURAL},
    "factor_evidence": {
        "LOOKAHEAD_REASON": METADATA, "SENTIMENT_REASON": METADATA,
        "CANNOT_TEST": METADATA, "RECONSTRUCTIBLE_FROM_PRICES": METADATA,
        "PLAIN": METADATA,
    },
    "factor_strategies": {"CANNOT_BACKTEST": METADATA, "PLAIN": METADATA},
    "backtest_integrity": {"SAFE_VALIDATED": METADATA, "SAFE_RESEARCH": METADATA},
    "screener": {"DB_PATH": ENVIRONMENT},
    "scan_health": {"COMPLETE_FRACTION": ALIAS,
                    "STALL_MINUTES": OPERATIONAL},
    "fama_french": {"RISK_FREE_RATE": BEHAVIOURAL,
                    "NIFTY_TICKER": BEHAVIOURAL,
                    "DEFAULT_UNIVERSE": BEHAVIOURAL},
    "research": {"RISK_FREE_RATE": BEHAVIOURAL, "NIFTY_TICKER": BEHAVIOURAL},
}

SPEC_MAPPING = {
    ("alpha_v2", "WEIGHTS_V2"): ("factor_weights", None),
    ("alpha_model", "FACTOR_WEIGHTS"): ("v1_factor_weights", None),
    ("alpha_model", "SIGNAL_STRONG_BUY"): ("signal_thresholds.signal_strong_buy", None),
    ("alpha_model", "SIGNAL_BUY"): ("signal_thresholds.signal_buy", None),
    ("alpha_model", "SIGNAL_SELL"): ("signal_thresholds.signal_sell", None),
    ("alpha_model", "SIGNAL_STRONG_SELL"): ("signal_thresholds.signal_strong_sell", None),
    ("alpha_model", "SENTIMENT_HALF_LIFE_DAYS"):
        ("momentum_factor.sentiment_half_life_days", None),
    ("alpha_model", "TOP_PICKS_UNIVERSE"):
        ("momentum_factor.top_picks_universe_size", len),
    ("momentum_backtest", "MIN_HOLDINGS"): ("backtest.min_holdings", None),
    ("momentum_backtest", "DEFAULT_UNIVERSE"): ("backtest.default_universe_size", len),
    ("momentum_backtest", "BROAD_UNIVERSE"): ("backtest.broad_universe_size", len),
    ("bhavcopy", "ARCHIVE_STARTS"): ("backtest.archive_starts", None),
    ("strategy_compare", "COST_PER_UNIT_TURNOVER"):
        ("costs.round_trip_cost_per_unit_turnover", None),
    ("market_validation", "BUCKET_ORDER"): ("pit_validation.bucket_order", list),
    ("prediction_tracker", "BENCHMARK"): ("benchmark_and_tracking.tracker_index", None),
    ("prediction_tracker", "MAX_CYCLE_AGE_DAYS"):
        ("benchmark_and_tracking.max_cycle_age_days", None),
    ("prediction_tracker", "MIN_EFFECTIVE_N"):
        ("benchmark_and_tracking.min_effective_n", None),
    ("benchmark", "BENCHMARK"): ("benchmark_and_tracking.index", None),
    ("portfolio_optimizer", "RISK_FREE_RATE"):
        ("portfolio_construction.risk_free_rate", None),
    ("risk_management", "RISK_FREE"): ("shared_config.risk_free_rate", None),
    ("fama_french", "RISK_FREE_RATE"): ("shared_config.risk_free_rate", None),
    ("research", "RISK_FREE_RATE"): ("shared_config.risk_free_rate", None),
}
for name in ("MOMENTUM_LOOKBACK_DAYS", "MOMENTUM_SKIP_DAYS",
             "MOMENTUM_HISTORY_BUFFER_DAYS", "MOMENTUM_MIN_OBSERVATIONS",
             "MOMENTUM_MIN_RETURNS", "MOMENTUM_VOL_EPSILON",
             "MOMENTUM_TANH_DIVISOR", "MOMENTUM_CONFIDENCE_BASE",
             "MOMENTUM_CONFIDENCE_SPAN", "MOMENTUM_INTERP_STRONG",
             "MOMENTUM_INTERP_MILD"):
    SPEC_MAPPING[("alpha_model", name)] = (f"momentum_factor.{name.lower()}", None)
for name in ("GROWTH_REVENUE_DIVISOR", "GROWTH_EARNINGS_DIVISOR",
             "GROWTH_PART_WEIGHT", "GROWTH_CONFIDENCE_SCALE",
             "LOW_RISK_WINDOW_DAYS", "LOW_RISK_MIN_RETURNS", "LOW_RISK_VOL_REF",
             "LOW_RISK_DD_REF", "LOW_RISK_VOL_WEIGHT", "LOW_RISK_DD_WEIGHT",
             "LOW_RISK_CONFIDENCE_BASE", "LOW_RISK_CONFIDENCE_DIVISOR"):
    SPEC_MAPPING[("alpha_v2", name)] = (f"v2_factors.{name.lower()}", None)
for name in ("RISK_FREE_RATE", "TRADING_DAYS_PER_YEAR", "MONTHS_PER_YEAR",
             "COST_BROKERAGE_PCT", "COST_STT_PCT", "COST_STAMP_DUTY_PCT",
             "COST_EXCHANGE_PCT", "COST_GST_PCT", "BENCHMARK_INDEX"):
    SPEC_MAPPING[("model_config", name)] = (f"shared_config.{name.lower()}", None)
for name in ("COST_ROUNDTRIP_PCT", "LOOKBACK_MONTHS", "SKIP_MONTHS",
             "MIN_HOLDINGS", "MIN_MONTHLY_TURNOVER"):
    SPEC_MAPPING[("pit_backtest", name)] = (f"pit_backtest.{name.lower()}", None)
for name in ("MOM_LOOKBACK", "MOM_SKIP", "MOM_TANH_DIV", "LR_WINDOW",
             "LR_VOL_REF", "LR_DD_REF", "LR_VOL_W", "LR_DD_W",
             "MIN_MONTHLY_TURNOVER", "COST_ROUNDTRIP_PCT", "RISK_FREE",
             "N_BUCKETS", "MIN_NONOVERLAPPING", "REGIME_TREND_PCT",
             "REGIME_VOL_ANN"):
    SPEC_MAPPING[("pit_validation", name)] = (f"pit_validation.{name.lower()}", None)
SPEC_MAPPING[("model_config", "SCAN_COMPLETE_FRACTION")] = ("shared_config.scan_complete_fraction", None)
SPEC_MAPPING[("optimizer_stability", "DEFAULT_TRIALS")] = ("research_tools.stability_trials", None)
SPEC_MAPPING[("overfitting", "EULER_GAMMA")] = ("research_tools.euler_gamma", None)
SPEC_MAPPING[("fama_french", "DEFAULT_UNIVERSE")] = ("research_tools.fama_french_universe_size", len)
SPEC_MAPPING[("fama_french", "NIFTY_TICKER")] = ("shared_config.benchmark_index", None)
SPEC_MAPPING[("research", "NIFTY_TICKER")] = ("shared_config.benchmark_index", None)
SPEC_MAPPING[("benchmark", "BENCHMARK")] = ("shared_config.benchmark_index", None)
SPEC_MAPPING[("prediction_tracker", "BENCHMARK")] = ("shared_config.benchmark_index", None)
SPEC_MAPPING[("pit_validation", "HORIZONS")] = ("pit_validation.horizons", list)
SPEC_MAPPING[("pit_validation", "FACTORS")] = ("pit_validation.factors", list)
for name in ("MIN_INDEPENDENT_PER_STRATUM", "MIN_SECTORS", "MIN_CAP_BUCKETS",
             "MIN_INDEPENDENT_TOTAL", "MIN_DISTINCT_DATES"):
    SPEC_MAPPING[("market_validation", name)] = \
        (f"validation_thresholds.{name.lower()}", None)
for name in ("LINK_MAX_GAP_DAYS", "LINK_MAX_OVERLAP_DAYS"):
    SPEC_MAPPING[("security_identity", name)] = \
        (f"identity_resolution.{name.lower()}", None)
for name in ("MAX_SINGLE", "MAX_SECTOR", "MIN_HOLDINGS"):
    SPEC_MAPPING[("portfolio_fix", name)] = \
        (f"portfolio_construction.{name.lower()}", None)
for name in ("LARGE_CAP_RANK_MAX", "MID_CAP_RANK_MAX", "LARGE_CAP_MIN",
             "MID_CAP_MIN"):
    SPEC_MAPPING[("universe_scan", name)] = (f"universe_rules.{name.lower()}", None)


# ---------------------------------------------------------------- mechanisms
def constants_in_source(src):
    """
    Module-level constants, including forms a naive scan misses.

    Simple, tuple, list and annotated targets. The first version handled only
    simple targets and reported two tuple-assigned constants as deleted; a
    checker that cannot see a construct certifies it.
    """
    tree = ast.parse(src)
    found = {}

    def take(n, kind="assign", source=None):
        if n.isupper() and not n.startswith("_"):
            found[n] = {"kind": kind, "source": source}

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
        # An imported constant, with or without renaming. These were invisible
        # to the first version, which walked only assignments — so the moment a
        # duplicated constant was correctly consolidated into a shared module
        # and imported back under an alias, the auditor stopped seeing it. A
        # checker that goes blind precisely when the code improves is worse
        # than one that never looked.
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                name = a.asname or a.name
                take(name, kind="alias", source=f"{n.module}.{a.name}")
    return found


def module_constants(mod):
    p = os.path.join(MODDIR, mod + ".py")
    if not os.path.exists(p):
        return {}
    return constants_in_source(open(p, encoding="utf-8").read())


IGNORE_LITERALS = {0, 1, 2, 100, -1, 0.0, 1.0, 3, 4, 12, 252, 1000}


def scoring_literals_in_source(src, funcs):
    """Numeric literals in arithmetic or comparison inside named functions."""
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name in funcs):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, (ast.BinOp, ast.Compare)):
                for c in ast.walk(sub):
                    if (isinstance(c, ast.Constant)
                            and isinstance(c.value, (int, float))
                            and not isinstance(c.value, bool)
                            and c.value not in IGNORE_LITERALS):
                        out.append((node.name, c.lineno, c.value))
    return sorted(set(out))


CRITICAL_FUNCS = {
    "alpha_model": ["_compute_momentum_factor", "compute_alpha_score",
                    "signal_for_score"],
    "alpha_v2": ["_low_risk_factor", "_growth_factor", "compute_v2"],
}


def flatten(d, prefix="", into=None):
    into = {} if into is None else into
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and k not in ("factor_weights", "v1_factor_weights"):
            flatten(v, key + ".", into)
        else:
            into[key] = v
    return into


def at_path(node, path):
    for p in path.split("."):
        if not isinstance(node, dict) or p not in node:
            return ("__ABSENT__",)
        node = node[p]
    return node


def _norm(v):
    if isinstance(v, dict):
        return {str(k): _norm(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_norm(x) for x in v]
    if isinstance(v, float):
        return round(v, 9)
    return v


# ================================================================ SECTION 0
print("=" * 72)
print("SECTION 0 — audit the auditor")
print("=" * 72)
FIXTURE = textwrap.dedent('''
    SIMPLE = 5
    TUPLE_A, TUPLE_B = 1.5, 2.5
    [LIST_A, LIST_B] = [3, 4]
    ANNOTATED: int = 7
    ALIAS = SIMPLE
    NESTED = {"inner": {"deep": 9}}
    DERIVED = SIMPLE * 2
    _PRIVATE = 11
    lowercase = 13
    from math import pi as IMPORTED_PI

    def scorer(x):
        return x * 1.5 + 0.85 if x > 40 else x / 0.30
''')
found = constants_in_source(FIXTURE)
for name in ("SIMPLE", "TUPLE_A", "TUPLE_B", "LIST_A", "LIST_B", "ANNOTATED",
             "ALIAS", "NESTED", "DERIVED"):
    ok(name in found, f"detects {name}", gap=f"auditor blind to {name}")
ok("_PRIVATE" not in found, "ignores private names")
ok("lowercase" not in found, "ignores lowercase names")

ok("IMPORTED_PI" in found and found["IMPORTED_PI"]["kind"] == "alias",
   "detects an imported constant and marks it an alias",
   gap="auditor blind to imported constants")

lits = scoring_literals_in_source(FIXTURE, ["scorer"])
vals = {v for _, _, v in lits}
ok({1.5, 0.85, 40, 0.30} <= vals,
   f"detects inline scoring literals (found {sorted(vals)})",
   gap="auditor cannot see inline literals")

nested = flatten({"a": {"b": {"c": 1}}})
ok(nested.get("a.b.c") == 1, "flattens nested configuration")
ok(at_path({"a": {"b": 2}}, "a.b") == 2, "reads a value by path")
ok(at_path({"a": {}}, "a.missing") == ("__ABSENT__",), "reports an absent path")


# ================================================================ SECTION 1
print("\n" + "=" * 72)
print("SECTION 1 — is every constant classified?")
print("=" * 72)
unclassified, broken_alias = [], []
for mod, declared in INVENTORY.items():
    actual = module_constants(mod)
    for name, meta in actual.items():
        if name not in declared:
            unclassified.append(f"{mod}.{name} (NEW, unregistered)")
    for name in declared:
        if name not in actual:
            unclassified.append(f"{mod}.{name} (declared, no longer exists)")
    # An alias must actually equal what it aliases, or the consolidation that
    # created it is decorative.
    for name, kind in declared.items():
        if kind != ALIAS or name not in actual:
            continue
        src = (actual[name] or {}).get("source")
        try:
            here = getattr(__import__(mod), name)
            smod, sname = src.rsplit(".", 1)
            there = getattr(__import__(smod), sname)
            if here != there:
                broken_alias.append(f"{mod}.{name} != {src}")
        except Exception as _e:
            broken_alias.append(f"{mod}.{name} -> {src} unresolvable "
                                f"({type(_e).__name__})")
ok(not unclassified,
   f"every module-level constant is classified ({len(unclassified)} loose)",
   gap=("Unclassified/stale constants: " + ", ".join(unclassified))
       if unclassified else None)
for u in unclassified:
    print(f"         ! {u}")

ok(not broken_alias,
   f"every alias resolves to the constant it aliases ({len(broken_alias)} broken)",
   gap=("Aliases disagreeing with their source: " + ", ".join(broken_alias))
       if broken_alias else None)
for b in broken_alias:
    print(f"         ! {b}")

behavioural = {(m, n) for m, d in INVENTORY.items()
               for n, k in d.items() if k == BEHAVIOURAL}
counts = {k: sum(1 for d in INVENTORY.values() for v in d.values() if v == k)
          for k in (BEHAVIOURAL, METADATA, ENVIRONMENT, OPERATIONAL, ALIAS)}
print(f"\n  {sum(counts.values())} constants across {len(INVENTORY)} modules")
for k, v in counts.items():
    print(f"    {k:<12} {v}")


# ================================================================ SECTION 2
print("\n" + "=" * 72)
print("SECTION 2 — is every behavioural parameter in the spec?")
print("=" * 72)
spec = sv.current_spec()
flat = flatten(spec)

ok(not (spec.get("_capture_failures") or {}),
   "the live spec has no capture failures",
   gap=f"capture failures: {spec.get('_capture_failures')}")
ok(not any(k.endswith("_error") for k in spec),
   "no swallowed error marker stands in for a block",
   gap=f"error markers: {[k for k in spec if k.endswith('_error')]}")

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

ok(not wrong, f"every captured field matches its source module ({len(wrong)} wrong)",
   gap=("Spec disagreeing with source: "
        + "; ".join(f"{m}.{n}: {w}" for m, n, w in wrong)) if wrong else None)
for m, n, w in wrong:
    print(f"         ! {m}.{n} — {w}")
ok(not missing,
   f"every behavioural constant is captured ({len(covered)}/{len(behavioural)})",
   gap=("Behavioural constants absent from the freeze: "
        + ", ".join(f"{m}.{n}" for m, n, _ in missing)) if missing else None)
for m, n, why in missing:
    print(f"         ! {m}.{n} — {why}")


# ================================================================ SECTION 3
print("\n" + "=" * 72)
print("SECTION 3 — uncapturable literals inside scoring functions")
print("=" * 72)
inline = []
for mod, funcs in CRITICAL_FUNCS.items():
    p = os.path.join(MODDIR, mod + ".py")
    if os.path.exists(p):
        for fn, ln, v in scoring_literals_in_source(
                open(p, encoding="utf-8").read(), funcs):
            inline.append((mod, fn, ln, v))
ok(not inline,
   f"no uncapturable literals in scoring functions ({len(inline)} found)",
   gap=("Inline literals unreachable by any import: "
        + ", ".join(f"{m}.{f}:{ln}={v}" for m, f, ln, v in inline[:20]))
       if inline else None)
for m, f, ln, v in inline[:20]:
    print(f"         ! {m}.{f}  line {ln}  literal {v}")


# ================================================================ SECTION 4
print("\n" + "=" * 72)
print("SECTION 4 — does every captured field move the hash?")
print("=" * 72)
import copy  # noqa: E402
base_hash = sv._hash(spec)
inert = []
SENTINELS = {int: 987654, float: 9.87654, str: "__CHANGED__", bool: None,
             list: ["__CHANGED__"], dict: {"__CHANGED__": 1}}
for path in sorted(flat):
    if path.startswith(("environment", "captured_at", "_capture")):
        continue
    cur = at_path(spec, path)
    sent = SENTINELS.get(type(cur))
    if sent is None or sent == cur:
        continue
    s2 = copy.deepcopy(spec)
    node = s2
    parts = path.split(".")
    for p in parts[:-1]:
        node = node[p]
    node[parts[-1]] = sent
    if sv._hash(s2) == base_hash:
        inert.append(path)
print(f"  mutated {len([p for p in flat if not p.startswith(('environment','captured_at','_capture'))])} "
      f"captured fields")
ok(not inert, "every captured field changes the hash when altered",
   gap=f"fields in the spec that do not affect the hash: {inert}" if inert else None)


# ================================================================ SECTION 5
print("\n" + "=" * 72)
print("SECTION 5 — drift semantics: four distinct outcomes")
print("=" * 72)
_get, _cur = sv.get, sv.current_spec
frozen = copy.deepcopy(spec)
sv.get = lambda v: {"found": True, "version": v, "frozen_at": "x",
                    "spec": frozen, "spec_hash": sv._hash(frozen)}

cases = [
    ("A. behavioural value changed", "signal_thresholds", "signal_strong_buy", 25,
     lambda d: d["behavioural_drift"] and not d.get("environment_drift")),
    ("B. specification incomplete", None, None, None,
     lambda d: (not d["behavioural_drift"]) and d["coverage_gap"]),
    ("C. metadata changed", None, "factors_not_historically_testable", ["all"],
     lambda d: d["metadata_drift"] and not d["behavioural_drift"]),
    ("D. environment changed", "environment", "python_version", "0.0.0",
     lambda d: d.get("environment_drift") and not d["behavioural_drift"]),
]
for label, block, key, val, check in cases:
    m = copy.deepcopy(spec)
    if label.startswith("B"):
        m["a_field_v13_never_captured"] = 1
    elif block:
        m[block] = dict(m[block]); m[block][key] = val
    else:
        m[key] = val
    sv.current_spec = lambda mm=m: mm
    d = sv.drift("v1.3")
    ok(check(d), f"{label} -> classified correctly")

sv.current_spec = lambda: copy.deepcopy(spec)
ok(not sv.drift("v1.3")["drifted"], "an unchanged configuration reports no drift")
sv.get, sv.current_spec = _get, _cur


# ================================================================ SECTION 6
print("\n" + "=" * 72)
print("SECTION 6 — environment and reproducibility")
print("=" * 72)
env = spec.get("environment") or {}
required = ("python_version", "numpy_version", "pandas_version", "scipy_version",
            "code_commit", "archive", "random_seeds")
env_missing = [k for k in required if env.get(k) in (None, {})]
ok(not env_missing, f"the spec records its environment ({len(env_missing)} missing)",
   gap=f"environment fields absent or null: {', '.join(env_missing)}"
       if env_missing else None)
for k in required:
    print(f"    {k:<18} {str(env.get(k))[:60]}")

# Randomness: the question is whether a seed exists and is recorded, not
# whether randomness exists. The earlier version flagged its presence, which
# reported sampling methods as defects.
unseeded = []
for mod in ("monte_carlo", "optimizer_stability", "overfitting"):
    seed = (env.get("random_seeds") or {}).get(mod)
    if seed is None:
        unseeded.append(mod)
try:
    import inspect
    import monte_carlo
    if inspect.signature(monte_carlo.simulate).parameters["seed"].default is None:
        unseeded.append("monte_carlo.simulate default seed is None")
except Exception:
    pass
ok(not unseeded, f"every research randomness source is seeded and recorded",
   gap=f"randomness without a recorded seed: {', '.join(unseeded)}"
       if unseeded else None)


# ================================================================ result
print("\n" + "=" * 72)
print(f"RESULT: {len(PASS)} checks passed, {len(FAIL)} gaps")
print("=" * 72)
if GAPS:
    print("\nGAPS — the specification is NOT certified complete:\n")
    for i, g in enumerate(GAPS, 1):
        print(f"  {i}. {g}\n")
else:
    print(f"\nCERTIFIED: {len(covered)}/{len(behavioural)} behavioural parameters "
          f"captured, every one matching its source and affecting the hash.")
    print("No uncapturable literals. Environment and seeds recorded. Drift "
          "distinguishes behaviour, coverage, metadata and environment.\n")
sys.exit(1 if FAIL else 0)
