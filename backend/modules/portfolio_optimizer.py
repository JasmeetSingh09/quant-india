"""
portfolio_optimizer.py — Black-Litterman Portfolio Optimizer for NSE stocks.

TWO ALGORITHMS IMPLEMENTED:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALGORITHM 1 — Mean-Variance Optimization (Markowitz 1952)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Classic portfolio theory: find weights that maximise the Sharpe ratio
by solving:

  maximise    (μᵀw - rf) / √(wᵀΣw)
  subject to  Σwᵢ = 1,  wᵢ ≥ 0   (no short selling)

Where:
  μ  = expected returns vector
  Σ  = covariance matrix of returns
  w  = portfolio weights
  rf = risk-free rate (RBI repo rate proxy)

Solved numerically using scipy.optimize.minimize.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALGORITHM 2 — Black-Litterman (1990, 1992) WITH SENTIMENT VIEWS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The KEY INNOVATION: Black-Litterman lets us inject our FinBERT
sentiment scores as "views" that shift the equilibrium expected returns.

Standard BL formula:
  μ_BL = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹ · [(τΣ)⁻¹π + PᵀΩ⁻¹Q]

Where:
  π    = implied equilibrium returns (from market cap weights)
  P    = views matrix (which stocks the views apply to)
  Q    = views vector (what we expect each stock to return)
  Ω    = views uncertainty matrix (diagonal, from sentiment confidence)
  τ    = scalar (~1/T, scales prior uncertainty)

Our innovation: Q is derived from the alpha model's sentiment factor.
Ω is set inversely proportional to FinBERT confidence.
This creates a mathematically principled link between NLP and portfolio weights.

Result: the optimizer tilts weights AWAY from stocks with strong negative
sentiment and TOWARD stocks with strong positive sentiment, but only by
as much as the market-cap equilibrium allows — preventing extreme positions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALGORITHM 3 — Efficient Frontier
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Traces the full frontier of (risk, return) combinations by
solving the MVO at 50 target return levels. Useful for
showing where your current portfolio sits vs the optimal.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.optimize import minimize
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

RISK_FREE_RATE = 0.065   # default: RBI repo rate proxy


def _rf(risk_free_pct: float = None) -> float:
    """
    Resolve the risk-free rate used in every Sharpe calculation.

    Pass `risk_free_pct` as a PERCENT (e.g. 7.0 for a 10-year G-Sec yield) to
    override the default RBI-repo proxy. Every Sharpe figure inherits this, so
    it is a real assumption rather than a cosmetic setting — which is why it is
    now caller-selectable instead of hardcoded.
    """
    try:
        if risk_free_pct is not None:
            return float(risk_free_pct) / 100.0
    except (TypeError, ValueError):
        pass
    return RISK_FREE_RATE


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _get_returns(tickers: list, start: str, end: str) -> pd.DataFrame:
    """Download and return daily log returns for a list of tickers.
    Uses the shared price cache so repeated requests for the same ticker
    (common across MVO/HRP/BL/frontier in one session) hit memory, not yfinance."""
    prices = {}
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from data_fetcher import download_close
    except Exception:
        download_close = None

    for t in tickers:
        try:
            if download_close:
                s = download_close(t, start, end)
            else:
                df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
                s = df["Close"].squeeze() if not df.empty else pd.Series(dtype=float)
            if len(s) > 0:
                prices[t] = s
        except Exception:
            pass
    if not prices:
        return pd.DataFrame()
    df    = pd.DataFrame(prices).ffill().dropna()
    # Log returns: r = ln(P_t / P_{t-1})
    return np.log(df / df.shift(1)).dropna()


def _cov(log_returns: pd.DataFrame, as_frame: bool = False):
    """
    Annualised covariance using LEDOIT-WOLF SHRINKAGE instead of the raw sample
    covariance. Sample covariance is noisy and unstable for optimisation
    (it 'error-maximises'); Ledoit-Wolf shrinks it toward a structured target,
    which real quant desks use for far more stable portfolio weights.
    Falls back to sample covariance if sklearn isn't available.
    """
    try:
        from sklearn.covariance import LedoitWolf
        lw = LedoitWolf().fit(log_returns.values)
        cov = lw.covariance_ * 252
    except Exception:
        cov = log_returns.cov().values * 252
    if as_frame:
        return pd.DataFrame(cov, index=log_returns.columns, columns=log_returns.columns)
    return cov


def risk_decomposition(holdings: dict, period_months: int = 24) -> dict:
    """
    Decompose a portfolio's total volatility into each holding's RISK
    CONTRIBUTION — the share of portfolio risk it actually drives, which is
    usually very different from its capital weight. A 20%-weight high-beta,
    high-correlation stock can contribute 40% of the risk.

    Method (Euler / marginal risk contribution):
      port_vol      = sqrt(w' Σ w)
      marginal_i    = (Σ w)_i / port_vol            (∂σ_p/∂w_i)
      risk_contrib_i= w_i · marginal_i              (these sum to port_vol)
      pct_i         = risk_contrib_i / port_vol      (these sum to 100%)

    Σ is the annualised Ledoit-Wolf covariance. Also reports a diversification
    ratio (weighted-avg st-alone vol ÷ portfolio vol): higher = more
    diversification benefit.
    """
    tickers = list(holdings.keys())
    if len(tickers) < 2:
        return {"error": "Need at least 2 holdings to decompose risk."}

    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")
    log_returns = _get_returns(tickers, start, end)
    valid = [t for t in tickers if t in log_returns.columns]
    excluded = [t for t in tickers if t not in valid]
    if len(valid) < 2:
        return {"error": f"Need ≥2 tickers with price data. Got: {valid}"}

    log_returns = log_returns[valid]
    w = np.array([float(holdings[t]) for t in valid])
    if w.sum() <= 0:
        return {"error": "weights must be positive"}
    w = w / w.sum()

    cov = _cov(log_returns, as_frame=False)           # annualised
    port_var = float(w @ cov @ w)
    port_vol = float(np.sqrt(max(port_var, 1e-12)))
    marginal = (cov @ w) / port_vol                   # ∂σ/∂w_i
    risk_contrib = w * marginal                        # sums to port_vol
    pct = risk_contrib / port_vol * 100.0
    own_vol = np.sqrt(np.diag(cov))                    # stand-alone annualised vol

    components = []
    for i, t in enumerate(valid):
        components.append({
            "ticker":              t,
            "weight_pct":          round(float(w[i] * 100), 2),
            "standalone_vol_pct":  round(float(own_vol[i] * 100), 2),
            "risk_contribution_pct": round(float(pct[i]), 2),
            # >1 means it punches ABOVE its weight in risk terms
            "risk_to_weight":      round(float(pct[i] / (w[i] * 100)) if w[i] > 0 else 0, 2),
        })
    components.sort(key=lambda c: c["risk_contribution_pct"], reverse=True)

    wavg_vol = float(w @ own_vol)
    div_ratio = wavg_vol / port_vol if port_vol > 0 else 1.0
    top = components[0]

    return {
        "portfolio_vol_pct":   round(port_vol * 100, 2),
        "diversification_ratio": round(div_ratio, 3),
        "components":          components,
        "excluded_tickers":    excluded,
        "top_risk_driver":     top["ticker"],
        "interpretation": (
            f"{top['ticker'].replace('.NS','')} is your biggest risk driver: "
            f"{top['weight_pct']}% of capital but {top['risk_contribution_pct']}% of "
            f"portfolio risk ({top['risk_to_weight']}× its weight). "
            f"Diversification ratio {round(div_ratio,2)} — "
            + ("holdings move together, so diversification is limited."
               if div_ratio < 1.15 else
               "you're getting meaningful diversification benefit.")
        ),
        "note": "Risk contributions sum to 100%; based on annualised Ledoit-Wolf covariance.",
    }


def _perf_stats(w, log_returns, cov, risk_free_pct: float = None):
    """Annualised expected return / vol / Sharpe for a weight vector."""
    exp_ret = float(w @ (log_returns.mean().values * 252))
    exp_vol = float(np.sqrt(max(w @ cov @ w, 1e-12)))
    sharpe = (exp_ret - _rf(risk_free_pct)) / exp_vol if exp_vol > 0 else 0.0
    return round(exp_ret * 100, 2), round(exp_vol * 100, 2), round(sharpe, 3)


def equal_risk_contribution(tickers: list, period_months: int = 24,
                            risk_free_pct: float = None) -> dict:
    """
    Risk Parity (Equal Risk Contribution): weights chosen so every holding
    contributes the SAME amount of portfolio risk — not equal money, equal risk.
    Distinct from HRP (which clusters) and from min-variance. Solved by
    minimising the dispersion of risk contributions (Maillard et al. 2010).
    """
    from scipy.optimize import minimize
    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")
    log_returns = _get_returns(tickers, start, end)
    valid = [t for t in tickers if t in log_returns.columns]
    if len(valid) < 2:
        return {"error": f"Need ≥2 tickers with data. Got: {valid}"}
    log_returns = log_returns[valid]
    cov = _cov(log_returns, as_frame=False)
    n = len(valid)

    def obj(w):
        pv = np.sqrt(max(w @ cov @ w, 1e-12))
        rc = w * (cov @ w) / pv               # risk contributions
        return float(np.sum((rc - rc.mean()) ** 2))

    res = minimize(obj, np.repeat(1 / n, n), method="SLSQP",
                   bounds=[(0, 1)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"maxiter": 500, "ftol": 1e-12})
    w = np.clip(res.x, 0, None); w = w / w.sum()
    pv = float(np.sqrt(max(w @ cov @ w, 1e-12)))
    rc_pct = (w * (cov @ w) / pv) / pv * 100
    er, ev, sh = _perf_stats(w, log_returns, cov, risk_free_pct)
    return {
        "algorithm":        "Equal Risk Contribution (Risk Parity, Maillard 2010)",
        "excluded_tickers": [t for t in tickers if t not in valid],
        "tickers":          valid,
        "optimal_weights":  {t: round(float(w[i]), 4) for i, t in enumerate(valid)},
        "optimal_pct":      {t: round(float(w[i] * 100), 2) for i, t in enumerate(valid)},
        "risk_contribution_pct": {t: round(float(rc_pct[i]), 2) for i, t in enumerate(valid)},
        "expected_annual_return_pct": er,
        "expected_annual_vol_pct":    ev,
        "expected_sharpe":            sh,
        "interpretation": "Every holding contributes ~equal risk, so no single name "
                          "dominates the portfolio's volatility — robust when you "
                          "can't forecast returns.",
    }


def maximum_diversification(tickers: list, period_months: int = 24,
                            risk_free_pct: float = None) -> dict:
    """
    Maximum Diversification portfolio (Choueifaty & Coignard 2008): weights that
    MAXIMISE the diversification ratio = (weighted-average stand-alone vol) /
    (portfolio vol). Pushes toward low-correlation combinations.
    """
    from scipy.optimize import minimize
    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")
    log_returns = _get_returns(tickers, start, end)
    valid = [t for t in tickers if t in log_returns.columns]
    if len(valid) < 2:
        return {"error": f"Need ≥2 tickers with data. Got: {valid}"}
    log_returns = log_returns[valid]
    cov = _cov(log_returns, as_frame=False)
    own_vol = np.sqrt(np.diag(cov))
    n = len(valid)

    def neg_div_ratio(w):
        pv = np.sqrt(max(w @ cov @ w, 1e-12))
        return -float((w @ own_vol) / pv)

    res = minimize(neg_div_ratio, np.repeat(1 / n, n), method="SLSQP",
                   bounds=[(0, 1)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"maxiter": 500, "ftol": 1e-12})
    w = np.clip(res.x, 0, None); w = w / w.sum()
    pv = float(np.sqrt(max(w @ cov @ w, 1e-12)))
    div_ratio = float((w @ own_vol) / pv)
    er, ev, sh = _perf_stats(w, log_returns, cov, risk_free_pct)
    return {
        "algorithm":        "Maximum Diversification (Choueifaty & Coignard 2008)",
        "excluded_tickers": [t for t in tickers if t not in valid],
        "tickers":          valid,
        "optimal_weights":  {t: round(float(w[i]), 4) for i, t in enumerate(valid)},
        "optimal_pct":      {t: round(float(w[i] * 100), 2) for i, t in enumerate(valid)},
        "diversification_ratio":      round(div_ratio, 3),
        "expected_annual_return_pct": er,
        "expected_annual_vol_pct":    ev,
        "expected_sharpe":            sh,
        "interpretation": f"Diversification ratio {round(div_ratio,2)} — maximises the "
                          "gap between the holdings' own volatility and the (lower) "
                          "portfolio volatility, i.e. the most diversification per unit of risk.",
    }


def _get_market_caps(tickers: list) -> dict:
    """Get market capitalisation weights (used as BL equilibrium prior)."""
    caps = {}
    for t in tickers:
        try:
            mc = yf.Ticker(t).fast_info.market_cap
            if mc:
                caps[t] = float(mc)
        except Exception:
            caps[t] = 1e10   # fallback
    total = sum(caps.values())
    return {t: v / total for t, v in caps.items()}


# ---------------------------------------------------------------------------
# Algorithm 1: Mean-Variance Optimisation
# ---------------------------------------------------------------------------

def mean_variance_optimize(
    tickers: list,
    start_date: str = None,
    end_date:   str = None,
    period_months: int = 24,
    target: str = "max_sharpe",
    min_weight: float = 0.0,
    max_weight: float = 1.0,
    risk_free_pct: float = None,
) -> dict:
    """
    Find the portfolio weights that maximise Sharpe ratio (or minimise variance).

    tickers        — list of NSE tickers
    target         — "max_sharpe" | "min_variance" | "max_return"
    min_weight     — minimum allocation per stock (0 = no floor)
    max_weight     — maximum allocation per stock (1.0 = no cap)

    Returns optimal weights, expected return, expected volatility, Sharpe.
    """
    end   = end_date   or datetime.now().strftime("%Y-%m-%d")
    start = start_date or (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")

    log_returns = _get_returns(tickers, start, end)
    valid       = [t for t in tickers if t in log_returns.columns]

    if len(valid) < 2:
        return {"error": f"Need ≥2 tickers with data. Got: {valid}"}

    log_returns = log_returns[valid]
    n           = len(valid)

    # Annualised parameters
    mu  = log_returns.mean().values * 252
    cov = _cov(log_returns)                       # Ledoit-Wolf shrinkage
    rf  = _rf(risk_free_pct)

    def neg_sharpe(w):
        port_ret = float(w @ mu)
        port_vol = float(np.sqrt(w @ cov @ w))
        if port_vol < 1e-8:
            return 0.0
        return -(port_ret - rf) / port_vol

    def port_variance(w):
        return float(w @ cov @ w)

    def neg_return(w):
        return -float(w @ mu)

    obj = {"max_sharpe": neg_sharpe,
           "min_variance": port_variance,
           "max_return": neg_return}[target]

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds      = [(min_weight, max_weight)] * n
    w0          = np.array([1 / n] * n)

    result = minimize(obj, w0, method="SLSQP",
                      bounds=bounds, constraints=constraints,
                      options={"maxiter": 1000, "ftol": 1e-9})

    if not result.success:
        return {"error": f"Optimisation failed: {result.message}"}

    w_opt   = result.x
    exp_ret = round(float(w_opt @ mu) * 100, 2)
    exp_vol = round(float(np.sqrt(w_opt @ cov @ w_opt)) * 100, 2)
    sharpe  = round((float(w_opt @ mu) - rf) / float(np.sqrt(w_opt @ cov @ w_opt)), 4)

    # Equal-weight comparison
    w_eq      = np.array([1 / n] * n)
    eq_ret    = round(float(w_eq @ mu) * 100, 2)
    eq_vol    = round(float(np.sqrt(w_eq @ cov @ w_eq)) * 100, 2)
    eq_sharpe = round((float(w_eq @ mu) - rf) / float(np.sqrt(w_eq @ cov @ w_eq)), 4)

    return {
        "algorithm":       "Mean-Variance Optimisation (Markowitz)",
        "excluded_tickers": [t for t in tickers if t not in valid],
        "target":          target,
        "tickers":         valid,
        "period":          f"{start} to {end}",
        "optimal_weights": {t: round(float(w), 4) for t, w in zip(valid, w_opt)},
        "optimal_pct":     {t: round(float(w) * 100, 2) for t, w in zip(valid, w_opt)},
        "expected_annual_return_pct": exp_ret,
        "expected_annual_vol_pct":    exp_vol,
        "expected_sharpe":            sharpe,
        "vs_equal_weight": {
            "return_pct": eq_ret,
            "vol_pct":    eq_vol,
            "sharpe":     eq_sharpe,
            "sharpe_improvement": round(sharpe - eq_sharpe, 4),
        },
        "correlation_matrix": log_returns.corr().round(3).to_dict(),
    }


# ---------------------------------------------------------------------------
# Algorithm 2: Black-Litterman with Sentiment Views
# ---------------------------------------------------------------------------

def black_litterman_optimize(
    tickers: list,
    sentiment_views: dict,
    start_date: str = None,
    end_date:   str = None,
    period_months: int = 24,
    tau: float = 0.05,
    max_weight: float = 0.35,
    risk_free_pct: float = None,
) -> dict:
    """
    Black-Litterman optimiser with FinBERT sentiment views injected as priors.

    sentiment_views: dict mapping ticker → (expected_excess_return, confidence)
      e.g. {"HDFCBANK.NS": (0.05, 0.8), "TCS.NS": (-0.03, 0.6)}
      where 0.05 means "I expect 5% excess return above equilibrium"
      and   0.8  means "I am 80% confident in this view"

    These views come directly from the alpha model's sentiment factor.

    τ (tau): scales uncertainty of the prior (typically 0.01 to 0.1).
             Smaller τ = more trust in equilibrium, less in views.
    """
    end   = end_date   or datetime.now().strftime("%Y-%m-%d")
    start = start_date or (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")

    log_returns = _get_returns(tickers, start, end)
    valid       = [t for t in tickers if t in log_returns.columns]
    if len(valid) < 2:
        return {"error": f"Need ≥2 tickers. Got: {valid}"}

    log_returns = log_returns[valid]
    n           = len(valid)

    # Annualised covariance (Ledoit-Wolf shrinkage)
    Sigma = _cov(log_returns)

    # ── Step 1: Equilibrium implied returns (π) ───────────────────────────
    # Reverse-engineer expected returns from market-cap weights
    # π = δΣw_mkt  (δ = risk aversion coefficient, typically 2.5)
    mkt_caps  = _get_market_caps(valid)
    w_mkt     = np.array([mkt_caps.get(t, 1/n) for t in valid])
    w_mkt    /= w_mkt.sum()
    delta     = 2.5   # market risk aversion (He & Litterman 1999)
    pi        = delta * Sigma @ w_mkt  # implied equilibrium excess returns

    # ── Step 2: Build views matrices P, Q, Ω ─────────────────────────────
    # Only include views for tickers that are in our valid list
    view_tickers = [t for t in sentiment_views if t in valid]
    if not view_tickers:
        # No views: use the pure market-EQUILIBRIUM implied returns π.
        # This is the whole point of Black-Litterman — sensible, market-derived
        # expected returns, NOT noisy historical means that punish fallen stocks
        # (e.g. a stock down 30% does not have a -30% expected future return).
        mu_bl = pi
    else:
        k = len(view_tickers)
        P = np.zeros((k, n))   # views matrix: k views × n assets
        Q = np.zeros(k)         # views vector: expected excess return per view
        Omega_diag = np.zeros(k)  # view uncertainty

        for i, t in enumerate(view_tickers):
            j = valid.index(t)
            P[i, j] = 1.0  # absolute view on this stock
            expected_excess, confidence = sentiment_views[t]
            Q[i] = expected_excess
            # Ω_ii = (1-confidence) × (P_i Σ P_iᵀ)  — He & Litterman uncertainty
            # High confidence → small Ω → views matter more
            view_var       = float(P[i] @ Sigma @ P[i].T)
            Omega_diag[i]  = max((1 - confidence) * view_var, 1e-8)

        Omega = np.diag(Omega_diag)

        # ── Step 3: Black-Litterman posterior expected returns ────────────────
        # μ_BL = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹ · [(τΣ)⁻¹π + PᵀΩ⁻¹Q]
        tau_sigma_inv = np.linalg.inv(tau * Sigma)
        omega_inv     = np.linalg.inv(Omega)

        A      = tau_sigma_inv + P.T @ omega_inv @ P
        b      = tau_sigma_inv @ pi + P.T @ omega_inv @ Q
        mu_bl  = np.linalg.solve(A, b)

    # ── Step 4: MVO with BL returns ───────────────────────────────────────
    def neg_sharpe(w):
        port_ret = float(w @ mu_bl)
        port_vol = float(np.sqrt(w @ Sigma @ w))
        return -(port_ret - _rf(risk_free_pct)) / port_vol if port_vol > 1e-8 else 0

    # Cap each weight at max_weight to force diversification.
    # Must be >= 1/n or no feasible solution exists (weights can't sum to 1).
    cap         = max(max_weight, 1.0 / n)
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds      = [(0.0, cap)] * n
    w0          = w_mkt.copy()

    result = minimize(neg_sharpe, w0, method="SLSQP",
                      bounds=bounds, constraints=constraints,
                      options={"maxiter": 1000})

    if not result.success:
        return {"error": f"BL optimisation failed: {result.message}"}

    w_bl    = result.x
    exp_ret = round(float(w_bl @ mu_bl) * 100, 2)
    exp_vol = round(float(np.sqrt(w_bl @ Sigma @ w_bl)) * 100, 2)
    sharpe  = round((float(w_bl @ mu_bl) - _rf(risk_free_pct))
                    / float(np.sqrt(w_bl @ Sigma @ w_bl)), 4)

    # Weight shifts vs equilibrium
    weight_shifts = {
        t: round(float(w_bl[i] - w_mkt[i]) * 100, 2)
        for i, t in enumerate(valid)
    }

    has_views = bool(view_tickers)
    return {
        "algorithm":        ("Black-Litterman (He & Litterman 1999) + FinBERT Views"
                             if has_views else
                             "Black-Litterman (market equilibrium — no views)"),
        "excluded_tickers": [t for t in tickers if t not in valid],
        "tickers":          valid,
        "period":           f"{start} to {end}",
        "tau":              tau,
        "views_injected":   {
            t: {"expected_excess_pct": round(sentiment_views[t][0]*100, 2),
                "confidence":         sentiment_views[t][1]}
            for t in view_tickers
        },
        "equilibrium_weights": {t: round(float(w_mkt[i]), 4) for i, t in enumerate(valid)},
        "bl_weights":       {t: round(float(w_bl[i]), 4) for i, t in enumerate(valid)},
        "bl_pct":           {t: round(float(w_bl[i]) * 100, 2) for i, t in enumerate(valid)},
        "weight_shifts_pct":weight_shifts,
        "implied_equilibrium_returns": {t: round(float(pi[i]) * 100, 2) for i, t in enumerate(valid)},
        "bl_posterior_returns":        {t: round(float(mu_bl[i]) * 100, 2) for i, t in enumerate(valid)},
        "expected_annual_return_pct":  exp_ret,
        "expected_annual_vol_pct":     exp_vol,
        "expected_sharpe":             sharpe,
        "interpretation": (
            (
                "Black-Litterman adjusted the equilibrium weights using your sentiment views. "
                f"Stocks with positive sentiment received higher allocations. "
                f"Largest weight increase: {max(weight_shifts, key=weight_shifts.get)} "
                f"(+{max(weight_shifts.values()):.2f}%)."
            ) if has_views else
            (
                "No views supplied, so weights follow the market-equilibrium portfolio. "
                "Expected returns are derived from market caps and risk (π = δΣw), not from "
                "noisy historical averages — which is why they stay sensible even for stocks "
                "that recently fell. Add sentiment views to tilt away from equilibrium."
            )
        ),
    }


# ---------------------------------------------------------------------------
# Algorithm 3: Efficient Frontier
# ---------------------------------------------------------------------------

def efficient_frontier(
    tickers: list,
    start_date: str = None,
    end_date:   str = None,
    period_months: int = 24,
    n_points: int = 50,
    risk_free_pct: float = None,
) -> dict:
    """
    Trace the efficient frontier for a set of NSE stocks.

    Returns 50 (risk, return) points along the frontier plus:
      - The maximum Sharpe portfolio (tangency point)
      - The minimum variance portfolio
      - Current equal-weight portfolio position

    Used to show investors where their portfolio sits vs optimal.
    """
    end   = end_date   or datetime.now().strftime("%Y-%m-%d")
    start = start_date or (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")

    log_returns = _get_returns(tickers, start, end)
    valid       = [t for t in tickers if t in log_returns.columns]
    if len(valid) < 2:
        return {"error": "Need ≥2 tickers with data"}

    log_returns = log_returns[valid]
    n    = len(valid)
    mu   = log_returns.mean().values * 252
    cov  = _cov(log_returns)                      # Ledoit-Wolf shrinkage
    rf   = _rf(risk_free_pct)

    def port_stats(w):
        r   = float(w @ mu)
        vol = float(np.sqrt(w @ cov @ w))
        s   = (r - rf) / vol if vol > 1e-8 else 0
        return r, vol, s

    # Target returns between min and max
    min_ret = mu.min()
    max_ret = mu.max()
    targets = np.linspace(min_ret, max_ret, n_points)

    frontier = []
    for target_ret in targets:
        cons = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1},
            {"type": "eq", "fun": lambda w, t=target_ret: float(w @ mu) - t},
        ]
        res = minimize(
            lambda w: float(w @ cov @ w),
            np.array([1/n] * n),
            method="SLSQP",
            bounds=[(0, 1)] * n,
            constraints=cons,
            options={"maxiter": 500},
        )
        if res.success:
            r, v, s = port_stats(res.x)
            frontier.append({
                "return_pct": round(r * 100, 2),
                "vol_pct":    round(v * 100, 2),
                "sharpe":     round(s, 4),
            })

    # Keep ONLY the efficient arm. Sweeping target returns from min to max traces
    # the whole minimum-variance bullet, whose LOWER arm (below the min-variance
    # point) is inefficient: those portfolios are dominated — same volatility,
    # less return — so no rational investor holds them and they don't belong on
    # something labelled "efficient frontier". Previously ~2/3 of the plotted
    # points were on that dominated arm, which made volatility appear to FALL as
    # return rose.
    if frontier:
        mv_idx = min(range(len(frontier)), key=lambda i: frontier[i]["vol_pct"])
        mv_ret = frontier[mv_idx]["return_pct"]
        inefficient = [p for p in frontier if p["return_pct"] < mv_ret]
        frontier = [p for p in frontier if p["return_pct"] >= mv_ret]
    else:
        inefficient = []

    # Tangency (max Sharpe)
    tang = mean_variance_optimize(valid, start_date, end_date, period_months)
    # Min variance
    min_var = mean_variance_optimize(valid, start_date, end_date, period_months,
                                     target="min_variance")
    # Equal weight
    w_eq    = np.array([1/n] * n)
    eq_r, eq_v, eq_s = port_stats(w_eq)

    return {
        "algorithm":    "Efficient Frontier (Markowitz 1952)",
        "excluded_tickers": [t for t in tickers if t not in valid],
        "tickers":      valid,
        "period":       f"{start} to {end}",
        "frontier":     frontier,          # EFFICIENT arm only (min-variance point and above)
        "inefficient_arm_points": len(inefficient),  # dominated portfolios, excluded from the plot
        "note": "Only the efficient arm is returned: portfolios below the "
                "minimum-variance point are dominated (same risk, less return).",
        "tangency_portfolio": {
            "weights":     tang.get("optimal_pct", {}),
            "return_pct":  tang.get("expected_annual_return_pct"),
            "vol_pct":     tang.get("expected_annual_vol_pct"),
            "sharpe":      tang.get("expected_sharpe"),
        },
        "min_variance_portfolio": {
            "weights":     min_var.get("optimal_pct", {}),
            "return_pct":  min_var.get("expected_annual_return_pct"),
            "vol_pct":     min_var.get("expected_annual_vol_pct"),
            "sharpe":      min_var.get("expected_sharpe"),
        },
        "equal_weight_portfolio": {
            "weights":    {t: round(100/n, 2) for t in valid},
            "return_pct": round(eq_r * 100, 2),
            "vol_pct":    round(eq_v * 100, 2),
            "sharpe":     round(eq_s, 4),
        },
    }


# ---------------------------------------------------------------------------
# Algorithm 4: Hierarchical Risk Parity (HRP) — López de Prado 2016
# ---------------------------------------------------------------------------
#
# HRP is the modern answer to Markowitz's instability. Instead of inverting
# the covariance matrix (the source of Markowitz's extreme weights), HRP:
#
#   1. TREE CLUSTERING — group stocks by correlation using hierarchical
#      clustering. Stocks that move together end up in the same branch.
#      (This is a graph/tree algorithm — same family as USACO tree problems.)
#
#   2. QUASI-DIAGONALISATION — reorder the covariance matrix so similar
#      assets sit next to each other, concentrating large values on the
#      diagonal.
#
#   3. RECURSIVE BISECTION — walk down the tree, splitting capital between
#      each pair of clusters in inverse proportion to their risk. Riskier
#      cluster gets less, safer cluster gets more.
#
# Result: diversified, stable weights that hold up far better out-of-sample
# than Markowitz — with NO matrix inversion and NO expected-return estimates.
# ---------------------------------------------------------------------------

def _ivp(cov: pd.DataFrame) -> np.ndarray:
    """Inverse-variance portfolio: weight each asset by 1/variance."""
    ivp = 1.0 / np.diag(cov.values)
    return ivp / ivp.sum()


def _cluster_variance(cov: pd.DataFrame, items: list) -> float:
    """Variance of an inverse-variance-weighted sub-portfolio (a cluster)."""
    sub = cov.loc[items, items]
    w   = _ivp(sub).reshape(-1, 1)
    return float((w.T @ sub.values @ w)[0, 0])


def _quasi_diagonal(link: np.ndarray) -> list:
    """Reorder leaves so clustered (similar) assets are adjacent."""
    link = link.astype(int)
    sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
    n_items = link[-1, 3]
    while sort_ix.max() >= n_items:
        sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
        df0 = sort_ix[sort_ix >= n_items]
        i   = df0.index
        j   = df0.values - n_items
        sort_ix[i] = link[j, 0]
        df1 = pd.Series(link[j, 1], index=i + 1)
        sort_ix = pd.concat([sort_ix, df1]).sort_index()
        sort_ix.index = range(sort_ix.shape[0])
    return sort_ix.tolist()


def _recursive_bisection(cov: pd.DataFrame, sort_ix: list) -> pd.Series:
    """Split capital top-down between clusters in inverse proportion to risk."""
    w = pd.Series(1.0, index=sort_ix)
    clusters = [sort_ix]
    while clusters:
        # Bisect each cluster with >1 element
        clusters = [c[j:k] for c in clusters
                    for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        for i in range(0, len(clusters), 2):
            c0, c1 = clusters[i], clusters[i + 1]
            v0     = _cluster_variance(cov, c0)
            v1     = _cluster_variance(cov, c1)
            alpha  = 1 - v0 / (v0 + v1)   # safer cluster gets more
            w[c0] *= alpha
            w[c1] *= (1 - alpha)
    return w


def hierarchical_risk_parity(
    tickers: list,
    start_date: str = None,
    end_date:   str = None,
    period_months: int = 24,
    risk_free_pct: float = None,
) -> dict:
    """
    Hierarchical Risk Parity optimiser (López de Prado, 2016).

    Produces diversified, robust weights using correlation-based clustering
    instead of matrix inversion. Returns weights, expected stats, the cluster
    ordering, and a comparison vs equal-weight and Markowitz.
    """
    end   = end_date   or datetime.now().strftime("%Y-%m-%d")
    start = start_date or (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")

    log_returns = _get_returns(tickers, start, end)
    valid       = [t for t in tickers if t in log_returns.columns]
    if len(valid) < 2:
        return {"error": f"Need >=2 tickers with data. Got: {valid}"}

    log_returns = log_returns[valid]
    cov  = _cov(log_returns, as_frame=True)       # Ledoit-Wolf shrinkage
    corr = log_returns.corr()

    # Step 1: distance matrix from correlation, then hierarchical clustering
    dist = np.sqrt((1 - corr) / 2.0)
    # condensed distance for scipy linkage
    condensed = squareform(dist.values, checks=False)
    link      = linkage(condensed, method="single")

    # Step 2: quasi-diagonalisation (reorder by cluster)
    sort_ix_pos = _quasi_diagonal(link)
    sort_ix     = [valid[i] for i in sort_ix_pos]

    # Step 3: recursive bisection
    weights = _recursive_bisection(cov, sort_ix)
    weights = weights.reindex(valid).fillna(0)

    # Portfolio stats
    mu      = log_returns.mean().values * 252
    w_arr   = weights.values
    exp_ret = round(float(w_arr @ mu) * 100, 2)
    exp_vol = round(float(np.sqrt(w_arr @ cov.values @ w_arr)) * 100, 2)
    sharpe  = round((float(w_arr @ mu) - _rf(risk_free_pct)) / float(np.sqrt(w_arr @ cov.values @ w_arr)), 4)

    # Equal-weight baseline
    n      = len(valid)
    w_eq   = np.array([1 / n] * n)
    eq_vol = round(float(np.sqrt(w_eq @ cov.values @ w_eq)) * 100, 2)

    return {
        "algorithm":       "Hierarchical Risk Parity (López de Prado 2016)",
        "excluded_tickers": [t for t in tickers if t not in valid],
        "tickers":         valid,
        "period":          f"{start} to {end}",
        "optimal_weights": {t: round(float(weights[t]), 4) for t in valid},
        "optimal_pct":     {t: round(float(weights[t]) * 100, 2) for t in valid},
        "cluster_order":   sort_ix,
        "expected_annual_return_pct": exp_ret,
        "expected_annual_vol_pct":    exp_vol,
        "expected_sharpe":            sharpe,
        "vs_equal_weight": {
            "vol_pct":           eq_vol,
            "vol_reduction_pct": round(eq_vol - exp_vol, 2),
        },
        "correlation_matrix": corr.round(3).to_dict(),
        "interpretation": (
            f"HRP grouped {n} stocks by correlation, then allocated capital "
            f"across clusters by risk. No single stock dominates. "
            f"Annual volatility: {exp_vol}% (vs {eq_vol}% equal-weight). "
            f"Unlike Markowitz, HRP avoids extreme concentrated weights and "
            f"holds up better on unseen data."
        ),
    }


# ---------------------------------------------------------------------------
# Convenience: auto-generate BL views from alpha model
# ---------------------------------------------------------------------------

def optimize_with_alpha_views(
    tickers: list,
    start_date: str = None,
    end_date:   str = None,
    period_months: int = 24,
    risk_free_pct: float = None,
    tau: float = 0.05,
) -> dict:
    """
    Full pipeline:
      1. Compute alpha scores for all tickers
      2. Convert scores to Black-Litterman views
      3. Run BL optimiser
      4. Compare vs equal-weight and MVO

    This is the complete original algorithm:
      FinBERT → sentiment score → BL view → optimal portfolio weights
    """
    from alpha_model import compute_alpha_score

    views = {}
    alpha_scores = {}

    print(f"  Computing alpha scores for {len(tickers)} tickers...")
    for ticker in tickers:
        try:
            result = compute_alpha_score(ticker)
            score  = result["alpha_score"]  # -100 to +100
            conf   = result["confidence"]
            alpha_scores[ticker] = score

            # Convert alpha score to expected excess return
            # score of +50 → +2.5% excess return view
            # score of -50 → -2.5% excess return view
            expected_excess = score / 100 * 0.05   # max ±5% excess view
            views[ticker] = (expected_excess, conf)
        except Exception as e:
            print(f"  Warning: could not score {ticker}: {e}")

    if not views:
        return {"error": "Could not compute alpha scores for any ticker"}

    bl_result   = black_litterman_optimize(tickers, views, start_date, end_date, period_months,
                                           tau=tau, risk_free_pct=risk_free_pct)
    mvo_result  = mean_variance_optimize(tickers, start_date, end_date, period_months)

    return {
        "pipeline":     "Alpha Score → Black-Litterman → Optimal Weights",
        "alpha_scores": alpha_scores,
        "bl_result":    bl_result,
        "mvo_result":   {
            "weights": mvo_result.get("optimal_pct"),
            "sharpe":  mvo_result.get("expected_sharpe"),
        },
        "recommendation": max(alpha_scores, key=alpha_scores.get),
        "avoid":          min(alpha_scores, key=alpha_scores.get),
    }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 65)
    print("Portfolio Optimizer — MVO + Black-Litterman + Frontier")
    print("=" * 65)

    tickers = ["HDFCBANK.NS", "TCS.NS", "RELIANCE.NS", "INFY.NS",
               "HINDUNILVR.NS", "SBIN.NS"]

    print("\n1. Mean-Variance Optimisation (max Sharpe)...")
    mvo = mean_variance_optimize(tickers, period_months=24)
    if "error" not in mvo:
        print(f"   Expected return : {mvo['expected_annual_return_pct']}%")
        print(f"   Expected vol    : {mvo['expected_annual_vol_pct']}%")
        print(f"   Expected Sharpe : {mvo['expected_sharpe']}")
        print(f"   Sharpe improvement vs equal-weight: "
              f"{mvo['vs_equal_weight']['sharpe_improvement']:+.4f}")
        print(f"\n   Optimal weights:")
        for t, w in mvo["optimal_pct"].items():
            bar = "█" * int(w / 5)
            print(f"   {t:20s}  {w:5.1f}%  {bar}")

    print("\n2. Black-Litterman with manually specified sentiment views...")
    views = {
        "HDFCBANK.NS": (0.04, 0.80),   # positive: +4% excess, 80% confident
        "TCS.NS":      (-0.02, 0.70),  # negative: -2% excess, 70% confident
        "SBIN.NS":     (0.03, 0.60),   # mildly positive
    }
    bl = black_litterman_optimize(tickers, views, period_months=24)
    if "error" not in bl:
        print(f"   BL Expected return : {bl['expected_annual_return_pct']}%")
        print(f"   BL Sharpe          : {bl['expected_sharpe']}")
        print(f"\n   Weight shifts from equilibrium:")
        for t, shift in bl["weight_shifts_pct"].items():
            arrow = "▲" if shift > 0 else "▼"
            print(f"   {arrow} {t:20s}  {shift:+.2f}%  (BL: {bl['bl_pct'][t]:.1f}%)")
        print(f"\n   {bl['interpretation']}")

    print("\n3. Efficient Frontier (15 points)...")
    frontier = efficient_frontier(tickers, period_months=24, n_points=15)
    if "error" not in frontier:
        tang = frontier["tangency_portfolio"]
        minv = frontier["min_variance_portfolio"]
        eq   = frontier["equal_weight_portfolio"]
        print(f"   Tangency portfolio : return={tang['return_pct']}%  "
              f"vol={tang['vol_pct']}%  Sharpe={tang['sharpe']}")
        print(f"   Min variance       : return={minv['return_pct']}%  "
              f"vol={minv['vol_pct']}%  Sharpe={minv['sharpe']}")
        print(f"   Equal weight       : return={eq['return_pct']}%  "
              f"vol={eq['vol_pct']}%   Sharpe={eq['sharpe']}")
        print(f"\n   Frontier points ({len(frontier['frontier'])} computed):")
        for pt in frontier["frontier"][::3]:
            print(f"   vol={pt['vol_pct']:5.1f}%  return={pt['return_pct']:5.1f}%  "
                  f"Sharpe={pt['sharpe']:.3f}")

    print("\n" + "=" * 65)
    print("portfolio_optimizer.py test complete")
    print("=" * 65)
