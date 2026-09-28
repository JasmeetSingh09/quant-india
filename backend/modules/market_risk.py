"""
market_risk.py — is the market's recent volatility above or below its usual level?

Replaces the Bull / Bear / Sideways label on the dashboard (owner approval
2026-09-28). A pre-registered test found the HMM regime label tracked single
days: a median run of 1 day over 2008-2026, with 99% of "Bull" days simply up
days (docs/REGIME_DETECTOR_RESULT_2026-09-28.md).

This rule was confirmed on four markets it was not chosen on
(docs/PREREG_MARKET_RISK_SIGNAL_2026-09-28.md). After an "Elevated" day, the
next month's realised volatility was higher on Nifty Bank, the S&P 500, the
FTSE 100 and the Nikkei 225 (+4.6 to +6.4 points, all p < 1e-5). It showed no
reliable link to the next month's return, so it says nothing about direction.

The rule, unchanged from the test:
  vol20    = standard deviation of the last 20 daily returns
  Elevated if vol20 > median of vol20 over the last 252 trading days
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

TICKER = "^NSEI"
VOL_WINDOW = 20
MEDIAN_WINDOW = 252
HISTORY_DAYS = 90
CACHE_TTL = 1800

EVIDENCE = {
    "test": "docs/PREREG_MARKET_RISK_SIGNAL_2026-09-28.md",
    "result": "docs/market_risk_confirm_2026-09-28.json",
    "summary": ("Confirmed on Nifty Bank, S&P 500, FTSE 100 and Nikkei 225: after an Elevated day, "
                "the next month's volatility was 4.6 to 6.4 points (annualised) higher. No reliable "
                "link to the next month's return."),
}
MEANING = {
    "Elevated": ("Recent volatility is above its one-year typical level. Elevated periods have tended "
                 "to stay volatile over the next month. It does not forecast direction."),
    "Normal": ("Recent volatility is at or below its one-year typical level. Calm periods have tended "
               "to stay calmer over the next month. It does not forecast direction."),
}


def classify(closes: pd.Series) -> pd.DataFrame:
    """Per-day vol20, its one-year median, and the state. NaN where history is short."""
    r = closes.pct_change()
    vol20 = r.rolling(VOL_WINDOW).std()
    med = vol20.rolling(MEDIAN_WINDOW).median()
    state = pd.Series(np.where(vol20 > med, "Elevated", "Normal"), index=closes.index)
    state[vol20.isna() | med.isna()] = None
    return pd.DataFrame({"close": closes, "ret": r, "vol20": vol20, "median": med, "state": state})


def summarise(df: pd.DataFrame) -> dict:
    df = df.dropna(subset=["state"])
    if df.empty:
        return {"error": "Not enough history to measure market risk"}
    last = df.iloc[-1]
    states = df["state"].tolist()
    run = 1
    for s in reversed(states[:-1]):
        if s != states[-1]:
            break
        run += 1
    ann = np.sqrt(252) * 100
    hist = df.tail(HISTORY_DAYS)
    return {
        "state": last["state"],
        "as_of": str(df.index[-1])[:10],
        "last_day_return_pct": round(float(last["ret"]) * 100, 2),
        "volatility_20d_pct": round(float(last["vol20"]) * ann, 1),
        "typical_volatility_pct": round(float(last["median"]) * ann, 1),
        "days_in_state": run,
        "meaning": MEANING[last["state"]],
        "rule": ("Elevated when the last 20 days' volatility is above its median over the last "
                 "252 trading days."),
        "evidence": EVIDENCE,
        "history": [{"date": str(d)[:10], "state": s, "volatility_20d_pct": round(float(v) * ann, 1)}
                    for d, s, v in zip(hist.index, hist["state"], hist["vol20"])],
    }


def _download(ticker: str) -> pd.Series:
    import yfinance as yf
    # end is EXCLUSIVE in yf.download: tomorrow, so today's close is included
    # (the regime detector left it out; found 2026-09-28).
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=800)).strftime("%Y-%m-%d")
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    return df["Close"].squeeze().dropna()


def market_risk(ticker: str = TICKER) -> dict:
    from swr_cache import cached

    # Failures raise, so the cache never stores an error: a failed refresh keeps
    # serving the last good answer, and a failed first call is retried next time.
    def _compute():
        closes = _download(ticker)
        if len(closes) < VOL_WINDOW + MEDIAN_WINDOW + 1:
            raise ValueError("Not enough history to measure market risk")
        out = summarise(classify(closes))
        out["ticker"] = ticker
        return out

    try:
        return cached(f"market_risk:{ticker}", CACHE_TTL, _compute)
    except Exception as e:
        return {"error": f"Market risk unavailable: {e}"}
