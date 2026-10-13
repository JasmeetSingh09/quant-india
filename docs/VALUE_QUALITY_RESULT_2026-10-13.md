# Value and quality test: insufficient data, not run (2026-10-13)

**Verdict under the approved plan (`docs/PREREG_VALUE_QUALITY_REPORTS_2026-10-06.md`, e285f22):
INSUFFICIENT DATA. The tests are not run.** The plan's gate needs at least 80% of eligible company-years
with every input accepted. We have 36.4%. No returns were joined to any accounts; no result exists.
Decision recorded by the owner on 2026-10-13 ("ok" to accepting the plan's verdict).

## Coverage

Eligible company-years: 1,033 (the top 100 by traded value per FY2012–FY2025, financial companies excluded).

| | Company-years | Every input accepted | Value inputs | Quality inputs |
|---|---|---|---|---|
| All | 1,033 | **376 (36.4%)** | 458 (44.3%) | 415 (40.2%) |
| Still trading | 950 | 349 (36.7%) | 425 (44.7%) | 387 (40.7%) |
| Stopped trading | 83 | 27 (32.5%) | 33 (39.8%) | 28 (33.7%) |

By year (every input accepted / eligible): 2012 11/77, 2013 19/76, 2014 24/74, 2015 21/73, 2016 26/76,
2017 20/73, 2018 33/75, 2019 32/74, 2020 29/69, 2021 30/74, 2022 36/75, 2023 36/74, 2024 31/69, 2025 28/74.

## Why the gate can't be met

- **385 company-years have no usable report.** 224 have no file at all, mostly MARUTI 14 years,
  HINDUNILVR 13, ASIANPAINT 13, JUBLFOOD 10, ACC 8. Those companies' sites block scripts or need hand
  clicks, and BSE allows hand downloads only. The remainder are short files (notices, extracts), scanned
  files, or files whose statements could not be located.
- **Even perfect reading of every file on disk would reach about 78%.**
- **272 read company-years still miss an input.** Mostly a figure not printed as one line, or a
  face-value check that fails, often because preference shares are inside share capital.

## How the figures were accepted

Every figure had to pass `research/ar_review.py`: the quote must be on the cited page and contain the
number, AND either the report's own checks pass or independent readers agree.

There were three readers:
1. **The rule reader**, `research/ar_extract.py`.
2. **Claude**, which read all right-year reports by hand.
3. **A blind third reader** (Haiku sub-agents). It saw only the statement pages and the reading rules.
   Its run logs were scanned, and it never opened another reader's answers.

A dispute is settled by a strict majority of readers (commit cf80d92).

The checker rejected the blind reader's fabricated or reassembled quotes. 86 page citations were moved to
the one statement page that holds the exact quoted line; the change is logged.

## Data-integrity findings along the way

- **11 downloaded files were another company's report** and are rejected
  (`manifest/wrong_company_2026-10-06.json`). Examples: Deepak Phenolics for Deepak Nitrite, Mahindra
  Lifespace for M&M, ONGC Videsh for ONGC, Tech Mahindra for M&M. A balance check passes on them, so the
  checker now honours a reader's "reject:" note.
- **The rule reader is unreliable on revenue.** It takes gross revenue where net is required, takes
  "total income", or takes note numbers. It disagreed with the hand reading on 125 revenue figures.

## What this means for the app

- Value and quality stay **untested**. The app already shows them as "not yet testable as we compute it
  (needs accounts as first published)", which remains accurate. No model or wording change is made.
- Only momentum has a validated edge. The approved plan cannot be loosened after seeing coverage. Any
  future value/quality test needs a NEW pre-registration written before any run. If it uses only companies
  with complete reports, it must state the survivorship bias that brings.

## Where everything is

- Readings: `C:\Users\seeraj\quant_data\annual_reports\review_v11\`
  (`*.claude.json`, `*.haiku.json`, `accepted.json`).
- Year confirmations: `manifest/year_confirm_2026-10-06.json`.
- Blind-reader brief, transcripts check and page-fix log: session scratchpad `blind/`.
