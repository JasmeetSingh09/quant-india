"""
stock_compare.py — 2 to 6 stocks side by side: charts, value, quality, risk and
the model's view. Approved in docs/PROPOSAL_PRODUCT_ADDITIONS_2026-09-23.md (#2).

Reads only. Risk is measured from adjusted daily prices over the chosen period
and is past-only. Value and quality are Yahoo's current view, not point-in-time.
No row declares a winner: the frontend marks "highest" and "lowest", never
"best", because higher is not better for volatility, P/E or drawdown.
"""

import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

PERIODS = {"6m": 182, "1y": 365, "3y": 3 * 365, "5y": 5 * 365}
BENCHMARK = "^NSEI"
MIN_DAYS = 60
CACHE_TTL = 900

VALUE_FIELDS = ["pe_ratio", "forward_pe", "price_to_book", "price_to_sales", "ev_ebitda",
                "dividend_yield", "market_cap", "sector"]
QUALITY_FIELDS = ["roe", "roa", "operating_margin", "profit_margin", "revenue_growth",
                  "earnings_growth", "debt_to_equity", "current_ratio", "free_cashflow"]


def normalise(tickers):
    out = []
    for t in tickers:
        t = (t or "").strip().upper()
        if not t:
            continue
        if not t.startswith("^") and "." not in t:
            t += ".NS"
        if t not in out:
            out.append(t)
    return out


def _max_drawdown(prices: pd.Series):
    dd = prices / prices.cummax() - 1
    trough = dd.idxmin()
    peak = prices.loc[:trough].idxmax()
    return float(dd.min() * 100), str(peak)[:10], str(trough)[:10]


def _worst_month(prices: pd.Series):
    m = prices.resample("ME").last().pct_change().dropna()
    if m.empty:
        return None, None
    return float(m.min() * 100), str(m.idxmin())[:7]


def _cvar95(r: pd.Series):
    if len(r) < 20:
        return None
    cut = r.quantile(0.05)
    return float(r[r <= cut].mean() * 100)


def _beta(r: pd.Series, rb: pd.Series):
    both = pd.concat([r, rb], axis=1, join="inner").dropna()
    if len(both) < 20 or both.iloc[:, 1].var() == 0:
        return None
    return float(both.iloc[:, 0].cov(both.iloc[:, 1]) / both.iloc[:, 1].var())


def risk_block(prices: pd.Series, bench: pd.Series = None) -> dict:
    from risk_metrics import sharpe, sortino
    r = prices.pct_change().dropna()
    mdd, peak, trough = _max_drawdown(prices)
    wm, wm_month = _worst_month(prices)
    rb = bench.pct_change().dropna() if bench is not None and len(bench) else None
    sh, so = sharpe(r.values, 252), sortino(r.values, 252)
    return {
        "total_return_pct": round(float(prices.iloc[-1] / prices.iloc[0] - 1) * 100, 2),
        "volatility_pct": round(float(r.std(ddof=1) * math.sqrt(252) * 100), 2),
        "max_drawdown_pct": round(mdd, 2), "max_drawdown_peak": peak, "max_drawdown_trough": trough,
        "worst_month_pct": None if wm is None else round(wm, 2), "worst_month": wm_month,
        "cvar95_daily_pct": None if _cvar95(r) is None else round(_cvar95(r), 3),
        "beta_vs_nifty": None if rb is None or _beta(r, rb) is None else round(_beta(r, rb), 3),
        "sharpe": None if sh is None else round(sh, 3),
        "sortino": None if so is None else round(so, 3),
    }


def series_block(prices: pd.Series, weekly: bool) -> dict:
    s = prices.resample("W-FRI").last().dropna() if weekly else prices
    rebased = 100 * s / s.iloc[0]
    dd = s / s.cummax() - 1
    return {"dates": [str(d)[:10] for d in s.index],
            "rebased": [round(float(v), 3) for v in rebased.values],
            "drawdown_pct": [round(float(v) * 100, 3) for v in dd.values]}


def _model_view(ticker):
    """The latest nightly scan row: score, rank, coverage and factor scores."""
    try:
        from universe_scan import _init_db
        from db import get_conn
        _init_db()
        conn = get_conn()
        row = conn.execute(
            "SELECT scanned_at, alpha_score, signal, confidence, momentum, quality, value, sentiment "
            "FROM alpha_scan2 WHERE ticker = ? AND error IS NULL ORDER BY scanned_at DESC LIMIT 1",
            (ticker,)).fetchone()
        conn.close()
    except Exception:
        return None
    if not row:
        return None
    return {"scanned_at": row[0], "alpha_score": row[1], "signal": row[2], "data_coverage": row[3],
            "factors": {"momentum": row[4], "quality": row[5], "value": row[6], "sentiment": row[7]}}


def _fundamentals(ticker):
    try:
        from metrics import get_full_metrics, piotroski_score
        m = get_full_metrics(ticker) or {}
    except Exception:
        return None, None, None
    value = {k: m.get(k) for k in VALUE_FIELDS}
    quality = {k: m.get(k) for k in QUALITY_FIELDS}
    try:
        p = piotroski_score(ticker) or {}
        quality["piotroski"] = p.get("f_score")
        quality["piotroski_tests_run"] = p.get("inputs_available")
    except Exception:
        quality["piotroski"] = quality["piotroski_tests_run"] = None
    return value, quality, datetime.now().strftime("%Y-%m-%d")


def compare(tickers, period="1y", with_fundamentals=True) -> dict:
    tickers = normalise(tickers)
    if not 2 <= len(tickers) <= 6:
        return {"error": f"Compare 2 to 6 stocks; got {len(tickers)}."}
    if period not in PERIODS:
        return {"error": f"Period must be one of {', '.join(PERIODS)}."}
    from data_fetcher import download_close
    start = (datetime.now() - timedelta(days=PERIODS[period])).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    prices, excluded = {}, {}
    for t in tickers:
        s = download_close(t, start, end)
        s = s.dropna() if s is not None else pd.Series(dtype=float)
        if len(s) < MIN_DAYS:
            excluded[t] = f"only {len(s)} days of prices in the period (need {MIN_DAYS})"
        else:
            prices[t] = s
    if len(prices) < 2:
        return {"error": "Fewer than 2 of these stocks have enough price history for this period.",
                "excluded": excluded}

    frame = pd.DataFrame(prices).dropna()           # common trading days only
    if len(frame) < MIN_DAYS:
        return {"error": "These stocks share too few trading days in this period.", "excluded": excluded}
    bench = download_close(BENCHMARK, start, end)
    bench = bench.dropna().reindex(frame.index).ffill() if bench is not None and len(bench) else None
    if bench is not None and bench.isna().all():
        bench = None

    weekly = period in ("3y", "5y")
    included = list(frame.columns)
    out = {
        "period": period, "from": str(frame.index[0])[:10], "to": str(frame.index[-1])[:10],
        "trading_days": len(frame), "tickers": included, "excluded": excluded,
        "series": {t: series_block(frame[t], weekly) for t in included},
        "benchmark": None if bench is None else {
            "ticker": BENCHMARK, "label": "Nifty 50 (price index, excludes dividends)",
            **series_block(bench.dropna(), weekly)},
        "risk": {t: risk_block(frame[t], bench) for t in included},
        "correlation": {a: {b: round(float(v), 3) for b, v in row.items()}
                        for a, row in frame.pct_change().dropna().corr().to_dict().items()},
        "model": {t: _model_view(t) for t in included},
        "notes": {
            "risk": f"Measured over {period} ({str(frame.index[0])[:10]} to {str(frame.index[-1])[:10]}); past only.",
            "fundamentals": "Value and quality figures are Yahoo's current view, not point-in-time.",
            "beta": "Beta is computed here from daily prices against the Nifty 50, not taken from Yahoo.",
            "highlights": "Rows mark the highest and lowest values. Higher is not better for every row, so no row names a winner.",
            "model": "Momentum is the only factor that has passed a historical test; the others and the combined score are untested.",
        },
    }
    if with_fundamentals:
        out["value"], out["quality"] = {}, {}
        for t in included:
            v, q, asof = _fundamentals(t)
            out["value"][t], out["quality"][t] = v, q
            out["fundamentals_as_of"] = asof
        sectors = {(out["value"].get(t) or {}).get("sector") for t in included} - {None}
        out["notes"]["sectors"] = ("These stocks are in different sectors, so their valuation multiples are "
                                   "not directly comparable." if len(sectors) > 1 else None)
    return out


class _NotCached(Exception):
    pass


def compare_cached(tickers, period="1y") -> dict:
    """compare(), cached 15 minutes per ticker set and period. An error is
    returned but never cached, so a failed download is retried next time."""
    from swr_cache import cached
    tickers = normalise(tickers)
    key = f"stock_compare:{','.join(sorted(tickers))}:{period}"

    def _fn():
        r = compare(tickers, period)
        if "error" in r:
            raise _NotCached(r)
        return r

    try:
        return cached(key, CACHE_TTL, _fn)
    except _NotCached as e:
        return e.args[0]
