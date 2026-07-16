"""
Edge-case + property stress test for the NEW algorithms:
Black-Scholes, Equal Risk Contribution, Max Diversification, risk decomposition,
low-vol backtest, seasonality. Network calls are monkeypatched with synthetic
data so we can hammer thousands of cases deterministically.
"""
import sys, math, warnings, random
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "modules"))
import numpy as np, pandas as pd

FAILS, N = [], 0
def check(cond, label, ctx=""):
    global N; N += 1
    if not cond: FAILS.append(f"[{label}] {ctx}")
def section(s): print(f"\n=== {s} ===")

rng = np.random.default_rng(20260716)
random.seed(20260716)   # seed the stdlib RNG too — random.choice() is used below,
                        # and without this the suite is NOT reproducible run-to-run
                        # (check counts drifted and flaky cases appeared/vanished).

# ---------------------------------------------------------------------------
section("Black-Scholes: 6000 random cases — parity, Greek bounds, IV round-trip")
import black_scholes as BS

for _ in range(6000):
    S = float(rng.uniform(10, 5000)); K = float(rng.uniform(10, 5000))
    days = float(rng.uniform(1, 900)); T = days / 365
    r = float(rng.uniform(0, 12)); v = float(rng.uniform(1, 120))
    c = BS.black_scholes(S, K, T, r, v, "call")
    p = BS.black_scholes(S, K, T, r, v, "put")
    check("error" not in c and "error" not in p, "bs_errored", f"{S},{K},{days},{r},{v}")
    if "error" in c: continue
    # non-negative, >= intrinsic
    check(c["price"] >= -1e-6, "call_negative", f"{c['price']}")
    check(p["price"] >= -1e-6, "put_negative", f"{p['price']}")
    # European lower bounds (NOT max/American): call >= S - K e^-rT ; put >= K e^-rT - S.
    # A European put CAN trade below its (undiscounted) intrinsic — that is correct.
    disc = math.exp(-(r/100) * T)
    check(c["price"] >= max(0, S - K*disc) - 1e-3, "call_below_euro_bound", f"{c}")
    check(p["price"] >= max(0, K*disc - S) - 1e-3, "put_below_euro_bound", f"{p}")
    # bounds: call <= S ; put <= K
    check(c["price"] <= S + 1e-4, "call_gt_spot", f"{c['price']} vs {S}")
    check(p["price"] <= K + 1e-4, "put_gt_strike", f"{p['price']} vs {K}")
    # put-call parity: C - P = S - K e^-rT
    parity = S - K * math.exp(-(r/100) * T)
    check(abs((c["price"] - p["price"]) - parity) < 0.02 * max(1, S/100), "parity_broken",
          f"C-P={c['price']-p['price']:.3f} vs {parity:.3f}")
    # Greek bounds
    g = c["greeks"]
    check(0 <= g["delta"] <= 1.0001, "call_delta_oob", f"{g['delta']}")
    check(-1.0001 <= p["greeks"]["delta"] <= 0.0001, "put_delta_oob", f"{p['greeks']['delta']}")
    check(g["gamma"] >= -1e-9, "gamma_negative", f"{g['gamma']}")
    check(g["vega"] >= -1e-9, "vega_negative", f"{g['vega']}")
    check(0 <= c["prob_itm_pct"] <= 100, "probitm_oob", f"{c['prob_itm_pct']}")
    check(all(math.isfinite(x) for x in g.values()), "greek_nonfinite", f"{g}")

# monotonicity: call rises with spot and with vol
for _ in range(500):
    K = float(rng.uniform(50, 2000)); T = float(rng.uniform(0.05, 2)); r = 6.0; v = 30.0
    lo = BS.black_scholes(K*0.8, K, T, r, v, "call")["price"]
    hi = BS.black_scholes(K*1.2, K, T, r, v, "call")["price"]
    check(hi >= lo - 1e-9, "call_not_incr_in_spot", f"{lo}->{hi}")
    v1 = BS.black_scholes(K, K, T, r, 10, "call")["price"]
    v2 = BS.black_scholes(K, K, T, r, 60, "call")["price"]
    check(v2 >= v1 - 1e-9, "call_not_incr_in_vol", f"{v1}->{v2}")

# implied-vol round trip (well-conditioned range)
for _ in range(800):
    S = float(rng.uniform(50, 2000)); K = S * float(rng.uniform(0.8, 1.2))
    T = float(rng.uniform(0.1, 1.5)); r = 6.0; v_true = float(rng.uniform(8, 80))
    typ = random.choice(["call", "put"])
    res = BS.black_scholes(S, K, T, r, v_true, typ)
    price = res["price"]
    # Implied vol is only RECOVERABLE where the price actually responds to vol.
    # For a near-worthless option vega -> 0, so a 2.6-vol-point range maps to
    # prices of 0.0002 vs 0.0079 — the price carries almost no information about
    # sigma and the inverse problem is ill-posed. That is mathematics, not a
    # solver defect, so only assert the round-trip where vega is meaningful.
    if price < 0.01 or res["greeks"]["vega"] < 0.01:
        continue
    iv = BS.implied_volatility(price, S, K, T, r, typ)
    if "error" in iv: continue
    check(abs(iv["implied_vol_pct"] - v_true) < 0.5, "iv_roundtrip_off",
          f"true={v_true:.2f} got={iv['implied_vol_pct']} vega={res['greeks']['vega']}")

# BS edge cases
check("error" in BS.black_scholes(-1, 100, 1, 5, 20, "call"), "bs_neg_spot_ok")
check("error" in BS.black_scholes(100, 0, 1, 5, 20, "call"), "bs_zero_strike_ok")
check(BS.black_scholes(150, 100, 0, 5, 20, "call")["price"] == 50, "bs_T0_intrinsic")
check(BS.black_scholes(100, 100, 1, 5, 0, "call")["price"] == 0, "bs_zerovol_atm")
check(BS.black_scholes(100, 100, 1, 5, 20, "BANANA").get("error"), "bs_bad_type")
check("error" in BS.implied_volatility(0.001, 100, 100, 1, 5, "call") or True, "iv_tiny")  # shouldn't crash

# ---------------------------------------------------------------------------
section("Optimizers ERC / MaxDiv: synthetic covariance, weight & risk invariants")
import portfolio_optimizer as PO

def synth_returns(tickers, start, end):
    n = 400
    # random but PSD-ish correlated returns
    k = len(tickers)
    base = rng.normal(0, 1, (n, 1))
    data = {}
    for t in tickers:
        load = rng.uniform(-0.6, 1.0)
        data[t] = (load * base[:, 0] + rng.normal(0, 1, n)) * rng.uniform(0.008, 0.025) + rng.uniform(-2e-4, 6e-4)
    return pd.DataFrame(data)
PO._get_returns = synth_returns

for _ in range(120):
    k = int(rng.integers(2, 9)); tickers = [f"S{i}.NS" for i in range(k)]
    erc = PO.equal_risk_contribution(tickers)
    if "error" in erc: check(False, "erc_errored", erc.get("error")); continue
    w = erc["optimal_weights"]; rc = erc["risk_contribution_pct"]
    check(abs(sum(w.values()) - 1) < 1e-3, "erc_not_simplex", f"{sum(w.values())}")
    check(all(v >= -1e-6 for v in w.values()), "erc_negative", f"{w}")
    # the whole point: risk contributions ~equal
    vals = list(rc.values())
    check(max(vals) - min(vals) < 2.0, "erc_risk_not_equal", f"spread={max(vals)-min(vals):.3f} {rc}")
    check(abs(sum(vals) - 100) < 1.0, "erc_rc_sum", f"{sum(vals)}")

for _ in range(120):
    k = int(rng.integers(2, 9)); tickers = [f"M{i}.NS" for i in range(k)]
    md = PO.maximum_diversification(tickers)
    if "error" in md: check(False, "md_errored", md.get("error")); continue
    w = md["optimal_weights"]
    check(abs(sum(w.values()) - 1) < 1e-3, "md_not_simplex", f"{sum(w.values())}")
    check(all(v >= -1e-6 for v in w.values()), "md_negative", f"{w}")
    # diversification ratio must be >= 1 by definition (port vol <= weighted avg vol)
    check(md["diversification_ratio"] >= 1 - 1e-6, "md_ratio_lt_1", f"{md['diversification_ratio']}")

# risk decomposition invariants
for _ in range(120):
    k = int(rng.integers(2, 9)); tickers = [f"R{i}.NS" for i in range(k)]
    hold = {t: float(rng.uniform(1, 100)) for t in tickers}
    rd = PO.risk_decomposition(hold)
    if "error" in rd: check(False, "rd_errored", rd.get("error")); continue
    s = sum(c["risk_contribution_pct"] for c in rd["components"])
    check(abs(s - 100) < 0.5, "rd_sum_not_100", f"{s}")
    check(rd["portfolio_vol_pct"] > 0, "rd_vol_nonpos", f"{rd['portfolio_vol_pct']}")
    check(rd["diversification_ratio"] >= 1 - 1e-6, "rd_divratio_lt1", f"{rd['diversification_ratio']}")
    check(all(math.isfinite(c["risk_contribution_pct"]) for c in rd["components"]), "rd_nonfinite", "")

# optimizer edge cases
check("error" in PO.equal_risk_contribution(["ONLY.NS"]), "erc_single_ticker")
check("error" in PO.maximum_diversification(["ONLY.NS"]), "md_single_ticker")

# ---------------------------------------------------------------------------
section("Backtests low-vol + momentum: synthetic prices, structure invariants")
import momentum_backtest as MB

def make_multi(tickers, n=1600, seed=1):
    r = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-01", periods=n, freq="B")
    cols = {}
    for t in tickers:
        drift = r.uniform(-0.0003, 0.0009); vol = r.uniform(0.008, 0.03)
        path = 100 * np.cumprod(1 + r.normal(drift, vol, n))
        cols[(t, "Close")] = path
    return pd.DataFrame(cols, index=idx)

import yfinance as _yf
TICKS = [f"T{i}.NS" for i in range(30)]
_orig_dl = _yf.download
def fake_dl(tickers, *a, **k):
    return make_multi(list(tickers))
_yf.download = fake_dl

for frac in (0.1, 0.2, 0.3):
    for fn, name in ((MB.low_vol_backtest, "lowvol"), (MB.momentum_backtest, "momentum")):
        kwargs = {"bottom_fraction": frac} if name == "lowvol" else {"top_fraction": frac}
        r = fn(universe=TICKS, start="2019-01-01", **kwargs)
        if "error" in r: check(False, f"{name}_errored", r.get("error")); continue
        s = r["strategy_stats"]; b = r["benchmark_stats"]
        check(all(math.isfinite(s[k]) for k in ("cagr_pct","sharpe","max_drawdown_pct")), f"{name}_nonfinite", str(s))
        check(s["max_drawdown_pct"] <= 0, f"{name}_dd_positive", f"{s['max_drawdown_pct']}")
        check(0 <= s["hit_rate_pct"] <= 100, f"{name}_hitrate_oob", f"{s['hit_rate_pct']}")
        check(len(r["equity_curve"]) > 5, f"{name}_short_curve", f"{len(r['equity_curve'])}")
        check(isinstance(r["significant_5pct"], bool), f"{name}_sig_type", "")
        check("survivorship" in " ".join(r["caveats"]).lower(), f"{name}_no_caveat", "")
_yf.download = _orig_dl

# ---------------------------------------------------------------------------
section("Seasonality: synthetic index series, structure invariants")
import seasonality as SEA
def fake_dl2(ticker, *a, **k):
    r = np.random.default_rng(3)
    idx = pd.date_range("2005-01-01", periods=5000, freq="B")
    path = 1000 * np.cumprod(1 + r.normal(0.0004, 0.011, 5000))
    return pd.DataFrame({"Close": path}, index=idx)
_yf.download = fake_dl2

s = SEA.seasonality_analysis("^NSEI", years=20)
check("error" not in s, "seasonality_errored", s.get("error", ""))
if "error" not in s:
    check(len(s["monthly"]) == 12, "seasonality_not_12", f"{len(s['monthly'])}")
    for m in s["monthly"]:
        check(0 <= m["hit_rate_pct"] <= 100, "seas_hitrate_oob", f"{m}")
        check(math.isfinite(m["t_stat"]), "seas_tstat_nonfinite", f"{m}")
        check(isinstance(m["significant"], bool), "seas_sig_type", "")
    check(s["best_month"] in [m["month"] for m in s["monthly"]], "seas_best_invalid", "")
    check("multiple" in s["caveat"].lower() or "comparison" in s["caveat"].lower(), "seas_no_caveat", "")
_yf.download = _orig_dl

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print(f"TOTAL CHECKS: {N}")
print(f"FAILURES:     {len(FAILS)}")
if FAILS:
    from collections import Counter
    for c, n in Counter(f.split(']')[0][1:] for f in FAILS).most_common():
        print(f"  {n:5d}  {c}")
    print("\nSamples:")
    for f in FAILS[:25]: print("  -", f)
else:
    print("\nALL CHECKS PASSED ✓")
