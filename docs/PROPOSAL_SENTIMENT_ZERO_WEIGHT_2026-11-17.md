# Proposal: a stock whose only headlines are years old gets "no recent news", not an empty score (2026-11-17)

**Status:** awaiting the owner's approval. Nothing is changed. This changes model behaviour for a
handful of stocks, so if approved it ships as a new version (v1.6.2) with its own freeze.

## The defect

Most nights, one to three stocks are stored with **no alpha score and no error**, labelled
NEUTRAL. Their factor-history row has an empty score and is still promoted to research-grade.

- **Production count:** 36 rows across 13 stocks in `alpha_scan2`. Examples: NCLIND, AMDIND,
  MPSLTD, BHARATWIRE, GRPLTD, SHIVAAGRO. Seen since at least 2026-10-20.
- **What they share:** the other three factors (momentum, quality, value) are normal, and
  **sentiment is NaN**. One NaN factor makes the whole composite NaN. `_sanitize` then turns the
  NaN into NULL, and `signal_for_score(NaN)` falls through to NEUTRAL, because every comparison
  with NaN is false.

## Root cause (`alpha_model._compute_sentiment_factor`)

On 16 Nov, the stored headlines for NCLIND and AMDIND were stock-chart pages dated **July and
December 2017**, for example "NCLIND Stock Price and Chart — NSE:NCLIND". Three things then go
wrong in turn:

1. **The news source ignores the 14-day window.** `get_stock_news(ticker, days_back=14)` still
   returns those pages.
2. **Each headline's weight becomes 0.** The weight is `exp(-ln2 / 3 * age_days)`. A headline
   3,200+ days old underflows to exactly 0.0, and is stored with weight 0.
3. **The average is 0 / 0.** `sum(weighted_scores) / sum(weights)` divides two numpy zeros, so it
   returns NaN instead of raising. The later `* confidence` (0) leaves it NaN.

## Proposed fix

1. **The zero-weight case.** If the headlines' total weight is zero, or too small to carry any
   evidence, return what the factor already returns when nothing can be scored:
   `score 0.0, confidence 0.0, reason "no recent headlines"`. The headlines are still stored.
   These stocks then get a real composite score built from the other three factors, exactly like a
   stock with no news today.
2. **A guard.** If the composite is ever not a finite number, `compute_alpha_score` returns an
   **error** ("no score produced: a factor was not a number"). The row is then a failure: never
   NEUTRAL, never promoted to research-grade.
3. **Not changed here:** the news source returning 2017 pages for a 14-day request. Enforcing the
   window in the fetcher is a separate, larger change to what sentiment sees, so it would need its
   own proposal.
4. **Tests.** Headlines all decades old give a score of 0 with reason "no recent headlines", never
   NaN. A forced NaN factor gives an error row, not a NEUTRAL one.

## What it affects

- **The ~13 affected stocks** get scores, where today they have none. No other stock's score
  changes, because the new branch only runs when total weight is zero.
- **The stored NULL rows are left as they are.** They are history. The forward tests should
  exclude rows with an empty score; that rule belongs in each pre-registration.
- **This is a behaviour change, so it ships as v1.6.2** with a freeze, after a deploy you approve.

## Decision needed

Approve items 1, 2 and 4 as written; item 3 is out of scope. Or approve item 2 alone: those
stocks would then be recorded as failures, with no score change for anyone. That stops the bad
rows without changing the model.
