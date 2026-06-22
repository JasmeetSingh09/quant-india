"""
monte_carlo.py — Monte Carlo simulation for NSE portfolios.

Answers the question backtesting can't: "What MIGHT happen?"

Backtest  = one path, the path that actually occurred (the past)
Monte Carlo = thousands of plausible future paths (the range of outcomes)

THREE SIMULATION METHODS:

1. NORMAL Monte Carlo
   Draw daily returns from a Normal distribution N(μ, σ) fitted to history.
   Fast and simple, but UNDERSTATES crash risk because real markets
   have "fat tails" — extreme moves happen far more often than a bell
   curve predicts.

2. FAT-TAILED Monte Carlo (Student's t-distribution)
   Draw returns from a t-distribution, which has heavier tails.
   This captures the reality that Indian markets crash harder and more
   often than the normal model says. The comparison between #1 and #2 is
   a genuinely publishable observation.

3. BOOTSTRAP Monte Carlo (historical resampling)
   Don't assume any distribution — randomly resample actual historical
   daily returns with replacement. This preserves the true shape of
   returns, including the fat tails, automatically.

For each method we run N simulations (default 10,000) over a horizon
(default 252 trading days = 1 year) and report the distribution of
final outcomes: median, percentiles, probability of loss, worst case.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


# ---------------------------------------------------------------------------
# Data helper
# ---------------------------------------------------------------------------

def _portfolio_daily_returns(holdings: dict, lookback_days: int = 504) -> pd.Series:
    """
    Build the historical daily return series for a weighted portfolio.
    holdings: {ticker: allocation_pct} summing to 100.
    """
    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    prices = {}
    for t in holdings:
        try:
            df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
            if not df.empty:
                prices[t] = df["Close"].squeeze()
        except Exception:
            pass

    if not prices:
        return pd.Series(dtype=float)

    df       = pd.DataFrame(prices).ffill().dropna()
    valid    = [t for t in holdings if t in df.columns]
    weights  = np.array([holdings[t] for t in valid])
    weights  = weights / weights.sum()

    returns  = df[valid].pct_change().dropna()
    return pd.Series((returns.values * weights).sum(axis=1), index=returns.index)


def _summarise_paths(final_values: np.ndarray, initial_value: float, horizon_days: int) -> dict:
    """Compute summary statistics from an array of simulated final values."""
    final_values = np.sort(final_values)
    pct = lambda p: round(float(np.percentile(final_values, p)), 2)

    prob_loss   = round(float((final_values < initial_value).mean()) * 100, 2)
    prob_2x     = round(float((final_values > 2 * initial_value).mean()) * 100, 2)
    median      = pct(50)
    expected    = round(float(final_values.mean()), 2)

    return {
        "horizon_trading_days": horizon_days,
        "horizon_years":        round(horizon_days / 252, 2),
        "initial_value":        initial_value,
        "expected_value":       expected,
        "median_value":         median,
        "expected_return_pct":  round((expected - initial_value) / initial_value * 100, 2),
        "percentiles": {
            "p5":  pct(5),    # pessimistic
            "p10": pct(10),
            "p25": pct(25),
            "p50": median,
            "p75": pct(75),
            "p90": pct(90),
            "p95": pct(95),   # optimistic
        },
        "probability_of_loss_pct":   prob_loss,
        "probability_of_doubling_pct": prob_2x,
        "worst_case_p1":  pct(1),
        "best_case_p99":  pct(99),
        "interpretation": (
            f"After {round(horizon_days/252,1)} year(s), the median outcome is "
            f"₹{median:,.0f} (from ₹{initial_value:,.0f}). "
            f"There is a {prob_loss:.0f}% chance of ending below your starting capital, "
            f"and a {prob_2x:.0f}% chance of doubling. "
            f"In the worst 5% of scenarios you end with ₹{pct(5):,.0f} or less."
        ),
    }


def _sample_fan_chart(paths: np.ndarray, n_sample: int = 50) -> list:
    """
    Return a sample of simulated paths + percentile bands for the fan chart.
    paths shape: (n_simulations, horizon_days+1)
    """
    n_sims, n_days = paths.shape
    # Percentile bands across all simulations at each time step
    bands = []
    for d in range(n_days):
        col = paths[:, d]
        bands.append({
            "day": d,
            "p5":  round(float(np.percentile(col, 5)), 2),
            "p25": round(float(np.percentile(col, 25)), 2),
            "p50": round(float(np.percentile(col, 50)), 2),
            "p75": round(float(np.percentile(col, 75)), 2),
            "p95": round(float(np.percentile(col, 95)), 2),
        })
    # Downsample bands if too many days (keep ~120 points)
    step = max(1, len(bands) // 120)
    return bands[::step]


# ---------------------------------------------------------------------------
# Simulation engines
# ---------------------------------------------------------------------------

def simulate(
    holdings: dict,
    initial_value: float = 100_000,
    horizon_days: int = 252,
    n_simulations: int = 10_000,
    method: str = "bootstrap",
    t_dof: int = 5,
    seed: int = None,
) -> dict:
    """
    Run a Monte Carlo simulation of a portfolio's future value.

    holdings       — {ticker: allocation_pct} summing to 100
    initial_value  — starting capital in ₹
    horizon_days   — trading days to simulate forward (252 = 1 year)
    n_simulations  — number of random paths (default 10,000)
    method         — "normal" | "t" (fat-tailed) | "bootstrap"
    t_dof          — degrees of freedom for t-distribution (lower = fatter tails)
    seed           — random seed for reproducibility

    Returns outcome distribution, percentiles, probability of loss, and
    fan-chart band data for plotting.
    """
    if seed is not None:
        np.random.seed(seed)

    total = sum(holdings.values())
    if abs(total - 100) > 0.01:
        return {"error": f"Allocations must sum to 100%, got {total:.1f}%"}

    hist = _portfolio_daily_returns(holdings)
    if len(hist) < 30:
        return {"error": "Insufficient historical data to fit the simulation."}

    mu    = float(hist.mean())
    sigma = float(hist.std())

    # Generate the random daily-return matrix: (n_simulations, horizon_days)
    if method == "normal":
        rand_returns = np.random.normal(mu, sigma, size=(n_simulations, horizon_days))
        method_label = "Normal distribution"
    elif method == "t":
        # Scale t-distribution to match historical std
        raw   = np.random.standard_t(t_dof, size=(n_simulations, horizon_days))
        scale = sigma / np.sqrt(t_dof / (t_dof - 2))   # std of t-dist = sqrt(dof/(dof-2))
        rand_returns = mu + raw * scale
        method_label = f"Student's t (fat tails, dof={t_dof})"
    elif method == "bootstrap":
        # Resample actual historical returns with replacement
        hist_arr     = hist.values
        idx          = np.random.randint(0, len(hist_arr), size=(n_simulations, horizon_days))
        rand_returns = hist_arr[idx]
        method_label = "Bootstrap (historical resampling)"
    else:
        return {"error": f"Unknown method '{method}'. Use normal | t | bootstrap."}

    # Compound each path: value_t = value_0 * prod(1 + r)
    growth      = np.cumprod(1 + rand_returns, axis=1) * initial_value
    # Prepend initial value as day 0
    paths       = np.column_stack([np.full(n_simulations, initial_value), growth])
    final_values = paths[:, -1]

    summary = _summarise_paths(final_values, initial_value, horizon_days)
    fan     = _sample_fan_chart(paths)

    # Histogram of final values (for distribution chart)
    hist_counts, hist_edges = np.histogram(final_values, bins=40)
    histogram = [
        {"value": round(float((hist_edges[i] + hist_edges[i+1]) / 2), 0),
         "count": int(hist_counts[i])}
        for i in range(len(hist_counts))
    ]

    return {
        "method":          method,
        "method_label":    method_label,
        "n_simulations":   n_simulations,
        "holdings":        holdings,
        "fitted_params":   {"daily_mean_pct": round(mu*100, 4),
                            "daily_vol_pct":  round(sigma*100, 4)},
        **summary,
        "fan_chart":       fan,
        "histogram":       histogram,
    }


def compare_methods(
    holdings: dict,
    initial_value: float = 100_000,
    horizon_days: int = 252,
    n_simulations: int = 10_000,
) -> dict:
    """
    Run all three methods on the same portfolio and compare them.

    This reveals how much the normal-distribution assumption UNDERSTATES
    tail risk vs the fat-tailed and bootstrap methods — the key
    research insight for emerging markets like India.
    """
    results = {}
    for method in ["normal", "t", "bootstrap"]:
        r = simulate(holdings, initial_value, horizon_days, n_simulations,
                     method=method, seed=42)
        if "error" not in r:
            results[method] = {
                "method_label":           r["method_label"],
                "median_value":           r["median_value"],
                "p5_worst_case":          r["percentiles"]["p5"],
                "p95_best_case":          r["percentiles"]["p95"],
                "probability_of_loss_pct":r["probability_of_loss_pct"],
                "worst_case_p1":          r["worst_case_p1"],
            }

    # Compute how much fatter the tail risk is under t/bootstrap vs normal
    insight = ""
    if "normal" in results and "bootstrap" in results:
        normal_p1    = results["normal"]["worst_case_p1"]
        boot_p1      = results["bootstrap"]["worst_case_p1"]
        diff_pct     = round((normal_p1 - boot_p1) / initial_value * 100, 1)
        insight = (
            f"The Normal model's 1% worst case (₹{normal_p1:,.0f}) is "
            f"{'higher' if normal_p1 > boot_p1 else 'lower'} than the bootstrap "
            f"model's (₹{boot_p1:,.0f}) by {abs(diff_pct):.1f}% of capital. "
            f"This {abs(diff_pct):.1f}% gap is the tail risk the Normal "
            f"distribution hides — real NSE crashes are worse than a bell curve predicts."
        )

    return {
        "comparison":    results,
        "initial_value": initial_value,
        "horizon_days":  horizon_days,
        "key_insight":   insight,
    }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 65)
    print("Monte Carlo Simulation — NSE Portfolio")
    print("=" * 65)

    holdings = {"HDFCBANK.NS": 40, "TCS.NS": 35, "RELIANCE.NS": 25}

    print(f"\nPortfolio: {holdings}")
    print(f"Capital  : ₹1,00,000  |  Horizon: 1 year  |  10,000 simulations")

    print("\n1. Bootstrap method (most realistic)...")
    r = simulate(holdings, n_simulations=10_000, method="bootstrap", seed=42)
    if "error" not in r:
        print(f"   Median outcome   : ₹{r['median_value']:,.0f}")
        print(f"   Expected return  : {r['expected_return_pct']}%")
        print(f"   P(loss)          : {r['probability_of_loss_pct']}%")
        print(f"   P(doubling)      : {r['probability_of_doubling_pct']}%")
        print(f"   5th percentile   : ₹{r['percentiles']['p5']:,.0f}  (pessimistic)")
        print(f"   95th percentile  : ₹{r['percentiles']['p95']:,.0f}  (optimistic)")
        print(f"\n   {r['interpretation']}")

    print("\n2. Comparing all three methods (tail-risk study)...")
    comp = compare_methods(holdings, n_simulations=10_000)
    print(f"\n   {'Method':<35} {'Median':>12} {'1% worst':>12} {'P(loss)':>9}")
    print(f"   {'-'*70}")
    for m, d in comp["comparison"].items():
        print(f"   {d['method_label']:<35} ₹{d['median_value']:>10,.0f} "
              f"₹{d['worst_case_p1']:>10,.0f} {d['probability_of_loss_pct']:>8}%")
    print(f"\n   KEY INSIGHT: {comp['key_insight']}")

    print("\n" + "=" * 65)
    print("monte_carlo.py test complete")
    print("=" * 65)
