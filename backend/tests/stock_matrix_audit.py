"""
stock_matrix_audit.py — real NSE stocks chosen for the situations that break things.

A model that works on RELIANCE and TCS has been tested on the easy half of the
market. This runs the same pipeline over stocks picked for the specific
conditions that produce nonsense: negative earnings, negative book value,
enormous multiples, no news, thin volume, recent listings.

The pass condition is never "produces a number". It is "produces a number that
survives its own invariants, or refuses and says why". A stock that cannot be
scored is a pass when the refusal is explicit.
"""

import io
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

checks = 0
failures = []
rows = []


def ok(cond, label, evidence=""):
    global checks
    checks += 1
    if not cond:
        failures.append(label + (f" — {evidence}" if evidence else ""))


# Situation -> ticker. Chosen for the condition, not for the answer.
MATRIX = [
    ("large profitable",      "RELIANCE.NS"),
    ("expensive multiple",    "DMART.NS"),
    ("cheap / low multiple",  "COALINDIA.NS"),
    ("loss-making",           "RPOWER.NS"),
    ("recovering distress",   "YESBANK.NS"),
    ("high debt",             "IDEA.NS"),
    ("low debt / cash rich",  "TCS.NS"),
    ("high growth",           "TRENT.NS"),
    ("weak momentum",         "HDFCBANK.NS"),
    ("defensive / low vol",   "NESTLEIND.NS"),
    ("cyclical / high vol",   "TATASTEEL.NS"),
    ("thin volume",           "MRF.NS"),
    ("PSU",                   "BEL.NS"),
]

from alpha_v2 import compute_v2, WEIGHTS_V2
from scenario_valuation import scenarios as sv

print(f"{'situation':<22}{'ticker':<14}{'alpha':>8}{'cov':>7}  {'scenario':<12} invariants")
print("-" * 88)

for situation, ticker in MATRIX:
    row = {"situation": situation, "ticker": ticker}

    # --- alpha ---
    try:
        a = compute_v2(ticker)
    except Exception as e:
        ok(False, f"{ticker} ({situation}): compute_v2 raised", type(e).__name__)
        rows.append({**row, "alpha": "RAISED"})
        continue

    if "error" in a:
        # A refusal is a pass, as long as it is explicit.
        ok(bool(a["error"]), f"{ticker}: refusal states a reason")
        row["alpha"] = "refused"
        row["alpha_ok"] = True
    else:
        score = a.get("alpha_score")
        contribs = a.get("contributions") or {}
        cov = a.get("factor_coverage")
        row["alpha"] = score
        row["cov"] = cov

        ok(score is None or math.isfinite(score),
           f"{ticker} ({situation}): alpha score is finite", str(score))
        if score is not None and contribs:
            total = sum(contribs.values())
            ok(abs(total - score) <= 0.05,
               f"{ticker} ({situation}): contributions reconcile with score",
               f"{total:.3f} vs {score:.3f}")
        if cov is not None:
            ok(0.0 <= cov <= 1.0, f"{ticker}: coverage in [0,1]", str(cov))
        for name, f in (a.get("factors") or {}).items():
            fs = (f or {}).get("score")
            if fs is None:
                continue
            ok(math.isfinite(fs) and -1.0001 <= fs <= 1.0001,
               f"{ticker}: {name} score is a finite number in [-1,1]", str(fs))
        sig = a.get("signal")
        if sig in ("BUY", "SELL") and score is not None:
            ok((score > 0) == (sig == "BUY"),
               f"{ticker}: signal matches score sign", f"{score} / {sig}")
        row["alpha_ok"] = True

    # --- scenario valuation ---
    try:
        s = sv(ticker, years=3)
    except Exception as e:
        ok(False, f"{ticker} ({situation}): scenarios raised", type(e).__name__)
        rows.append({**row, "scenario": "RAISED"})
        continue

    if not s.get("available"):
        ok(bool(s.get("reason")), f"{ticker}: scenario refusal states a reason")
        ok("scenarios" not in s, f"{ticker}: refused scenario emits no numbers")
        row["scenario"] = "refused"
    else:
        cases = s["scenarios"]
        row["scenario"] = "ok"
        by = {c["scenario"]: c for c in cases}
        ok(by["Bull"]["implied_value"] >= by["Base"]["implied_value"]
           >= by["Bear"]["implied_value"],
           f"{ticker} ({situation}): bull >= base >= bear",
           f"{by['Bull']['implied_value']}/{by['Base']['implied_value']}/{by['Bear']['implied_value']}")
        for c in cases:
            ok(math.isfinite(c["implied_value"]) and c["implied_value"] > 0,
               f"{ticker}: {c['scenario']} value is a positive finite number",
               str(c["implied_value"]))
            ok(abs(c["eps_end"] * c["exit_multiple"] - c["implied_value"]) < 0.05,
               f"{ticker}: {c['scenario']} displayed numbers multiply out",
               f"{c['eps_end']} x {c['exit_multiple']}")
        # A positive P/E must imply positive EPS.
        ok(s["eps_now"] > 0, f"{ticker}: EPS positive when P/E is positive",
           str(s["eps_now"]))

    rows.append(row)
    a_s = row.get("alpha")
    a_txt = f"{a_s:.2f}" if isinstance(a_s, (int, float)) else str(a_s)
    c_txt = f"{row.get('cov'):.2f}" if isinstance(row.get("cov"), float) else "-"
    print(f"{situation:<22}{ticker:<14}{a_txt:>8}{c_txt:>7}  {row.get('scenario','-'):<12}ok")


# Across the whole matrix, at least one stock must exercise each path, or the
# matrix is not testing what it claims to.
refused_scen = [r for r in rows if r.get("scenario") == "refused"]
scored_scen = [r for r in rows if r.get("scenario") == "ok"]
ok(len(scored_scen) >= 5, "the matrix scored several stocks", f"{len(scored_scen)}")
ok(len(refused_scen) >= 1,
   "the matrix included at least one stock the valuation must refuse",
   f"{len(refused_scen)} refused")

print("\n" + "=" * 66)
print(f"MATRIX CHECKS: {checks}")
print(f"FAILURES:      {len(failures)}")
for f in failures:
    print(f"   FAIL: {f}")
print(f"\nscenario: {len(scored_scen)} valued, {len(refused_scen)} refused")
print("=" * 66)
sys.exit(1 if failures else 0)
