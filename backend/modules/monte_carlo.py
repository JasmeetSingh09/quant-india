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

import time
import threading
import numpy as np
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


# ---------------------------------------------------------------------------
# Data helper
# ---------------------------------------------------------------------------

_HIST_CACHE: dict = {}          # (tickers, lookback) -> (timestamp, Series)
_HIST_TTL = 30 * 60             # 30 min — intraday drift is irrelevant to a 1y sim
_HIST_LOCK = threading.Lock()


def _portfolio_daily_returns(holdings: dict, lookback_days: int = 504) -> pd.Series:
    """
    Build the historical daily return series for a weighted portfolio.
    holdings: {ticker: allocation_pct} summing to 100.

    Cached and fetched in parallel: compare_methods runs three simulations off
    the SAME history, and this used to re-download every ticker sequentially for
    each one (a 4-stock compare = 12 serial Yahoo round-trips). On a throttled
    cloud IP that download, not the simulation maths, was the entire wait.
    """
    # The key must include the WEIGHTS, not just the tickers. Keying on tickers
    # alone meant every re-weighting of the same names reused the first
    # portfolio's return series, so 55/30/15 and equal-weight simulated
    # identically — which silently made every what-if scenario report a zero
    # delta. Weights are rounded so trivial float noise still hits the cache.
    key = (tuple(sorted((t, round(float(w), 4)) for t, w in holdings.items())),
           lookback_days)
    now = time.time()
    with _HIST_LOCK:
        hit = _HIST_CACHE.get(key)
        if hit and now - hit[0] < _HIST_TTL:
            return hit[1]

    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    def _one(t):
        try:
            df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
            return t, (df["Close"].squeeze() if not df.empty else None)
        except Exception:
            return t, None

    prices = {}
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(holdings)))) as pool:
        for t, s in pool.map(_one, list(holdings)):
            if s is not None:
                prices[t] = s

    if not prices:
        return pd.Series(dtype=float)

    df       = pd.DataFrame(prices).ffill().dropna()
    valid    = [t for t in holdings if t in df.columns]
    weights  = np.array([holdings[t] for t in valid])
    weights  = weights / weights.sum()

    returns  = df[valid].pct_change().dropna()
    series   = pd.Series((returns.values * weights).sum(axis=1), index=returns.index)
    with _HIST_LOCK:
        _HIST_CACHE[key] = (time.time(), series)
    return series


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


def _sample_fan_chart(paths: np.ndarray, n_sample: int = 50, initial_value: float = None) -> list:
    """
    Return percentile bands for the fan chart.
    paths shape: (n_simulations, horizon_days) — day 1 onwards.

    Day 0 is identical for every path (everyone starts at initial_value), so it
    is prepended as a constant rather than stored as a column.
    """
    n_sims, n_days = paths.shape
    # Downsample FIRST, then take all five percentiles in one vectorised call.
    # The old version ran 5 separate np.percentile calls for every one of ~253
    # days (≈1,265 sorts of the full column) and then discarded half the result.
    step = max(1, n_days // 120)
    days = np.arange(0, n_days, step)
    if days[-1] != n_days - 1:          # always land on the horizon's final day
        days = np.append(days, n_days - 1)
    qs   = np.percentile(paths[:, days], [5, 25, 50, 75, 95], axis=0)
    out  = []
    if initial_value is not None:
        iv = round(float(initial_value), 2)
        out.append({"day": 0, "p5": iv, "p25": iv, "p50": iv, "p75": iv, "p95": iv})
    out += [
        {"day": int(d) + 1,
         "p5":  round(float(qs[0, i]), 2),
         "p25": round(float(qs[1, i]), 2),
         "p50": round(float(qs[2, i]), 2),
         "p75": round(float(qs[3, i]), 2),
         "p95": round(float(qs[4, i]), 2)}
        for i, d in enumerate(days)
    ]
    return out


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
    with_charts: bool = True,
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

    # Guard rails. The working set is n_simulations x horizon_days float64s and
    # numpy holds a few copies of it at once, so an unbounded request is a
    # memory spike, not just a slow one. These caps are far above any useful
    # setting — 50k paths already pins the percentiles to 2 decimal places.
    try:
        n_simulations = int(n_simulations)
        horizon_days  = int(horizon_days)
    except (TypeError, ValueError):
        return {"error": "n_simulations and horizon_days must be whole numbers"}
    if n_simulations < 100 or horizon_days < 1:
        return {"error": "Need at least 100 simulations and a 1-day horizon"}
    n_simulations = min(n_simulations, 50_000)
    horizon_days  = min(horizon_days, 2_520)      # 10 years

    # Capping the two independently is NOT enough — the working set is their
    # PRODUCT. 50,000 paths x 2,520 days is 126M cells (~1 GB in float64),
    # which killed the worker even though each value was within its own limit.
    # Keep the full horizon the user asked for and trim the path count instead;
    # percentiles converge on paths, so 8k paths still gives stable bands.
    MAX_CELLS = 20_000_000
    if n_simulations * horizon_days > MAX_CELLS:
        n_simulations = max(1_000, MAX_CELLS // horizon_days)

    total = sum(holdings.values())
    if abs(total - 100) > 0.01:
        return {"error": f"Allocations must sum to 100%, got {total:.1f}%"}

    # Fetch at least as much history as we intend to project, and never less
    # than three years. Previously this always pulled a fixed ~1.4 years of
    # trading data regardless of horizon, so a 3.5-year run extrapolated 2.5x
    # beyond its own sample: a window that happened to contain a 26%/yr bull
    # run produced a +124% median and a 0.48% chance of loss over 3.5 years,
    # which is not a believable outcome for three Indian equities.
    lookback = max(1095, int(horizon_days / 252 * 365 * 2))
    hist = _portfolio_daily_returns(holdings, lookback_days=lookback)
    if len(hist) < 30:
        return {"error": "Insufficient historical data to fit the simulation."}

    # Even with a longer window the sample can still be shorter than the
    # horizon. Say so rather than presenting an extrapolation as a forecast.
    history_years = len(hist) / 252
    horizon_years = horizon_days / 252
    extrapolation_warning = None
    if history_years < horizon_years:
        extrapolation_warning = (
            f"Only {history_years:.1f} years of history available for a "
            f"{horizon_years:.1f}-year projection. Outcomes beyond the sample "
            f"length assume this period's average return continues, which is a "
            f"strong assumption — treat the range as illustrative."
        )

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
        # Resample actual historical returns with replacement (i.i.d.)
        hist_arr     = hist.values
        idx          = np.random.randint(0, len(hist_arr), size=(n_simulations, horizon_days))
        rand_returns = hist_arr[idx]
        method_label = "Bootstrap (historical resampling)"
    elif method == "block":
        # BLOCK BOOTSTRAP: resample CONSECUTIVE blocks of returns instead of
        # single days. This preserves autocorrelation and volatility clustering
        # (calm stretches and stormy stretches stay intact) — far more realistic
        # than i.i.d. resampling, which shuffles those patterns away.
        hist_arr   = hist.values
        block      = max(5, min(20, horizon_days // 10 or 5))   # ~5-20 day blocks
        n_blocks   = int(np.ceil(horizon_days / block))
        max_start  = len(hist_arr) - block
        if max_start < 1:
            return {"error": "not enough history for block bootstrap"}
        starts     = np.random.randint(0, max_start, size=(n_simulations, n_blocks))
        # Build each path by stitching blocks, then trim to horizon
        rand_returns = np.empty((n_simulations, n_blocks * block), dtype=np.float32)
        for b in range(n_blocks):
            for off in range(block):
                rand_returns[:, b * block + off] = hist_arr[starts[:, b] + off]
        rand_returns = rand_returns[:, :horizon_days]
        method_label = f"Block bootstrap ({block}-day blocks — preserves vol clustering)"
    else:
        return {"error": f"Unknown method '{method}'. Use normal | t | bootstrap | block."}

    # float32 halves the working set. Returns are ~1e-2 and we only report
    # percentiles to 2 dp, so float32's ~7 significant digits is far more
    # precision than the output carries.
    if rand_returns.dtype != np.float32:
        rand_returns = rand_returns.astype(np.float32, copy=False)

    # Compound each path in place: value_t = value_0 * prod(1 + r).
    # Reusing rand_returns' buffer avoids holding a second full-size array —
    # at 50k x 252 each copy is ~100 MB.
    np.add(rand_returns, np.float32(1.0), out=rand_returns)
    np.cumprod(rand_returns, axis=1, out=rand_returns)
    rand_returns *= np.float32(initial_value)
    paths        = rand_returns
    # Summary stats go back to float64 — this vector is only n_simulations long,
    # so the precision is free.
    final_values = paths[:, -1].astype(np.float64)

    summary = _summarise_paths(final_values, initial_value, horizon_days)

    # compare_methods only reads the summary stats, so let it skip the chart
    # work entirely rather than build payloads it throws away.
    fan, histogram = [], []
    if with_charts:
        fan = _sample_fan_chart(paths, initial_value=initial_value)
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
        "history_years":   round(history_years, 2),
        "extrapolation_warning": extrapolation_warning,
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
    first_error = None
    for method in ["normal", "t", "bootstrap"]:
        # with_charts=False: only the summary stats below are read, so there is
        # no reason to build fan-chart bands and histograms three times over.
        r = simulate(holdings, initial_value, horizon_days, n_simulations,
                     method=method, seed=42, with_charts=False)
        if "error" in r:
            first_error = first_error or r["error"]
            continue
        if "error" not in r:
            results[method] = {
                "method_label":           r["method_label"],
                "median_value":           r["median_value"],
                "p5_worst_case":          r["percentiles"]["p5"],
                "p95_best_case":          r["percentiles"]["p95"],
                "probability_of_loss_pct":r["probability_of_loss_pct"],
                "worst_case_p1":          r["worst_case_p1"],
            }

    # If every method failed (e.g. allocations don't sum to 100%, or no price
    # data), surface the reason instead of returning a silently-empty table.
    if not results:
        return {"error": first_error or "Could not run any simulation method."}

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
