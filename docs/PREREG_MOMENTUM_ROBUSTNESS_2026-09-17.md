# Momentum robustness: pre-registration

**Written 2026-09-17, before any of these runs.** This is item 3 of the
post-freeze order (see the v1.4.1 release notes).

## What is already known, and was seen before writing this

Factor test 1 (`FACTOR_TEST1_RESULT_2026-09-13.md`), on adjusted point-in-time
prices, 2011-07 to 2026-09, monthly traded value of at least Rs 1 crore:

- **Momentum 1-month top-minus-bottom spread:** +1.54% a month (p 0.0001).
- **Split by liquidity (exploratory):**

  | Liquidity third | Spread per month | p |
  |---|---|---|
  | Least liquid | +1.12% | < 0.0001 |
  | Middle | +0.88% | 0.0002 |
  | Most liquid | +0.30% | 0.25 |

- **Low risk failed at every holding period.** It is not retested here.

IIMA's value-weighted WML earned +1.11% a month over 2013–2025
(`IIMA_FACTOR_CHECK_RESULT_2026-09-17.md`). That factor is dominated by large
companies, which is in tension with the weak most-liquid third above.

Because the liquidity pattern was seen first, H1 is **not** a blind test. It is
registered so the investable version is judged by a fixed rule, not by
whichever cut looks best.

## Statistic

The same as factor test 1:
- **Spread:** the top fifth's return minus the bottom fifth's, net of the market
  that month, averaged across monthly rankings.
- **p-value:** as `pit_validation` computes it.
- **Scoring:** momentum exactly as frozen in v1.4.1 (12-1, volatility-adjusted),
  from `GET /validation/pit`.

## Primary tests (three; Bonferroni, each at 0.05 / 3 = 0.0167)

| Test | Hypothesis | Settings | Code change? |
|---|---|---|---|
| **H1 investable** | 1-month spread > 0 | `min_turnover=1e8` (Rs 10 crore a month) | No |
| **H2 recent half** | 1-month spread > 0 | Default floor; rankings formed 2019-01 onward only | Yes: a date window |
| **H3 independent** | Our monthly 1-month spread correlates positively with IIMA WML over common months, to 2025-12 | Default floor; Pearson r, p from t with n − 2 degrees of freedom | Yes: output the per-month spread |

**Sufficiency rule.** If the median number of eligible stocks per month is below
100 (fewer than 20 per fifth), the test is reported as **insufficient**, not as a
pass or a failure.

## Secondary (described, no claims)

1. `min_turnover=5e8` (Rs 50 crore a month): the 1-month spread.
2. At Rs 10 crore: 3-month spread, and the liquidity thirds.
3. The earlier half (rankings before 2019-01).
4. Regression of our monthly spread on WML: slope and intercept, Newey-West 6 lags.

## Wording decided in advance

- **H1 passes:** "Momentum's edge held among stocks trading at least Rs 10 crore a
  month."
- **H1 fails:** "Momentum's edge was not demonstrated among stocks trading at least
  Rs 10 crore a month; the demonstrated edge is concentrated in less liquid
  stocks." This goes wherever the momentum result is quoted.
- **H2:** "held / was not demonstrated in 2019–2026."
- **H3 passes:** "our momentum ranking moved with IIMA's independently built
  momentum factor." A pass is agreement, not proof of a profit.

## Run conditions

- **Production only.** The archive is there, not locally. Each run takes about 6
  minutes; factor test 1 peaked at 1,465 MB.
- **Not before** production memory has been flat for a day after the cache fix
  (`569a18e`).
- **Never** during the scan (00:02–03:00 UTC).
- **One run per setting.** A failed run may be repeated only for an
  infrastructure fault, and that fault is recorded.
- **H2 and H3 need a research-only change to `pit_validation`:** an optional
  date window and a per-month spread in the output, with defaults unchanged. It
  needs approval and one deploy, and it changes no model parameter.
