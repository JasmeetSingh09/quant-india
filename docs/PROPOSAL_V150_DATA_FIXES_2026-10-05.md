# Proposal: v1.5.0, three data fixes in the alpha model

**Status: owner approved the fixes in principle on 2026-10-05 ("approve the ratios one and fix the
problems"). Built and tested locally; NOT deployed or frozen.** Deploying and freezing v1.5.0 each need
the owner's go-ahead, with this document in front of them.

Factor formulas, weights, signal cut-offs and portfolio rules are unchanged. What changes is which data
reaches them, and which securities are scored.

## 1. Piotroski F-score: three points no NSE stock could earn

**Evidence.**
- `metrics.piotroski_score` read total assets, equity and long-term debt only from Yahoo's `.info`.
  For NSE stocks Yahoo never supplies them (the code's own comment records this), so:
  - **F4** (cash flow beats ROA) and **F5** (low leverage) were 0 for every stock;
  - **F2** (positive operating cash flow) was 0 for almost every stock, because `.info` rarely has
    operating cash flow either.
- The balance sheet and cash-flow statement the app already downloads have all four figures.

**Fix.**
- When `.info` lacks a figure, it is read from those statements (`data_fetcher._derived_fundamentals`).
- If there is no long-term debt row, total debt is used. That can only make F5 harder to earn.
- With no debt figure at all, or negative equity, F5 is not given: unknown is never a free point.

**Measured effect** on 120 randomly chosen NSE stocks (seed 2026), old code against new:

| Piotroski check | Earned before | After |
|---|---|---|
| F2 positive operating cash flow | 4 | 82 |
| F4 cash flow / assets above ROA | 0 | 64 |
| F5 long-term debt / equity below 0.5 | 0 | 101 |

| Measure | Change |
|---|---|
| F-score | mean +2.0 (range 0 to +3); 7 of 120 unchanged |
| Quality score | mean +0.067 |
| Alpha score (quality weight 0.25) | mean +1.7 points (range 0 to +3.8) |

**What this means for labels.** On the 2026-10-04 scan (2,448 companies):
- 153 companies sit within 3.8 points below the "Top ranked" line (+15), and 67 within 1.7 points.
- 31 sit just below +40, 123 just below -15, and 23 just below -40.

Some of these will move up one label. Because almost every stock rises, rankings mostly hold; what
changes is that a strong balance sheet now counts, as the formula always intended.

## 2. Funds and ETFs were scored as if they were companies

**Evidence.**
- The scan's universe is every symbol in the exchange's daily file. 349 of 2,892 are mutual fund or
  ETF units: their ISINs start INF, while companies' start INE.
- On 2026-10-04, 292 funds were scored on company measures (P/E, ROE, Piotroski):
  - 178 were labelled NEUTRAL;
  - 100 were labelled BUY;
  - 13 were labelled SELL;
  - 1 was labelled STRONG BUY: LIQUID1, a liquid fund, which is in effect cash.

**Fix.**
- `universe_scan` leaves out ISINs starting INF (`EXCLUDED_ISIN_PREFIXES`).
- The pattern goes in as a query parameter: a literal `%` in the SQL fails on Postgres when parameters are passed.

**Effect.** About 290 fewer securities are scored and ranked each night. No company's score changes.

## 3. Sixty distress scores were recorded as computed from nothing

**Evidence.**
- The scan's own provenance audit reported DEFECT: 60 stocks whose value score had every declared
  input missing.
- A read-only query showed all 60 had a value score of exactly -0.5. That is the deliberate distress
  rule for negative earnings or negative book value, whose return value omitted the negative multiples.

**Fix.**
- The -0.5 result now records the negative P/E and P/B, `legs_used = 0`, and `valued_on = "distress: ..."`.
- **Recording only:** the score is unchanged.

## Not changed here (known, separate)

- **Piotroski F7 (no dilution)** is still given to every stock, as before. Prior-year share counts
  would be needed; that would be its own proposal.
- **EPS and book-value disagreements inside Yahoo's own data:** found by the ratio audit run on all
  2,553 stocks on 2026-10-05, and still being analysed. Any fix will be proposed separately.

## Versioning and tests

- **Version stamps:**
  - `alpha_model.MODEL_VERSION`: alpha-v5-statement-inputs;
  - `alpha_v2.MODEL_VERSION_V2`: alpha-v2.1-six-factor;
  - `universe_scan.MODEL_VERSION`: v1.5.0-statement-inputs.
- **The spec records the new rules:** `universe_rules.excluded_isin_prefixes` and
  `universe_rules.piotroski_statement_fallbacks`, so v1.5.0 has its own hash and drift against v1.4.3
  shows exactly these changes.
- **Tests:** `backend/tests/v150_fixes_test.py` (17 checks) covers every rule above, including that
  unknown debt earns no point. CI: 61 of 61 suites pass.
- **Deploy timing:**
  - deploy outside 00:02 to 03:00 UTC, while no scan is running;
  - the new MODEL_VERSION means the next nightly cycle scores every stock fresh;
  - after deploy, `/strategy/drift/v1.4.3` should show behavioural drift in `universe_rules` only;
  - then freeze v1.5.0 with this document as its notes.
