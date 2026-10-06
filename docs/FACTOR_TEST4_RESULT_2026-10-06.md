# Factor test 4 result: nearness to the 52-week high adds to momentum; short-term reversal is reversed

**Run:** once, 2026-10-06, 08:15–08:23 UTC, `GET /validation/price-signals` on production
(commit `cf9e3be`, model v1.6.0 with no drift).

**Rules:** `docs/PREREG_FACTOR_TEST4_PRICE_SIGNALS_2026-10-06.md`, approved by the owner and
committed (`be7da02`) before any code for the test existed.

**Raw output:** `docs/factor_test4_price_signals_result_2026-10-06.json`.

**Preconditions, recorded by the run:**
- The 31 duplicate split rows were withdrawn; only ALANKIT and DAAWAT remain hand-verified.
- Prices run 2011-07-04 to 2026-09-07, with 19,994 corporate actions applied (304 could not be).
- There are 171 formation months, every primary test is usable, and the level is 0.05 / 8 = **0.00625**.

## Verdicts, by the pre-registered rules

| Signal | Verdict | Passing holding periods |
|---|---|---|
| **Nearness to the 52-week high** | **Adds beyond momentum** | 3, 6 and 12 months |
| **Short-term reversal** | **Reversed** | none (significant in the wrong direction at 3, 6 and 12 months) |

## Results (momentum-neutral spread: top signal group minus bottom, with momentum held fixed)

| Signal | Holding | Neutral spread | p | t | 95% interval | Standalone (described) | First half / second half | After costs |
|---|---|---|---|---|---|---|---|---|
| 52-week high | 1 month | +0.94% | 0.0225 | 2.3 | +0.13 to +1.74 | +1.54% | +1.77 / +0.11 | +0.48% |
| 52-week high | 3 months | **+3.27%** | <0.0001 | 5.1 | +1.99 to +4.54 | +4.46% | +5.45 / +1.03 | +4.54% |
| 52-week high | 6 months | **+6.71%** | <0.0001 | 8.0 | +5.06 to +8.36 | +8.64% | +9.95 / +3.27 | +6.88% |
| 52-week high | 12 months | **+10.23%** | <0.0001 | 6.8 | +7.27 to +13.20 | +13.12% | +15.16 / +4.58 | +13.90% |
| Reversal | 1 month | -0.20% | 0.54 | -0.6 | -0.84 to +0.44 | -0.22% | -0.59 / +0.19 | -0.85% |
| Reversal | 3 months | -1.81% | 0.0008 | -3.4 | -2.87 to -0.76 | -1.94% | -2.85 / -0.75 | -5.24% |
| Reversal | 6 months | -4.46% | <0.0001 | -6.0 | -5.91 to -3.00 | -4.74% | -5.44 / -3.42 | -7.35% |
| Reversal | 12 months | -9.23% | <0.0001 | -6.3 | -12.12 to -6.34 | -9.21% | -8.92 / -9.58 | -12.50% |

**Overlap with momentum** (average monthly rank correlation): 52-week high 0.55; reversal -0.05.

## Reading

### Nearness to the 52-week high
- **It is not just momentum leaking through.** Before the run, synthetic prices where returns
  depend on momentum alone gave this signal t of about 1.0–2.5 in the neutral sort. The real
  t values at 3, 6 and 12 months are 5.1, 8.0 and 6.8, far above that.
- **It meets all three conditions the prereg sets for a proposal** at 3, 6 and 12 months:
  1. it passes the decision rule;
  2. it is positive in both halves of the sample;
  3. it is positive after costs.
- **It is much weaker in the second half (2019–2026) than in the first.** At 3 months the
  spread is +5.45% in the first half and +1.03% in the second.
- **At 1 month it does not pass** (p 0.0225 against 0.00625).

### Short-term reversal
- **It points the wrong way.** Stocks that fell most over the last month go on to *underperform*
  over 3–12 months, even with momentum held fixed. Over those horizons, the last month behaves
  like more momentum, not like a bounce.
- **It must not be added to the model as a reversal signal.**
- **A question for later, not a finding:** whether the month that momentum's 12-1 window skips
  carries information. Answering it would be a separate pre-registered test.

## What this does and does not change

- **v1.6.0 is unchanged.** A pass permits a written proposal; it does not change the model.
- **Any proposal to add nearness to the 52-week high** (at 3–12 month horizons) is the owner's
  decision. It should state:
  - the weaker second half;
  - the 0.55 overlap with momentum;
  - that the app's score is used at a 21-day horizon, where this signal did **not** pass.
- **Reversal is closed.** It was tested, and it is reversed.
