# Pre-registration: confirm the "market risk" rule on markets it was not chosen on

**Written:** 2026-09-28, before any run. **Owner approval:** "approve 1 2 3" (2026-09-28): (1) include the current day, (2) replace the regime label with a tested market-risk signal, (3) the optimiser uses HRP until then.

## Why a confirmation

The regime test (`docs/REGIME_DETECTOR_RESULT_2026-09-28.md`) found that the app's HMM labels single days. A one-line volatility rule flagged coming volatility on the Nifty (p = 0.002), and a trend rule did too (p = 0.0001).

That rule was one of two benchmarks, and it is being picked after its Nifty result was seen. So before the app shows it, it must work on markets that played no part in choosing it.

- **Nifty Bank:** a different index.
- **S&P 500, FTSE 100 and Nikkei 225:** other countries.

The Sensex is not used: it moves almost exactly with the Nifty, so it would not be a second test.

## The rule, fixed now (as run on the Nifty)

- vol20 = standard deviation of the last 20 daily returns.
- **Elevated** if vol20 is above the median of vol20 over the last 252 trading days; otherwise **Normal**.
- Computed at day t's close from data up to t.

It was chosen over the trend rule because it measures risk directly, which is what the label is for. The trend rule is also reported, as a comparison only.

## Hypotheses (4 primary, one per market)

- **The question:** is forward 20-day realised volatility (days t+1 to t+20) higher after Elevated days than after Normal days?
- **Estimate:** regression on an Elevated indicator, with Newey-West standard errors (19 lags).
- **Data:** Yahoo daily closes for `^NSEBANK`, `^GSPC`, `^FTSE` and `^N225`, from the first date with a full year of history to 2026-09-25.

## Decision rule

- Significance level 0.05 / 4 = 0.0125 per market (Bonferroni).
- **Confirmed:** at least 3 of the 4 markets show a positive difference with p below 0.0125. The app may then show the signal.
- **Not confirmed:** anything else. The app shows no regime or risk label, only a plain note.

## Reported, not tested

- The forward 20-day return difference.
- How long a label lasts (median run), on the four markets and on the Nifty.
- The trend rule, same measures.

## Commitments

- One run. No change to the rule, window, horizon or thresholds after the numbers are seen.
- If the signal flickers (short runs), that is reported. Smoothing it would be a new rule and needs its own test.
- What the app says, if confirmed: "Market risk: elevated / normal. Recent volatility is above / below its one-year typical level. Elevated periods have tended to stay volatile over the next month. It does not forecast direction."
