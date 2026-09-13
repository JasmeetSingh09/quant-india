# Factor test 1 result: momentum and low risk on the point-in-time archive

**Run:** 2026-09-13, 21:21–21:27 UTC, `GET /validation/pit?min_turnover=10000000&buckets=5`
on production, commit `7718754`. **Rules:** `docs/PREREG_FACTOR_TEST1_2026-09-13.md`,
committed at 21:20:58 UTC, before the run. **Raw output:**
`docs/factor_test1_pit_result.json`.

## Verdict, by the pre-registered rules

| Factor | Verdict |
|---|---|
| **Momentum** | **Demonstrated an edge** at all four holding periods |
| **Low risk** | **No demonstrated edge** at any holding period |

Significance level: 0.05 / 8 usable tests = **0.00625** (Bonferroni). All 8
primary tests had enough non-overlapping windows to count.

## The data

- NSE end-of-day prices, 2011-07-04 to 2026-09-07: 3,744 trading days, 3,758
  securities including delisted ones.
- Adjusted for corporate actions: 19,047 of 20,280 stored actions applied
  (1,233 could not be applied); 3.9 million of 6.6 million prices moved.
- Identity resolution linked 584 ISIN changes; 6 ambiguous ones were left
  unmerged.
- 170 monthly rankings. Universe each month: stocks with at least Rs 1 crore of
  monthly traded value.
- Server memory peaked at 1,465 MB of 2 GB; no restart.

## Primary results

Spread = the top fifth's return minus the bottom fifth's, net of the market that
month, averaged across months.

| Factor | Holding | Spread | 95% interval | p-value | Independent windows | Passes |
|---|---|---|---|---|---|---|
| Momentum | 1 month | +1.54% | +0.77 to +2.30 | 0.0001 | 170 | Yes |
| Momentum | 3 months | +4.25% | +2.81 to +5.69 | <0.0001 | 56 | Yes |
| Momentum | 6 months | +7.49% | +5.63 to +9.35 | <0.0001 | 27 | Yes |
| Momentum | 12 months | +11.04% | +8.02 to +14.07 | <0.0001 | 13 | Yes |
| Low risk | 1 month | +0.96% | −0.16 to +2.08 | 0.091 | 170 | No |
| Low risk | 3 months | +2.41% | +0.38 to +4.44 | 0.020 | 56 | No |
| Low risk | 6 months | +3.32% | +0.55 to +6.08 | 0.019 | 27 | No |
| Low risk | 12 months | +2.85% | −1.53 to +7.23 | 0.201 | 13 | No |

**Momentum's five groups are in order at every holding period** (1 month, excess
return by group from lowest to highest score: −0.78%, −0.26%, −0.06%, +0.35%,
+0.76%).

**Low risk's are not.** Its spread comes mostly from the most volatile group
doing badly (−0.95% a month), while the calmest group earned about the market
(+0.02%). "Avoid the jumpiest stocks" describes it better than "buy the calmest";
that is a description, not a tested finding.

## Described, not tested

A portfolio of momentum's top group, rebalanced monthly, net of 0.4% round-trip
costs: **23.8% a year, volatility 22.3%, Sharpe 0.78, worst fall −38.7%,** up in
66.5% of months. Low risk's top group: 15.9% a year, volatility 13.7%, Sharpe
0.69, worst fall −25.1%.

## Exploratory cuts: 18 comparisons, uncorrected, never a finding

Momentum's top group, 1-month excess return:

| Cut | Excess per month | p-value |
|---|---|---|
| Least liquid third | +1.12% | <0.0001 |
| Middle liquidity third | +0.88% | 0.0002 |
| **Most liquid third** | **+0.30%** | **0.25** |
| Bull markets (76 months) | +0.68% | 0.016 |
| Sideways (53 months) | +1.13% | 0.003 |
| Bear markets (38 months) | +0.42% | 0.40 |
| Low volatility (92 months) | +1.04% | <0.0001 |
| High volatility (75 months) | +0.43% | 0.23 |

Low risk showed nothing in any cut.

## What this does and does not show

- **It shows** that, over 2011–2026, NSE stocks ranked high on this app's
  momentum measure went on to beat those ranked low, on data that includes
  failed companies and corrects for splits and bonuses, by rules fixed before
  the run.
- **The edge sits mostly in less liquid stocks.** In the most liquid third it
  was small and not significant. Real trading costs in thin stocks are likely
  well above the 0.4% assumed, so the tradeable edge is probably smaller than
  the table.
- **Most individual picks did not win.** About 48% of top-group stocks beat the
  market in a month; the average is carried by the winners.
- **One market, one period.** A result that survives correction over 170 months
  still needs to hold out of sample before it is called durable.
- **Low risk** did not clear the bar. It is not shown to be worthless either:
  its p-values at 3 and 6 months were about 0.02.

## Why earlier tests found no momentum edge

The app currently says momentum "did not demonstrate a statistically significant
edge", and the V2 weights cut it from 25% to 18% on that basis. Those tests were
much smaller: walk-forward runs over about 42 windows with five-stock
portfolios, and backtests on the 50 to 100 most liquid names over 2020–2026.
This test covers every stock above Rs 1 crore of monthly turnover for 15 years.
The two agree once liquidity is taken into account: among the most liquid
stocks, this test also finds no significant edge. That matches
`RESEARCH_momentum.md`: momentum in Indian equities lives in breadth.

## Not changed by this result

The V1.4 model is frozen. The factor weights, the momentum wording on the
evidence page (`/factors/evidence`) and the V2 weight notes all still say momentum
is unproven. Whether to change any of them is a decision, not a consequence of
this run.

## Found while reading the output

The response's `limits` text says prices are "unadjusted for splits and
dividends". The same response reports `adjusted_for_corporate_actions: true` with
19,047 actions applied. The sentence predates the adjustment and should be
corrected in `pit_validation.py`.
