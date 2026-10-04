# Pre-registration: a Markov-switching market regime

**Status: IN FORCE from its commit, 2026-10-05.** Approved by the owner ("approved", 2026-10-05) and by
Jasmeet (confirmed by the owner, 2026-10-05). Nothing in it changes from here on. When it was approved:
- no model in it had been fitted to the Nifty or any other market;
- no outcome after any signal date had been looked at;
- the runner's plumbing check had run, on simulated data only (see Commitments).

**Owner's choice (2026-10-05):** of three candidates offered (a statistical jump model, a
Markov-switching model, and a trend-plus-volatility rule), the owner chose the Markov-switching
model. Choosing one model before the test means it is the only primary model, so it pays no
multiple-testing penalty. The other candidates may get their own tests later; this one cannot ship them.

## Why

The app's current regime detector (a 3-state HMM on daily returns) failed its pre-registered test
(`docs/REGIME_DETECTOR_RESULT_2026-09-28.md`):
- its median regime lasts 1 day;
- its Bull/Bear label agrees with the same day's up/down move 99% of the time;
- it showed no predictive value.

It is not shown in the app. Its routes are retired whatever this test finds.

What can honestly be predicted is risk, not direction: volatility clusters. The market-risk reading
(`docs/PREREG_MARKET_RISK_SIGNAL_2026-09-28.md`, confirmed on four markets) already uses that.
This test asks whether a standard regime model, Hamilton's Markov-switching model, gives a regime
that lasts and that warns of rougher months ahead.

## The model, fixed now

- **Data:** Nifty 50 (`^NSEI`) daily closes from Yahoo, 2007-09-17 (first date available) to
  2026-09-30. Weekly log returns in percent, from Friday closes (or the last trading day of the week).
- **Model:** `statsmodels` `MarkovRegression`, 2 regimes, a switching constant (mean) and switching
  variance (`k_regimes=2, trend="c", switching_variance=True`), fitted by maximum likelihood with
  `search_reps=20` and a fixed random seed of 2026, to avoid a poor local optimum.
- **Labels:** in every fit, the regime with the higher variance is **High-risk** and the other is
  **Low-risk**. This rule is fixed, so the label never depends on which number the fit gives a state.
- **Walk-forward, no look-ahead:**
  - At each month-end the model is refitted on all weeks up to that date (expanding window, at
    least 260 weeks, so the first signal is at the end of September 2012).
  - The signal is the **filtered** probability of High-risk in the last week ending on or before
    the month-end. Smoothed probabilities use later data and are never used.
  - The month is **High-risk** if that probability is above 0.5, otherwise **Low-risk**.
- **Outcomes, over the next calendar month (daily closes):**
  - realised volatility: standard deviation of daily log returns, times the square root of 252;
  - maximum drawdown: the largest fall from a running peak, starting from the month-end close;
  - return: the month's price return (reported only, see below).

## Hypotheses

**Primary (2), on the Nifty, from the October 2012 to September 2026 signals:**
- **P1:** next-month realised volatility is higher after High-risk months than after Low-risk months.
- **P2:** next-month maximum drawdown is deeper after High-risk months.

Each is estimated by regressing the outcome on a High-risk indicator, with Newey-West standard errors
(3 lags), because volatility persists from one month to the next.

**Secondary (reported, never a basis for shipping on their own):**
- **S1, does it add anything?** P1's regression with the market-risk reading (Elevated at the same
  month-end) added. Reported: the Markov-switching coefficient and its p-value.
- **S2, direction:** next-month return after High-risk vs Low-risk months. Expected to show nothing;
  reported either way.

## Decision rule

1. **Persistence gate.** The median length of a regime spell must be at least 4 weeks:
   - in the month-end walk-forward signals;
   - and in the weekly filtered states of the final fit.

   A model that flickers fails here, as the old one would have, whatever P1 and P2 say.
2. **Primary:** a significance level of 0.05 / 2 = 0.025 each (Bonferroni). **Passed** means P1 has
   a positive difference with p below 0.025. P2 is reported with its own verdict.
3. **Confirmation, required to ship.** If P1 passes on the Nifty, the identical code is run on Nifty
   Bank (`^NSEBANK`), S&P 500 (`^GSPC`), FTSE 100 (`^FTSE`) and Nikkei 225 (`^N225`), over each
   market's history to 2026-09-30. It must show a positive P1 difference at p below 0.0125
   (0.05 / 4) in at least 3 of the 4 markets.
4. **Ship only if 1, 2 and 3 all pass.** S1 then decides the wording:
   - if it adds information beyond the market-risk reading, the page says so;
   - if not, the page says it agrees with the market-risk reading and adds nothing new.
5. **Otherwise:** not shipped. The app keeps the market-risk reading, and the result is published as
   a finding. "A standard regime model did not beat a one-line volatility rule" is a result, not a failure to hide.

## What the app may say, if it ships

> "Market regime (Markov-switching model): High-risk, probability 78%, for the last 5 weeks.
> Months that started in this state have historically been rougher than usual: higher volatility and
> deeper falls. It does not forecast whether the market goes up or down."

The numbers are the live values. It never says Bull or Bear, and never anything about direction
unless a later pre-registered test supports it.

## Reported, not tested

- The market-risk reading and a trend rule (Nifty against its 200-day average with a 2% buffer)
  scored on the same months and outcomes, as comparisons.
- The fitted means, variances and switching probabilities, and how much they move across refits.
- The number of fits that did not converge, and how each was handled. A non-converged fit gives no
  signal for that month; the month is dropped and counted.

## Commitments

- **Plumbing check first:** the runner (`research/markov_regime_test.py`) must recover the regimes of
  a simulated two-regime series with known switch dates before it touches real data. That check is
  committed with its result.
  - Done 2026-10-05: `docs/markov_regime_plumbing_2026-10-05.json`. Three of its four checks passed.
  - It recovered the parameters, detected the effect strongly, and gave no false signal on three series
    without regimes.
  - It missed the runner's own 80% weekly-state accuracy bar, at 78.4%. That bar was not in this
    pre-registration and was not changed.
  - The diagnosis: the real-time (filtered) state confirms a switch about 3 weeks late. Even
    hindsight states reach only 86% on that data.
  - The owner accepted the plumbing on that basis.
- **Order:** the runner is committed before it is run on the Nifty. One run.
- **Fixed after approval:** no change to the model, data, labels, threshold, window, outcomes,
  horizons, lags or decision rule once the numbers are seen.
- **Reruns:** a technical failure is rerun once with identical settings, and recorded.
- **The frozen model (v1.4.3) is not changed by this test.** Using a regime to adjust factor
  weights would need its own test, a written proposal and a new version (AGENTS.md rule 3).
- **Old routes go regardless of the result:** the old HMM's routes (`/regime/weights`,
  `/alpha/regime-adjusted`) and its advice text are retired.
