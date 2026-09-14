"""
unscoreable_reason_test.py — a real company the price source is short of must
not be reported as a mistyped symbol, and must not look like an outage.

On 2026-09-14, 47 stocks that had been scoring failed two nights running with
"No market data found ... Check the symbol". The symbols were right: Yahoo held
18-19 days of their price history (it restarted on 2026-08-17) and no market
cap. The nightly check read the run as an outage of ours.

What must NOT change is checked first: scores, the filter's reading of the
message, and the message for a symbol that does not exist.

Offline: the price download and every other factor are stubs.
"""
import os
import sys
import types

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""),
          flush=True)


import alpha_model as A  # noqa: E402


def prices(n):
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({"Close": 100.0 * np.cumprod(np.full(n, 1.001))}, index=idx)


def stub_download(n):
    stub = types.ModuleType("yfinance")
    stub.download = lambda *a, **k: prices(n) if n else pd.DataFrame({"Close": []})
    A.yf = stub


NEUTRAL = {"score": 0.0, "confidence": 0.0}
A._compute_sentiment_factor = lambda t, *a, **k: dict(NEUTRAL)
A._compute_quality_factor = lambda t, *a, **k: dict(NEUTRAL)
A._compute_value_factor = lambda t, *a, **k: dict(NEUTRAL)


def refusal(n, info):
    stub_download(n)
    A._ticker_info = lambda t: dict(info)
    A._SCORE_CACHE.clear()
    return A.compute_alpha_score("REAL.NS")


print("=" * 74 + "\n1. WHAT MUST NOT CHANGE\n" + "=" * 74)
stub_download(320)
full = A._compute_momentum_factor("REAL.NS")
check("a full history still scores momentum", full.get("confidence", 0) > 0, str(full)[:80])
for n in (0, 19):
    stub_download(n)
    r = A._compute_momentum_factor("REAL.NS")
    check(f"{n} days of prices: momentum still scores nothing",
          r.get("score") == 0.0 and r.get("confidence") == 0.0, str(r))
fake = refusal(0, {})
check("a symbol with no prices and no market cap is still told to check the symbol",
      "Check the symbol" in fake.get("error", ""), str(fake))

print("\n" + "=" * 74 + "\n2. A SHORT HISTORY IS REPORTED AS WHAT IT IS\n" + "=" * 74)
stub_download(19)
r = A._compute_momentum_factor("REAL.NS")
check("19 days of prices: the reason says the history is too short",
      r.get("reason") == getattr(A, "_SHORT_PRICE_HISTORY", "price history too short"),
      str(r.get("reason")))
stub_download(0)
check("no prices at all: the reason is unchanged",
      A._compute_momentum_factor("REAL.NS").get("reason") == "price data unavailable")
short = refusal(19, {"longName": "Real Company Ltd", "quoteType": "EQUITY"})
err = short.get("error", "")
check("19 days of prices and no market cap: refused, with the real reason",
      "fewer than 60 days of prices and no market cap" in err, err)
check("  ...and not told to check the symbol", "Check the symbol" not in err, err)

print("\n" + "=" * 74 + "\n3. THE FILTER AND THE AUDITS STILL READ IT\n" + "=" * 74)
fake_db = types.ModuleType("db")
fake_db.get_conn = lambda: None
fake_db.IS_POSTGRES = False
sys.modules.setdefault("db", fake_db)
import universe_scan as U  # noqa: E402
import data_integrity as DI  # noqa: E402

check("the filter still counts it as no market data", U._NO_DATA in err.lower(), err)
check("the early warning recognises it as a short history", U._SHORT_HISTORY in err.lower(), err)
check("the old message is not mistaken for a short history",
      U._SHORT_HISTORY not in fake.get("error", "").lower())
other = refusal(19, {}).get("error", "").replace("REAL.NS", "OTHER.NS")
check("the failure audit groups every short-history stock as one cause",
      DI._err_signature(err) == DI._err_signature(other), DI._err_signature(err))
check("  ...separate from mistyped symbols",
      DI._err_signature(err) != DI._err_signature(fake.get("error", "")))

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
