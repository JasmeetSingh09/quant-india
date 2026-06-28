"""
overfitting.py — Is a backtest's performance REAL, or just luck?

Implements López de Prado / Bailey (2014) tools that institutional quants use
to avoid fooling themselves:

  - Probabilistic Sharpe Ratio (PSR): probability the TRUE Sharpe is > a
    benchmark, accounting for sample length, skew, and fat tails.
  - Deflated Sharpe Ratio (DSR): PSR but ALSO corrected for how many strategies
    you tried — because if you test 500 variations, one looks great by luck.

These let every backtest report "this result is X% likely to be real, not luck."
"""

import numpy as np
from scipy.stats import norm, skew as _skew, kurtosis as _kurtosis

EULER_GAMMA = 0.5772156649


def _sharpe_per_period(returns: np.ndarray) -> float:
    """Non-annualised Sharpe (per observation) — what the PSR/DSR formula needs."""
    sd = returns.std(ddof=1)
    return float(returns.mean() / sd) if sd > 0 else 0.0


def probabilistic_sharpe_ratio(returns, benchmark_sharpe: float = 0.0) -> dict:
    """
    PSR — probability the true (per-period) Sharpe exceeds benchmark_sharpe,
    given the sample's length, skew, and kurtosis.
    """
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    T = len(r)
    if T < 10:
        return {"error": "need >= 10 return observations"}

    sr  = _sharpe_per_period(r)
    g3  = float(_skew(r))                 # skewness
    g4  = float(_kurtosis(r, fisher=False))  # kurtosis (normal = 3)

    denom = np.sqrt(1 - g3 * sr + ((g4 - 1) / 4) * sr ** 2)
    if denom <= 0:
        denom = 1e-9
    psr = float(norm.cdf(((sr - benchmark_sharpe) * np.sqrt(T - 1)) / denom))

    return {
        "psr": round(psr, 4),
        "per_period_sharpe": round(sr, 4),
        "skew": round(g3, 3),
        "kurtosis": round(g4, 3),
        "n_obs": T,
    }


def deflated_sharpe_ratio(returns, n_trials: int = 1,
                          trial_sharpe_std: float = None) -> dict:
    """
    DSR — like PSR, but the benchmark is the Sharpe you'd expect to achieve by
    LUCK ALONE after trying n_trials strategies. If DSR is high despite many
    trials, the edge is probably real.

    trial_sharpe_std: std of Sharpe ratios across the strategies you tried.
      If unknown, we estimate it from the sampling error of the Sharpe estimator.
    """
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    T = len(r)
    if T < 10:
        return {"error": "need >= 10 return observations"}
    n_trials = max(1, int(n_trials))

    # Estimate dispersion of trial Sharpes if not provided (sampling error proxy)
    if trial_sharpe_std is None or trial_sharpe_std <= 0:
        trial_sharpe_std = 1.0 / np.sqrt(T - 1)

    if n_trials > 1:
        # Expected maximum Sharpe under the null from N independent trials
        z1 = norm.ppf(1 - 1.0 / n_trials)
        z2 = norm.ppf(1 - 1.0 / (n_trials * np.e))
        sr_benchmark = trial_sharpe_std * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)
    else:
        sr_benchmark = 0.0

    psr_at_benchmark = probabilistic_sharpe_ratio(r, benchmark_sharpe=sr_benchmark)
    if "error" in psr_at_benchmark:
        return psr_at_benchmark

    dsr = psr_at_benchmark["psr"]
    is_real = dsr > 0.95   # 95% confidence the edge survives multiple testing

    return {
        "deflated_sharpe": round(dsr, 4),
        "n_trials": n_trials,
        "luck_benchmark_sharpe": round(float(sr_benchmark), 4),
        "per_period_sharpe": psr_at_benchmark["per_period_sharpe"],
        "annualised_sharpe": round(psr_at_benchmark["per_period_sharpe"] * np.sqrt(252), 3),
        "skew": psr_at_benchmark["skew"],
        "kurtosis": psr_at_benchmark["kurtosis"],
        "n_obs": psr_at_benchmark["n_obs"],
        "edge_is_real": bool(is_real),
        "verdict": (
            f"Deflated Sharpe = {dsr:.0%}: after accounting for {n_trials} trial(s), "
            + ("this edge is very likely REAL, not luck." if is_real
               else "this result is likely LUCK — not statistically convincing once you "
                    "account for how many strategies were tried.")
        ),
    }


def analyze_ticker(ticker: str, n_trials: int = 1, years: int = 3) -> dict:
    """Compute PSR/DSR for buy-and-hold of a ticker over the last `years`."""
    import yfinance as yf
    from datetime import datetime
    start = f"{datetime.now().year - years}-01-01"
    try:
        px = yf.download(ticker, start=start, progress=False, auto_adjust=True)["Close"].squeeze()
        rets = px.pct_change().dropna().values
    except Exception as e:
        return {"error": f"could not fetch {ticker}: {e}"}
    res = deflated_sharpe_ratio(rets, n_trials=n_trials)
    if "error" not in res:
        res["ticker"] = ticker
        res["years"] = years
    return res


if __name__ == "__main__":
    print("=" * 60)
    print("Testing overfitting.py (Deflated Sharpe Ratio)")
    print("=" * 60)
    rng = np.random.default_rng(42)

    # A genuinely good strategy (positive drift), long sample
    good = rng.normal(0.0008, 0.01, 2000)
    print("\n1. Good strategy, 1 trial:")
    d = deflated_sharpe_ratio(good, n_trials=1)
    print(f"   annual SR {d['annualised_sharpe']} | DSR {d['deflated_sharpe']} | real: {d['edge_is_real']}")

    print("\n2. SAME strategy but found after trying 500 strategies:")
    d = deflated_sharpe_ratio(good, n_trials=500)
    print(f"   luck benchmark SR {d['luck_benchmark_sharpe']} | DSR {d['deflated_sharpe']} | real: {d['edge_is_real']}")
    print(f"   -> {d['verdict']}")

    # A pure-noise strategy that happens to look ok (cherry-picked)
    noise = rng.normal(0.0003, 0.012, 300)
    print("\n3. Marginal strategy, short sample, 200 trials:")
    d = deflated_sharpe_ratio(noise, n_trials=200)
    print(f"   annual SR {d['annualised_sharpe']} | DSR {d['deflated_sharpe']} | real: {d['edge_is_real']}")

    print("\n4. PSR edge case (too few obs):", probabilistic_sharpe_ratio([0.01,0.02]).get("error"))
    print("\nDone.")
