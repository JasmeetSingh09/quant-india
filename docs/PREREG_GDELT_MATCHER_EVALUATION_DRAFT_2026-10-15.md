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
| Strict attempt 4 (seed 20260930), commit `00bb4e0` | 9, 19, 29 | **Failed narrowly:** 89.3% (85.3–92.3). The lower bound (85.3%) cleared the 85% requirement; the point estimate (89.3%) missed the 90% requirement. Errors: 12 clear rule gaps, 9 not about the business, 6 passing or industry mentions, 5 separate relatives |

**The gate those attempts used,** committed before each was labelled: precision ≥ 90% **and** a 95%
Wilson lower bound ≥ 85%, on 300 random matches.

**What those attempts did not measure:**
- **Recall** (headlines about a listed company that the matcher missed);
- results **by ambiguity category**;
- **agreement** between independent labellers. Every label so far came from one reader.

**The risk this creates is a winner's curse.** The matcher was revised three times after reading
labelled errors. Further revise-and-retest cycles would eventually pass by chance alone. This
evaluation is therefore designated the **final attempt** (section 9).

## 2. The matcher under evaluation: M-4 (owner decision, 2026-10-15)

- **M-4** is the attempt-4 matcher **exactly as committed** in `00bb4e0` (`research/gdelt_strict.py`,
  unchanged since; checked 2026-10-15).
- **It gets no change of any kind.** That includes the 12 known rule gaps, which are documented in
  section 10 and **not** fixed.
- **The matcher is frozen by commit hash.** The evaluation script refuses to run if
  `research/gdelt_strict.py` differs from `00bb4e0`.
- **M-4 is never turned into a revised matcher during or after this evaluation.**
  - If M-4 fails, the evaluation stops.
  - Whether a new matcher design deserves a study is a separate decision. Such a study would get its
    own independent specification and new untouched days, and would be reported alongside every
    earlier failure.
- **M-5** (M-4 plus fixes for the 12 gaps) was considered and **not chosen**.

## 3. Evaluation data

- **Days:** only days of the month **5, 15 and 25**, in every month from 2019-09-22 (when GDELT titles
  begin) to 2026-09-16. None of these days has been read in any earlier step.
- **Reserve:** days **2, 12 and 22** stay untouched for any later confirmation. Nothing in this
  protocol reads them.
- **Headlines:** unique titles as `gdelt_strict.sample` reads them, with duplicate titles counted
  once.
- **Missing GDELT files are missing, not zero.** Known gaps include 2025-06-15 to 07-01. The run
  reports which evaluation days have no files.
- **Company list:** the 204 names in `~/quant_data/gdelt_names.json`. Its sha256 begins
  `a3c5cb00f700bb73`, and the script checks it.
  - 195 companies are `active`. **9 stopped trading** between 2021-06-11 and 2026-02-25 (DRREDDY's
    entry, HDFC, RELCAPITAL, PEL, DHFL, MINDTREE, NAUKRI's entry, PCJEWELLER, ANGELONE, as the file
    records them). 195 names come from Yahoo and 9 were hand-entered.
  - The list carries a per-company `ranked` field of years. Whether the list as a whole is free of
    survivorship bias is **not** claimed here. It is the return test's question, to be argued in that
    pre-registration.

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

| Category | Rule (all lists are read from frozen code, not restated) |
|---|---|
| **A. Common-word names** | The company's lower-cased ticker is in M-4's `DROP_TICKER` (tickers that are ordinary words or mean something else) **and** that ticker is not a key of M-4's `UPPER_ONLY` (acronyms) |
| **B. Group-name companies** | The first word of the company's name, lower-cased, is in the frozen spec's `news_matching.group_tokens` (adani, aditya, bajaj, birla, godrej, hero, hindustan, mahindra, reliance, tata) |
| **C. Short tickers and acronyms** | Among the terms M-4's `build()` produces for the company, at least one is 4 characters or fewer, ignoring spaces and punctuation. Keys of `UPPER_ONLY` fall here |
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

## 10. Known rule gaps in M-4 (documented, deliberately NOT fixed)

These are the 12 attempt-4 errors labelled `rule_gap_clear`, from
`quant_data/gdelt_match/strict_label_300_days9-19-29_seed20260930_labelled.tsv`. Headlines are
abbreviated.

| # | Matched | Headline (abbreviated) | Gap |
|---|---|---|---|
| 7 | VEDL | "Semiconductor business not to 'short circuit' Vedanta Resou…" | Another group entity (Vedanta Resources, the parent), not the listed company |
| 88 | ITC | "Fertiliser business faces ITC pile-up…" | "ITC" here is input tax credit |
| 151 | SAIL | "Vedanta readies for post-Covid… former Secretar…" | The term is matched inside unrelated text |
| 169 | BATAINDIA | "Q4 Results 2024 LIVE Updates: Cummins India, Tata Steel, GMR…, Bata India, Liberty Shoe…" | A list headline the list cue misses |
| 198 | HDFC | "HDFC Pharma & Healthcare Fund delivers…" | A mutual-fund scheme ("Fund" is not a relative word) |
| 212 | SBIN | "SBI's credit card arm files offer document…" | A relative named through "credit card arm" |
| 223 | PAYTM | "Paytm banking arm inks Visa deal…" | A relative ("banking arm") |
| 238 | PAYTM | "Paytm Payments Bank disables…" | A separately regulated relative (Payments Bank) |
| 243 | SBIN | "SBI-ETF Nifty share price…" | An ETF, not the bank |
| 248 | LT | "…Reliance tops list of companies…, Larsen & Toubro, Tata M…" | A list headline |
| 266 | WIPRO | "Top Events Of The Day: Reliance Ind, Wipro, JSW Steel Q1 Results…" | A list or digest headline |
| 291 | RECLTD | "Oil flirting with $70 challenges world's economic rec…" | "rec" inside "recovery" |

**These gaps appear in the error analysis by category and flag. They are expected to cost precision,
and nothing in the evaluation compensates for them.**

## 11. Changes before approval

**2026-10-23 (before approval; nothing sampled from the evaluation days):**
- **The loose candidate term (section 4) is made exact.** A word counts if it is 3+ characters, from
  the company's full name, its hand-listed short names or its ticker. It must not be one of M-4's
  `LEGAL` words (limited, ltd, corporation, …), and not one of `india`, `indian`, `the`, `of`, `and`,
  `company`.
  - Without the exclusions, "Coal India" would make almost every headline a candidate, and the C
    and R samples would be meaningless.
- **The tool is `research/gdelt_matcher_eval.py`.**
  - It refuses `--final` unless the matcher is byte-identical to `00bb4e0`, the name list's hash is
    `a3c5cb00f700bb73`, and the approved pre-registration's commit is given.
  - The reserve days (2/12/22) can never be read.
  - It was dry-run on the already-seen development days (1/11/21) only.
- **Categories assigned by the frozen rules:** A 21, B 27, C 49, D 107.
- **Dry run on the already-seen development days (1/11/21), 2026-10-23.**
  - Populations: P 47,279; C 467,837; R 1,267,883.
  - The blind packet holds 2,200 headlines, shuffled, showing only number, date, source and text,
    with no leak of sample, category or matcher decision.
  - **Design weakness found:** C is dominated by ordinary name words ("consumer", "energy", "state"),
    so each of 600 C draws stands for about 780 headlines and the recall estimate would be very
    noisy.
  - **Proposed for the owner's decision before freezing:** split C into C-strong and C-weak.
    - C-strong: a ticker, a two-word name fragment, or a one-word company name.
    - C-weak: only an ordinary name word.
    - Draw 400 and 200.

**2026-10-15 (owner):**
- **M-4 chosen;** M-5 not chosen.
- The 12 rule gaps are documented, not fixed.
- The category rules are made mechanical from frozen lists.
- The name-list facts are corrected (9 stopped-trading companies are included).
- The attempt-4 bounds are stated precisely.

Nothing has been sampled or labelled.
