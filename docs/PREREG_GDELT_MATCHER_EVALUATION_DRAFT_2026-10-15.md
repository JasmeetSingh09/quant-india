# Pre-registration DRAFT: evaluating the GDELT company matcher (sentiment, stage 3)

**Status: DRAFT, awaiting owner approval.** Nothing has been sampled, labelled or measured for this
document.

**Binding order:**
1. The owner approves this text.
2. It is committed.
3. The matcher version it names is committed.
4. Only then is any evaluation day read.

No production system is touched. No return is computed. The app's own news matcher and the frozen
model (v1.6.0) are not changed.

**Purpose.** Decide, by criteria fixed now, whether a research matcher attributes GDELT headlines to
the right listed company reliably enough to support a sentiment **return** test. This document tests
**attribution only**. Whether sentiment predicts returns is a later, separate pre-registration, and
it runs only if this one passes.

---

## 1. What has already happened (disclosed, not hidden)

| Step | Days of month examined | Result |
|---|---|---|
| The app's own matcher on GDELT (stage 2, 2026-09-26) | 1, 11, 21 (249 days) | About 10% of matches correct. OIL alone took 225,686 of 588,558 matches |
| Strict matcher, attempts 0 and 1 | 1, 11, 21 (development) | Withdrawn **before labelling**: an organisation-list rule and a coding bug |
| Strict attempt 2 (seed 20260928) | 6, 16, 26 | **Failed:** 78.3% (95% CI 73.3–82.6) |
| Strict attempt 3 (seed 20260929) | 3, 13, 23 | **Failed:** 88.0% (83.8–91.2) |
| Strict attempt 4 (seed 20260930), commit `00bb4e0` | 9, 19, 29 | **Failed narrowly:** 89.3% (85.3–92.3). Errors: 12 clear rule gaps, 9 not about the business, 6 passing or industry mentions, 5 separate relatives |

**The gate those attempts used,** committed before each was labelled: precision ≥ 90% **and** a 95%
Wilson lower bound ≥ 85%, on 300 random matches.

**What those attempts did not measure:**
- **Recall** (headlines about a listed company that the matcher missed);
- results **by ambiguity category**;
- **agreement** between independent labellers. Every label so far came from one reader.

**The risk this creates is a winner's curse.** The matcher was revised three times after reading
labelled errors. Further revise-and-retest cycles would eventually pass by chance alone. This
evaluation is therefore designated the **final attempt** (section 9).

## 2. The matcher under evaluation (owner chooses one before freezing)

- **M-4:** the attempt-4 matcher exactly as committed (`00bb4e0`). It gets no further change.
- **M-5:** M-4 plus fixes for the **12 errors labelled "rule_gap_clear" in attempt 4**, and nothing
  else.
  - The fixes are written, committed and listed in section 10 **before** any evaluation day is read.
  - They may use only the attempt-4 labelled file. No evaluation-day headline may be looked at.

**Recommendation: M-5.** The 12 gaps were identified as mechanical misses before this protocol
existed. Fixing them and then testing once on untouched days, with a hard stop, is a single
development step. It is not iterating toward a pass. M-4 is the more conservative choice if the
owner prefers no change at all.

**Whichever is chosen, the matcher is frozen by commit hash.** The evaluation script refuses to run
if `research/gdelt_strict.py` differs from that commit.

## 3. Evaluation data

- **Days:** only days of the month **5, 15 and 25**, in every month from 2019-09-22 (when GDELT titles
  begin) to 2026-09-16. None of these days has been read in any earlier step.
- **Reserve:** days **2, 12 and 22** stay untouched for any later confirmation. Nothing in this
  protocol reads them.
- **Headlines:** unique titles as `gdelt_strict.sample` reads them, with duplicate titles counted
  once.
- **Missing GDELT files are missing, not zero.** Known gaps include 2025-06-15 to 07-01. The run
  reports which evaluation days have no files.
- **Company list:** the 204 names in `~/quant_data/gdelt_names.json` (sha256 recorded at freeze).
  - These are **current** listings, so a company that delisted during 2019–2026 is absent. That
    survivorship limit carries into any return test and is stated there.

## 4. The three samples (drawn by script, seed 20261016, written to files before any labelling)

1. **P, precision sample: 600 matches,** drawn at random from all matcher output on the evaluation
   days.
2. **C, candidate-miss sample: 600 headlines** that contain a **loose candidate term** for at least one
   of the 204 companies but that the matcher did **not** assign.
   - A loose candidate term is any case-insensitive word or phrase from that company's full name,
     its hand-listed short names, or its ticker. It includes ordinary words, by design.
   - The candidate rule is written into the script and frozen with it.
3. **R, residual sample: 1,000 headlines** with **no** candidate term, drawn at random. This
   estimates misses the candidate rule could not see. They are expected to be rare.

**The sampling script also records each stratum's total population:** matched headlines,
candidate-but-unmatched, and no candidate. This lets the estimates be reweighted to the whole
evaluation set.

## 5. Ambiguity categories (assigned mechanically, before labelling)

Every company is placed in **exactly one** of these categories, in this order of precedence, by a
rule in the script. The list of which company is in which category is written to a file and frozen
with the samples.

| Category | Rule |
|---|---|
| **A. Common-word names** | The full name or ticker contains an ordinary English word that a headline could use with its everyday meaning (for example Oil India, Idea, Trent, Titan, Indigo). Assigned by a fixed word list, frozen with the script |
| **B. Group-name companies** | The name starts with a group name shared by several listed companies (Tata, Adani, Reliance, Bajaj, Mahindra, Birla, Godrej, Hindustan, Hero, Aditya) |
| **C. Short tickers and acronyms** | Matched mainly through a ticker or acronym of 4 characters or fewer (SBI, HAL, BEL, LIC, TCS...) |
| **D. Distinctive names** | Everything else |

**Each headline in P and C also gets two mechanical flags:**
- **multi-company:** it contains terms for 2 or more companies;
- **parent-or-relative word:** it contains one of the relative cue words listed in `gdelt_strict.py`.

## 6. Labelling (blind, independent, with the guide fixed now)

**The question each labeller answers for a headline:** "Which of the 204 companies, if any, is this
headline **about**? That means news about the company's own business, shares, results, management
or deals."
- They may answer **none**, or list several companies.
- **Not about the company:**
  - passing mentions;
  - list headlines ("stocks to watch: A, B, C...");
  - separately incorporated relatives (Reliance Jio, HDFC Securities, ONGC Videsh...);
  - research or economist forecasts by the company's staff about the economy;
  - a person named after the company;
  - everyday uses of the word.

This guide continues the earlier attempts' guide. It is restated here and not changed afterwards.

**Blind.** Labellers see the headline, the source domain and the date, plus the full list of the
204 companies. They do **not** see the matcher's decision, which sample the headline came from, or
its category.

**Independent readers.** All 2,200 headlines are labelled by **two independent readers**:
- **Reader 1:** a Claude instance with no access to the matcher, the samples' origin or the other
  reader's labels;
- **Reader 2:** a second, separate Claude instance, under the same conditions;
- **Owner:** adjudicates every disagreement, blind to the matcher's decision.

**Agreement gate:**
- Cohen's κ between the two readers is reported on the "is it about company X" decision.
- **If κ < 0.70, the labels are judged unreliable and the evaluation is reported as INCONCLUSIVE,
  not as a pass or a fail.**

## 7. Metrics (estimated on the adjudicated labels)

- **Precision:** the correct share of P, overall and by category and flag, with Wilson 95%
  intervals.
- **Recall:**
  - true assignments ÷ (true assignments + missed assignments);
  - missed assignments are estimated from C and R, each weighted by its stratum's population;
  - a 95% interval comes from a stratified bootstrap (10,000 draws, seed 20261016);
  - reported overall and by category.
- **False-match rate:** wrong assignments per 10,000 evaluated headlines, overall and by category.
  This is the practical form of the false-positive rate, because almost all headlines are about none
  of the 204 companies.
- **Coverage:** the share of company-weeks in the evaluation period with at least one **correct**
  match. It is estimated as matched company-weeks × that category's precision.
  - Reported by company and by category.
  - The list of companies with zero matches is reported.

## 8. Pass criteria (all must hold)

1. **Overall precision ≥ 0.90 and Wilson lower bound ≥ 0.85.** This is the same gate as attempts 2–4.
   It is **not** loosened.
2. **Every category with at least 50 headlines in P has precision ≥ 0.80** (the point estimate). That
   way a good average cannot hide a bad category.
3. **Overall recall ≥ 0.60** (the point estimate), and **no category with at least 30 true positives
   below 0.40.** Missed headlines are not neutral: if misses cluster in one kind of company, the
   return test would be biased toward the companies the matcher finds easily.
4. **κ ≥ 0.70** (section 6). Below that, the result is INCONCLUSIVE.

**Verdict wording:**
- **Pass:** "The matcher is reliable enough to support a pre-registered GDELT sentiment return test,
  within the measured precision and recall."
- **Fail:** "The GDELT company attribution failed its pre-set criteria. No GDELT sentiment return
  test is run." The sentiment verdict stays **Testable, insufficient evidence**.
- **Inconclusive:** reported as such, with the cause. The labels are not used to tune anything.

## 9. Stop rule

- **This is the final matcher attempt.** Whatever the result, the matcher is **not** revised and
  re-tested on the reserve days, or on any other days, to obtain a pass.
- Any future attempt would need a **new** pre-registration. It would have to argue why it is not a
  repeat of this one, and it would be reported alongside every earlier failure.
- A pass permits, but does not start, a return-test pre-registration. That pre-registration must
  fix, before any return is computed:
  - only headlines published **before** the return window opens (GDELT's DATE is the 15-minute batch
    time);
  - the horizon;
  - the universe and its survivorship limit;
  - missing days treated as missing;
  - FinBERT at the pinned revision with the approved failure policy;
  - the measured precision and recall carried into the interpretation.

## 10. Matcher changes for M-5 (to be filled before freezing, only if M-5 is chosen)

(empty)

## 11. Changes before approval

(none yet)
