# v1.4.1 release notes

Frozen on 2026-09-14 on production at `d2feee6`, whose behaviour is identical to `a2418ba`.

## What kind of release this is

A data-correction and measurement release.

**V1 and V2 scoring are unchanged.** No factor formula, weight, threshold, label,
universe rule, rebalance rule, cost assumption or portfolio limit changed.
- The 339 recorded scoring outputs (momentum, low risk, growth and every label
  boundary) match the baseline exactly.
- The provenance audit captures 99 of 99 behavioural parameters, with 0 gaps.

**What changed:** how the research backtests read prices and measure results, and
several operational and wording defects.

**Two momentum backtests, named apart throughout:**
- the **point-in-time momentum backtest** (`/backtest/full-pit`, `pit_backtest.py`): the exchange archive from 2011, delisted stocks included;
- the **Yahoo momentum backtest** (`momentum_backtest.py`, behind the Backtest page and `/factors/strategies`): a fixed list of today's stocks, priced from Yahoo.

## What the specification records differently from v1.4

From `GET /strategy/drift/v1.4` on production at `a2418ba`:

| Field | v1.4 | v1.4.1 | Why |
|---|---|---|---|
| `backtest.archive_starts` | 2024-01-01 | 2011-07-04 | The point-in-time price archive was extended back to 2011. |
| `pit_backtest.adjust_prices` | not recorded | `true` | The point-in-time momentum backtest's closes are corrected for corporate actions (`9b2d764`). |
| `pit_backtest.excess_benchmark` | not recorded | `eligible_universe_equal_weight` | Benchmark A (`a2418ba`). |
| `pit_validation.adjust_prices` | not recorded | `true` | v1.4 did not record whether the point-in-time factor study (`pit_validation`) adjusted prices. Factor test 1 (2026-09-13) ran with adjustment on. |
| `shared_config.scan_complete_fraction` | not recorded | 0.9 | An existing setting, now captured. |

## Changes in behaviour: research and operations, not scoring

1. **Adjusted prices** (`9b2d764`).
   - The point-in-time momentum backtest and the momentum variants study now correct closes for splits, bonuses and dividends.
   - They use `pit_validation.load_adjusted`, the same loader as the point-in-time factor study.
   - Traded value stays as printed.
   - The identity comparison (`/backtest/identity-ab`) stays on printed closes and says so.
2. **One Sharpe and one Sortino** (`9b2d764`, `risk_metrics.py`).
   - Per-period excess return over the risk-free rate, annualised. Sortino's downside deviation is taken over all periods.
   - An undefined ratio is reported as none, not 0.
   - Used by the simulator, the Yahoo momentum backtest, strategy comparison, the point-in-time momentum backtest and the point-in-time factor study's described portfolio.
   - Pairs trading uses it with a target of 0, because the position is self-financing.
   - Not changed: the optimiser's expected Sharpe, and the deflated Sharpe statistic.
   - Strategy comparison feeds the formula the wrong kind of return; see Known limitations.
3. **Benchmark A** (`a2418ba`), for the point-in-time momentum backtest only.
   - Its excess return is measured against every eligible stock that month: equal-weighted, over the same hold month, from the same closes, with −100% for a stock that stopped trading. The benchmark pays no costs.
   - The Nifty 50 price index stays as a reference labelled "dividends excluded; not a measure of alpha".
   - A month without Nifty data is left out of that reference. It used to count as 0%.
4. **The local SQLite file** (`9b2d764`).
   - `stock_universe`, `screener` and `alerts` wait 30 seconds for a lock and use WAL.
   - The screener fetches from Yahoo before writing.
   - Startup runs one writer at a time.
5. **Unscoreable stocks** (`aa4d2f9`).
   - A real stock with fewer than 60 days of Yahoo prices and no market cap is refused with that reason, instead of "Check the symbol".
   - The nightly check separates those from unexplained failures.
   - The exclusion filter is unchanged.
6. **Stale text corrected** (`9b2d764`).
   - `alpha_model` no longer says momentum is a peer rank or that the weights were fitted by OLS on 2019–2022 data. The weights are described as hand-set.
   - Quality's reference values are described as unsourced.
   - The API docs no longer say "proprietary".
   - Limits texts no longer call adjusted prices unadjusted or the archive 2024-only.
7. **Phase 0 records** (`ff74a30`): `docs/PHASE0_V1_METHODOLOGY_2026-09-14.md` and `docs/PHASE0_V1_V2_DIFFERENCES_2026-09-14.md`.
8. **Persistent storage on production** (Render configuration, not code).
   - A 1 GB disk is mounted at `/app/data`, and `QUANT_DATA_DIR` is set to `/app/data`.
   - Production's local SQLite file (`nse_stocks`, `bse_stocks`, `screener_metrics`, `news_cache`, `alert_log`) now survives deploys and restarts.
   - Deploys now have a few seconds of downtime, and the service cannot run more than one instance.

## Results produced under this behaviour

Full record: `docs/BACKTEST_RERUN_ADJUSTED_2026-09-14.md` (`d2feee6`).

**These are historical research results for one market over one period.** They
do not show that the strategy will earn these returns in future, and nothing here
is an out-of-sample or forward result.

**Point-in-time momentum backtest** (`/backtest/full-pit`; frozen 12-1, 170 monthly rebalances, 2012-08 to 2026-09, same archive):

| All stocks trading at the time | Before (`aa4d2f9`) | After (`a2418ba`) |
|---|---|---|
| Yearly return (CAGR) | 15.70% | 24.00% |
| Sharpe | 0.382 (old formula) | 0.747 |
| Sortino | 0.356 (old formula) | 1.129 |
| Worst fall | −47.23% | −41.85% |
| Headline excess | 0.483% a month against the Nifty price index (p 0.195) | 0.693% a month against the eligible universe (95% interval 0.316 to 1.071, p 0.0004) |
| Nifty price reference | not reported | 1.073% a month (p 0.0051), dividends excluded |
| Survivorship cost, CAGR points | 3.24 | 3.41 |

- **Corporate actions applied:** 19,047 of 20,280. That is 18,045 dividends, 519 bonuses and 483 splits; 1,233 were not applied.
- **Delistings 35 → 32 is explained.**
  - The eligible pool and the position-months were identical in both runs; the corrected momentum ranking selected different stocks.
  - `INE275A01028` (held into 2013-07) and `INE218G01017` (held into 2015-07) were booked as delisted before the fix, and not after.

**Momentum variants study** (`/research/momentum-variants`; pre-registered, on adjusted prices):
- **No variant meets the rule, so the frozen 12-1 stands.**
- 12-1 gives +1.535% a month (p 0.0001) and is positive in bull, sideways and bear markets.
- 12-0 gives +1.575% a month but −0.051% in bear markets.
- 6-1 and 6-0 do not beat 12-1, and 6-0 gives −0.796% in bear markets.
- 12-1's result equals factor test 1's momentum result, from the same price loader.

## Evidence

- **CI gate:** 49 suites, 169,941 checks, all passing at `a2418ba`. The gate's self-test passes 27 of 27.
- **The new suites fail against the code before them:**
  - `risk_metrics_test`: 8 of 18 checks fail;
  - `sqlite_local_test`: 7 of 10;
  - `adjusted_backtest_test`: 10 of 16 against `aa4d2f9`'s code, and its 6 Benchmark A checks against `9b2d764`.
- **`unscoreable_reason_test` exits with an error against the code before `aa4d2f9`,** because a name it checks does not exist there yet.
- **Provenance audit:** 99 of 99, 0 gaps.
- **Recorded scoring outputs:** 339 identical.
- **Production:** `a2418ba` went live at 09:11 UTC with CI green. Since 09:39 UTC production runs `d2feee6`, a documentation-only commit on top of it, deployed when the environment variable was saved.
- **Persistence was verified across that 09:38 UTC redeploy.** The live commit changed from `a2418ba` to `d2feee6`, which proves a real restart.
  - The BSE list kept its 09:35:54 write instead of being reloaded.
  - The screener cache kept 200 stocks written at 09:37:43, before the restart.

## Decisions recorded with this version

- The frozen 12-1 momentum rule is kept (momentum variants study).
- Benchmark A is approved for the point-in-time momentum backtest. The Nifty price comparison is kept as a labelled reference, not as alpha.
- **Point-in-time company accounts:** recorded going forward. Historical point-in-time validation of quality, value, growth and sentiment is deferred.

## Known limitations

- **One market and one period.** Costs are assumed, not measured. In factor test 1, momentum's top group earned a small, non-significant return in the most liquid third of stocks (exploratory).
- **1,233 corporate actions could not be applied.**
- **Factor test 1's 3-, 6- and 12-month p-values overstate the independent evidence,** because holding periods overlap. Low risk's 50-stock minimum has not been checked.
- **Three other tools still use the Nifty price index as their benchmark,** while their portfolio returns come from Yahoo's dividend-adjusted closes:
  - the Yahoo momentum backtest;
  - strategy comparison (`/strategy/compare`);
  - the simulator's historical backtest.

  Benchmark A applies only to the point-in-time momentum backtest. `benchmark.py` describes Nifty's change as "total return", which `^NSEI` is not.
- **Strategy comparison computes its statistics from the wrong kind of return** (found 2026-09-14, during review of these notes; not fixed).
  - `portfolio_optimizer._get_returns` returns daily log returns.
  - `strategy_compare` weights them across holdings and passes them to its statistics function, which treats them as simple returns.
  - Its reported returns, drawdowns, Sharpe and Sortino, and those of its Nifty comparison, are therefore not exactly the portfolio's. The size of the error has not been measured.
- **Two endpoints are slow.** `/backtest/full-pit` and `/research/momentum-variants` take 7–8 minutes, so a client must keep the connection alive; there is no background job.
- **NSE collection has been paused since 2026-09-08.**
  - The archive ends 2026-09-07.
  - Production's NSE equity list is empty.
- **Nothing in the scores is point-in-time except prices.**
  - No point-in-time company accounts.
  - Sector peers come from today's map.
  - Piotroski F4 and F5 are always 0.
  - Market-wide headlines are still scored as company news (open finding, 2026-09-09).
- **The composite score and the labels are untested.** The forward test starts 2026-12-27 and excludes the degraded cycles of 2026-09-11, 12 and 13.
- **V2's written weight rationale is contradicted by factor test 1:** it cut momentum for having no edge and raised low risk. The weights are unchanged, pending a decision.
- **The nightly check's "stocks that were scoring" line is expected to fail until the 2026-09-15 cycle.** Errors recorded before `aa4d2f9` carry the old wording. On 2026-09-14 it failed as expected: 47 stocks, 0 marked as short history.

## Operational state at the time of this freeze

These are not limitations of the release.

- **The screener cache holds 200 of the 236 stocks it held before the disk was added.** The first build on the new disk was cut off by the redeploy.
  - The periodic check rebuilds the cache only when it is empty, so it will not fill on its own.
  - It fills when a screener refresh is run (`POST /screener/refresh`).

## Prior versions unchanged

- **v1.0's result stays attributed to v1.0:** 7.85% CAGR, p 0.61, on the 2024–2026 archive with printed closes and the Nifty benchmark. It is not comparable with the figures above.
- v1.1, v1.3 and v1.4 are unchanged.
- v1.2 remains retracted.
