"""
regime_walkforward.py: the app's regime detector, refitted every trading day
since 2008, and scored by the rules in docs/PREREG_REGIME_DETECTOR_2026-09-28.md.

Imports GaussianHMM from backend/modules/regime_detector.py unchanged and
copies its window (282 calendar days), features ([r, |r|]), settings
(3 states, 150 iterations, tol 1e-5) and labelling (states sorted by mean
return: Bear, Sideways, Bull). Each day's label uses data up to and including
that day's close.

    python research/regime_walkforward.py <out_dir>
"""

import json
import os
import sys
import warnings
from datetime import datetime, timedelta
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "modules"))
warnings.filterwarnings("ignore")

WINDOW_DAYS = 252 + 30          # detect_regime: start = now - (lookback_days + 30)
LAST_DAY = "2026-09-25"
H = 20

_DATES = _CLOSES = None


def _init(dates, closes):
    global _DATES, _CLOSES
    _DATES, _CLOSES = dates, closes


def label_window(i, full_history=False):
    from regime_detector import GaussianHMM
    t = _DATES[i]
    lo = t - np.timedelta64(WINDOW_DAYS, "D")
    m = (_DATES >= lo) & (_DATES <= t)
    p = pd.Series(_CLOSES[m], index=_DATES[m])
    r = p.pct_change().dropna()
    X = np.column_stack([r.values, np.abs(r.values)])
    hmm = GaussianHMM(n_states=3, n_iter=150, tol=1e-5)
    hmm.fit(X)
    states, proba = hmm.predict(X)
    means = [X[states == k, 0].mean() if (states == k).sum() > 0 else 0 for k in range(3)]
    order = np.argsort(means)
    name = {order[0]: "Bear", order[1]: "Sideways", order[2]: "Bull"}
    out = {"date": str(t)[:10], "label": name[int(states[-1])], "p": float(proba[-1].max()),
           "bull_mean_pct": float(X[states == order[2], 0].mean() * 100) if (states == order[2]).any() else None,
           "bull_stay": float(hmm.A[order[2], order[2]])}
    if full_history:
        out["history"] = [(str(d)[:10], name[int(s)]) for d, s in zip(r.index, states)]
    return out


def runs(labels):
    lens, cur = [], 1
    for a, b in zip(labels[:-1], labels[1:]):
        if a == b:
            cur += 1
        else:
            lens.append(cur)
            cur = 1
    lens.append(cur)
    return lens


def hac_diff(y, groups, a, b, lags):
    """Mean(y | a) - mean(y | b), Newey-West standard error, from y on group dummies."""
    import statsmodels.api as sm
    cats = sorted(set(groups) - {b})
    X = pd.DataFrame({c: (groups == c).astype(float) for c in cats})
    X = sm.add_constant(X)
    ok = ~np.isnan(y)
    res = sm.OLS(y[ok], X[ok]).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    est, se = float(res.params[a]), float(res.bse[a])
    return {"diff": est, "se": se, "t": est / se, "p": float(res.pvalues[a]),
            "n": int(ok.sum()), "n_by_group": {g: int(((groups == g) & ok).sum()) for g in set(groups)}}


def main():
    import yfinance as yf
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)
    df = yf.download("^NSEI", start="2007-01-01", end="2026-09-26", progress=False, auto_adjust=True)
    close = df["Close"].squeeze().dropna()
    close = close[close.index <= LAST_DAY]
    dates = close.index.values.astype("datetime64[ns]")
    closes = close.values.astype(float)
    first = int(np.argmax(dates >= dates[0] + np.timedelta64(WINDOW_DAYS, "D")))
    idx = list(range(first, len(dates)))
    print(f"Nifty {str(dates[0])[:10]} to {str(dates[-1])[:10]}; labelling {len(idx)} days", flush=True)

    with Pool(os.cpu_count(), initializer=_init, initargs=(dates, closes)) as pool:
        rows = pool.map(label_window, idx, chunksize=20)
    _init(dates, closes)
    final = label_window(len(dates) - 1, full_history=True)

    lab = pd.DataFrame(rows).set_index("date")
    lab.to_csv(os.path.join(out_dir, "regime_walkforward_labels.csv"))
    s = pd.Series(closes, index=pd.to_datetime(dates))
    r = s.pct_change()
    L = lab["label"].values
    same_day = r.reindex(pd.to_datetime(lab.index)).values

    # D1, D2
    rl = runs(list(L))
    d1 = {"median_run_days": float(np.median(rl)), "mean_run_days": float(np.mean(rl)), "n_runs": len(rl),
          "share_runs_1_day": float(np.mean(np.array(rl) == 1))}
    d2 = {"bull_days_up_pct": float(np.mean(same_day[L == "Bull"] > 0) * 100),
          "bear_days_down_pct": float(np.mean(same_day[L == "Bear"] < 0) * 100),
          "sideways_days_down_pct": float(np.mean(same_day[L == "Sideways"] < 0) * 100),
          "days_by_label": {k: int((L == k).sum()) for k in ("Bull", "Sideways", "Bear")}}

    # D3: chart (final fit, smoothed) vs label shown on the day
    chart = dict(final["history"][-90:])
    shown = lab["label"].to_dict()
    both = [d for d in chart if d in shown]
    d3 = {"days_compared": len(both), "differ_pct": float(np.mean([chart[d] != shown[d] for d in both]) * 100)}

    # D4: the app's own download call, today
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    app_df = yf.download("^NSEI", start=start, end=end, progress=False, auto_adjust=True)
    full_df = yf.download("^NSEI", start=start, progress=False, auto_adjust=True)
    d4 = {"run_at_local": datetime.now().isoformat(timespec="minutes"), "end_param": end,
          "last_day_with_app_call": str(app_df.index[-1])[:10], "last_day_available": str(full_df.index[-1])[:10]}

    # H1, H2 and benchmarks
    n = len(s)
    fwd_ret = np.full(n, np.nan)
    fwd_vol = np.full(n, np.nan)
    rv = r.values
    for i in range(n - H):
        fwd_ret[i] = s.values[i + H] / s.values[i] - 1
        fwd_vol[i] = np.std(rv[i + 1:i + H + 1], ddof=1) * np.sqrt(252)
    pos = {d: i for i, d in enumerate(pd.to_datetime(dates))}
    ii = np.array([pos[pd.Timestamp(d)] for d in lab.index])
    yR, yV = fwd_ret[ii] * 100, fwd_vol[ii] * 100
    G = np.array(L)
    res = {"H1_return_bull_minus_bear_pct": hac_diff(yR, G, "Bull", "Bear", H - 1),
           "H2_vol_bear_minus_bull_pct": hac_diff(yV, G, "Bear", "Bull", H - 1)}
    for k, v in res.items():
        right = v["diff"] > 0
        v["verdict"] = ("useful" if right and v["p"] < 0.025 else
                        "reversed" if (not right) and v["p"] < 0.025 else "no demonstrated value")

    tr20 = s / s.shift(20) - 1
    vol20 = r.rolling(20).std()
    volmed = vol20.rolling(252).median()
    trend = np.where(tr20.values[ii] > 0, "Bull", "Bear")
    volr = np.where(vol20.values[ii] > volmed.values[ii], "Bear", "Bull")
    bench = {"trend20": {"H1": hac_diff(yR, trend, "Bull", "Bear", H - 1), "H2": hac_diff(yV, trend, "Bear", "Bull", H - 1)},
             "vol20": {"H1": hac_diff(yR, volr, "Bull", "Bear", H - 1), "H2": hac_diff(yV, volr, "Bear", "Bull", H - 1)}}

    # Exploratory
    expl = {}
    years = pd.to_datetime(lab.index).year
    for name, (a, b) in {"2008-13": (2008, 2013), "2014-19": (2014, 2019), "2020-26": (2020, 2026)}.items():
        m = (years >= a) & (years <= b)
        expl[name] = {"H1": hac_diff(yR[m], G[m], "Bull", "Bear", H - 1), "H2": hac_diff(yV[m], G[m], "Bear", "Bull", H - 1),
                      "median_run_days": float(np.median(runs(list(G[m]))))}
    for h in (5, 60):
        fr = np.full(n, np.nan)
        for i in range(n - h):
            fr[i] = s.values[i + h] / s.values[i] - 1
        expl[f"H1_{h}d"] = hac_diff(fr[ii] * 100, G, "Bull", "Bear", h - 1)

    out = {"run": datetime.now().isoformat(timespec="seconds"), "prereg": "docs/PREREG_REGIME_DETECTOR_2026-09-28.md",
           "data": {"first": str(dates[0])[:10], "last": str(dates[-1])[:10], "days_labelled": len(idx)},
           "D1_persistence": d1, "D2_same_day_return": d2, "D3_chart_vs_shown": d3, "D4_missing_day": d4,
           "primary": res, "benchmarks": bench, "exploratory": expl,
           "fitted_bull_state": {"median_bull_mean_daily_pct": float(np.nanmedian(lab["bull_mean_pct"].astype(float))),
                                 "median_bull_stay_prob": float(np.median(lab["bull_stay"]))}}
    json.dump(out, open(os.path.join(out_dir, "regime_detector_result_2026-09-28.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("exploratory",)}, indent=1, default=str))


if __name__ == "__main__":
    main()
