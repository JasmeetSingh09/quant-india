# Momentum robustness: result

**Run 2026-09-18, 04:48–05:30 UTC,** on production (commit `8081691`, v1.4.1 with
no behavioural drift). The rules were set in `PREREG_MOMENTUM_ROBUSTNESS_2026-09-17.md`,
committed first (`037413c`).

**Raw outputs:**
- `momentum_robustness_H1_2026-09-18.json`
- `momentum_robustness_H2_2026-09-18.json`
- `momentum_robustness_full_2026-09-18.json`
- `momentum_robustness_floor50cr_2026-09-18.json`
- `momentum_iima_agreement_2026-09-18.json` (script `research/momentum_iima_agreement.py`)

**Server:** memory stayed at about 1,405 MB through all four runs, with no restart.

## Primary tests (three; Bonferroni, each at 0.0167)

| Test | Setting | Result | p | Verdict |
|---|---|---|---|---|
| **H1 investable** | Traded value at least Rs 10 crore a month. 170 monthly rankings, about 394 stocks each | 1-month top-minus-bottom spread **+1.11%**, 95% CI +0.31 to +1.92 | 0.0072 | **Passes** |
| **H2 recent** | Rs 1 crore floor; rankings from 2019-01 only. 92 rankings, about 1,040 stocks each | spread **+1.49%**, 95% CI +0.42 to +2.55 | 0.0066 | **Passes** |
| **H3 independent** | Our monthly spread against IIMA's WML. 161 months, 2012-08 to 2025-12 | Pearson **r = 0.80** (t 16.9) | < 0.0001 | **Passes** |

**Pre-registered wording:**
- "Momentum's edge held among stocks trading at least Rs 10 crore a month."
- "It held in 2019–2026."
- "Our momentum ranking moved with IIMA's independently built momentum factor."
  A pass is agreement, not proof of a profit.

**H3 month pairing.** Our spread is keyed by the month the ranking was formed,
and measures the following month's return. So our formation month m is paired
with IIMA's month m + 1, the month in which both returns were earned. The
pre-registration said "common months" without stating this; the pairing is
recorded here, before interpretation, as the only one that compares returns
earned over the same month.

## Secondary (described; no claims)

- **Rs 50 crore floor:** spread +0.86% a month, 95% CI −0.05 to +1.76, p 0.063.
  About 188 stocks a month. **Not significant.** Among the biggest, most-traded
  stocks, the edge shrinks and can no longer be told apart from zero.
- **Rs 10 crore floor, split into liquidity thirds (exploratory):**

  | Liquidity third | Momentum result | p |
  |---|---|---|
  | Least liquid | +0.93% | 0.0005 |
  | Middle | +0.90% | 0.0012 |
  | Most liquid | +0.07% | 0.82 |

- **Rs 10 crore floor, longer holding periods:** 3-month spread +3.50%, 6-month
  +6.25%, 12-month +8.92%, each p < 0.0001.
- **Earlier half** (rankings before 2019-01, Rs 1 crore floor): +1.59% a month,
  t 2.79, over 78 rankings.
- **Regression of our monthly spread on IIMA's WML** (Newey-West, 6 lags):
  - slope 0.88, t 10.0;
  - intercept **+0.59% a month**, t 2.49, p 0.013.

  Our spread earns somewhat more than IIMA's factor explains. IIMA's factor is
  value-weighted with 30% tails; ours is equal-weighted with 20% tails, so this
  is a difference of construction, not a separate edge.
- **Consistency:** the full-period run at the default floor reproduced factor
  test 1 exactly (+1.535% a month, p 0.0001). The new `from_month` window and the
  per-month output changed nothing when unused.

## What this means

Momentum as V1 computes it (12-1, volatility-adjusted):
- holds on point-in-time, corporate-action-adjusted prices, delisted stocks
  included;
- holds among stocks trading at least Rs 10 crore a month;
- holds after 2019 as well as before;
- tracks an independent academic momentum factor closely.

It is **not** demonstrated among the most liquid, largest stocks (the most
liquid third, and the Rs 50 crore floor). Any claim about momentum must say that
the edge sits in mid-sized, reasonably liquid stocks.

## Limits

- **No trading costs** in these spreads.
- **Signal only:** a top-minus-bottom spread needs a short position, which retail
  investors in India cannot easily take. The long-only top group is reported in
  the JSON output.
- **Single factor:** this tests the momentum score alone, not V1's composite score
  or its labels.
