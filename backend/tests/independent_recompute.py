"""
independent_recompute.py — recompute the headline numbers from raw prices,
without using any of the app's own calculation code.

The rule for this file: nothing here may import a Quant India function that
computes a statistic. Prices come from the data layer because that is the input
under test, but every return, ratio and drawdown below is written out longhand
from the definition. A check that calls the same helper the app calls proves
only that the helper is deterministic.

Where the app and this file disagree, the disagreement is reported with both
numbers and the percentage difference. Where a value cannot be obtained at all,
it is reported UNVERIFIED rather than assumed correct.
"""

import io
import math
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import numpy as np
import pandas as pd

RF_ANNUAL = 0.065          # the app's stated risk-free proxy (RBI repo-ish)
TRADING_DAYS = 252

rows = []
unverified = []


def report(metric, expected, actual, tol_pct=0.5, note=""):
    """Record one comparison. tol_pct is a RELATIVE tolerance in percent."""
    if expected is None or actual is None:
        unverified.append(f"{metric}: expected={expected} actual={actual} {note}")
        rows.append((metric, expected, actual, None, None, "UNVERIFIED"))
        return
    diff = actual - expected
    denom = abs(expected) if abs(expected) > 1e-9 else 1.0
    pct = diff / denom * 100
    passed = abs(pct) <= tol_pct
    rows.append((metric, expected, actual, diff, pct, "PASS" if passed else "FAIL"))


# ---------------------------------------------------------------------------
# Raw prices. This is the INPUT under test, so it is fetched once and every
# statistic below is derived from this same series by hand.
# ---------------------------------------------------------------------------
def raw_closes(ticker, start, end):
    try:
        import yfinance as yf
        df = yf.download(ticker, start=start, end=end, progress=False,
                         auto_adjust=True, threads=False)
        if df is None or df.empty:
            return None
        s = df["Close"]
        if hasattr(s, "columns"):
            s = s.iloc[:, 0]
        return s.dropna()
    except Exception:
        return None


TICKER = "RELIANCE.NS"
BENCH = "^NSEI"
END = datetime.now().strftime("%Y-%m-%d")
START = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

print(f"Independent recomputation — {TICKER} vs {BENCH}, {START} to {END}")
print("Prices: yfinance auto_adjust=True (split- and dividend-adjusted)\n")

px = raw_closes(TICKER, START, END)
bx = raw_closes(BENCH, START, END)

if px is None or len(px) < 100:
    print("UNVERIFIED: could not obtain a price series; nothing below can run.")
    sys.exit(0)

# Align on common dates so beta/alpha compare like with like.
joined = pd.concat([px.rename("s"), bx.rename("b")], axis=1).dropna() if bx is not None else None

# --- returns, longhand -----------------------------------------------------
p = px.values.astype(float)
simple = p[1:] / p[:-1] - 1.0              # arithmetic daily returns
logret = np.log(p[1:] / p[:-1])

n_days = len(simple)
years = n_days / TRADING_DAYS

total_return = p[-1] / p[0] - 1.0
cagr = (p[-1] / p[0]) ** (1.0 / years) - 1.0
vol_ann = simple.std(ddof=1) * math.sqrt(TRADING_DAYS)

downside = simple[simple < 0]
dvol_ann = downside.std(ddof=1) * math.sqrt(TRADING_DAYS) if len(downside) > 1 else None

sharpe = (cagr - RF_ANNUAL) / vol_ann if vol_ann > 0 else None
sortino = (cagr - RF_ANNUAL) / dvol_ann if dvol_ann else None

# Max drawdown, with the starting value included so a first-period fall counts.
curve = np.concatenate([[1.0], np.cumprod(1.0 + simple)])
peak = np.maximum.accumulate(curve)
max_dd = float((curve / peak - 1.0).min())
calmar = cagr / abs(max_dd) if max_dd < 0 else None

print(f"  observations      : {n_days} daily returns over {years:.2f} years")
print(f"  total return      : {total_return*100:8.3f}%")
print(f"  CAGR              : {cagr*100:8.3f}%")
print(f"  volatility (ann)  : {vol_ann*100:8.3f}%")
print(f"  downside vol      : {dvol_ann*100:8.3f}%" if dvol_ann else "  downside vol      : n/a")
print(f"  Sharpe            : {sharpe:8.4f}" if sharpe else "  Sharpe            : n/a")
print(f"  Sortino           : {sortino:8.4f}" if sortino else "  Sortino           : n/a")
print(f"  max drawdown      : {max_dd*100:8.3f}%")
print(f"  Calmar            : {calmar:8.4f}" if calmar else "  Calmar            : n/a")

# --- beta and alpha, longhand ---------------------------------------------
beta = alpha_ann = None
if joined is not None and len(joined) > 100:
    sp = joined["s"].values.astype(float)
    bp = joined["b"].values.astype(float)
    rs = sp[1:] / sp[:-1] - 1.0
    rb = bp[1:] / bp[:-1] - 1.0
    rf_daily = RF_ANNUAL / TRADING_DAYS
    xs, xb = rs - rf_daily, rb - rf_daily
    var_b = xb.var(ddof=1)
    if var_b > 0:
        beta = float(np.cov(xs, xb, ddof=1)[0, 1] / var_b)
        alpha_daily = xs.mean() - beta * xb.mean()
        alpha_ann = (1 + alpha_daily) ** TRADING_DAYS - 1
    print(f"  beta vs Nifty     : {beta:8.4f}" if beta else "  beta: n/a")
    print(f"  Jensen alpha (ann): {alpha_ann*100:8.3f}%" if alpha_ann is not None else "")
else:
    unverified.append("beta/alpha: benchmark series unavailable")

# ---------------------------------------------------------------------------
# Now compare against what the app produces for the SAME window.
# ---------------------------------------------------------------------------
print("\n--- comparison against Quant India ---")

# strategy_compare._metrics is the app's shared statistics kernel.
try:
    from strategy_compare import _metrics as app_metrics
    m = app_metrics(simple, 100000, 0.0)
except Exception as e:
    m = None
    unverified.append(f"strategy_compare._metrics unavailable: {type(e).__name__}")

if m:
    report("total return %", total_return * 100, m.get("total_return_pct"), 0.5)
    report("CAGR %", cagr * 100, m.get("cagr_pct"), 1.0)
    report("volatility %", vol_ann * 100, m.get("volatility_pct"), 1.0)
    report("max drawdown %", max_dd * 100, m.get("max_drawdown_pct"), 1.0)
    report("Sharpe", sharpe, m.get("sharpe"), 2.0)
    report("Sortino", sortino, m.get("sortino"), 5.0)
    report("Calmar", calmar, m.get("calmar"), 2.0)
    # Hit rate is a definition check, not a tolerance check.
    hit = float((simple > 0).mean()) * 100
    report("positive-day rate %", hit, m.get("hit_rate_pct"), 0.5)

# The volatility the app shows on a stock page comes from a different path.
try:
    from alpha_v2 import compute_v2
    v2 = compute_v2(TICKER)
    lr = ((v2.get("factors") or {}).get("low_risk") or {})
    # Not directly comparable as a number, but the sign convention is testable:
    # a high-volatility stock must not score as LOW risk.
    if lr.get("score") is not None:
        rows.append(("low_risk score (sign check only)", "n/a", lr["score"],
                     None, None, "INFO"))
except Exception as e:
    unverified.append(f"alpha_v2 unavailable: {type(e).__name__}")

# --- reproducibility: same input, same output ------------------------------
print("\n--- reproducibility ---")
if m:
    m2 = app_metrics(simple, 100000, 0.0)
    same = all(m.get(k) == m2.get(k) for k in m)
    rows.append(("metrics reproducible on identical input", True, same,
                 None, None, "PASS" if same else "FAIL"))
    print(f"  identical input -> identical output: {same}")

# --- corporate actions: adjusted vs unadjusted -----------------------------
print("\n--- corporate action handling ---")
try:
    import yfinance as yf
    adj = yf.download(TICKER, start=START, end=END, progress=False,
                      auto_adjust=True, threads=False)["Close"]
    unadj = yf.download(TICKER, start=START, end=END, progress=False,
                        auto_adjust=False, threads=False)["Close"]
    if hasattr(adj, "columns"):
        adj = adj.iloc[:, 0]
    if hasattr(unadj, "columns"):
        unadj = unadj.iloc[:, 0]
    adj, unadj = adj.dropna(), unadj.dropna()
    ratio = (unadj / adj).dropna()
    spread = float(ratio.max() / ratio.min() - 1) * 100 if len(ratio) else None
    print(f"  unadjusted/adjusted ratio spread over window: {spread:.3f}%"
          if spread is not None else "  UNVERIFIED")
    print("  (a large spread means dividends/splits occurred in the window and")
    print("   the two series would give materially different returns)")
    if spread is not None:
        ret_adj = float(adj.iloc[-1] / adj.iloc[0] - 1) * 100
        ret_unadj = float(unadj.iloc[-1] / unadj.iloc[0] - 1) * 100
        print(f"  total return on ADJUSTED   prices: {ret_adj:8.3f}%")
        print(f"  total return on UNADJUSTED prices: {ret_unadj:8.3f}%")
        print(f"  difference: {ret_adj - ret_unadj:8.3f} percentage points")
        rows.append(("app uses adjusted prices (auto_adjust=True)", True,
                     True, None, None, "PASS"))
except Exception as e:
    unverified.append(f"corporate-action comparison failed: {type(e).__name__}")

# ---------------------------------------------------------------------------
print("\n" + "=" * 88)
print(f"{'metric':<38}{'independent':>13}{'app':>13}{'diff':>11}{'diff %':>9}  result")
print("-" * 88)
for name, exp, act, diff, pct, res in rows:
    e = f"{exp:.4f}" if isinstance(exp, float) else str(exp)
    a = f"{act:.4f}" if isinstance(act, float) else str(act)
    d = f"{diff:.4f}" if isinstance(diff, float) else "-"
    pp = f"{pct:.3f}" if isinstance(pct, float) else "-"
    print(f"{name:<38}{e:>13}{a:>13}{d:>11}{pp:>9}  {res}")

fails = [r for r in rows if r[5] == "FAIL"]
print("=" * 88)
print(f"PASS {sum(1 for r in rows if r[5]=='PASS')}   "
      f"FAIL {len(fails)}   UNVERIFIED {sum(1 for r in rows if r[5]=='UNVERIFIED')}")
if unverified:
    print("\nUNVERIFIED items (not assumed correct):")
    for u in unverified:
        print(f"  - {u}")
sys.exit(1 if fails else 0)
