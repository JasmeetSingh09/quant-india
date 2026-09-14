"""
factor_test2_checks.py — checks on factor test 2, run after it. NOT part of the
pre-registered rule, and nothing here changes a verdict.

1. Overlap. The rule tests the mean of the monthly top-minus-bottom spreads with
   a plain t-test, the same arithmetic as pit_validation. At 3 and 6 months
   neighbouring months share most of their holding period, so their spreads move
   together and the plain t-test overstates the independent evidence. The same
   spreads are re-tested with a Newey-West standard error (h-1 lags), and each
   non-overlapping subset (every h-th month) is tested on its own.
2. Timing. The spread by formation year, and how many months were positive.
3. Outliers. Every forward return capped at the pooled 1st and 99th percentile
   for its holding period, then the rule re-applied unchanged.

    python research/factor_test2_checks.py DATA_DIR
"""

import copy
import math
import os
import sys

import numpy as np
from scipy import stats as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import factor_test2_run as R  # noqa: E402


def newey_west_p(x, lags):
    x = np.asarray(x, dtype=float)
    n = len(x)
    e = x - x.mean()
    v = e @ e / n
    for k in range(1, lags + 1):
        v += 2 * (1 - k / (lags + 1)) * (e[k:] @ e[:-k]) / n
    t = x.mean() / math.sqrt(v / n)
    return float(2 * st.t.sf(abs(t), df=n - 1))


def spreads_of(panel, factor, h):
    """The exact monthly spreads test_factor tests, with the months they belong to."""
    captured = []
    original = R.mean_test
    R.mean_test = lambda x: (captured.append(list(x)), original(x))[1]
    try:
        R.test_factor(panel, factor, h)
    finally:
        R.mean_test = original
    # the same month filter test_factor applies
    months = [ym for ym, rows in panel.items()
              if sum(1 for r in rows if h in r["fwd"] and r["scores"].get(factor) is not None)
              >= R.MIN_ELIGIBLE]
    assert len(months) == len(captured[0]), "month filter drifted from test_factor"
    return months, captured[0]


def capped(panel):
    pooled = {h: [] for h in R.HORIZONS}
    for rows in panel.values():
        for r in rows:
            for h, v in r["fwd"].items():
                pooled[h].append(v)
    cuts = {h: np.percentile(v, [1, 99]) for h, v in pooled.items() if v}
    out = copy.deepcopy(panel)
    for rows in out.values():
        for r in rows:
            for h in r["fwd"]:
                lo, hi = cuts[h]
                r["fwd"][h] = float(min(max(r["fwd"][h], lo), hi))
    return out, cuts


def main(data_dir):
    stmts, prices = R.load(data_dir)
    _, _, panel = R.build_panel(stmts, prices)

    print("1-2. OVERLAP AND TIMING")
    for factor in R.FACTORS:
        for h in R.HORIZONS:
            months, s = spreads_of(panel, factor, h)
            line = (f"{factor:<8} {h}m  mean {np.mean(s) * 100:+.2f}%  months {len(s)} "
                    f"({months[0]} to {months[-1]})")
            if h > 1:
                line += f"  Newey-West p={newey_west_p(s, h - 1):.4f}"
            print(line)
            if h > 1:
                for off in range(h):
                    sub = s[off::h]
                    if len(sub) >= 3:
                        print(f"    subset from month {off}: n={len(sub)} "
                              f"mean {np.mean(sub) * 100:+.2f}% "
                              f"p={st.ttest_1samp(sub, 0).pvalue:.3f}")
            years = {}
            for ym, v in zip(months, s):
                years.setdefault(ym[:4], []).append(v)
            print("    by formation year: " + ", ".join(
                f"{y} {np.mean(v) * 100:+.2f}% ({len(v)} months)" for y, v in years.items()))
            print(f"    months with a positive spread: {sum(v > 0 for v in s)} of {len(s)}")

    print("\n3. OUTLIERS: forward returns capped at the 1st and 99th percentile")
    cpanel, cuts = capped(panel)
    for h, (lo, hi) in cuts.items():
        print(f"    {h}m caps: {lo * 100:+.1f}% to {hi * 100:+.1f}%")
    for factor in R.FACTORS:
        for h in R.HORIZONS:
            a = R.test_factor(panel, factor, h)["top_minus_bottom"]
            b = R.test_factor(cpanel, factor, h)["top_minus_bottom"]
            print(f"{factor:<8} {h}m  as run {a['mean_pct']:+.2f}% p={a['p_value']}   "
                  f"capped {b['mean_pct']:+.2f}% p={b['p_value']}")


if __name__ == "__main__":
    main(sys.argv[1])
