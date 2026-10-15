# Pre-registration DRAFT (revision 2): factor test 5, momentum net of trading costs

**Status: DRAFT, awaiting owner approval. Nothing has been run.** No harness exists, and no new
number has been computed for this document.

**When it becomes binding:**
1. The owner approves this text.
2. It is committed, and its file hash is recorded in the harness commit.
3. That harness commit precedes the single run.

Every edit made before approval is listed in section 14. After approval, sections 3–12 do not
change.

**Model:** unchanged. The frozen spec is v1.6.0, hash `54ced1e2c8af0a77`. This test reads the
frozen momentum code. It changes no weight, threshold, label or scoring rule.

**Authorisation for the run** (owner, 2026-10-15):
- mode **L**: local and read-only;
- no production run, no deployment, no production write.

---

## 1. Question

After Indian delivery-trading costs, does a long-only, equal-weight, monthly-rebalanced portfolio
of the **top fifth of stocks by the frozen v1.6.0 momentum score** beat an equal-weight portfolio of
all eligible stocks? Both portfolios have their own turnover charged at the same cost schedule.

The objective is to measure whether the reported gross edge survives costs, and what claim the
evidence supports. It is **not** to obtain a pass.

## 2. What has already been seen

These results were seen before this was written. This test is **not** independent of them.

**Factor test 1** (`FACTOR_TEST1_RESULT_2026-09-13.md`; re-run twice after data corrections, with
the verdict unchanged):
- The gross 1-month top-minus-bottom spread is about +1.5% a month, p ≤ 0.0001.
- The top-fifth portfolio was described net of 0.4% round-trip costs: 23.8% a year, volatility
  22.3%, worst fall −38.7%.
- **Liquidity thirds (exploratory):** most of the edge sits in the less liquid two thirds. The most
  liquid third showed +0.30% a month, p 0.25.

**Frozen v1.0 backtest** (`RELEASE_NOTES_v1.4.1.md`, `pit_backtest.run`): +0.693% a month over a
cost-free eligible universe, after 0.4% costs, p 0.0004. That test used the raw 12-1 return, not
v1.6.0's volatility-adjusted score.

**Therefore:**
- Any result on 2011–2026 is labelled **historical, partly seen**.
- New calculations on that period (costs on both sides, drift-aware turnover, the liquid-only
  result, the break-even cost) **add** evidence. They are **not** independent confirmation, however
  they turn out.
- Stronger claims are reserved for the prospective window (section 12). Its rules are fixed now,
  before its data exist.

## 3. Signal (read from frozen code, not restated)

The score is `pit_validation._momentum_scores(C, col)`, unchanged:
- **Window:** the return from 252 trading days before formation to 21 days before.
- **Scaling:** that return is divided by annualised daily volatility over the window (`np.nanstd`,
  ddof 0), then put through tanh(÷1.5).

**What this means for the test:**
- Portfolios use rank order only, and tanh does not change rank.
- The live factor's ddof 1 ranks identically wherever a stock has the full 231-return window. This
  is D-07, recorded and not changed.
- **Missing values, as the code does them:**
  - If the close at either window end is missing, the score is missing, and the stock is not
    eligible.
  - Missing days inside the window are skipped by `nanstd`.
  - A volatility of 1e-6 or below gives a score of 0. The stock stays eligible, and the run reports
    how many such cases there are.
- The signal uses only closes up to 21 trading days before formation.

## 4. Data

The loader is `pit_validation.load_adjusted`, unchanged.

**Closes:**
- NSE end-of-day closes from `bhavcopy_eod`.
- Adjusted for splits, bonuses, dividends and rights, from the stored corporate actions.
- Joined across ticker changes by ISIN identity resolution.

**Traded value:**
- Printed close × printed volume for that day.
- Not adjusted.
- A null volume counts as 0.

**Range:**
- The stored archive is 2011-07-04 to 2026-09-07 (3,744 days, checked 2026-10-15).
- The harness records the first and last day it actually reads, and refuses to run if the archive
  has changed from those figures without this text being amended first.
- No other price source is read. Yahoo is used only for the labelled Nifty price reference
  (section 8).

## 5. Formation, eligibility and execution (frozen)

**Formation dates:**
- The **last stored trading day of each calendar month** in the archive (`_month_end_cols`). It is
  one date for the whole market.
- The harness writes the full list of formation dates into the output.
- The first formation month is the first with a full 252-day lookback.
- The last is **2026-07**, held to the 2026-08 formation date. The archive stops on 2026-09-07, so
  any hold month ending in September 2026 is excluded.

**Eligibility, at each formation date.** A stock is eligible only if all three hold:
1. it has a finite, positive close **on that exact day** (a stock with no row that day is not
   eligible, even if it traded the day before);
2. its momentum score is finite;
3. **its traded value on that single day (printed close × printed volume) is at least the floor:**
   Rs 1 crore (1e7) for H1, Rs 10 crore (1e8) for H2.

The floor is **not** monthly traded value. Earlier documents describe it as monthly; they are
wrong, and the code has always used the single formation day.

**Timing disclosure.** The formation day's volume is fully known only at that day's close, which is
when the trade is assumed to execute. This is the rule as implemented, and it is kept. Section 10
item 4 reports the same test with eligibility on the **previous trading day's** traded value, which
was fully known beforehand.

**Thin months:**
- A month with fewer than **50** eligible stocks is skipped, and the skip is recorded.
- Stocks are ranked within the month. The **top fifth** is `pit_validation`'s top bucket: a stable
  ascending sort, with label = min(4, ⌊rank × 5 ÷ n⌋).

**Execution and holding:**
- Trades happen at the **formation-day close**, using adjusted closes for returns.
- Each position is held to the **next formation date's close**.
- The holding period is **one month**. Hold periods do not overlap, and no 3-, 6- or 12-month
  horizon is part of this test.

**Missing close at the end of a hold:**
- A held stock with no close on the next formation date is marked to **−100%**, as both frozen
  studies do. It drifts to zero weight, and no sale cost is charged.
- The run reports how many such cases there are, and how many of those stocks have a close again
  within the following 21 trading days. Those are non-trading days, not delistings. This is
  description only, and the −100% rule is not changed.

## 6. Portfolios and turnover (the same rules for both portfolios)

There are two portfolios:
- **S (strategy):** the eligible top fifth, equal-weighted.
- **B (benchmark):** every eligible stock, equal-weighted.

Both are rebalanced to equal weight on every formation date.

**Turnover:**
- For each portfolio, let w_drift be the old weights after the month's returns. They are
  renormalised to the surviving value, and a −100% holding has weight 0.
- Let w_target be the new equal weights.
- **Buys** = Σ max(w_target − w_drift, 0). **Sells** = Σ max(w_drift − w_target, 0).
- Both are fractions of portfolio value, summed over the union of old and new holdings.
- **One-way turnover** T = ½ × (buys + sells).
- **First formation month:** buys = 1, sells = 0.
- There is no final liquidation.
- **Legacy turnover**, |cur △ prev| ÷ (2 × |cur|), is reported for S only, for reconciliation
  (section 10).

## 7. Cost model (one definition, fixed now)

**Rule used to choose it.** The primary cost is the project's **frozen trading-cost total, 0.415%
for a round trip** (`PHASE0_V1_METHODOLOGY_2026-09-14.md`). That number was fixed before this test
existed. It is read as a **round trip**: one buy plus one sell of the same value.

The alternative reading, "0.415% per side", equals 0.83% a round trip. It is reported, as the 2×
case in section 10. **Neither reading was chosen by its result.**

**Itemised per side.** The statutory and broker items are `execution.py`'s published rates. The
spread-and-impact allowance is the remainder of the frozen 0.415% total, split equally between the
two sides.

| Item (fraction of trade value) | Buy | Sell |
|---|---|---|
| Brokerage (`BROKERAGE_PCT`) | 0.0300% | 0.0300% |
| STT, delivery (`STT_PCT`; delivery STT is charged on both sides) | 0.1000% | 0.1000% |
| Stamp duty (`STAMP_DUTY_PCT`; buy only) | 0.0150% | — |
| Exchange transaction charge (`EXCHANGE_PCT`) | 0.00345% | 0.00345% |
| SEBI fee (`SEBI_PCT`) | 0.0001% | 0.0001% |
| GST 18% on brokerage + exchange (as `execution.py`) | 0.006021% | 0.006021% |
| **Statutory and broker subtotal** | **0.154571%** | **0.139571%** |
| Spread and impact allowance (remainder of 0.415%, halved) | 0.060429% | 0.060429% |
| **Total per side** | **0.215000%** | **0.200000%** |

Round trip: 0.215% + 0.200% = **0.415%**.

**Charge per formation date,** for each portfolio separately: cost = buys × 0.215% + sells × 0.200%.
This cost is subtracted from that portfolio's return for the hold month.

**Stated limits:**
- **One schedule for the whole of 2011–2026.** Historical rates are not reconstructed. Stamp duty,
  for example, varied by state before July 2020, and exchange charges have changed.
- **The spread-and-impact allowance is an assumption, not a measurement.** No bid-ask or order-book
  history exists here. Thinly traded stocks probably cost more than this.
- The cost multiples (section 10) and the break-even multiple (section 9) carry that uncertainty.
  They do not replace it with a number nobody measured.
- The existing studies' "0.4% round trip" constant appears only in the legacy reconciliation.

## 8. Comparisons and statistics

**Three comparisons, each one series per formation month:**

| Name | Series | Role |
|---|---|---|
| **Net vs net** | e_t = (S gross − S cost) − (B gross − B cost) | **Primary.** Like-for-like |
| Gross vs gross | g_t = S gross − B gross | Reported. The edge before any cost |
| Net vs cost-free benchmark | h_t = (S gross − S cost) − B gross | Reported, labelled **"additional hurdle: benchmark charged no costs"**. Not like-for-like |

**Nifty 50 price index:**
- `^NSEI`, via `pit_backtest._benchmark`.
- Dividends are excluded, so it is not comparable and not a measure of alpha.
- Reported for reference only.
- No Nifty total return index is stored, and none is reconstructed.

**Statistic:** the mean of the monthly series.

**Dependence in monthly returns.** The p-value used for every decision is the **larger** of:
1. the plain two-sided t-test (`pit_validation._mean_test`);
2. a Newey-West HAC two-sided test with **6 lags**;
3. a moving-block bootstrap (block length 6 months, 5,000 resamples, seed 20261015, two-sided,
   centred under the null).

The larger p is taken, so that serial correlation cannot manufacture significance. All three are
reported.

## 9. Hypotheses and decision rule

There are two primary hypotheses. Bonferroni: each is tested at **0.05 ÷ 2 = 0.025**.

| | Hypothesis | Settings |
|---|---|---|
| **H1** | Mean e_t > 0 | Floor of Rs 1 crore on the formation day |
| **H2** | Mean e_t > 0 | Floor of Rs 10 crore on the formation day. S **and** B are both rebuilt at that floor |

**Sufficiency.** A hypothesis is reported as **insufficient**, not as passed or failed, if either:
- fewer than 120 formation months qualify; or
- the median size of S is below 10 stocks.

**Break-even multiple k\*:**
- k\* is the factor by which the whole cost schedule (both sides, both portfolios) must be scaled
  for mean e_t to reach 0: k\* = mean(g_t) ÷ mean(S cost − B cost).
- If mean(S cost − B cost) ≤ 0, k\* is "not reached", which counts as meeting the gate.
- It is reported with a 95% block-bootstrap interval (same settings as section 8).

**Verdict for "momentum, net of costs"** (from H1):

- **Passed historical validation (historical, partly seen)** needs all three:
  1. H1's mean e_t > 0, with decision p < 0.025;
  2. **k\* ≥ 2**: the edge survives double the assumed costs, which covers the "per side" reading;
  3. mean e_t > 0 in **both halves**: formation months before 2019-01, and from 2019-01 on.
- **Failed:** mean e_t ≤ 0, or a significantly negative mean.
- **Testable, insufficient evidence:** anything else, with the failing condition named. For
  example: "positive but not significant", "significant, but breaks even below 2× costs", or
  "positive in one half only".

**H2 governs one claim only:** whether the app may say momentum's edge survives costs **among
liquid stocks**.
- If H2 fails or is insufficient, that sentence is not used, whatever H1 shows.
- In that case the result carries a prominent caveat: the edge sits in thinly traded stocks, whose
  real costs are probably above the assumed schedule.

**No verdict here is "prospectively validated" or "independently confirmed".**

## 10. Reported, not used for any decision

1. **Cost multiples.** e_t and h_t at multiples 0, 1, 2 and 3 of the schedule. 2× is the "0.415% per
   side" reading.
2. **Legacy reconciliation.** S with legacy turnover and 0.4% round trip, against a cost-free B. This
   reconciles with the 23.8% a year already seen.
3. **One-day lag.** Trade at the close of the first trading day after each formation date, and hold
   to the same point a month later.
4. **Prior-day eligibility.** The floor applied to the previous trading day's traded value instead
   of the formation day's.
5. **Impact sketch.** `execution.estimate_slippage_pct`'s square-root shape replaces the flat
   allowance.
   - Participation is trade size over the stock's median traded value across the 21 trading days up
     to formation.
   - Two illustrative book sizes: Rs 10 lakh and Rs 1 crore.
   - Description only. The shape is an assumption.
6. **Statistics for S, B and the Nifty reference, gross and net:**
   - CAGR, volatility, Sharpe (`risk_metrics.sharpe`), worst drawdown, months up;
   - mean and median T, and buys and sells;
   - holdings counts, months skipped and why, and the counts from sections 3 and 5.

## 11. Harness and leakage checks

**Code.**
- A new research module, `research/momentum_net_costs.py`.
- It imports `load_adjusted`, `_month_end_cols`, `_momentum_scores` and `_mean_test` from
  `pit_validation`, and the cost rates from `execution`.
- It restates none of them and touches no production module.

**Before the real run.** The checks below must pass on synthetic data, and they are committed along
with the module.
1. **Future-perturbation invariance.** Randomising every close after formation − 21 trading days
   leaves every score unchanged. Randomising every close and volume after the formation day leaves
   the eligible set and target weights unchanged.
2. **Shuffled-signal null.** With scores permuted at random within each month, over 200 shuffles:
   - mean g_t ≈ 0;
   - mean e_t ≈ −mean(S cost − B cost).
3. **Reconciliation.** The legacy series (section 10 item 2) equals the top-bucket series
   `pit_validation.validate()` builds on the same panel, to 1e-12.
4. **Turnover and cost arithmetic,** on hand-worked cases:
   - no change: T = 0;
   - full replacement: T = 1;
   - drift only: the expected T;
   - a −100% holding: weight 0, no sale cost;
   - the first month: buys = 1 at 0.215%.
5. **Boundaries.** A synthetic delisting is booked at −100%. A hold that ends after the archive's
   last day is excluded. A month with 49 eligible stocks is skipped.
6. **Freeze check.**
   - `strategy_version.current_spec()` hash = `54ced1e2c8af0a77`.
   - `backend/modules` has no uncommitted change.
   - This document's hash matches the one recorded in the harness commit.

**During the real run:**
- Check 1 is repeated on **five formation months of the real panel**, chosen with seed 20261015,
  before any return is computed.
- The run aborts if a score changes.

## 12. Run, and the prospective window

**The single run (mode L):**
- On this machine.
- `DATABASE_URL` is set by the owner in their own terminal and is never pasted into chat.
- The script sets the session to `default_transaction_read_only = on` and issues only SELECTs.
- No deploy, no production endpoint, no write.

**Run discipline:**
- Run once.
- A technical failure allows **one** rerun with identical parameters, and the failure is recorded.
- The output JSON is saved under `docs/`. It contains:
  - the commit and spec hash;
  - this document's hash;
  - the data range and formation dates;
  - every count and number in sections 8–10.
- Everything is reported, including failure.

**Prospective window (independent evidence).** The rules are fixed now, before the data exist. This
needs NSE collection resumed by the existing approved pipeline, **after** it is verified (owner
decision, 2026-10-15).
- **What it covers:** formation dates **after the date this pre-registration is approved**, using
  the same frozen code, cost schedule, statistics and H1 settings.
- **Prices:** the existing NSE end-of-day pipeline only. No Yahoo prices are mixed into the series.
  Any gap days are filled from the same NSE daily files, by the same parser.
- **When it is graded:** once, when **24 complete hold months** exist.
- **Rule:**
  - "Prospectively validated" if mean e_t > 0 with decision p < 0.05.
  - "Failed prospectively" if mean e_t ≤ 0.
  - Otherwise, "insufficient evidence".
- **Before then:** interim figures are description only. No early verdict is drawn.

## 13. Not in scope

Quality, value, sentiment, the composite and the labels are not tested here. Nor are horizons other
than 1 month, or any change to the momentum definition.

## 14. Changes before approval

**Revision 1** (2026-10-15): the first draft.

**Revision 2** (2026-10-15, after owner review; nothing had been run):
- **A. Costs.** One itemised per-side schedule: 0.215% buy and 0.200% sell, which is the frozen
  0.415% round trip. The rule for choosing it is stated, and the per-side reading is reported as 2×.
  This replaces "0.415% per unit of one-way turnover".
- **B. Benchmark.** B is now charged its own drift-aware turnover at the same schedule. Net vs net
  is primary; gross vs gross and the cost-free hurdle are reported and labelled. The break-even
  became a multiple of the whole schedule.
- **C. Liquidity.** The floor is frozen exactly as implemented. Its timing and missing-value
  handling are stated, and the prior-day variant is reported.
- **D. Evidence.** Every 2011–2026 verdict is labelled "historical, partly seen". A prospective
  window with fixed rules was added.
- **E. Mechanics.** Formation dates, execution, the non-overlapping 1-month holding and missing
  closes are fixed. A block bootstrap was added to the dependence-robust p-value, and a
  real-panel leakage check runs before any return is computed.
