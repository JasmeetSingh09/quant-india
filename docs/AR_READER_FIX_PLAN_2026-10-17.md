# Reader fixes: plan, split and rules (written 2026-10-17, before any case was examined)

**Authorised (owner, 2026-10-17):** "approve the reader fixes first, with strict safeguards …
Test against held-out reports that were not used to tune the changes."

**Not authorised:** deployment, automated BSE collection, and the research run.

**Scope.** Two documented failure groups from `AR_COLLECTION_GAP_2026-10-17.md`:
- **FACE:** 108 read company-years blocked by the face-value check;
- **OCR:** 91 company-years whose file has no statements located (scanned pages, extracts or
  notices).

## 1. The split (fixed before looking)

`research/ar_reader_fix_split.py` → `quant_data/annual_reports/manifest/reader_fix_split_2026-10-17.json`
(sha256_16 `654456353d056d4d`, seed 20261017).

**By company,** not company-year, because a company's layout repeats across years:

| Population | Company-years | Development | Held out |
|---|---|---|---|
| FACE | 108 (50 companies) | 53 (25) | 55 (25) |
| OCR | 91 (58 companies) | 46 (29) | 45 (29) |

**How the split is used:**
- Development cases may be read, diagnosed and tuned on.
- **Held-out cases are not opened** (their pages, readings or check output) until the fixes are
  committed and frozen. They are then run **once**.

## 2. What may change, and what may not

**May change:** how the reader finds and reads a figure, so that the right printed number is
picked. Examples:
- the EPS line;
- share capital net of preference capital, where the note prints both;
- statement pages located in OCR text.

**May not change** (each of these would be loosening):
- the face-value tolerance or the list of standard face values (`ar_extract.face_check`, `FACES`);
- the balance tolerance;
- the grounding rule;
- the majority rule;
- the gross-revenue refusal;
- any acceptance threshold.

**Preference capital.** Where share capital includes preference shares, the equity figure is read
**only from the line the report prints** (the equity share capital line in the note). It is never
computed by subtraction unless both lines are printed.

**OCR is held to a stricter rule than text.** Two readers of the same OCR text would agree on the
same OCR mistake. So a figure from an OCR'd page is accepted only if:
1. it is grounded in the OCR text; **and**
2. it is confirmed independently by a reading of the **page image** itself (rendered from the PDF,
   not the OCR text), or by the report's own checks (balance or face value).

OCR'd figures are tagged `ocr` in `accepted.json` so they can always be told apart.

## 3. How the result is judged (held-out, run once)

1. **No regression.** Every company-year complete today (474) stays complete, with identical
   accepted values. Any regression withdraws the change that caused it.
2. **Gain.** The number of held-out company-years that become complete, reported whatever it is,
   including zero, by population. Development gains are reported separately and never mixed in.
3. **Correctness audit.**
   - Up to 20 newly complete held-out company-years, drawn at random (seed 20261018), are checked
     figure by figure against the printed statements, by the owner or another reader the owner
     approves.
   - **Any wrong accepted figure withdraws the fix that produced it,** and the audit result is
     reported.
4. **No further tuning on the held-out cases** after they are seen. A later change needs a new
   held-out set.

## 4. Order

1. Diagnose FACE development cases. Fix. Re-run the development cases and the no-regression check.
2. Wire OCR, which is installed (Tesseract 5.4, owner-approved 2026-10-05), into the text cache for
   pages with no text layer. Diagnose and fix on OCR development cases. Read page images for the
   independent confirmation.
3. Commit and freeze. Then run the held-out cases once, the no-regression check and the audit draw.
4. Report.

## 5. Phasing and development results (added before any held-out case was run)

**Phasing.** The fixes are frozen and judged in two phases:
- **phase 1:** FACE fixes A and B;
- **phase 2:** OCR.

The two populations and their held-out halves are disjoint, so freezing phase 1 first changes nothing
for phase 2. No OCR case has been examined.

**Phase 1 fixes, diagnosed on development cases only:**
- **A. Units.**
  - Readers' spellings of one unit ("Lakhs", "lacs", "crores", "millions") are merged before voting.
    Agreeing readers had been split, the report's unit came out undetermined, and no check ran.
  - "rupees" is added to the unit table, so reports kept in whole rupees can be checked at all.
- **B. The equity line.** `research/ar_equity_capital.py` reads the equity share capital line from the
  share-capital note. Two conditions apply:
  - it must be internally consistent: count × face value = amount, within 0.5%, with magnitude
    guards;
  - it is used only when the face check fails with the voted figure **and** the implied face value
    then equals the face value that line prints, within the face check's own tolerance.

  That is stricter than the face check. The development cases behind it are TCS and JSW Steel
  (preference capital, forfeited shares, treasury shares) and UPL (a wrong voted figure).

**Unchanged:** the face-value tolerance, the standard face values, the balance tolerance, grounding,
the majority rule and the gross-revenue refusal.

**Development result** (`research/ar_reader_fix_eval.py development`):
- **No regression:** 474 complete company-years, 0 problems; every accepted value is identical.
- **Gain:** **11 of 53** development company-years became complete: DELTACORP 2018, DIVISLAB 2021 and
  2022, INDUSTOWER 2024, and JSWSTEEL 2013, 2014, 2015, 2016, 2018, 2019 and 2022.
- **Equity-line substitutions:** 11.
- **Spot-checked on development:**
  - Divi's share capital is Rs 53.09 crore (Rs 2 shares);
  - Indus Towers is Rs 2,694.9 crore (Rs 10);
  - JSW Steel's implied face values are 0.998–1.003 (Re 1) and 9.82 (Rs 10).
- **Still failing, correctly:** Aban (EPS is after preference dividends), Tata Steel FY2017 (EPS after
  perpetual-bond coupons), and wrong voted figures the check rightly rejects (Grasim FY2022, BHEL
  FY2016).

## 6. Phase 1 held-out result (run once, after the freeze at `7f6a709`)

- **No regression:** 474 complete company-years, 0 problems.
- **Held-out gain:** **3 of 55** company-years became complete (CIPLA 2022 and 2024, ZEEL 2014).
  There was 1 equity-line substitution.
- **Development showed 11 of 53. The held-out result is the honest estimate.** Most of the
  development gain was one company: JSW Steel accounts for 7 of the 11. On companies the fixes never
  saw, the equity-line fix triggered once.
- **Whole collection, frozen fixes** (a scratch run; `review_v11/accepted.json` is **unchanged**):
  - **489 / 1,033 (47.3%)**, up from 474;
  - 15 newly complete: 11 development, 3 held-out, and 1 outside both groups (COALINDIA 2017, via
    the unit merge). List: `docs/audit/reader_fix_phase1_newly_complete_2026-10-17.json`.
- **Correctness audit.**
  - All 15 are audited, since that is under the cap of 20 (seed 20261018).
  - The packet has 105 figures, each with page and printed line:
    `quant_data/annual_reports/manifest/phase1_audit_packet_2026-10-17.md`.
  - **Awaiting the owner, or a reader the owner approves.** Until it passes, the official coverage
    stays 474 and `accepted.json` is not replaced. Any wrong figure withdraws the fix that produced
    it.
- **Phase 2 (OCR):** not started. Its 91 cases are untouched.

## 7. Phase 1 correctness audit and promotion (2026-10-20)

**Auditor (owner's choice, 2026-10-20):** a blind image re-read. A fresh Claude reader saw only the
51 cited page images, rendered at 150 dpi, and a list of items with their definitions. It **never saw
the accepted values**, quotes or earlier readings. It worked in an isolated folder and listed every
file it opened: `tasks.json` and the images only.

This is an independent channel: the page image, not the extracted text. It is still an AI reader,
not the owner's own check.

**Round 1 (values).**
- **All 105 blind readings equal the accepted figures**, current and previous year, with 0
  disagreements.
- 78 figures were correct outright. 27 were unresolved only because the image does not say
  "standalone" or "consolidated".

**Round 2 (statement type from context, the reviewer's rule).**
- The nearest earlier and later pages naming a statement type were shown.
- 14 pages were settled as standalone: they sit between pages marked standalone, or follow a
  standalone auditor's report with no consolidated section in between.
- **The reader's two weak calls** (JSW FY2013 cases 21 and 23, resting only on a consolidated report
  36–40 pages later) **are treated as unclear**, as are the two JSW FY2013 pages with no context.

**Final.**
- **98 correct, 0 incorrect, 7 unresolved** (all JSW Steel FY2013).
- **No fix is withdrawn.**
- 14 of 15 company-years are confirmed. JSW Steel FY2013 stays incomplete.
- Record: `docs/audit/reader_fix_phase1_audit_record_2026-10-20.csv`.

**Promotion.**
- `review_v11/accepted.json` now holds the frozen phase-1 readings, with JSW Steel FY2013's pre-fix
  record kept.
- Backup: `review_v11/accepted_before_phase1_2026-10-20.json`.
- **Coverage: 488 / 1,033 (47.2%)**, up from 474. The gate needs 827, so it is **short by 339**.
- **No-regression on the promoted file:** 474 baseline company-years, 0 problems.

**Notes for the next value/quality pre-registration:**
- **JSW Steel share capital is net of treasury shares** (owner, 2026-10-18).
- **The total-equity subtotal includes preference capital** for JSW Steel FY2013–16 and Zee FY2014.
  For P/B, the pre-registration should say whether preference capital is excluded from book value.
- **Revenue where excise is shown only as an expense line** (Coal India FY2017, JSW Steel FY2018) is
  the printed revenue line, unadjusted.

## 8. Phase 2 development log (not frozen; no held-out case examined)

**What the OCR population really is.** Diagnosis on the 54 development files (`ocr_dev_diag`):
- **Scanned or partly scanned:** 3 files. OCR helps.
- **Garbled text layer:** 3 files (Adani Ent FY2012, Coal India FY2012, ONGC FY2014). Under 10% of the
  words are common English. OCR helps.
- **Short extracts, notices or results:** 17 files. These need the full report, which means a download.
- **Text layer present but the statements not located:** 21 files. Most of these were wrong-year
  files or consolidated or auditor pages, correctly skipped. A few were genuine locator misses.
- **Text present, but no balance-sheet text** at all: 13 files.

**Scope of phase 2, fixed here before any freeze.**
- **2A, OCR** (`research/ar_ocr.py`). It runs on pages with no text layer, and on whole files whose
  text layer is garbled. Garbled means fewer than 10% of words are common English **and** no page
  says "balance sheet". Tesseract 5.4 at 300 dpi, psm 6. It writes to a separate cache,
  `ar_cache_ocr`; the original cache is never modified. Every OCR'd page is listed. Writes are
  atomic and the run resumes, after a 2026-10-20 run was stopped and left one truncated file, now
  quarantined.
- **2B, banner lines** (`ar_extract.head_for_skip`). A line above a statement title that names two
  or more report sections is a running banner (Tata Power: "… at a glance … value creation …
  Financial Statements"). It is ignored by the skip test. A line saying the page is a notes or
  auditor's page is never treated as a banner. That refinement came from a development side effect:
  Jubilant FY2023 p99.

**Locator regression (2026-10-22, after the refinement):**
- **Part 2:** all 489 files behind the 488 complete company-years were re-extracted and re-checked,
  with **0 problems**.
- **Part 1:** 794 non-held-out reports were re-located, and **4 selections changed, all checked by
  page heading and all corrections:**
  - Tata Power FY2024: nothing → its standalone statements;
  - Grasim FY2017: a five-year summary → the balance sheet;
  - ONGC FY2025: a consolidated reconciliation note → the "Standalone Balance Sheet";
  - Tata Motors FY2013: a "summarised balance sheet" → the balance sheet.
- None of them is accepted without an independent reading or passing accounting checks.
- Record: `docs/audit/reader_fix_phase2_locator_regression_2026-10-22.json`.

**OCR development run:** 5 of 12 files complete and verified. The rest, plus the quarantined Coal
India file, resume next. **Tata Power FY2024 stays unresolved.** `accepted.json` is unchanged.
