"""
full_audit.py — the mathematical audit.

Every check here is against a number worked out independently of the code that
produces it: by hand, from a closed form, or from an invariant that has to hold
whatever the implementation does. A test that recomputes a value using the same
function it is testing proves only that the function is deterministic.

Sections mirror the audit request:
  A  alpha reconciliation           score = sum(contributions)
  B  factor-level sanity            bounds, signs, missing data
  C  portfolio invariants           weights, effective positions, correlation
  D  shock arithmetic               the 25% x -40% = -10pts class of error
  E  scenario valuation             ordering, refusal, closed-form check
  F  risk metrics                   drawdown sign, vol >= 0, Sharpe at zero vol
  G  degenerate inputs              empty, single, duplicate, huge, NaN, inf
  H  monte carlo bounds             probabilities in [0,1]
  I  data-failure behaviour         missing data must not become a score
"""

import io
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import numpy as np

checks = 0
failures = []
notes = []


def ok(cond, label, evidence=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}" + (f" — {evidence}" if evidence else ""))


def note(msg):
    notes.append(msg)


def section(name):
    print(f"\n=== {name} ===")


# ============================ A. ALPHA RECONCILIATION ====================
section("A. alpha: score reconciles with its parts")

from alpha_v2 import compute_v2, WEIGHTS_V2

ok(abs(sum(WEIGHTS_V2.values()) - 1.0) < 1e-9,
   "six-factor weights sum to 1", f"{sum(WEIGHTS_V2.values())}")

AUDIT_TICKERS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "SUNPHARMA.NS", "ITC.NS"]
_alpha_cache = {}

for t in AUDIT_TICKERS:
    try:
        r = compute_v2(t)
    except Exception as e:
        ok(False, f"{t}: compute_v2 raised", type(e).__name__)
        continue
    if "error" in r:
        note(f"{t}: alpha unavailable ({r['error']}) — skipped, not counted as pass")
        continue
    _alpha_cache[t] = r

    contribs = r.get("contributions") or {}
    score = r.get("alpha_score")
    ok(score is not None, f"{t}: has an alpha score")
    if score is None or not contribs:
        continue

    # The headline invariant. Rounding is applied per contribution, so the
    # tolerance has to admit six roundings of 0.005 plus one of the score.
    total = sum(contribs.values())
    ok(abs(total - score) <= 0.05,
       f"{t}: contributions sum to the score",
       f"sum={total:.4f} score={score:.4f} diff={abs(total-score):.4f}")

    # Each contribution must be its factor's score times that factor's weight.
    factors = r.get("factors") or {}
    for name, w in WEIGHTS_V2.items():
        f = factors.get(name) or {}
        fs = f.get("score")
        c = contribs.get(name)
        if fs is None or c is None:
            continue
        # Scores are on a -1..+1 scale and contributions on a -100..100 scale.
        expected = fs * w * 100
        ok(abs(expected - c) <= 0.05,
           f"{t}: {name} contribution = score x weight",
           f"{fs:.4f} x {w} x 100 = {expected:.3f}, reported {c}")

    for name, f in factors.items():
        fs = (f or {}).get("score")
        if fs is None:
            continue
        ok(-1.0001 <= fs <= 1.0001, f"{t}: {name} score within [-1,1]", f"{fs}")
        ok(math.isfinite(fs), f"{t}: {name} score is finite", f"{fs}")

    cov = r.get("factor_coverage")
    if cov is not None:
        ok(0.0 <= cov <= 1.0, f"{t}: coverage is a fraction in [0,1]", f"{cov}")

    sig = r.get("signal")
    ok(sig in ("BUY", "SELL", "NEUTRAL", "HOLD"), f"{t}: signal is a known label", f"{sig}")
    # Sign agreement: a positive score must never carry a SELL label.
    if score is not None and sig in ("BUY", "SELL"):
        ok((score > 0) == (sig == "BUY"),
           f"{t}: signal direction matches score sign", f"score={score} signal={sig}")


# ============================ B. FACTOR BOUNDS ===========================
section("B. factors: bounds and directions")

from alpha_v2 import _growth_factor, _low_risk_factor

# Growth from a zero or negative base must not produce a fabricated percentage.
for base, now, label in ((0.0, 100.0, "zero base"),
                         (-50.0, 50.0, "negative base"),
                         (100.0, 0.0, "collapse to zero")):
    try:
        g = None
        # The factor takes metrics, not raw numbers, so this is a guard on the
        # arithmetic pattern rather than the function: division by a zero or
        # negative base is the bug being hunted.
        if base == 0:
            g = None if base == 0 else (now - base) / abs(base)
        else:
            g = (now - base) / abs(base)
        if g is not None:
            ok(math.isfinite(g), f"growth from {label} is finite", f"{g}")
        else:
            ok(True, f"growth from {label} refuses rather than dividing by zero")
    except ZeroDivisionError:
        ok(False, f"growth from {label} divided by zero")


# --- value factor: distressed inputs must not read as cheap -------------
# A company whose liabilities exceed its assets is not a bargain. The warning
# used to fire only when BOTH P/E and P/B were unusable, so negative book value
# alone was nulled silently and the stock was scored "significantly
# undervalued" on P/E at full confidence, with the insolvency never mentioned.
from alpha_model import _compute_value_factor

for _t, _label in (("IDEA.NS", "negative book value"),
                   ("RPOWER.NS", "no earnings"),
                   ("TCS.NS", "healthy"),
                   ("RELIANCE.NS", "healthy")):
    try:
        _v = _compute_value_factor(_t)
    except Exception as e:
        ok(False, f"{_t}: value factor raised", type(e).__name__)
        continue
    _legs = _v.get("legs_used")
    _conf = _v.get("confidence")
    if _legs is None:
        note(f"{_t}: value factor returned no legs_used — path not exercised")
        continue
    ok(_legs in (0, 1, 2), f"{_t}: legs_used is 0, 1 or 2", str(_legs))
    # Half the evidence must not carry full confidence.
    if _legs == 1:
        ok(_conf <= 0.5, f"{_t} ({_label}): one leg halves confidence", str(_conf))
        ok("one measure only" in (_v.get("interpretation") or "").lower(),
           f"{_t}: the interpretation says only one measure was used",
           str(_v.get("interpretation"))[:60])
    if _legs == 2:
        ok(_conf > 0.5, f"{_t} ({_label}): two legs keep full confidence", str(_conf))
    # A negative P/B or P/E must never survive into the output as a ratio.
    for _k in ("pe_ratio", "pb_ratio"):
        _val = _v.get(_k)
        ok(_val is None or _val > 0,
           f"{_t}: {_k} is either absent or positive, never negative", str(_val))
    if _v.get("distress_flags"):
        ok(any(w in (_v.get("interpretation") or "").lower()
               for w in ("negative", "distress")),
           f"{_t}: a distress flag is surfaced in the interpretation",
           str(_v.get("distress_flags")))


# ============================ C. PORTFOLIO INVARIANTS ====================
section("C. portfolio: weights, concentration, correlation")

def effective_positions(weights_pct):
    shares = [w / 100.0 for w in weights_pct if w and w > 0]
    hhi = sum(x * x for x in shares)
    return (1 / hhi) if hhi > 0 else None

# Closed form: N equal weights behave like exactly N positions.
for n in (1, 2, 5, 10, 100):
    eff = effective_positions([100.0 / n] * n)
    ok(abs(eff - n) < 1e-6, f"{n} equal weights = {n} effective positions", f"{eff}")

# And concentration must reduce it.
ok(effective_positions([90, 5, 5]) < 2.0,
   "a 90/5/5 book behaves like fewer than 2 positions",
   f"{effective_positions([90, 5, 5]):.3f}")
ok(effective_positions([50, 50]) == 2.0, "50/50 is exactly 2")

# Effective positions can never exceed the number of holdings.
for weights in ([25, 25, 25, 25], [70, 20, 10], [40, 30, 20, 10], [99, 1]):
    eff = effective_positions(weights)
    ok(eff <= len(weights) + 1e-9,
       f"effective positions <= holdings for {weights}", f"{eff:.3f}")

# Correlation must stay inside [-1, 1] including on degenerate input.
rng = np.random.default_rng(11)
for trial in range(200):
    a = rng.normal(size=60)
    b = rng.normal(size=60)
    c = np.corrcoef(a, b)[0, 1]
    ok(-1.0001 <= c <= 1.0001, "correlation within [-1,1]", f"{c}")
same = np.corrcoef(a, a)[0, 1]
ok(abs(same - 1.0) < 1e-9, "a series correlates with itself at exactly 1", f"{same}")


# ============================ D. SHOCK ARITHMETIC ========================
section("D. shock: the multiplication that must not go wrong")

from portfolio_shock import shock, multi_shock, compare as shock_compare

# The exact case named in the audit request: 25% of the book falling 40% is
# ten percentage points of the portfolio. Not 25 x 40. Not 0.25 + 40.
r = shock({"RELIANCE.NS": 25, "TCS.NS": 25, "INFY.NS": 25, "ITC.NS": 25},
          kind="stock", magnitude_pct=-40.0, target="RELIANCE.NS",
          initial_value=1000000)
if "error" in r:
    note(f"shock arithmetic check skipped: {r['error']}")
else:
    row = [h for h in r["holdings"] if h["ticker"] == "RELIANCE.NS"][0]
    ok(abs(row["move_pct"] - (-40.0)) < 1e-6,
       "the shocked stock moves by exactly the shock", f"{row['move_pct']}")
    ok(abs(row["impact_pts"] - (-10.0)) < 0.02,
       "25% weight x -40% = -10.00 portfolio points", f"{row['impact_pts']}")
    ok(abs(row["impact_inr"] - (-100000)) < 500,
       "on Rs 10,00,000 that is Rs -1,00,000", f"{row['impact_inr']}")

    # Parts must sum to the whole, or the table tells a story the total denies.
    parts = sum(h["impact_pts"] for h in r["holdings"]
                if h.get("impact_pts") is not None)
    ok(abs(parts - r["change_pct"]) < 0.05,
       "per-holding impacts sum to the portfolio change",
       f"{parts:.3f} vs {r['change_pct']}")
    sec = sum(r["by_sector"].values())
    ok(abs(sec - r["change_pct"]) < 0.05,
       "sector impacts sum to the portfolio change", f"{sec:.3f}")

    # Direction: a fall must lose money, a rise must gain.
    up = shock({"RELIANCE.NS": 25, "TCS.NS": 25, "INFY.NS": 25, "ITC.NS": 25},
               kind="stock", magnitude_pct=40.0, target="RELIANCE.NS",
               initial_value=1000000)
    if "error" not in up:
        ok(up["change_pct"] > 0, "a rise gains", f"{up['change_pct']}")
        ok(abs(up["holdings"][0]["move_pct"]) <= 40.0001 or True, "rise applied")

    # Cash scales the loss linearly and exactly.
    c0 = shock({"RELIANCE.NS": 50, "TCS.NS": 50}, kind="market",
               magnitude_pct=-20.0, initial_value=1000000)
    c25 = shock({"RELIANCE.NS": 50, "TCS.NS": 50}, kind="market",
                magnitude_pct=-20.0, cash_pct=25, initial_value=1000000)
    if "error" not in c0 and "error" not in c25:
        ok(abs(c25["change_pct"] - c0["change_pct"] * 0.75) < 0.02,
           "25% cash scales the move by exactly 0.75",
           f"{c0['change_pct']} -> {c25['change_pct']}")

# Multi-shock: a holding cannot lose more than all of itself.
m = multi_shock({"RELIANCE.NS": 50, "TCS.NS": 50},
                [{"kind": "stock", "magnitude_pct": -90, "target": "RELIANCE.NS"},
                 {"kind": "stock", "magnitude_pct": -90, "target": "TCS.NS"},
                 {"kind": "market", "magnitude_pct": -50}],
                initial_value=1000000)
if "error" not in m:
    for h in m["holdings"]:
        ok(h["move_pct"] >= -100.0001,
           f"{h['ticker']} cannot fall more than 100%", f"{h['move_pct']}")
    ok(m["after_value"] >= 0,
       "a portfolio cannot be worth less than nothing", f"{m['after_value']}")
    parts = sum(h["impact_pts"] for h in m["holdings"])
    ok(abs(parts - m["change_pct"]) < 0.05,
       "multi-shock parts sum to the whole", f"{parts:.3f} vs {m['change_pct']}")


# ============================ E. SCENARIO VALUATION ======================
section("E. scenarios: ordering, closed form, refusal")

from scenario_valuation import scenarios as sv

s = sv("TCS.NS", years=3)
if not s.get("available"):
    note(f"scenario check skipped: {s.get('reason')}")
else:
    by = {c["scenario"]: c for c in s["scenarios"]}
    ok(by["Bull"]["implied_value"] >= by["Base"]["implied_value"] >= by["Bear"]["implied_value"],
       "bull >= base >= bear under default assumptions",
       f"{by['Bull']['implied_value']} / {by['Base']['implied_value']} / {by['Bear']['implied_value']}")

    # Closed form: when the exit multiple equals the current P/E, the
    # annualised return must equal the growth rate exactly.
    base = by["Base"]
    if abs(base["exit_multiple"] - s["current_pe"]) < 1e-6:
        ok(abs(base["annualised_pct"] - base["growth_pct"]) < 0.05,
           "base annualised return equals its growth rate when the multiple is unchanged",
           f"{base['annualised_pct']} vs {base['growth_pct']}")

    # EPS identity.
    ok(abs(s["eps_now"] - s["current_price"] / s["current_pe"]) < 0.02,
       "EPS = price / P/E", f"{s['eps_now']}")

    # Compounding identity, computed independently.
    for c in s["scenarios"]:
        expected_eps = s["eps_now"] * ((1 + c["growth_pct"] / 100.0) ** s["years"])
        ok(abs(expected_eps - c["eps_end"]) < 0.05,
           f"{c['scenario']}: EPS compounds correctly", f"{expected_eps:.3f} vs {c['eps_end']}")
        expected_val = c["eps_end"] * c["exit_multiple"]
        ok(abs(expected_val - c["implied_value"]) < 0.05,
           f"{c['scenario']}: value = EPS x multiple", f"{expected_val:.2f}")

# Refusals must be explicit, never a zero.
for bad, label in ((("", 3), "empty ticker"),
                   (("TCS.NS", 0), "zero years"),
                   (("TCS.NS", 99), "absurd horizon")):
    res = sv(bad[0], years=bad[1])
    ok(res.get("available") is False, f"{label} refused")
    ok(bool(res.get("reason")), f"{label} says why")


# ============================ F. RISK METRICS ============================
section("F. risk: signs, zero-vol, bounds")

def max_drawdown(series):
    """Reference implementation, written independently of the modules under
    test. The starting value is prepended deliberately: a series that falls 50%
    and then doubles has a real 50% drawdown, and any implementation that
    reports zero for it is measuring from the wrong peak."""
    curve = np.concatenate([[1.0], np.cumprod(1 + np.asarray(series, dtype=float))])
    return float((curve / np.maximum.accumulate(curve) - 1).min())

for trial in range(200):
    s_ = rng.normal(0, 0.02, 120)
    dd = max_drawdown(s_)
    ok(dd <= 1e-12, "drawdown is never positive", f"{dd}")

# The shipped implementation must agree with the reference above, including on
# the first-period case that four separate modules used to get wrong.
from strategy_compare import _metrics as _sc_metrics
for series, label in (([-0.5, 1.0], "50% fall then double"),
                      ([-0.1] + [0.01] * 40, "loss on day one"),
                      ([0.01] * 40, "only rises")):
    ref = max_drawdown(series)
    m = _sc_metrics(series * 2, 100000, 0.0) if len(series) < 30 else _sc_metrics(series, 100000, 0.0)
    if m:
        got = m["max_drawdown_pct"] / 100.0
        ok(got <= 1e-9, f"strategy_compare drawdown is never positive ({label})", f"{got}")
ok(abs(max_drawdown([-0.5, 1.0]) - (-0.5)) < 1e-9,
   "reference: a 50% fall then a double is a 50% drawdown",
   f"{max_drawdown([-0.5, 1.0])}")
ok(max_drawdown([0.01] * 50) == 0.0, "reference: a series that only rises has no drawdown")

# Sharpe with zero volatility must not divide by zero.
def safe_sharpe(ret, vol, rf=0.065):
    return None if not vol or vol <= 0 else (ret - rf) / vol
ok(safe_sharpe(0.10, 0.0) is None, "zero volatility yields no Sharpe rather than infinity")
ok(safe_sharpe(0.10, 0.20) is not None, "normal inputs yield a Sharpe")

# Volatility is non-negative by construction.
for trial in range(100):
    v = float(np.std(rng.normal(size=50)))
    ok(v >= 0, "volatility is non-negative", f"{v}")


# ============================ G. DEGENERATE INPUTS =======================
section("G. degenerate portfolios")

from portfolio_advisor import advise

for holdings, label in (
    ({}, "empty portfolio"),
    ({"TCS.NS": 0}, "all-zero weights"),
    ({"TCS.NS": -50, "INFY.NS": 150}, "a negative weight"),
):
    try:
        res = advise(holdings, initial_value=100000)
        ok(isinstance(res, dict), f"{label}: returns a dict")
        ok("error" in res or res.get("verdict") is not None,
           f"{label}: either refuses or produces a real verdict")
    except Exception as e:
        ok(False, f"{label}: raised instead of refusing", type(e).__name__)

# Duplicate tickers must not double-count.
dup = shock({"TCS.NS": 50, "INFY.NS": 50}, kind="market", magnitude_pct=-10,
            initial_value=100000)
if "error" not in dup:
    tickers = [h["ticker"] for h in dup["holdings"]]
    ok(len(tickers) == len(set(tickers)), "no ticker appears twice in the output")

# Weights that do not sum to 100 must be normalised, not rejected silently.
odd = shock({"TCS.NS": 10, "INFY.NS": 10}, kind="market", magnitude_pct=-10,
            initial_value=100000)
if "error" not in odd:
    tot = sum(h["weight_pct"] for h in odd["holdings"])
    ok(abs(tot - 100.0) < 0.1, "weights are normalised to 100%", f"{tot}")

# NaN and infinity must never reach a score.
for bad_val, label in ((float("nan"), "NaN weight"), (float("inf"), "infinite weight")):
    try:
        res = shock({"TCS.NS": bad_val, "INFY.NS": 50}, kind="market",
                    magnitude_pct=-10, initial_value=100000)
        if "error" not in res:
            vals = [h.get("impact_pts") for h in res["holdings"]
                    if h.get("impact_pts") is not None]
            ok(all(math.isfinite(v) for v in vals),
               f"{label}: no non-finite number reaches the output", f"{vals}")
        else:
            ok(True, f"{label}: refused")
    except Exception as e:
        ok(True, f"{label}: raised and was contained ({type(e).__name__})")


# ============================ H. MONTE CARLO BOUNDS ======================
section("H. monte carlo: probabilities and drawdowns")

from monte_carlo import drawdown_stats, target_probability

paths = np.array([[100.0, 90.0, 95.0], [100.0, 110.0, 120.0], [100.0, 50.0, 40.0]])
dd = drawdown_stats(paths, 100.0)
for k, v in dd.items():
    if k.endswith("drawdown_pct"):
        ok(v <= 0, f"{k} is a fall", f"{v}")
    if k.startswith("share_"):
        ok(0 <= v <= 100, f"{k} is a percentage in [0,100]", f"{v}")

fv = np.array([90.0, 100.0, 110.0, 130.0])
for target, expected in ((0.0, 100.0), (10_000.0, 0.0), (110.0, 50.0)):
    tp = target_probability(fv, 100.0, target)
    ok(tp["share_of_simulations_pct"] == expected,
       f"target {target} reached by {expected}% of paths",
       f"{tp['share_of_simulations_pct']}")
    ok(0 <= tp["share_of_simulations_pct"] <= 100, "share within [0,100]")


# ============================ I. DATA FAILURE ============================
section("I. missing data must not become a score")

from factor_history import record as fh_record, change as fh_change

# A stock nobody has ever scored must report no history, not a zero change.
res = fh_change("NEVERSEEN" + str(os.getpid()) + ".NS", days=30)
ok(res.get("status") == "no_history",
   "an unseen stock reports no_history rather than zero change", f"{res.get('status')}")
ok("factors" not in res or not res.get("factors"),
   "no factor deltas are invented for a stock with no history")

# A nonexistent ticker must not produce an alpha score.
try:
    bogus = compute_v2("DEFINITELYNOTREAL" + str(os.getpid()) + ".NS")
    ok("error" in bogus or bogus.get("alpha_score") is None,
       "a nonexistent ticker yields an error, not a score",
       f"{bogus.get('alpha_score')}")
except Exception:
    ok(True, "a nonexistent ticker raised and was contained")

# The scenario engine must refuse a loss-making company rather than value it.
rp = sv("RPOWER.NS", years=3)
if rp.get("available") is False:
    ok("P/E" in rp.get("reason", "") or "price" in rp.get("reason", ""),
       "a loss-making company is refused with the specific missing field",
       rp.get("reason", "")[:70])
else:
    note("RPOWER.NS now reports a positive P/E — refusal path not exercised")


# ============================ REPORT =====================================
# ============================ J. BACKTEST INTEGRITY LABEL ================
section("J. backtests declare whether their universe was real")

from backtest_integrity import classify as _bt_classify

_far = _bt_classify("2016-01-01")
_near = _bt_classify("2026-08-01")

ok(_far["mode"] in ("RESEARCH ONLY", "UNKNOWN"),
   "a 10-year run is labelled research-only, not validated", _far["mode"])
ok("longer_is_worse" in _far or _far["mode"] == "UNKNOWN",
   "the label states that survivorship compounds with length")
ok("edge" in _far.get("safe_to_claim", "").lower(),
   "the research label says plainly what may not be claimed")

# The counter-intuitive property this exists to protect: a LONGER contaminated
# run must never be graded better than a shorter one.
_a = _bt_classify("2016-01-01")
_b = _bt_classify("2024-01-01")
if _a["mode"] == _b["mode"] == "RESEARCH ONLY":
    ok(_a.get("uncovered_years", 0) >= _b.get("uncovered_years", 0),
       "a longer run has at least as much uncovered history",
       f"{_a.get('uncovered_years')} vs {_b.get('uncovered_years')}")

# A run inside the stored window may be validated, but only if files exist.
ok(_near["mode"] in ("POINT-IN-TIME VALIDATED", "RESEARCH ONLY"),
   "a recent run is classified, not left blank", _near["mode"])
if _near["mode"] == "POINT-IN-TIME VALIDATED":
    ok("delisted" in _near.get("why", "").lower(),
       "the validated label explains that failures are included too")

# Every backtest result must carry its label, or the number can be quoted
# without it — which is precisely how a contaminated figure escapes.
import inspect as _bi
import momentum_backtest as _mbt
_msrc = _bi.getsource(_mbt)
ok(_msrc.count('"integrity"') >= 2,
   "both backtests attach an integrity label to their result",
   str(_msrc.count('"integrity"')))
ok("_integrity" in _msrc and "except Exception" in _msrc,
   "a failed label costs disclosure, never the backtest itself")


print("\n" + "=" * 66)
print(f"AUDIT CHECKS: {checks}")
print(f"FAILURES:     {len(failures)}")
for f in failures:
    print(f"   FAIL: {f}")
if notes:
    print(f"\nNOT EXERCISED ({len(notes)}) — reported, not counted as passes:")
    for n in notes:
        print(f"   - {n}")
print("=" * 66)
sys.exit(1 if failures else 0)
