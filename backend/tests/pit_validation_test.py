"""
pit_validation_test.py — can the validator be fooled, and does it peek?

Three questions, each with an answer known in advance:

  1. On pure noise, does it stay quiet? A validator that finds edges in random
     walks is worse than no validator, because it launders noise into evidence.
  2. On a planted effect, does it find it? A validator that never fires is
     quiet for the wrong reason.
  3. Does any factor score change when data AFTER the formation date changes?
     If it does, the whole exercise is look-ahead and every number is void.

Question 3 is the one that cannot be argued with. The factor is computed at a
column, then every price to the right of that column is overwritten with
garbage, and the factor is computed again. The two must be bit-identical.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import pit_validation as pv  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


N_SEC, N_DAY = 300, 700
rng = np.random.default_rng(20260901)


def random_walk(n_sec=N_SEC, n_day=N_DAY, drift=0.0003, vol=0.02):
    r = rng.normal(drift, vol, size=(n_sec, n_day))
    return (100.0 * np.cumprod(1 + r, axis=1)).astype(np.float32)


print("\n3. Look-ahead: a factor must not move when the future changes")
C = random_walk()
col = 600
mom_before = pv._momentum_scores(C, col)
lr_before = pv._low_risk_scores(C, col)

C_tampered = C.copy()
# Replace everything after the formation column with implausible values.
C_tampered[:, col + 1:] = rng.uniform(1, 10000, size=(N_SEC, N_DAY - col - 1))
mom_after = pv._momentum_scores(C_tampered, col)
lr_after = pv._low_risk_scores(C_tampered, col)

ok(np.array_equal(np.nan_to_num(mom_before, nan=-999),
                  np.nan_to_num(mom_after, nan=-999)),
   "momentum is identical after the entire future is overwritten")
ok(np.array_equal(np.nan_to_num(lr_before, nan=-999),
                  np.nan_to_num(lr_after, nan=-999)),
   "low_risk is identical after the entire future is overwritten")

# And the mirror: changing the PAST must move the score, or the test above
# passes for the trivial reason that the function ignores its input.
C_past = C.copy()
C_past[:, col - 200:col - 100] *= 1.5
mom_past = pv._momentum_scores(C_past, col)
ok(not np.array_equal(np.nan_to_num(mom_before, nan=-999),
                      np.nan_to_num(mom_past, nan=-999)),
   "momentum DOES move when the past changes (so the test above means something)")

print("\n1. Pure noise: the momentum spread must not look like a finding")
# Independent random walks. There is no cross-sectional signal by construction,
# so a top-minus-bottom spread should be indistinguishable from zero.
C_noise = random_walk()
spreads = []
for c in range(300, 680, 21):
    m = pv._momentum_scores(C_noise, c)
    if m is None or c + 21 >= N_DAY:
        continue
    fwd = C_noise[:, c + 21] / C_noise[:, c] - 1.0
    good = np.isfinite(m) & np.isfinite(fwd)
    if good.sum() < 50:
        continue
    ms, fs = m[good], fwd[good]
    order = np.argsort(ms)
    k = len(order) // 5
    spreads.append(float(np.mean(fs[order[-k:]]) - np.mean(fs[order[:k]])))

res = pv._mean_test(spreads)
print(f"    noise spread: mean {res['mean_pct']}%  t={res['t_stat']}  "
      f"p={res['p_value']}  n={res['n']}")
ok(res["p_value"] is not None and res["p_value"] > 0.05,
   f"no significant momentum spread in random walks (p={res['p_value']})")

print("\n2. Planted effect: a real signal must be detected")
# Build prices where the next month's return is genuinely tied to the trailing
# 12-1 return. If the validator cannot see THIS, it cannot see anything.
r = rng.normal(0.0003, 0.02, size=(N_SEC, N_DAY))
C_signal = np.empty((N_SEC, N_DAY), dtype=np.float32)
C_signal[:, :300] = (100.0 * np.cumprod(1 + r[:, :300], axis=1))
for c in range(300, N_DAY):
    trail = C_signal[:, c - 1] / C_signal[:, c - 252] - 1.0
    boost = 0.004 * np.tanh(trail / 0.3)      # winners drift, by construction
    step = r[:, c] + boost
    C_signal[:, c] = C_signal[:, c - 1] * (1 + step)

spreads = []
for c in range(560, 680, 21):
    m = pv._momentum_scores(C_signal, c)
    if m is None or c + 21 >= N_DAY:
        continue
    fwd = C_signal[:, c + 21] / C_signal[:, c] - 1.0
    good = np.isfinite(m) & np.isfinite(fwd)
    if good.sum() < 50:
        continue
    ms, fs = m[good], fwd[good]
    order = np.argsort(ms)
    k = len(order) // 5
    spreads.append(float(np.mean(fs[order[-k:]]) - np.mean(fs[order[:k]])))

res2 = pv._mean_test(spreads)
print(f"    planted spread: mean {res2['mean_pct']}%  t={res2['t_stat']}  "
      f"p={res2['p_value']}  n={res2['n']}")
ok(res2["mean_pct"] > 0, "planted momentum effect shows a positive spread")
ok(res2["mean_pct"] > abs(res["mean_pct"]),
   "the planted effect is larger than the noise baseline")

print("\n4. Statistics behave at the edges")
ok(pv._mean_test([0.01, 0.02])["insufficient"] is True,
   "two observations are refused rather than given a p-value")
ok(pv._grade([], "empty", 5, 1)["insufficient"] is True,
   "an empty group is refused")
g = pv._grade([("2025-01", 0.01, 0.02)] * 40 + [("2025-02", -0.01, 0.0)] * 40,
              "two months", 2, 12)
ok("insufficient_independent_windows" in g,
   "a 12-month horizon over 2 months is flagged as too few windows")

print("\n5. Low-risk scores calmer stocks higher")
calm = np.full((1, 400), 100.0, dtype=np.float32)
calm[0] = 100.0 * np.cumprod(1 + rng.normal(0.0002, 0.004, 400))
wild = 100.0 * np.cumprod(1 + rng.normal(0.0002, 0.05, 400))
both = np.vstack([calm, wild[None, :]]).astype(np.float32)
lr = pv._low_risk_scores(both, 399)
print(f"    calm {lr[0]:.3f}  vs wild {lr[1]:.3f}")
ok(lr[0] > lr[1], "the calmer series scores higher on low_risk")

print("\n6. Untestable components are declared, not estimated")
ok(set(pv.UNTESTABLE) >= {"quality", "value", "growth", "sentiment",
                          "composite_alpha_and_signals"},
   "all four missing factors and the composite are declared untestable")
ok(all(v.get("needs") and v.get("why_not") for v in pv.UNTESTABLE.values()),
   "each untestable component names the data it would require")

print("\n" + "=" * 64)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
