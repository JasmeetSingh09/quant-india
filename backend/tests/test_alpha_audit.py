"""
alpha_audit.py — independent audit of the alpha model.

Does NOT just re-run the model and check it doesn't crash. For every stock it
recomputes momentum from raw prices with a SEPARATE implementation and compares,
then checks the composite algebra, the signal bands, and every declared range.
Finally it throws deliberately hostile inputs at it.

Run:  python alpha_audit.py [n_stocks]
"""
import sys, os, math, time, json, warnings, random
warnings.filterwarnings("ignore")
sys.path.insert(0, r"C:\Users\seeraj\OneDrive\Documents\Desktop\code\ai_stock\backend\modules")

import numpy as np, pandas as pd, yfinance as yf
import alpha_model as AM
from data_fetcher import NSE_SECTORS

FAILS, CHECKS = [], {"n": 0}

def check(cond, tag, detail=""):
    CHECKS["n"] += 1
    if not cond:
        FAILS.append((tag, detail))
    return cond


# --------------------------------------------------------------------------
# Independent momentum reimplementation (deliberately written from the docstring,
# not copied from the model, so a shared bug can't hide in both)
# --------------------------------------------------------------------------
def independent_momentum(ticker):
    from datetime import datetime, timedelta
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=430)).strftime("%Y-%m-%d")
    try:
        df = yf.download(ticker, start=start, end=end, progress=False,
                         auto_adjust=True, threads=False, timeout=20)
        s = df["Close"].squeeze().dropna()
    except Exception:
        return None
    if s is None or len(s) < 60:
        return None
    n = len(s)
    i0 = max(0, n - 1 - 252)
    i1 = n - 1 - 21
    if i1 <= i0:
        return None
    mom = float(s.iloc[i1]) / float(s.iloc[i0]) - 1.0
    window = s.iloc[i0:i1 + 1]
    rets = window.pct_change().dropna()
    vol = float(rets.std(ddof=1) * math.sqrt(252)) if len(rets) > 5 else 0.0
    ra = mom / vol if vol > 1e-6 else 0.0
    return {"mom": mom * 100, "vol": vol * 100, "ra": ra,
            "score": math.tanh(ra / 1.5), "n_bars": n}


def audit_stock(t):
    row = {"ticker": t}
    try:
        r = AM.compute_alpha_score(t)
    except Exception as e:
        FAILS.append(("crashed", f"{t}: {type(e).__name__}: {e}"))
        return {"ticker": t, "crashed": str(e)}

    if "error" in r:
        row["error"] = r["error"]
        return row

    a = r["alpha_score"]; f = r["factors"]; w = r["weights_used"]
    row.update(alpha=a, signal=r["signal"], conf=r["confidence"])

    # 1. ranges
    check(-100.01 <= a <= 100.01, "alpha_out_of_range", f"{t}={a}")
    check(0 <= r["confidence"] <= 1.0001, "conf_out_of_range", f"{t}={r['confidence']}")
    for name, fac in f.items():
        sc = fac.get("score"); cf = fac.get("confidence")
        check(sc is not None and -1.0001 <= sc <= 1.0001, "factor_out_of_range", f"{t}.{name}={sc}")
        check(cf is not None and 0 <= cf <= 1.0001, "factor_conf_range", f"{t}.{name}={cf}")
        check(sc is None or math.isfinite(sc), "factor_nonfinite", f"{t}.{name}={sc}")

    # 2. composite algebra: alpha == 100 * sum(w_i * score_i)
    recomposed = 100.0 * sum(w[k] * f[k]["score"] for k in w)
    check(abs(recomposed - a) < 0.02, "composite_mismatch",
          f"{t}: model={a} recomputed={recomposed:.4f}")

    # 3. contributions must sum to alpha
    csum = sum(r["contributions"].values())
    check(abs(csum - a) < 0.05, "contrib_sum_mismatch", f"{t}: contrib={csum:.3f} alpha={a}")

    # 4. weights sum to 1
    check(abs(sum(w.values()) - 1.0) < 1e-9, "weights_not_unit", f"{t}: {sum(w.values())}")

    # 5. signal bands match the score
    exp = ("STRONG BUY" if a > 40 else "BUY" if a > 15 else
           "STRONG SELL" if a < -40 else "SELL" if a < -15 else "NEUTRAL")
    check(r["signal"] == exp, "signal_band_mismatch", f"{t}: {a} -> {r['signal']} expected {exp}")

    # 6. momentum verified against an independent implementation
    im = independent_momentum(t)
    mf = f["momentum"]
    if im and mf.get("mom_12_1_pct") is not None:
        row["mom_model"] = mf["mom_12_1_pct"]; row["mom_indep"] = round(im["mom"], 2)
        check(abs(mf["mom_12_1_pct"] - im["mom"]) < 0.75, "momentum_return_mismatch",
              f"{t}: model={mf['mom_12_1_pct']:.2f}% indep={im['mom']:.2f}%")
        check(abs(mf["ann_vol_pct"] - im["vol"]) < 0.75, "momentum_vol_mismatch",
              f"{t}: model={mf['ann_vol_pct']:.2f}% indep={im['vol']:.2f}%")
        check(abs(mf["score"] - im["score"]) < 0.02, "momentum_score_mismatch",
              f"{t}: model={mf['score']:.4f} indep={im['score']:.4f}")
        # tanh must be monotone in risk_adj and correctly signed
        check((mf["score"] >= 0) == (im["ra"] >= 0) or abs(im["ra"]) < 1e-9,
              "momentum_sign_flip", f"{t}: ra={im['ra']:.3f} score={mf['score']}")
    elif im is None:
        row["mom_indep"] = None

    # 7. a zero-confidence factor must not move the score much
    for name, fac in f.items():
        if fac.get("confidence") == 0.0:
            check(abs(fac["score"]) < 1e-9, "zeroconf_nonzero_score",
                  f"{t}.{name}: conf=0 but score={fac['score']}")

    # 8. determinism — same inputs, same answer (caches are warm by now)
    r2 = AM.compute_alpha_score(t)
    check(abs(r2["alpha_score"] - a) < 1e-9, "nondeterministic",
          f"{t}: {a} then {r2['alpha_score']}")
    return row


def main():
    n_target = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    universe = sorted({t for v in NSE_SECTORS.values() for t in v})
    random.seed(11)
    sample = random.sample(universe, min(n_target, len(universe)))

    print(f"AUDIT: {len(sample)} real NSE stocks + hostile inputs", flush=True)
    rows = []
    t0 = time.time()
    for i, t in enumerate(sample, 1):
        rows.append(audit_stock(t))
        if i % 10 == 0:
            print(f"  {i}/{len(sample)}  ({time.time()-t0:.0f}s, {len(FAILS)} fails)", flush=True)

    # ---------------- hostile / edge inputs ----------------
    print("\nEDGE CASES", flush=True)
    edge = {
        "delisted":      "LTFH.NS",
        "bad_suffix":    "RELIANCE",
        "nonexistent":   "ZZZQQQ123.NS",
        "empty":         "",
        "spaces":        "   ",
        "sql_ish":       "'; DROP TABLE x;--",
        "unicode":       "रिलायंस.NS",
        "very_long":     "A" * 300 + ".NS",
        "index":         "^NSEI",
        "us_stock":      "AAPL",
        "lowercase":     "tcs.ns",
        "whitespace_pad": "  TCS.NS  ",
    }
    edge_rows = {}
    for label, t in edge.items():
        try:
            r = AM.compute_alpha_score(t)
            a = r.get("alpha_score")
            ok = ("error" in r) or (a is not None and math.isfinite(a) and -100.01 <= a <= 100.01)
            check(ok, "edge_bad_output", f"{label}({t!r}) -> {str(r)[:110]}")
            edge_rows[label] = "error" if "error" in r else f"alpha={a} sig={r.get('signal')}"
        except Exception as e:
            check(False, "edge_crashed", f"{label}({t!r}): {type(e).__name__}: {e}")
            edge_rows[label] = f"CRASH {type(e).__name__}"
        print(f"  {label:15s} {t[:28]!r:32s} -> {edge_rows[label]}", flush=True)

    # ---------------- report ----------------
    ok = [r for r in rows if "alpha" in r]
    print("\n" + "=" * 74)
    print(f"stocks audited     : {len(rows)}   scored: {len(ok)}   errored: {len(rows)-len(ok)}")
    print(f"assertions run     : {CHECKS['n']}")
    print(f"FAILURES           : {len(FAILS)}")
    if ok:
        al = [r["alpha"] for r in ok]
        print(f"alpha range        : {min(al):.1f} .. {max(al):.1f}  (mean {np.mean(al):.1f})")
        from collections import Counter
        print(f"signal spread      : {dict(Counter(r['signal'] for r in ok))}")
        nz = [r for r in ok if r.get("mom_indep") is not None]
        print(f"momentum verified  : {len(nz)}/{len(ok)} against independent recompute")
    if FAILS:
        print("\n--- FAILURES (first 25) ---")
        from collections import Counter
        for tag, cnt in Counter(t for t, _ in FAILS).most_common():
            print(f"  [{tag}] x{cnt}")
        for tag, d in FAILS[:25]:
            print(f"   {tag}: {d}")
    else:
        print("\nNo failures.")
    json.dump({"rows": rows, "fails": FAILS, "checks": CHECKS["n"]},
              open(os.path.join(os.path.dirname(__file__), "alpha_audit_result.json"), "w"),
              indent=1, default=str)


if __name__ == "__main__":
    main()
