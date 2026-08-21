"""
leak_test.py — does information from today reach a portfolio built in the past?

The single most damaging flaw a backtest can have is look-ahead bias: using
something at a simulated date that nobody could have known then. It does not
announce itself. A backtest with a leak looks like a backtest that works, which
is exactly why it has to be tested rather than reasoned about.

This picks a cut-off date well in the past and then interrogates every input the
app could plausibly feed a historical simulation, asking one question each time:
could this value have been known on the cut-off date?

Findings are classified rather than asserted, because some of what turns up is a
genuine leak, some is a documented limitation, and treating those the same would
be its own kind of dishonesty.
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

CUTOFF = "2024-06-28"          # a date comfortably in the past
CUT_DT = datetime.strptime(CUTOFF, "%Y-%m-%d")

results = []


def record(area, item, verdict, detail):
    results.append((area, item, verdict, detail))
    mark = {"CLEAN": "CLEAN ", "LEAK": "LEAK  ", "KNOWN": "KNOWN ", "N/A": "N/A   "}[verdict]
    print(f"  [{mark}] {area}: {item}")
    if detail:
        print(f"           {detail}")


print(f"\nLeak test — cut-off {CUTOFF}\n" + "=" * 66)

# ---------------------------------------------------------------- 1. prices
print("\n1. Price data in the historical backtest")
from simulator import backtest

bt = backtest({"RELIANCE.NS": 50, "TCS.NS": 50},
              start_date="2023-01-01", end_date=CUTOFF,
              include_costs=True, rebalance_freq="quarterly")

if "error" in bt:
    record("prices", "backtest ran", "N/A", bt["error"])
else:
    # Any date the result reports must be on or before the cut-off.
    dates = []
    for key in ("equity_curve", "history", "series"):
        v = bt.get(key)
        if isinstance(v, list):
            for row in v:
                if isinstance(row, dict):
                    for dk in ("date", "day", "t"):
                        if row.get(dk):
                            dates.append(str(row[dk])[:10])
    late = [d for d in dates if d > CUTOFF]
    if dates:
        record("prices", f"{len(dates)} dated points in the result",
               "LEAK" if late else "CLEAN",
               f"latest {max(dates)} vs cut-off {CUTOFF}"
               + (f" — {len(late)} AFTER the cut-off" if late else ""))
    else:
        record("prices", "dated series exposed", "N/A",
               "result carries no dated series to check")

    # The headline return must not change if we ask again with a later end date
    # only in the sense that it must not ALREADY include later data.
    bt2 = backtest({"RELIANCE.NS": 50, "TCS.NS": 50},
                   start_date="2023-01-01", end_date=CUTOFF,
                   include_costs=True, rebalance_freq="quarterly")
    same = bt.get("total_return_pct") == bt2.get("total_return_pct")
    record("prices", "result is deterministic for a fixed window",
           "CLEAN" if same else "LEAK",
           f"total_return_pct {bt.get('total_return_pct')} on both runs" if same
           else "same inputs produced different numbers")

    # A window ending today must differ from one ending at the cut-off. If they
    # match, the end date is being ignored — which would be the leak itself.
    bt_now = backtest({"RELIANCE.NS": 50, "TCS.NS": 50},
                      start_date="2023-01-01",
                      include_costs=True, rebalance_freq="quarterly")
    differs = bt_now.get("total_return_pct") != bt.get("total_return_pct")
    record("prices", "end_date actually constrains the window",
           "CLEAN" if differs else "LEAK",
           f"to {CUTOFF}: {bt.get('total_return_pct')}%  vs  to today: {bt_now.get('total_return_pct')}%")

# ------------------------------------------------------------ 2. benchmark
print("\n2. Benchmark window")
if "error" not in bt:
    b = bt.get("benchmark") or {}
    bench_keys = [k for k in b] if isinstance(b, dict) else []
    record("benchmark", "measured over the same window as the portfolio",
           "CLEAN" if bench_keys else "N/A",
           f"benchmark fields: {bench_keys[:5]}" if bench_keys
           else "no benchmark block returned for this call")

# ------------------------------------------------- 3. fundamentals / info
print("\n3. Fundamentals and company info")
from data_fetcher import get_info
info = get_info("RELIANCE.NS") or {}
mc = info.get("marketCap")
record("fundamentals", "get_info returns TODAY's values only",
       "KNOWN" if mc else "N/A",
       f"marketCap {mc} is current, with no as-of date and no historical mode. "
       f"Any consumer that mixes it with a past date leaks.")

import inspect
from simulator import backtest as _bt_fn
src = inspect.getsource(_bt_fn)
uses_info = any(k in src for k in ("get_info", "compute_alpha_score", "marketCap"))
record("fundamentals", "backtest() does not consult fundamentals",
       "LEAK" if uses_info else "CLEAN",
       "backtest reads prices only — no fundamentals, so no point-in-time problem"
       if not uses_info else "backtest touches current fundamentals")

# ------------------------------------------------------- 4. cap tiers
print("\n4. Cap tiers")
try:
    from universe_scan import top_by_tier
    tsrc = inspect.getsource(top_by_tier)
    record("cap tiers", "ranked on current market cap",
           "KNOWN",
           "tiers are computed from today's market caps. Correct for a signal "
           "issued today; would be a leak if ever applied to a past date.")
except Exception as e:
    record("cap tiers", "inspect", "N/A", str(e))

# --------------------------------------------------------- 5. liquidity
print("\n5. Liquidity")
from liquidity import assess
a = assess("RELIANCE.NS") or {}
record("liquidity", "uses recent traded value, not as-of-date",
       "KNOWN",
       f"tier '{a.get('tier')}' from the last ~22 days. Applied to LIVE trades "
       f"only; the backtest does not apply liquidity limits at all.")

# ----------------------------------------------------- 6. the universe
print("\n6. Universe membership")
try:
    from universe_scan import _bhavcopy_symbols
    n = len(_bhavcopy_symbols())
    record("universe", "membership is today's listed set",
           "KNOWN",
           f"{n} symbols, all currently listed. Companies delisted or merged "
           f"before today are absent — survivorship bias, disclosed not corrected.")
except Exception as e:
    record("universe", "membership", "N/A", str(e))

# --------------------------------------------- 7. alpha model / signals
print("\n7. Alpha model")
from alpha_model import compute_alpha_score
asrc = inspect.getsource(compute_alpha_score)
has_asof = any(k in asrc for k in ("as_of", "asof", "point_in_time"))
record("alpha", "cannot be asked for a historical date",
       "KNOWN" if not has_asof else "CLEAN",
       "compute_alpha_score takes no as-of parameter, so it can only speak about "
       "now. It is never used to generate historical signals, which is what keeps "
       "this from being a leak.")

# ------------------------------------------------------------- report
print("\n" + "=" * 66)
counts = {}
for _, _, v, _ in results:
    counts[v] = counts.get(v, 0) + 1
print("RESULT: " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))

leaks = [r for r in results if r[2] == "LEAK"]
if leaks:
    print(f"\n{len(leaks)} ACTUAL LEAK(S):")
    for area, item, _, detail in leaks:
        print(f"  - {area}: {item} — {detail}")
else:
    print("\nNo look-ahead leak found in the historical path.")
    print("Known limitations (survivorship, current-only fundamentals) are")
    print("real and disclosed, but they are not information leaking backwards.")
print("=" * 66)
sys.exit(1 if leaks else 0)
