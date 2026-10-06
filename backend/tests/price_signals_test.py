"""
price_signals_test.py — factor test 4's machinery on synthetic prices (no real data).

Required by docs/PREREG_FACTOR_TEST4_PRICE_SIGNALS_2026-10-06.md before any run:
  - a planted reversal effect is recovered;
  - an effect that is pure momentum shows in the standalone sort but not the momentum-neutral one;
  - pure noise gives no pass;
  - the 100-stock and 200-close floors behave as written;
  - no score reads a column to the right of the formation column.
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

import numpy as np  # noqa: E402
import price_signals as PS  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


DPM = 21                                    # trading days per synthetic month


def make(n=300, months=72, seed=0, kind="noise"):
    """Daily closes built from monthly returns spread evenly over 21 days per calendar month."""
    rng = np.random.default_rng(seed)
    R = np.zeros((n, months))
    for m in range(months):
        noise = rng.normal(0, 0.06, n)
        if kind == "reversal" and m > 0:
            R[:, m] = -0.3 * R[:, m - 1] + noise
        elif kind == "momentum" and m > 12:
            past = np.prod(1 + R[:, m - 12:m - 1], axis=1) - 1     # months m-12 .. m-2: the 12-1 window
            R[:, m] = 0.15 * past + noise
        else:
            R[:, m] = noise
    days, cols = [], []
    for m in range(months):
        y, mo = 2010 + m // 12, m % 12 + 1
        days += [f"{y}-{mo:02d}-{d:02d}" for d in range(1, DPM + 1)]
    daily = np.repeat((1 + R) ** (1 / DPM), DPM, axis=1)
    C = (100 * np.cumprod(daily, axis=1)).astype(np.float32)
    V = np.full(C.shape, 1e9, dtype=np.float32)
    return [f"K{i}" for i in range(n)], days, C, V


def neutral_t(res, s, h="1m"):
    return res["signals"][s]["horizons"][h]["momentum_neutral_spread"].get("t_stat") or 0.0


print("\n1. A planted reversal is found")
res = PS.run_on_matrix(*make(kind="reversal", seed=1))
ok(res["verdicts"]["reversal"]["verdict"] == "adds beyond momentum",
   f"reversal: {res['verdicts']['reversal']} (t {neutral_t(res, 'reversal'):.1f})")

print("\n2. Pure momentum: visible alone, gone once momentum is held fixed")
res = PS.run_on_matrix(*make(kind="momentum", seed=2))
alone = res["signals"]["high52"]["horizons"]["1m"]["standalone_spread_described"].get("t_stat") or 0.0
neut = neutral_t(res, "high52")
ok(alone > 3, f"52-week high looks predictive on its own (t {alone:.1f}) because it carries momentum")
ok(res["verdicts"]["high52"]["verdict"] != "adds beyond momentum" and neut < alone,
   f"held momentum-neutral it does not pass (t {neut:.1f} vs {alone:.1f} alone; verdict {res['verdicts']['high52']['verdict']})")
# Five momentum groups control momentum only coarsely: some leaks through (t about 1-2.5 over
# 15 synthetic years with a momentum effect as strong as the real one), below the pass line
# (t about 2.9 at p 0.00625). The run reports this limit; see price_signals.KNOWN_LIMIT.
ok((res["signals"]["high52"]["rank_correlation_with_momentum"]["mean"] or 0) > 0.3,
   f"and its overlap with momentum is reported ({res['signals']['high52']['rank_correlation_with_momentum']})")

print("\n3. Noise gives no pass")
res = PS.run_on_matrix(*make(kind="noise", seed=3))
ok(all(v["verdict"] == "no demonstrated added edge" for v in res["verdicts"].values()),
   f"{ {k: v['verdict'] for k, v in res['verdicts'].items()} }")
ok(res["multiple_testing"]["primary_usable"] == 8 and abs(res["multiple_testing"]["level"] - 0.00625) < 1e-12,
   "all 8 primary tests usable; level 0.05/8")

print("\n4. Floors")
res = PS.run_on_matrix(*make(n=90, kind="reversal", seed=4))
ok(res["multiple_testing"]["primary_usable"] == 0, "90 eligible stocks a month: below 100, no month is used")
keys, days, C, V = make(n=300, seed=5)
col = 30 * DPM - 1
C2 = C.copy()
C2[0, col - 251:col - 251 + 60] = np.nan                     # 192 valid closes left in the window
ok(np.isnan(PS.high52_scores(C2, col)[0]) and np.isfinite(PS.high52_scores(C, col)[0]),
   "fewer than 200 valid closes in 252 days: no 52-week-high score")
C3 = C.copy(); C3[1, col - 21] = np.nan
ok(np.isnan(PS.reversal_scores(C3, col)[1]), "reversal needs both closes")

print("\n5. No look-ahead")
C4 = C.copy(); C4[:, col + 1:] = C4[:, col + 1:] * 3.7
ok(np.allclose(PS.reversal_scores(C, col), PS.reversal_scores(C4, col), equal_nan=True)
   and np.allclose(PS.high52_scores(C, col), PS.high52_scores(C4, col), equal_nan=True),
   "changing every later price changes no score at the formation date")

print("\n6. Momentum-neutral groups hold the same momentum mix")
rng = np.random.default_rng(6)
mom, sig = rng.normal(size=500), rng.normal(size=500)
ng, mg = PS.neutral_groups(mom, sig), PS._groups(mom)
ok(all(np.bincount(mg[ng == k], minlength=5).min() >= 15 for k in range(5)),
   "every signal group draws from every momentum group")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print("  FAILED:", x)
sys.exit(1 if FAIL else 0)
