# Pre-registration: factor test 1 — momentum and low risk on the point-in-time archive

**Written:** 2026-09-13, before the run. **Committed before any result exists.**
This is the rerun of the momentum validation on the corporate-action-adjusted
archive ("A5"), extended to the low-risk factor. The rules below are fixed now
and will not be changed after the numbers are seen.

## What is run

`GET /validation/pit?min_turnover=10000000&buckets=5` on production, commit
`7718754`, code in `backend/modules/pit_validation.py`. No parameter differs from
the module's defaults.

## Data

- NSE end-of-day prices as printed (`bhavcopy_eod`), from the first stored day
  to the last. NSE collection has been paused since 2026-09-08, so the archive
  ends where collection stopped; the run records the exact range.
- Adjusted for splits, bonuses and dividends from the stored corporate actions.
- Securities joined across ticker changes by ISIN identity resolution.
- A security with no price at the end of a holding period is counted at -100%,
  so delisted companies stay in and count against the factor.

## Factors, read from the frozen model

- **Momentum:** 12-1 return, volatility-adjusted, through tanh.
- **Low risk:** trailing volatility and worst drawdown, 60/40, through tanh.

## Universe and buckets

- At each month-end, stocks with monthly traded value of at least Rs 1 crore and
  a valid score. A month with fewer than 50 such stocks is skipped.
- Stocks are split into 5 groups by score **within each month**.

## Primary hypotheses (8)

For each factor (2) and holding period of 1, 3, 6 and 12 months (4):
*does the top group's return, net of the market that month, beat the bottom
group's?* The statistic is the mean of the monthly top-minus-bottom spread,
tested across months (so stocks picked in the same month are not counted as
independent). A holding period counts as a usable test only if at least 3
non-overlapping windows fit.

## Decision rule

- Significance level: **0.05 divided by the number of usable primary tests**
  (at most 8, so at most 0.00625). Bonferroni.
- A factor has **demonstrated an edge** if at least one of its holding periods
  has a **positive** mean spread **and** a p-value below that level.
- A significant **negative** spread is reported as **reversed**: the factor
  picked losers. It is not an edge.
- Anything else is reported as **no demonstrated edge**. That means the data
  did not show one, not that none exists.

## Reported but not tested

- The 1-month top-group portfolio net of 0.4% round-trip costs: return,
  volatility, drawdown. Description only.
- Cuts by market regime and by liquidity. Exploratory: uncorrected, cut from the
  same months, never a finding.

## Commitments

- Every result is reported, including no edge and reversed.
- No rerun with different parameters, universes, periods or bucket counts. If
  the run fails for a technical reason (for example the server runs out of
  memory), it is rerun once with exactly these parameters and the failure is
  recorded.
- Quality, growth, value, sentiment, the composite score and the Buy/Sell
  labels are **not** tested here; the archive cannot reconstruct them.
