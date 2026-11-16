# Proposal: count the same stocks when measuring scan completeness (2026-11-16)

**Status:** awaiting the owner's approval. Nothing is changed until then.

## The defect

Three places decide whether a nightly scan "covered the market", and they disagree about what the
market is.

| Where | Numerator | Denominator | 16 Nov result |
|---|---|---|---|
| The scan itself (`universe_scan.py:593`) | stocks scored | its own universe: the latest bhavcopy, **minus funds/ETFs (ISIN `INF…`) and `-RE` rights entitlements** (v1.5.0) | 2,509 / 2,514 = **99.8%, complete** |
| `/scan/health` (`scan_health.py:123`) | stocks scored | **every** symbol in the bhavcopy for that day, funds and ETFs included | 2,509 / 2,892 = **86.8%, not complete** |
| `/scan/cycle-audit` (`cycle_audit.py:138`) | stocks scored | the same unfiltered count | same 86.8%, so its check "marked complete matches measured coverage" fails |

The bar itself, `SCAN_COMPLETE_FRACTION = 0.90`, is the same in all three. Only the denominator
differs.

## Evidence (live `/scan/health`, read 2026-11-16 13:49 UTC)

- **0 of the 30 cycles shown reached the bar.** Every cycle since 2026-10-06 sits at 84.6–86.9%.
  The page says the collector "is NOT reliably producing daily observations", although every one of
  those scans scored 99%+ of what it set out to score.
- **The gap is about 378 symbols, the funds and ETFs.** v1.5.0 (2026-10-05) removed them from the
  scan, because company factors are meaningless for a fund: on 2026-10-04 a liquid fund was
  labelled STRONG BUY. The health check and the audit were never told.
- **The denominator is frozen at 2,892 for every cycle.** The bhavcopy archive ends on 2026-09-07,
  because NSE collection is paused. So "the universe that day" is 7 September's file for every
  cycle since. The scan uses the same file, so this does not cause the disagreement, but the page
  should say so.
- **The nightly email check is NOT affected.** It does not read `/scan/health`, and it passed
  every night from 12 to 16 Nov.

## Proposed fix

1. **One shared count.** Add a single function in `universe_scan` that returns the size of the
   scannable universe for a given day. It applies the same exclusions as the scan:
   - `EXCLUDED_ISIN_PREFIXES`;
   - `EXCLUDED_SYMBOL_PATTERN`.

   `scan_health` and `cycle_audit` call it instead of counting raw bhavcopy symbols. The three can
   then never disagree again.
2. **The bar is unchanged.** It stays at 90%, the scan's own rule is unchanged, and no score
   changes. The spec hash does not move, because `SCAN_COMPLETE_FRACTION` is untouched.
3. **Say which bhavcopy day was used.** Each cycle reports the bhavcopy day it was measured
   against, and the page notes when that day is older than the cycle because the archive stopped.
4. **Cycles before v1.5.0 are judged by the rules of their time.** Before 2026-10-05 the scan did
   score funds, so for those cycles the old, unfiltered denominator was the right one. The shared
   function applies the fund exclusion only from 2026-10-05.
5. **A test.** A suite that fails if the three completeness numbers ever differ on the same cycle.
6. **The audit timeout, separately.** `/scan/cycle-audit` timed out twice today. Its universe count
   is a `COUNT(DISTINCT symbol)` with a subquery over the 6.6M-row archive. The shared function
   would read the scan's stored universe size instead, which also fixes the timeout. It still needs
   confirming by timing after the change.

## What it affects

- Only the two reports: `/scan/health` and `/scan/cycle-audit`.
- The forward-test seals use their own completeness check, on factor_history, and are not affected.
- After the fix, the 12–16 Nov cycles should show as complete, and 11 Nov (2,344 scored, about 93%
  of the ~2,514 scannable stocks) would just pass the bar. The gap log keeps 11 Nov as a partial, after-restart cycle either way.

## Decision needed

Approve as written, or revise. Item 4 is the one judgement call. The alternative is one denominator
for all cycles, which would misjudge the pre-October cycles: they scored funds, so their numerator includes
stocks their denominator would leave out.
