"""
optimizer_audit.py — do the optimisers produce portfolios that are actually valid?

An optimiser can return a plausible-looking set of weights that violates its own
constraints, sums to something other than 100%, or rests on a covariance matrix
that is not positive semi-definite. None of those show up as an error; they show
up as a portfolio the user is told to hold.

Every check here is a property that must hold whatever the optimiser did:
weights sum to one, no weight exceeds its stated cap, no negative weight where
shorting is not offered, the covariance matrix is symmetric and PSD, and the
same inputs produce the same outputs.

Costs are audited separately at the end: a strategy that only works at zero
transaction cost is not a strategy.
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
        failures.append(label + (f" — {evidence}" if evidence else ""))


def note(m):
    notes.append(m)


UNIVERSE = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS",
            "ITC.NS", "SUNPHARMA.NS"]

# ===========================================================================
print("=== 1. COVARIANCE MATRIX ===")
print("Symmetric, PSD, and finite. A non-PSD covariance makes 'minimum")
print("variance' meaningless — the optimiser can find negative variance.\n")

try:
    from portfolio_optimizer import _get_returns
    from datetime import datetime, timedelta
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
    rets = _get_returns(UNIVERSE, start, end)
except Exception as e:
    rets = None
    note(f"returns unavailable ({type(e).__name__}) — covariance UNVERIFIED")

if rets is not None and not rets.empty:
    cols = [c for c in UNIVERSE if c in rets.columns]
    R = rets[cols].dropna()
    print(f"  {len(cols)} assets, {len(R)} overlapping days")

    S = np.cov(R.values, rowvar=False, ddof=1)
    ok(S.shape[0] == S.shape[1] == len(cols), "covariance is square",
       str(S.shape))
    ok(np.allclose(S, S.T, atol=1e-12), "covariance is symmetric")
    ok(np.all(np.isfinite(S)), "covariance has no NaN or infinity")

    eig = np.linalg.eigvalsh(S)
    min_eig = float(eig.min())
    print(f"  smallest eigenvalue (sample cov): {min_eig:.3e}")
    ok(min_eig >= -1e-10, "sample covariance is positive semi-definite",
       f"min eigenvalue {min_eig:.3e}")

    # Diagonal must be the variances, and every variance non-negative.
    for i, c in enumerate(cols):
        ok(S[i, i] >= 0, f"variance of {c} is non-negative", f"{S[i,i]:.3e}")

    # Ledoit-Wolf shrinkage, if the app uses it, must IMPROVE conditioning.
    try:
        from sklearn.covariance import LedoitWolf
        lw = LedoitWolf().fit(R.values).covariance_
        eig_lw = np.linalg.eigvalsh(lw)
        cond_s = float(eig.max() / max(eig.min(), 1e-18))
        cond_lw = float(eig_lw.max() / max(eig_lw.min(), 1e-18))
        print(f"  condition number: sample {cond_s:.1f} -> shrunk {cond_lw:.1f}")
        ok(float(eig_lw.min()) > 0,
           "shrunk covariance is strictly positive definite",
           f"{eig_lw.min():.3e}")
        ok(cond_lw <= cond_s * 1.001,
           "shrinkage does not worsen conditioning",
           f"{cond_s:.1f} -> {cond_lw:.1f}")
    except Exception:
        note("Ledoit-Wolf comparison UNVERIFIED (sklearn unavailable)")
else:
    note("covariance section UNVERIFIED — no returns")


# ===========================================================================
print("\n=== 2. PORTFOLIO WEIGHT VALIDATION ===")
print("Every optimiser's output must obey its own stated constraints.\n")

OPTIMISERS = []
try:
    from portfolio_optimizer import mean_variance_optimize
    OPTIMISERS.append(("mean-variance (cap 35%)",
                       lambda: mean_variance_optimize(
                           UNIVERSE, target="max_sharpe", max_weight=0.35,
                           period_months=24),
                       ("optimal_pct",), 35.0))
except Exception:
    note("mean_variance_optimize UNVERIFIED")

try:
    from portfolio_optimizer import black_litterman_optimize
    OPTIMISERS.append(("black-litterman",
                       lambda: black_litterman_optimize(UNIVERSE, sentiment_views={}),
                       ("bl_pct", "optimal_pct"), None))
except Exception:
    note("black_litterman_optimize UNVERIFIED")

try:
    from portfolio_optimizer import hierarchical_risk_parity
    OPTIMISERS.append(("HRP",
                       lambda: hierarchical_risk_parity(UNIVERSE),
                       ("optimal_pct", "hrp_pct", "weights_pct"), None))
except Exception:
    try:
        from portfolio_optimizer import hrp_optimize
        OPTIMISERS.append(("HRP",
                           lambda: hrp_optimize(UNIVERSE),
                           ("optimal_pct", "hrp_pct", "weights_pct"), None))
    except Exception:
        note("HRP UNVERIFIED — no recognised entry point")

try:
    from portfolio_optimizer import equal_risk_contribution
    OPTIMISERS.append(("equal risk contribution",
                       lambda: equal_risk_contribution(UNIVERSE),
                       ("optimal_pct", "weights_pct"), None))
except Exception:
    note("equal_risk_contribution UNVERIFIED")

for name, fn, keys, cap in OPTIMISERS:
    try:
        r = fn()
    except Exception as e:
        ok(False, f"{name}: raised", type(e).__name__)
        continue
    if not isinstance(r, dict) or "error" in r:
        note(f"{name}: UNVERIFIED — {str(r.get('error') if isinstance(r, dict) else r)[:60]}")
        continue

    w = None
    for k in keys:
        if isinstance(r.get(k), dict) and r[k]:
            w = r[k]
            break
    if not w:
        note(f"{name}: UNVERIFIED — no weight dict under {keys}")
        continue

    total = sum(w.values())
    print(f"  {name:<26} n={len(w):<3} sum={total:8.4f}%  max={max(w.values()):6.2f}%  "
          f"min={min(w.values()):6.2f}%")

    ok(abs(total - 100.0) < 0.5, f"{name}: weights sum to 100%", f"{total:.4f}")
    ok(all(v >= -1e-9 for v in w.values()),
       f"{name}: no negative weight (long-only)",
       str({k: v for k, v in w.items() if v < 0}))
    ok(all(math.isfinite(v) for v in w.values()),
       f"{name}: every weight is finite")
    if cap is not None:
        worst = max(w.values())
        ok(worst <= cap + 0.51,
           f"{name}: no holding exceeds the {cap:.0f}% cap", f"max={worst:.3f}%")

    # Reproducibility: same inputs, same outputs.
    try:
        r2 = fn()
        w2 = None
        for k in keys:
            if isinstance(r2.get(k), dict) and r2[k]:
                w2 = r2[k]
                break
        if w2:
            same = all(abs(w[t] - w2.get(t, -999)) < 1e-6 for t in w)
            ok(same, f"{name}: reproducible on identical input",
               "weights differed between two identical calls")
    except Exception:
        note(f"{name}: reproducibility UNVERIFIED")


# ===========================================================================
print("\n=== 3. TRANSACTION COST SENSITIVITY ===")
print("A strategy that only survives at zero cost is not a strategy.\n")

try:
    from momentum_backtest import momentum_backtest, BROAD_UNIVERSE
    print(f"  {'cost (bps round-trip)':<26}{'CAGR':>9}{'excess vs Nifty':>18}")
    prev_excess = None
    monotone = True
    for bps in (0, 10, 25, 50, 100):
        r = momentum_backtest(universe=BROAD_UNIVERSE, start="2019-01-01",
                              top_fraction=0.2, cost_roundtrip_pct=bps / 100.0,
                              pit_universe_size=50)
        if "error" in r:
            note(f"cost {bps}bps UNVERIFIED — {r['error'][:50]}")
            continue
        cagr = r["strategy_stats"]["cagr_pct"]
        exc = r.get("excess_cagr_pct")
        print(f"  {bps:<26}{cagr:>8.2f}%{exc:>17.2f}")
        if prev_excess is not None and exc > prev_excess + 1e-9:
            monotone = False
        prev_excess = exc
    ok(monotone, "higher costs never improve the result",
       "excess return rose as costs rose, which is impossible")
except Exception as e:
    note(f"transaction-cost sweep UNVERIFIED ({type(e).__name__})")


print("\n" + "=" * 72)
print(f"OPTIMIZER AUDIT CHECKS: {checks}")
print(f"FAILURES:               {len(failures)}")
for f in failures:
    print(f"   FAIL: {f}")
if notes:
    print(f"\nUNVERIFIED ({len(notes)}) — not assumed correct:")
    for n in notes:
        print(f"   - {n}")
print("=" * 72)
sys.exit(1 if failures else 0)
