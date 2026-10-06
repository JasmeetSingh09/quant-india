# Pre-registration: factor test 4 — do two price signals add anything beyond momentum?

**Status: APPROVED by the owner on 2026-10-06** (signals chosen 2026-10-05: short-term reversal and nearness to the 52-week high; illiquidity not chosen). Committed before any code for it exists. Nothing below may change after this commit.

## Why this test

The frozen model (v1.6.0) uses two kinds of input:
- **Technical (price) inputs:** momentum, and low risk (shown but no longer scored since v1.6.0). In
  factor test 1, momentum showed an edge at all four holding periods and low risk showed none.
- **Fundamental inputs:** value, quality, growth and sentiment. They cannot be tested properly
  yet, because there is no point-in-time history of fundamentals.

Prices *can* be tested properly: 15 years of exchange closes, adjusted for corporate actions and
joined across ISIN changes. This test asks whether two well-documented price signals carry
information **that momentum does not already carry**. A signal that only restates momentum
would add nothing to the model except double counting, so the primary test controls for momentum.

**Deliberately not tested:** RSI, MACD, Bollinger bands and moving-average crossovers.
- These are transformations of the same recent-return information as momentum and short-term
  reversal.
- Testing them as well would multiply the comparisons without testing a new idea.
- They stay on the stock page as descriptions. They are not candidates for the score.

## What is run

- A new function beside `pit_validation.validate`. It uses the same price matrix
  (`load_adjusted`), the same identity resolution, the same month-end formation dates, the same
  forward returns (a security with no price at the horizon counts as -100%), the same excess
  return (against the equal-weighted eligible universe that month) and the same statistics
  (mean of monthly spreads, tested across months; design-effect-adjusted intervals).
- It is exposed as `GET /validation/price-signals` on production and called once, with defaults.
- **Preconditions, checked and recorded in the output before the run:**
  - The 31 duplicate hand-verified split rows (2026-10-05) have been withdrawn.
  - The output records the corporate-action counts seen and applied, and the archive's first and
    last day. NSE collection is paused, so the archive ends where collection stopped.

## The two signals

Both are computed at formation column `col`, from columns at or before `col` only.

1. **Short-term reversal.**
   - Score = minus the return over the last 21 trading days: `-(C[col] / C[col-21] - 1)`.
   - Higher score = bigger recent fall = expected bounce.
   - This is exactly the month momentum's 12-1 window skips.
   - Needs both closes.
2. **Nearness to the 52-week high.**
   - Score = `C[col] / max(C[col-251 .. col])`.
   - Higher = closer to the high.
   - Needs at least 200 valid closes in the window.

**Considered and not chosen by the owner (2026-10-05): illiquidity (Amihud).** It is not tested
here, and it cannot be added to this test later.

Lookbacks (21 and 252 days) are fixed here. No other window is tried.

## Universe and the momentum-neutral sort

- **Eligible** at a month-end means all four of these hold:
  - a positive close on the formation day;
  - traded value **on the formation day** of at least Rs 1 crore. This is the rule as
    `pit_validation` applies it. Factor test 1's pre-registration describes it as "monthly traded
    value", which is a wording error in that document; the code and this test use the
    formation-day value;
  - a finite momentum score (the frozen 12-1, volatility-adjusted, tanh);
  - a finite score for the signal being tested.
- A month with **fewer than 100** eligible stocks for a signal is skipped for that signal (100
  gives at least 4 stocks per cell below).
- **Primary sort (momentum-neutral):**
  1. Within each month, split the eligible stocks into 5 momentum groups.
  2. Within each momentum group, split them into 5 groups by the signal.
  3. Signal group *k* is the union of sub-group *k* across the five momentum groups.

  So every signal group holds the same mix of momentum.

## Primary hypotheses (8)

For each signal (2) and holding period of 1, 3, 6 and 12 months (4): **in the momentum-neutral
sort, does signal group 5's excess return beat signal group 1's?**
- The statistic is the mean of the monthly group-5-minus-group-1 spread, tested across months.
- A holding period counts as a usable test only if at least 3 non-overlapping windows fit.

## Decision rule

- **Significance level:** 0.05 divided by the number of usable primary tests (at most 8, so at
  least as strict as **0.00625**). Bonferroni, across both signals together.
- A signal **adds beyond momentum** if at least one holding period has a **positive** mean spread
  **and** a p-value below that level.
- A significant **negative** spread is reported as **reversed** (the signal points the wrong way
  once momentum is held fixed). It is not an edge.
- Anything else is **no demonstrated added edge**: the data did not show one, which is not proof
  that none exists.

## Reported, not tested

- **Standalone spreads:** each signal's plain quintile spread, without the momentum control, the
  way factor test 1 reported momentum. These are shown so a reader can see how much of a signal is
  momentum.
- **Overlap with momentum:** the monthly rank correlation between each signal and momentum, and
  its average.
- **Costs:** at every holding period, the momentum-neutral group-5 portfolio and the
  group-5-minus-group-1 spread, net of 0.4% round trip on the turnover realised when
  rebalancing at that holding period.
  - Reversal trades heavily (most of the portfolio changes every month), so its net-of-cost
    figure is the one to watch.
- **Halves:** the spread at each horizon in the first and second half of the formation months
  (split at the middle month), as point estimates.
- **Exploratory:** cuts by market regime and by liquidity, as in factor test 1. Uncorrected,
  never a finding.

## What a pass does and does not do

A pass does **not** change v1.6.0. A written proposal for a new model version may follow only if
**all** of these hold for the same signal and horizon:
1. it passes the decision rule above;
2. its spread is positive in **both** halves of the formation months;
3. its momentum-neutral spread at that holding period stays positive **after costs**: 0.4% round
   trip on the turnover realised when rebalancing at that holding period.

Even then, the weight given to it is a separate decision, made in the proposal and approved by
the owner. It is not set by this test.

## Implementation, before the run

- The code is written **after** this document is committed. It is committed **before** the run,
  with offline tests on synthetic prices:
  - a planted reversal effect is recovered;
  - a planted effect that is pure momentum shows up in the standalone sort but **not** in the
    momentum-neutral one;
  - pure noise gives no pass;
  - the 200-day and 100-stock floors behave as written;
  - no score reads a column to the right of `col`.
- The run reuses the compact per-month arrays that let factor test 1 run within the server's
  memory.

## Commitments

- Every result is reported, including no edge and reversed.
- No rerun with different windows, floors, horizons, bucket counts or universes. A technical
  failure (for example the server running out of memory) allows one rerun with exactly these
  settings, and the failure is recorded.
- Quality, value, growth, sentiment, the composite score and the Buy/Sell labels are not tested
  here.

## Approvals

- [x] Owner, 2026-10-06 ("Approve as written")
- Committed before the test code is written; pushed together with that code, before any run on real data.
