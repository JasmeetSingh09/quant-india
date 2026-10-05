# Proposal v1.6.0: stop scoring low risk; its weight goes to momentum

**Date:** 2026-10-05. **Owner decision:** approved 2026-10-05 ("Drop it, give 18% to momentum").
**Scope:** the six-factor model only (`backend/modules/alpha_v2.py`). The live four-factor model,
which produces every score and ranking on the site, does not use low risk and is unchanged.

## Evidence

Factor test 1 (`docs/PREREG_FACTOR_TEST1_2026-09-13.md`) tested both price factors on 15 years of
point-in-time NSE prices. The correction re-run on repaired corporate actions
(`docs/CORRECTION_RERUN_FACTOR_TEST1_RESULT_2026-10-05.md`) gave the same verdicts.

| Factor | 1 month | 3 months | 6 months | 12 months | Verdict |
|---|---|---|---|---|---|
| Momentum | +1.57%, p 0.0001 | +4.34%, p < 0.0001 | +7.67%, p < 0.0001 | +11.44%, p < 0.0001 | Edge at every horizon |
| Low risk | +0.97%, p 0.094 | +2.45%, p 0.020 | +3.47%, p 0.015 | +3.29%, p 0.143 | No demonstrated edge (level 0.00625) |

Momentum also passed the pre-registered robustness tests (`docs/MOMENTUM_ROBUSTNESS_RESULT_2026-09-18.md`):
- in liquid stocks;
- in 2019–2026 alone;
- against IIMA's independent momentum factor, with correlation 0.80.

## The change

| Factor | Before (v2.1, six-factor) | After (v2.2) |
|---|---|---|
| Momentum | 18% | **36%** |
| Quality | 22% | 22% |
| Value | 17% | 17% |
| Growth | 15% | 15% |
| Sentiment | 10% | 10% |
| Low risk | 18% | **0%: computed and shown as risk information, not scored** |

- `MODEL_VERSION_V2` becomes `alpha-v2.2-five-factor`.
- The frozen specification records the new weights, and the app is frozen as **v1.6.0**.

## Why this option

- **Low risk has no demonstrated edge.** Scoring it puts 18% of the six-factor score on an input
  that failed its test.
- **Its weight goes to momentum,** the only factor that passed. That is also roughly the live
  four-factor model's momentum weight (35%), so the two models stop disagreeing about the one
  thing the evidence settles.
- **Low risk stays visible.** A stock's volatility and drawdown are still useful facts about risk,
  in the same way liquidity is reported beside the score without being part of it.

## What this does not claim

- **The six-factor model is not validated.** Quality, value, growth and sentiment are still
  untested on point-in-time data, and the combined score has no track record.
- **Low risk is not proven worthless.** Its point estimates were positive; the test did not show an
  edge at the pre-registered level.
- **Weights chosen after seeing a test result carry a selection risk.** Here the choice follows a
  pre-registered verdict rather than a search over weights, and no other weight moved.

## Rejected options

- **Spread the 18% evenly:** it moves weight onto factors that are themselves unproven.
- **Keep low risk and label it failed:** the panel would keep scoring an input that failed.
