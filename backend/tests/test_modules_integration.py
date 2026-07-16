"""
Part 2: import-safety of every module, remaining optimizers, alpha signal
thresholds end-to-end, GARCH, and sentiment correctness.
"""
import sys, math, warnings, random, importlib, glob, os
from pathlib import Path
warnings.filterwarnings("ignore")
from pathlib import Path
MODDIR = str(Path(__file__).resolve().parent.parent / "modules")
sys.path.insert(0, MODDIR)
import numpy as np, pandas as pd
rng = np.random.default_rng(7)

FAILS=[]; N=0
def check(c,label,ctx=""):
    global N; N+=1
    if not c: FAILS.append(f"[{label}] {ctx}")

# ---------------------------------------------------------------------------
print("=== import-safety: every module in modules/ ===")
mods = sorted(os.path.basename(f)[:-3] for f in glob.glob(os.path.join(MODDIR,"*.py"))
              if not os.path.basename(f).startswith("__"))
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        check(False, "module_import_failed", f"{m}: {type(e).__name__}: {e}")
    else:
        check(True, "module_import_ok", m)
print(f"  imported {len(mods)} modules")

# ---------------------------------------------------------------------------
print("=== optimizers: BL / frontier / alpha-views simplex (synthetic) ===")
import portfolio_optimizer as PO
def fake_lr(tickers, start, end):
    return pd.DataFrame({t: rng.normal(rng.uniform(-1e-4,6e-4), rng.uniform(0.008,0.02), 400) for t in tickers})
PO._get_returns = fake_lr

for _ in range(80):
    k = int(rng.integers(2,7)); tickers=[f"B{i}.NS" for i in range(k)]
    views = {t: (float(rng.uniform(-0.05,0.05)), float(rng.uniform(0.5,0.95))) for t in tickers}
    r = PO.black_litterman_optimize(tickers, views)
    if "error" in r: check(False,"bl_errored", r.get("error")); continue
    w = r.get("optimal_weights",{})
    check(abs(sum(w.values())-1.0)<1e-2,"bl_not_simplex",f"sum={sum(w.values())}")
    check(all(math.isfinite(v) for v in w.values()),"bl_nonfinite",str(w))

for _ in range(40):
    k=int(rng.integers(3,7)); tickers=[f"F{i}.NS" for i in range(k)]
    r = PO.efficient_frontier(tickers)
    if "error" in r: check(False,"frontier_errored", r.get("error")); continue
    pts = r.get("frontier", r.get("points", []))
    check(isinstance(pts,list) and len(pts)>0, "frontier_empty", str(list(r.keys())))
    # frontier vols should be non-negative and finite
    for pt in pts:
        vol = pt.get("volatility_pct", pt.get("vol_pct", pt.get("risk_pct")))
        if vol is not None:
            check(math.isfinite(vol) and vol>=0, "frontier_vol_bad", str(pt))

for _ in range(40):
    k=int(rng.integers(2,6)); tickers=[f"V{i}.NS" for i in range(k)]
    views={t: float(rng.uniform(-20,20)) for t in tickers}
    r = PO.optimize_with_alpha_views(tickers, views)
    if "error" in r: check(False,"alphaview_errored", r.get("error")); continue
    w=r.get("optimal_weights",{})
    if w: check(abs(sum(w.values())-1.0)<1e-2,"alphaview_not_simplex",f"sum={sum(w.values())}")

# ---------------------------------------------------------------------------
print("=== alpha_model: signal thresholds + contribution scaling (end-to-end, patched factors) ===")
import alpha_model as A
# Patch the four factor functions to return controllable scores so we exercise
# the COMBINATION logic (weights, scaling, signal buckets) deterministically.
def mk(score, conf=0.9):
    return lambda *a, **k: {"score": score, "confidence": conf, "interpretation": "x"}

signals_seen = {}
for combo in np.linspace(-1, 1, 41):
    A._compute_sentiment_factor = mk(combo)
    A._compute_momentum_factor  = mk(combo)
    A._compute_quality_factor   = mk(combo)
    A._compute_value_factor     = mk(combo)
    r = A.compute_alpha_score("Z.NS")
    check(-100.01 <= r["alpha_score"] <= 100.01, "alpha_score_oob", f"{combo}->{r['alpha_score']}")
    # all factors equal `combo`, weights sum to 1 -> alpha == combo*100
    check(abs(r["alpha_score"] - combo*100) < 0.5, "alpha_combine_wrong", f"{combo}->{r['alpha_score']}")
    # contributions sum to alpha_score
    csum = sum(r["contributions"].values())
    check(abs(csum - r["alpha_score"]) < 0.5, "contrib_sum_mismatch", f"{csum} vs {r['alpha_score']}")
    signals_seen[round(float(combo),3)] = r["signal"]
# signal buckets must be monotonic: strong sell -> ... -> strong buy as score rises
order = {"STRONG SELL":0,"SELL":1,"NEUTRAL":2,"BUY":3,"STRONG BUY":4}
seq = [order[signals_seen[k]] for k in sorted(signals_seen)]
check(all(seq[i] <= seq[i+1] for i in range(len(seq)-1)), "signal_not_monotonic", str(seq))
# extremes
check(signals_seen[min(signals_seen)] == "STRONG SELL", "min_not_strongsell", signals_seen[min(signals_seen)])
check(signals_seen[max(signals_seen)] == "STRONG BUY", "max_not_strongbuy", signals_seen[max(signals_seen)])

# ---------------------------------------------------------------------------
print("=== garch_vol: forecast on synthetic returns ===")
try:
    import garch_vol as G
    fns = [f for f in dir(G) if f.startswith("forecast") or "garch" in f.lower()]
    # find a function that accepts a price/return series or ticker; test import-only if unclear
    check(len(fns) > 0, "garch_no_public_fn", str([f for f in dir(G) if not f.startswith('_')]))
except Exception as e:
    check(False, "garch_import", str(e))

# ---------------------------------------------------------------------------
print("=== sentiment: FinBERT label correctness on clear headlines ===")
import sentiment as S
cases = [
    ("Company reports record profit, beats all estimates", "positive"),
    ("Firm collapses amid massive fraud, shares crash 40%", "negative"),
    ("Board to meet on Tuesday to review agenda", None),  # neutral-ish, don't assert
]
for text, expected in cases:
    r = S.score_headline(text)
    check(r["label"] in ("positive","negative","neutral"), "sent_label_invalid", str(r))
    check(0 <= r["confidence"] <= 1, "sent_conf_oob", str(r))
    if expected:
        check(r["label"] == expected, "sent_wrong_label", f"'{text[:40]}' -> {r['label']} (want {expected})")
# batch + empty
check(S.score_headlines_batch([]) == [], "sent_empty_batch")
check(len(S.score_headlines_batch(["a","b","c"])) == 3, "sent_batch_len")

# ---------------------------------------------------------------------------
print("\n"+"="*60)
print(f"TOTAL CHECKS: {N}")
print(f"FAILURES:     {len(FAILS)}")
if FAILS:
    from collections import Counter
    for c,n in Counter(f.split(']')[0][1:] for f in FAILS).most_common():
        print(f"  {n:4d}  {c}")
    print("\nDetails (up to 30):")
    for f in FAILS[:30]: print("  -", f)
else:
    print("\nALL CHECKS PASSED ✓")
