# Pre-registration: does the regime detector detect regimes?

**Written:** 2026-09-28, before any run. **Committed before any result exists.**
Prompted by the owner: on 28 September the market fell 1.56% and the app still
said "Bull ~100%".

## What was already seen (so it is not presented as a finding later)

Before this plan was written, a read-only look at the live `/regime` showed:
- Its latest day was 25 September. `yf.download(..., end=today)` excludes the end date, so the model never sees the current day.
- In its 90-day history, the label changed almost daily and followed each day's own return. Up days were "Bull", small falls "Sideways", falls over about 0.8% "Bear".
- The fitted "Bull" state averages +0.71% a day, and Bull-to-Bull persistence is 0.47.

That is one window. The tests below measure it across 18 years.

## The detector, exactly as the app runs it

`backend/modules/regime_detector.py`:
- `GaussianHMM(n_states=3, n_iter=150, tol=1e-5)`, fitted on `[daily return, |daily return|]`;
- Nifty 50 (`^NSEI`, Yahoo, auto-adjusted) over the previous 282 calendar days;
- states named Bear, Sideways and Bull by their mean return;
- the current label is the last day's argmax posterior.

The runner imports that class and its labelling unchanged. It refits every trading day using data up to and including that day's close. That is the design as intended; the missing-day bug is measured separately in D4.

## Data

- **Series:** Nifty 50 daily closes from Yahoo, the app's own source, downloaded once for the run.
- **Labelled days:** every trading day from the first with 282 calendar days of history (mid-2008) to 25 September 2026.

## Descriptive measures (reported, with fixed readings)

| | Measure | Reading fixed now |
|---|---|---|
| D1 | Median length, in trading days, of a run of the same label (the label the app would have shown each day) | 10 days or more: behaves like a regime detector. 2 or fewer: flips like a daily classifier |
| D2 | Share of Bull days with a positive same-day return; share of Bear days with a negative one | Both 90% or more (together with D1 of 2 or fewer): the label is mostly that day's own return |
| D3 | For the last 90 trading days (the app's chart), share of days whose chart label differs from the label shown on that day | Anything above 0% means the chart is not what users saw |
| D4 | Last date in the app's own download on a day after the close | Anything before that day confirms the missing-day bug |

## Hypotheses (2 primary)

The label is read at day t's close. The outcomes are Nifty over days t+1 to t+20.

- **H1 (return):** is the mean forward 20-day return after Bull days higher than after Bear days?
- **H2 (risk):** is the forward 20-day realised volatility after Bear days higher than after Bull days?

The difference in means is estimated by regressing the outcome on Bull and Bear indicators, with Sideways as the base. The standard errors are Newey-West with 19 lags, because the windows overlap.

## Decision rule

- Significance level 0.05 / 2 = 0.025 for each hypothesis (Bonferroni).
- **Useful:** the right sign and p below 0.025.
- **Reversed:** the wrong sign and p below 0.025.
- **No demonstrated value:** anything else.

## Benchmarks (reported beside the results, not tested)

- Trend: Bull if the trailing 20-day return is positive, else Bear.
- Volatility: Bear if trailing 20-day volatility is above its trailing one-year median.

The same two regressions are run on each. The question is whether the HMM adds anything over rules a person could write in one line.

## Exploratory only (never a finding)

- The same measures by sub-period (2008–13, 2014–19, 2020–26).
- 5-day and 60-day horizons.

## Commitments

- One run. All results are reported.
- No change after the numbers are seen to the detector, window, horizons or rules.
- The frozen model (v1.4.1) is not changed by the result. The missing-day bug and any redesign go to the owner as a proposal with this evidence.
- Not tested here: whether tilting factor weights by regime improves returns. That needs the month-by-month factor spreads, which were not saved (`docs/factor_test1_pit_result.json` keeps only aggregates).
