# Quant India — Production Data Integrity Audit

- **Snapshot (UTC):** 2026-09-09T10:36:10Z
- **Record generated:** 2026-09-09T10:44:19+00:00
- **Target:** production Postgres, via the read-only endpoint `/health/data-integrity` at https://quant-india.onrender.com
- **Mode:** read-only. No production row was created, altered, repaired, backfilled, normalised or deleted.
- **Model:** V1.4, frozen. No factor formula, weight, threshold, identity mapping or historical observation was changed.

There is deliberately **no single data-health score**. A duplicate price row and an undated article are not the same unit; averaging them would invent a number that hides which half is broken.

## Status by domain

| Domain | Status | Examined | Failed checks |
|---|---|---|---|
| `prices` | **PASS** | rows = 6,598,053 | 0 |
| `continuity` | **FAIL** | day_over_day_steps = 6,593,800 | 1 |
| `identity` | **FAIL** | rows_with_isin = 6,598,053 | 1 |
| `fundamentals_pit` | **FAIL** | corporate_actions = 32,964 | 1 |
| `news` | **FAIL** | articles = 29,710 | 2 |
| `missing_data` | **PASS** | factors = 4 | 0 |

## prices

**Status: PASS**  ·  96.2s

Examined: **rows** = 6,598,053, **securities** = 4,253, **trading_days** = 3,744

| Check | Result | Examined | Defects |
|---|---|---|---|
| close is present | **PASS** | 6,598,053 | 0 |
| open/high/low are present | **PASS** | 6,598,053 | 0 |
| close is positive | **PASS** | 6,598,053 | 0 |
| high >= low | **PASS** | 6,598,053 | 0 |
| close lies within its own high-low range | **PASS** | 6,598,053 | 0 |
| volume is not negative | **PASS** | 6,598,053 | 0 |
| every row carries an ISIN | **PASS** | 6,598,053 | 0 |
| no observation is dated in the future | **PASS** | 6,598,053 | 0 |
| no duplicate (symbol, day) | **PASS** | 6,598,053 | 0 |

- _open/high/low are present_ — a null OHLC is a day that is stored and unusable
- _close lies within its own high-low range_ — the strongest single check on a price row's internal consistency
- _every row carries an ISIN_ — identity is what the corporate-action join is keyed on
- _no observation is dated in the future_ — boundary 2026-09-10; one day of slack because the server clock is UTC and NSE trading days are IST, so today in Mumbai can look like tomorrow to the server
- _no duplicate (symbol, day)_ — enforced by the primary key; checked anyway

## continuity

**Status: FAIL**  ·  77.0s

Examined: **day_over_day_steps** = 6,593,800, **large_moves_examined** = 2,233, **large_moves_total** = 2,233, **distinct_days** = 3,744, **first_day** = 2011-07-04, **last_day** = 2026-09-07

| Check | Result | Examined | Defects |
|---|---|---|---|
| a large move is explained by a corporate action | **FAIL** | 2,233 | 1,667 |

- _a large move is explained by a corporate action_ — moves of at least 40.0% day-over-day; a corporate action on the same ISIN within 3 days counts as explained. 566 explained, 1667 not. An unexplained jump of this size is where momentum goes wrong.

**Offenders — a large move is explained by a corporate action:**

- `KAUSHALYA.NS@2024-02-06 +9933.5%`
- `WINSOME.NS@2023-09-26 +5600.0%`
- `MBECL.NS@2026-09-01 +4072.6%`
- `ARIHANT.NS@2026-04-20 +2188.9%`
- `EASTSILK.NS@2025-08-18 +1300.0%`
- `SUMEETINDS.NS@2025-06-19 +1044.4%`
- `SHEKHAWATI.NS@2024-09-10 +879.9%`
- `VERTOZ.NS@2025-07-11 +849.9%`
- `LCCINFOTEC.NS@2021-03-31 +738.5%`
- `CCCL.NS@2024-09-03 +662.7%`
- `PARASPETRO.NS@2022-12-23 +500.0%`
- `BATLIBOI.NS@2026-04-20 +421.3%`

**calendar_gap_count:**

```json
1
```

**gap_note:**

```json
"Gaps are listed, not failed. NSE holidays are not derivable from this table, so a holiday and a hole look identical here and a human has to tell them apart."
```

## identity

**Status: FAIL**  ·  162.4s

Examined: **rows_with_isin** = 6,598,053, **symbols** = 4,253, **distinct_isins** = 4,342

| Check | Result | Examined | Defects |
|---|---|---|---|
| one symbol means one security | **FAIL** | 4,253 | 549 |
| one ISIN trades under one symbol on any given day | **PASS** | 6,598,053 | 0 |

- _one symbol means one security_ — a symbol carrying two ISINs is two companies in one series
- _one ISIN trades under one symbol on any given day_ — two symbols sharing an ISIN on the same day is a merge error, not a rename -- a rename is sequential and this is not

**Offenders — one symbol means one security:**

- `JBMA.NS (4 ISINs)`
- `ASTRAL.NS (3 ISINs)`
- `AGIIL.NS (3 ISINs)`
- `ALANKIT.NS (3 ISINs)`
- `AMRUTANJAN.NS (3 ISINs)`
- `APCOTEXIND.NS (3 ISINs)`
- `AJANTPHARM.NS (3 ISINs)`
- `ALKYLAMINE.NS (3 ISINs)`

**renames_observed:**

```json
[
 "INE126M01010 -> 6 symbols",
 "INF109K012R6 -> 5 symbols",
 "INF109KA1962 -> 5 symbols",
 "INF346A01034 -> 5 symbols",
 "INE195N01013 -> 4 symbols",
 "INE200A01026 -> 4 symbols",
 "INE878A01011 -> 4 symbols",
 "INE189B01011 -> 4 symbols"
]
```

**note:**

```json
"A rename (one ISIN, several symbols) is normal and is counted, not failed. Ticker reuse (one symbol, several ISINs) is the defect, because it fabricates a continuous history."
```

## fundamentals_pit

**Status: FAIL**  ·  2.4s

Examined: **corporate_actions** = 32,964, **corporate_action_isins** = 2,884, **ex_date_span** = 2011-07-04 .. 2026-09-21, **announced_future_ex_dates** = 13, **factor_inputs** = 481,419

| Check | Result | Examined | Defects |
|---|---|---|---|
| every corporate action carries an ISIN | **PASS** | 32,964 | 0 |
| every corporate action was parsed into a multiplier | **FAIL** | 32,964 | 12,778 |
| every factor input carries an observation time | **PASS** | 481,419 | 0 |
| no factor input was observed in the future | **PASS** | 481,419 | 0 |

- _every corporate action carries an ISIN_ — an action with no ISIN cannot be joined to a price series, so it silently never applies
- _every corporate action was parsed into a multiplier_ — an unparsed action is stored, visible, and has no effect on any price
- _every factor input carries an observation time_ — without one there is no way to say what was knowable when
- _no factor input was observed in the future_ — boundary 2026-09-10 (UTC/IST slack)

**fundamentals_history:**

```json
{
 "stored": false,
 "status": "UNMEASURED",
 "reason": "No point-in-time fundamentals table exists. Valuation and quality inputs are fetched live from Yahoo at scoring time, which returns the statement as it reads today, not as it read on the date being scored.",
 "consequence": "No historical fundamentals PIT audit is possible, and no backtest using these factors can claim to be point-in-time. Only the price and corporate-action layer is PIT."
}
```

## news

**Status: FAIL**  ·  5.5s

Examined: **articles** = 29,710, **securities** = 1,498, **articles_in_cycle** = 29,710, **complete** = 1, **truncated_by_bound** = 0

| Check | Result | Examined | Defects |
|---|---|---|---|
| every scored article names the company it was scored for | **FAIL** | 29,710 | 18,024 |
| no article is published in the future | **PASS** | 29,710 | 0 |
| every article carries a publication date | **PASS** | 29,710 | 0 |
| no article is scored for more than 5 companies | **FAIL** | 24,499 | 148 |

- _every scored article names the company it was scored for_ — re-run through the production matcher, not a copy of it
- _no article is published in the future_ — boundary 2026-09-10 (UTC/IST slack)
- _every article carries a publication date_ — an undated article cannot be time-decayed, so its weight is a guess
- _no article is scored for more than 5 companies_ — a headline attached to dozens of securities is a market story wearing a company's name

**Offenders — every scored article names the company it was scored for:**

- `20MICRONS.NS: Why Is 20 Microns Share Price Falling: Key Reasons and I`
- `20MICRONS.NS: 20 Microns Q1 FY27 Results Preview`
- `20MICRONS.NS: 20 Microns Q2 FY2026 Earnings: Strong EPS of ₹18.94 as R`
- `20MICRONS.NS: 20 Microns Q4 Results FY26 Expectations: PAT to rise 12-`
- `20MICRONS.NS: 20 Microns Ltd. Share Price Today - 20 Microns Ltd. Stoc`
- `20MICRONS.NS: 20 Microns Standalone June 2026 Net Sales at Rs 212.73 c`
- `20MICRONS.NS: 20 Microns Limited Sees Marginal Decline Amid Consolidat`
- `20MICRONS.NS: 20 Microns Q1 FY27 Results: PAT Rs 18 Cr, Revenue Rs 244`
- `20MICRONS.NS: 20 Microns Share Price Target 2026 Bull Bear Case Analys`
- `20MICRONS.NS: 20 Microns Consolidated June 2026 Net Sales at Rs 244.72`

**Offenders — no article is scored for more than 5 companies:**

- `market wrap: bel, hul, icici bank, axis bank (135 companies)`
- `market trading guide: data patterns among fo (134 companies)`
- `ahead of market: 10 things that will decide  (129 companies)`
- `nifty september futures trade at premium (128 companies)`
- `demat additions surge to 3.3 mn as ipo boom  (119 companies)`
- `quick wrap: nifty media index rises 1.31% (119 companies)`
- `closing auction leaves retail options trader (117 companies)`
- `stock market prediction today: sensex, nifty (116 companies)`
- `defence stocks rally as dac clears rs 1.10 l (115 companies)`
- `is a relief rally possible in nifty as rsi n (94 companies)`

**known_defect_sbin_state_bank:**

```json
{
 "mechanism": "CONFIRMED",
 "articles_matching_state_bank_not_india": 0,
 "examples": [],
 "note": "Not fixed in this run. Changing the matcher changes which articles feed sentiment, which changes scores, and V1.4 is frozen."
}
```

**worst_securities:**

```json
[
 "ABSLBANETF.NS: 20/20 off-topic",
 "ABSLNN50ET.NS: 20/20 off-topic",
 "ADANIGREEN.NS: 20/20 off-topic",
 "AGARIND.NS: 20/20 off-topic",
 "ALPHAETF.NS: 20/20 off-topic",
 "AONELIQUID.NS: 20/20 off-topic",
 "AONENIFTY.NS: 20/20 off-topic",
 "AONETMMQ50.NS: 20/20 off-topic",
 "AONETOTAL.NS: 20/20 off-topic",
 "ARSSBL.NS: 20/20 off-topic"
]
```

**relevance_pct:**

```json
39.3
```

**distinct_titles:**

```json
24499
```

**titles_shared_by_more_than_one_security:**

```json
1758
```

**cycle:**

```json
"2026-09-09"
```

## missing_data

**Status: PASS**

Examined: **factors** = 4, **input_rows** = 70,576

| Check | Result | Examined | Defects |
|---|---|---|---|
| no input is missing without saying why | **PASS** | 70,576 | 0 |

- _no input is missing without saying why_ — a value that is absent, not flagged missing and carries no refusal reason is the only one of the five states that is a defect

**note:**

```json
"A missing input with a recorded reason is a limitation. One without a reason is a defect. Zero, NULL, refusal and unavailable are four different things and are not pooled."
```

**per_factor:**

```json
[
 {
  "factor": "momentum",
  "securities": 2704,
  "inputs_recorded": 16354,
  "present": 15964,
  "genuine_zero": 8,
  "flagged_missing": 390,
  "securities_that_refused": 130,
  "unexplained": 0,
  "pct_inputs_missing": 2.38
 },
 {
  "factor": "quality",
  "securities": 2704,
  "inputs_recorded": 18928,
  "present": 18153,
  "genuine_zero": 277,
  "flagged_missing": 775,
  "securities_that_refused": 0,
  "unexplained": 0,
  "pct_inputs_missing": 4.09
 },
 {
  "factor": "sentiment",
  "securities": 2704,
  "inputs_recorded": 10829,
  "present": 10803,
  "genuine_zero": 2704,
  "flagged_missing": 26,
  "securities_that_refused": 13,
  "unexplained": 0,
  "pct_inputs_missing": 0.24
 },
 {
  "factor": "value",
  "securities": 2704,
  "inputs_recorded": 24465,
  "present": 22255,
  "genuine_zero": 706,
  "flagged_missing": 2210,
  "securities_that_refused": 129,
  "unexplained": 0,
  "pct_inputs_missing": 9.03
 }
]
```

**cycle:**

```json
"2026-09-09"
```

