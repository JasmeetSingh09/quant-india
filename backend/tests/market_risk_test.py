"""
market_risk_test.py — the market-risk reading that replaced the regime label.

Owner approval 2026-09-28. Pins:
  - the rule is exactly the one confirmed on four markets
    (docs/PREREG_MARKET_RISK_SIGNAL_2026-09-28.md);
  - today's close is downloaded (yf.download's end date is exclusive; the
    regime detector used end=today and missed the current day);
  - a failed download is never cached as the answer;
  - the regime-adaptive optimiser uses HRP only.
No network: every download is replaced with a synthetic series.
"""

import ast
import os
import sys
import types
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "modules"))

import market_risk as mr  # noqa: E402
import swr_cache  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


def series(vols, seed=7):
    rng = np.random.default_rng(seed)
    r = np.concatenate([rng.normal(0, v, n) for v, n in vols])
    idx = pd.bdate_range("2024-01-01", periods=len(r) + 1)
    return pd.Series(100 * np.cumprod(np.r_[1.0, 1 + r]), index=idx)


TOMORROW = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

print("\n1. The rule")
calm_then_wild = series([(0.005, 320), (0.02, 25)])
df = mr.classify(calm_then_wild)
ok(df["state"].iloc[-1] == "Elevated", "a volatile month after a calm year reads Elevated")
ok(df["state"].iloc[: mr.VOL_WINDOW + mr.MEDIAN_WINDOW - 2].isna().all(), "no reading before 20 + 252 days of history")
back_to_calm = series([(0.005, 320), (0.02, 25), (0.004, 60)])
ok(mr.classify(back_to_calm)["state"].iloc[-1] == "Normal", "calm again reads Normal")
rnd = series([(0.01, 600)], seed=3)
r = rnd.pct_change(); v = r.rolling(20).std(); m = v.rolling(252).median()
ref = np.where(v.isna() | m.isna(), None, np.where(v > m, "Elevated", "Normal"))
got = mr.classify(rnd)["state"].values
norm = lambda x: None if (x is None or (isinstance(x, float) and np.isnan(x))) else x
ok(all(norm(a) == norm(b) for a, b in zip(ref, got)) and sum(norm(g) is not None for g in got) == sum(x is not None for x in ref) > 300,
   "identical to the rule in research/market_risk_confirm.py (every day read, over 300)")

print("\n2. The summary")
s = mr.summarise(mr.classify(calm_then_wild))
ok(s["state"] == "Elevated" and s["days_in_state"] >= 1, f"state and run length ({s['state']}, {s['days_in_state']} days)")
ok(s["volatility_20d_pct"] > s["typical_volatility_pct"], "Elevated means 20-day volatility above its typical level")
ok("does not forecast direction" in s["meaning"], "the meaning says it does not forecast direction")
ok(len(mr.summarise(mr.classify(rnd))["history"]) == mr.HISTORY_DAYS, f"{mr.HISTORY_DAYS} days of history")
ok(s["evidence"]["test"].endswith("PREREG_MARKET_RISK_SIGNAL_2026-09-28.md"), "cites the confirming test")
ok("error" in mr.summarise(mr.classify(series([(0.01, 100)]))), "too little history is an error, not a guess")

print("\n3. Today's close is downloaded")
seen = {}


def fake_download(ticker, start=None, end=None, **kw):
    seen["end"] = end
    s = series([(0.01, 700)])
    return pd.DataFrame({"Close": s.values}, index=s.index)


real_yf = sys.modules.get("yfinance")
sys.modules["yfinance"] = types.SimpleNamespace(download=fake_download)
mr._download("^NSEI")
ok(seen["end"] == TOMORROW, f"market risk asks for data up to tomorrow ({seen['end']})")
import regime_detector as rd  # noqa: E402
rd.yf = sys.modules["yfinance"]
seen.clear()
rd._detect_regime_uncached("^NSEI", 252, 3)
ok(seen.get("end") == TOMORROW, f"regime detector asks for data up to tomorrow ({seen.get('end')})")

print("\n4. A failed download is not cached as the answer")
swr_cache.clear()
real_dl = mr._download
mr._download = lambda t: (_ for _ in ()).throw(ConnectionError("down"))
first = mr.market_risk()
ok("error" in first, "a failure is reported as an error")
mr._download = lambda t: series([(0.005, 320), (0.02, 25)])
second = mr.market_risk()
ok(second.get("state") == "Elevated", "the next call computes afresh instead of serving the error")
mr._download = real_dl
if real_yf is not None:
    sys.modules["yfinance"] = real_yf

print("\n5. The optimiser no longer switches on the regime label")
src = open(os.path.join(HERE, "..", "main.py"), encoding="utf-8").read()
tree = ast.parse(src)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "optimizer_regime_adaptive")
calls = {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
ok("hierarchical_risk_parity" in calls, "it calls HRP")
ok(not ({"mean_variance_optimize", "min_cvar_optimize", "detect_regime"} & calls),
   f"it calls neither Markowitz, Min-CVaR nor the regime detector ({sorted(calls)})")
ok('@app.get("/market-risk")' in src, "the /market-risk endpoint exists")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
