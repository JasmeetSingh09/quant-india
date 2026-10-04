"""
stock_analysis.py — one stock's statement history (fundamentals over the
years) and its price indicators (technicals), for the stock page. Requested by
the owner on 2026-10-04.

Reads only, and describes; it never recommends.

- Statement figures are Yahoo's latest values, which may be restated. They are
  not the accounts as first published, so nothing here is point-in-time and
  none of it may be used in a backtest.
- The indicators are the standard textbook formulas. This project has not
  tested any of them for predictive power, so they are never shown as buy or
  sell signals, and the readings say what an indicator measures, not what to do.
- A figure Yahoo does not have is None, never 0, and a ratio with a missing
  input is None too.
"""

import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

CRORE = 1e7
TECH_PERIODS = {"3m": 92, "6m": 182, "1y": 365, "2y": 730}
WARMUP_DAYS = 320           # calendar days fetched before the window so a 200-day average exists from bar one
MIN_BARS = 30
FUND_TTL = 6 * 3600
TECH_TTL = 900

UNTESTED = ("These indicators describe past prices. This project has not tested any of them for "
            "predictive power, so they are not buy or sell signals.")
NOT_PIT = ("Yahoo's latest figures, which can include later restatements. They are not the accounts "
           "as first published, so they are not point-in-time.")

# Yahoo row names, first match wins.
INCOME_ROWS = {
    "revenue": ("Total Revenue", "Operating Revenue"),
    "operating_income": ("Operating Income",),
    "ebitda": ("EBITDA", "Normalized EBITDA"),
    "net_income": ("Net Income Common Stockholders", "Net Income"),
    "eps_diluted": ("Diluted EPS", "Basic EPS"),
}
BALANCE_ROWS = {
    "total_assets": ("Total Assets",),
    "equity": ("Stockholders Equity", "Common Stock Equity"),
    "total_debt": ("Total Debt",),
    "cash": ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"),
}
CASHFLOW_ROWS = {
    "operating_cash_flow": ("Operating Cash Flow",),
    "capex": ("Capital Expenditure",),
    "free_cash_flow": ("Free Cash Flow",),
}
IN_CRORE = {"revenue", "operating_income", "ebitda", "net_income", "total_assets", "equity",
            "total_debt", "cash", "operating_cash_flow", "capex", "free_cash_flow"}


# ── helpers ──────────────────────────────────────────────────────────────────

def _num(v):
    """A finite float, or None. Never turns a gap into 0."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _ratio(a, b):
    return None if a is None or b is None or b == 0 else a / b


def _rows(df, wanted):
    """{period_end: {field: value}} from a Yahoo statement frame."""
    out = {}
    if df is None or getattr(df, "empty", True):
        return out
    for field, names in wanted.items():
        name = next((n for n in names if n in df.index), None)
        if name is None:
            continue
        for col, v in df.loc[name].items():
            out.setdefault(pd.Timestamp(col).normalize(), {})[field] = _num(v)
    return out


def _fy_label(ts):
    # Indian companies close their year in March: the year ending 31 Mar 2026 is FY2026.
    return f"FY{ts.year}" if ts.month == 3 else ts.strftime("%b %Y")


def _yahoo_statements(ticker):
    import yfinance as yf
    tk = yf.Ticker(ticker)
    try:
        from data_fetcher import get_info
        ccy = (get_info(ticker) or {}).get("financialCurrency")
    except Exception:
        ccy = None
    return {"income": tk.income_stmt, "balance": tk.balance_sheet, "cashflow": tk.cashflow,
            "quarterly": tk.quarterly_income_stmt, "currency": ccy}


def _yahoo_ohlcv(ticker, start, end):
    import yfinance as yf
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):           # one ticker still comes back two-level
        df.columns = df.columns.get_level_values(0)
    return df[["Open", "High", "Low", "Close", "Volume"]]


# Injectable, so the tests run offline against known frames.
STATEMENTS = _yahoo_statements
OHLCV = _yahoo_ohlcv


# ── fundamentals over the years ──────────────────────────────────────────────

def fundamentals_history(ticker):
    try:
        st = STATEMENTS(ticker)
    except Exception as e:
        return {"error": f"Could not fetch statements for {ticker}: {type(e).__name__}"}
    # Shown in the company's own reporting currency. Infosys and HCL Tech report in
    # US dollars; labelling their figures "Rs crore" was off by ~88x. Converting past
    # years at today's rate would distort growth, so they are not converted.
    ccy = (st.get("currency") or "INR").upper()
    unit = CRORE if ccy == "INR" else 1e6
    money_label = "Rs crore" if ccy == "INR" else f"{ccy} million"
    years = {}
    for part, wanted in (("income", INCOME_ROWS), ("balance", BALANCE_ROWS), ("cashflow", CASHFLOW_ROWS)):
        for ts, vals in _rows(st.get(part), wanted).items():
            years.setdefault(ts, {}).update(vals)
    years = {ts: v for ts, v in years.items() if any(x is not None for x in v.values())}
    if not years:
        return {"error": f"Yahoo has no annual statements for {ticker}."}

    annual, prev = [], None
    for ts in sorted(years):
        v = years[ts]
        row = {"period_end": ts.strftime("%Y-%m-%d"), "label": _fy_label(ts)}
        for k in list(INCOME_ROWS) + list(BALANCE_ROWS) + list(CASHFLOW_ROWS):
            x = v.get(k)
            row[k] = None if x is None else (_crore(x, unit) if k in IN_CRORE else round(x, 2))
        rev, ni, oi, eq = v.get("revenue"), v.get("net_income"), v.get("operating_income"), v.get("equity")
        # A margin is a share of revenue, so it only exists when revenue is positive. Investment
        # companies can report negative revenue (losses on holdings); a "margin" of that is noise.
        row["net_margin_pct"] = _pct(_ratio(ni, rev)) if rev and rev > 0 else None
        row["operating_margin_pct"] = _pct(_ratio(oi, rev)) if rev and rev > 0 else None
        row["roe_pct"] = _pct(_ratio(ni, eq)) if eq and eq > 0 else None
        row["debt_to_equity"] = _round(_ratio(v.get("total_debt"), eq) if eq and eq > 0 else None, 2)
        # Growth only between consecutive fiscal years, both present: a gap year
        # would otherwise show two years of growth as one.
        consecutive = prev is not None and 300 <= (ts - prev[0]).days <= 430
        for k in ("revenue", "net_income"):
            a, b = v.get(k), prev[1].get(k) if consecutive else None
            # Growth from a loss or a negative base has no meaning as a percentage, so it is left blank.
            row[f"{k}_growth_pct"] = _pct((a - b) / b) if a is not None and b is not None and b > 0 else None
        annual.append(row)
        prev = (ts, v)

    quarterly = []
    for ts, v in sorted(_rows(st.get("quarterly"), INCOME_ROWS).items()):
        if not any(x is not None for x in v.values()):
            continue
        q = {"period_end": ts.strftime("%Y-%m-%d"), "label": ts.strftime("%b %Y")}
        for k in ("revenue", "operating_income", "net_income"):
            x = v.get(k)
            q[k] = None if x is None else _crore(x, unit)
        q["eps_diluted"] = _round(v.get("eps_diluted"), 2)
        qr = v.get("revenue")
        q["net_margin_pct"] = _pct(_ratio(v.get("net_income"), qr)) if qr and qr > 0 else None
        quarterly.append(q)

    plain = {"revenue": "revenue", "operating_income": "operating income", "net_income": "net profit",
             "equity": "equity", "operating_cash_flow": "cash from operations"}
    missing = sorted({plain[k] for r in annual for k, x in r.items() if x is None and k in plain})
    return {
        "ticker": ticker,
        "as_of": datetime.now().strftime("%Y-%m-%d"),
        "source": "Yahoo Finance",
        "currency": ccy,
        "units": {"money": money_label, "eps": f"{'Rs' if ccy == 'INR' else ccy} per share",
                  "ratios": "percent unless named otherwise"},
        "annual": annual,
        "quarterly": quarterly,
        "notes": {
            "point_in_time": NOT_PIT,
            "roe": "Return on equity here is the year's profit divided by year-end equity.",
            "currency": (f"This company reports in {ccy}. Figures are in {money_label} as reported, not "
                         "converted to rupees, so exchange-rate moves do not distort growth.") if ccy != "INR" else None,
            "gaps": (f"Yahoo leaves some figures blank for this company ({', '.join(missing)}); "
                     "they are shown as gaps, not zero.") if missing else None,
            "eps_break": _eps_break(annual),
            "margin_outliers": _margin_outliers(annual),
            "banks": ("Banks and lenders report no operating income or EBITDA in the same sense, so those rows "
                      "can be empty for them. Their cash flow is driven by deposits and loans, so free cash "
                      "flow does not mean for a bank what it means for other companies."),
        },
    }


def _eps_break(annual):
    """A year where EPS moves by a factor of about 2 or more while profit barely moves.

    That is the mark of a bonus issue or split that Yahoo applied to some years
    and not others, so EPS on either side of it is not comparable. Said, never
    corrected: the true share counts are not in this data.
    """
    for p, r in zip(annual, annual[1:]):
        e0, e1, n0, n1 = p["eps_diluted"], r["eps_diluted"], p["net_income"], r["net_income"]
        if None in (e0, e1, n0, n1) or e0 <= 0 or e1 <= 0 or n0 <= 0 or n1 <= 0:
            continue
        eps_ratio, profit_ratio = e1 / e0, n1 / n0
        if (eps_ratio <= 0.6 or eps_ratio >= 1.67) and 0.7 <= profit_ratio <= 1.5:
            return (f"EPS moved from Rs {e0:,.2f} ({p['label']}) to Rs {e1:,.2f} ({r['label']}) while net profit "
                    f"changed by only {(profit_ratio - 1) * 100:+.0f}%. That usually means a bonus issue, split or "
                    f"merger changed the number of shares and the figures are adjusted for it in some years but not "
                    f"others, so EPS before and after {r['label']} is not comparable.")
    return None


MARGIN_CHART_LIMIT = 100.0      # percent; beyond this the page keeps the figure in its table but not on the chart


def _margin_outliers(annual):
    """Years whose net or operating margin is beyond +/-100%: profit or loss larger than revenue.

    The figure is correct arithmetic and stays in the response; the page leaves it
    off the margin chart (owner decision 2026-10-04) and shows this note instead.
    """
    years = [r["label"] for r in annual
             if any(r[k] is not None and abs(r[k]) > MARGIN_CHART_LIMIT for k in ("net_margin_pct", "operating_margin_pct"))]
    if not years:
        return None
    return (f"In {', '.join(years)} the margin is beyond 100% either way: profit or loss was larger than revenue. "
            "That happens when most of the profit comes from other income or holdings in other companies, or when "
            "revenue is very small, so a margin means little here. Those years are left off the margin chart; "
            "the figures table shows them.")


def _crore(x, unit=CRORE):
    """Money in the display unit (crore for rupees, million otherwise). Two decimals
    normally, but full precision below 0.01 of a unit, so a company with Rs 29,000
    of revenue is not shown as 0."""
    c = x / unit
    return round(c, 2) if abs(c) >= 0.01 else round(c, 7)


def _pct(x):
    return None if x is None else round(x * 100, 2)


def _round(x, n):
    return None if x is None else round(x, n)


# ── technical indicators ─────────────────────────────────────────────────────

def indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Standard indicators on a daily OHLCV frame (columns Open High Low Close Volume)."""
    c, h, l = df["Close"], df["High"], df["Low"]
    out = pd.DataFrame(index=df.index)
    for n in (20, 50, 200):
        out[f"sma{n}"] = c.rolling(n).mean()
    out["ema20"] = c.ewm(span=20, adjust=False).mean()
    mid, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    out["bb_mid"], out["bb_upper"], out["bb_lower"] = mid, mid + 2 * sd, mid - 2 * sd

    # RSI, Wilder's smoothing (alpha = 1/14), the original definition.
    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = gain / loss
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.where(loss != 0, 100.0).where(~((loss == 0) & (gain == 0)))    # all gains: 100; flat: undefined
    out["rsi14"] = rsi.where(gain.notna())

    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    out["macd"] = ema12 - ema26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]

    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    out["vol_avg20"] = df["Volume"].rolling(20).mean()
    return out


def _last_cross(a: pd.Series, b: pd.Series):
    """Date a last moved from one side of b to the other, and the side it is on now."""
    diff = (a - b).dropna()
    if diff.empty:
        return None, None
    side = np.sign(diff)
    side = side[side != 0]
    if side.empty:
        return None, None
    changes = side[side != side.shift()]
    since = str(changes.index[-1])[:10] if len(changes) > 1 else None
    return ("above" if side.iloc[-1] > 0 else "below"), since


def readings(df: pd.DataFrame, ind: pd.DataFrame) -> list:
    """Plain-language descriptions of the latest bar. What each measures, never what to do."""
    c = df["Close"]
    last, li = float(c.iloc[-1]), ind.iloc[-1]
    out = []

    for n in (50, 200):
        avg = _num(li[f"sma{n}"])
        if avg:
            gap = (last / avg - 1) * 100
            out.append({"key": f"vs_sma{n}", "label": f"Price vs {n}-day average", "value": round(gap, 2),
                        "unit": "%", "text": f"The close is {abs(gap):.1f}% {'above' if gap >= 0 else 'below'} "
                                             f"its {n}-day average of Rs {avg:,.2f}."})
    side, since = _last_cross(ind["sma50"], ind["sma200"])
    if side:
        out.append({"key": "sma50_vs_sma200", "label": "50-day vs 200-day average", "value": side, "unit": None,
                    "text": f"The 50-day average is {side} the 200-day average"
                            + (f", and has been since {since}." if since else " for the whole period shown.")})

    rsi = _num(li["rsi14"])
    if rsi is not None:
        band = ("above 70, the level many traders call overbought" if rsi > 70 else
                "below 30, the level many traders call oversold" if rsi < 30 else "between 30 and 70")
        out.append({"key": "rsi14", "label": "RSI (14 days)", "value": round(rsi, 1), "unit": None,
                    "text": f"RSI is {rsi:.1f}, {band}. It compares the size of recent up days with recent down days."})

    side, since = _last_cross(ind["macd"], ind["macd_signal"])
    if side:
        out.append({"key": "macd", "label": "MACD vs its signal line", "value": side, "unit": None,
                    "text": f"MACD is {side} its signal line" + (f" (since {since})." if since else ".")
                            + " MACD is the gap between the 12-day and 26-day exponential averages."})

    up, lo = _num(li["bb_upper"]), _num(li["bb_lower"])
    if up is not None and lo is not None and up > lo:
        pb = (last - lo) / (up - lo) * 100
        out.append({"key": "bollinger", "label": "Position in Bollinger band", "value": round(pb, 1), "unit": "%",
                    "text": f"The close sits {pb:.0f}% of the way from the lower band (Rs {lo:,.2f}) to the upper band "
                            f"(Rs {up:,.2f}); the bands are two standard deviations around the 20-day average."})

    atr = _num(li["atr14"])
    if atr:
        out.append({"key": "atr14", "label": "Typical daily range (ATR 14)", "value": round(atr / last * 100, 2),
                    "unit": "%", "text": f"Over the last 14 days the stock has typically moved Rs {atr:,.2f} "
                                         f"({atr / last * 100:.1f}% of its price) between high and low each day."})

    tail = df.tail(252)
    hi, lo52 = float(tail["High"].max()), float(tail["Low"].min())
    out.append({"key": "range_52w", "label": "52-week range", "value": round((last / hi - 1) * 100, 2), "unit": "%",
                "text": f"The close is {abs(last / hi - 1) * 100:.1f}% below the 52-week high of Rs {hi:,.2f} and "
                        f"{(last / lo52 - 1) * 100:.1f}% above the 52-week low of Rs {lo52:,.2f}."
                        + ("" if len(tail) >= 240 else f" (Only {len(tail)} trading days of history.)")})

    va = _num(li["vol_avg20"])
    vol = _num(df["Volume"].iloc[-1])
    if va and vol is not None:
        out.append({"key": "volume", "label": "Volume vs 20-day average", "value": round(vol / va, 2), "unit": "x",
                    "text": f"The last session traded {vol / va:.1f} times its 20-day average volume."})
    return out


def technicals(ticker, period="1y"):
    if period not in TECH_PERIODS:
        return {"error": f"Period must be one of {', '.join(TECH_PERIODS)}."}
    days = TECH_PERIODS[period]
    now = datetime.now()
    start = (now - timedelta(days=days + WARMUP_DAYS)).strftime("%Y-%m-%d")
    end = (now + timedelta(days=1)).strftime("%Y-%m-%d")          # yfinance's end is exclusive
    try:
        df = OHLCV(ticker, start, end)
    except Exception as e:
        return {"error": f"Could not fetch prices for {ticker}: {type(e).__name__}"}
    if df is None or df.empty:
        return {"error": f"No price history for {ticker}."}
    df = df.dropna(subset=["Close"]).sort_index()
    ind = indicators(df)
    window_start = pd.Timestamp(now - timedelta(days=days)).normalize()
    shown = df.index >= window_start
    if shown.sum() < MIN_BARS:
        return {"error": f"Only {int(shown.sum())} trading days of prices for {ticker} in this period."}

    bars = []
    for ts, row in df[shown].iterrows():
        i = ind.loc[ts]
        bar = {"date": str(ts)[:10]}
        for k, src in (("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close")):
            bar[k] = _round(_num(row[src]), 2)
        bar["volume"] = _num(row["Volume"])
        for k in ("sma20", "sma50", "sma200", "ema20", "bb_upper", "bb_mid", "bb_lower",
                  "macd", "macd_signal", "macd_hist", "rsi14"):
            bar[k] = _round(_num(i[k]), 2 if not k.startswith("macd") else 3)
        bars.append(bar)

    return {
        "ticker": ticker, "period": period, "from": bars[0]["date"], "to": bars[-1]["date"],
        "bars": bars,
        "readings": readings(df, ind),
        "notes": {
            "untested": UNTESTED,
            "prices": "Daily prices adjusted for splits and dividends (Yahoo), so they can differ from the "
                      "prices printed on the day.",
            "warmup": "Averages are computed from earlier history too, so the 200-day line starts on the first bar "
                      "whenever the stock has that much history.",
        },
    }


# ── cached entry points (an error is returned but never cached) ──────────────

class _NotCached(Exception):
    pass


def _cached(key, ttl, fn):
    from swr_cache import cached

    def _fn():
        r = fn()
        if "error" in r:
            raise _NotCached(r)
        return r

    try:
        return cached(key, ttl, _fn)
    except _NotCached as e:
        return e.args[0]


def fundamentals_history_cached(ticker):
    return _cached(f"stock_fund_hist:{ticker}", FUND_TTL, lambda: fundamentals_history(ticker))


def technicals_cached(ticker, period="1y"):
    return _cached(f"stock_tech:{ticker}:{period}", TECH_TTL, lambda: technicals(ticker, period))
