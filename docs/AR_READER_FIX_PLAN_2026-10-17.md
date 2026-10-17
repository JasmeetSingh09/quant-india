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
