# IIMA factor library check: result

**Run 2026-09-17**, following `IIMA_FACTOR_CHECK_PREREG_2026-09-17.md`, which was
committed before any statistic was computed (`aa29527`).

- **Script:** `research/iima_factor_check.py`
- **Output:** `iima_factor_check_2026-09-17.json`, including each data file's SHA-256.
- **Data:** Agarwalla, S. K., Jacob, J. and Varma, J. R. (2013), *Four factor model in
  Indian equities market*, W.P. No. 2013-09-05, IIM Ahmedabad; December 2025
  release, survivorship-bias adjusted, monthly.

## Primary tests (each at 0.025, Bonferroni over two)

| Test | Months | Mean per month | Newey-West t (6 lags) | p (two-sided) | Result |
|---|---|---|---|---|---|
| P1 momentum (WML, 12-1) | 386 | +1.12% | 3.14 | 0.0017 | **Passes** |
| P2 value (HML, book-to-market) | 386 | +0.71% | 2.44 | 0.0146 | **Passes** |

**Pre-registered wording:**

- **Momentum:** "A 12-1 momentum premium existed in Indian equities from 1993 to
  2025 on IIMA's survivorship-adjusted factor (Agarwalla, Jacob and Varma). This
  supports the idea behind our momentum factor; it does not test our scoring."
- **Value:** "A book-to-market value premium existed on the same data, using
  retrospectively updated accounts. It does not test our value, quality or growth
  scores, which remain untested on point-in-time data."

## Secondary (descriptive; no claims drawn)

**Split into two subperiods**

| Factor | Oct 1993 – Dec 2012 | Jan 2013 – Dec 2025 |
|---|---|---|
| WML | +1.12%/mo, t 2.06, p 0.040 | +1.11%/mo, t 3.04, p 0.002 |
| HML | +0.67%/mo, t 1.66, p 0.097 | +0.77%/mo, t 1.88, p 0.061 |

- **Momentum:** about the same size in both halves.
- **Value:** positive in both halves, but in neither half is it below 5% on its
  own. The full-period pass depends on the length of the record; value is the
  weaker and noisier of the two.

**Over the whole period**

| Factor | Compound per year | Positive calendar years | Worst fall |
|---|---|---|---|
| WML | 10.9% | 22 of 31 | −53.5% |
| HML | 6.8% | 21 of 31 | −58.8% |
| SMB | −4.1% | 15 of 31 | −86.1% |
| MF (as published) | 5.7% | 18 of 32 | −75.1% |

- **Size (SMB)** is negative and not significant (t −0.79).
- **Survivorship adjustment:** it changes the WML and HML means by about 0.01% a
  month, so it is negligible here, consistent with the working paper.
- **Both premiums have fallen by more than half from a peak** at some point. A
  premium that exists on average can still lose for years.

## Limits

1. **Not point-in-time for accounts.** IIMA rebuilds the library from each new
   Prowess release. CMIE adds companies and corrects past data between releases
   (IIMA FAQ), so HML uses today's view of past book values.
2. **Different construction from ours:**
   - value-weighted, where our backtests are equal-weighted;
   - total returns with dividends;
   - no trading costs;
   - 30% tails, with size groups at the top 10% by market value.

   The magnitudes are not comparable with Quant India's backtests.
3. **Deferred:** the month-by-month correlation of our 12-1 top-minus-bottom returns
   with WML. It needs a rerun, because the saved record keeps only the months used.
4. **This tests ideas, not our model.** Quality, growth and sentiment are not
   covered by this library at all.
