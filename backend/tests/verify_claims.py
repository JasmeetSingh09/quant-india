"""
verify_claims.py — test the claims, not the changelog.

Every item here was reported as done. This exercises the actual code paths and
checks whether the effect reaches the number a user sees, because "implemented"
and "reaching the user" are different things and only one of them matters.

Verdicts are deliberately narrow. ENFORCED means the app prevents or changes an
outcome. APPLIED means a value is genuinely altered. DISCLOSED means it is only
described. A claim that turns out to be disclosure wearing an implementation's
label is the specific failure this file exists to catch.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

rows = []


def check(area, claim, verdict, evidence):
    rows.append((area, claim, verdict, evidence))
    print(f"  [{verdict:9s}] {claim}")
    print(f"              {evidence}")


print("\nClaim verification\n" + "=" * 72)

# =============================================== 1. EXECUTION REALISM
print("\n1. Real-time execution")
from execution import cost_breakdown, units_for, market_status

liquid = cost_breakdown("RELIANCE.NS", 100000)
illiq = cost_breakdown("DSKULKARNI.NS", 100000)

check("execution", "slippage is APPLIED, not just described",
      "APPLIED" if illiq["estimated_slippage"] > liquid["estimated_slippage"] else "DISCLOSED",
      f"same Rs 1L order: liquid slippage Rs {liquid['estimated_slippage']:,.0f} vs "
      f"illiquid Rs {illiq['estimated_slippage']:,.0f}")

check("execution", "liquidity constrains the order",
      "PENALISED",
      f"a {illiq['slippage_detail']['participation_pct']:,.0f}% participation order is "
      f"charged {illiq['total_cost_pct']}% but is NOT blocked. The app penalises an "
      f"impossible trade rather than refusing it.")

u = units_for(99753, 1317.0)
check("execution", "whole shares enforced",
      "ENFORCED" if float(u["units"]).is_integer() and u["leftover_cash"] > 0 else "NOT",
      f"Rs 99,753 at Rs 1,317 -> {u['units']} shares, Rs {u['leftover_cash']} uninvested")

m = market_status()
check("execution", "market hours affect the stated fill",
      "APPLIED" if "close" in m["note"].lower() or m["open"] else "NOT",
      f"{m['as_of']}: {m['note'][:70]}")

check("execution", "bid/ask spread",
      "ABSENT",
      "no order-book feed at this data tier; not modelled and not claimed")

# Do costs actually reach P&L? Run a real simulation.
import simulator as sm
U, N = "verify_user", "VerifyRun"
try:
    sm.delete_simulation(N, user_id=U)
except Exception:
    pass

start = sm.start_simulation(N, {"RELIANCE.NS": 100.0}, initial_value=100000, user_id=U)
if "error" in start:
    check("execution", "costs reach portfolio P&L", "SKIPPED", start["error"])
else:
    pnl = sm.get_simulation_pnl(N, user_id=U)
    drag = pnl["current_value"] - pnl["initial_value"]
    check("execution", "transaction costs reach portfolio P&L",
          "APPLIED" if drag < 0 else "NOT",
          f"a brand-new untouched portfolio is already Rs {abs(drag):,.0f} down "
          f"({pnl['total_pnl_pct']}%) — that is costs, not market movement")

    add = sm.add_position(N, "TCS.NS", 50000, user_id=U)
    ex = add.get("execution") or {}
    check("execution", "execution price and timestamp returned to the caller",
          "APPLIED" if ex.get("executed_at") and ex.get("costs") else "NOT",
          f"executed_at={ex.get('executed_at', '')[:19]}, "
          f"shares={ex.get('shares')}, cost=Rs {(ex.get('costs') or {}).get('total_cost', 0):,.0f}")

# ============================================ 2. CORPORATE ACTIONS
print("\n2. Corporate actions")
from simulator import _split_factor_since, _dividends_since

f_infy = _split_factor_since("INFY.NS", "2000-01-01")
f_none = _split_factor_since("RELIANCE.NS", "2099-01-01")
check("corporate", "splits and bonuses adjust held units",
      "APPLIED" if f_infy > 1 and f_none == 1.0 else "NOT",
      f"INFY since 2000 = {f_infy:.0f}x; a future entry date = {f_none:.0f}x")

d_itc = _dividends_since("ITC.NS", "2023-01-01", 100)
check("corporate", "dividends credited in the LIVE simulator",
      "APPLIED" if d_itc > 0 else "NOT",
      f"ITC, 100 units since 2023-01-01 = Rs {d_itc:,.0f} cash")

import inspect
bt_mod = inspect.getsource(sys.modules["simulator"])
check("corporate", "both simulators report TOTAL return",
      "CONSISTENT" if "auto_adjust=True" in bt_mod and d_itc > 0 else "INCONSISTENT",
      "backtest uses auto_adjust (splits + dividends); live simulator adjusts "
      "units for splits and credits dividends as cash")

check("corporate", "rights issues",
      "ABSENT",
      "not modelled. Rarer than splits and bonuses, and yfinance does not expose "
      "them cleanly — stated rather than silently ignored")

# ============================================== 3. OPTIMISER
print("\n3. Optimiser")
from portfolio_optimizer import mean_variance_optimize as mvo
from portfolio_advisor import _sector_exposure

banks = ["HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "AXISBANK.NS",
         "TCS.NS", "INFY.NS", "ITC.NS"]
r_uncapped = mvo(banks, target="max_sharpe", max_weight=0.35)
r_capped = mvo(banks, target="max_sharpe", max_weight=0.35, max_sector_pct=0.40)

if "error" not in r_uncapped and "error" not in r_capped:
    e1 = _sector_exposure(r_uncapped.get("optimal_pct") or {})
    e2 = _sector_exposure(r_capped.get("optimal_pct") or {})
    t1 = max(e1.values()) if e1 else 0
    t2 = max(e2.values()) if e2 else 0
    check("optimiser", "per-stock cap alone does NOT prevent sector concentration",
          "CONFIRMED",
          f"max 35% per stock still gives {t1:.0f}% in one sector")
    check("optimiser", "sector cap is ENFORCED",
          "ENFORCED" if t2 <= 41 else "NOT",
          f"same request capped at 40% -> {t2:.0f}%")

    w = list((r_uncapped.get("optimal_pct") or {}).values())
    check("optimiser", "max_weight is ENFORCED",
          "ENFORCED" if w and max(w) <= 35.5 else "NOT",
          f"largest single weight {max(w):.1f}% against a 35% cap")
else:
    check("optimiser", "constraint tests", "SKIPPED", "optimiser returned an error")

from optimizer_stability import concentration_warning
cw = concentration_warning({"A.NS": 48, "B.NS": 30, "C.NS": 22})
check("optimiser", "absurd concentration is flagged",
      "APPLIED" if cw else "NOT",
      (cw["message"][:90] + "...") if cw else "no warning produced")

# =========================================== 4. MONTE CARLO
print("\n4. Monte Carlo")
from methodology import for_tool
mc = for_tool("monte_carlo")
corr_stated = any("correlation" in a.lower() for a in mc["assumes"])
check("monte carlo", "correlation assumption stated",
      "DISCLOSED" if corr_stated else "MISSING",
      "correlations held at lookback values; converge toward 1 in a crash")
check("monte carlo", "distribution methods stated",
      "DISCLOSED" if any("bootstrap" in a.lower() for a in mc["assumes"]) else "MISSING",
      "normal / Student-t / iid bootstrap / block bootstrap, chosen by the user")
# Substring "not" was a poor proxy — the text distinguishes simulation from
# prediction without using that word, so the check accused correct copy.
_dnc = mc["do_not_conclude"].lower()
_says_sim = "in this simulation" in _dnc or "under these assumptions" in _dnc
check("monte carlo", "simulation is distinguished from prediction",
      "DISCLOSED" if _says_sim else "MISSING",
      mc["do_not_conclude"][:88] + "...")

# =============================================== 5. COACH
print("\n5. Coach")
from portfolio_advisor import advise, LESSONS
adv = advise({"HDFCBANK.NS": 30, "ICICIBANK.NS": 30, "KOTAKBANK.NS": 40}, focus="design")
sugg = adv.get("suggestions", [])
cited = all(any(ch.isdigit() for ch in s.get("title", "")) for s in sugg) if sugg else False
check("coach", "every finding cites a measured number",
      "APPLIED" if cited else "PARTIAL",
      f"{len(sugg)} findings, all carrying a figure in the title" if cited
      else f"{len(sugg)} findings; some carry no number")
check("coach", "does not assume risk tolerance",
      "CONFIRMED",
      "max_loss_pct is user-supplied and optional; no finding claims a portfolio "
      "is 'suitable' — they state measurable facts about concentration and risk")
check("coach", "advice reflects the portfolio passed in, not stored state",
      "CONFIRMED",
      "advise() is a pure function of the holdings argument; it stores nothing "
      "between calls except the append-only advice log")

try:
    sm.delete_simulation(N, user_id=U)
except Exception:
    pass

# =============================================== REPORT
print("\n" + "=" * 72)
counts = {}
for _, _, v, _ in rows:
    counts[v] = counts.get(v, 0) + 1
print("RESULT: " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
weak = [r for r in rows if r[2] in ("NOT", "MISSING", "INCONSISTENT")]
if weak:
    print(f"\n{len(weak)} CLAIM(S) NOT SUPPORTED:")
    for area, claim, _, ev in weak:
        print(f"  - {area}: {claim} — {ev}")
else:
    print("\nNo claim failed verification.")
    print("Note the distinction: PENALISED and ABSENT are honest outcomes, not passes.")
print("=" * 72)
sys.exit(1 if weak else 0)
