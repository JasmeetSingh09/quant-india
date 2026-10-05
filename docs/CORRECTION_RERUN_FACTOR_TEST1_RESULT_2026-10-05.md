# Correction re-run result: factor test 1 on repaired corporate actions

**Run:** 2026-10-05, 03:27 to 03:35 UTC, `GET /validation/pit?min_turnover=10000000&buckets=5` on
production, commit 158890d. Plan committed beforehand: `docs/CORRECTION_RERUN_FACTOR_TEST1_2026-10-05.md`.
**Raw output:** `docs/factor_test1_pit_result_corrected_2026-10-05.json`. The original result
(`docs/FACTOR_TEST1_RESULT_2026-09-13.md`, `docs/factor_test1_pit_result.json`) stays as the record of
the 2026-09-13 run.

## Verdict: unchanged

Under the same rules (`docs/PREREG_FACTOR_TEST1_2026-09-13.md`, significance level 0.00625):
- **Momentum** still demonstrates an edge at all four holding periods.
- **Low risk** still demonstrates none.

## What the repair changed in the data

| | Original run | Corrected run |
|---|---|---|
| Corporate actions seen | 20,280 | 20,296 |
| Applied | 19,047 | **19,992** |
| Could not be applied | 1,233 | **304** |
| Applied through the symbol (ISIN had no prices) | — | 931 |
| Price observations adjusted | 3,915,335 | 4,067,048 |

The 304 still unapplied are mostly dividends with no close before the ex-date.

## Results, side by side

The spread is the top fifth's return minus the bottom fifth's, net of the market, averaged across
months.

| Factor | Holding | Original spread | p | Corrected spread | p | Corrected 95% interval | Passes (orig / corr) |
|---|---|---|---|---|---|---|---|
| Momentum | 1 month | +1.53% | 0.0001 | +1.57% | 0.0001 | +0.80 to +2.34 | yes / yes |
| Momentum | 3 months | +4.25% | <0.0001 | +4.34% | <0.0001 | +2.88 to +5.80 | yes / yes |
| Momentum | 6 months | +7.49% | <0.0001 | +7.67% | <0.0001 | +5.79 to +9.55 | yes / yes |
| Momentum | 12 months | +11.04% | <0.0001 | +11.44% | <0.0001 | +8.41 to +14.48 | yes / yes |
| Low risk | 1 month | +0.96% | 0.091 | +0.97% | 0.094 | -0.17 to +2.10 | no / no |
| Low risk | 3 months | +2.41% | 0.020 | +2.45% | 0.020 | +0.39 to +4.50 | no / no |
| Low risk | 6 months | +3.31% | 0.019 | +3.47% | 0.015 | +0.68 to +6.26 | no / no |
| Low risk | 12 months | +2.85% | 0.201 | +3.29% | 0.143 | -1.13 to +7.71 | no / no |

Momentum's five groups are still in order at every holding period; low risk's still are not.

**Described, not tested:** momentum's top group as a portfolio, rebalanced monthly, net of costs.

| | Original | Corrected |
|---|---|---|
| Annual return | 23.8% | 24.5% |
| Sharpe ratio | 0.78 | 0.82 |
| Worst fall | -38.7% | -36.8% |

## Reading

- **Why momentum got slightly stronger:** the fake crashes from missing splits were noise in both
  directions. A stock with an unrecorded split looked like it had collapsed, which pushed it into the
  bottom group and gave it a false recovery or a false loss. Removing that noise moved the momentum
  spreads up by 0.04 to 0.40 points. The conclusion does not rest on the repair.
- **Still open:** 46 suspected splits that no source records yet are listed in
  `docs/HAND_CHECK_SPLITS_2026-10-05.md`. When they are verified from company filings, this run is
  repeated under the same plan.
