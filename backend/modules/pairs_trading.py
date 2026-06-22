"""
pairs_trading.py — Statistical Arbitrage (Pairs Trading) for NSE stocks.

THE classic quant strategy — how Renaissance, D.E. Shaw and Morgan Stanley's
original quant desk made their name. Market-neutral: profits whether the
market goes up or down.

THE IDEA
────────
Two stocks that are economically linked (e.g. HDFC Bank & ICICI Bank) tend to
move together. Their price *spread* is mean-reverting. When the spread
stretches abnormally wide, bet it will snap back:

  - Spread too HIGH  → SHORT the expensive one, LONG the cheap one
  - Spread too LOW   → LONG the expensive one, SHORT the cheap one
  - Spread back to normal → close both, bank the convergence

THE MATH
────────
1. COINTEGRATION (Engle-Granger test)
   Correlation isn't enough — two stocks can be correlated but drift apart.
   Cointegration tests whether a linear combination of the two is *stationary*
   (mean-reverting). We use the Engle-Granger test (p < 0.05 = cointegrated).

2. HEDGE RATIO (β)
   OLS regression: price_A = α + β·price_B. β tells you how many shares of B
   to trade against each share of A so the position is market-neutral.

3. SPREAD & Z-SCORE
   spread = price_A − β·price_B
   z = (spread − mean) / std
   Trade when |z| crosses a threshold (entry), close when it reverts (exit).

4. HALF-LIFE OF MEAN REVERSION (Ornstein-Uhlenbeck)
   How many days the spread takes to revert halfway to its mean. Short
   half-life = the pair reverts quickly = better for trading.

NOTE: signal model only, not financial advice.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from itertools import combinations
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


# ---------------------------------------------------------------------------
# Data helper
# ---------------------------------------------------------------------------

def _prices(tickers: list, start: str, end: str) -> pd.DataFrame:
    frames = {}
    for t in tickers:
        try:
            df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
            if not df.empty:
                frames[t] = df["Close"].squeeze()
        except Exception:
            pass
    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames).dropna()


def _hedge_ratio(a: pd.Series, b: pd.Series) -> float:
    """OLS slope of a on b (how many units of b per unit of a)."""
    return float(np.polyfit(b.values, a.values, 1)[0])


def _half_life(spread: pd.Series) -> float:
    """Ornstein-Uhlenbeck half-life of mean reversion (in trading days)."""
    lag   = spread.shift(1).dropna()
    delta = (spread - spread.shift(1)).dropna()
    lag   = lag.loc[delta.index]
    beta  = np.polyfit(lag.values, delta.values, 1)[0]
    if beta >= 0:
        return float("inf")   # not mean-reverting
    return float(-np.log(2) / beta)


# ---------------------------------------------------------------------------
# 1. Find cointegrated pairs
# ---------------------------------------------------------------------------

def find_cointegrated_pairs(
    tickers: list,
    start_date: str = None,
    end_date:   str = None,
    period_months: int = 24,
    pvalue_threshold: float = 0.05,
) -> dict:
    """
    Scan all pairs in a list of tickers and find the cointegrated ones.

    Returns pairs sorted by cointegration p-value (lower = stronger).
    A p-value < 0.05 means the pair is statistically cointegrated and
    suitable for pairs trading.
    """
    from statsmodels.tsa.stattools import coint

    end   = end_date   or datetime.now().strftime("%Y-%m-%d")
    start = start_date or (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")

    prices = _prices(tickers, start, end)
    valid  = list(prices.columns)
    if len(valid) < 2:
        return {"error": "Need >=2 tickers with data"}

    results = []
    for a, b in combinations(valid, 2):
        try:
            score, pvalue, _ = coint(prices[a], prices[b])
            corr = float(prices[a].corr(prices[b]))
            results.append({
                "pair":        f"{a} / {b}",
                "stock_a":     a,
                "stock_b":     b,
                "pvalue":      round(float(pvalue), 4),
                "correlation": round(corr, 3),
                "cointegrated": bool(pvalue < pvalue_threshold),
            })
        except Exception:
            pass

    results.sort(key=lambda x: x["pvalue"])
    cointegrated = [r for r in results if r["cointegrated"]]

    return {
        "period":            f"{start} to {end}",
        "tickers_tested":    valid,
        "pairs_tested":      len(results),
        "cointegrated_count":len(cointegrated),
        "all_pairs":         results,
        "tradeable_pairs":   cointegrated,
        "interpretation": (
            f"Found {len(cointegrated)} cointegrated pair(s) out of {len(results)} tested. "
            f"Cointegrated pairs have a mean-reverting spread suitable for pairs trading."
            if cointegrated else
            "No cointegrated pairs found in this set. Try stocks from the same sector "
            "(e.g. HDFCBANK + ICICIBANK, or TCS + INFY)."
        ),
    }


# ---------------------------------------------------------------------------
# 2. Analyse a single pair (current signal)
# ---------------------------------------------------------------------------

def analyze_pair(
    stock_a: str,
    stock_b: str,
    period_months: int = 12,
    entry_z: float = 2.0,
    exit_z:  float = 0.5,
) -> dict:
    """
    Analyse a pair and return the current trading signal.

    Computes hedge ratio, spread, z-score, cointegration p-value, half-life,
    and tells you what the strategy says to do RIGHT NOW.
    """
    from statsmodels.tsa.stattools import coint

    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")

    prices = _prices([stock_a, stock_b], start, end)
    if stock_a not in prices.columns or stock_b not in prices.columns:
        return {"error": f"Could not fetch both {stock_a} and {stock_b}"}

    a, b   = prices[stock_a], prices[stock_b]
    beta   = _hedge_ratio(a, b)
    spread = a - beta * b
    mean   = float(spread.mean())
    std    = float(spread.std())
    zscore = (spread - mean) / std
    current_z = float(zscore.iloc[-1])

    try:
        _, pvalue, _ = coint(a, b)
    except Exception:
        pvalue = None

    half_life = _half_life(spread)

    # Current signal
    if current_z > entry_z:
        signal = f"SHORT spread: SELL {stock_a}, BUY {stock_b}"
        action = "short"
    elif current_z < -entry_z:
        signal = f"LONG spread: BUY {stock_a}, SELL {stock_b}"
        action = "long"
    elif abs(current_z) < exit_z:
        signal = "CLOSE / FLAT — spread near its mean"
        action = "flat"
    else:
        signal = "HOLD — spread between entry and exit bands"
        action = "hold"

    # z-score history for charting
    z_hist = [
        {"date": str(d.date()), "z": round(float(z), 3)}
        for d, z in zscore.items()
    ]
    step = max(1, len(z_hist) // 180)

    return {
        "stock_a":        stock_a,
        "stock_b":        stock_b,
        "period":         f"{start} to {end}",
        "hedge_ratio":    round(beta, 4),
        "cointegration_pvalue": round(float(pvalue), 4) if pvalue is not None else None,
        "is_cointegrated": bool(pvalue is not None and pvalue < 0.05),
        "half_life_days": round(half_life, 1) if half_life != float("inf") else None,
        "current_zscore": round(current_z, 3),
        "entry_threshold": entry_z,
        "exit_threshold":  exit_z,
        "signal":         signal,
        "action":         action,
        "zscore_history": z_hist[::step],
        "interpretation": (
            f"The spread is {abs(current_z):.1f} standard deviations "
            f"{'above' if current_z > 0 else 'below'} its mean. "
            + (f"This pair reverts halfway to its mean in ~{half_life:.0f} trading days. "
               if half_life != float('inf') else "")
            + (f"Signal: {signal}." if action in ('long','short') else
               "No trade right now — wait for the spread to stretch past the entry band.")
        ),
        "disclaimer": "Signal model only, not financial advice.",
    }


# ---------------------------------------------------------------------------
# 3. Backtest a pairs strategy
# ---------------------------------------------------------------------------

def backtest_pair(
    stock_a: str,
    stock_b: str,
    period_months: int = 36,
    entry_z: float = 2.0,
    exit_z:  float = 0.5,
    lookback: int = 60,
) -> dict:
    """
    Backtest a market-neutral pairs trading strategy.

    Uses a rolling z-score (lookback window). Enters when |z| > entry_z,
    exits when |z| < exit_z. Returns performance vs a market-neutral baseline.
    """
    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")

    prices = _prices([stock_a, stock_b], start, end)
    if stock_a not in prices.columns or stock_b not in prices.columns:
        return {"error": f"Could not fetch both {stock_a} and {stock_b}"}

    a, b = prices[stock_a], prices[stock_b]
    beta = _hedge_ratio(a, b)
    spread = a - beta * b

    # Rolling z-score
    roll_mean = spread.rolling(lookback).mean()
    roll_std  = spread.rolling(lookback).std()
    zscore    = ((spread - roll_mean) / roll_std).dropna()

    # Spread daily returns (per unit spread)
    spread_ret = spread.diff().loc[zscore.index] / (a.loc[zscore.index].abs() + beta * b.loc[zscore.index].abs())

    # Generate positions: +1 long spread, -1 short spread, 0 flat
    position = pd.Series(0.0, index=zscore.index)
    pos = 0
    trades = 0
    for i, z in enumerate(zscore.values):
        if pos == 0:
            if z > entry_z:   pos = -1; trades += 1
            elif z < -entry_z: pos = 1; trades += 1
        elif pos == 1 and z >= -exit_z:
            pos = 0
        elif pos == -1 and z <= exit_z:
            pos = 0
        position.iloc[i] = pos

    # Strategy return = yesterday's position * today's spread return
    strat_ret = position.shift(1).fillna(0) * spread_ret
    strat_ret = strat_ret.dropna()

    if len(strat_ret) < 5:
        return {"error": "Not enough data to backtest"}

    cum = (1 + strat_ret).cumprod()
    total_return = round(float(cum.iloc[-1] - 1) * 100, 2)
    sharpe = round(float(strat_ret.mean() / strat_ret.std() * np.sqrt(252)), 3) if strat_ret.std() > 0 else 0
    win_rate = round(float((strat_ret[strat_ret != 0] > 0).mean()) * 100, 1) if (strat_ret != 0).any() else 0
    roll_max = cum.cummax()
    max_dd = round(float(((cum - roll_max) / roll_max).min()) * 100, 2)

    equity = [{"date": str(d.date()), "value": round(float(v), 4)}
              for d, v in cum.items()]
    step = max(1, len(equity) // 180)

    return {
        "stock_a":        stock_a,
        "stock_b":        stock_b,
        "period":         f"{start} to {end}",
        "hedge_ratio":    round(beta, 4),
        "entry_z":        entry_z,
        "exit_z":         exit_z,
        "lookback_days":  lookback,
        "total_return_pct": total_return,
        "sharpe_ratio":   sharpe,
        "max_drawdown_pct": max_dd,
        "num_trades":     trades,
        "win_rate_pct":   win_rate,
        "equity_curve":   equity[::step],
        "interpretation": (
            f"The pairs strategy on {stock_a}/{stock_b} returned {total_return}% over "
            f"{period_months} months with a Sharpe of {sharpe} across {trades} trades. "
            f"Because it is market-neutral (long one, short the other), it can profit "
            f"even when the overall market falls."
        ),
        "disclaimer": "Backtest only, not financial advice. Excludes shorting costs.",
    }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 65)
    print("Pairs Trading / Statistical Arbitrage")
    print("=" * 65)

    print("\n1. Finding cointegrated pairs among banking stocks...")
    banks = ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS"]
    res = find_cointegrated_pairs(banks, period_months=24)
    print(f"   {res.get('interpretation')}")
    for p in res.get("tradeable_pairs", [])[:5]:
        print(f"   {p['pair']:30s}  p={p['pvalue']}  corr={p['correlation']}")

    print("\n2. Analysing HDFCBANK / ICICIBANK current signal...")
    a = analyze_pair("HDFCBANK.NS", "ICICIBANK.NS")
    if "error" not in a:
        print(f"   Hedge ratio    : {a['hedge_ratio']}")
        print(f"   Cointegrated   : {a['is_cointegrated']} (p={a['cointegration_pvalue']})")
        print(f"   Half-life      : {a['half_life_days']} days")
        print(f"   Current z      : {a['current_zscore']}")
        print(f"   Signal         : {a['signal']}")

    print("\n3. Backtesting HDFCBANK / ICICIBANK pairs strategy...")
    bt = backtest_pair("HDFCBANK.NS", "ICICIBANK.NS", period_months=36)
    if "error" not in bt:
        print(f"   Total return : {bt['total_return_pct']}%")
        print(f"   Sharpe       : {bt['sharpe_ratio']}")
        print(f"   Max drawdown : {bt['max_drawdown_pct']}%")
        print(f"   Trades       : {bt['num_trades']}  | win rate {bt['win_rate_pct']}%")

    print("\n" + "=" * 65)
    print("pairs_trading.py test complete")
    print("=" * 65)
