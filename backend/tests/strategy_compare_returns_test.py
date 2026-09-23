"""
strategy_compare_returns_test.py — the comparison compounds simple returns.

portfolio_optimizer._get_returns returns LOG returns. strategy_compare used to
weight and compound them as if they were simple returns, which understated
every strategy (found 2026-09-14). These checks pin the figures to a portfolio
worked by hand from prices. No network: the price loader is replaced.
"""

import os
import sys
import types

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


rng = np.random.default_rng(20260923)
N = 300
idx = pd.bdate_range("2024-01-01", periods=N + 1)
prices = pd.DataFrame(
    {t: 100 * np.cumprod(1 + rng.normal(mu, 0.02, N + 1))
     for t, mu in (("AAA.NS", 0.0015), ("BBB.NS", 0.0008), ("CCC.NS", -0.0003))},
    index=idx)
nifty = pd.DataFrame({"^NSEI": 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, N + 1))},
                     index=idx)


def fake_get_returns(tickers, start, end):
    src = nifty if tickers == ["^NSEI"] else prices[[t for t in tickers if t in prices]]
    return np.log(src / src.shift(1)).dropna()


fake = types.ModuleType("portfolio_optimizer")
fake._get_returns = fake_get_returns
fake.mean_variance_optimize = lambda *a, **k: {"error": "not in this test"}
fake.black_litterman_optimize = lambda *a, **k: {}
sys.modules["portfolio_optimizer"] = fake

import strategy_compare as sc  # noqa: E402

res = sc.compare(list(prices.columns), "2024-01-01", "2025-03-01")
ok("error" not in res, f"compare ran ({res.get('error')})")
eq = next(r for r in res["strategies"] if r["strategy"] == "Equal weight")

# By hand: equal weights rebalanced daily = mean of the three simple returns.
simple = prices.pct_change().dropna()
port = simple.mean(axis=1)
want_total = (np.prod(1 + port) - 1) * 100
ok(abs(eq["total_return_pct"] - want_total) < 0.01,
   f"equal-weight total {eq['total_return_pct']}% = hand-worked {want_total:.2f}%")

logsum = np.log(prices / prices.shift(1)).dropna().mean(axis=1)
wrong = (np.prod(1 + logsum) - 1) * 100
ok(want_total - wrong > 0.1,
   f"the old log-return method would have understated it ({wrong:.2f}% vs {want_total:.2f}%)")

bench = res.get("benchmark") or res.get("nifty") or {}
nifty_total = (nifty["^NSEI"].iloc[-1] / nifty["^NSEI"].iloc[0] - 1) * 100
got = bench.get("total_return_pct")
ok(got is not None and abs(got - nifty_total) < 0.01,
   f"Nifty benchmark total {got}% equals the price change {nifty_total:.2f}%")

one = sc._metrics(np.array([0.10] * 30), 100000, 0.0)
ok(abs(one["total_return_pct"] - (1.1 ** 30 - 1) * 100) < 0.01,
   "_metrics compounds simple returns exactly")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
