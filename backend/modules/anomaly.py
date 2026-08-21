"""
anomaly.py — unusual activity, reported as an observation and not as a signal.

I argued against building this, and the reason still holds: an "unusual activity"
score with no evidence that it predicts anything would be a second unvalidated
signal stacked on a first. So it is built to describe rather than to advise.

The distinction is enforced in the output. Nothing here produces a BUY, a SELL,
or a score that could be mistaken for one. It answers a narrower question that is
verifiable today: is this stock behaving differently from how it normally
behaves? That is a statement about the past, and it is either true or false —
unlike a prediction, which is neither until time passes.

Where it is genuinely useful: a stock that has just moved five standard
deviations, or traded ten times its usual volume, is a stock whose recent
fundamentals and news the model may not have caught up with yet. That is a reason
to look, not a reason to buy.
"""

from datetime import datetime, timedelta

import numpy as np


def _series(ticker: str, days: int = 200):
    try:
        import yfinance as yf
        end = datetime.now()
        start = end - timedelta(days=days + 40)
        df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                         end=end.strftime("%Y-%m-%d"), progress=False,
                         auto_adjust=True)
        if df is None or len(df) < 60:
            return None
        return df
    except Exception:
        return None


def detect(ticker: str) -> dict:
    """
    Flag behaviour that is unusual for THIS stock, against its own history.

    Compared to itself rather than to the market, because "unusual" only means
    anything relative to a baseline. A 4% move is ordinary for a small cap and
    remarkable for a large one.
    """
    ticker = (ticker or "").strip().upper()
    df = _series(ticker)
    if df is None:
        return {"ticker": ticker, "checked": False,
                "note": "Not enough history to say what is normal for this stock."}

    close = df["Close"]
    vol = df["Volume"] if "Volume" in df else None
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    if vol is not None and hasattr(vol, "columns"):
        vol = vol.iloc[:, 0]

    rets = close.pct_change().dropna()
    if len(rets) < 60:
        return {"ticker": ticker, "checked": False, "note": "Insufficient returns."}

    findings = []

    # 1. A move that is large against this stock's own volatility.
    sd = float(rets.iloc[:-1].std())
    last = float(rets.iloc[-1])
    if sd > 0:
        z = last / sd
        if abs(z) >= 3:
            findings.append({
                "kind": "price_move",
                "detail": (f"Last close moved {last*100:+.1f}%, about "
                           f"{abs(z):.1f} standard deviations for this stock. "
                           f"Its typical daily move is {sd*100:.1f}%."),
            })

    # 2. Volume far above its own norm.
    if vol is not None and len(vol.dropna()) > 40:
        v = vol.dropna()
        med = float(v.iloc[-40:-1].median())
        latest = float(v.iloc[-1])
        if med > 0 and latest > med * 4:
            findings.append({
                "kind": "volume_spike",
                "detail": (f"Traded {latest/med:.1f}x its median volume of the last "
                           f"40 sessions. Heavy volume usually means news the "
                           f"model may not have processed yet."),
            })

    # 3. Volatility regime shift within the stock's own history.
    if len(rets) > 120:
        recent = float(rets.iloc[-20:].std())
        base = float(rets.iloc[-120:-20].std())
        if base > 0 and recent > base * 2:
            findings.append({
                "kind": "volatility_shift",
                "detail": (f"Volatility over the last month is {recent/base:.1f}x "
                           f"its prior level. Risk measures built on the calmer "
                           f"period will understate what is happening now."),
            })

    # 4. A drawdown that is deep for this stock.
    curve = (1 + rets).cumprod()
    dd = float((curve.iloc[-1] / curve.max() - 1) * 100)
    if dd < -30:
        findings.append({
            "kind": "drawdown",
            "detail": (f"Currently {abs(dd):.0f}% below its high for this window. "
                       f"Deep drawdowns often coincide with fundamentals that have "
                       f"changed rather than a price that has merely fallen."),
        })

    return {
        "ticker": ticker,
        "checked": True,
        "unusual": bool(findings),
        "findings": findings,
        "summary": (f"{len(findings)} unusual behaviour(s) detected."
                    if findings else
                    "Nothing unusual — this stock is behaving the way it normally does."),
        "this_is_not_a_signal": (
            "An observation, not a recommendation. Unusual behaviour is a reason "
            "to look at a stock, never a reason to buy or sell it. Nothing here "
            "has been tested for whether it predicts anything, and it deliberately "
            "produces no score that could be mistaken for one."),
    }
