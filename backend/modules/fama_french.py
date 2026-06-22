"""
fama_french.py — Fama-French 3-Factor Model for NSE stocks.

The academic gold standard of asset pricing, and exactly the vocabulary
AQR, Citadel, and Dimensional Fund Advisors use.

THE QUESTION IT ANSWERS
───────────────────────
"Is this stock's return real skill (alpha), or is it just exposure to
known risk factors?"

THE MODEL
─────────
A stock's excess return is regressed on THREE factors:

  R_stock − Rf = α + β_mkt·(R_mkt − Rf) + β_smb·SMB + β_hml·HML + ε

  α      (alpha)        — return NOT explained by the factors. Real edge.
  β_mkt  (market beta)  — sensitivity to the overall market (Nifty 50)
  β_smb  (size)         — exposure to Small-Minus-Big (small caps vs large)
  β_hml  (value)        — exposure to High-Minus-Low (value vs growth)

WHY IT MATTERS
──────────────
A stock can look like it "beats the market," but if that return just comes
from being a small-cap or a value stock, it isn't skill — it's factor
exposure you could get cheaply elsewhere. Only a statistically significant
POSITIVE alpha represents genuine outperformance.

FACTOR CONSTRUCTION (Indian market)
───────────────────────────────────
Kenneth French publishes US factors; India has no easy public feed, so we
CONSTRUCT the factors from an NSE universe the proper Fama-French way:

  Market : Nifty 50 (^NSEI) excess return
  SMB    : avg return of the smallest-third by market cap
           minus avg return of the largest-third
  HML    : avg return of the cheapest-third by P/B (value)
           minus avg return of the most expensive-third (growth)

NOTE: size/value buckets use current fundamentals as a proxy (yfinance does
not provide clean historical fundamentals). This is the standard
student/practitioner simplification and is stated as a limitation.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from scipy import stats

load_dotenv(Path(__file__).parent.parent / ".env")

NIFTY_TICKER   = "^NSEI"
RISK_FREE_RATE = 0.065   # RBI repo rate proxy

# Default universe used to build the factors (Nifty large/mid mix)
DEFAULT_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS", "LT.NS",
    "HINDUNILVR.NS", "BAJFINANCE.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
    "WIPRO.NS", "TATAMOTORS.NS", "TATASTEEL.NS", "AXISBANK.NS", "NESTLEIND.NS",
    "DABUR.NS", "MARICO.NS", "GODREJCP.NS", "TVSMOTOR.NS", "ASHOKLEY.NS",
    "FEDERALBNK.NS", "BANKBARODA.NS", "ESCORTS.NS", "CUMMINSIND.NS", "MPHASIS.NS",
]


# ---------------------------------------------------------------------------
# Build the factor return series
# ---------------------------------------------------------------------------

def build_factors(
    universe: list = None,
    start_date: str = None,
    end_date:   str = None,
    period_months: int = 36,
) -> dict:
    """
    Construct daily Market, SMB (size), and HML (value) factor returns
    from an NSE universe.

    Returns a DataFrame-like dict of the three factor series plus metadata.
    """
    universe = universe or DEFAULT_UNIVERSE
    end   = end_date   or datetime.now().strftime("%Y-%m-%d")
    start = start_date or (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")

    # Download universe prices + Nifty
    frames = {}
    for t in universe + [NIFTY_TICKER]:
        try:
            df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
            if not df.empty:
                frames[t] = df["Close"].squeeze()
        except Exception:
            pass

    prices = pd.DataFrame(frames).ffill().dropna(how="all")
    stocks = [t for t in universe if t in prices.columns]
    if len(stocks) < 6 or NIFTY_TICKER not in prices.columns:
        return {"error": "Not enough data to build factors"}

    returns = prices[stocks].pct_change().dropna()

    # Current fundamentals for bucketing (proxy)
    caps, pbs = {}, {}
    for t in stocks:
        try:
            info = yf.Ticker(t).info
            caps[t] = info.get("marketCap")
            pbs[t]  = info.get("priceToBook")
        except Exception:
            pass

    cap_stocks = [t for t in stocks if caps.get(t)]
    pb_stocks  = [t for t in stocks if pbs.get(t)]

    # SMB: small third minus big third (by market cap)
    cap_sorted = sorted(cap_stocks, key=lambda t: caps[t])
    third      = max(1, len(cap_sorted) // 3)
    small, big = cap_sorted[:third], cap_sorted[-third:]
    smb = returns[small].mean(axis=1) - returns[big].mean(axis=1)

    # HML: value (low P/B) minus growth (high P/B)
    pb_sorted    = sorted(pb_stocks, key=lambda t: pbs[t])
    third_v      = max(1, len(pb_sorted) // 3)
    value, growth = pb_sorted[:third_v], pb_sorted[-third_v:]
    hml = returns[value].mean(axis=1) - returns[growth].mean(axis=1)

    # Market excess
    daily_rf  = RISK_FREE_RATE / 252
    mkt_excess = prices[NIFTY_TICKER].pct_change().dropna() - daily_rf

    factors = pd.DataFrame({
        "MKT": mkt_excess,
        "SMB": smb,
        "HML": hml,
    }).dropna()

    return {
        "factors":      factors,
        "period":       f"{start} to {end}",
        "n_days":       len(factors),
        "small_basket": small,
        "big_basket":   big,
        "value_basket": value,
        "growth_basket":growth,
        "avg_factor_returns": {
            "MKT_annual_pct": round(float(factors["MKT"].mean() * 252 * 100), 2),
            "SMB_annual_pct": round(float(factors["SMB"].mean() * 252 * 100), 2),
            "HML_annual_pct": round(float(factors["HML"].mean() * 252 * 100), 2),
        },
    }


# ---------------------------------------------------------------------------
# Run the regression for one stock
# ---------------------------------------------------------------------------

def factor_regression(
    ticker: str,
    universe: list = None,
    period_months: int = 36,
) -> dict:
    """
    Regress a stock's excess returns on the 3 Fama-French factors.

    Returns alpha, factor betas (market/size/value loadings), t-stats,
    p-values, R², and a plain-English interpretation of whether the stock
    has genuine alpha or is just factor exposure.
    """
    fb = build_factors(universe, period_months=period_months)
    if "error" in fb:
        return fb
    factors = fb["factors"]

    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")
    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        stock_ret = df["Close"].squeeze().pct_change().dropna()
    except Exception as e:
        return {"error": f"Could not fetch {ticker}: {e}"}

    daily_rf   = RISK_FREE_RATE / 252
    y_full     = (stock_ret - daily_rf)

    # Align stock returns with factor dates
    data = factors.join(y_full.rename("Y"), how="inner").dropna()
    if len(data) < 30:
        return {"error": "Not enough overlapping data for regression"}

    Y = data["Y"].values
    X = data[["MKT", "SMB", "HML"]].values
    X_aug = np.column_stack([np.ones(len(X)), X])   # add intercept (alpha)

    # OLS via least squares
    beta, *_ = np.linalg.lstsq(X_aug, Y, rcond=None)
    y_hat    = X_aug @ beta
    resid    = Y - y_hat

    # R²
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((Y - Y.mean()) ** 2))
    r2     = 1 - ss_res / ss_tot if ss_tot else 0

    # Standard errors → t-stats → p-values
    n, k       = X_aug.shape
    sigma2     = ss_res / (n - k)
    cov        = sigma2 * np.linalg.pinv(X_aug.T @ X_aug)
    se         = np.sqrt(np.diag(cov))
    t_stats    = beta / se
    p_values   = [2 * (1 - stats.t.cdf(abs(t), df=n - k)) for t in t_stats]

    names = ["alpha", "market_beta", "size_beta_smb", "value_beta_hml"]
    coefs = {}
    for i, nm in enumerate(names):
        coefs[nm] = {
            "coefficient": round(float(beta[i]), 5),
            "t_stat":      round(float(t_stats[i]), 3),
            "p_value":     round(float(p_values[i]), 4),
            "significant": bool(p_values[i] < 0.05),
        }

    # Annualised alpha
    alpha_annual = round(float(beta[0]) * 252 * 100, 2)
    alpha_sig    = coefs["alpha"]["significant"]

    # Interpret factor tilts
    def tilt(b, pos, neg):
        if abs(b) < 0.1: return "neutral"
        return pos if b > 0 else neg

    return {
        "ticker":         ticker,
        "period":         fb["period"],
        "observations":   n,
        "r_squared":      round(r2, 4),
        "alpha_annual_pct": alpha_annual,
        "alpha_significant": alpha_sig,
        "coefficients":   coefs,
        "factor_tilts": {
            "market": tilt(beta[1], "moves with market", "defensive"),
            "size":   tilt(beta[2], "small-cap tilt", "large-cap tilt"),
            "value":  tilt(beta[3], "value tilt", "growth tilt"),
        },
        "factor_returns": fb["avg_factor_returns"],
        "interpretation": (
            (f"{ticker} shows a statistically significant alpha of {alpha_annual:+.1f}%/yr — "
             f"genuine outperformance not explained by market, size, or value exposure."
             if alpha_sig and alpha_annual > 0 else
             f"{ticker} has a significant NEGATIVE alpha of {alpha_annual:+.1f}%/yr — it "
             f"underperformed what its factor exposure would predict."
             if alpha_sig and alpha_annual < 0 else
             f"{ticker} has no statistically significant alpha (p={coefs['alpha']['p_value']}). "
             f"Its returns are essentially explained by factor exposure, not stock-picking skill.")
            + f" The model explains {r2*100:.0f}% of its return variation (R²={r2:.2f})."
        ),
        "note": (
            "Size/value buckets use current fundamentals as a proxy for historical "
            "ones — a standard simplification given yfinance data limits."
        ),
        "disclaimer": "Research model only, not financial advice.",
    }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 65)
    print("Fama-French 3-Factor Model")
    print("=" * 65)

    print("\n1. Building factors from NSE universe (may take a minute)...")
    fb = build_factors(period_months=36)
    if "error" not in fb:
        print(f"   Days        : {fb['n_days']}")
        print(f"   Factor returns (annualised):")
        for k, v in fb["avg_factor_returns"].items():
            print(f"     {k}: {v}%")
        print(f"   Small basket: {[t.replace('.NS','') for t in fb['small_basket']]}")
        print(f"   Value basket: {[t.replace('.NS','') for t in fb['value_basket']]}")

    for tk in ["HDFCBANK.NS", "TCS.NS", "BAJFINANCE.NS"]:
        print(f"\n2. Factor regression for {tk}...")
        r = factor_regression(tk, period_months=36)
        if "error" not in r:
            print(f"   R²             : {r['r_squared']}")
            print(f"   Alpha (annual) : {r['alpha_annual_pct']}%  (significant: {r['alpha_significant']})")
            c = r["coefficients"]
            print(f"   Market beta    : {c['market_beta']['coefficient']}  (t={c['market_beta']['t_stat']})")
            print(f"   Size  (SMB)    : {c['size_beta_smb']['coefficient']}  → {r['factor_tilts']['size']}")
            print(f"   Value (HML)    : {c['value_beta_hml']['coefficient']}  → {r['factor_tilts']['value']}")
            print(f"   → {r['interpretation']}")
        else:
            print(f"   {r['error']}")

    print("\n" + "=" * 65)
    print("fama_french.py test complete")
    print("=" * 65)
