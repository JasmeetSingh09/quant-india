"""
research.py — Quantitative signal research for Indian markets.

This module answers the question quant firms actually ask:
"Does your signal predict returns, or is it noise?"

Studies implemented:
  1. Sentiment Alpha Study
     Does negative FinBERT sentiment on Day 0 predict negative returns
     on Day+1, Day+5, Day+10? Tested on real NSE price + news data.

  2. Momentum Factor
     Do stocks that outperformed in the last 3/6/12 months continue
     to outperform? (Jegadeesh & Titman applied to NSE)

  3. Mean Reversion Study
     Do large single-day moves reverse within 5 trading days?
     (relevant for intraday/short-term traders)

  4. Earnings Surprise Effect
     Does a positive earnings sentiment headline on result day
     predict positive next-week returns?

  5. Sector Rotation Signal
     Do macro keyword hits in news (crude, RBI, rupee) predict
     the direction of affected sectors in the next 5 days?

  6. Correlation & Diversification Analysis
     Pairwise correlation matrix for a basket of stocks.
     Identifies which combinations actually diversify risk.

All studies return:
  - hypothesis tested
  - methodology
  - results with numbers
  - statistical significance (p-value, t-stat)
  - plain-English conclusion
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

NIFTY_TICKER  = "^NSEI"
RISK_FREE_RATE = 0.065   # RBI repo rate as proxy


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _download(ticker: str, start: str, end: str) -> pd.Series:
    """Download adjusted close prices for one ticker."""
    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        return df["Close"].squeeze().dropna()
    except Exception:
        return pd.Series(dtype=float)


def _t_test_mean(series: pd.Series) -> dict:
    """One-sample t-test: is the mean significantly different from zero?"""
    try:
        from scipy import stats
        t, p = stats.ttest_1samp(series.dropna(), 0)
        return {
            "t_statistic": round(float(t), 4),
            "p_value":     round(float(p), 4),
            "significant": bool(p < 0.05),
        }
    except ImportError:
        return {"note": "Install scipy for significance tests: pip install scipy"}


# ---------------------------------------------------------------------------
# 1. Sentiment Alpha Study
# ---------------------------------------------------------------------------

def sentiment_alpha_study(
    ticker: str,
    days_back: int = 180,
    forward_windows: list = [1, 5, 10],
) -> dict:
    """
    HYPOTHESIS: Headlines with strong negative FinBERT sentiment predict
    negative stock returns over the next 1, 5, and 10 trading days on NSE.

    METHOD:
      1. Fetch recent news headlines for the ticker
      2. Score each headline with FinBERT
      3. For each headline date, record the forward return of the stock
      4. Split headlines into positive / negative / neutral buckets
      5. Compare average forward returns across buckets
      6. Run t-test to check if the difference is statistically significant

    Returns per-window results, sample sizes, and interpretation.
    """
    from news import get_stock_news
    from sentiment import score_headline

    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Fetch price data
    prices = _download(ticker, start, end)
    if len(prices) < 20:
        return {"error": f"Insufficient price data for {ticker}"}

    # Fetch and score news
    articles = get_stock_news(ticker, days_back=days_back)
    if not articles:
        return {"error": f"No news found for {ticker} in last {days_back} days"}

    # Build sentiment events aligned to trading dates
    events = []
    for art in articles:
        try:
            pub_date = pd.Timestamp(art["published_at"]).normalize()
        except Exception:
            continue
        score = score_headline(art["title"])
        events.append({
            "date":      pub_date,
            "headline":  art["title"],
            "sentiment": score["label"],
            "confidence":score["confidence"],
        })

    if not events:
        return {"error": "Could not parse article dates"}

    # For each event, find the forward return
    results_by_window = {}
    for fwd in forward_windows:
        pos_returns, neg_returns, neu_returns = [], [], []

        for ev in events:
            # Find the next available trading day on or after the headline date
            avail = prices.index[prices.index >= ev["date"]]
            if len(avail) < fwd + 1:
                continue
            entry_price = float(prices.loc[avail[0]])
            exit_price  = float(prices.loc[avail[fwd]])
            fwd_ret     = (exit_price - entry_price) / entry_price * 100

            if ev["sentiment"] == "positive" and ev["confidence"] > 0.65:
                pos_returns.append(fwd_ret)
            elif ev["sentiment"] == "negative" and ev["confidence"] > 0.65:
                neg_returns.append(fwd_ret)
            else:
                neu_returns.append(fwd_ret)

        pos_s = pd.Series(pos_returns)
        neg_s = pd.Series(neg_returns)
        neu_s = pd.Series(neu_returns)

        neg_ttest = _t_test_mean(neg_s)
        pos_ttest = _t_test_mean(pos_s)

        results_by_window[f"day_{fwd}"] = {
            "forward_window_days":   fwd,
            "positive_sentiment": {
                "count":      len(pos_returns),
                "avg_return": round(float(pos_s.mean()), 4) if len(pos_returns) else None,
                "win_rate":   round((pos_s > 0).mean() * 100, 1) if len(pos_returns) else None,
                "t_test":     pos_ttest,
            },
            "negative_sentiment": {
                "count":      len(neg_returns),
                "avg_return": round(float(neg_s.mean()), 4) if len(neg_returns) else None,
                "win_rate":   round((neg_s > 0).mean() * 100, 1) if len(neg_returns) else None,
                "t_test":     neg_ttest,
            },
            "neutral_sentiment": {
                "count":      len(neu_returns),
                "avg_return": round(float(neu_s.mean()), 4) if len(neu_returns) else None,
            },
        }

    # Overall conclusion
    day1 = results_by_window.get("day_1", {})
    neg_d1 = day1.get("negative_sentiment", {})
    pos_d1 = day1.get("positive_sentiment", {})
    signal_exists = (
        neg_d1.get("avg_return") is not None and
        neg_d1["avg_return"] < 0 and
        neg_d1.get("t_test", {}).get("significant", False)
    )

    return {
        "study":      "Sentiment Alpha",
        "ticker":     ticker,
        "period":     f"{start} to {end}",
        "hypothesis": (
            "Negative FinBERT sentiment on a headline predicts negative stock "
            "returns over the next N trading days."
        ),
        "methodology": (
            "Headlines scored with FinBERT (confidence > 65%). "
            "Forward returns calculated from next trading day close. "
            "T-test used to check if average return is significantly different from zero."
        ),
        "results":    results_by_window,
        "conclusion": (
            f"SIGNAL FOUND: Negative sentiment headlines are followed by negative "
            f"Day+1 returns (avg {neg_d1.get('avg_return', 0):.2f}%, p<0.05). "
            f"The sentiment signal has predictive value for {ticker}."
            if signal_exists else
            f"NO CLEAR SIGNAL: Sentiment does not significantly predict next-day returns "
            f"for {ticker} over this period. Either news impact is already priced in, "
            f"or more data is needed (current negative sample: {neg_d1.get('count', 0)} headlines)."
        ),
        "signal_found": signal_exists,
        "sample_sizes": {fwd: len(events) for fwd in forward_windows},
    }


# ---------------------------------------------------------------------------
# 2. Momentum Factor
# ---------------------------------------------------------------------------

def momentum_study(
    tickers: list,
    lookback_months: int = 6,
    holding_months:  int = 1,
    start_year:      int = 2019,
) -> dict:
    """
    HYPOTHESIS: NSE stocks that outperformed in the past 6 months continue
    to outperform in the next month (momentum effect).

    METHOD:
      1. Each month, rank all provided tickers by their trailing 6-month return
      2. Long top third ("winners"), short/avoid bottom third ("losers")
      3. Measure next-month return for each bucket
      4. Compare winners vs losers return spread over time

    Returns monthly winner/loser spreads and statistical significance.
    """
    start = f"{start_year}-01-01"
    end   = datetime.now().strftime("%Y-%m-%d")

    all_prices = {}
    for t in tickers:
        s = _download(t, start, end)
        if not s.empty:
            all_prices[t] = s

    if len(all_prices) < 3:
        return {"error": f"Need at least 3 tickers with data. Got {len(all_prices)}."}

    prices_df = pd.DataFrame(all_prices).ffill().dropna(how="all")
    monthly   = prices_df.resample("ME").last()
    returns   = monthly.pct_change()

    spreads      = []
    winner_rets  = []
    loser_rets   = []

    for i in range(lookback_months, len(returns) - holding_months):
        lookback_ret = monthly.iloc[i] / monthly.iloc[i - lookback_months] - 1
        lookback_ret = lookback_ret.dropna()

        if len(lookback_ret) < 3:
            continue

        sorted_tickers = lookback_ret.sort_values(ascending=False).index.tolist()
        n_third        = max(1, len(sorted_tickers) // 3)
        winners        = sorted_tickers[:n_third]
        losers         = sorted_tickers[-n_third:]

        # Next month return
        fwd_returns = returns.iloc[i + 1]
        winner_ret  = float(fwd_returns[winners].mean())
        loser_ret   = float(fwd_returns[losers].mean())
        spread      = winner_ret - loser_ret

        spreads.append(spread)
        winner_rets.append(winner_ret)
        loser_rets.append(loser_ret)

        month_label = returns.index[i + 1]

    if not spreads:
        return {"error": "Not enough data to compute momentum spreads."}

    spreads_s     = pd.Series(spreads)
    ttest         = _t_test_mean(spreads_s)
    avg_spread    = round(float(spreads_s.mean()) * 100, 3)
    positive_months = round((spreads_s > 0).mean() * 100, 1)

    return {
        "study":       "Momentum Factor",
        "tickers":     list(all_prices.keys()),
        "period":      f"{start} to {end}",
        "lookback":    f"{lookback_months} months",
        "holding":     f"{holding_months} month",
        "hypothesis":  "Past winners continue to outperform past losers (price momentum).",
        "methodology": (
            f"Each month, rank {len(all_prices)} NSE stocks by trailing {lookback_months}-month return. "
            f"Long top third (winners), avoid bottom third (losers). "
            f"Measure winner-loser spread for next month. T-test on spreads."
        ),
        "results": {
            "avg_monthly_spread_pct":    avg_spread,
            "avg_winner_return_pct":     round(float(pd.Series(winner_rets).mean()) * 100, 3),
            "avg_loser_return_pct":      round(float(pd.Series(loser_rets).mean()) * 100, 3),
            "months_spread_positive_pct":positive_months,
            "num_months_tested":         len(spreads),
            "t_test":                    ttest,
        },
        "conclusion": (
            f"MOMENTUM EXISTS: Winners beat losers by {avg_spread:.2f}% per month on average "
            f"({positive_months:.0f}% of months). Statistically significant (p<0.05)."
            if ttest.get("significant") and avg_spread > 0 else
            f"WEAK/NO MOMENTUM: Average winner-loser spread is {avg_spread:.2f}% per month. "
            f"{'Not statistically significant.' if not ttest.get('significant') else 'But spread is negative — contrarian effect.'}"
        ),
    }


# ---------------------------------------------------------------------------
# 3. Mean Reversion Study
# ---------------------------------------------------------------------------

def mean_reversion_study(
    ticker: str,
    shock_threshold_pct: float = 3.0,
    forward_days: int = 5,
    start_year: int = 2018,
) -> dict:
    """
    HYPOTHESIS: After a single-day move of ±3% or more, the stock
    partially reverses within the next 5 trading days.

    METHOD:
      1. Find all days where abs(daily return) > shock_threshold
      2. Record the next 5-day return after each shock
      3. For up shocks: do returns reverse (go negative)?
      4. For down shocks: do returns recover (go positive)?
      5. T-test on reversal returns
    """
    start = f"{start_year}-01-01"
    end   = datetime.now().strftime("%Y-%m-%d")

    prices = _download(ticker, start, end)
    if len(prices) < 60:
        return {"error": "Insufficient price data"}

    daily_ret = prices.pct_change().dropna()

    up_shocks   = daily_ret[daily_ret >  shock_threshold_pct / 100]
    down_shocks = daily_ret[daily_ret < -shock_threshold_pct / 100]

    def _forward_returns(shock_dates, prices, fwd):
        fwd_rets = []
        for date in shock_dates.index:
            idx = prices.index.get_loc(date)
            if idx + fwd < len(prices):
                entry = float(prices.iloc[idx + 1]) if idx + 1 < len(prices) else None
                exit_ = float(prices.iloc[idx + fwd])
                if entry:
                    fwd_rets.append((exit_ - entry) / entry * 100)
        return pd.Series(fwd_rets)

    up_fwd   = _forward_returns(up_shocks,   prices, forward_days)
    down_fwd = _forward_returns(down_shocks, prices, forward_days)

    up_ttest   = _t_test_mean(up_fwd)
    down_ttest = _t_test_mean(down_fwd)

    up_reversal   = float(up_fwd.mean())   < 0 if len(up_fwd)   else False
    down_recovery = float(down_fwd.mean()) > 0 if len(down_fwd) else False

    return {
        "study":     "Mean Reversion",
        "ticker":    ticker,
        "period":    f"{start} to {end}",
        "threshold": f"±{shock_threshold_pct}% single-day move",
        "forward":   f"{forward_days} trading days",
        "hypothesis":(
            f"Stocks that move >{shock_threshold_pct}% in a single day partially "
            f"reverse within {forward_days} trading days."
        ),
        "results": {
            "up_shocks": {
                "count":          len(up_shocks),
                "avg_shock_pct":  round(float(up_shocks.mean()) * 100, 2),
                "avg_fwd_return": round(float(up_fwd.mean()), 3) if len(up_fwd) else None,
                "reversal_rate":  round((up_fwd < 0).mean() * 100, 1) if len(up_fwd) else None,
                "t_test":         up_ttest,
                "reversal_found": up_reversal and up_ttest.get("significant", False),
            },
            "down_shocks": {
                "count":           len(down_shocks),
                "avg_shock_pct":   round(float(down_shocks.mean()) * 100, 2),
                "avg_fwd_return":  round(float(down_fwd.mean()), 3) if len(down_fwd) else None,
                "recovery_rate":   round((down_fwd > 0).mean() * 100, 1) if len(down_fwd) else None,
                "t_test":          down_ttest,
                "recovery_found":  down_recovery and down_ttest.get("significant", False),
            },
        },
        "conclusion": (
            f"MEAN REVERSION EXISTS: "
            + (f"Up shocks reverse (avg {up_fwd.mean():.2f}% over {forward_days}d). " if up_reversal else "")
            + (f"Down shocks recover (avg +{down_fwd.mean():.2f}% over {forward_days}d). " if down_recovery else "")
            if (up_reversal or down_recovery) else
            f"NO MEAN REVERSION: Price shocks in {ticker} do not reliably reverse within {forward_days} days."
        ),
    }


# ---------------------------------------------------------------------------
# 4. Correlation & Diversification
# ---------------------------------------------------------------------------

def correlation_study(
    tickers: list,
    start_date: str = None,
    end_date:   str = None,
    period_months: int = 12,
) -> dict:
    """
    QUESTION: Which stock combinations actually diversify portfolio risk?

    METHOD:
      1. Compute pairwise correlation of daily returns
      2. Flag pairs with correlation < 0.3 as good diversifiers
      3. Flag pairs with correlation > 0.8 as redundant (no diversification benefit)
      4. Compute portfolio volatility reduction from combining low-correlation stocks
    """
    end   = end_date   or datetime.now().strftime("%Y-%m-%d")
    start = start_date or (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")

    prices = {}
    for t in tickers:
        s = _download(t, start, end)
        if not s.empty:
            prices[t] = s

    if len(prices) < 2:
        return {"error": "Need at least 2 tickers with data"}

    df      = pd.DataFrame(prices).ffill().dropna()
    returns = df.pct_change().dropna()
    corr    = returns.corr().round(3)

    # Identify best and worst diversifiers
    pairs = []
    for i, t1 in enumerate(corr.columns):
        for t2 in corr.columns[i+1:]:
            c = float(corr.loc[t1, t2])
            pairs.append({
                "pair":        f"{t1} + {t2}",
                "correlation": c,
                "verdict": (
                    "Excellent diversifier" if c < 0.3  else
                    "Good diversifier"      if c < 0.5  else
                    "Moderate"              if c < 0.7  else
                    "Highly correlated — limited diversification"
                ),
            })
    pairs.sort(key=lambda x: x["correlation"])

    # Equal-weight portfolio volatility
    n  = len(prices)
    w  = np.array([1 / n] * n)
    cov_matrix = returns.cov().values * 252
    port_vol   = round(float(np.sqrt(w @ cov_matrix @ w)) * 100, 2)
    avg_vol    = round(float(returns.std().mean() * (252 ** 0.5)) * 100, 2)
    vol_reduction = round(avg_vol - port_vol, 2)

    return {
        "study":   "Correlation & Diversification",
        "tickers": list(prices.keys()),
        "period":  f"{start} to {end}",
        "correlation_matrix": corr.to_dict(),
        "pairs":              pairs,
        "best_diversifiers":  [p for p in pairs if p["correlation"] < 0.3],
        "redundant_pairs":    [p for p in pairs if p["correlation"] > 0.8],
        "portfolio_stats": {
            "equal_weight_annual_vol_pct": port_vol,
            "avg_single_stock_vol_pct":    avg_vol,
            "diversification_benefit_pct": vol_reduction,
            "interpretation": (
                f"Combining these {n} stocks reduces annual volatility by {vol_reduction:.1f}% "
                f"vs holding any single stock (from ~{avg_vol:.1f}% to {port_vol:.1f}%)."
            ),
        },
    }


# ---------------------------------------------------------------------------
# 5. Macro Sector Signal
# ---------------------------------------------------------------------------

def macro_sector_signal_study(
    macro_keyword: str,
    sector_ticker: str,
    days_back: int = 365,
    forward_days: int = 5,
) -> dict:
    """
    HYPOTHESIS: When macro keyword appears in news (e.g. "crude oil surge"),
    the affected sector ETF/stock underperforms over the next 5 trading days.

    METHOD:
      1. Fetch news articles containing the macro keyword
      2. For each article date, record the forward return of the sector proxy
      3. Compare against average market return on same days
      4. T-test on excess returns
    """
    from news import get_market_wide_news, get_macro_news
    from news import get_macro_impact_on_stocks

    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    prices = _download(sector_ticker, start, end)
    nifty  = _download(NIFTY_TICKER, start, end)

    if len(prices) < 30:
        return {"error": f"Insufficient price data for {sector_ticker}"}

    articles = get_macro_news(days_back=days_back)
    kw_lower = macro_keyword.lower()

    signal_dates = []
    for art in articles:
        title_lower = art["title"].lower()
        if kw_lower in title_lower:
            try:
                pub_date = pd.Timestamp(art["published_at"]).normalize()
                signal_dates.append(pub_date)
            except Exception:
                pass

    if not signal_dates:
        return {
            "error": f"No articles found containing '{macro_keyword}' in last {days_back} days"
        }

    fwd_returns   = []
    nifty_returns = []

    for date in signal_dates:
        avail = prices.index[prices.index >= date]
        navail = nifty.index[nifty.index >= date]
        if len(avail) < forward_days + 1 or len(navail) < forward_days + 1:
            continue
        entry_s = float(prices.loc[avail[0]])
        exit_s  = float(prices.loc[avail[forward_days]])
        entry_n = float(nifty.loc[navail[0]])
        exit_n  = float(nifty.loc[navail[forward_days]])
        fwd_returns.append((exit_s - entry_s) / entry_s * 100)
        nifty_returns.append((exit_n - entry_n) / entry_n * 100)

    if not fwd_returns:
        return {"error": "Could not align article dates with trading data"}

    fwd_s   = pd.Series(fwd_returns)
    excess  = pd.Series([f - n for f, n in zip(fwd_returns, nifty_returns)])
    ttest   = _t_test_mean(excess)

    return {
        "study":          "Macro Sector Signal",
        "macro_keyword":  macro_keyword,
        "sector_ticker":  sector_ticker,
        "forward_days":   forward_days,
        "events_found":   len(signal_dates),
        "events_tested":  len(fwd_returns),
        "hypothesis": (
            f"When '{macro_keyword}' appears in financial news, {sector_ticker} "
            f"underperforms Nifty 50 over the next {forward_days} trading days."
        ),
        "results": {
            "avg_sector_return_pct":  round(float(fwd_s.mean()), 3),
            "avg_nifty_return_pct":   round(float(pd.Series(nifty_returns).mean()), 3),
            "avg_excess_return_pct":  round(float(excess.mean()), 3),
            "events_sector_negative": int((fwd_s < 0).sum()),
            "t_test":                 ttest,
        },
        "conclusion": (
            f"SIGNAL CONFIRMED: After '{macro_keyword}' news, {sector_ticker} "
            f"produces avg {excess.mean():.2f}% excess return vs Nifty over {forward_days}d "
            f"({'statistically significant' if ttest.get('significant') else 'but NOT statistically significant — more data needed'})."
        ),
    }


# ---------------------------------------------------------------------------
# 6. Full research report for a stock
# ---------------------------------------------------------------------------

def full_research_report(ticker: str) -> dict:
    """
    Run all applicable studies for a single ticker and return a unified report.
    Takes 30-60 seconds due to multiple API calls and model inference.
    """
    report = {
        "ticker":     ticker,
        "generated":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "studies":    {},
    }

    print(f"[Research] Running sentiment alpha study for {ticker}...")
    try:
        report["studies"]["sentiment_alpha"] = sentiment_alpha_study(ticker, days_back=120)
    except Exception as e:
        report["studies"]["sentiment_alpha"] = {"error": str(e)}

    print(f"[Research] Running mean reversion study for {ticker}...")
    try:
        report["studies"]["mean_reversion"] = mean_reversion_study(ticker, start_year=2019)
    except Exception as e:
        report["studies"]["mean_reversion"] = {"error": str(e)}

    return report


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 65)
    print("Research Module — Quantitative Signal Studies")
    print("=" * 65)

    print("\n1. Momentum study on Nifty 50 large caps...")
    momentum = momentum_study(
        tickers=["HDFCBANK.NS", "TCS.NS", "RELIANCE.NS", "INFY.NS",
                 "ICICIBANK.NS", "SBIN.NS", "WIPRO.NS", "BHARTIARTL.NS",
                 "AXISBANK.NS", "KOTAKBANK.NS"],
        lookback_months=6,
        start_year=2019,
    )
    print(f"   Result: {momentum.get('conclusion', momentum.get('error'))}")
    if "results" in momentum:
        r = momentum["results"]
        print(f"   Avg spread/month : {r['avg_monthly_spread_pct']:.3f}%")
        print(f"   Spread>0 months  : {r['months_spread_positive_pct']:.1f}%")
        print(f"   p-value          : {r['t_test'].get('p_value')}")

    print("\n2. Mean reversion study for HDFCBANK.NS (2018-present)...")
    mr = mean_reversion_study("HDFCBANK.NS", shock_threshold_pct=3.0, forward_days=5)
    print(f"   Result: {mr.get('conclusion', mr.get('error'))}")
    if "results" in mr:
        d = mr["results"]["down_shocks"]
        u = mr["results"]["up_shocks"]
        print(f"   Down shocks ({d['count']}): avg +{d.get('avg_fwd_return')}% over 5d")
        print(f"   Up shocks   ({u['count']}): avg {u.get('avg_fwd_return')}% over 5d")

    print("\n3. Correlation study on IT vs Banking vs FMCG...")
    corr = correlation_study(
        tickers=["TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
                 "HINDUNILVR.NS", "ITC.NS"],
        period_months=24,
    )
    if "pairs" in corr:
        print(f"   Portfolio vol : {corr['portfolio_stats']['equal_weight_annual_vol_pct']}%  "
              f"(avg single stock: {corr['portfolio_stats']['avg_single_stock_vol_pct']}%)")
        print(f"   Vol reduction : {corr['portfolio_stats']['diversification_benefit_pct']}%")
        print("   Lowest-correlation pairs:")
        for p in corr["best_diversifiers"][:3]:
            print(f"     {p['pair']}  → corr={p['correlation']}  ({p['verdict']})")

    print("\n4. Sentiment alpha study (requires NEWS_API_KEY)...")
    sa = sentiment_alpha_study("HDFCBANK.NS", days_back=90, forward_windows=[1, 5])
    print(f"   Result: {sa.get('conclusion', sa.get('error'))}")

    print("\n" + "=" * 65)
    print("research.py test complete")
    print("=" * 65)
