"""
garch_vol.py — GJR-GARCH(1,1,1) volatility forecasting for NSE stocks.

Unlike returns (near-unpredictable), VOLATILITY is genuinely forecastable: it
clusters — calm periods follow calm, storms follow storms. We use GJR-GARCH
(the asymmetric variant, o=1), which captures the *leverage effect*: bad news
raises volatility more than equally-sized good news — a well-documented feature
of equity markets. This is the standard tool on every risk desk.

This module forecasts next-day volatility and tests it HONESTLY against a naive
baseline (trailing rolling std) using proper out-of-sample 1-step-ahead
forecasts. Verdict = does the model actually beat naive?
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def _returns_pct(ticker: str, years: int = 5) -> pd.Series:
    start = f"{datetime.now().year - years}-01-01"
    px = yf.download(ticker, start=start, progress=False, auto_adjust=True)["Close"].squeeze()
    return (px.pct_change().dropna() * 100.0)   # arch works best on % returns


def forecast_vol(ticker: str, horizon: int = 5) -> dict:
    """
    Fit GARCH(1,1) on a stock and forecast volatility for the next `horizon` days.
    Returns the annualised forecast and the current (latest) conditional vol.
    """
    from arch import arch_model
    r = _returns_pct(ticker)
    if len(r) < 250:
        return {"error": "not enough data"}

    # GJR-GARCH(1,1,1): the o=1 term captures the LEVERAGE EFFECT — markets
    # react more violently to bad news than good news, so a negative return
    # raises tomorrow's volatility more than a positive one. Plain GARCH misses this.
    am  = arch_model(r, vol="Garch", p=1, o=1, q=1, dist="normal")
    res = am.fit(disp="off")
    fc  = res.forecast(horizon=horizon, reindex=False)
    daily_var = fc.variance.values[-1]                       # next h days, in %^2
    avg_daily_vol = float(np.sqrt(daily_var.mean()))         # % per day
    annualised = round(avg_daily_vol * np.sqrt(252), 2)      # % per year

    cond = res.conditional_volatility
    # Long-run (unconditional) variance for GJR-GARCH: omega / (1 - alpha - beta - gamma/2)
    p = res.params
    persistence = (p.get("alpha[1]", 0) + p.get("beta[1]", 0) + p.get("gamma[1]", 0) / 2)
    long_run = float(np.sqrt(p.get("omega", 0) / max(1 - persistence, 1e-6)) * np.sqrt(252))
    return {
        "ticker": ticker,
        "model": "GJR-GARCH(1,1,1)",
        "horizon_days": horizon,
        "forecast_daily_vol_pct": round(avg_daily_vol, 3),
        "forecast_annual_vol_pct": annualised,
        "current_daily_vol_pct": round(float(cond.iloc[-1]), 3),
        "long_run_annual_vol_pct": round(long_run, 2),
        "leverage_effect": round(float(p.get("gamma[1]", 0)), 4),
        "interpretation": (
            f"GJR-GARCH expects {ticker} to have ~{annualised}% annualised volatility over the "
            f"next {horizon} days. It captures the leverage effect — bad news raises risk more "
            f"than good news. Volatility clusters, so this adapts to current market stress."
        ),
    }


def test_vs_naive(ticker: str, test_days: int = 150) -> dict:
    """
    Honest out-of-sample test: do GARCH 1-day-ahead variance forecasts predict
    realised volatility better than a naive trailing-std forecast?

    Metric: MSE between the forecast variance and the realised squared return,
    plus correlation with next-day |return|. Lower MSE / higher corr = better.
    """
    from arch import arch_model
    r = _returns_pct(ticker)
    if len(r) < 400:
        return {"error": "not enough data"}

    split_idx = len(r) - test_days
    split_obs = r.index[split_idx]

    # GJR-GARCH: fit on the training portion, produce OOS 1-step forecasts over the test
    am  = arch_model(r, vol="Garch", p=1, o=1, q=1, dist="normal")
    res = am.fit(disp="off", last_obs=split_obs)
    fc  = res.forecast(horizon=1, start=split_obs, reindex=False)
    garch_var = fc.variance.values.flatten()          # predicted next-day variance

    # Naive: trailing 21-day variance as the forecast for next day
    naive_var = (r.rolling(21).var().shift(1)).iloc[split_idx:split_idx + len(garch_var)].values

    # Realised proxy: actual squared returns on those days
    realised = (r.iloc[split_idx:split_idx + len(garch_var)].values) ** 2

    # Align lengths + drop NaNs
    m = min(len(garch_var), len(naive_var), len(realised))
    g, n, a = garch_var[:m], naive_var[:m], realised[:m]
    mask = ~(np.isnan(g) | np.isnan(n) | np.isnan(a))
    g, n, a = g[mask], n[mask], a[mask]

    garch_mse = float(np.mean((g - a) ** 2))
    naive_mse = float(np.mean((n - a) ** 2))
    garch_corr = float(np.corrcoef(g, a)[0, 1])
    naive_corr = float(np.corrcoef(n, a)[0, 1])

    garch_wins = garch_mse < naive_mse
    return {
        "ticker": ticker,
        "test_days": int(mask.sum()),
        "garch_mse": round(garch_mse, 2),
        "naive_mse": round(naive_mse, 2),
        "garch_corr_with_realised": round(garch_corr, 4),
        "naive_corr_with_realised": round(naive_corr, 4),
        "winner": "GARCH" if garch_wins else "Naive",
        "garch_beats_naive": garch_wins,
        "verdict": (
            f"GARCH MSE {round(garch_mse,1)} vs Naive {round(naive_mse,1)}. "
            + ("GARCH predicts volatility better — worth keeping."
               if garch_wins else
               "GARCH did not beat the naive baseline here.")
        ),
    }


if __name__ == "__main__":
    print("=" * 60)
    print("GARCH(1,1) volatility forecasting — honest OOS test")
    print("=" * 60)
    for tk in ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]:
        print(f"\n--- {tk} ---")
        t = test_vs_naive(tk)
        if "error" in t:
            print("  ", t["error"]); continue
        print(f"   GARCH MSE: {t['garch_mse']}  | Naive MSE: {t['naive_mse']}  -> {t['winner']}")
        print(f"   GARCH corr: {t['garch_corr_with_realised']}  | Naive corr: {t['naive_corr_with_realised']}")
        f = forecast_vol(tk)
        if "error" not in f:
            print(f"   Forecast annual vol: {f['forecast_annual_vol_pct']}%  (current daily {f['current_daily_vol_pct']}%)")
