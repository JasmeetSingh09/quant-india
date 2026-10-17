# Annual-report collection: the gap to the 80% gate, and a coverage audit (2026-10-17)

**Owner order (2026-10-17):** security first, then research. This document covers research steps 2
(the collection gap) and 3 (the coverage audit).

**Read-only.** Nothing was downloaded, fetched or sent. The model is unchanged, and report-based
figures stay separate from live scoring.

**Reproducible:**
- `research/ar_gap_list.py` reproduces the coverage count of `VALUE_QUALITY_RESULT_2026-10-13.md`
  with the same eligibility, the same financial-company list and the same acceptance rule.
- It writes `quant_data/annual_reports/manifest/gap_list_2026-10-17.csv`, one row per incomplete
  company-year.

## 1. Where coverage stands (reconciled)

| | Company-years |
|---|---|
| Eligible: top 100 by traded value, FY2012–FY2025, financials excluded | **1,033** |
| Every value and quality input accepted | **474 (45.9%)**, unchanged since 2026-10-14 |
| The gate (80%) needs | **827** |
| **Short by** | **353** |

## 2. Why the 559 incomplete company-years are incomplete (one cause each)

| Cause | Count | What fixes it |
|---|---|---|
| **Read, an input not accepted:** a right-year report was read, but a figure failed grounding, agreement or a check | **173** | Reader or validation work on files already held. No download |
| **File on disk, not usable** | **166** | A better copy, or OCR for scanned ones |
| … no statements located (scanned pages, an extract or a notice) | 91 | OCR, which is installed but not wired into the reader; otherwise a full copy |
| … year not confirmed | 33 | A check of the statement header, or a new copy |
| … another company's report | 8 | The right report |
| … statements inside are a different year | 34 | The right year's report |
| **No file at all** | **220** | A download |

**The arithmetic.** If **every one** of the 173 read-incomplete company-years were fixed, coverage
would reach **647 (62.6%)**. **The gate cannot be reached without at least about 180 more usable
reports.** Downloads are required, not optional.

**Where the downloads would come from** (386 company-years, 148 companies):

| Route | No file | Unusable file | How |
|---|---|---|---|
| BSE's annual-report archive, **by hand** | 136 | 98 | The owner downloads. BSE's terms forbid automation, and the `bse_access` pause enforces that |
| The company's site, hand-only (blocks scripts, CAPTCHA, clicks) | 47 | 34 | The owner clicks. No block or CAPTCHA is ever bypassed |
| The company's own site, known to serve files | 37 | 34 | Automated header-checked download, as in batches 1–6. Each batch needs the owner's yes |

**Priority used:**
- **P1:** companies the sample marks as stopped trading. They carry the survivorship test.
- **P2:** FY2012–2015, the thinnest years (11–24 complete out of about 75 each).
- **P3:** the rest.

**Caveat.** P1 follows the sample's own `status` field. For some (Dr Reddy's, BEML, HEG, TTK
Prestige) that probably reflects an **ISIN change after a share split, not a delisting**. They are
listed as the field says; this is not reclassified by hand.

## 3. The coverage audit: inputs missing in the 173 read company-years

| Missing input | Company-years |
|---|---|
| Face-value check failed | 108 (30 of them miss nothing else) |
| Total equity | 78 |
| Operating cash flow | 65 |
| Revenue | 58 |
| EPS | 52 |
| Profit for the year | 47 |
| Share capital | 37 |
| Total assets | 35 |

**Proposed reader work, against documented failures only. No acceptance rule is loosened.**

1. **The face-value check (30 company-years blocked by it alone).** The 2026-10-14 reading found two
   kinds of failure:
   - a wrong input winning the vote (for example Hero's EPS read as face value "2");
   - genuine preference or perpetual capital inside share capital.

   A fix must separate the two on the printed note, not relax the check.
2. **OCR for the 91 "no statements located" files.** Tesseract is installed (owner-approved
   2026-10-05) but not wired in. Every OCR'd figure would still need grounding plus a second reader.
3. **Any reader change is scored on files it was not tuned on**, as in batches 1–3, before it
   counts.

## 4. What reaching 80% does and does not mean

- **The approved plan has already recorded its verdict:** "insufficient data, not run", accepted by
  the owner on 2026-10-13. That note says **any future value/quality test needs a new
  pre-registration, written before any run.**
- More coverage therefore **permits** a new pre-registration. It does not reopen the old one. The new
  one may reuse the old rules unchanged, but it must be written, committed and approved first.
- Coverage alone **proves nothing about the factors.** A test still needs:
  - point-in-time correctness: report dates and the 9-month lag;
  - data quality;
  - the pre-set statistics;
  - robustness.

## 5. The BSE permission request: correction needed before sending

The existing draft (`quant_data/annual_reports/BSE_permission_request_DRAFT.txt`, also a Gmail draft,
unsent) describes the project as **a student's non-commercial school project** for ISEF and Wharton.

The project record says Quant India is **the owner's own app**, not the ISEF project. A request that
misstates who uses the data, and for what, could void any permission it wins.

A corrected version with the facts to confirm marked in brackets is at
`quant_data/annual_reports/BSE_permission_request_DRAFT_v2_2026-10-17.txt`. **Nothing is sent.** The
owner confirms the facts and sends it, or not.

## 6. Download checklist by company

Sorted by priority, then by the number of years a single visit recovers. Full detail per company-year
is in the CSV.

| Priority | Company | Years needed | Route | Why |
|---|---|---|---|---|
| P1 | RANBAXY | 4: FY2012, FY2013, FY2014, FY2015 | bse_by_hand | no file |
| P1 | CAIRN | 3: FY2012, FY2015, FY2017 | bse_by_hand | no file; no statements located |
| P1 | DRREDDY | 3: FY2020, FY2023, FY2024 | hand_only_site | site 404s |
| P1 | HDIL | 3: FY2015, FY2017, FY2018 | bse_by_hand | no file; no statements located |
| P1 | PCJEWELLER | 3: FY2018, FY2019, FY2020 | bse_by_hand | no file |
| P1 | BEML | 2: FY2018, FY2019 | bse_by_hand | no file; statements inside are FY2020 |
| P1 | FEL | 2: FY2012, FY2013 | bse_by_hand | another company's report; year not confirmed |
| P1 | HEG | 2: FY2018, FY2019 | bse_by_hand | no statements located |
| P1 | JETAIRWAYS | 2: FY2012, FY2019 | bse_by_hand | statements inside are FY2013; statements inside are FY2020 |
| P1 | LITL | 2: FY2012, FY2013 | bse_by_hand | no file |
| P1 | TTKPRESTIG | 2: FY2012, FY2013 | bse_by_hand | no file |
| P1 | ABIRLANUVO | 1: FY2017 | bse_by_hand | no file |
| P1 | GITANJALI | 1: FY2013 | bse_by_hand | year not confirmed |
| P1 | HEXAWARE | 1: FY2014 | bse_by_hand | year not confirmed |
| P1 | IVRCLINFRA | 1: FY2012 | bse_by_hand | statements inside are FY2011 |
| P1 | JPASSOCIAT | 1: FY2014 | bse_by_hand | year not confirmed |
| P1 | MINDTREE | 1: FY2023 | bse_by_hand | no file |
| P1 | NAUKRI | 1: FY2021 | bse_by_hand | no file |
| P1 | RUSHIL | 1: FY2012 | bse_by_hand | no file |
| P1 | SATYAMCOMP | 1: FY2013 | bse_by_hand | no file |
| P1 | SINTEX | 1: FY2012 | bse_by_hand | no file |
| P1 | STER | 1: FY2012 | bse_by_hand | statements inside are FY2013 |
| P2 | MARUTI | 14: FY2012, FY2013, FY2014, FY2015, FY2016, FY2017, FY2018, FY2019, FY2020, FY2021, FY2022, FY2023, FY2024, FY2025 | hand_only_site | URL pattern failed |
| P2 | ASIANPAINT | 13: FY2013, FY2014, FY2015, FY2016, FY2017, FY2018, FY2019, FY2020, FY2021, FY2022, FY2023, FY2024, FY2025 | hand_only_site | custom widget |
| P2 | BAJAJ-AUTO | 13: FY2012, FY2013, FY2014, FY2015, FY2016, FY2017, FY2019, FY2020, FY2021, FY2022, FY2023, FY2024, FY2025 | hand_only_site | files served were not valid PDFs |
| P2 | HINDUNILVR | 13: FY2013, FY2014, FY2015, FY2016, FY2017, FY2018, FY2019, FY2020, FY2021, FY2022, FY2023, FY2024, FY2025 | hand_only_site | returns 403 to scripts |
| P2 | JUBLFOOD | 10: FY2012, FY2013, FY2014, FY2016, FY2017, FY2018, FY2019, FY2020, FY2021, FY2022 | company_site | no file |
| P2 | ACC | 8: FY2012, FY2013, FY2014, FY2015, FY2019, FY2020, FY2021, FY2023 | bse_by_hand | no file |
| P2 | EMBDL | 8: FY2012, FY2013, FY2014, FY2015, FY2016, FY2017, FY2018, FY2022 | bse_by_hand | no file |
| P2 | JINDALSTEL | 8: FY2012, FY2013, FY2017, FY2018, FY2020, FY2021, FY2022, FY2023 | hand_only_site | needs clicks |
| P2 | RCOM | 8: FY2012, FY2013, FY2014, FY2015, FY2016, FY2017, FY2018, FY2019 | bse_by_hand | no file |
| P2 | RELINFRA | 8: FY2012, FY2013, FY2014, FY2015, FY2016, FY2017, FY2018, FY2019 | bse_by_hand | no file |
| P2 | JUSTDIAL | 7: FY2014, FY2015, FY2016, FY2017, FY2018, FY2019, FY2020 | bse_by_hand | no file |
| P2 | HCLTECH | 6: FY2012, FY2013, FY2014, FY2015, FY2016, FY2017 | company_site | no file |
| P2 | RELIANCE | 6: FY2012, FY2013, FY2014, FY2015, FY2016, FY2019 | company_site | no file |
| P2 | AMBUJACEM | 5: FY2012, FY2013, FY2014, FY2016, FY2023 | bse_by_hand | no statements located; year not confirmed |
| P2 | DLF | 5: FY2012, FY2018, FY2019, FY2020, FY2022 | company_site | no file |
| P2 | HINDPETRO | 5: FY2012, FY2017, FY2018, FY2019, FY2024 | company_site | no statements located |
| P2 | M&M | 5: FY2012, FY2013, FY2016, FY2023, FY2024 | hand_only_site | filter posts through /antibot |
| P2 | ONGC | 5: FY2012, FY2014, FY2016, FY2021, FY2025 | company_site | another company's report; no file |
| P2 | BHARTIARTL | 4: FY2014, FY2015, FY2017, FY2022 | company_site | no file; year not confirmed |
| P2 | NTPC | 4: FY2012, FY2016, FY2017, FY2018 | hand_only_site | Radware CAPTCHA (never solved by a script) |
| P2 | TVSMOTOR | 4: FY2015, FY2016, FY2017, FY2023 | bse_by_hand | no file |
| P2 | APOLLOTYRE | 3: FY2014, FY2016, FY2018 | bse_by_hand | no file; no statements located |
| P2 | BATAINDIA | 3: FY2012, FY2013, FY2020 | bse_by_hand | no file; year not confirmed |
| P2 | BHARATFORG | 3: FY2015, FY2016, FY2017 | bse_by_hand | no statements located |
| P2 | LUPIN | 3: FY2015, FY2019, FY2021 | hand_only_site | needs clicks |
| P2 | MOTHERSON | 3: FY2015, FY2017, FY2021 | bse_by_hand | statements inside are FY2014; statements inside are FY2018 |
| P2 | POWERGRID | 3: FY2012, FY2013, FY2014 | company_site | no statements located |
| P2 | DISHTV | 2: FY2012, FY2016 | bse_by_hand | no file |
| P2 | IGL | 2: FY2013, FY2021 | bse_by_hand | no file |
| P2 | JISLJALEQS | 2: FY2012, FY2018 | bse_by_hand | no file; year not confirmed |
| P2 | RPOWER | 2: FY2012, FY2013 | bse_by_hand | no statements located; statements inside are FY2014 |
| P2 | STAR | 2: FY2013, FY2019 | bse_by_hand | no file; no statements located |
| P2 | SUNTV | 2: FY2012, FY2013 | company_site | no file |
| P2 | UBL | 2: FY2013, FY2014 | bse_by_hand | no file |
| P2 | UNITDSPR | 2: FY2013, FY2014 | bse_by_hand | no statements located; year not confirmed |
| P2 | ADANIENT | 1: FY2012 | bse_by_hand | no statements located |
| P2 | BFUTILITIE | 1: FY2012 | bse_by_hand | year not confirmed |
| P2 | COALINDIA | 1: FY2012 | bse_by_hand | no statements located |
| P2 | DELTACORP | 1: FY2012 | bse_by_hand | no file |
| P2 | EICHERMOT | 1: FY2015 | company_site | year not confirmed |
| P2 | GMRAIRPORT | 1: FY2015 | bse_by_hand | no file |
| P2 | LOVABLE | 1: FY2012 | bse_by_hand | no file |
| P2 | RENUKA | 1: FY2012 | bse_by_hand | statements inside are FY2013 |
| P2 | SUNPHARMA | 1: FY2014 | bse_by_hand | no statements located |
| P2 | ULTRACEMCO | 1: FY2015 | bse_by_hand | statements inside are FY2014 |
| P2 | VIPIND | 1: FY2012 | bse_by_hand | no statements located |
| P2 | WOCKPHARMA | 1: FY2013 | bse_by_hand | no statements located |
| P3 | ZEEL | 7: FY2017, FY2018, FY2019, FY2020, FY2021, FY2023, FY2024 | company_site | no file; no statements located |
| P3 | COFORGE | 5: FY2019, FY2022, FY2023, FY2024, FY2025 | bse_by_hand | no file |
| P3 | DMART | 5: FY2018, FY2019, FY2020, FY2022, FY2023 | bse_by_hand | no file |
| P3 | ESCORTS | 5: FY2018, FY2019, FY2020, FY2021, FY2022 | bse_by_hand | no file; no statements located |
| P3 | INFY | 5: FY2018, FY2020, FY2022, FY2023, FY2025 | hand_only_site | returns 403 to scripts |
| P3 | UPL | 5: FY2019, FY2020, FY2021, FY2022, FY2023 | bse_by_hand | no file |
| P3 | ETERNAL | 4: FY2022, FY2023, FY2024, FY2025 | bse_by_hand | no file |
| P3 | PAYTM | 4: FY2022, FY2023, FY2024, FY2025 | bse_by_hand | no file |
| P3 | ADANIPOWER | 3: FY2023, FY2024, FY2025 | bse_by_hand | no file; no statements located |
| P3 | APOLLOHOSP | 3: FY2020, FY2022, FY2023 | bse_by_hand | no statements located; statements inside are FY2023 |
| P3 | CEATLTD | 3: FY2016, FY2017, FY2018 | bse_by_hand | no file; no statements located |
| P3 | HINDALCO | 3: FY2023, FY2024, FY2025 | company_site | no statements located |
| P3 | MAZDOCK | 3: FY2023, FY2024, FY2025 | bse_by_hand | no statements located |
| P3 | SAIL | 3: FY2019, FY2020, FY2021 | company_site | no file; no statements located |
| P3 | ASHOKLEY | 2: FY2017, FY2019 | company_site | statements inside are FY2018; statements inside are FY2020 |
| P3 | BRITANNIA | 2: FY2021, FY2023 | bse_by_hand | no file; statements inside are FY2022 |
| P3 | COCHINSHIP | 2: FY2024, FY2025 | bse_by_hand | no statements located |
| P3 | DABUR | 2: FY2019, FY2021 | bse_by_hand | no file; statements inside are FY2012 |
| P3 | DEEPAKNTR | 2: FY2022, FY2023 | bse_by_hand | another company's report |
| P3 | DIXON | 2: FY2024, FY2025 | bse_by_hand | no file |
| P3 | GRAPHITE | 2: FY2018, FY2019 | bse_by_hand | no file |
| P3 | INDIGO | 2: FY2016, FY2019 | company_site | no statements located |
| P3 | INDUSTOWER | 2: FY2021, FY2025 | company_site | no file; statements inside are FY2020 |
| P3 | IRCTC | 2: FY2020, FY2024 | bse_by_hand | no statements located |
| P3 | MRF | 2: FY2017, FY2021 | bse_by_hand | no file |
| P3 | NESTLEIND | 2: FY2020, FY2021 | bse_by_hand | no statements located; year not confirmed |
| P3 | NHPC | 2: FY2024, FY2025 | bse_by_hand | no file |
| P3 | PERSISTENT | 2: FY2024, FY2025 | bse_by_hand | no file; no statements located |
| P3 | RVNL | 2: FY2024, FY2025 | bse_by_hand | no file |
| P3 | TATAELXSI | 2: FY2017, FY2019 | bse_by_hand | no file; no statements located |
| P3 | TATAPOWER | 2: FY2021, FY2024 | bse_by_hand | no statements located |
| P3 | TCS | 2: FY2017, FY2025 | bse_by_hand | no statements located; year not confirmed |
| P3 | VOLTAS | 2: FY2021, FY2025 | bse_by_hand | no file |
| P3 | ABB | 1: FY2025 | bse_by_hand | no file |
| P3 | ABREL | 1: FY2017 | bse_by_hand | another company's report |
| P3 | ADANIENSOL | 1: FY2025 | bse_by_hand | no statements located |
| P3 | ADANIGREEN | 1: FY2023 | bse_by_hand | no statements located |
| P3 | AMBER | 1: FY2025 | bse_by_hand | no statements located |
| P3 | AUROPHARMA | 1: FY2019 | company_site | statements inside are FY2020 |
| P3 | BIOCON | 1: FY2019 | company_site | no statements located |
| P3 | BPCL | 1: FY2022 | bse_by_hand | no statements located |
| P3 | CCAVENUE | 1: FY2019 | bse_by_hand | no file |
| P3 | FORTIS | 1: FY2018 | bse_by_hand | no statements located |
| P3 | GLENMARK | 1: FY2021 | bse_by_hand | no statements located |
| P3 | GODREJPROP | 1: FY2022 | bse_by_hand | year not confirmed |
| P3 | GRASIM | 1: FY2020 | bse_by_hand | statements inside are FY2003 |
| P3 | GRSE | 1: FY2025 | bse_by_hand | no statements located |
| P3 | HAL | 1: FY2024 | bse_by_hand | statements inside are FY2025 |
| P3 | HAVELLS | 1: FY2021 | bse_by_hand | no statements located |
| P3 | HFCL | 1: FY2025 | bse_by_hand | no file |
| P3 | IDEA | 1: FY2021 | company_site | year not confirmed |
| P3 | INDHOTEL | 1: FY2023 | bse_by_hand | no file |
| P3 | INDIACEM | 1: FY2018 | bse_by_hand | no file |
| P3 | IOC | 1: FY2020 | bse_by_hand | no statements located |
| P3 | IRCON | 1: FY2024 | bse_by_hand | no statements located |
| P3 | KALYANKJIL | 1: FY2025 | bse_by_hand | no statements located |
| P3 | KAYNES | 1: FY2025 | bse_by_hand | no statements located |
| P3 | NATIONALUM | 1: FY2022 | bse_by_hand | no statements located |
| P3 | NBCC | 1: FY2025 | bse_by_hand | no statements located |
| P3 | NMDC | 1: FY2022 | bse_by_hand | no file |
| P3 | NYKAA | 1: FY2023 | bse_by_hand | no file |
| P3 | OLAELEC | 1: FY2025 | bse_by_hand | no file |
| P3 | OLECTRA | 1: FY2024 | bse_by_hand | statements inside are FY2025 |
| P3 | PAGEIND | 1: FY2019 | bse_by_hand | no file |
| P3 | PATANJALI | 1: FY2023 | bse_by_hand | no statements located |
| P3 | POLYCAB | 1: FY2025 | bse_by_hand | no statements located |
| P3 | PVRINOX | 1: FY2021 | bse_by_hand | no file |
| P3 | RAIN | 1: FY2018 | bse_by_hand | no file |
| P3 | SIEMENS | 1: FY2025 | bse_by_hand | no file |
| P3 | SJVN | 1: FY2024 | bse_by_hand | no file |
| P3 | SRF | 1: FY2023 | bse_by_hand | no statements located |
| P3 | SWIGGY | 1: FY2025 | bse_by_hand | no file |
| P3 | TATACHEM | 1: FY2021 | bse_by_hand | statements inside are FY2022 |
| P3 | TATACONSUM | 1: FY2020 | company_site | statements inside are FY2022 |
| P3 | TMPV | 1: FY2016 | bse_by_hand | year not confirmed |
| P3 | TORNTPHARM | 1: FY2021 | bse_by_hand | no file |
| P3 | TRENT | 1: FY2025 | bse_by_hand | no file |
| P3 | VBL | 1: FY2023 | bse_by_hand | year not confirmed |
| P3 | VEDL | 1: FY2024 | company_site | no statements located |
