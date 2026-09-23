"""
correlation_time.py: does diversification hold up when the market falls?

A single correlation matrix averages calm and stressed months together, which
hides the thing that hurts investors: holdings that looked unrelated tend to
fall together in a crash. This reports correlation through time instead.

- The rolling 12-month average pairwise correlation of the holdings.
- The rolling correlation of the three most correlated pairs.
- Average pairwise correlation in calm months versus falling months, where a
  falling month is one in which the Nifty 50 fell 5% or more. The split is
  defined by the market, never by the holdings' own returns, so it cannot be
  tuned by the choice of portfolio. The threshold was fixed in
  docs/PROPOSAL_PRODUCT_ADDITIONS_2026-09-23.md before anything was computed.

What it must say beside the numbers:
- Correlation measured in volatile months is mechanically higher (Forbes and
  Rigobon, 2002), so part of any calm-to-falling rise is that effect. The
  figures are measured, not adjusted.
- Fewer than MIN_GROUP_MONTHS months in a group gives no number for it.
- Missing history excludes a ticker; it is never filled.

The regime model is deliberately not used: it is fitted over the full Nifty
history, so its label for a past month uses later data.
"""

from datetime import datetime

import numpy as np
import pandas as pd

WINDOW_MONTHS = 12
FALL_THRESHOLD = -0.05          # Nifty 50 monthly return at or below this = falling month
MIN_GROUP_MONTHS = 6
MIN_TICKERS, MAX_TICKERS = 2, 15
INDEX_TICKER = "^NSEI"

NOTE_FORBES_RIGOBON = (
    "Correlation measured in volatile months is mechanically higher than in "
    "calm months, even when the stocks' underlying relationship is unchanged "
    "(Forbes and Rigobon, 2002). Part of any rise in falling months is that "
    "effect. These figures are measured, not adjusted.")
NOTE_PAST = "Past correlation does not guarantee future correlation."


def _monthly_returns(series: pd.Series) -> pd.Series:
    s = series.dropna()
    if s.empty:
        return s
    s.index = pd.to_datetime(s.index)
    return s.resample("ME").last().pct_change().dropna()


def _avg_pairwise(frame: pd.DataFrame):
    """Mean of the off-diagonal correlations, or None if not computable."""
    if frame.shape[1] < 2 or len(frame) < 3:
        return None
    c = frame.corr().values
    iu = np.triu_indices_from(c, k=1)
    vals = c[iu]
    vals = vals[np.isfinite(vals)]
    return float(vals.mean()) if len(vals) else None


def _group(frame: pd.DataFrame, months: list) -> dict:
    n = len(months)
    if n < MIN_GROUP_MONTHS:
        return {"months": n, "avg_correlation": None,
                "note": f"Too few months to compare ({n}; at least {MIN_GROUP_MONTHS} needed).",
                "month_list": [m.strftime("%Y-%m") for m in months]}
    v = _avg_pairwise(frame.loc[months])
    return {"months": n, "avg_correlation": None if v is None else round(v, 3),
            "month_list": [m.strftime("%Y-%m") for m in months]}


def correlation_over_time(tickers: list, months: int = 36, loader=None) -> dict:
    """
    tickers: 2-15 symbols; months: how many recent months to report.
    loader(ticker, start) -> daily adjusted close Series (defaults to
    data_fetcher.download_close; replaced in tests).
    """
    tickers = [t.strip().upper() for t in (tickers or []) if t and t.strip()]
    tickers = list(dict.fromkeys(tickers))
    if not (MIN_TICKERS <= len(tickers) <= MAX_TICKERS):
        return {"error": f"Give between {MIN_TICKERS} and {MAX_TICKERS} different tickers."}
    months = int(max(12, min(months, 120)))

    if loader is None:
        from data_fetcher import download_close as _dc

        def loader(t, start):
            return _dc(t, start)

    # One extra window of history so the first reported month has a full
    # rolling window behind it, plus a month for the first return.
    start = (pd.Timestamp(datetime.now()) - pd.DateOffset(months=months + WINDOW_MONTHS + 2)
             ).strftime("%Y-%m-%d")

    rets, excluded = {}, []
    for t in tickers:
        try:
            m = _monthly_returns(loader(t, start))
        except Exception as e:
            excluded.append({"ticker": t, "reason": f"could not load prices ({type(e).__name__})"})
            continue
        if len(m) < WINDOW_MONTHS + 1:
            excluded.append({"ticker": t, "reason": f"only {len(m)} months of price history"})
            continue
        rets[t] = m
    if len(rets) < MIN_TICKERS:
        return {"error": "Fewer than two tickers have enough price history.",
                "excluded": excluded}

    # Only months every included ticker has: nothing is filled.
    frame = pd.DataFrame(rets).dropna()
    if len(frame) < WINDOW_MONTHS + 1:
        return {"error": "The tickers do not share enough months of history.",
                "excluded": excluded}

    report = frame.index[-months:] if len(frame) > months else frame.index

    rolling = []
    for end in report:
        pos = frame.index.get_loc(end)
        if pos + 1 < WINDOW_MONTHS:
            continue
        v = _avg_pairwise(frame.iloc[pos + 1 - WINDOW_MONTHS:pos + 1])
        rolling.append({"month": end.strftime("%Y-%m"),
                        "avg_correlation": None if v is None else round(v, 3)})

    win = frame.loc[report]
    cols = list(frame.columns)
    pairs = []
    full = win.corr()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = full.iloc[i, j]
            if np.isfinite(v):
                pairs.append((float(v), cols[i], cols[j]))
    pairs.sort(reverse=True)
    top_pairs = []
    for v, a, b in pairs[:3]:
        series = []
        for end in report:
            pos = frame.index.get_loc(end)
            if pos + 1 < WINDOW_MONTHS:
                continue
            w = frame.iloc[pos + 1 - WINDOW_MONTHS:pos + 1]
            c = w[a].corr(w[b])
            series.append({"month": end.strftime("%Y-%m"),
                           "correlation": None if not np.isfinite(c) else round(float(c), 3)})
        top_pairs.append({"pair": [a, b], "correlation_over_period": round(v, 3),
                          "rolling": series})

    split = {"available": False,
             "reason": "Nifty 50 prices unavailable, so falling months cannot be identified."}
    try:
        idx = _monthly_returns(loader(INDEX_TICKER, start))
    except Exception:
        idx = pd.Series(dtype=float)
    idx = idx.reindex(report).dropna()
    if len(idx) >= MIN_GROUP_MONTHS:
        falling = [m for m in idx.index if idx[m] <= FALL_THRESHOLD]
        calm = [m for m in idx.index if idx[m] > FALL_THRESHOLD]
        f, c = _group(win, falling), _group(win, calm)
        rise = (round(f["avg_correlation"] - c["avg_correlation"], 3)
                if f["avg_correlation"] is not None and c["avg_correlation"] is not None else None)
        split = {"available": True,
                 "rule": f"Falling month: the Nifty 50 fell {abs(FALL_THRESHOLD):.0%} or more that month.",
                 "falling": f, "calm": c, "rise_in_falling_months": rise,
                 "months_without_index_data": int(len(report) - len(idx))}

    return {
        "tickers": cols,
        "excluded": excluded,
        "months_reported": len(report),
        "first_month": report[0].strftime("%Y-%m"),
        "last_month": report[-1].strftime("%Y-%m"),
        "window_months": WINDOW_MONTHS,
        "rolling_avg_correlation": rolling,
        "top_pairs": top_pairs,
        "calm_vs_falling": split,
        "notes": [NOTE_FORBES_RIGOBON, NOTE_PAST,
                  "Monthly returns from adjusted closing prices. Only months every "
                  "included stock has are used; nothing is filled in."],
    }
