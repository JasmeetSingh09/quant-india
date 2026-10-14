# Pre-registration DRAFT: factor test 5, momentum net of trading costs

**Status: DRAFT, awaiting owner approval. Nothing has been run.** No harness exists yet. No new
number has been computed for this document.

It becomes binding when:
1. the owner approves it;
2. it is committed;
3. that commit precedes the harness commit and the single run.

Any edit made before approval is listed in section 13. After approval, nothing in sections 3–11
changes.

**Model.** Unchanged. The frozen spec stays v1.6.0, hash `54ced1e2c8af0a77`. This test reads the
frozen momentum code. It changes no weight, threshold, label or scoring rule.

---

## 1. Question

After realistic Indian delivery-trading costs, does a long-only, equal-weight, monthly-rebalanced
portfolio of the **top fifth of stocks by the frozen v1.6.0 momentum score** beat the
equal-weighted universe of eligible stocks?

## 2. What has already been seen (this is not a blind test)

These results were seen before this was written. They are stated so nobody mistakes this test for
independent evidence.

**Factor test 1** (`FACTOR_TEST1_RESULT_2026-09-13.md`, re-run twice after data corrections with
the verdict unchanged):
- The gross 1-month top-minus-bottom spread is about +1.5% a month, p ≤ 0.0001.
- The top-fifth portfolio was *described* net of 0.4% round-trip costs: 23.8% a year, volatility
  22.3%, worst fall −38.7%.

**Liquidity thirds** (exploratory): most of the edge sits in the less liquid two thirds. The most
liquid third showed +0.30% a month, p 0.25.

**Frozen v1.0 backtest** (`RELEASE_NOTES_v1.4.1.md`, `pit_backtest.run`): +0.693% a month over the
eligible universe after 0.4% costs, p 0.0004. That backtest used the *raw* 12-1 return, not
v1.6.0's volatility-adjusted score.

**Consequence.**
- On the 2011–2026 archive, the answer to the primary question can largely be predicted from those
  numbers. A pass there is labelled **"Passed historical validation (in-sample, partly seen)"** and
  never "prospectively validated".
- The informative outputs here are three things the earlier work did not measure:
  - the **break-even cost**;
  - a **drift-aware turnover** figure;
  - the **liquid-only net result** (H2).
- Independent evidence can only come from data not yet looked at (section 12).

## 3. Signal (read from frozen code, not restated)

The score is `pit_validation._momentum_scores(C, col)`, unchanged:
- **Window:** return from 252 trading days before formation to 21 days before;
- **Scaling:** divided by annualised daily volatility over that window, then put through tanh.

Portfolios use rank order only, and tanh does not change rank.

**Known difference (D-07):** the point-in-time copy uses population standard deviation (ddof 0);
the live factor uses the sample standard deviation (ddof 1). With a full 231-return window the
two rank stocks identically. This is recorded, not changed.

The signal uses only closes up to 21 trading days before formation, so it is fully known three
weeks before the trade.

## 4. Data

`pit_validation.load_adjusted`, unchanged:
- **Prices:** NSE end-of-day closes (`bhavcopy_eod`), adjusted for splits, bonuses, dividends and
  rights from the stored corporate actions.
- **Identity:** securities joined across ticker changes by ISIN identity resolution.
- **Traded value:** left as printed.

**Range:** the stored archive, 2011-07-04 to 2026-09-07. The harness records the exact first and
last day it reads.

**Partial month:** the archive stops on 2026-09-07, so September 2026 is incomplete. Any hold
period ending in it is **excluded**. The last formation month used is 2026-07 (held through
2026-08).

## 5. Universe, formation and execution

**Formation day:** the last stored trading day of each month (`_month_end_cols`).

**Eligible stocks** are those with all three of:
- a finite, positive adjusted close on the formation day;
- a finite momentum score;
- **traded value on the formation day** (close × volume, printed) of at least Rs 1 crore.

**Documentation defect (2026-10-15).** Earlier documents call this floor "monthly traded value of
Rs 1 crore". The code (`pit_validation._load`, `V = close × volume` per day; the same in
`pit_backtest`) measures traded value **on the single formation day**. Earlier results are correct
for the rule the code applies; only their wording is wrong. This test uses the code's rule and
names it correctly. The wording fix is proposed separately and changes no number.

**Rules carried over from factor test 1:**
- A month with fewer than 50 eligible stocks is skipped.
- Stocks are ranked within the month. The top fifth is the top bucket under `pit_validation`'s
  bucket rule: a stable ascending sort, label = min(4, rank × 5 ÷ n).

**Execution (primary):**
- Trade at the formation-day close. The signal is known 21 trading days earlier, so this needs no
  information from the formation day except its closing price.
- Hold to the next formation day's close.

**Delisting:** a holding with no close at the end of the hold month is marked to −100%. No sale
cost is charged on it, since it cannot be sold.

## 6. Portfolio and turnover

**Weights:** equal at each formation day.

**Turnover (primary), drift-aware one-way turnover T:**
- T = ½ × Σ |w_target − w_drifted|, summed over the union of old and new holdings.
- w_drifted is each old holding's weight after the month's returns. A holding marked to −100%
  drifts to zero weight.
- At the first formation month, T = ½ (buying only).
- This also charges the trades that rebalance continuing holdings back to equal weight. The
  symmetric-difference formula used so far leaves those out.

**Turnover (legacy, reported for comparison):** |cur △ prev| ÷ (2 × |cur|), exactly as
`pit_validation` and `pit_backtest` compute it.

## 7. Cost model

**Primary cost: c = 0.415% per unit of one-way turnover.** This is the project's frozen trading
cost (`PHASE0_V1_METHODOLOGY_2026-09-14.md`, "Trading costs"). Turning over a fraction T of the
book costs T × c, and the net return is gross − T × c.

**Where 0.415% comes from.** It is the simulator's `_apply_transaction_costs` total: brokerage 0.1%
each way, slippage 0.05% each way, STT 0.1%, stamp duty 0.015%.

**Its listed components disagree with each other.** Recorded, not resolved here:
- The simulator assumes STT on the sell side only. Delivery STT is charged on both buy and sell.
- `execution.py` assumes brokerage of 0.03% a side.
- **Statutory items on a delivery round trip,** at the rates in `execution.py` (STT 0.1% each side,
  stamp 0.015% on the buy, exchange 0.00345% each side, SEBI fee, 18% GST on brokerage and exchange,
  brokerage 0.03% each side): about 0.29%.
- **Adding** 0.05% slippage each side: about 0.39%.

0.415% is therefore a reasonable central figure. It is **not** a measured cost for thinly traded
stocks. No bid-ask or order-book history exists here, so the uncertain part, spread and impact, is
handled by sensitivity (section 9), not asserted.

**Historical rates:** no history of statutory rates is applied. Stamp duty, for example, varied by
state before July 2020. One constant cost is used for the whole period, and this is stated.

**Benchmark:** charged **no** cost. That understates the excess rather than flattering it. This is
the approved benchmark A of `pit_backtest`.

## 8. Benchmarks and statistic

**Primary benchmark:** every eligible stock that month, equal-weighted over the same hold month,
from the same closes, with −100% for a stock that stopped trading, and no costs. This is the same
definition as `pit_backtest.EXCESS_BENCHMARK`, applied to this test's eligible set.

**Reference only:** the Nifty 50 *price* index (`^NSEI`, as `pit_backtest._benchmark` fetches it).
Dividends are excluded, so it is not comparable and is not a measure of alpha. **No Nifty total
return index is stored. None is reconstructed.**

**Monthly series:** e_t = (top-fifth gross return − T_t × c) − benchmark return, one value per
formation month.

**Statistic:** the mean of e_t. The p-value is the **larger** of:
- the plain two-sided t-test p (`pit_validation._mean_test`);
- the Newey-West (6 lags) two-sided p.

The larger one is taken so that serial correlation cannot manufacture significance.

## 9. Hypotheses and decision rule

There are two primary hypotheses. Bonferroni: each is tested at **0.05 ÷ 2 = 0.025**.

| | Hypothesis | Settings |
|---|---|---|
| **H1** | Mean e_t > 0 | As above: Rs 1 crore formation-day floor, c = 0.415% |
| **H2** | Mean e_t > 0 among liquid stocks | Floor raised to **Rs 10 crore** on the formation day; the universe and benchmark are rebuilt at that floor; c = 0.415% |

**Sufficiency.** A hypothesis is reported as **insufficient** (not as pass or fail) if:
- fewer than 120 formation months qualify; or
- the median top-fifth size is below 10 stocks.

**Verdict for "momentum, net of costs"** (from H1, with two robustness gates fixed now):

- **Passed historical validation (in-sample, partly seen)** requires all three:
  1. H1: mean > 0 and p < 0.025;
  2. **break-even cost ≥ 0.83%**, twice c;
  3. mean e_t > 0 in **both halves**: formation months before 2019-01, and 2019-01 onward (the
     split used by momentum robustness H2).
- **Failed:** mean e_t ≤ 0, or a significant negative mean.
- **Testable, insufficient evidence:** anything else, with the failing condition named. For
  example, "positive but not significant", or "significant, but breaks even below 0.83%".

**H2 decides only this sentence:** whether the app may say momentum's edge survives costs **among
liquid stocks**.
- If H2 fails or is insufficient, that sentence is not used, whatever H1 shows.
- A failing H2 also becomes a **prominent caveat**: the edge sits in thinly traded stocks, whose real
  costs are probably above c.

**Break-even cost** = mean gross excess ÷ mean T. It is the c at which mean e_t = 0. It is reported
with a 95% interval, by a block bootstrap of months (block 6, 5,000 draws, seed 20261015).

## 10. Reported, not used for any decision

1. e_t at c = 0, 0.415%, 0.83% and 1.245% (0×, 1×, 2× and 3×).
2. **Legacy turnover:** the H1 series recomputed with the symmetric-difference formula and c = 0.4%,
   to reconcile with the 23.8%-a-year figure already seen.
3. **One-day lag:** trade at the close of the first trading day after formation; hold to the same
   point a month later.
4. **Impact sketch:** `execution.estimate_slippage_pct`'s square-root shape, applied to each trade.
   - Participation is the trade size over the stock's median traded value across the 21 trading
     days up to formation.
   - Two illustrative book sizes: Rs 10 lakh and Rs 1 crore.
   - Description only. The shape is an assumption, not a measurement.
5. Top-fifth statistics, gross and net: CAGR, volatility, Sharpe (`risk_metrics.sharpe`), worst
   drawdown, months up. Same for the benchmark and for the Nifty price reference.
6. Mean and median monthly T; holdings count; months skipped and why; delisted holdings booked at
   −100%.

## 11. Harness, leakage checks and run

**Code.** A new research module, `research/momentum_net_costs.py`. It imports `load_adjusted`,
`_month_end_cols`, `_momentum_scores` and `_mean_test` from `pit_validation`, and restates none of
them. It touches no production module.

**Before the real run:** these checks must all pass on **synthetic data**, and the module and checks
are committed:
1. **Future-perturbation invariance.** Changing any close after formation − 21 days leaves every
   score unchanged. Changing any close after formation leaves the eligible set and the weights
   unchanged.
2. **Shuffled-signal null.** With scores permuted at random within each month, mean gross excess ≈ 0
   across 200 shuffles, and mean net excess ≈ −mean(T) × c.
3. **Reconciliation.** With legacy turnover and c = 0.4%, the top-fifth net series equals the series
   `pit_validation.validate()` builds on the same panel, to 1e-12.
4. **Turnover arithmetic.** Hand-worked cases: no change gives T = 0; a full replacement gives
   T = 1; drift-only rebalancing gives the expected T; a −100% holding drifts to zero and is not
   charged.
5. **Delisting and partial month.** A synthetic delisting is booked at −100%. A hold month that
   ends past the archive's last day is excluded.
6. **Freeze check.** `strategy_version.current_spec()` hash = `54ced1e2c8af0a77`, and
   `backend/modules` has no uncommitted change.

**The single run.** It is read-only against the production archive, in one of two ways (owner's
choice; neither is done without approval):

- **(L) Local, recommended.** The owner sets `DATABASE_URL` in their own terminal (it is never
  pasted into chat). The script then opens a **read-only** transaction and runs on this machine.
  No deploy is needed, so the 17 local commits waiting for the release decision are not shipped to
  run it.
- **(P) Production endpoint,** as factor tests 1 and 4 were run. This needs a backend deploy, which
  belongs to the release decision.

**Run discipline:**
- Run once.
- A technical failure (memory, connection) allows **one** rerun with identical parameters, and the
  failure is recorded.
- The output JSON is saved under `docs/` with:
  - commit, spec hash, data range;
  - every count and every number in sections 9–10.
- Everything is reported, including failure.

## 12. What would be independent evidence (not part of this test)

Each needs its own pre-registration and is named here so it is not improvised later.

1. **Forward window.** Formation months after 2026-07, graded once at least 24 complete months
   exist.
   - **Blocker:** no new NSE prices are being stored. Collection is paused, and fetching NSE is the
     owner's decision.
   - The evidence verdicts page's phrase "accruing since 2026-09-07" is therefore not true today and
     should be corrected.
   - The owner must choose a forward price source:
     - resume NSE end-of-day collection; or
     - use Yahoo with its limits stated (no delisted names, no corporate-action provenance).
2. **Pre-2011 NSE history.** End-of-day files reportedly reach back to 1998, which makes 1999–2011
   unseen. Needs:
   - owner permission to fetch from NSE;
   - a data-integrity check of that period (identity, corporate actions, gaps) passed **before any
     return is computed**.

## 13. Changes before approval

(none yet)
