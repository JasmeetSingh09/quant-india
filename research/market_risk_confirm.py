"""
market_risk_confirm.py: the one-line volatility rule on four markets it was not
chosen on. Rules: docs/PREREG_MARKET_RISK_SIGNAL_2026-09-28.md.

    python research/market_risk_confirm.py <out.json>
"""

import json
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
H, LAST_DAY = 20, "2026-09-25"
MARKETS = {"^NSEBANK": "Nifty Bank", "^GSPC": "S&P 500", "^FTSE": "FTSE 100", "^N225": "Nikkei 225"}
REPORT_ONLY = {"^NSEI": "Nifty 50 (the market the rule was chosen on)"}


def hac(y, flag, lags):
    import statsmodels.api as sm
    ok = ~np.isnan(y) & ~np.isnan(flag)
    X = sm.add_constant(flag[ok].astype(float))
    res = sm.OLS(y[ok], X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return {"diff": float(res.params[1]), "se": float(res.bse[1]), "t": float(res.tvalues[1]),
            "p": float(res.pvalues[1]), "n": int(ok.sum())}


def median_run(flags):
    f = [x for x in flags if not np.isnan(x)]
    lens, cur = [], 1
    for a, b in zip(f[:-1], f[1:]):
        if a == b:
            cur += 1
        else:
            lens.append(cur)
            cur = 1
    lens.append(cur)
    return float(np.median(lens)), float(np.mean(lens))


def one(ticker):
    import yfinance as yf
    df = yf.download(ticker, start="1990-01-01", end="2026-09-26", progress=False, auto_adjust=True)
    s = df["Close"].squeeze().dropna()
    s = s[s.index <= LAST_DAY]
    r = s.pct_change()
    vol20 = r.rolling(20).std()
    med = vol20.rolling(252).median()
    elevated = np.where(vol20.isna() | med.isna(), np.nan, (vol20 > med).astype(float))
    trend_down = np.where(s.shift(20).isna(), np.nan, (s / s.shift(20) - 1 < 0).astype(float))
    n = len(s)
    fv, fr = np.full(n, np.nan), np.full(n, np.nan)
    rv = r.values
    for i in range(n - H):
        fv[i] = np.std(rv[i + 1:i + H + 1], ddof=1) * np.sqrt(252) * 100
        fr[i] = (s.values[i + H] / s.values[i] - 1) * 100
    first = int(np.argmax(~np.isnan(elevated)))
    return {"first_labelled": str(s.index[first])[:10], "last": str(s.index[-1])[:10],
            "days": int(np.sum(~np.isnan(elevated))), "share_elevated_pct": float(np.nanmean(elevated) * 100),
            "H_vol": hac(fv, elevated, H - 1), "return_diff_reported": hac(fr, elevated, H - 1),
            "median_run_days": median_run(elevated)[0], "mean_run_days": median_run(elevated)[1],
            "trend_rule": {"H_vol": hac(fv, trend_down, H - 1), "median_run_days": median_run(trend_down)[0]}}


def main():
    out = {"prereg": "docs/PREREG_MARKET_RISK_SIGNAL_2026-09-28.md", "markets": {}, "report_only": {}}
    for t, name in MARKETS.items():
        out["markets"][name] = one(t)
    for t, name in REPORT_ONLY.items():
        out["report_only"][name] = one(t)
    passed = [n for n, v in out["markets"].items() if v["H_vol"]["diff"] > 0 and v["H_vol"]["p"] < 0.05 / 4]
    out["confirmed_markets"] = passed
    out["verdict"] = "confirmed" if len(passed) >= 3 else "not confirmed"
    json.dump(out, open(sys.argv[1], "w"), indent=1)
    for n, v in {**out["markets"], **out["report_only"]}.items():
        h = v["H_vol"]
        print(f"{n:45} {v['first_labelled']}..{v['last']}  vol diff {h['diff']:+.2f} pts  p {h['p']:.2g}  "
              f"median run {v['median_run_days']:.0f}d (mean {v['mean_run_days']:.1f})  "
              f"return diff {v['return_diff_reported']['diff']:+.2f} (p {v['return_diff_reported']['p']:.2f})")
    print("\nconfirmed on:", passed, "->", out["verdict"])


if __name__ == "__main__":
    main()
