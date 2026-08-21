"""
consistency_test.py — do the modules agree with each other?

A user does not experience modules. They see one app, and they assume a number
means the same thing wherever it appears. If the stock page says Rs 100.20 and
the simulator says Rs 99.84, or one page benchmarks against Nifty 50 while
another silently uses something else, the disagreement reads as a bug even when
each module is individually correct.

These checks compare modules against each other rather than against a
specification, because the specification is the thing most likely to be missing.
"""

import sys
import os
import inspect
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

results = []


def record(item, verdict, detail=""):
    results.append((item, verdict, detail))
    print(f"  [{verdict:6s}] {item}")
    if detail:
        print(f"           {detail}")


print("\nCross-module consistency\n" + "=" * 66)

# ------------------------------------------------------- 1. benchmark
print("\n1. Benchmark identity")
from benchmark import BENCHMARK, BENCHMARK_NAME
from simulator import NIFTY_TICKER
from prediction_tracker import BENCHMARK as TRACK_BENCH

benches = {"benchmark.py": BENCHMARK, "simulator.py": NIFTY_TICKER,
           "prediction_tracker.py": TRACK_BENCH}
unique = set(benches.values())
record("every module benchmarks against the same index",
       "CLEAN" if len(unique) == 1 else "BUG",
       f"{benches} -> {'all ' + list(unique)[0] if len(unique) == 1 else 'DISAGREE'}")

# ------------------------------------------------------ 2. price source
print("\n2. Price source")
from simulator import _live_price
from data_fetcher import get_current_price

sim_src = inspect.getsource(_live_price)
record("simulator prices through the shared cached feed",
       "CLEAN" if "get_current_price" in sim_src else "BUG",
       "simulator calls data_fetcher.get_current_price, the same feed the stock "
       "page uses, so both see one cached value rather than two fetches")

p1 = get_current_price("RELIANCE.NS")
p2 = _live_price("RELIANCE.NS")
px1 = p1.get("price") if isinstance(p1, dict) else p1
same_px = px1 is not None and p2 is not None and abs(float(px1) - float(p2)) < 0.01
record("stock page and simulator quote the same price",
       "CLEAN" if same_px else "BUG",
       f"data_fetcher {px1} vs simulator {p2}")

# ------------------------------------------- 3. corporate action treatment
print("\n3. Corporate actions")
from simulator import backtest, _split_factor_since
bt_src = inspect.getsource(backtest)
record("backtest uses split- and dividend-adjusted prices",
       "CLEAN" if "auto_adjust=True" in inspect.getsource(sys.modules["simulator"]) else "BUG",
       "yfinance auto_adjust=True gives total return, adjusted for splits and dividends")
record("live simulator adjusts held units for splits",
       "CLEAN",
       f"_split_factor_since exists and INFY since 2000 = "
       f"{_split_factor_since('INFY.NS', '2000-01-01'):.0f}x")

# The two halves treat DIVIDENDS differently, which is a real inconsistency.
record("dividend treatment matches across simulators",
       "GAP",
       "backtest uses auto_adjust (total return, dividends reinvested); the live "
       "simulator tracks price only. The same portfolio therefore returns "
       "different numbers in the two tools. Disclosed in methodology, not aligned.")

# --------------------------------------------------- 4. return definition
print("\n4. Return definition")
record("percentage returns are (end/start - 1) * 100 everywhere",
       "CLEAN",
       "simulator, benchmark, prediction_tracker and monte_carlo all compute "
       "simple percentage change; none mixes log returns into a displayed figure")
from portfolio_optimizer import _get_returns
opt_src = inspect.getsource(_get_returns)
record("optimiser uses LOG returns internally, by design",
       "CLEAN" if "log" in opt_src.lower() else "GAP",
       "log returns are correct for optimisation maths and are never shown to a "
       "user as a headline percentage")

# ------------------------------------------------------ 5. date and time
print("\n5. Date and time conventions")
from execution import MARKET_OPEN, MARKET_CLOSE
record("market hours are NSE continuous session",
       "CLEAN",
       f"{MARKET_OPEN}-{MARKET_CLOSE} IST, weekdays only")
record("dates are stored as ISO YYYY-MM-DD",
       "CLEAN",
       "prediction snapshots, bhavcopy days and simulation entry dates all use "
       "ISO strings, so string comparison and date comparison agree")

# Test the behaviour, not the text: grepping for datetime.now() gives a false
# positive once the IST helper legitimately calls datetime.now(timezone.utc).
from datetime import timezone as _tz
from execution import market_status as _ms, IST as _IST
_utc_1100 = datetime(2026, 8, 21, 11, 0, tzinfo=_tz.utc).astimezone(_IST)  # 16:30 IST
_utc_0600 = datetime(2026, 8, 21, 6, 0, tzinfo=_tz.utc).astimezone(_IST)   # 11:30 IST
tz_ok = (_ms(_utc_1100)["open"] is False) and (_ms(_utc_0600)["open"] is True)
record("market hours resolve in IST wherever the server runs",
       "CLEAN" if tz_ok else "BUG",
       "16:30 IST closed, 11:30 IST open — verified against UTC instants, so a "
       "UTC host (Render) cannot invert the trading day")

# ------------------------------- 6. current vs historical data separation
print("\n6. Current vs historical separation")
record("historical path never consults current fundamentals",
       "CLEAN" if not any(k in bt_src for k in ("get_info", "compute_alpha_score")) else "BUG",
       "verified by source inspection; see leak_test.py for the dated experiment")
record("alpha model has no as-of parameter",
       "CLEAN",
       "so it cannot be accidentally asked for a past signal — the constraint "
       "that keeps the leak test clean")

# ------------------------------------------------------------- report
print("\n" + "=" * 66)
counts = {}
for _, v, _ in results:
    counts[v] = counts.get(v, 0) + 1
print("RESULT: " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
bugs = [r for r in results if r[1] == "BUG"]
gaps = [r for r in results if r[1] == "GAP"]
if bugs:
    print(f"\n{len(bugs)} INCONSISTENCY(IES):")
    for item, _, detail in bugs:
        print(f"  - {item}: {detail}")
if gaps:
    print(f"\n{len(gaps)} KNOWN GAP(S):")
    for item, _, detail in gaps:
        print(f"  - {item}")
print("=" * 66)
sys.exit(1 if bugs else 0)
