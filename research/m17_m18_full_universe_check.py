"""Full-universe check for M17/M18 (read-only Yahoo; nothing written anywhere but the output file).

For each ticker: the same yf.download call _compute_momentum_factor makes. Records whether the
Close series is chronological and has one row per date. For any series that is not, computes the
momentum score both ways (old code: as returned; new code: stable sort + keep last per date),
using the same window arithmetic as alpha_model, so a score difference is measured, not assumed.
A download that fails is retried once and then recorded as failed, never counted as clean.
"""
import json
import sys
import time
from datetime import datetime, timedelta

import numpy as np
import yfinance as yf

LOOKBACK, SKIP, MIN_OBS, MIN_RETS, EPS, TANH_DIV = 252, 21, 60, 5, 1e-6, 1.5
BUFFER_DAYS = 430


def score(s):
    if s is None or len(s) < MIN_OBS:
        return None
    n = len(s)
    a, b = max(0, n - 1 - LOOKBACK), n - 1 - SKIP
    if b <= a:
        return None
    mom = float(s.iloc[b] / s.iloc[a] - 1)
    rets = s.iloc[a:b + 1].pct_change().dropna()
    vol = float(rets.std() * np.sqrt(252)) if len(rets) > MIN_RETS else 0.0
    ra = mom / vol if vol > EPS else 0.0
    return float(np.tanh(ra / TANH_DIV))


def fetch(t, start, end):
    df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True, threads=True, timeout=15)
    return df["Close"].squeeze().dropna()


tickers = open(sys.argv[1], encoding="utf-8").read().strip().split(",")
out_path = sys.argv[2]
start = (datetime.now() - timedelta(days=BUFFER_DAYS)).strftime("%Y-%m-%d")
end = datetime.now().strftime("%Y-%m-%d")
res = {"started_utc": datetime.utcnow().isoformat(timespec="seconds"), "window": [start, end],
       "n": len(tickers), "fetched": 0, "empty_series": [], "failed": [], "unsorted": [],
       "duplicate_dates": [], "affected_scores": []}
for i, t in enumerate(tickers, 1):
    s = None
    for attempt in (1, 2):
        try:
            s = fetch(t, start, end)
            break
        except Exception as e:
            if attempt == 2:
                res["failed"].append([t, type(e).__name__])
            time.sleep(2)
    if s is None:
        continue
    if not hasattr(s, "index") or len(s) == 0:
        res["empty_series"].append(t)
        continue
    res["fetched"] += 1
    uns = not s.index.is_monotonic_increasing
    dup = bool(s.index.duplicated().any())
    if uns:
        res["unsorted"].append(t)
    if dup:
        res["duplicate_dates"].append(t)
    if uns or dup:
        fixed = s.sort_index(kind="mergesort")
        fixed = fixed[~fixed.index.duplicated(keep="last")]
        res["affected_scores"].append({"ticker": t, "old": score(s), "new": score(fixed)})
    if i % 100 == 0:
        print(f"{i}/{len(tickers)} fetched={res['fetched']} unsorted={len(res['unsorted'])} "
              f"dup={len(res['duplicate_dates'])} empty={len(res['empty_series'])} failed={len(res['failed'])}",
              flush=True)
        json.dump(res, open(out_path, "w", encoding="utf-8"), indent=1)
    time.sleep(0.25)
res["finished_utc"] = datetime.utcnow().isoformat(timespec="seconds")
json.dump(res, open(out_path, "w", encoding="utf-8"), indent=1)
print("DONE", json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in res.items()}))
