# Quality and value on Kenneth French's factor library: pre-registration

**Written 2026-09-17, before any statistic was computed.** Only the file headers
and first rows were looked at, to confirm the columns and the missing-value code.

## Question

Did the profitability premium (RMW, the standard "quality" factor) and the value
premium (HML) exist in emerging markets, which include India, and in the US?

- **Scope:** the ideas behind our quality and value factors, on independent data.
- **Not tested:** our scores, our formulas or any Quant India result. The Indian
  value premium alone is already recorded separately in
  `IIMA_FACTOR_CHECK_RESULT_2026-09-17.md`.

## Data

**Source:** Kenneth R. French Data Library, Tuck School of Business, Dartmouth.
https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
- **Files:** `Emerging_5_Factors_CSV.zip` (Bloomberg database of 2026-07) and
  `F-F_Research_Data_5_Factors_2x3_CSV.zip` (CRSP database of 2026-07).
- **Data use:** monthly section only, percent per month. The −99.99 code means
  missing and is excluded, never treated as zero.
- **Raw files:** not committed; the script records each file's SHA-256.

**Emerging markets sample, as the library describes it:**
- **Countries:** 24, **including India**. The others are Brazil, Chile, China,
  Colombia, Czech Republic, Egypt, Greece, Hungary, Indonesia, Malaysia, Mexico,
  Kuwait, Peru, Philippines, Poland, Qatar, Saudi Arabia, South Africa, South
  Korea, Taiwan, Thailand, Turkey and the UAE.
- **Returns:** US dollars, with dividends.
- **Sorting:** within each country, at the end of each June.
- **Monthly data:** from July 1989. RMW is missing in its first months.

**Construction, both regions:**
- **RMW:** robust minus weak operating profitability. Operating profitability is
  revenue minus cost of goods sold, SG&A and interest expense, over book equity,
  from the prior fiscal year.
- **HML:** high minus low book-to-market.
- **Portfolios:** 30th and 70th percentile breakpoints, value-weighted.

**Known limits, stated before the results:**
- **Not India alone.** India's share of the emerging sample is not published.
- **Not our definition of quality.** Our quality score combines ROE, free cash
  flow and distress penalties. RMW's operating profitability is the closest
  standard factor, not the same measure.
- **In-sample periods:** the US five-factor model was published with data to 2013
  (Fama and French 2015), and the international tests with data to 2015 (Fama and
  French 2017). Months up to then were part of the evidence that defined these
  factors, so only later months are out-of-sample. Those are reported as their
  own tests below.

## Primary tests (two; Bonferroni, each at 0.025)

| Test | Hypothesis | Sample |
|---|---|---|
| **Q1 emerging quality** | Mean monthly emerging-markets RMW > 0 | Every non-missing month from July 1989 |
| **Q2 US quality** | Mean monthly US RMW > 0 | Every month from July 1963 |

**Statistic:** mean divided by its Newey-West standard error with 6 lags, and a
two-sided normal p-value. This is the same code as the IIMA check
(`research/iima_factor_check.py`).

## Secondary (descriptive; no claims)

1. **Out-of-sample only:**
   - US RMW and HML from January 2014;
   - emerging RMW and HML from January 2016.
2. Emerging-markets HML over its full sample, and US HML over its full sample.
3. **For each primary series:**
   - compound annual return;
   - positive calendar years out of full years;
   - worst peak-to-trough fall.

## Wording decided in advance

- **Q1 passes:** "A profitability (quality) premium existed across emerging
  markets, including India, from 1989 to 2026 on Fama and French's factor. This
  supports the idea behind our quality factor; it does not test our quality
  score, which uses a different measure."
- **Q2 passes:** "The same premium existed in the US from 1963 to 2026."
- **A test fails:** say so, with the same prominence.
- **Out-of-sample:** if the months after publication are near zero or negative,
  that is reported beside the full-sample result. It is never omitted.
