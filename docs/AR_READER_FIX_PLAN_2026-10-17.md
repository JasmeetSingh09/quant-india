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
