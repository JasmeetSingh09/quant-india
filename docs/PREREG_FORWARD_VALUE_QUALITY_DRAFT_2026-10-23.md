# Pre-registration DRAFT: forward (prospective) test of value and quality

**Status: DRAFT for the owner and the reviewer. Nothing has been run, and no graded month exists
yet.**

**When it binds:** once approved and committed, **before the first formation date** (section 3).
After that, sections 2–9 do not change. Any edit before approval goes in section 11.

**Why forward.** The historical route needs accounts as first published for 80% of company-years. It
stands at 488 of 1,033 (47.2%), and the remaining 339 need hand downloads. A forward test needs none
of that:
- the app already stores its own scores and the accounts it saw, every night;
- the data for a month cannot exist before the rules are written, so the result cannot have been
  seen;
- it is the only route to the verdict **"prospectively validated"**.

**What already accrues** (checked 2026-10-23):

| Record | From | Contents |
|---|---|---|
| `factor_history` | 2026-08-24 | Nightly V1 factor scores and price, 2,794 stocks |
| `accounts_observed` | 2026-09-19 | Fundamentals as the app saw them |
| `predictions` | 2026-07-24 | Logged score snapshots |

## 1. Question

Do the app's **V1 value** and **V1 quality** scores, as computed live and stored at the time, rank
stocks by their **next month's return**?

## 2. Signals: exactly what the app stored, never recomputed

- **The scores:** `factor_history.value` and `factor_history.quality` for `model = 'v1'`, from the
  formation date's nightly cycle. They are never recomputed, and they are read only from rows stored
  on that date.
- **Measured:** a stock counts as measured for a factor only if that cycle's `factor_inputs` hold at
  least one non-missing input for the factor:
  - value: `legs_used` > 0;
  - quality: `roe` or `fcf_yield` present.

  A stored 0 with no inputs is a refusal, not a score.
- **Methodology version.** The window covers one value/quality methodology: the one live at the
  first formation date.
  - **A change to how value or quality is computed ends the current segment and starts a new one,**
    each graded separately on its own clock. This includes the drafted sector-map v1.6.2, the
    Piotroski statement inputs, and any weight or formula change.
  - **The owner decides before approval:** hold such changes until the 24-month look, or accept
    segments. This draft assumes they are held.
  - Changes that touch neither factor (for example v1.6.1, sentiment and momentum) do not split the
    window.

## 3. Formation, universe and returns

**Formation dates:**
- The last **complete** nightly cycle (`cycle_complete = 1`) of each calendar month.
- If the month's last cycle is incomplete, the latest complete cycle in that month's final 5
  calendar days is used. If there is none, the month is skipped and recorded.
- **First formation date:** the last complete cycle of the first calendar month that ends **after**
  this document is approved (for example 30 November 2026).

**Universe:**
- Every stock in that cycle that is measured for the factor (section 2).
- Funds and ETFs are already excluded by the scan.
- **Financial companies are included,** because the app scores them. A secondary cut excludes them.

**Return:** from the formation date's close to the next formation date's close, adjusted for splits,
bonuses and dividends.

**Price source: the app's own nightly record.**
- **Primary: (P0) the price stored with the scores in `factor_history`, every night, for every
  scored stock.**
  - It already accrues without NSE. For example, October 2026 cycles are all complete, with prices
    for about 2,480 stocks a night (2,482 on 2026-10-23).
  - It is point-in-time by construction: written on the night, never fetched later.
  - A stock that later delists keeps every price recorded while it traded. This removes most of the
    survivor bias a later Yahoo fetch would have.
- **Splits, bonuses and dividends.** Stored prices are as quoted, so a split inside a month would
  look like a crash. Each month's return is therefore adjusted with the corporate actions known for
  that month, from:
  - the stored NSE corporate actions, if collection is permitted; otherwise
  - Yahoo's split and dividend events, fetched at grading time.

  A stock with a price change beyond ±50% in a month and **no** recorded action is excluded that
  month, and reported.
- **Cross-check (reported, not deciding):** Yahoo adjusted closes for the same dates. Monthly
  returns that differ by more than 5 percentage points are listed.
- **NSE end-of-day files** replace nothing. If NSE grants written permission, they are a second
  cross-check.

**Delistings.** A stock that stops being scored is exited at its **last stored price**. This rule is
the primary one, and the count is reported. A sensitivity re-grades those exits at **−100%**.

## 4. Statistics, fixed now

**Primary.** The monthly **Spearman rank correlation (rank IC)** between the factor score and the
next-month return, across the month's universe. The test statistic is the **mean of the monthly
ICs**.
- **The p-value used for decisions** is the larger of: a two-sided t-test on the monthly ICs, and a
  two-sided Newey-West test with 3 lags.

**Secondary (reported, not used for decisions):**
- the equal-weight top-fifth minus bottom-fifth spread, gross;
- the same spread net of the frozen 0.415% round-trip cost;
- the same tests within the 500 largest stocks by stored market cap;
- excluding financials;
- the delisting sensitivity.

**Two factors, two looks:** the overall 5% significance budget is split in advance.

| Look | When | Level per factor |
|---|---|---|
| **First** | after **24** graded months | **0.005** |
| **Final** | after **60** graded months | **0.020** |

Per factor: 0.005 + 0.020 = 0.025. Across both factors: 0.05.

**No other look decides anything.** Interim figures, for example at 12 months, are description only
and carry no verdict.

## 5. Verdicts

**At 24 months, for each factor:**
- **Prospectively validated:** mean IC > 0, decision p < 0.005, **and** the top-minus-bottom spread
  is positive.
- **Failed prospectively (reversed):** mean IC < 0 with decision p < 0.005.
- **Not yet conclusive:** anything else. The test continues to 60 months; this is not a failure.

**At 60 months, for each factor still open:**
- **Prospectively validated:** mean IC > 0, decision p < 0.020, and a positive spread.
- **Not validated:** anything else. If the mean IC is ≤ 0, the verdict is **failed prospectively**.

**What may be said in the app:** only these verdicts, worded as written, with the window, the
universe and the price source stated. Nothing in between.

## 6. Expectations, stated before any data

This is a rough planning estimate, not a result.
- **Assumption:** the monthly IC varies by about 0.10 from month to month.
- **24 months:** the standard error of the mean IC is about 0.02. Passing at 0.005 needs a mean IC
  near 0.06, which is large for value or quality factors.
- **60 months:** the standard error is about 0.013, so a mean IC near 0.03 could pass at 0.020.

**So the most likely 24-month verdict is "not yet conclusive".** The plan accepts that rather than
over-reading a short window.

## 7. Integrity of the record

- **No rewriting.** At each month's formation date, the formation cycle's rows (ticker, score,
  inputs, price) are exported and their sha256 is committed to `docs/audit/forward_vq/`. Grading uses
  only rows whose hash matches. **Any later edit to stored rows is detectable.**
  - This is a small script plus a monthly commit. It needs the owner's approval, because it reads
    production.
- **Gaps:** a cycle missing or incomplete for a whole month skips that month, and the skip is
  recorded. A missing month is never filled in.
- **Monitoring:** the nightly check already watches scan completeness. A month whose cycle covers
  fewer than 90% of the usual universe is graded but flagged.

## 8. Not in scope

The composite score and labels (the separate `predictions` record), momentum, and sentiment.
Sentiment could join this framework, see the note in the report; that would be a separate
pre-registration.

## 9. Decisions needed from the owner before approval

1. **Methodology:** hold value/quality changes (the v1.6.2 sector map, the Piotroski inputs) until
   the 24-month look, or accept graded segments.
2. **Price source (section 3):** confirm the app's own nightly stored prices (P0) as the primary source.
3. **Integrity:** approve the monthly read-only export and its hash commit (section 7).

## 10. Relation to the historical route

The annual-report collection is optional from here. If it ever reaches the 80% gate, the historical
test needs its own new pre-registration. It would complement this forward test; it would not replace
it.

## 11. Changes before approval

**2026-10-23:** the primary price source is now the app's own nightly stored prices (P0), not NSE or a later Yahoo
fetch. This was prompted by the owner ("collect data so we can validate after 2 years") and checked
against the stored record. NSE becomes an optional cross-check.
