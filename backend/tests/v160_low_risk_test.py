"""
v160_low_risk_test.py — low risk is shown, not scored (v1.6.0, owner approval 2026-10-05).

Factor test 1 found no demonstrated edge for low risk at any horizon on 2011-2026
point-in-time prices; momentum passed at all four. The six-factor model's 18% for
low risk moved to momentum (docs/PROPOSAL_V160_LOW_RISK_2026-10-05.md). Offline:
every factor is replaced with a fixed value.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp()
open(os.path.join(TMP, "quant_platform.db"), "wb").close()
os.environ["QUANT_DATA_DIR"] = TMP
os.environ.pop("DATABASE_URL", None)

import alpha_v2  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


print("\n1. The weights")
W = alpha_v2.WEIGHTS_V2
ok(abs(sum(W.values()) - 1.0) < 1e-9, "weights sum to 1")
ok("low_risk" not in W and "low_risk" in alpha_v2.REPORTED_NOT_SCORED, "low risk is reported, not scored")
ok(W["momentum"] == 0.36, "momentum carries the 18% low risk had (18% + 18% = 36%)")
ok(W == {"momentum": 0.36, "quality": 0.22, "growth": 0.15, "value": 0.17, "sentiment": 0.10},
   "no other weight moved")
ok(alpha_v2.MODEL_VERSION_V2 == "alpha-v2.2-five-factor", "the model version says so")

print("\n2. A stock's score ignores low risk, and the response still shows it")
FIXED = {"momentum": 0.5, "quality": 0.2, "value": -0.1, "sentiment": 0.3}


V1 = {"alpha_score": 10.0, "signal": "NEUTRAL",
      "factors": {n: {"score": sc, "confidence": 1.0} for n, sc in FIXED.items()}}
alpha_v2._growth_factor = lambda t: {"score": 0.4, "confidence": 1.0}
try:
    import liquidity
    liquidity.assess = lambda t: {}
except Exception:
    pass


def run(lr_score):
    alpha_v2._low_risk_factor = lambda t: {"score": lr_score, "confidence": 1.0, "annual_volatility_pct": 30.0,
                                           "max_drawdown_pct": -40.0, "reason": "Annualised volatility 30%"}
    return alpha_v2.compute_v2("TEST.NS", v1_result=V1)


a, b = run(-1.0), run(1.0)
ok("error" not in a, f"the score computes ({a.get('error') or a.get('alpha_score')})")
ok(a.get("alpha_score") == b.get("alpha_score"),
   f"the best and worst low-risk readings give the same score ({a.get('alpha_score')} vs {b.get('alpha_score')})")
expect = round((0.36 * 0.5 + 0.22 * 0.2 + 0.17 * -0.1 + 0.10 * 0.3 + 0.15 * 0.4) * 100, 2)
ok(abs((a.get("alpha_score") or 0) - expect) < 0.01, f"the score is the five weighted factors ({expect})")
ok((a.get("reported_not_scored") or {}).get("low_risk", {}).get("annual_volatility_pct") == 30.0,
   "low risk's volatility and drawdown are still reported beside the score")
ok("low_risk" not in (a.get("contributions") or {}), "low risk contributes no points")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
