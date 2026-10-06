# Proposal v1.7.0: show nearness to the 52-week high as a tested 3–12 month signal

**Date:** 2026-10-06. **Status: PROPOSAL, awaiting the owner's decision.** Nothing is built
until the owner approves an option below. The model stays at v1.6.0 until then.

## The evidence

Factor test 4 (`docs/PREREG_FACTOR_TEST4_PRICE_SIGNALS_2026-10-06.md`, result
`docs/FACTOR_TEST4_RESULT_2026-10-06.md`) was pre-registered, approved and committed before any
code existed, and run once on 15 years of adjusted NSE prices. It asked whether stocks near their
52-week high beat stocks **with the same momentum** that are far from it.

| Holding | Extra return (top fifth minus bottom fifth, momentum held fixed) | p | Verdict |
|---|---|---|---|
| 1 month | +0.94% | 0.0225 | **does not pass** (line 0.00625) |
| 3 months | +3.27% | <0.0001 | passes |
| 6 months | +6.71% | <0.0001 | passes |
| 12 months | +10.23% | <0.0001 | passes |

At 3, 6 and 12 months it meets all three conditions the plan set before the run:
- it passes;
- it is positive in both halves of the sample;
- it is positive after trading costs.

A check run before the real test showed that momentum alone could not produce t values this large.

## What the evidence does not support

1. **Adding it to the main score.** The app's score and ranking work on a 21-day horizon, and at
   1 month the signal did not pass. Putting it into the 21-day score would claim something the
   test did not show.
2. **Treating it as a per-stock forecast.** The test measured averages of groups of about 150+
   stocks a month. Any one stock near its high can still fall.
3. **Assuming the effect is as large now as on average.** It was much stronger in 2011–2018 than
   in 2019–2026:
   - 3 months: +5.45% in the first half, +1.03% in the second;
   - 12 months: +15.16% in the first half, +4.58% in the second.
4. **Treating it as independent of momentum.** Its overlap with momentum is 0.55 (rank
   correlation). The test shows it adds information *beyond* momentum, not that it is unrelated
   to it.

## Options

### A. A separate "longer-term signal" card on the stock page, outside the score (recommended)

- **What it shows**, per stock:
  - nearness to the 52-week high, computed exactly as the test did (latest close divided by the
    highest close of the last 252 trading days, closes not intraday highs, at least 200 valid
    closes);
  - which fifth the stock is in **among stocks with similar momentum**, from the nightly scan,
    using the same momentum-neutral grouping as the test.
- **Wording.** The card states the horizon (3–12 months), the test result with its link, the
  1-month failure and the weaker recent half. It says it is not part of the score, the same way
  liquidity and low risk are shown beside the score, not in it.
- **What changes:** nothing in any score, ranking or Buy/Sell label.
- **Version:** v1.7.0 records the new reported signal and its definition in the frozen
  specification, so drift checks cover it.
- **Work:**
  - the nightly scan computes nearness and the momentum-neutral fifth (it already computes momentum);
  - a stock-page card;
  - tests: same definition as the test, no look-ahead, and fifths matching on a fixed fixture;
  - deploy and freeze. About half a day.

### B. A separate 3–12 month ranking: momentum plus nearness to the 52-week high

- **What it would be:** a second ranking for longer holding periods.
- **Why not now:** it needs weights for the two signals. The test validated the signal beyond
  momentum, not any combined score, so any weights would be untested. A combined ranking needs
  its own pre-registered test first. That is possible later, on the same price archive, in
  about a day.

### C. Add it to the 21-day score (not recommended)

It did not pass at 1 month. Rejected on the evidence.

### D. Do nothing

Keep the finding in the research record only.

## Recommendation

**Option A.** It shows users a signal that passed a pre-registered test, at the horizon where it
passed, with its limits stated, and it leaves every score unchanged. Option B can follow later if
the owner wants a longer-horizon ranking, after its own test.

## Live data is not the test data

- The app's live prices come from the nightly scan's sources.
- The test used exchange prints adjusted for corporate actions.
- Option A uses closes adjusted the same way the stock page's price history already is.
- Because a stock's fifth is computed within the scanned universe each night, small differences
  in price source move a few stocks between neighbouring fifths. They do not change the
  definition. The card will name its price source.

## Monitoring after release

- Each night's nearness and fifth are recorded per stock (`factor_history`, which already stores
  dated factor readings).
- After 12 months of live data, the live top-fifth minus bottom-fifth spread can be compared with
  the test's.
- That comparison is description, not a new test, unless the owner pre-registers one.

## Decision needed

Approve one of **A**, **B (pre-register a combined test first)** or **D**. Option C is not offered
for approval because it contradicts the test result.
