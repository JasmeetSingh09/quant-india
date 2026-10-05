# Correction re-run plan: factor test 1 on repaired corporate-action data

**Written 2026-10-05, before the re-run.** Owner approval: "yes approve all six" (fix 2 in
`docs/INTEGRITY_REVIEW_2026-10-05.md`).

## Why

Factor test 1 (`docs/FACTOR_TEST1_RESULT_2026-09-13.md`) is the project's one passed test: momentum
demonstrated an edge at all four holding periods. The 2026-10-05 integrity review found corporate
actions that the price adjustment silently dropped or never had. Each one leaves a fake crash in the
adjusted prices that the test read as a real return:

1. **Actions filed under an ISIN with no prices** (9 splits, 17 bonuses, 909 dividends), e.g. Kotak's
   2026 split and Britannia's 2018 split. Fixed in code (commit 39b7bdc): such actions go to the ISIN
   their symbol traded under.
2. **Actions the old parser did not read** (8 splits, 2 consolidations), e.g. Asian Paints 2013 and
   SBI 2014. Recovered by the existing additive re-parse.
3. **Splits missing from the data entirely.** 14 are added from Yahoo, only where Yahoo's factor
   matched the price jump within 10% (e.g. JSW Steel 2017, United Spirits 2018). The rest go on a
   hand-check list.

## What is re-run, unchanged

- **The same request:** `GET /validation/pit?min_turnover=10000000&buckets=5` on production.
- **The same rules:** `docs/PREREG_FACTOR_TEST1_2026-09-13.md`, with significance level
  0.05 / 8 = 0.00625.
- **The same code** for scoring, bucketing and statistics. The only difference is which corporate
  actions reach the price adjustment.

## What is reported

- **Both results, side by side:** the original (2026-09-13) and the corrected one.
- **The adjustment counts:** actions applied, applied via symbol, and unapplied.
- **The original stays the record of what was run on 2026-09-13.** The corrected result is added as
  a dated correction; neither is deleted or edited.
- **Whichever way it goes:** if a verdict changes (a horizon that passed no longer passes, or the
  reverse), that is reported plainly. Nothing else changes to restore it.
- **The 46 suspected splits not yet verified remain a known gap.** The result says so. When they are
  verified by hand, the run is repeated under this same plan.
