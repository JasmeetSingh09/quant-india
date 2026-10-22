# Phase 2 locator change: every changed page selection (2026-10-22)

**Code:** `research/ar_extract.head_for_skip` in commit `cb61b15`, with the notes/auditor refinement.

**Run:** the refined regression run, completed 2026-10-22 **before** the OCR run was resumed.

**Scope:**
- **Part 1:** 794 already-read reports were re-located. Held-out FACE and OCR case files were excluded.
- **Part 2:** all 489 files behind the 488 complete company-years were re-extracted and re-checked.

**Result.** Part 2 found **0 problems**: every accepted figure is identical. Part 1 found **4 changed
selections**. In each case below, both the old and the new page were inspected by their printed
heading text.

## The four changes in the refined run

| Report | Old selection (page: printed heading) | New selection (page: printed heading) | Assessment |
|---|---|---|---|
| Tata Power FY2024 | nothing located | p300 "Standalone Balance Sheet as at March 31, 2024"; p302 "Standalone Statement of Profit and Loss"; p304 "Standalone Cash Flow Statement" | **Intended fix.** A running banner ("… at a glance … value creation … Financial Statements") had made all three pages look like summary pages. The figures remain **unresolved**: the rule reader's values fail the balance and face checks, and no independent reading exists yet |
| ONGC FY2025 | BS p674, P&L p675: "Reconciliation of restated items of Balance Sheet …", inside the CONSOLIDATED section (the reversed side tab reads "DETADILOSNOC") | p271 "Standalone Balance Sheet as at March 31, 2025"; p273 "Standalone Statement of Profit and Loss …"; p276 "Standalone Statement of Cash Flows …" | **Correction.** The banner ignored above p271 is "Overview Annexures to the Board's Report Consolidated Financial Statements", a list of sections, not the page's own type |
| Grasim FY2017 | BS p31: a five-year summary ("Balance Sheet 2015-16 2014-15 2013-14 2012-13") | p132 "BALANCE SHEET As At 31st March, 2017" | **Correction.** The old page was a summary table |
| Tata Motors FY2013 | BS p42: "COMPANY (STANDALONE) SUMMARISED BALANCE SHEET" | p122 "BALANCE SHEET AS AT MARCH 31, 2013", with p123 for the P&L and p124 for the cash flow | **Correction.** The old page was the summarised version |

## The first-run side effect, and why it is gone

**Jubilant FoodWorks FY2023.** The first, unrefined run selected **p99** as a balance sheet. That
page's running header reads "Integrated Report 2022-23 Notes forming part of the standalone financial
statements". It is a **notes** page (Note 16, treasury shares).

**Cause.** The header names two report sections, so the first rule treated it as a banner and dropped
the "Notes forming part" text that should have triggered the skip.

**Refinement.** A line saying what the page itself is ("Notes to …", "Notes forming part of …", an
auditor's page) is never treated as a banner. In the refined run Jubilant FY2023's selection is
**unchanged from before the fix**, so its proper exclusion is restored. It does not appear among the
changes.

## What none of this does

- No changed selection makes anything accepted. Each of the four still needs an independent figure
  reading, or the report's own accounting checks, before any figure counts.
- `review_v11/accepted.json` is unchanged.
- No held-out case was opened.
