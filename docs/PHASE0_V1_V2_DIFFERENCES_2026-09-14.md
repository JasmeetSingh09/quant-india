# How V2 differs from V1

**Phase 0 record, written 2026-09-14 from the code at `aa4d2f9`.** V1 is described
in `PHASE0_V1_METHODOLOGY_2026-09-14.md`. This lists every difference, so that
neither model can change quietly because a result looks better.

## In one sentence

V2 takes V1's four factor results unchanged, adds growth and low risk, uses
different weights, and leaves out unmeasured factors instead of counting them
as 0. Nothing else differs.

## Side by side

| | V1 (four-factor) | V2 (six-factor) |
|---|---|---|
| Code | `alpha_model.compute_alpha_score` | `alpha_v2.compute_v2` |
| Stamp on each result | `alpha-v4-distress-coverage` | `alpha-v2-six-factor` |
| Momentum | 35% | 18% |
| Sentiment | 25% | 10% |
| Quality | 25% | 22% |
| Value | 15% | 17% |
| Growth | not used | 15% |
| Low risk | not used | 18% |
| Unmeasured factor | contributes 0; other weights not scaled up | left out; the remaining weights are scaled up to sum to 1 |
| Score | 100 × weighted sum | 100 × weighted sum ÷ weights used |
| Labels | shared `signal_for_score`: above 40 Strong Buy, above 15 Buy, below −40 Strong Sell, below −15 Sell | the same function |
| Stated horizon | 21 trading days | 21 trading days |
| Used by | nightly scan, Top Picks, stock pages, all live labels | `/alpha/v2` and `/alpha/compare`, and read by `model_comparison`, `regime_weights`, `factor_evidence`, `factor_correlation` and `pit_validation` |

## Shared, not duplicated

- **The four common factors.** V2 reuses V1's momentum, sentiment, quality and
  value results for the same stock; it does not compute them again. A defect in
  one of them (for example the Piotroski ceiling of 7) is in both models.
- **The label thresholds.** One function. Until v1.4, V2 carried its own copy.
- **Refusal.** V2 returns V1's error when V1 refuses a stock. It also refuses
  when no factor has usable data.

## The two added factors

### Growth, weight 15%

- **Inputs:** Yahoo's latest `revenueGrowth`, and `earningsGrowth` (falling back
  to `earningsQuarterlyGrowth`). This is a live figure with no history.
- **Score:** mean of tanh(revenue growth ÷ 0.30) and tanh(earnings growth ÷ 0.50),
  over whichever legs exist.
- **Confidence:** 0.85 with both legs, 0.425 with one. Neither leg: score 0,
  confidence 0.

### Low risk, weight 18%

- **Inputs:** about 400 calendar days of Yahoo closes, adjusted. Fewer than 60
  closes or returns: score 0, confidence 0.
- **Measures:** annualised volatility of daily returns, and the worst
  peak-to-trough fall over the window, counting a fall in the first period.
- **Score:** 0.6 × tanh((20% − volatility) ÷ 20%) + 0.4 × tanh((25% + worst fall)
  ÷ 25%), clipped to −1 and +1. Calmer stocks score higher.
- **Confidence:** min(1, 0.5 + number of returns ÷ 500).

## Why the weights differ, as written in the code

`alpha_v2.py` gives these reasons:

- **Momentum** cut from 25% to 18%: no significant edge in 12 walk-forward
  configurations on about 42 windows.
- **Sentiment** cut from 15% to 10%: weakest published evidence, untested here.
- **Low risk** raised to 18%: broadest published replication.
- **Quality and value** raised slightly.

The code says plainly that none of this validates the model.

Two of those reasons have since been tested on this project's data:

| Reason in the code | What the tests found | Changes the weights? |
|---|---|---|
| Momentum has not shown an edge here | Factor test 1 (2011–2026, all stocks above Rs 1 crore monthly turnover): momentum passed at all four holding periods, mostly outside the most liquid third | No. Whether to change momentum's weight or wording is an open decision. |
| Low risk has the broadest record | Factor test 1: low risk did not pass at any holding period | No |

V1's weights have no written rationale in the repo; see "Stale claims" in the V1
record.

## Differences that affect testing

- **Growth as tested is not V2's growth.** Factor test 2 rebuilt growth from
  annual statements, fiscal year over fiscal year. V2 reads Yahoo's latest
  quarterly figure, which has no history. The approximate lead found in test 2
  is evidence about the annual version.
- **Low risk as tested uses a different window.** Factor test 1 used a
  270-trading-day window from the exchange archive. V2 uses about 400 calendar
  days of Yahoo prices. The reference points (20% volatility, 25% fall) and the
  0.6 / 0.4 split are the same.
- **V2's composite cannot be backtested.** Neither can V1's, for the same
  reason: quality, value, growth and sentiment use today's data.

## Rules that keep the two apart

1. V1 and V2 are compared, never merged. Promoting V2 to drive the live labels
   is a decision recorded as a new specification version, with the comparison
   that justified it.
2. A change to either model's factors, weights, thresholds or missing-data rule
   is a new specification version with notes, frozen before any result it is
   used for.
3. A factor shared by both models changes both. The notes must say so.
