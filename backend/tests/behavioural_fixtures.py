"""
behavioural_fixtures.py — record what the model does, so a refactor can prove
it changed nothing.

Promoting an inline literal to a named constant is supposed to be invisible.
"Supposed to be" is not evidence, and a typo in a divisor would be invisible in
review and obvious only in a backtest three weeks later. So the outputs are
recorded first, against the code as it stands, and compared afterwards.

Two independent proofs, because each catches what the other cannot:

  VALUES   — the promoted constants are read out of the pre-refactor source by
             walking its syntax tree, and must equal the new named constants
             exactly. This cannot be fooled by a mocking mistake.

  OUTPUTS  — the factor functions are run on synthetic price series with the
             data layer stubbed, and every returned number must match to the
             bit. This cannot be fooled by promoting a constant correctly and
             then using it in the wrong place.

Run with --record against the pre-refactor code to write the baseline. Run with
no argument afterwards to check against it.
"""

import json
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
BASELINE = os.path.join(HERE, "fixtures", "behavioural_baseline.json")
SNAPSHOT = os.path.join(HERE, "fixtures", "pre_refactor")


# --------------------------------------------------------------- synthetic data
def price_series(kind, n=320, seed=0):
    """Deterministic price paths. No randomness that is not seeded here."""
    rng = np.random.default_rng(seed)
    if kind == "flat":
        vals = np.full(n, 100.0)
    elif kind == "steady_up":
        vals = 100.0 * np.cumprod(np.full(n, 1.002))
    elif kind == "steady_down":
        vals = 100.0 * np.cumprod(np.full(n, 0.998))
    elif kind == "volatile_up":
        vals = 100.0 * np.cumprod(1 + rng.normal(0.0015, 0.030, n))
    elif kind == "volatile_down":
        vals = 100.0 * np.cumprod(1 + rng.normal(-0.0015, 0.030, n))
    elif kind == "calm":
        vals = 100.0 * np.cumprod(1 + rng.normal(0.0003, 0.004, n))
    elif kind == "crash":
        vals = 100.0 * np.cumprod(np.full(n, 1.001))
        vals[n // 2:] *= 0.55
    elif kind == "spike":
        vals = 100.0 * np.cumprod(np.full(n, 1.0005))
        vals[n // 2:] *= 1.8
    elif kind == "short":
        vals = 100.0 * np.cumprod(np.full(40, 1.001))
    else:
        raise ValueError(kind)
    idx = pd.bdate_range("2024-01-01", periods=len(vals))
    return pd.DataFrame({"Close": vals}, index=idx)


CASES = ["flat", "steady_up", "steady_down", "volatile_up", "volatile_down",
         "calm", "crash", "spike", "short"]


def _stub_yf(module, kind):
    """
    Replace the download with a fixed series, so the factor is a function of its
    arithmetic and nothing else.

    Both binding styles have to be covered: alpha_model imports yfinance at
    module level, so the module attribute is what it resolves; alpha_v2 imports
    it inside the function, so only sys.modules will do. Patching one and
    assuming the other let real network calls through on the first run.
    """
    import types
    df = price_series(kind)
    stub = types.ModuleType("yfinance")
    stub.download = lambda *a, **k: df
    sys.modules["yfinance"] = stub
    module.yf = stub
    return stub


def _stub_growth_source(rev, earn):
    """data_fetcher.get_info is imported inside _growth_factor."""
    import data_fetcher
    data_fetcher.get_info = lambda t: {"revenueGrowth": rev,
                                       "earningsGrowth": earn}


# --------------------------------------------------------------- collection
def collect(alpha_model, alpha_v2):
    out = {"momentum": {}, "low_risk": {}, "growth": {}, "signal": {}}

    real_yf_m = getattr(alpha_model, "yf", None)
    real_yf_v = getattr(alpha_v2, "yf", None)
    try:
        for kind in CASES:
            _stub_yf(alpha_model, kind)
            r = alpha_model._compute_momentum_factor("TEST.NS")
            out["momentum"][kind] = {k: v for k, v in r.items()
                                     if isinstance(v, (int, float))}

            _stub_yf(alpha_v2, kind)
            r2 = alpha_v2._low_risk_factor("TEST.NS")
            out["low_risk"][kind] = {k: v for k, v in r2.items()
                                     if isinstance(v, (int, float))}
    finally:
        if real_yf_m is not None:
            alpha_model.yf = real_yf_m
        if real_yf_v is not None:
            alpha_v2.yf = real_yf_v

    # Growth is a pure function of two reported numbers once its source is fixed.
    import data_fetcher
    real_get_info = getattr(data_fetcher, "get_info", None)
    try:
        for rev in (-0.5, -0.1, 0.0, 0.05, 0.15, 0.30, 0.60, 1.5, None):
            for earn in (-0.5, -0.1, 0.0, 0.05, 0.20, 0.50, 1.2, None):
                _stub_growth_source(rev, earn)
                g = alpha_v2._growth_factor("TEST.NS")
                out["growth"][f"{rev}|{earn}"] = {
                    k: v for k, v in g.items() if isinstance(v, (int, float))}
    finally:
        if real_get_info is not None:
            data_fetcher.get_info = real_get_info

    # Signal thresholds across a fine grid, including every boundary.
    for s in [x / 2 for x in range(-120, 121)] + [40, 15, -15, -40,
                                                  40.0001, 39.9999,
                                                  15.0001, 14.9999,
                                                  -15.0001, -14.9999,
                                                  -40.0001, -39.9999]:
        out["signal"][repr(float(s))] = _signal_of(alpha_model, float(s))
    return out


def _signal_of(alpha_model, score):
    """
    The signal for a given alpha score.

    Before the refactor there is no function to call — the thresholds are
    inline in compute_alpha_score — so the pre-refactor baseline reads them out
    of the snapshot's syntax tree rather than transcribing them by hand, which
    would be the one place a typo could silently redefine the baseline.
    """
    fn = getattr(alpha_model, "signal_for_score", None)
    if fn is not None:
        return fn(score)
    thr = _thresholds_from_source(
        os.path.join(SNAPSHOT, "alpha_model.py"))
    if score > thr["strong_buy"]:
        return "STRONG BUY"
    if score > thr["buy"]:
        return "BUY"
    if score < thr["strong_sell"]:
        return "STRONG SELL"
    if score < thr["sell"]:
        return "SELL"
    return "NEUTRAL"


def _thresholds_from_source(path):
    """
    Extract the four signal cut-points from a source file by AST.

    literal_eval, not isinstance(Constant): -40 parses as UnaryOp(USub,
    Constant(40)), so requiring a Constant silently found the two positive
    thresholds and missed both negative ones. A baseline built from half the
    thresholds would have looked fine and proved nothing about SELL.
    """
    import ast
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef)
                and node.name == "compute_alpha_score"):
            continue
        found = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.If) and isinstance(sub.test, ast.Compare):
                c = sub.test
                if isinstance(c.left, ast.Name) and c.left.id == "alpha_score":
                    try:
                        val = ast.literal_eval(c.comparators[0])
                    except Exception:
                        continue
                    found.append((type(c.ops[0]).__name__, val))
        gts = sorted((v for o, v in found if o == "Gt"), reverse=True)
        lts = sorted(v for o, v in found if o == "Lt")
        if len(gts) >= 2 and len(lts) >= 2:
            return {"strong_buy": gts[0], "buy": gts[1],
                    "strong_sell": lts[0], "sell": lts[1]}
    raise RuntimeError(f"could not extract signal thresholds from {path}")


def _fn_source(path, name):
    import ast
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.unparse(node)
    raise RuntimeError(f"{name} not found in {path}")


def promoted_literals_from_snapshot():
    """
    The values the refactor must preserve, read out of the snapshot.

    Matched against the unparsed source of each function rather than by walking
    for a particular node shape. The shapes here are awkward — a divisor inside
    a tanh inside a call inside a comprehension — and a matcher tuned to one
    shape quietly returns nothing when the shape shifts, which is the failure
    mode that matters least visibly and most.
    """
    import re
    vals = {}
    p = os.path.join(SNAPSHOT, "alpha_model.py")
    vals.update({f"signal.{k}": v
                 for k, v in _thresholds_from_source(p).items()})

    mom = _fn_source(p, "_compute_momentum_factor")
    for key, pat in (("momentum.lookback", r"LOOKBACK\s*=\s*([0-9.]+)"),
                     ("momentum.skip", r"SKIP\s*=\s*([0-9.]+)"),
                     ("momentum.tanh_div", r"tanh\(risk_adj\s*/\s*([0-9.]+)\)"),
                     ("momentum.conf_base", r"round\(([0-9.]+)\s*\+\s*[0-9.]+\s*\*\s*history_frac"),
                     ("momentum.conf_span", r"round\([0-9.]+\s*\+\s*([0-9.]+)\s*\*\s*history_frac")):
        m = re.search(pat, mom)
        if m:
            vals[key] = float(m.group(1)) if "." in m.group(1) else int(m.group(1))

    v = os.path.join(SNAPSHOT, "alpha_v2.py")
    lr = _fn_source(v, "_low_risk_factor")
    for key, pat in (("low_risk.window_days", r"timedelta\(days=([0-9]+)\)"),
                     ("low_risk.vol_ref", r"tanh\(\(([0-9.]+)\s*-\s*ann_vol\)"),
                     ("low_risk.dd_ref", r"tanh\(\(([0-9.]+)\s*\+\s*drawdown\)"),
                     ("low_risk.vol_weight", r"([0-9.]+)\s*\*\s*vol_score"),
                     ("low_risk.dd_weight", r"([0-9.]+)\s*\*\s*dd_score"),
                     ("low_risk.min_returns", r"len\(rets\)\s*<\s*([0-9]+)")):
        m = re.search(pat, lr)
        if m:
            vals[key] = float(m.group(1)) if "." in m.group(1) else int(m.group(1))

    gr = _fn_source(v, "_growth_factor")
    for key, pat in (("growth.rev_div", r"float\(rev_g\)\s*/\s*([0-9.]+)"),
                     ("growth.earn_div", r"float\(earn_g\)\s*/\s*([0-9.]+)"),
                     ("growth.conf_scale", r"round\(([0-9.]+)\s*\*\s*wsum")):
        m = re.search(pat, gr)
        if m:
            vals[key] = float(m.group(1))
    return vals


# --------------------------------------------------------------- main
def main():
    record = "--record" in sys.argv
    import alpha_model
    import alpha_v2
    data = collect(alpha_model, alpha_v2)
    data["_promoted_literal_values"] = promoted_literals_from_snapshot()

    os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
    if record:
        with open(BASELINE, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        n = sum(len(v) for v in data.values() if isinstance(v, dict))
        print(f"recorded {n} baseline values -> {BASELINE}")
        print("  literals captured from the snapshot:")
        for k, v in sorted(data["_promoted_literal_values"].items()):
            print(f"    {k:<28} {v}")
        return 0

    if not os.path.exists(BASELINE):
        print("no baseline; run with --record first")
        return 2
    old = json.load(open(BASELINE))
    diffs = []

    for section in ("momentum", "low_risk", "growth", "signal"):
        o, n = old.get(section, {}), data.get(section, {})
        for k in sorted(set(o) | set(n)):
            if k not in o:
                diffs.append(f"{section}.{k}: NEW case appeared")
            elif k not in n:
                diffs.append(f"{section}.{k}: case disappeared")
            elif isinstance(o[k], dict):
                for f in sorted(set(o[k]) | set(n[k])):
                    a, b = o[k].get(f), n[k].get(f)
                    same = (a == b) or (isinstance(a, float) and isinstance(b, float)
                                        and math.isclose(a, b, rel_tol=0, abs_tol=0))
                    if not same:
                        diffs.append(f"{section}.{k}.{f}: {a!r} -> {b!r}")
            elif o[k] != n[k]:
                diffs.append(f"{section}.{k}: {o[k]!r} -> {n[k]!r}")

    # The promoted constants must equal the literals they replaced.
    print("\nPromoted constant values, snapshot vs live:")
    import alpha_model as am
    import alpha_v2 as av
    live = {
        "signal.strong_buy": getattr(am, "SIGNAL_STRONG_BUY", None),
        "signal.buy": getattr(am, "SIGNAL_BUY", None),
        "signal.sell": getattr(am, "SIGNAL_SELL", None),
        "signal.strong_sell": getattr(am, "SIGNAL_STRONG_SELL", None),
        "momentum.lookback": getattr(am, "MOMENTUM_LOOKBACK_DAYS", None),
        "momentum.skip": getattr(am, "MOMENTUM_SKIP_DAYS", None),
        "momentum.tanh_div": getattr(am, "MOMENTUM_TANH_DIVISOR", None),
        "low_risk.vol_ref": getattr(av, "LOW_RISK_VOL_REF", None),
        "low_risk.dd_ref": getattr(av, "LOW_RISK_DD_REF", None),
        "low_risk.window_days": getattr(av, "LOW_RISK_WINDOW_DAYS", None),
        "growth.rev_div": getattr(av, "GROWTH_REVENUE_DIVISOR", None),
        "growth.earn_div": getattr(av, "GROWTH_EARNINGS_DIVISOR", None),
    }
    snap = old.get("_promoted_literal_values", {})
    for k in sorted(live):
        want, got = snap.get(k), live[k]
        if want is None:
            print(f"    {k:<28} snapshot: (not extracted)  live: {got}")
            continue
        mark = "ok  " if want == got else "DIFF"
        print(f"    [{mark}] {k:<26} snapshot {want!r}  live {got!r}")
        if want != got:
            diffs.append(f"promoted constant {k}: was {want!r}, now {got!r}")

    # V2 carried its own inline copy of the signal thresholds and now shares
    # V1's. Equivalence is proved by reading what V2 USED to compare against,
    # out of the snapshot, and checking the shared function agrees with it on
    # every case — including the boundaries, where an accidental >= would show.
    try:
        import ast
        v2_src = _fn_source(os.path.join(SNAPSHOT, "alpha_v2.py"), "compute_v2")
        old_thr = []
        for node in ast.walk(ast.parse(v2_src)):
            if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
                c = node.test
                if isinstance(c.left, ast.Name) and c.left.id == "alpha":
                    old_thr.append((type(c.ops[0]).__name__,
                                    ast.literal_eval(c.comparators[0])))
        gts = sorted((v for o, v in old_thr if o == "Gt"), reverse=True)
        lts = sorted(v for o, v in old_thr if o == "Lt")

        def old_v2_signal(x):
            if x > gts[0]:
                return "STRONG BUY"
            if x > gts[1]:
                return "BUY"
            if x < lts[0]:
                return "STRONG SELL"
            if x < lts[1]:
                return "SELL"
            return "NEUTRAL"

        mismatch = [s for s in [x / 2 for x in range(-120, 121)]
                    + [40, 40.0001, 39.9999, 15, 15.0001, 14.9999,
                       -15, -15.0001, -14.9999, -40, -40.0001, -39.9999]
                    if old_v2_signal(float(s)) != am.signal_for_score(float(s))]
        print(f"V2 signal consolidation: old thresholds {gts + lts}, "
              f"{len(mismatch)} mismatch(es) across the grid")
        if mismatch:
            diffs.append(f"V2 signal differs from the shared function at "
                         f"{mismatch[:6]}")
    except Exception as e:
        diffs.append(f"could not verify the V2 signal consolidation: {e}")

    print()
    if diffs:
        print(f"BEHAVIOUR CHANGED — {len(diffs)} difference(s):")
        for d in diffs[:40]:
            print(f"   {d}")
        return 1
    checked = sum(len(v) for k, v in data.items()
                  if isinstance(v, dict) and not k.startswith("_"))
    print(f"IDENTICAL — {checked} fixture cases match the baseline exactly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
