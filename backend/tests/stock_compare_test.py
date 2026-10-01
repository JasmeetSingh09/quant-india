"""
stock_compare_test.py — the stock comparer (#2 in
docs/PROPOSAL_PRODUCT_ADDITIONS_2026-09-23.md) against hand-worked figures.
No network: every price series is synthetic.
"""

import math
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "modules"))

import data_fetcher  # noqa: E402
import risk_metrics  # noqa: E402
import stock_compare as sc  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


def near(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


idx = pd.bdate_range("2025-01-01", periods=260)
rng = np.random.default_rng(11)
nifty_r = rng.normal(0.0004, 0.01, len(idx))
nifty = pd.Series(10000 * np.cumprod(1 + nifty_r), index=idx)
beta_r = 1.5 * nifty_r + rng.normal(0, 0.002, len(idx))
SERIES = {
    "^NSEI": nifty,
    "AAA.NS": pd.Series(100 * np.cumprod(1 + beta_r), index=idx),
    "BBB.NS": pd.Series(50 * np.cumprod(1 + rng.normal(0.0002, 0.015, len(idx))), index=idx),
    "CCC.NS": pd.Series(80 * np.cumprod(1 + rng.normal(0, 0.012, len(idx))), index=idx),
    "SHORT.NS": pd.Series(10 + np.arange(30.0), index=idx[-30:]),
}
data_fetcher.download_close = lambda t, start, end=None: SERIES.get(t, pd.Series(dtype=float))
sc.compare.__globals__["_model_view"] = lambda t: None

print("\n1. Limits")
ok("error" in sc.compare(["AAA.NS"]), "1 ticker is refused")
ok("error" in sc.compare([f"T{i}.NS" for i in range(7)]), "7 tickers are refused")
ok("error" in sc.compare(["AAA.NS", "BBB.NS"], period="2w"), "an unknown period is refused")
ok(sc.normalise(["tcs", "TCS.NS", " infy "]) == ["TCS.NS", "INFY.NS"], "tickers normalised and de-duplicated")

print("\n2. Charts")
r = sc.compare(["AAA.NS", "BBB.NS", "CCC.NS", "SHORT.NS"], period="1y", with_fundamentals=False)
ok("error" not in r, "a comparison is returned")
ok(all(r["series"][t]["rebased"][0] == 100.0 for t in r["tickers"]), "every series starts at exactly 100")
ok(r["benchmark"] is not None and r["benchmark"]["rebased"][0] == 100.0, "the Nifty starts at 100 too")
ok("excludes dividends" in r["benchmark"]["label"], "the Nifty is labelled as a price index")
ok("SHORT.NS" in r["excluded"] and "SHORT.NS" not in r["tickers"], "a stock with too little history is excluded, not filled")
w = sc.compare(["AAA.NS", "BBB.NS"], period="3y", with_fundamentals=False)
ok(len(w["series"]["AAA.NS"]["dates"]) < 60, f"3 years is sent weekly ({len(w['series']['AAA.NS']['dates'])} points)")

print("\n3. Risk, against hand-worked values")
p = pd.Series([100.0, 110.0, 99.0, 105.0, 120.0], index=pd.bdate_range("2025-03-03", periods=5))
mdd, peak, trough = sc._max_drawdown(p)
ok(near(mdd, -10.0), f"max drawdown 110 -> 99 is -10% ({mdd:.4f})")
ok(peak == "2025-03-04" and trough == "2025-03-05", f"its dates ({peak} to {trough})")
rr = pd.Series([-0.05, -0.04] + [0.01] * 38)
ok(near(sc._cvar95(rr), -4.5), f"CVaR: mean of the worst 5% of 40 days (-5%, -4%) = -4.5% ({sc._cvar95(rr)})")
ra = r["risk"]["AAA.NS"]
ok(abs(ra["beta_vs_nifty"] - 1.5) < 0.05, f"beta of 1.5 x Nifty plus noise is about 1.5 ({ra['beta_vs_nifty']})")
a_ret = SERIES["AAA.NS"].pct_change().dropna().values
ok(near(ra["sharpe"], round(risk_metrics.sharpe(a_ret, 252), 3)), "Sharpe equals risk_metrics exactly")
ok(near(ra["sortino"], round(risk_metrics.sortino(a_ret, 252), 3)), "Sortino equals risk_metrics exactly")
vol = float(pd.Series(a_ret).std(ddof=1) * math.sqrt(252) * 100)
ok(near(ra["volatility_pct"], round(vol, 2)), "volatility is the annualised sample standard deviation")
wm = SERIES["AAA.NS"].resample("ME").last().pct_change().dropna()
ok(near(ra["worst_month_pct"], round(float(wm.min() * 100), 2)), "worst month matches month-end returns")
c = r["correlation"]
ok(all(c[t][t] == 1.0 for t in r["tickers"]), "correlation diagonal is 1")
ok(all(c[a][b] == c[b][a] for a in r["tickers"] for b in r["tickers"]), "correlation matrix is symmetric")
ok("past only" in r["notes"]["risk"], "risk carries 'past only'")

print("\n4. Fundamentals are labelled and never filled")
sc.compare.__globals__["_fundamentals"] = lambda t: (
    {k: (12.5 if k == "pe_ratio" else None) for k in sc.VALUE_FIELDS} | {"sector": {"AAA.NS": "IT", "BBB.NS": "Banks"}.get(t)},
    {k: None for k in sc.QUALITY_FIELDS}, "2026-10-01")
f = sc.compare(["AAA.NS", "BBB.NS"], period="1y")
ok(f["value"]["AAA.NS"]["pe_ratio"] == 12.5 and f["value"]["AAA.NS"]["forward_pe"] is None, "a missing metric stays missing")
ok("not point-in-time" in f["notes"]["fundamentals"], "fundamentals say they are not point-in-time")
ok(f["notes"]["sectors"] and "not directly comparable" in f["notes"]["sectors"], "different sectors get a warning")

print("\n5. The page never names a winner")
page = os.path.join(HERE, "..", "..", "frontend", "src", "pages", "Compare.jsx")
if os.path.exists(page):
    src = open(page, encoding="utf-8").read()
    visible = " ".join(re.findall(r">([^<>{}]+)<", src) + re.findall(r"'([^'\n]{3,})'", src)).lower()
    bad = [w for w in ("best", "winner", "buy") if re.search(r"\b" + w + r"\b", visible)]
    ok(not bad, f"no 'best', 'buy' or 'winner' in the comparer's text ({bad})")
else:
    ok(False, "frontend/src/pages/Compare.jsx exists")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
