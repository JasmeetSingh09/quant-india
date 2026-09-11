"""
lab_findings_test.py — Step 5 findings 3, 4 and 5.

  3. /optimizer/stability called an allocation "Stable" when its weights could
     not move: at a 40% cap, 40/0/40/20 has three weights on a limit and the
     fourth forced to the remainder, so perturbing expected returns moved
     nothing. That is the constraint talking, not the covariance.

  4. /portfolio/fit said a stock "overlaps with what you hold" when it had no
     price history, so no correlation was ever measured. The verdict bands
     describe co-movement; without a correlation they describe a guess.

  5. A negative holding was dropped by _norm and the result shown without a
     word, for a portfolio the user did not enter.

Each defect has a guard against the over-correction beside it: an allocation
whose weights are free to move and do not is still Stable; a priceable stock
still gets a normal fit verdict; a zero in an edit still removes a stock.

Offline: the optimiser, sector map, health score and simulator are stubbed, so
nothing leaves the machine and every number is fixed.
"""

import os
import sqlite3
import sys
import types

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "lab_findings_test.db")
fake_db = types.ModuleType("db")
fake_db.get_conn = lambda: sqlite3.connect(DB)
fake_db.IS_POSTGRES = False
sys.modules["db"] = fake_db

scan = types.ModuleType("universe_scan")
scan.top_by_tier = lambda n=25, min_confidence=0.4: {}
scan.get_signal_history = lambda t, limit=1: []
sys.modules["universe_scan"] = scan

# Returns for every stock except SMALL250, which has no price history at all.
_rng = np.random.default_rng(11)
_IDX = pd.bdate_range("2024-01-01", periods=300)
RETS = pd.DataFrame({t: _rng.normal(0.0004, 0.015, len(_IDX))
                     for t in ("RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS",
                               "SUNPHARMA.NS")}, index=_IDX)

opt = types.ModuleType("portfolio_optimizer")


def _get_returns(tickers, start, end):
    cols = [t for t in tickers if t in RETS.columns]
    return RETS[cols] if cols else pd.DataFrame()


PLAN = {"fn": None}


def mean_variance_optimize(tickers, target="max_sharpe", max_weight=1.0,
                           period_months=24, _mu_shift=None, **kw):
    return {"optimal_pct": PLAN["fn"](_mu_shift)}


opt._get_returns = _get_returns
opt.mean_variance_optimize = mean_variance_optimize
sys.modules["portfolio_optimizer"] = opt

SECTORS = {"RELIANCE.NS": "Energy", "TCS.NS": "IT", "HDFCBANK.NS": "Financials",
           "INFY.NS": "IT", "SUNPHARMA.NS": "Pharma"}
adv = types.ModuleType("portfolio_advisor")
adv._sector_of = lambda t: SECTORS.get(t)


def _sector_exposure(w):
    tot = sum(w.values()) or 1.0
    out = {}
    for t, v in w.items():
        if SECTORS.get(t):
            out[SECTORS[t]] = out.get(SECTORS[t], 0.0) + v * 100.0 / tot
    return out


adv._sector_exposure = _sector_exposure
sys.modules["portfolio_advisor"] = adv

# Health score: "before" for the current portfolio, "after" once the candidate
# is in it. Setting the pair walks the fit score through every verdict band.
FIT_CANDIDATES = {"SMALL250.NS", "SUNPHARMA.NS"}
SCORE = {"before": 60.0, "after": 60.0}
pscore = types.ModuleType("portfolio_score")
pscore.score = lambda w: {"score": SCORE["after"] if FIT_CANDIDATES & set(w)
                          else SCORE["before"]}
sys.modules["portfolio_score"] = pscore

import optimizer_stability as OS     # noqa: E402
import portfolio_fit as PF           # noqa: E402
import portfolio_scenarios as PS     # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""),
          flush=True)


def banner(title):
    print("\n" + "=" * 74 + f"\n{title}\n" + "=" * 74, flush=True)


def safely(fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as e:                       # a crash is a failed check, not a stop
        return {"crashed": f"{type(e).__name__}: {e}"}


STAB = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS"]
PINNED = {"RELIANCE.NS": 40.0, "TCS.NS": 0.0, "HDFCBANK.NS": 40.0, "INFY.NS": 20.0}

# --------------------------------------------------------------------------
banner("3. STABILITY — WEIGHTS THAT CANNOT MOVE ARE NOT STABLE")

PLAN["fn"] = lambda shift: dict(PINNED)
r = safely(OS.stability, STAB, max_weight=0.4, trials=20)
v = str(r.get("verdict", ""))
check("40/0/40/20 at a 40% cap, unmoved, is not called Stable",
      bool(v) and not v.lower().startswith("stable"), v[:70] or str(r))
check("  ...the verdict says the limits hold it", "limit" in v.lower(), v[:70])
check("  ...it is flagged as a corner", r.get("corner_solution") is True,
      f"corner_solution={r.get('corner_solution')}")
check("  ...and names the three weights on a limit",
      r.get("pinned_by_limits") is True
      and sorted(r.get("at_limit") or []) == ["HDFCBANK.NS", "RELIANCE.NS", "TCS.NS"],
      f"pinned_by_limits={r.get('pinned_by_limits')}, at_limit={r.get('at_limit')}")

# Four stocks at a 25% cap: every weight on the cap, forced to equal weight.
PLAN["fn"] = lambda shift: {t: 25.0 for t in STAB}
r = safely(OS.stability, STAB, max_weight=0.25, trials=20)
check("equal weight forced by a 25% cap on four stocks is not called Stable",
      not str(r.get("verdict", "")).lower().startswith("stable")
      and r.get("pinned_by_limits") is True, str(r.get("verdict", r))[:70])

# Over-correction guards.
PLAN["fn"] = lambda shift: {"RELIANCE.NS": 30.0, "TCS.NS": 25.0,
                            "HDFCBANK.NS": 25.0, "INFY.NS": 20.0}
r = safely(OS.stability, STAB, max_weight=0.4, trials=20)
check("weights free to move that do not move are still Stable",
      str(r.get("verdict", "")).startswith("Stable"), str(r.get("verdict", r))[:70])
check("  ...and are not a corner",
      r.get("corner_solution") is False and not r.get("pinned_by_limits"))

PLAN["fn"] = lambda shift: {"RELIANCE.NS": 60.0, "TCS.NS": 40.0,
                            "HDFCBANK.NS": 0.0, "INFY.NS": 0.0}
r = safely(OS.stability, STAB, max_weight=1.0, trials=20)
check("two free weights beside two zeros are still Stable",
      str(r.get("verdict", "")).startswith("Stable"), str(r.get("verdict", r))[:70])

PLAN["fn"] = lambda shift: {"RELIANCE.NS": 100.0, "TCS.NS": 0.0,
                            "HDFCBANK.NS": 0.0, "INFY.NS": 0.0}
r = safely(OS.stability, STAB, max_weight=1.0, trials=20)
check("an unconstrained 100% corner keeps its own message",
      str(r.get("verdict", "")).startswith("Pinned to one holding")
      and r.get("corner_solution") is True, str(r.get("verdict", r))[:70])

FLIPPED = {"RELIANCE.NS": 0.0, "TCS.NS": 40.0, "HDFCBANK.NS": 20.0, "INFY.NS": 40.0}
PLAN["fn"] = lambda shift: dict(PINNED) if shift is None or sum(shift) > 0 else dict(FLIPPED)
r = safely(OS.stability, STAB, max_weight=0.4, trials=40)
check("weights on limits that DO jump between corners are called Unstable",
      str(r.get("verdict", "")).startswith("Unstable") and not r.get("pinned_by_limits"),
      f"mean shift {r.get('mean_abs_shift_pct')}: {str(r.get('verdict', r))[:50]}")

# --------------------------------------------------------------------------
banner("4. FIT — NO CO-MOVEMENT CLAIM WITHOUT A CORRELATION")

H = {"RELIANCE.NS": 40, "TCS.NS": 30, "HDFCBANK.NS": 30}
CLAIMS = ("overlap", "doubling", "brings something", "existing bet")

# Concentration score is 50 + 2.5 x (after - before): 75, 50 and 25 land the
# fit score in the top, middle and bottom verdict bands.
for band, after in (("top", 70.0), ("middle", 60.0), ("bottom", 50.0)):
    SCORE.update(before=60.0, after=after)
    r = safely(PF.fit, "SMALL250.NS", H)
    v = str(r.get("verdict", "")).lower()
    check(f"no price history, {band} band: the verdict claims nothing about co-movement",
          bool(v) and not any(c in v for c in CLAIMS),
          f"score {r.get('fit_score')}: {v[:70]!r}")
    check(f"  ...says it could not measure correlation ({band} band)",
          "correlation" in (r.get("not_measured") or []) and "price history" in v,
          f"not_measured={r.get('not_measured')}")

SCORE.update(before=60.0, after=60.0)
r = safely(PF.fit, "SUNPHARMA.NS", H)
check("a priceable stock is still judged on correlation",
      "correlation" in (r.get("components") or {}), str(sorted(r.get("components") or r)))
check("  ...gets one of the normal verdicts",
      str(r.get("verdict", "")).startswith(("Fits well", "Adds little", "Poor fit")),
      str(r.get("verdict"))[:60])
check("  ...and reports nothing unmeasured", r.get("not_measured") == [],
      f"not_measured={r.get('not_measured')}")

r = safely(PF.fit, "SUNPHARMA.NS", {"RELIANCE.NS": -40, "TCS.NS": 140})
check("fit refuses a negative holding and names it",
      "error" in r and "RELIANCE" in r["error"], str(r)[:90])

# --------------------------------------------------------------------------
banner("5. A NEGATIVE HOLDING IS REFUSED, NOT QUIETLY DROPPED")

CALLS = []


def spy(holdings, initial_value, horizon_days):
    CALLS.append(dict(holdings))
    return {"median_value": initial_value * 1.1, "p5_value": initial_value * 0.8,
            "return_pct": 10.0, "downside_pct": -20.0, "loss_prob_pct": 30.0}


PS._measure = spy

r = safely(PS.what_if, {"RELIANCE.NS": -50000, "TCS.NS": 150000})
check("what-if refuses a negative holding", "error" in r, str(r)[:90])
check("  ...names it", "RELIANCE" in str(r.get("error", "")), str(r.get("error"))[:90])
check("  ...and simulates nothing", not CALLS, f"{len(CALLS)} simulations run")

CALLS.clear()
r = safely(PS.what_if, {"RELIANCE.NS": 50000, "TCS.NS": 50000},
           new_holdings={"RELIANCE.NS": -10, "TCS.NS": 60, "INFY.NS": 50})
check("an edit containing a negative holding is refused, naming it",
      "error" in r and "RELIANCE" in r["error"], str(r)[:90])
check("  ...before anything is simulated", not CALLS, f"{len(CALLS)} simulations run")

CALLS.clear()
r = safely(PS.scenarios, {"RELIANCE.NS": -50000, "TCS.NS": 100000, "HDFCBANK.NS": 50000})
check("scenarios refuses a negative holding, naming it",
      "error" in r and "RELIANCE" in r["error"], str(r)[:90])
check("  ...and simulates nothing", not CALLS, f"{len(CALLS)} simulations run")

# Over-correction guard: zero is how an edit removes a stock.
CALLS.clear()
r = safely(PS.what_if, {"RELIANCE.NS": 50000, "TCS.NS": 30000, "INFY.NS": 20000},
           new_holdings={"RELIANCE.NS": 50, "TCS.NS": 50, "INFY.NS": 0})
check("a zero in an edit still removes the stock",
      "error" not in r and "removed INFY" in " ".join(r.get("applied") or []),
      str(r.get("applied", r))[:90])

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
