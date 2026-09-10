"""
unpriced_holdings_test.py — the portfolio simulated must be the portfolio shown.

Step 5 found two ways Portfolio Lab answered a question nobody asked:

  1. A holding with no price history was dropped inside the Monte Carlo layer
     and the rest re-scaled to 100%, while what-if kept displaying the original
     weights. Typing RELIANC for RELIANCE showed a 50/50 portfolio and simulated
     100% of the other stock.

  2. Scenarios added the highest-alpha stocks from the scan and simulated them
     by resampling their own past returns. A stock picked FOR strong past
     returns, replayed from those returns, looks like an improvement on both
     return and downside every time.

Offline: yfinance is replaced by a fixed price table, so results are
deterministic and no request leaves the machine. The table deliberately
INCLUDES the stock a scan would pick, so the scenarios check cannot pass merely
because the pick failed to price.
"""

import os
import sqlite3
import sys
import types

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "unpriced_holdings_test.db")
fake_db = types.ModuleType("db")
fake_db.get_conn = lambda: sqlite3.connect(DB)
fake_db.IS_POSTGRES = False
sys.modules["db"] = fake_db

# A scan that would hand scenarios a very attractive stock to add.
planted_scan = types.ModuleType("universe_scan")
planted_scan.top_by_tier = lambda n=25, min_confidence=0.4: {
    "large_cap": {"buys": [{"ticker": "PICK.NS", "alpha_score": 91.0}]},
    "mid_cap": {"buys": [{"ticker": "PICK2.NS", "alpha_score": 80.0}]},
    "small_cap": {"buys": [{"ticker": "PICK3.NS", "alpha_score": 70.0}]},
}
planted_scan.get_signal_history = lambda t, limit=1: []
sys.modules["universe_scan"] = planted_scan

import monte_carlo as MC            # noqa: E402
import portfolio_scenarios as PS    # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""),
          flush=True)


def banner(title):
    print("\n" + "=" * 74 + f"\n{title}\n" + "=" * 74, flush=True)


_rng = np.random.default_rng(3)
_IDX = pd.bdate_range("2023-01-02", periods=800)


def _series(drift):
    return pd.DataFrame(
        {"Close": 100 * np.exp(np.cumsum(_rng.normal(drift, 0.012, len(_IDX))))},
        index=_IDX)


PRICES = {t: _series(0.0003) for t in ("RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS")}
# The picks have had a spectacular run -- exactly what a momentum-heavy score rewards.
for _t in ("PICK.NS", "PICK2.NS", "PICK3.NS"):
    PRICES[_t] = _series(0.003)


def fake_download(ticker, start=None, end=None, progress=False, auto_adjust=True, **kw):
    return PRICES.get(ticker, pd.DataFrame())


MC.yf.download = fake_download


def reset_caches():
    MC._HIST_CACHE.clear()
    MC._PRICE_CACHE.clear()


# --------------------------------------------------------------------------
banner("1. THE SIMULATOR NAMES WHAT IT COULD NOT PRICE")

reset_caches()
series, unpriced = MC._portfolio_daily_returns({"RELIANCE.NS": 50, "RELIANC.NS": 50})
check("the returns helper reports the unpriced holding",
      unpriced == ["RELIANC.NS"], str(unpriced))
check("  ...and builds no series for a portfolio it cannot fully price",
      len(series) == 0, f"{len(series)} rows")

r = MC.simulate({"RELIANCE.NS": 50, "RELIANC.NS": 50}, 100000)
check("simulate refuses a portfolio with an unpriced holding",
      "error" in r and "median_value" not in r, str(r.get("error"))[:80])
check("  ...and the refusal names it", "RELIANC" in str(r.get("error")))
check("  ...and lists it for the caller", r.get("unpriced") == ["RELIANC.NS"],
      str(r.get("unpriced")))

r = MC.simulate({"RELIANCE.NS": 50, "TCS.NS": 50}, 100000)
check("a fully priced portfolio still simulates", "error" not in r,
      str(r.get("error")))

# --------------------------------------------------------------------------
banner("2. A FAILURE IS NOT REMEMBERED")

# A symbol that fails once may be a blip. If the failure were cached, the blip
# would outlast the network problem that caused it.
reset_caches()
r = MC.simulate({"RELIANCE.NS": 50, "LATE.NS": 50}, 100000)
check("a portfolio with an unavailable holding is refused", "error" in r)
PRICES["LATE.NS"] = _series(0.0003)
r = MC.simulate({"RELIANCE.NS": 50, "LATE.NS": 50}, 100000)
check("  ...and simulates as soon as that holding can be priced",
      "error" not in r, str(r.get("error")))

# --------------------------------------------------------------------------
banner("3. WHAT-IF PASSES THE REASON ON")

reset_caches()
r = PS.what_if({"RELIANCE.NS": 50000, "RELIANC.NS": 50000})
check("what-if refuses a typo'd holding instead of simulating without it",
      "error" in r and "base" not in r, str(r)[:90])
check("  ...and says which holding", "RELIANC" in str(r.get("error")))

r = PS.what_if({"RELIANCE.NS": 50000, "TCS.NS": 50000},
               new_holdings={"RELIANCE.NS": 50000, "TSC.NS": 50000})
check("an edit that introduces a typo is refused and named",
      "error" in r and "TSC" in str(r.get("error")), str(r.get("error"))[:90])

r = PS.what_if({"RELIANCE.NS": 70000, "TCS.NS": 30000}, max_weight_pct=60)
check("a normal what-if still works", "error" not in r and r.get("changed") is True,
      str(r.get("error")))

# --------------------------------------------------------------------------
banner("4. SCENARIOS DOES NOT PICK STOCKS")

reset_caches()
PS._alpha_map = lambda tickers: {"RELIANCE.NS": 10.0, "TCS.NS": 5.0,
                                 "HDFCBANK.NS": -23.0}
held = {"RELIANCE.NS": 40000, "TCS.NS": 30000, "HDFCBANK.NS": 30000}
r = PS.scenarios(held)
check("scenarios runs", "error" not in r and r.get("n_scenarios", 0) > 0,
      str(r.get("error")))
added = sorted({t for s in r.get("scenarios", []) for t in (s.get("weights") or {})}
               - set(held))
check("no scenario adds a stock the user does not hold", not added,
      f"added {added} -- the planted picks were priceable, so this is not luck")
check("the helper that picked them is gone",
      not hasattr(PS, "_candidates_not_held"))
more = str(r.get("more_names") or "")
check("the advice to hold more names is still there, as a sentence",
      "8-12" in more and "forecast" in more.lower(), more[:80])
drop = [s for s in r.get("scenarios", []) if s["name"].startswith("Drop HDFCBANK")]
check("the drop-the-weakest option carries the track-record caveat",
      bool(drop) and "track record" in drop[0]["why"], (drop[0]["why"] if drop else "")[:80])

r = PS.scenarios({"RELIANCE.NS": 50000, "RELIANC.NS": 50000})
check("scenarios refuses a typo'd holding and names it",
      "error" in r and "RELIANC" in str(r.get("error")), str(r.get("error"))[:90])

try:
    os.remove(DB)
except Exception:
    pass

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
