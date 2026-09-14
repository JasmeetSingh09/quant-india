"""
risk_metrics_test.py — one Sharpe and one Sortino, and every page uses them.

Until 2026-09-14 four modules computed Sortino four ways and two computed Sharpe
differently, so one portfolio showed 0.27, 0.38, 0.48 or 0.61 depending on the
page (docs/PHASE2_FINDINGS_2026-09-14.md, section 2). These checks pin the
definition with numbers worked by hand, then check that every module reporting
the ratios gets the same answer from the same returns.

Offline and deterministic.
"""
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""),
          flush=True)


def close(a, b, tol=1e-4):
    return a is not None and b is not None and abs(a - b) <= tol


def attempt(label, fn):
    try:
        return fn()
    except Exception as e:
        check(f"{label} runs", False, f"{type(e).__name__}: {e}")
        return None


try:
    import risk_metrics as RM
except ImportError as e:
    check("risk_metrics can be imported", False, str(e))
    print(f"\npassed {len(PASS)}, failed {len(FAIL)}")
    sys.exit(1)

print("=" * 74 + "\n1. THE DEFINITION, WORKED BY HAND\n" + "=" * 74)
# Four monthly returns and a 12% risk-free rate, so the target is 1% a month.
#   excess = +0.01, -0.02, +0.02, -0.03; mean -0.005
#   sd of the returns (n - 1) = sqrt(0.0017 / 3) = 0.0238048
#   Sharpe  = -0.005 / 0.0238048 * sqrt(12) = -0.727607
#   downside deviation over ALL four months = sqrt((0.02^2 + 0.03^2) / 4) = 0.0180278
#   Sortino = -0.005 / 0.0180278 * sqrt(12) = -0.960769
R = [0.02, -0.01, 0.03, -0.02]
check("Sharpe matches the hand calculation, -0.727607",
      close(RM.sharpe(R, 12, 0.12), -0.727607), str(RM.sharpe(R, 12, 0.12)))
check("Sortino matches the hand calculation, -0.960769",
      close(RM.sortino(R, 12, 0.12), -0.960769), str(RM.sortino(R, 12, 0.12)))

print("\n" + "=" * 74 + "\n2. CASES THE OLD FORMULAS GOT WRONG, AND UNDEFINED ONES\n" + "=" * 74)
# Every losing day loses exactly 1%. The old simulator divided by the spread of
# the losing days among themselves, which is zero, and reported 0.00.
#   target 0.065/252 = 0.000258; losing-day excess -0.010258 on half the days
#   DD = 0.010258 / sqrt(2) = 0.0072535; Sortino = -0.000258 / 0.0072535 * sqrt(252) = -0.5646
steady = [0.01, -0.01] * 126
so = RM.sortino(steady, 252, 0.065)
check("steady 1% losses give a real Sortino, -0.5646, not 0.00",
      close(so, -0.5646, 1e-3), str(so))
check("no period below the target: Sortino is undefined (None), not 0",
      RM.sortino([0.02, 0.03, 0.01], 12, 0.0) is None)
check("a flat series: Sharpe is undefined (None)",
      RM.sharpe([0.01] * 10, 12, 0.0) is None)
check("fewer than two periods: both undefined",
      RM.sharpe([0.05], 12) is None and RM.sortino([0.05], 12) is None)
check("missing values are skipped, not counted as zero returns",
      close(RM.sharpe(R + [float("nan"), None], 12, 0.12), -0.727607))
check("the default target is the app's risk-free rate",
      close(RM.sharpe(R, 12), RM.sharpe(R, 12, 0.065), 1e-12))

print("\n" + "=" * 74 + "\n3. EVERY MODULE THAT REPORTS THEM AGREES\n" + "=" * 74)
rng = np.random.default_rng(20260914)
daily = rng.standard_t(4, 1260) * 0.009 + 0.0009
monthly = np.array([np.prod(1 + daily[i:i + 21]) - 1 for i in range(0, len(daily), 21)])
rf = 0.065
d_sh, d_so = RM.sharpe(daily, 252, rf), RM.sortino(daily, 252, rf)
m_sh, m_so = RM.sharpe(monthly, 12, rf), RM.sortino(monthly, 12, rf)
print(f"  reference: daily Sharpe {d_sh:.4f} Sortino {d_so:.4f}; "
      f"monthly Sharpe {m_sh:.4f} Sortino {m_so:.4f}")


def _simulator():
    import simulator as S
    return S._compute_sharpe(pd.Series(daily)), S._compute_sortino(pd.Series(daily))


got = attempt("simulator", _simulator)
if got:
    check("Historical backtest (simulator): Sharpe", got[0] == round(d_sh, 4), str(got[0]))
    check("Historical backtest (simulator): Sortino", got[1] == round(d_so, 4), str(got[1]))


def _strategy_compare():
    import strategy_compare as SC
    return SC._metrics(daily, 100000.0, 0.0)


got = attempt("strategy_compare", _strategy_compare)
if got:
    check("strategy comparison: Sharpe", got["sharpe"] == round(d_sh, 3), str(got["sharpe"]))
    check("strategy comparison: Sortino", got["sortino"] == round(d_so, 3), str(got["sortino"]))


def _momentum_backtest():
    import momentum_backtest as MB
    return MB._annualised(pd.Series(monthly))


got = attempt("momentum_backtest", _momentum_backtest)
if got:
    check("momentum backtest: Sharpe", got["sharpe"] == round(m_sh, 3), str(got["sharpe"]))
    check("momentum backtest: Sortino", got["sortino"] == round(m_so, 3), str(got["sortino"]))


def _pit_backtest():
    import pit_backtest as PB
    return PB._stats(list(monthly))


got = attempt("pit_backtest", _pit_backtest)
if got:
    check("point-in-time backtest: Sharpe", got["sharpe"] == round(m_sh, 3), str(got["sharpe"]))
    check("point-in-time backtest: Sortino", got["sortino"] == round(m_so, 3), str(got["sortino"]))


def _pit_validation():
    import pit_validation as PV
    return PV._series_stats(list(monthly))


got = attempt("pit_validation", _pit_validation)
if got:
    check("factor validation's described portfolio: Sharpe",
          got["sharpe"] == round(m_sh, 3), str(got["sharpe"]))

pairs_src = open(os.path.join(HERE, "..", "modules", "pairs_trading.py"), encoding="utf-8").read()
check("pairs trading takes its Sharpe from risk_metrics (target 0: self-financing)",
      "from risk_metrics import sharpe" in pairs_src
      and "strat_ret.mean() / strat_ret.std()" not in pairs_src)

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
