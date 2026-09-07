"""
optimizer_properties_test.py — does each optimiser compute what it claims?

`optimizer_audit.py` already checks that outputs are valid portfolios: weights
sum to 100%, none negative, none infinite, caps respected. That is hygiene. It
would pass just as happily if `equal_risk_contribution` returned equal WEIGHTS
instead of equal RISK, or if `hierarchical_risk_parity` quietly used expected
returns it is defined not to use.

This checks the defining property of each method instead. Every assertion here
is a mathematical identity, so none of them needs a p-value, a sample size or a
market to cooperate — unlike the alpha factors, an optimiser can simply be
proven right or wrong.

Data is injected rather than fetched. `_get_returns` and `_get_market_caps` are
replaced with deterministic synthetic series built from a covariance we choose,
so these exercise the real production functions on controlled input. The
covariance the optimisers actually see comes back through `_cov` (Ledoit-Wolf
shrinkage), so every expectation below is computed from `_cov` too — asserting
against the raw input matrix would be testing the shrinkage, not the optimiser.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import portfolio_optimizer as PO  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}" + (f"   {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Synthetic market. Fixed seed: a property test that passes only on some draws
# is not a property test.
# ---------------------------------------------------------------------------
TICKERS = ["AAA.NS", "BBB.NS", "CCC.NS", "DDD.NS", "EEE.NS"]
DAYS = 1400
RNG = np.random.default_rng(20260907)

# Two correlated pairs and one independent name — enough structure for the
# clustering in HRP to have something real to find.
CORR = np.array([
    [1.00, 0.80, 0.10, 0.10, 0.00],
    [0.80, 1.00, 0.10, 0.10, 0.00],
    [0.10, 0.10, 1.00, 0.75, 0.00],
    [0.10, 0.10, 0.75, 1.00, 0.00],
    [0.00, 0.00, 0.00, 0.00, 1.00],
])
VOL = np.array([0.010, 0.014, 0.008, 0.020, 0.012])   # daily
COV_D = np.outer(VOL, VOL) * CORR


def make_returns(mean_daily=None, days=DAYS, seed=None):
    rng = np.random.default_rng(seed) if seed is not None else np.random.default_rng(20260907)
    mu = np.zeros(len(TICKERS)) if mean_daily is None else np.asarray(mean_daily)
    X = rng.multivariate_normal(mu, COV_D, size=days)
    idx = pd.bdate_range("2021-01-01", periods=days)
    return pd.DataFrame(X, columns=TICKERS, index=idx)


_RETURNS = {"df": make_returns()}
PO._get_returns = lambda tickers, start, end: _RETURNS["df"][
    [t for t in tickers if t in _RETURNS["df"].columns]]
PO._get_market_caps = lambda tickers: {t: 1.0e11 * (i + 1) for i, t in enumerate(tickers)}


def sigma_now():
    """The annualised covariance the optimisers will actually see."""
    return np.asarray(PO._cov(_RETURNS["df"], as_frame=False))


def wvec(res):
    """Weights, whichever key this optimiser uses to report them.

    Black-Litterman returns `bl_weights`; the others `optimal_weights`. A test
    that silently read a missing key would compare zeros to zeros and pass.
    """
    w = res.get("optimal_weights") or res.get("bl_weights") or {}
    assert w, f"no weights in result: keys={sorted(res)[:8]}"
    return np.array([w.get(t, 0.0) for t in TICKERS])


# ---------------------------------------------------------------------------
print("\n1. EQUAL RISK CONTRIBUTION — does it equalise RISK, not money?")
erc = PO.equal_risk_contribution(TICKERS)
ok("error" not in erc, f"it runs ({erc.get('error','')})")
rc = list((erc.get("risk_contribution_pct") or {}).values())
if rc:
    spread = max(rc) / max(min(rc), 1e-9)
    ok(spread < 1.05,
       "every holding contributes the same risk",
       f"max/min = {spread:.4f}, contributions {[round(x,2) for x in rc]}")
    w = wvec(erc)
    ok(max(w) / max(min(w), 1e-9) > 1.3,
       "and the WEIGHTS are deliberately unequal — equal risk is not equal money",
       f"weights {[round(x,3) for x in w]}")

# Closed form: with uncorrelated assets, ERC weight is proportional to 1/vol.
print("\n   with an uncorrelated market, ERC has a closed form: w proportional to 1/vol")
_prev = _RETURNS["df"]
diag_rng = np.random.default_rng(7)
_RETURNS["df"] = pd.DataFrame(
    diag_rng.multivariate_normal(np.zeros(5), np.diag(VOL ** 2), size=DAYS),
    columns=TICKERS, index=_prev.index)
erc_d = PO.equal_risk_contribution(TICKERS)
w_d = wvec(erc_d)
inv_vol = 1.0 / np.sqrt(np.diag(sigma_now()))
expect = inv_vol / inv_vol.sum()
err = float(np.max(np.abs(w_d - expect)))
ok(err < 0.02, "matches the analytic 1/vol solution",
   f"max deviation {err:.4f}  got {[round(x,3) for x in w_d]} "
   f"vs {[round(x,3) for x in expect]}")
_RETURNS["df"] = _prev

# ---------------------------------------------------------------------------
print("\n2. RETURNS-AGNOSTIC BY CONSTRUCTION")
print("   ERC, HRP and min-variance are defined on covariance alone. Shifting")
print("   every asset's drift must not move a single weight.")
base = {
    "erc": wvec(PO.equal_risk_contribution(TICKERS)),
    "hrp": wvec(PO.hierarchical_risk_parity(TICKERS)),
    "minvar": wvec(PO.mean_variance_optimize(TICKERS, target="min_variance")),
}
_RETURNS["df"] = make_returns(mean_daily=[0.004, -0.003, 0.002, -0.001, 0.005])
shifted = {
    "erc": wvec(PO.equal_risk_contribution(TICKERS)),
    "hrp": wvec(PO.hierarchical_risk_parity(TICKERS)),
    "minvar": wvec(PO.mean_variance_optimize(TICKERS, target="min_variance")),
}
for k in base:
    d = float(np.max(np.abs(base[k] - shifted[k])))
    ok(d < 0.01, f"{k}: weights unchanged when drift changes", f"max shift {d:.5f}")
_RETURNS["df"] = make_returns()

print("\n   ...and max-Sharpe SHOULD move, or it is ignoring returns entirely")
ms_a = wvec(PO.mean_variance_optimize(TICKERS, target="max_sharpe"))
_RETURNS["df"] = make_returns(mean_daily=[0.004, -0.003, 0.002, -0.001, 0.005])
ms_b = wvec(PO.mean_variance_optimize(TICKERS, target="max_sharpe"))
ok(float(np.max(np.abs(ms_a - ms_b))) > 0.05,
   "max-Sharpe responds to expected returns",
   f"max shift {float(np.max(np.abs(ms_a - ms_b))):.4f}")
_RETURNS["df"] = make_returns()

# ---------------------------------------------------------------------------
print("\n3. MINIMUM VARIANCE — is it actually the minimum?")
mv = PO.mean_variance_optimize(TICKERS, target="min_variance")
w = wvec(mv)
S = sigma_now()
var0 = float(w @ S @ w)
beaten, best = 0, var0
rng = np.random.default_rng(11)
for _ in range(4000):
    p = w + rng.normal(0, 0.02, len(w))
    p = np.clip(p, 0, None)
    if p.sum() <= 0:
        continue
    p /= p.sum()
    v = float(p @ S @ p)
    if v < var0 - 1e-9:
        beaten += 1
        best = min(best, v)
ok(beaten == 0, "no feasible perturbation reduces portfolio variance",
   f"{beaten} of 4000 beat it" + (f", best {best:.8f} vs {var0:.8f}" if beaten else ""))

# Unconstrained closed form, for the case where it is interior and long-only.
inv = np.linalg.inv(S)
one = np.ones(len(TICKERS))
analytic = inv @ one / (one @ inv @ one)
if np.all(analytic > 0):
    ok(float(np.max(np.abs(w - analytic))) < 0.02,
       "matches the closed form  inv(S)1 / (1' inv(S) 1)",
       f"max deviation {float(np.max(np.abs(w - analytic))):.4f}")
else:
    print("   (closed form has a negative weight here, so the bound binds — skipped)")

# ---------------------------------------------------------------------------
print("\n4. MAXIMUM DIVERSIFICATION — is the diversification ratio maximised?")
md = PO.maximum_diversification(TICKERS)
w = wvec(md)
S = sigma_now()
sd = np.sqrt(np.diag(S))
dr = lambda x: float(x @ sd / np.sqrt(max(x @ S @ x, 1e-18)))
dr0 = dr(w)
beaten = 0
rng = np.random.default_rng(13)
for _ in range(4000):
    p = np.clip(w + rng.normal(0, 0.02, len(w)), 0, None)
    if p.sum() <= 0:
        continue
    p /= p.sum()
    if dr(p) > dr0 + 1e-9:
        beaten += 1
ok(beaten == 0, "no feasible perturbation raises the diversification ratio",
   f"ratio {dr0:.5f}, {beaten} of 4000 beat it")
ok(dr0 > 1.0, "and the portfolio is diversified at all (ratio > 1)", f"{dr0:.4f}")

# ---------------------------------------------------------------------------
print("\n5. BLACK-LITTERMAN — the identities that define it")
bl0 = PO.black_litterman_optimize(TICKERS, sentiment_views={})
ok("error" not in bl0, f"runs with no views ({bl0.get('error','')})")

# With views that merely restate equilibrium, the posterior must BE equilibrium
# for any confidence. This exercises the posterior formula, unlike the no-views
# branch which is an if-statement.
S = sigma_now()
caps = PO._get_market_caps(TICKERS)
w_mkt = np.array([caps[t] for t in TICKERS]); w_mkt = w_mkt / w_mkt.sum()
pi = 2.5 * S @ w_mkt
for conf in (0.2, 0.9):
    views = {t: (float(pi[i]), conf) for i, t in enumerate(TICKERS)}
    bl = PO.black_litterman_optimize(TICKERS, sentiment_views=views)
    same = wvec(bl)
    ok("error" not in bl and float(np.max(np.abs(same - wvec(bl0)))) < 0.02,
       f"views equal to equilibrium leave the answer unchanged (confidence {conf})",
       f"max weight shift {float(np.max(np.abs(same - wvec(bl0)))):.4f}")

# A strong bullish view on one name must tilt toward it, not away.
idx = 2
bull = {TICKERS[idx]: (float(pi[idx]) + 0.25, 0.95)}
blb = PO.black_litterman_optimize(TICKERS, sentiment_views=bull)
ok("error" not in blb and wvec(blb)[idx] > wvec(bl0)[idx] + 1e-4,
   f"a confident bullish view raises that holding's weight",
   f"{TICKERS[idx]}: {wvec(bl0)[idx]:.4f} -> {wvec(blb)[idx]:.4f}")
bear = {TICKERS[idx]: (float(pi[idx]) - 0.25, 0.95)}
blr = PO.black_litterman_optimize(TICKERS, sentiment_views=bear)
ok("error" not in blr and wvec(blr)[idx] < wvec(bl0)[idx] - 1e-4,
   "and a bearish one lowers it",
   f"{TICKERS[idx]}: {wvec(bl0)[idx]:.4f} -> {wvec(blr)[idx]:.4f}")

# ---------------------------------------------------------------------------
print("\n6. MINIMUM CVaR — is the reported tail loss the real one?")
cv = PO.min_cvar_optimize(TICKERS, confidence=0.95)
ok("error" not in cv, f"runs ({cv.get('error','')})")
w = wvec(cv)
port = (_RETURNS["df"][TICKERS].values @ w)
var95 = -np.quantile(port, 0.05)
cvar95 = -port[port <= np.quantile(port, 0.05)].mean()
ok(cvar95 >= var95 - 1e-12,
   "CVaR is at least VaR, as it must be by definition",
   f"VaR {var95*100:.3f}%  CVaR {cvar95*100:.3f}% (daily)")
# and it should beat equal-weight on the thing it optimises
ew = np.repeat(1 / len(TICKERS), len(TICKERS))
pe = _RETURNS["df"][TICKERS].values @ ew
cvar_ew = -pe[pe <= np.quantile(pe, 0.05)].mean()
ok(cvar95 <= cvar_ew + 1e-9,
   "and its CVaR is no worse than equal weight — the objective it minimises",
   f"optimised {cvar95*100:.3f}% vs equal-weight {cvar_ew*100:.3f}%")

# ---------------------------------------------------------------------------
print("\n7. HRP — clustering, and no matrix inversion")
hrp = PO.hierarchical_risk_parity(TICKERS)
ok("error" not in hrp, f"runs ({hrp.get('error','')})")
w = wvec(hrp)
ok(abs(w.sum() - 1.0) < 1e-6, "weights sum to 1", f"{w.sum():.8f}")
ok(np.all(w >= 0), "no short positions")
# EEE is uncorrelated with everything; the two correlated pairs share risk.
# A clustering method should not hand the lone diversifier a trivial slice.
ok(w[4] > 1.0 / len(TICKERS) * 0.8,
   "the uncorrelated asset is not starved by the clustering",
   f"EEE weight {w[4]:.4f} vs equal weight {1/len(TICKERS):.4f}")
# HRP must be invariant to a singular covariance, where Markowitz cannot invert.
_prev = _RETURNS["df"]
dup = _prev.copy()
dup["BBB.NS"] = dup["AAA.NS"]           # perfectly collinear -> singular
_RETURNS["df"] = dup
hrp_s = PO.hierarchical_risk_parity(TICKERS)
# Tolerance is 1e-3, not 1e-6: reported weights are rounded to 4 decimals, so
# five of them can sum to 1.0001 while the underlying vector sums to exactly 1.
_ws = sum((hrp_s.get("optimal_weights") or {}).values())
ok(not hrp_s.get("error") and abs(_ws - 1) < 1e-3,
   "still solves when two assets are perfectly collinear",
   f"sum {_ws:.4f}, error {hrp_s.get('error')!r}")
# Worth naming: it survives partly because Ledoit-Wolf shrinkage leaves the
# covariance invertible (smallest eigenvalue ~2.3e-04 on this input), so this
# does not by itself prove HRP's inversion-free claim — it proves the pipeline
# does not fall over on collinear inputs, which is the property that matters
# to a user holding two share classes of the same company.
_RETURNS["df"] = _prev

# ---------------------------------------------------------------------------
print("\n8. FINDING — reported, deliberately not asserted on")
print("   Black-Litterman defines pi = delta * Sigma @ w_mkt as the EXCESS return")
print("   over the risk-free rate, and the code's own comment says so. neg_sharpe")
print("   then computes -(w @ mu_bl - _rf()) / vol, deducting that rate a second")
print("   time. When portfolio pi falls below rf the numerator turns negative,")
print("   and minimising -(negative)/vol MAXIMISES volatility.")
print()
print(f"   {'market vol':<12}{'pi = 2.5*vol^2':>17}{'minus rf':>11}")
_rf_now = PO._rf()
for _v in (0.10, 0.14, 0.16, 0.18, 0.22):
    _pi = 2.5 * _v * _v
    _n = _pi - _rf_now
    print(f"   {_v*100:>9.0f}%  {_pi*100:>15.2f}%  {_n*100:>+9.2f}%"
          + ("   <- inverted" if _n < 0 else ""))
print()
print("   NSE index vol runs 13-18%, so the sign flips around 16%. Not asserted:")
print("   changing it moves portfolio weights users see, which is a model")
print("   decision rather than a test fixture. Printed so it is not forgotten.")

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
