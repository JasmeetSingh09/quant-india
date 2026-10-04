"""
stock_analysis_test.py — fundamentals over the years and technical indicators
(owner request 2026-10-04).

Offline. Statements and prices are replaced with fixed frames, and every
indicator is checked against a plain loop written from its textbook
definition, so a vectorised shortcut cannot drift from the formula unnoticed.
"""
import ast
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import stock_analysis as A  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


def frame(closes, start="2024-01-01"):
    c = pd.Series(closes, index=pd.bdate_range(start, periods=len(closes)), dtype=float)
    return pd.DataFrame({"Open": c.shift().fillna(c.iloc[0]), "High": c * 1.01, "Low": c * 0.99,
                         "Close": c, "Volume": 1000.0 + np.arange(len(c))})


print("\n1. Each indicator matches its textbook definition")
rng = np.random.default_rng(7)
px = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, 400)))
df = frame(px)
ind = A.indicators(df)
c = df["Close"].to_numpy()

sma50 = [None] * 49 + [c[i - 49:i + 1].mean() for i in range(49, len(c))]
ok(all(close(ind["sma50"].iloc[i], sma50[i]) for i in range(49, len(c))) and ind["sma50"].iloc[:49].isna().all(),
   "50-day average = mean of the last 50 closes, blank before day 50")

# Wilder RSI: seed with the simple average of the first 14 moves, then smooth by 1/14.
# pandas' ewm(adjust=False) seeds with the first move instead, so the two agree only
# after the seed washes out; compare from bar 120 on, where the gap is far below 0.01.
d = np.diff(c)
g, l = np.clip(d, 0, None), np.clip(-d, 0, None)
ag, al = g[:14].mean(), l[:14].mean()
wilder = {}
for i in range(14, len(d)):
    ag = (ag * 13 + g[i]) / 14
    al = (al * 13 + l[i]) / 14
    wilder[i + 1] = 100 - 100 / (1 + ag / al)
ok(all(abs(ind["rsi14"].iloc[i] - wilder[i]) < 0.01 for i in range(120, len(c))),
   "RSI (14) matches Wilder's smoothing")

e12 = e26 = c[0]
macd = []
for x in c:
    e12 = e12 + 2 / 13 * (x - e12)
    e26 = e26 + 2 / 27 * (x - e26)
    macd.append(e12 - e26)
sig, sigs = macd[0], []
for m in macd:
    sig = sig + 2 / 10 * (m - sig)
    sigs.append(sig)
ok(all(close(ind["macd"].iloc[i], macd[i]) and close(ind["macd_signal"].iloc[i], sigs[i]) for i in range(len(c))),
   "MACD = EMA12 - EMA26, signal = EMA9 of MACD")
ok(np.allclose(ind["macd_hist"], ind["macd"] - ind["macd_signal"]), "MACD histogram = MACD - signal")

i = 300
w = c[i - 19:i + 1]
ok(close(ind["bb_upper"].iloc[i], w.mean() + 2 * w.std()) and close(ind["bb_lower"].iloc[i], w.mean() - 2 * w.std()),
   "Bollinger bands = 20-day mean +/- 2 population standard deviations")

h, lo = df["High"].to_numpy(), df["Low"].to_numpy()
tr = [h[0] - lo[0]] + [max(h[k] - lo[k], abs(h[k] - c[k - 1]), abs(lo[k] - c[k - 1])) for k in range(1, len(c))]
ok(all(abs(ind["atr14"].iloc[k] - pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().iloc[k]) < 1e-9
       for k in range(13, len(c))), "ATR (14) = Wilder average of the true range")

print("\n2. Edge cases do not invent numbers")
up = A.indicators(frame(np.arange(1, 60, dtype=float)))
ok(up["rsi14"].dropna().eq(100).all(), "a series that only rises has RSI 100")
flat = A.indicators(frame([50.0] * 60))
ok(flat["rsi14"].isna().all(), "a flat series has no RSI (undefined), not 50 or 0")
short = A.indicators(frame(px[:30]))
ok(short["sma200"].isna().all(), "with 30 days of history there is no 200-day average")

print("\n3. Crossovers are dated from the data")
a = pd.Series([1, 1, 1, 3, 3, 3, 0.5, 0.5], index=pd.bdate_range("2024-01-01", periods=8), dtype=float)
b = pd.Series([2.0] * 8, index=a.index)
side, since = A._last_cross(a, b)
ok(side == "below" and since == "2024-01-09", f"last cross found ({side}, {since})")
side, since = A._last_cross(b + 1, b)
ok(side == "above" and since is None, "no cross in the period: no date is made up")

print("\n4. The technicals response")
# 520 trading days ending about a month ago: enough for a 200-day average before the 1-year window.
px_long = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, 520)))
A.OHLCV = lambda t, s, e: frame(px_long, start=(pd.Timestamp.now() - pd.Timedelta(days=750)).strftime("%Y-%m-%d"))
t = A.technicals("TEST.NS", "1y")
ok("error" not in t and len(t["bars"]) > 200, "a year of daily bars")
ok(t["bars"][0]["date"] >= (pd.Timestamp.now() - pd.Timedelta(days=366)).strftime("%Y-%m-%d"),
   "bars start at the period, the warm-up history is used but not shown")
ok(t["bars"][0]["sma200"] is not None, "the 200-day line exists from the first bar shown")
ok(json.dumps(t, allow_nan=False) is not None, "no NaN reaches the JSON")
ok(A.technicals("TEST.NS", "10y").get("error", "").startswith("Period"), "an unknown period is refused")
A.OHLCV = lambda t, s, e: frame(px[:20])
ok("error" in A.technicals("TEST.NS", "1y"), "too little history is an error, not a short chart")

print("\n5. Readings describe and never recommend")
A.OHLCV = lambda t, s, e: frame(px_long, start=(pd.Timestamp.now() - pd.Timedelta(days=750)).strftime("%Y-%m-%d"))
texts = " ".join(r["text"] for r in A.technicals("TEST.NS", "1y")["readings"]).lower()
banned = ["buy", "sell", "bullish", "bearish", "should", "target", "recommend", "golden cross", "death cross"]
ok(not any(w in texts for w in banned), "no buy/sell, bullish/bearish or 'should' in the readings")
ok("not buy or sell signals" in A.UNTESTED and "not tested" in A.UNTESTED.replace("has not tested", "not tested"),
   "the untested note is sent with every response")

print("\n6. Fundamentals: gaps stay gaps")
cols = [pd.Timestamp(f"{y}-03-31") for y in (2025, 2024, 2023, 2021)]
inc = pd.DataFrame({cols[0]: [1000e7, 120e7, 200e7, 50.0], cols[1]: [900e7, 100e7, np.nan, 45.0],
                    cols[2]: [800e7, np.nan, 150e7, 40.0], cols[3]: [600e7, 60e7, 90e7, 30.0]},
                   index=["Total Revenue", "Net Income", "Operating Income", "Diluted EPS"])
bal = pd.DataFrame({cols[0]: [5000e7, 600e7, 300e7], cols[1]: [4500e7, -10e7, 280e7]},
                   index=["Total Assets", "Stockholders Equity", "Total Debt"])
cf = pd.DataFrame({cols[0]: [150e7, -40e7, 110e7]}, index=["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow"])
q = pd.DataFrame({pd.Timestamp("2025-06-30"): [260e7, 30e7], pd.Timestamp("2025-03-31"): [250e7, np.nan]},
                 index=["Total Revenue", "Net Income"])
A.STATEMENTS = lambda t: {"income": inc, "balance": bal, "cashflow": cf, "quarterly": q}
f = A.fundamentals_history("TEST.NS")
yrs = {r["label"]: r for r in f["annual"]}
ok([r["label"] for r in f["annual"]] == ["FY2021", "FY2023", "FY2024", "FY2025"], "years in order, March year = FY")
ok(yrs["FY2025"]["revenue"] == 1000 and yrs["FY2025"]["net_income"] == 120, "money converted to Rs crore")
ok(yrs["FY2023"]["net_income"] is None and yrs["FY2023"]["net_margin_pct"] is None,
   "a missing profit is a gap, and so is the margin built from it")
ok(yrs["FY2024"]["operating_margin_pct"] is None, "a missing operating income gives no operating margin")
ok(close(yrs["FY2025"]["roe_pct"], 20.0) and close(yrs["FY2025"]["debt_to_equity"], 0.5), "ROE and debt/equity")
ok(yrs["FY2024"]["roe_pct"] is None and yrs["FY2024"]["debt_to_equity"] is None,
   "negative equity gives no ROE or debt/equity, not a misleading sign")
ok(close(yrs["FY2025"]["revenue_growth_pct"], 11.11) and yrs["FY2023"]["revenue_growth_pct"] is None,
   "growth only between consecutive years (FY2021 to FY2023 skips a year)")
ok(yrs["FY2025"]["free_cash_flow"] == 110 and yrs["FY2024"]["operating_cash_flow"] is None,
   "a year with no cash-flow statement shows gaps")
ok([x["label"] for x in f["quarterly"]] == ["Mar 2025", "Jun 2025"] and f["quarterly"][0]["net_income"] is None,
   "quarters in order, a missing quarterly profit stays missing")
ok(f["notes"]["gaps"] and "not zero" in f["notes"]["gaps"], "the page is told which figures Yahoo left blank")
ok("not point-in-time" in f["notes"]["point_in_time"], "fundamentals are labelled not point-in-time")
ok(json.dumps(f, allow_nan=False) is not None, "no NaN reaches the JSON")
ok(f["notes"]["eps_break"] is None, "steady EPS raises no share-count warning")
ok("operating_income" not in (f["notes"]["gaps"] or ""), "the gaps note uses plain words, not field names")

# HDFC Bank as Yahoo has it: EPS halves (shares adjusted in later years only) while profit rises 26%.
hd = pd.DataFrame({pd.Timestamp("2024-03-31"): [62266e7, 44.16], pd.Timestamp("2023-03-31"): [49545e7, 88.68]},
                  index=["Net Income", "Diluted EPS"])
A.STATEMENTS = lambda t: {"income": hd, "balance": None, "cashflow": None, "quarterly": None}
br = A.fundamentals_history("TEST.NS")["notes"]["eps_break"]
ok(br is not None and "FY2024" in br and "not comparable" in br, "an EPS halving with steady profit is flagged")
ok(A._eps_break([{"label": "FY1", "eps_diluted": 10, "net_income": 100},
                 {"label": "FY2", "eps_diluted": 5, "net_income": 50}]) is None,
   "EPS halving because profit halved is not flagged")
# 21st Century Management as Yahoo has it: an investment company with negative revenue in FY2023.
neg = pd.DataFrame({pd.Timestamp("2024-03-31"): [40e7, 20e7], pd.Timestamp("2023-03-31"): [-13.52e7, -18.06e7],
                    pd.Timestamp("2022-03-31"): [30e7, 10e7]}, index=["Total Revenue", "Net Income"])
A.STATEMENTS = lambda t: {"income": neg, "balance": None, "cashflow": None, "quarterly": None}
ny = {r["label"]: r for r in A.fundamentals_history("TEST.NS")["annual"]}
ok(ny["FY2023"]["revenue"] == -13.52 and ny["FY2023"]["net_margin_pct"] is None,
   "negative revenue is shown as reported, with no margin computed from it")
ok(ny["FY2024"]["revenue_growth_pct"] is None and ny["FY2024"]["net_income_growth_pct"] is None,
   "no growth percentage from a negative base year")
ok(ny["FY2023"]["revenue_growth_pct"] is not None, "growth from a positive base into a loss is still shown")
# Alembic Ltd / Alfred Herbert as Yahoo has them: profit larger than revenue (income from holdings).
hold = pd.DataFrame({pd.Timestamp("2025-03-31"): [211.18e7, 310.68e7], pd.Timestamp("2024-03-31"): [147.12e7, 50e7]},
                    index=["Total Revenue", "Net Income"])
A.STATEMENTS = lambda t: {"income": hold, "balance": None, "cashflow": None, "quarterly": None}
h = A.fundamentals_history("TEST.NS")
ok(h["annual"][-1]["net_margin_pct"] > 100, "a margin above 100% is kept in the data, not altered")
ok(h["notes"]["margin_outliers"] and "FY2025" in h["notes"]["margin_outliers"]
   and "FY2024" not in h["notes"]["margin_outliers"], "the note names exactly the years beyond 100%")
ok(f["notes"]["margin_outliers"] is None, "ordinary margins raise no note")

# DCM Financial Services as Yahoo has it: Rs 29,000 of revenue. Rounded to 0.01 crore that is 0.
tinyrev = pd.DataFrame({pd.Timestamp("2026-03-31"): [29000.0, -10238000.0]}, index=["Total Revenue", "Net Income"])
A.STATEMENTS = lambda t: {"income": tinyrev, "balance": None, "cashflow": None, "quarterly": None}
tr = A.fundamentals_history("TEST.NS")["annual"][0]
ok(tr["revenue"] != 0 and abs(tr["revenue"] * 1e7 - 29000) < 1, "Rs 29,000 of revenue is kept, not rounded to 0")

# Infosys as Yahoo has it: statements in US dollars.
usd = pd.DataFrame({pd.Timestamp("2026-03-31"): [19.3e9, 3.2e9]}, index=["Total Revenue", "Net Income"])
A.STATEMENTS = lambda t: {"income": usd, "balance": None, "cashflow": None, "quarterly": None, "currency": "USD"}
u = A.fundamentals_history("INFY.NS")
ok(u["units"]["money"] == "USD million" and u["annual"][0]["revenue"] == 19300.0,
   "a USD reporter is shown in USD million, not labelled Rs crore")
ok(u["notes"]["currency"] and "not converted" in u["notes"]["currency"], "the page says the figures are in USD")
ok(f["notes"]["currency"] is None and f["units"]["money"] == "Rs crore", "rupee reporters stay in Rs crore, with no note")

A.STATEMENTS = lambda t: {"income": pd.DataFrame(), "balance": None, "cashflow": pd.DataFrame(), "quarterly": None}
ok("error" in A.fundamentals_history("TEST.NS"), "no statements at all is an error")

print("\n7. Errors are never cached")
calls = []


def failing():
    calls.append(1)
    return {"error": "down"}


A._cached("stock_analysis_test:err", 900, failing)
A._cached("stock_analysis_test:err", 900, failing)
ok(len(calls) == 2, "a failed fetch is tried again on the next request")

print("\n8. Routes and rate limits")
tree = ast.parse(open(os.path.join(HERE, "..", "main.py"), encoding="utf-8").read())
paths = {n.args[0].value for f in tree.body if isinstance(f, ast.FunctionDef) for n in f.decorator_list
         if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "get" and n.args}
ok({"/stock/fundamentals-history", "/stock/technicals"} <= paths, "both routes exist")
import rate_limit  # noqa: E402
ok(rate_limit.bucket_for("/stock/technicals") == "medium" and rate_limit.bucket_for("/stock/fundamentals-history") == "medium",
   "both are in the medium rate-limit tier")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
