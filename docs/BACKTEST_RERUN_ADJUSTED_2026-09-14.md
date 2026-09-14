# Backtest rerun on adjusted prices, and the momentum variants study

**2026-09-14.** Results of the fixes approved in `PHASE2_FINDINGS_2026-09-14.md`:

- **`9b2d764`, live 08:31 UTC:** adjusted prices, and one Sharpe and Sortino definition.
- **`a2418ba`, live 09:11 UTC:** Benchmark A.

No factor formula, weight, threshold or label changed in either commit.

## The runs

| Run | Code | Time (UTC) | Prices | Sharpe and Sortino | Excess measured against | File |
|---|---|---|---|---|---|---|
| Before | `aa4d2f9` | 08:17–08:20 | as the exchange printed them | the old per-module formulas | Nifty 50 price index | `full_pit_printed_closes_2026-09-14.json` |
| After | `a2418ba` | 09:13–09:20 | adjusted for corporate actions | `risk_metrics` | eligible universe (Benchmark A) | `full_pit_adjusted_benchmark_a_2026-09-14.json` |
| Momentum variants | `9b2d764` | 08:48–08:55 | adjusted | not used | eligible universe (built into the study) | `momentum_variants_adjusted_2026-09-14.json` |

**Runs not kept as files:**
- **A run on `9b2d764`** (08:40–08:48, adjusted prices, excess still against Nifty) gave strategy figures identical to the "after" run. Its excess against Nifty, 1.073% a month (p 0.0051), is the Nifty reference in the "after" run.
- **The momentum variants study on `aa4d2f9`** did not complete: the connection was dropped at 301 seconds. That was the Python client, which sends no keep-alives. The same requests with `curl --keepalive-time` took 7–8 minutes and succeeded. So this study has **no before-the-fix result**.

**Data:**
- **Price archive:** NSE daily files, 2011-07-04 to 2026-09-07; 6,598,053 rows; 3,758 securities, delisted ones included.
- **Corporate actions:** 19,047 of 20,280 applied (18,045 dividends, 519 bonuses, 483 splits); 1,233 could not be applied.
- **Identity:** 584 ISIN changes linked; 6 ambiguous ones left unmerged.

## The momentum backtest, `/backtest/full-pit`

**Strategy (frozen since v1.0, 2026-08-25):**
- Hold the top fifth of stocks by 12-1 momentum, rebalanced monthly.
- Eligible stocks need at least Rs 1 crore of traded value on the month-end day.
- Costs are 0.4% per round trip on turnover.
- A holding that stopped trading is marked at −100%.
- **170 monthly rebalances, holding months August 2012 to September 2026.**

| All stocks trading at the time | Before | After |
|---|---|---|
| Yearly return (CAGR) | 15.70% | **24.00%** |
| Volatility | 24.09% | 24.41% |
| Sharpe | 0.382 (old formula) | **0.747** |
| Sortino | 0.356 (old formula) | **1.129** |
| Worst fall | −47.23% | −41.85% |
| Mean monthly return | 1.471% (p 0.0065) | 2.062% (p 0.0002) |
| **Excess return, headline** | 0.483% a month against the Nifty price index (p 0.195) | **0.693% a month against the eligible universe, 95% interval 0.316 to 1.071, p 0.0004** |
| Nifty 50 price reference, dividends excluded | not reported separately | strategy minus Nifty 1.073% a month (p 0.0051); Nifty's own yearly return 11.16%, price only |
| Eligible universe, the benchmark | not reported | yearly return 14.42%, volatility 23.80%, Sharpe 0.417, worst fall −59.44% |
| Holdings booked as delisted | 35 | 32 |

| Survivors only (bias reproduced on purpose) | Before | After |
|---|---|---|
| Yearly return (CAGR) | 18.94% | 27.41% |
| Excess, headline | 0.713% a month against Nifty (p 0.055) | 0.663% a month against the survivors' own eligible universe (p 0.0005) |
| Survivorship cost, CAGR points | 3.24 | 3.41 |

### Which change moved which figure

- **Yearly return, volatility, worst fall, mean monthly return and delistings** moved only because prices are now adjusted.
- **Sharpe and Sortino** moved for two reasons: adjusted prices and the single formula.
- **Excess return** moved for two reasons: adjusted prices and the new benchmark.

### How to read it

- **The corrected result is materially stronger than the old one.** The old run booked every bonus issue and split inside a holding month as a loss (1,002 such actions are in the archive), and it left out dividends.
- **The headline excess is 0.69% a month against the eligible universe.** That universe is the same stocks, dates, closes and dividend treatment. The benchmark pays no trading costs, so this figure understates the strategy rather than flattering it.
- **The Nifty comparison is a reference, not alpha.** The index is price only, and the portfolio's return includes dividends.
- **The 12-1 rule was not chosen on this data.** It was fixed in v1.0 on 2026-08-25, when the archive started in January 2024, and the archive was extended back to 2011 afterwards.
- **That does not make it a test of predictive power.** Momentum is a well-known anomaly, and this is one market over one period.
- **The edge may sit mostly in thin stocks.** Factor test 1 found momentum's top group earned +0.30% a month (p 0.25) in the most liquid third of stocks. This backtest has no liquidity cut beyond the Rs 1 crore floor.
- **Trading costs are assumed, not measured.** Real costs in thinly traded stocks are likely above 0.4%.

## Why delistings changed from 35 to 32

It is not a data problem.

| | Before | After |
|---|---|---|
| Eligible stocks per month (average, lowest, highest) | 819.0, 282, 1,561 | 819.0, 282, 1,561 |
| Average holdings | 163.8 | 163.8 |
| Position-months | 27,851 | 27,851 |
| Distinct stocks held | 1,932 | 1,921 |
| Monthly turnover | 29.8% | 29.4% |
| Holdings booked as delisted | 35 | 32 |

**The pool of stocks the strategy could buy was identical.** The ranking changed: a bonus or split inside the 12-month lookback used to look like a crash and pushed that stock down the momentum ranking. With adjusted prices the ranking changed, so different stocks were held, and a different set of them later stopped trading.

Two stocks booked as delisted before are not booked after:

| Holding month | ISIN | Before | After |
|---|---|---|---|
| 2013-07 | `INE275A01028` | held, booked at −100% | not booked |
| 2015-07 | `INE218G01017` | held, booked at −100% | not booked |

**Why "not booked" is conclusive.**
- **The list is complete for those months.** The endpoint lists a run's delistings in date order and returns the first eight. The "after" list's first eight run from February 2013 to March 2017, so it covers both months.
- **Not booked means not held.** A holding with no next month-end price is always booked, and both runs read the same prices. So neither stock was held in those months after the fix.

**What the output cannot show:**
- whether each one's own adjusted ranking fell, or corrected stocks moved above it;
- the rest of the net change of −3, which lies beyond the eight listed examples.

## The momentum variants study, `/research/momentum-variants`

The study was pre-registered. Its rule: a variant replaces the frozen 12-1 only if it
- beats it on the mean 1-month top-minus-bottom spread (measured against the equal-weighted eligible universe);
- survives Bonferroni correction across the four variants (0.05 / 4 = 0.0125);
- keeps the same sign across bull, sideways and bear markets, and across the 1- and 3-month horizons;
- has at least 3 non-overlapping windows.

Universe: 3,758 securities, 183 months, Rs 1 crore turnover floor, 0.4% costs.

| Variant | 1-month spread | 3-month spread | Beats 12-1 | Survives correction | Same sign everywhere | Meets the rule |
|---|---|---|---|---|---|---|
| **A: 12-1, frozen V1.4** | **+1.535% (p 0.0001), 170 windows** | +4.251% | baseline | yes | yes | stays |
| B: 12-0 | +1.575% (p 0.0002) | +4.670% | yes | yes | **no** | no |
| C: 6-1 | +1.464% (p < 0.0001) | +4.283% | no | yes | yes | no |
| D: 6-0 | +1.446% (p 0.0001) | +4.536% | no | yes | **no** | no |

1-month spread by market regime (months in brackets):

| Variant | Bull | Sideways | Bear |
|---|---|---|---|
| A: 12-1 | +1.536% (77) | +2.249% (55) | **+0.498% (38)** |
| B: 12-0 | +1.826% (77) | +2.345% (55) | **−0.051% (38)** |
| C: 6-1 | +1.788% (77) | +1.906% (57) | +0.268% (39) |
| D: 6-0 | +1.965% (77) | +2.305% (57) | **−0.796% (39)** |

- **Conclusion, by the pre-declared rule: no variant qualifies, and the frozen 12-1 stands.** The variants without the skipped month earn more in rising and flat markets and lose it in falling ones.
- **Consistency check:** variant A's result (+1.535% at 1 month, p 0.0001; +4.251% at 3 months) equals factor test 1's momentum result. Both now read prices through `pit_validation.load_adjusted`.
- **Regime splits are descriptive only.** Bear markets supplied 38 months.

## Limits of this record

- One market and one period; costs assumed.
- 1,233 corporate actions could not be applied.
- `/backtest/full-pit` and `/research/momentum-variants` take 7–8 minutes on production. A caller needs a client that keeps the connection alive; there is no background job.
- Other modules still compare with the Nifty price index while their portfolio returns include dividends:
  - `momentum_backtest`, on Yahoo closes;
  - the simulator's historical backtest, which credits dividends.

  Neither was changed here.
- The v1.0 result (7.85% CAGR, p 0.61) remains attributed to v1.0. It was run on the 2024–2026 archive with printed closes and is not comparable with these figures.
