# Pre-registration DRAFT: forward (prospective) test of sentiment

**Status: DRAFT for the owner and the reviewer. Nothing has been run.**

**When it binds:** once approved and committed, before its first formation date. Same rules as
`PREREG_FORWARD_VALUE_QUALITY_DRAFT_2026-10-23.md`, which this mirrors where it can.

**What is already true:**
- **The instrument is valid.** FinBERT reads Indian headlines correctly (factor test 3, macro-F1
  0.734).
- **Whether the score predicts returns is untested.**
- **The app stores what a forward test needs, every night:**
  - the sentiment score (`factor_history.sentiment`);
  - its inputs: `factor_inputs`, with `n_articles` and, when sentiment is refused, `refusal_reason`;
  - the stock's price.

  On 2026-10-22, 2,485 of 2,490 stocks had `n_articles` > 0, and 5 were refusals with a reason.

## 1. Question

Does the app's live V1 **sentiment** score, as stored at the time, rank stocks by their return over
the **following week**?

## 2. Signal

- **The score:** `factor_history.sentiment` for `model = 'v1'` from the formation cycle, never
  recomputed.
- **Measured:** `n_articles` > 0 in that cycle's `factor_inputs`. A stored 0 with no articles, or with
  a `refusal_reason`, is a refusal and is excluded.
- **Methodology.**
  - The window covers the sentiment methodology live at the first formation date. Changes to it
    start a new graded segment: the news matcher, the FinBERT revision, the window or decay, the
    failure policy.
  - **Planned before the window:** v1.6.1, with the failure policy and the pinned FinBERT. If it is
    deployed after the first formation date, it starts segment 2. **Recommended: start the window
    after v1.6.1 is deployed and frozen,** so the window opens on the methodology users will see.

## 3. Formation, timing and returns

**Formation:** the **last complete nightly cycle of each trading week.** If that cycle is incomplete,
use the week's latest complete cycle. If there is none, skip the week and record it.

**Timing.**
- The scan runs about 00:00–03:00 UTC (05:30–08:30 IST), **before** the market opens. The stored
  price is therefore taken to be the **previous** close, and the score uses news published up to the
  scan.
- To avoid crediting a reaction the market had already made:
  - **entry** is the price stored by the **next** cycle (that day's close);
  - **exit** is the price stored by the cycle 5 trading days after entry.
- **Pre-freeze check (must pass before approval):** on a sample of at least 50 stocks and 10 nights,
  confirm that `factor_history.price` equals the previous trading day's close. If it does not, the
  timing is restated before freezing, and never after.

**Returns:**
- **Prices:** the app's own stored nightly prices. No NSE and no later Yahoo fetch is needed.
- **Adjustments:** for splits and bonuses, as in the value/quality pre-registration. A move beyond
  ±50% with no recorded action is excluded.
- **Delistings:** a stock that stops being scored exits at its last stored price, with a −100%
  sensitivity.

## 4. Statistics

**Primary.** The weekly **Spearman rank IC** between the score and the next-week return across
measured stocks. The test statistic is the **mean weekly IC**.
- **Decision p:** the larger of a two-sided t-test and a two-sided Newey-West test with 4 lags.

**Secondary (reported, not used for decisions):**
- the top-fifth minus bottom-fifth weekly spread, gross and net of the frozen 0.415% round trip;
- the 1-month horizon;
- within stocks with 5 or more articles;
- within the 500 largest stocks;
- stocks with only one or two articles.

**Looks** (the whole 5% budget is for sentiment, since it is a separate pre-registration):

| Look | When | Level |
|---|---|---|
| **First** | after **52** graded weeks | **0.01** |
| **Second** | after **104** graded weeks (2 years) | **0.04** |

No other look decides anything.

## 5. Verdicts

- **Prospectively validated:** at either look, mean IC > 0, decision p below that look's level, and
  a positive gross spread.
- **Failed prospectively (reversed):** mean IC < 0 with p below the look's level.
- **Not validated:** at 104 weeks, anything else. If the mean IC is ≤ 0, the verdict is **failed
  prospectively**.
- **Costs.** A pass that does not survive costs (the net spread ≤ 0) is reported as **"predicts
  before costs only"**. With weekly turnover, this is likely.

## 6. Expectations, stated before any data

This is a rough planning estimate.
- **Assumption:** the weekly IC varies by about 0.10.
- **104 weeks:** the standard error is about 0.01, so a mean IC near 0.02–0.03 could pass at 0.04.
- **52 weeks:** the standard error is about 0.014, so passing at 0.01 needs a mean IC near 0.035.

**Known weaknesses the result inherits:**
- The live news matcher. Step-1 Google News search is still weak for some names, such as OIL and
  SBIN.
- Stocks with very few articles.
- Weekly turnover.

## 7. Integrity

The same monthly sealed export and hash as the value/quality pre-registration. It covers the
sentiment inputs and the stored headlines (`factor_input_articles`).

**Known storage gap.** Headline rows were stored for only about 47% of stocks, because of a
batch-write bug. The fix (`40c2b23`) is not yet deployed. The **score** and `n_articles` are stored
for all stocks, so the primary test is unaffected. Only the headline-level audit trail is
incomplete until the fix ships.

## 8. Relation to the historical GDELT route

They are independent.
- The GDELT test, if its matcher passes M-4, asks whether FinBERT-on-titles predicted returns in
  2019–2026.
- This test asks whether the **live app's** score predicts going forward.

Either can pass or fail without the other.

## 9. Decisions needed before approval

1. **Start the window after v1.6.1 is deployed** (recommended), or now.
2. ~~The timing check~~: done 2026-10-23, passed (section 10).
3. **The sealed monthly export** is approved (shared with value/quality).

## 10. Changes before approval

**2026-10-23: the section 3 timing check was run, and passed.**
- **Sample:** 50 stocks drawn at random (md5 order with seed `timing20261023`) × 11 nights, 2026-10-13
  to 2026-10-23, giving 550 stored prices compared with Yahoo daily closes.
- **Result:** **469** equal the previous trading day's close, and **68** equal both closes because the
  price did not change. So **537 of 550 (97.6%)** are consistent with the previous close.
- **The rest:** 1 equals the same-day close. **12 (2.2%) match neither**; all 12 are very thinly
  traded stocks (for example Consolidated Finvest, MFML, DCM), where Yahoo's closes are unreliable.
- **Conclusion:** the stored price is the previous close, so section 3's timing stands. Entry at the
  next cycle's stored price, which is that day's close, is the rule.
- **Note:** `captured_at` holds a date only, with no time, so the check used the date of the cycle.
