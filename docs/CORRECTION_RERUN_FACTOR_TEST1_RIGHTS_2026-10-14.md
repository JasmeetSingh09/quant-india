# Correction re-run plan: factor test 1 with rights issues adjusted

**Written 2026-10-14, before the re-run.** Owner approval: "approve rights fix" (2026-10-14).
This closes open defect 3 in `docs/HAND_CHECK_SPLITS_2026-10-05.md`.

## Why

**The problem.** The exchange feed holds 322 rights-issue lines and none of them adjusted a price.
A rights issue sold below the market lowers the share price on the ex-date. The backtest read that
mechanical drop as a real loss.

**How big it is.** Measured on production (`bhavcopy_eod` and `corporate_actions`, read-only):
- 287 lines have a ratio, a premium and a prior close.
- On 184 of them the theoretical drop exceeds 5%; on 62 it exceeds 20%.
- The median gap between the expected and the printed ex-day price is 6.7% with no adjustment.
  With the adjustment it is about 3%.

## The rule

**The formula.** A rights issue of A new shares for every B held, at issue price S, with prior
close P, scales earlier prices by (B·P + A·S) / ((A+B)·P). This is the theoretical ex-rights price
divided by P.

**Issue price.** The issue price is the premium plus the face value. The feed prints only the
premium. The face value is found in one of two ways:
- From the exchange's own split lines, when the company has one. That covers 80 of 322 events.
  Yahoo and hand-added rows are not used, because they hold share factors, not face values.
- Otherwise it is assumed to be Rs 10. This is the commonest face value and the highest usual one,
  so the drop is under-corrected, never over-corrected.

**Edge cases:**
- An issue priced at or above the prior close moves nothing.
- Some lines are not adjusted and stay unparsed: rights in debentures, CCPS or with warrants,
  two-tranche lines, and lines with no price. There are 11 such lines.
- Partly paid rights use the full issue price.

**Side fix.** Three lines carry a dividend and a rights issue together (HATSUN 2018, KESORAMIND 2013,
LAKSHVILAS 2014). The old parser dropped their dividends; they are now read.

## Order of steps

1. **Deploy the code.** It changes nothing on its own, because no row is of kind `rights` yet.
2. **Re-parse dry run** (read-only). Expected:
   - ADD: about 310 rights and 3 dividends.
   - CONFLICT: 0.
   - DROP: 0.

   Any CONFLICT or DROP stops the run.
3. **Re-parse apply** (`confirm=APPLY-REPARSE`). This is additive only: inserts with
   ON CONFLICT DO NOTHING, and rows that already exist are fingerprinted before and after.
4. **Re-run factor test 1, unchanged.** Same request as before:
   `GET /validation/pit?min_turnover=10000000&buckets=5`. Same rules:
   `docs/PREREG_FACTOR_TEST1_2026-09-13.md`, significance level 0.00625.

## What is reported

- **Results side by side:** the second correction re-run (2026-10-05 19:33) and this one, plus
  the adjustment counts, including rights applied and their face-value source.
- **Verdict changes:** if any verdict changes, it is reported plainly, and nothing else is changed
  to restore it.
- **Assumed face value:** the Rs 10 assumption is a known approximation, stated alongside the
  result.
