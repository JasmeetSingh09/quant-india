# Result: the Markov-switching market regime

**Run:** 2026-10-05, once, by `research/markov_regime_test.py` at commit f273dd7, under
`docs/PREREG_MARKOV_SWITCHING_REGIME_2026-10-05.md`. Numbers: `docs/markov_regime_result_2026-10-05.json`;
every month: `docs/markov_regime_months_2026-10-05.csv`.

## Verdict: not shipped

| Rule | Needed | Result |
|---|---|---|
| Persistence gate | median spell of at least 4 weeks | **passed**: 19 weeks (weekly states), 30 weeks (monthly signals) |
| P1, next-month volatility | positive, p below 0.025 | **not passed**: +22.5 points, p = 0.0254 |
| P2, next-month drawdown | positive, p below 0.025 | **not passed**: +6.5 points, p = 0.0995 |
| Confirmation on 4 other markets | at least 3 of 4 | **not run**: the rules run it only if P1 passes |

P1 missed by 0.0004. Under the rules that is a miss, and it is reported as one. No threshold, lag or
model setting has been or will be changed to turn it into a pass.

## What happened

- **Persistence:** the model holds a state for months, unlike the old HMM (1 day). That part works.
- **High-risk is rare:** in 168 months (September 2012 to August 2026) it called High-risk in only 6.
  - Five were February to June 2020 (COVID); the sixth was February 2021.
  - Months after a High-risk call averaged 35.9% annualised volatility and a 10.1% drawdown.
  - Months after a Low-risk call averaged 13.4% and 3.6%.
- **One episode, not a pattern:** the difference is large but rests almost entirely on a single
  episode, which is why the p-value sits at the edge and not well below it. One crash is not enough
  evidence that the model warns of rough months in general.
- **Direction (S2):** no relation to next-month returns (p = 0.97), as expected.
- **Beyond the market-risk reading (S1):** with the market-risk state in the same regression, the
  Markov coefficient is +20.3 (p = 0.044) and market risk's is +4.2 (p < 0.0001). Secondary, and
  not a basis for shipping.

## Comparisons (reported, not tested here)

Same 168 months, same outcomes:

| Signal | Next-month volatility | Next-month drawdown |
|---|---|---|
| Market-risk reading (already confirmed on 4 markets) | +5.6 points, p = 0.0002 | +1.5 points, p = 0.005 |
| Trend rule (200-day average, 2% buffer) | +4.6, p = 0.081 | +1.1, p = 0.19 |
| Markov-switching (this test) | +22.5, p = 0.025 | +6.5, p = 0.10 |

The one-line volatility rule, which is already in the app and was confirmed beforehand on other
markets, carries much stronger evidence. It flags smaller differences, but far more often.

## What follows

- **The app:**
  - The Markov-switching regime is not shown.
  - The market-risk reading stays as the app's tested regime signal.
  - The old HMM's routes are retired, as the pre-registration commits to whatever the result.
- **Wording, if the regime idea is mentioned anywhere:** "A standard Markov-switching model held
  stable regimes but called High-risk almost only during the 2020 crash; that was not enough
  evidence to show it, so the app uses the simpler, tested market-risk reading."
- **Further tests:** a new regime model (for example the statistical jump model) would need its own
  pre-registration. It may not be tuned against this result.
