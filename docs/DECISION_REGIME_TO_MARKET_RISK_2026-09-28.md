# Decision record: replace the regime label with a tested market-risk reading

**Date:** 2026-09-28. **Owner approval:** "approve 1 2 3".

## Why

On 28 September the Nifty fell 1.56% and the dashboard said "Bull ~100%". The pre-registered test (`docs/REGIME_DETECTOR_RESULT_2026-09-28.md`, 4,477 days, 2008–2026) found two problems.

**1. The label described single days, not market regimes.**
- A label lasted a median of **1 day**.
- 99.3% of Bull days were up days, and 99.4% of Bear days down days.
- It did not predict the next month's return (p = 0.59). It did not pass the plan's level on volatility either (p = 0.042 against 0.025).

**2. The app never saw the current day.** `yf.download(end=today)` leaves out the end date.

## What changes

1. **The current day is included.** `regime_detector.py` downloads up to tomorrow, so today's close is used. `/regime` is kept for anything that still reads it.
2. **Market risk replaces the label on the dashboard.** New module `market_risk.py` and endpoint `GET /market-risk`.
   - **Rule:** Elevated when the last 20 days' volatility is above its median over the last 252 trading days.
   - **Confirmation:** the rule was confirmed on four markets it was not chosen on, as pre-registered (`docs/PREREG_MARKET_RISK_SIGNAL_2026-09-28.md`). After an Elevated day, the next month's volatility was **4.6 to 6.4 points higher** on Nifty Bank, the S&P 500, the FTSE 100 and the Nikkei 225, all at p < 1e-5.
   - **Limit, shown in the app:** it does not forecast direction.
   - **Persistence:** a reading lasts a median of 6 to 9 days, against 1 day for the old label.
3. **The optimiser uses HRP.** The "Regime-Adaptive" tab is now "Risk-Aware (HRP)". It uses Hierarchical Risk Parity and shows the market-risk reading for information only. No test shows that switching optimiser on any signal helps, so nothing switches. The path `/optimizer/regime-adaptive` is kept.
4. **Wording.**
   - The dashboard banner and header chip show market risk. The HMM statistics grid is removed.
   - The landing page and glossary are updated. The glossary's regime limit now states the test result.

## What does not change

- **The v1.4.1 model:** factor formulas, weights, thresholds, signal cut-offs and stock scores. The main scores never used the regime label.
- **The frozen spec:** its hash does not cover `regime_detector` or the optimiser switch. `/strategy/drift/v1.4.1` reported `behavioural_drift: false` before the change, and must still do so after deploy.
- **Still tied to the old HMM:** `/alpha/regime-adjusted` and the `/regime/weights` proposal. Neither is shown on any page. They should be retired or rebuilt on a tested signal in a later decision.

## Tests

- `backend/tests/market_risk_test.py` (17 checks) covers:
  - the rule matches the confirmed one exactly;
  - today's close is requested, by both modules;
  - a failed download is never cached as the answer;
  - the optimiser calls HRP only.
- Added to `tests/run_ci.py`.
- The glossary test still passes: every term has a definition and a limit, and there are no promises of moves.
- The dashboard banner was checked in the browser with the day's real reading (Normal: 20-day volatility 10.2% against a typical 10.3%, as of 28 Sep including the -1.56% day), on desktop and phone widths.

## Correction noted during this work

- **The issue:** in the regime test's volatility benchmark, the first months before a full year of volatility history existed were counted as "Normal" rather than left out.
- **Effect:** it affects about the first 90 of 4,477 days. It is a benchmark, not a hypothesis, and it cannot change the HMM verdict.
- **Handling:** the confirmation run leaves those days out, as it should.
