# Pre-registration: factor test 2 — quality, value and growth, approximately

**Written:** 2026-09-13, before any code for this test exists and before any
result. The rules below are fixed now and will not be changed after the numbers
are seen.

## What this test can and cannot show

This is an **approximate** test, and every result will carry that word.

- The app has no record of company financials *as they were filed*. This test
  uses Yahoo's annual statements, fetched in September 2026. Where a company
  later restated a year, Yahoo shows the restated figure, which nobody could
  have seen at the time.
- Yahoo keeps about four fiscal years (FY2023–FY2026), so the test covers only
  about two to three years of monthly rankings.
- Only companies listed today are included. Companies that failed or delisted
  are missing, which flatters every factor.

So: **a pass is a lead worth following, not proof; a fail is weak evidence
against.** Neither changes the model. The real test for these factors is the
forward test on the app's own recorded inputs, from 27 December 2026.

## Data

- **Statements:** Yahoo annual income statement, balance sheet and cash flow,
  fetched once and saved, for every EQ-series stock in the app's NSE equity
  list. A coverage probe of 40 random stocks found 39 with four years of net
  income and 30 with every field below.
- **Prices:** Yahoo daily closes adjusted for splits and dividends, and volume.
- **When a figure becomes usable:** a fiscal year's statements count as known
  from the **month-end at least 60 days after the fiscal year ends** (SEBI's
  deadline for annual results; 31 March year-ends become usable at 31 May). Until
  then the previous year's statements are used. Nothing is used before that date.

## Factors, rebuilt from statements as close to the live code as the data allows

Each factor uses only the components whose inputs exist for that company and
year, and renormalises over them, as the live model does.

- **Quality** (live: `alpha_model._compute_quality_factor`):
  0.4 × (Piotroski proxy / 9) + 0.4 × ((ROE − 12%) / 8%) / 3 + 0.2 × ((FCF yield −
  3.5%) / 4%) / 3, then distress penalties (negative equity −0.5; interest cover
  below 1.5×, a loss, or negative operating cash flow −0.25 each; with any flag
  the score is capped at neutral first), then tanh.
  ROE = net income / shareholders' equity. FCF = operating cash flow + capital
  expenditure. FCF yield = FCF / market value at the formation date (price ×
  shares). The Piotroski proxy is the same nine signals the live
  `metrics.piotroski_score` computes, including its fixed "no dilution" point
  and treating missing long-term debt as zero.
- **Value** (live: `alpha_model._compute_value_factor`): −0.6 × P/E z-score −
  0.4 × P/B z-score, then tanh(x / 2). P/E = price / diluted EPS; P/B = price /
  (equity / shares). A non-positive multiple is dropped; if both are dropped the
  stock scores −0.5 as distressed.
  **Deviation, stated in advance:** the z-scores use the live model's own
  market fallback (P/E 22 ± 8, P/B 3.2 ± 1.5) rather than today's sector peers,
  because today's sector map would import look-ahead into every past month.
- **Growth** (live: `alpha_v2._growth_factor`): mean of tanh(revenue growth /
  0.30) and tanh(earnings growth / 0.50).
  **Deviation, stated in advance:** growth is fiscal year over fiscal year from
  the statements; the live factor reads Yahoo's latest quarterly growth figure,
  which has no history.

## Universe, buckets and returns

- At each month-end from June 2023: stocks with a usable score, a price, and
  monthly traded value of at least Rs 1 crore. A month with fewer than 50 is
  skipped.
- Five groups by score within each month.
- Forward returns at 1, 3 and 6 months, net of the equal-weight return of that
  month's eligible stocks. 12 months is not tested: fewer than 3 non-overlapping
  windows fit.

## Primary hypotheses (up to 9) and decision rule

For each factor (3) and holding period of 1, 3 and 6 months (3): does the top
group beat the bottom group? The statistic is the mean monthly top-minus-bottom
spread, tested across months. A holding period is usable only with at least 3
non-overlapping windows.

- Significance level: **0.05 divided by the number of usable tests** (Bonferroni).
- **Approximate lead:** a positive mean spread with a p-value below that level.
- **Reversed:** a significant negative spread.
- **No lead:** anything else.

## Exploratory, never a finding

- Value using each month's cross-sectional rank of P/E and P/B instead of the
  fixed market constants.
- Results by liquidity tercile.

## Commitments

- Every result is reported, including no lead and reversed.
- No rerun with different parameters, periods, universes or bucket counts. A
  technical failure is rerun once with these exact rules and recorded.
- The saved statements and prices are kept with the result, so the test can be
  reproduced from exactly the data it used.
- Sentiment, the composite score and the Buy/Sell labels are not tested here.
