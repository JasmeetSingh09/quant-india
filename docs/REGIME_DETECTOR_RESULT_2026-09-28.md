# Regime detector result: it labels days, not regimes

**Run:** 2026-09-28 22:53 IST, `python research/regime_walkforward.py`.
**Rules:** `docs/PREREG_REGIME_DETECTOR_2026-09-28.md`, committed at `5853760` before the run.
**Raw output:** `docs/regime_detector_result_2026-09-28.json`.
**Data:** Nifty 50 (Yahoo), 2007-09-17 to 2026-09-25. **Days labelled:** 4,477. The app's model was refitted every day, unchanged.

## Verdict, by the pre-registered readings

| | Measure | Result | Reading |
|---|---|---|---|
| D1 | Median length of a run of one label | **1 day** (mean 1.7; 60% of runs last a single day) | Flips like a daily classifier (2 or fewer) |
| D2 | Bull days that were up days / Bear days that were down days | **99.3% / 99.4%** | The label is that day's own return |
| D3 | Chart label differs from the label shown on the day (last 90 days) | 2.2% (2 of 90) | The chart is mostly, not entirely, what users saw |
| D4 | Last day the app's download returns, run after the close on 28 Sep | **25 Sep**, while 28 Sep was available | Missing-day bug confirmed |
| H1 | Forward 20-day return, Bull minus Bear | +0.19 points, p = 0.59 | **No demonstrated value** |
| H2 | Forward 20-day volatility, Bear minus Bull | +1.3 points, p = 0.042 (level 0.025) | **No demonstrated value** |

## The benchmarks do better

| One-line rule | H1 (return), p | H2 (volatility), p |
|---|---|---|
| **Trend:** 20-day return below zero means "Bear" | -0.04 points, 0.94 | **+4.9 points, 0.0001** |
| **Volatility:** 20-day volatility above its one-year median means "Bear" | +0.36 points, 0.49 | **+3.4 points, 0.002** |
| The app's HMM | +0.19 points, 0.59 | +1.3 points, 0.042 |

- None of the three predicts returns.
- Both one-line rules flag coming volatility clearly. The HMM does not pass.

## Why

- The model fits 3 states to daily [return, |return|] with a full covariance. The states therefore split days by the sign and size of that day's move.
- The fitted "Bull" state has a median mean of **+0.99% a day** and a median probability of staying Bull of **0.45**. Those describe a single up day, not a bull market.
- The HMM is doing what it was set up to do. The setup cannot find multi-week regimes from single-day inputs.

## Exploratory (not findings)

- **Median run by sub-period:** 1 day in 2008–13, 2014–19 and 2020–26 alike.
- **H1 by sub-period:** nothing in any.
- **H2:** 2014–19 only (p < 0.001).
- **H1 at 5 and 60 days:** nothing (p 0.97 and 0.96).

## What this means in the app today

- **Dashboard banner:** "Bull ~100%" means *the last day in the model was an up day*. With the missing-day bug, that is the day before today.
- **"Regime-adaptive" optimiser:** picks Markowitz, Min-CVaR or HRP from this label, so its choice can change every day.
- **Main stock scores:** use fixed weights and are not affected. `/alpha/regime-adjusted` and the weights proposal would be.

The frozen model is not changed by this result. Fixes go to the owner as a proposal.
