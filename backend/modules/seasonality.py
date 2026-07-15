"""
seasonality.py — calendar-effect analysis for an NSE index/stock.

Tests whether returns depend on the month of the year (the "Sell in May" family
of anomalies): average monthly return, hit rate, and a t-stat per calendar month
over a long history, plus a summer (May-Oct) vs winter (Nov-Apr) split.

Honest by design: with 12 months tested, some will look significant by chance —
the output says so.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def seasonality_analysis(ticker: str = "^NSEI", years: int = 20) -> dict:
    """Monthly seasonality for `ticker` (default Nifty 50) over `years` of history."""
    import yfinance as yf
    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        close = df["Close"].squeeze().dropna()
    except Exception as e:
        return {"error": f"could not fetch {ticker}: {e}"}
    if len(close) < 250:
        return {"error": "not enough history"}

    m = close.resample("ME").last()
    ret = m.pct_change().dropna()
    ret.index = pd.to_datetime(ret.index)

    rows = []
    for mo in range(1, 13):
        r = ret[ret.index.month == mo]
        if len(r) == 0:
            continue
        mean = float(r.mean())
        se   = float(r.std(ddof=1) / np.sqrt(len(r))) if len(r) > 1 else 0.0
        t    = mean / se if se > 0 else 0.0
        rows.append({
            "month":        _MONTHS[mo - 1],
            "avg_return_pct": round(mean * 100, 2),
            "hit_rate_pct": round(float((r > 0).mean()) * 100, 1),
            "years":        int(len(r)),
            "t_stat":       round(t, 2),
            "significant":  bool(abs(t) > 1.96),
        })

    best  = max(rows, key=lambda x: x["avg_return_pct"])
    worst = min(rows, key=lambda x: x["avg_return_pct"])

    # "Sell in May": summer (May-Oct) vs winter (Nov-Apr)
    summer = ret[ret.index.month.isin([5, 6, 7, 8, 9, 10])]
    winter = ret[ret.index.month.isin([11, 12, 1, 2, 3, 4])]
    diff = float(winter.mean() - summer.mean())
    diff_se = float(np.sqrt(winter.var(ddof=1) / len(winter) + summer.var(ddof=1) / len(summer)))
    diff_t = diff / diff_se if diff_se > 0 else 0.0

    n_sig = sum(1 for r in rows if r["significant"])
    return {
        "ticker":  ticker,
        "years":   years,
        "n_months_observed": int(len(ret)),
        "monthly": rows,
        "best_month":  best["month"],
        "worst_month": worst["month"],
        "sell_in_may": {
            "winter_avg_pct": round(float(winter.mean()) * 100, 2),
            "summer_avg_pct": round(float(summer.mean()) * 100, 2),
            "winter_minus_summer_pct": round(diff * 100, 2),
            "t_stat": round(diff_t, 2),
            "significant": bool(abs(diff_t) > 1.96),
        },
        "interpretation": (
            f"Best month historically: {best['month']} ({best['avg_return_pct']}% avg); "
            f"worst: {worst['month']} ({worst['avg_return_pct']}%). "
            f"{n_sig} of 12 months are individually significant — "
            + ("about what you'd expect from chance alone with 12 tests, so treat "
               "single-month effects skeptically."
               if n_sig <= 2 else
               "more than chance would predict, but multiple-testing still applies.")
        ),
        "caveat": "12 months tested at once → multiple-comparison risk; calendar effects "
                  "are famously unstable out-of-sample. Descriptive, not a trading rule.",
    }


if __name__ == "__main__":
    import json, warnings
    warnings.filterwarnings("ignore")
    r = seasonality_analysis()
    print(json.dumps({k: v for k, v in r.items() if k != "monthly"}, indent=2))
    for row in r.get("monthly", []):
        print(row)
