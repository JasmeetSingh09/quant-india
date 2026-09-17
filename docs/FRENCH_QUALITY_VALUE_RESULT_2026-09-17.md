# Quality and value on Kenneth French's factor library: result

**Run 2026-09-17**, following `PREREG_FRENCH_QUALITY_VALUE_2026-09-17.md`
(committed first, `9729b7d`).

- **Script:** `research/french_quality_value_check.py`
- **Output:** `french_quality_value_check_2026-09-17.json`, with each file's SHA-256.
- **Data:** Kenneth R. French Data Library, files built from the July 2026
  Bloomberg (emerging) and CRSP (US) databases.

## Primary tests (each at 0.025)

| Test | Months | Mean per month | Newey-West t | p | Result |
|---|---|---|---|---|---|
| Q1 emerging-markets quality (RMW), Jul 1991 – Jul 2026 | 421 | +0.23% | 2.53 | 0.012 | **Passes** |
| Q2 US quality (RMW), Jul 1963 – Jul 2026 | 757 | +0.26% | 2.86 | 0.004 | **Passes** |

**Pre-registered wording:**
- "A profitability (quality) premium existed across emerging markets, including
  India, from 1989 to 2026 on Fama and French's factor. This supports the idea
  behind our quality factor; it does not test our quality score, which uses a
  different measure."
- "The same premium existed in the US from 1963 to 2026."

(Emerging-markets RMW data begins in July 1991; the months before it are missing.)

## Out-of-sample: the months after each factor was published

| Series | Months | Mean per month | t | p |
|---|---|---|---|---|
| Emerging RMW, Jan 2016 – Jul 2026 | 127 | +0.27% | 2.15 | 0.031 |
| Emerging HML, Jan 2016 – Jul 2026 | 127 | +0.65% | 2.44 | 0.015 |
| US RMW, Jan 2014 – Jul 2026 | 151 | +0.21% | 1.27 | 0.20 |
| US HML, Jan 2014 – Jul 2026 | 151 | −0.03% | −0.10 | 0.92 |

- **Emerging markets, both factors:** stayed positive after publication, at about
  the size seen before.
- **US quality:** also positive, about the same size, but too noisy over 12 years
  to be significant on its own.
- **US value:** has earned nothing since 2014.

## Full-sample value (HML)

| Region | Months | Mean per month | t | p |
|---|---|---|---|---|
| Emerging | 445 | +0.66% | 4.25 | < 0.0001 |
| US | 757 | +0.30% | 2.32 | 0.020 |

## Size of the quality premium

| Series | Compound per year | Positive years | Worst fall |
|---|---|---|---|
| Emerging RMW | 2.7% | 24 of 34 | −28.8% |
| US RMW | 2.8% | 42 of 62 | −41.8% |

The quality premium is real but small: about 3% a year, before costs.

## Limits

1. **Not India alone.** 24 countries, and India's weight is not published. With
   IIMA's Indian value result, value now has India-specific support; quality
   does not.
2. **Not our measure.** RMW is operating profitability over book equity. Our
   quality score combines ROE, free cash flow and distress penalties.
3. **Construction:** value-weighted, US-dollar returns, no trading costs.
4. **This tests ideas, not Quant India's scores.** Our value and quality scores
   remain untested on point-in-time data.
