"""
risk_metrics.py — one definition of the Sharpe and Sortino ratios.

Until 2026-09-14 the app computed Sortino four different ways and Sharpe two, so
one portfolio showed 0.27, 0.38, 0.48 or 0.61 depending on the page, and a
portfolio whose losing days all lost the same amount showed 0.00
(docs/PHASE2_FINDINGS_2026-09-14.md, section 2). Every realised-return Sharpe
and Sortino now comes from here.

Definitions, per period and then annualised
-------------------------------------------
    target    = annual target / periods_per_year   (the risk-free rate unless stated)
    excess_t  = r_t - target
    Sharpe    = mean(excess) / sd(r) * sqrt(periods_per_year)       sd with n - 1
    Sortino   = mean(excess) / DD    * sqrt(periods_per_year)
    DD        = sqrt( mean over ALL periods of min(excess_t, 0) squared )

DD averages over every period, not only the losing ones, and measures shortfall
below the target, not how spread out the losses are among themselves (Sortino
and Price, 1994). Averaging over the losers alone inflates it; measuring their
spread gives zero for steady losses.

None means undefined: fewer than two usable periods, no variation (Sharpe), or
no period below the target (Sortino). The caller decides how to show that; it is
never reported as a real zero here.

Not covered, on purpose
-----------------------
- The optimiser's expected Sharpe, computed from forecast returns and a
  covariance matrix rather than from returns that happened.
- The per-period Sharpe estimator inside overfitting.py (probabilistic and
  deflated Sharpe), which follows its own statistical definition.
"""

import math

from model_config import RISK_FREE_RATE as _RF

# Below this a standard deviation is rounding noise on a flat series, not risk.
_FLAT = 1e-12


def _usable(returns):
    """The finite numbers in a list, array or Series, in order."""
    out = []
    for r in (returns if returns is not None else []):
        try:
            v = float(r)
        except (TypeError, ValueError):
            continue
        if math.isfinite(v):
            out.append(v)
    return out


def sharpe(returns, periods_per_year, risk_free=_RF):
    """Annualised Sharpe ratio of per-period returns, or None when undefined."""
    r = _usable(returns)
    n = len(r)
    if n < 2:
        return None
    mean = sum(r) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in r) / (n - 1))
    if sd < _FLAT:
        return None
    return (mean - risk_free / periods_per_year) / sd * math.sqrt(periods_per_year)


def sortino(returns, periods_per_year, risk_free=_RF):
    """Annualised Sortino ratio of per-period returns, or None when undefined."""
    r = _usable(returns)
    n = len(r)
    if n < 2:
        return None
    target = risk_free / periods_per_year
    excess = [x - target for x in r]
    dd = math.sqrt(sum(min(e, 0.0) ** 2 for e in excess) / n)
    if dd < _FLAT:
        return None
    return (sum(excess) / n) / dd * math.sqrt(periods_per_year)
