# Value and quality validation: where it stands (2026-10-06)

## The short version

The test cannot run yet. This is not because of the code or the rules; it is because of the data.
The plan (`docs/PREREG_VALUE_QUALITY_REPORTS_DRAFT_2026-09-26.md`) requires that at least 80% of the
company-years in the sample have every input accepted before any test is run. We are at 25%.

| | Count | Share of the 1,056 needed |
|---|---|---|
| Company-years the test needs (top 100 by traded value, FY2012–FY2025, financials excluded) | 1,056 | 100% |
| Annual reports on disk | 426 | 40% |
| Reports the rule reader verifies, with the statement year matching the file | 259 | 25% |
| Required by the plan before the test may run | 845 | 80% |

## What was done (2026-10-05 and overnight)

- **Reports collected:** 426 of 1,056, up from 378.
  - Batches 3 to 6 came from the companies' own websites: Tata Motors, UltraTech, Tech Mahindra,
    Power Grid, Cipla, BPCL, Bajaj Auto, Titan, JSW Steel, Adani Ports, Eicher, HPCL,
    Adani Enterprises, Vodafone Idea, BHEL, Ashok Leyland, IOC, Aurobindo, BEL, United Spirits,
    Sun TV, SAIL, Biocon, IndiGo, Divi's, Indus Towers and Tata Consumer.
  - Every file was checked to be a complete PDF.
  - Files whose cover did not match were held. Every held file whose balance sheet could be read
    turned out to be the right year.
- **Reader accuracy, measured honestly:**
  - Fixes made on batch 2 raised it from 85 to 95 of 140.
  - Scored unchanged on 166 reports it had never seen (batch 3), it verified 94 (57%).
  - Out-of-sample accuracy is still about 57–60%.
- **Test runner:** `research/value_quality_test_run.py` is written to the plan, with a self-test of
  16/16 on synthetic data.
  - It enforces the 80% gate.
  - It can run the placebo check before the plan is committed, which the plan allows.
  - It needs one data export from production (month-end prices, share factors and forward returns
    from the factor-test-1 machinery). That export requires a small deploy, which was deliberately
    not done unattended.
- **OCR** (Tesseract) is installed for scanned reports.

## Why it has been stuck, plainly

1. **Old years and collapsed companies are not on company websites.** About 630 of the missing
   reports are mostly FY2012–2016 and companies that stopped trading (Jet Airways, RCOM, HDIL, DHFL
   and others). Company sites cannot supply them.
2. **The only complete source is BSE,** and automated BSE downloads are not allowed without
   permission. The permission request is already drafted in Gmail, unsent.
3. **Two figures need a second reader for every report.** Revenue and operating cash flow are not
   covered by any check the report can perform on itself, so under the plan they count only when two
   readers agree. That is about 430 reports to second-read once the collection is complete. The tool
   exists (`research/ar_review.py`).

## Decisions that would unstick it

1. **Send the BSE permission email** (owner). If BSE agrees, the missing reports can be collected
   in a day or two instead of weeks.
2. **If BSE declines or does not answer:** the remaining reports would have to be clicked by hand
   from BSE, using the URL pattern in `quant_data/annual_reports/report_links.html`. That is about
   630 clicks.
3. **Jasmeet's sign-off** on the plan. It includes the owner's Piotroski point-5 decision of
   2026-10-05.
4. **Do not lower the 80% gate to make the test run.** With about 75 eligible companies a month and
   a 50-stock minimum, a test on partial data would mostly measure which companies happen to publish
   old reports online. That is survivorship bias, and it is the thing the gate exists to stop.

## Hand-download list (sites that block scripts or hide older years)

- **Asian Paints:** custom widget.
- **Jindal Steel:** page redirects.
- **Lupin:** page redirects.
- **Dr Reddy's:** page returns 404.
- **NTPC:** CAPTCHA.
- **Infosys, HUL:** refuse scripts.
- **M&M:** anti-bot page.
- **Bajaj Auto:** 6 damaged files.
- **Older years only:**
  - Aurobindo before FY2022;
  - Jubilant before FY2023;
  - Zee except FY2015;
  - UPL and Motherson before FY2026;
  - Tata Consumer before FY2022.
