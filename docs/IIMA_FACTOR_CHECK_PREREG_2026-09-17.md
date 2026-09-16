# IIMA factor library check: pre-registration

**Written 2026-09-17, before any statistic was computed from the data.** Only
the file headers, first rows and last rows were looked at, to confirm columns
and dates.

## Question

Did the momentum and value premiums exist in Indian equities, measured
independently of our code?

This checks the ideas behind two of our factors. It does not test our scoring,
our weights or any Quant India result.

## Data

**Source:** Agarwalla, S. K., Jacob, J. and Varma, J. R. (2013), *Four factor model
in Indian equities market*, Working Paper W.P. No. 2013-09-05, Indian Institute of
Management, Ahmedabad.
- **Library:** https://faculty.iima.ac.in/iffm/Indian-Fama-French-Momentum/
- **Release:** December 2025; data from October 1993 to December 2025.
- **Terms:** the page asks for the citation above and states no other terms.

**File:** `2025-12_FourFactors_and_Market_Returns_Monthly_SurvivorshipBiasAdjusted.csv`
- **Columns:** Date, SMB, HML, WML, MF, RF, in percent per month.
- The unadjusted file is used only for the secondary comparison.
- Raw files are not committed to this repository. The script downloads them and
  records each file's SHA-256.

**Method, from the working paper (revised 5 September 2014):**
- **Coverage:** BSE-listed companies in CMIE Prowess. Stocks traded on fewer than
  50 days in the prior 12 months are excluded.
- **Weighting:** portfolios are value-weighted, using total returns including
  dividends. No trading costs are charged.
- **WML (momentum):** each month, stocks are ranked on their return from month
  t−12 to t−1, the same 12-1 lookback as our momentum factor. Top 30% (winners)
  minus bottom 30% (losers), averaged across the small and big size groups.
  Rebalanced monthly.
- **HML (value):** book-to-market is measured each September from March year-end
  accounts, a 6-month reporting lag. Top 30% minus bottom 30%, averaged across
  size groups. Rebalanced yearly.
- **Size groups:** "big" is the top 10% by market capitalisation.
- **Survivorship:** a company that vanishes in distress (last price below half its
  face value) counts as a 100% loss.

**Known limits, stated before the results:**
- **Not strictly point-in-time.** The library is recomputed from each new Prowess
  release, and the FAQ says CMIE adds companies and corrects old data between
  releases. HML uses today's view of past book values, not the figures as first
  published.
- **Different construction from ours.** The universe, weighting (value, not
  equal), costs (none) and returns (with dividends) all differ from our
  backtests.

## Primary tests (two; Bonferroni, each at 0.025)

**P1 (momentum):** mean monthly WML is above zero.
- **P2 (value):** mean monthly HML is above zero.
- **Sample:** every month with a non-missing value, October 1993 to December 2025.
- **Statistic:** mean divided by its Newey-West standard error with 6 lags; p-value
  two-sided from the normal distribution.

## Secondary, descriptive only (no claims drawn from these)

1. SMB, and MF as published (reported, with no hypothesis).
2. **P1 and P2 statistics split into two subperiods:**
   - October 1993 to December 2012;
   - January 2013 to December 2025, roughly our backtest window.
3. **For WML and HML:**
   - annualised mean;
   - share of calendar years with a positive total;
   - the worst peak-to-trough fall of the cumulative factor.
4. Adjusted versus unadjusted file: the difference in mean WML and HML.

## Deferred

**Month-by-month correlation of our 12-1 top-minus-bottom returns with WML.**
- **Why deferred:** the saved record `docs/momentum_variants_adjusted_2026-09-14.json`
  lists the months used but not each month's return.
- **What it needs:** a rerun of momentum variants, deferred while production
  memory is being fixed (Render restart 2026-09-16).

## Wording decided in advance

- **P1 passes:** "A 12-1 momentum premium existed in Indian equities from 1993
  to 2025 on IIMA's survivorship-adjusted factor (Agarwalla, Jacob and Varma).
  This supports the idea behind our momentum factor; it does not test our
  scoring."
- **P2 passes:** "A book-to-market value premium existed on the same data, using
  retrospectively updated accounts. It does not test our value, quality or
  growth scores, which remain untested on point-in-time data."
- **A test fails:** say so in the same place, with the same prominence.
