"""
piotroski_invariant_test.py — what a missing-data policy may and may not change.

No policy is implemented here and V1.4 is untouched. This test establishes the
invariant that any future policy must satisfy before it can be called
behaviour-preserving:

    when every declared input is present, the F-score, the Quality score and
    the Alpha contribution must be bit-identical to today's.

The four candidate policies are modelled side by side so their consequences can
be compared on the same inputs. Modelled — not installed. Nothing in
alpha_model or metrics imports anything from this file.

The second half is the part that matters: it shows what each policy does when
inputs are ABSENT, which is where they differ and where the choice is a
model-policy decision rather than an engineering one.
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


PIO = ("returnOnAssets", "operatingCashflow", "currentRatio", "longTermDebt",
       "grossMargins", "revenueGrowth", "totalAssets", "totalStockholderEquity")

# Which inputs each leg needs. no_dilution needs none — it is hard-coded to 1.
LEG_NEEDS = {
    "roa_positive":             ("returnOnAssets",),
    "cfo_positive":             ("operatingCashflow",),
    "roa_above_5pct":           ("returnOnAssets",),
    "cfo_beats_roa":            ("operatingCashflow", "totalAssets"),
    "low_leverage":             ("longTermDebt", "totalStockholderEquity"),
    "current_ratio_above_1":    ("currentRatio",),
    "no_dilution":              (),
    "gross_margin_above_20pct": ("grossMargins",),
    "positive_revenue_growth":  ("revenueGrowth",),
}


def legs(info, der):
    """The frozen V1.4 leg tests, transcribed. Not modified."""
    roa = info.get("returnOnAssets") or der.get("roa") or 0
    cfo = info.get("operatingCashflow", 0) or 0
    ta = info.get("totalAssets") or None
    ltd = info.get("longTermDebt", 0) or 0
    eq = info.get("totalStockholderEquity") or None
    cr = info.get("currentRatio") or der.get("current_ratio") or 0
    gm = info.get("grossMargins", 0) or 0
    rg = info.get("revenueGrowth", 0) or 0
    lev = (ltd / eq) if eq else None
    return {
        "roa_positive": 1 if roa > 0 else 0,
        "cfo_positive": 1 if cfo > 0 else 0,
        "roa_above_5pct": 1 if roa > 0.05 else 0,
        "cfo_beats_roa": 1 if (ta and (cfo / ta) > roa) else 0,
        "low_leverage": 1 if (lev is not None and lev < 0.5) else 0,
        "current_ratio_above_1": 1 if cr > 1.0 else 0,
        "no_dilution": 1,
        "gross_margin_above_20pct": 1 if gm > 0.20 else 0,
        "positive_revenue_growth": 1 if rg > 0 else 0,
    }


def policy_A(info, der):
    """Current behaviour. Missing becomes 0, 0 fails the test, the point is lost."""
    return sum(legs(info, der).values()), 9, "scored"


def policy_B(info, der, k=4):
    """Refuse when fewer than k of the 8 inputs are present."""
    n = sum(1 for f in PIO if info.get(f) is not None)
    if n < k:
        return None, 9, "refused"
    return sum(legs(info, der).values()), 9, "scored"


def policy_C(info, der):
    """Score only the decidable legs; report the denominator honestly."""
    L = legs(info, der)
    dec = [n for n, needs in LEG_NEEDS.items()
           if all(info.get(f) is not None for f in needs)]
    return sum(L[n] for n in dec), len(dec), "scored"


def policy_D(info, der):
    """Per-leg refusal, rescaled to 9 so the number stays comparable."""
    got, denom, _ = policy_C(info, der)
    if denom == 0:
        return None, 9, "refused"
    return round(9.0 * got / denom, 3), 9, "scored"


def quality(f_score, denom, roe, fcf_yield):
    """The frozen composite. Untouched."""
    if f_score is None:
        return None
    parts, w = [(0.4, f_score / denom)], 0.4
    if roe is not None:
        parts.append((0.4, ((roe - 0.12) / 0.08) / 3)); w += 0.4
    if fcf_yield is not None:
        parts.append((0.2, ((fcf_yield - 0.035) / 0.04) / 3)); w += 0.2
    return math.tanh(sum(a * b for a, b in parts) / w)


COMPLETE = {
    "returnOnAssets": 0.061, "operatingCashflow": 8.2e10, "currentRatio": 1.6,
    "longTermDebt": 4.0e10, "grossMargins": 0.31, "revenueGrowth": 0.09,
    "totalAssets": 9.0e11, "totalStockholderEquity": 3.2e11,
}
DER = {"roa": 0.058, "current_ratio": 1.55}
ROE, FCFY = 0.154, 0.031

print("\n1. THE INVARIANT — complete payload, every policy must agree")
base_f, base_d, _ = policy_A(COMPLETE, DER)
base_q = quality(base_f, base_d, ROE, FCFY)
print(f"       V1.4 today: F={base_f}/9  quality={base_q:.6f}  "
      f"alpha={25*base_q:+.4f} pts")
for name, fn in (("B refuse-if-thin", lambda i, d: policy_B(i, d, k=4)),
                 ("C decidable-only", policy_C),
                 ("D per-leg rescaled", policy_D)):
    f, d, st = fn(COMPLETE, DER)
    q = quality(f, d, ROE, FCFY)
    ok(f == base_f and d == base_d and q == base_q,
       f"{name:<20} F={f}/{d} quality={q:.6f} — identical to V1.4")

print("\n   ...and the same on a second complete payload with different values")
C2 = dict(COMPLETE, returnOnAssets=0.02, grossMargins=0.12, revenueGrowth=-0.04)
b2f, b2d, _ = policy_A(C2, DER)
b2q = quality(b2f, b2d, ROE, FCFY)
for name, fn in (("B", lambda i, d: policy_B(i, d, k=4)), ("C", policy_C),
                 ("D", policy_D)):
    f, d, _ = fn(C2, DER)
    ok(quality(f, d, ROE, FCFY) == b2q, f"policy {name}: quality identical ({b2q:.6f})")

print("\n2. WHERE THE POLICIES DIVERGE — SBIN's real shape (5 of 8 absent)")
SBIN = {"returnOnAssets": 0.01132, "grossMargins": 0.0, "revenueGrowth": 0.103}
SDER = {"roa": 0.0104, "current_ratio": None}
S_ROE, S_FCFY = 0.1518, 0.0313
print(f"  {'policy':<26}{'F':>10}{'denom':>8}{'quality':>11}{'alpha':>9}  meaning")
print("  " + "-" * 82)
rows = [("A  missing -> 0 (today)", policy_A(SBIN, SDER)),
        ("B  refuse if <4 present", policy_B(SBIN, SDER, k=4)),
        ("C  decidable legs only", policy_C(SBIN, SDER)),
        ("D  per-leg rescaled", policy_D(SBIN, SDER))]
for label, (f, d, st) in rows:
    q = quality(f, d, S_ROE, S_FCFY)
    fs = "refused" if f is None else f"{f}"
    qs = "  —  " if q is None else f"{q:.4f}"
    a = "  —  " if q is None else f"{25*q:+.2f}"
    mean = {"A": "3 of 9, as if 6 legs were tested and failed",
            "B": "no answer — the inputs were not there",
            "C": "only the legs its inputs can decide; denom states coverage",
            "D": "3/4 rescaled onto the 9-point scale"}[label[0]]
    print(f"  {label:<26}{fs:>10}{d:>8}{qs:>11}{a:>9}  {mean}")

print("\n3. THE ASYMMETRY THAT MAKES THIS A POLICY DECISION")
a_f, a_d, _ = policy_A(SBIN, SDER)
c_f, c_d, _ = policy_C(SBIN, SDER)
ok(a_f == c_f, f"A and C award the same points ({a_f})")
ok(a_d != c_d, f"but over different denominators: {a_d} vs {c_d}")
qa, qc = quality(a_f, a_d, S_ROE, S_FCFY), quality(c_f, c_d, S_ROE, S_FCFY)
print(f"       A: {a_f}/{a_d} -> quality {qa:.4f} -> {25*qa:+.2f} alpha pts")
print(f"       C: {c_f}/{c_d} -> quality {qc:.4f} -> {25*qc:+.2f} alpha pts")
print(f"       difference: {25*(qc-qa):+.2f} alpha points on ONE stock")
ok(abs(qc - qa) > 0.01,
   "the choice of denominator materially moves alpha — a model decision, "
   "not an engineering one")

print("\n4. NO POLICY IS INSTALLED")
import metrics, alpha_model  # noqa: E402
msrc = open(os.path.join(os.path.dirname(__file__), "..", "modules",
                         "metrics.py"), encoding="utf-8", errors="replace").read()
ok("policy_" not in msrc, "metrics.py references no policy from this file")
ok(metrics.piotroski_score.__module__ == "metrics",
   "piotroski_score is still the production function")
ok(alpha_model.FACTOR_WEIGHTS == {"sentiment": 0.25, "momentum": 0.35,
                                  "quality": 0.25, "value": 0.15},
   "V1.4 factor weights unchanged")

print("\n" + "=" * 70)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
