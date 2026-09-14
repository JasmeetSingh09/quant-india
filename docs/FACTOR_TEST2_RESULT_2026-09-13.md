# Factor test 2 result: growth shows an approximate lead; quality and value show none

**APPROXIMATE.** Restated statements, about three years of rankings, companies
listed today only. As the pre-registration says: a lead is worth following, not
proof; no lead is weak evidence against.

**Rules:** `docs/PREREG_FACTOR_TEST2_2026-09-13.md`, pushed 2026-09-13 at
21:25:03 UTC (`a8f3738`), amendments at 21:34:17 UTC (`10fc85e`), code at
21:37:18 UTC (`b22d157`), all before any run on real data.

**Runs:**
- **Run 1**, 2026-09-13 22:58 UTC: defective (below). Kept as a record, not a result.
- **Run 2**, 2026-09-14 05:51 UTC: the one rerun the pre-registration allows
  after a technical failure, approved before it ran.

**Raw output:** `docs/factor_test2_result.json` (run 2),
`docs/factor_test2_result_run1_defective.json` (run 1). **Checks:**
`research/factor_test2_checks.py`.

## Verdict, by the pre-registered rules (run 2)

| Factor | Verdict |
|---|---|
| **Quality** | **No lead** at any holding period |
| **Value** | **No lead** at any holding period |
| **Growth** | **Approximate lead** at 3 and 6 months; not at 1 month |

Significance level: 0.05 / 9 usable tests = **0.0056** (Bonferroni).

## Run 1 was defective

- **The rule.** The pre-registration defines a month's universe as stocks with
  a usable score, a price and Rs 1 crore of monthly turnover, and skips a month
  with fewer than 50. Run 1 applied the 50 before scoring, then ranked a factor
  with as few as 10 scored stocks.
- **What that did to growth.** Yahoo's statements start at FY2023, and growth
  needs the year before. From June 2023 to April 2024, while FY2023 was the
  latest public year, growth could be scored for only 14 to 36 stocks, so its
  top group held 3 to 8. July 2023's spread was +76%, from 3 stocks.
- **A second, smaller slip.** Group returns were measured against every priced
  stock rather than the scored ones the pre-registration names. This moved group
  averages, not spreads.
- **Quality and value were not affected.** They never had fewer than 1,547
  scored stocks; their spreads and p-values are identical in both runs.
- **Run 1 said** growth had a lead at 6 months only (+6.65%, p 0.0019). That
  number is withdrawn.
- **The fix.** `research/factor_test2_run.py` now counts only stocks scored for
  the factor being tested, and records every month it skips. Four new checks in
  `backend/tests/statement_factors_test.py` cover it; all four fail against run
  1's code.

## The data

- **Stocks.** 2,291 EQ-series stocks from the app's NSE equity list.
- **Statements.** Available for 2,283 (8 came back empty); 2,234 have four
  years of net income.
- **Prices.** Available for all 2,291. 671 start after 2022: 99 in 2023, 279 in
  2024–25, 293 in 2026. The last price is 2026-09-11.
- **Rankings.** Quality and value have 38 monthly rankings with a 1-month
  return (June 2023 to July 2026), with 1,549 to 2,041 eligible stocks a month.
  Growth starts in May 2024, when FY2024 became public: 27 rankings.
- **Where the data is kept.** Saved outside the repository, because of Yahoo's
  terms: a zip with SHA-256 `7e0868e219daa455f3a4494dc7c37ab5c9a9bfbaf6ed021f86e3bd48bd46773f`.
  It holds the inputs both runs read, plus run 1's output.

## Primary results (run 2)

Spread = the top fifth's return minus the bottom fifth's over the holding
period, averaged across formation months.

| Factor | Holding | Spread | 95% interval | p-value | Months | Independent windows | Passes |
|---|---|---|---|---|---|---|---|
| Quality | 1 month | +0.04% | −0.93 to +1.01 | 0.93 | 38 | 38 | No |
| Quality | 3 months | −0.07% | −1.78 to +1.65 | 0.94 | 36 | 12 | No |
| Quality | 6 months | −0.96% | −3.80 to +1.87 | 0.49 | 33 | 5 | No |
| Value | 1 month | +0.44% | −0.50 to +1.37 | 0.35 | 38 | 38 | No |
| Value | 3 months | +0.80% | −0.65 to +2.26 | 0.27 | 36 | 12 | No |
| Value | 6 months | +1.38% | −1.18 to +3.94 | 0.28 | 33 | 5 | No |
| Growth | 1 month | +0.74% | +0.11 to +1.37 | 0.024 | 27 | 27 | No |
| **Growth** | **3 months** | **+2.08%** | +1.03 to +3.14 | **0.0004** | 25 | 8 | **Yes** |
| **Growth** | **6 months** | **+3.00%** | +1.66 to +4.34 | **0.0001** | 22 | 3 | **Yes** |

Excess return by group, lowest score to highest, against the equal-weight
return of that month's scored stocks:

| Factor | Holding | Lowest | 2 | 3 | 4 | Highest |
|---|---|---|---|---|---|---|
| Growth | 1 month | −0.28% | −0.22% | −0.11% | +0.15% | +0.46% |
| Growth | 3 months | −0.89% | −0.56% | −0.24% | +0.50% | +1.19% |
| Growth | 6 months | −1.41% | −0.67% | −0.32% | +0.82% | +1.59% |
| Value | 1 month | −0.25% | −0.29% | +0.16% | +0.19% | +0.19% |
| Quality | 1 month | +0.06% | −0.15% | +0.06% | −0.06% | +0.10% |

**Growth's five groups are in order at every holding period.** Value's cheaper
half beat its dearer half, but not in order and not significantly. Quality
shows no pattern at any holding period.

## Checks made after the run, not part of the rule

None of these changes a verdict.

| Check | Growth, 3 months | Growth, 6 months |
|---|---|---|
| p-value allowing for overlapping months (Newey-West) | 0.0044 | 0.0022 |
| Each non-overlapping subset alone | 3 of 3 positive, +1.8% to +2.4%, p 0.04 to 0.10 | 6 of 6 positive, +1.1% to +4.8%, p 0.07 to 0.41 |
| By formation year: 2024 / 2025 / 2026 | +1.5% / +1.3% / +4.8% | +1.9% / +3.0% / +7.2% (2026: 2 months) |
| Months with a positive spread | 19 of 25 | 17 of 22 |
| Extreme returns capped at the 1st and 99th percentile | +2.11%, p 0.0004 | +3.10%, p 0.0001 |

- **Overlap.** The rule's t-test treats neighbouring months as independent,
  though at 3 and 6 months they share most of their holding period. Allowing
  for that, growth still clears 0.0056, but only just. Quality and value stay
  far from it (p 0.40 or more).
- **The size of the evidence.** At 6 months, 22 formation months are only 3
  independent windows, and no single non-overlapping subset is significant on
  its own. The lead is consistent in direction (every year, every subset, every
  group in order) more than it is large in sample.
- **Outliers.** The largest forward return was SILVERTUC, +1,665% over 6 months.
  Capping every extreme return changed no verdict.

## Exploratory, never a finding (12 comparisons, uncorrected)

The top group's 1-month excess return, by liquidity third within the month:

| Factor | Least liquid | Middle | Most liquid |
|---|---|---|---|
| Growth | +0.26% (p 0.55) | +0.48% (p 0.15) | +0.54% (p 0.13) |
| Quality | +0.51% (p 0.15) | −0.03% (p 0.93) | +0.01% (p 0.98) |
| Value | +0.23% (p 0.57) | −0.08% (p 0.81) | +0.54% (p 0.25) |

Value ranked on each month's P/E and P/B ranks instead of fixed market averages:
+0.42% (p 0.41), +0.81% (p 0.33) and +1.21% (p 0.38) at 1, 3 and 6 months, the
same answer as the rule's version.

Unlike momentum in test 1, growth's top group did not do best in the thinnest
stocks. That is a description, not a tested finding.

## What this does and does not show

- **It shows** that from May 2024 to 2026, NSE stocks with faster fiscal-year
  revenue and earnings growth, counted only once the accounts were public, beat
  slower-growing stocks over the next 3 and 6 months, with all five groups in
  order, by rules fixed before the run.
- **It is approximate.** The figures are as restated today. Only companies
  listed today are included, so companies whose growth collapsed and that then
  delisted are missing, which flatters exactly this kind of factor. The period
  is about two years, in one market.
- **It is not the live input.** The live growth factor reads Yahoo's latest
  quarterly growth figure, which has no history. This tests a fiscal-year
  version built from annual statements.
- **It does not show that growth adds anything beyond momentum.** Companies
  growing their earnings often have rising prices, so the two may pick the same
  stocks. That was not pre-registered, so it was not checked here.
- **Quality and value** showed no lead. Given the data, that is weak evidence
  against them, not proof they are worthless.

## Also affects factor test 1

- **Overlap.** Its 3-, 6- and 12-month p-values come from the same plain t-test
  on overlapping months, so they overstate the independent evidence. Momentum's
  1-month pass (170 separate months, p 0.0001) does not depend on this. The
  longer holding periods have not been rechecked; their monthly spreads are
  computed on production.
- **The 50-stock minimum.** This defect cannot affect momentum: a stock enters a
  test 1 month only with a momentum score. Low risk is ranked among those stocks
  with a minimum of 10 low-risk scores; whether any month fell below 50 has not
  been checked.

## Not changed by this result

The V1.4 model is frozen. Factor weights and the evidence page's wording are
unchanged. Whether to change either is a decision, not a consequence of this run.
The real test for these factors is the forward test on the app's own recorded
inputs, from 27 December 2026.
