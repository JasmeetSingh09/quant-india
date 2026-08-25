"""
factor_audit.py — are the factors pointing the right way, and are they
measuring different things?

Two questions the model's own arithmetic cannot answer.

SIGN. Every factor is built so that higher means more attractive. That is a
convention, and conventions get inverted in refactors. A cheap stock must score
HIGHER on value than an expensive one; a calm stock must score higher on
low_risk than a wild one. These are checked by finding real pairs of stocks
where the underlying quantity is unambiguous and asserting the ordering.

REDUNDANCY. Six factors with distinct names may still be three factors wearing
six hats. If momentum and low_risk correlate at 0.9 across the universe, the
model is double-counting one signal and the stated weights do not mean what
they appear to mean. Correlations are computed across whatever the scan has
scored, which is the same population the app ranks.

Nothing here changes a weight or a threshold. The output is a report.
"""

import io
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import numpy as np

checks = 0
failures = []
notes = []
FACTORS = ("momentum", "quality", "growth", "value", "sentiment", "low_risk")


def ok(cond, label, evidence=""):
    global checks
    checks += 1
    if not cond:
        failures.append(label + (f" — {evidence}" if evidence else ""))


def note(m):
    notes.append(m)


# ===========================================================================
print("=== 1. FACTOR SIGN TEST ===")
print("Higher must mean more attractive. Checked on real pairs where the")
print("underlying quantity is unambiguous.\n")

from alpha_v2 import compute_v2, WEIGHTS_V2

# Pairs chosen so the DIRECTION is not in dispute, whatever the level.
SIGN_PAIRS = [
    # (factor, cheaper/better ticker, richer/worse ticker, why)
    ("value", "COALINDIA.NS", "DMART.NS",
     "Coal India trades on a single-digit multiple; DMart on a very high one"),
    ("low_risk", "NESTLEIND.NS", "TATASTEEL.NS",
     "a defensive staple against a cyclical steel producer"),
]

scores = {}


def get(t):
    if t in scores:
        return scores[t]
    try:
        r = compute_v2(t)
        scores[t] = None if "error" in r else r
    except Exception:
        scores[t] = None
    return scores[t]


for factor, better, worse, why in SIGN_PAIRS:
    a, b = get(better), get(worse)
    if not a or not b:
        note(f"{factor}: UNVERIFIED — could not score {better} or {worse}")
        continue
    sa = ((a.get("factors") or {}).get(factor) or {}).get("score")
    sb = ((b.get("factors") or {}).get(factor) or {}).get("score")
    if sa is None or sb is None:
        note(f"{factor}: UNVERIFIED — factor missing on one side")
        continue
    print(f"  {factor:<10} {better.replace('.NS',''):<12} {sa:+.4f}   "
          f"{worse.replace('.NS',''):<12} {sb:+.4f}")
    print(f"             {why}")
    ok(sa > sb, f"{factor}: the more attractive stock scores higher",
       f"{better}={sa:.4f} vs {worse}={sb:.4f}")

# Direction of the aggregate: a stock scoring well on most factors must not
# come out with a SELL label.
for t in ("COALINDIA.NS", "NESTLEIND.NS", "DMART.NS", "TATASTEEL.NS"):
    r = get(t)
    if not r:
        continue
    sc, sig = r.get("alpha_score"), r.get("signal")
    if sc is None or sig not in ("BUY", "SELL"):
        continue
    ok((sc > 0) == (sig == "BUY"),
       f"{t}: label agrees with score sign", f"{sc} / {sig}")

# The contribution of a factor must carry the SAME sign as its score, since
# every weight is positive. A negative weight anywhere would silently invert
# a factor without changing its name.
for name, w in WEIGHTS_V2.items():
    ok(w > 0, f"weight for {name} is positive", str(w))

for t, r in scores.items():
    if not r:
        continue
    fs = r.get("factors") or {}
    cs = r.get("contributions") or {}
    for name in FACTORS:
        s = (fs.get(name) or {}).get("score")
        c = cs.get(name)
        if s is None or c is None:
            continue
        # Contributions are rounded to 2dp, so a score small enough that
        # score x weight x 100 lands under half a hundredth legitimately
        # reports 0.00 and has no sign to preserve. Skipping those is not
        # weakening the test: it is the difference between a sign error and
        # a rounding artefact, and asserting on the latter would make the
        # check fire on correct code.
        if abs(s * WEIGHTS_V2.get(name, 0) * 100) < 0.005:
            continue
        ok((s > 0) == (c > 0),
           f"{t}: {name} contribution keeps the sign of its score",
           f"score={s:.6f} weight={WEIGHTS_V2.get(name)} contribution={c}")


# ===========================================================================
print("\n=== 2. FACTOR REDUNDANCY ===")
print("Correlations across the scored universe. Six names may be fewer signals.\n")

# Pull the whole scan rather than a handful of stocks: correlation on five
# points is noise, and the scan has already scored the universe today.
rowsets = defaultdict(list)
universe_n = 0
try:
    from db import get_conn
    conn = get_conn()
    try:
        # v1 stores four factors per ticker per cycle; v2's six live in
        # factor_history. Prefer the wider one when it has enough rows.
        fh = conn.execute(
            "SELECT momentum, quality, growth, value, sentiment, low_risk "
            "FROM factor_history WHERE model = 'v2'").fetchall()
    except Exception:
        fh = []
    if len(fh) >= 50:
        source = "factor_history (v2, six factors)"
        for r in fh:
            for i, name in enumerate(FACTORS):
                rowsets[name].append(r[i])
        universe_n = len(fh)
    else:
        source = "alpha_scan2 (v1, four factors)"
        sc = conn.execute(
            "SELECT momentum, quality, value, sentiment FROM alpha_scan2 "
            "WHERE alpha_score IS NOT NULL AND error IS NULL").fetchall()
        for r in sc:
            for i, name in enumerate(("momentum", "quality", "value", "sentiment")):
                rowsets[name].append(r[i])
        universe_n = len(sc)
    conn.close()
except Exception as e:
    source = f"UNAVAILABLE ({type(e).__name__})"

print(f"  source: {source}   rows: {universe_n}")

if universe_n < 50:
    note(f"factor correlations: UNVERIFIED — only {universe_n} scored rows "
         f"available locally; run the universe scan for a real matrix")
else:
    names = [n for n in FACTORS if rowsets.get(n)]
    # Pairwise on complete cases only — dropping the whole row because one
    # factor is missing would silently shrink the sample for every pair.
    print(f"\n  {'':<12}" + "".join(f"{n[:8]:>10}" for n in names))
    high = []
    for a in names:
        line = f"  {a[:10]:<12}"
        for b in names:
            xa, xb = [], []
            for va, vb in zip(rowsets[a], rowsets[b]):
                if va is not None and vb is not None:
                    xa.append(float(va))
                    xb.append(float(vb))
            if len(xa) < 30:
                line += f"{'-':>10}"
                continue
            arr_a, arr_b = np.array(xa), np.array(xb)
            if arr_a.std() == 0 or arr_b.std() == 0:
                line += f"{'-':>10}"
                continue
            c = float(np.corrcoef(arr_a, arr_b)[0, 1])
            line += f"{c:>10.3f}"
            ok(-1.0001 <= c <= 1.0001, f"corr({a},{b}) in [-1,1]", f"{c}")
            if a < b and abs(c) >= 0.7:
                high.append((a, b, c, len(xa)))
        print(line)

    print()
    if high:
        for a, b, c, n in high:
            print(f"  REDUNDANCY: {a} and {b} correlate {c:+.3f} on {n} stocks.")
            print(f"              Their combined weight is "
                  f"{(WEIGHTS_V2.get(a,0)+WEIGHTS_V2.get(b,0))*100:.0f}%, which is "
                  f"effectively one signal carrying that much.")
        ok(False, "no factor pair correlates above 0.7",
           "; ".join(f"{a}~{b}={c:.2f}" for a, b, c, _ in high))
    else:
        print("  No pair correlates at or above 0.7 — the factors are")
        print("  measuring materially different things.")
        ok(True, "no factor pair correlates above 0.7")


# ===========================================================================
print("\n=== 3. FACTOR DOCUMENTATION ===")
print("Every factor must state its own formula, lookback and treatment.\n")

import inspect
import alpha_v2 as av
src = inspect.getsource(av)

for name in FACTORS:
    has_weight = name in WEIGHTS_V2
    ok(has_weight, f"{name} has a stated weight")
    # A factor whose weight is documented but whose method is not is a number
    # without a definition.
    documented = name in src
    ok(documented, f"{name} appears in the model source")

try:
    from alpha_v2 import WEIGHT_NOTES
    for name in FACTORS:
        ok(bool(WEIGHT_NOTES.get(name)),
           f"{name} has a stated reason for its weight",
           str(WEIGHT_NOTES.get(name))[:40])
except Exception:
    note("WEIGHT_NOTES: UNVERIFIED — could not import")

ok(abs(sum(WEIGHTS_V2.values()) - 1.0) < 1e-9,
   "weights sum to exactly 1", str(sum(WEIGHTS_V2.values())))


# ===========================================================================
print("\n" + "=" * 70)
print(f"FACTOR AUDIT CHECKS: {checks}")
print(f"FAILURES:            {len(failures)}")
for f in failures:
    print(f"   FAIL: {f}")
if notes:
    print(f"\nUNVERIFIED ({len(notes)}) — not assumed correct:")
    for n in notes:
        print(f"   - {n}")
print("=" * 70)
sys.exit(1 if failures else 0)
