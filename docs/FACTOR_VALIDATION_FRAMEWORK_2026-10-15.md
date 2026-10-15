# How factors are validated, and what each one's data allows (2026-10-15)

**Purpose.** This document fixes two things *before* more factor tests run:
- the procedure every factor test follows;
- which V1 factors the available data can test at all.

No test was run for this page. The frozen model (v1.6.0, `54ced1e2c8af0a77`) is not changed by
anything here.

**Passing software tests is not predictive validity.** The four-factor audit shows the scores are
*computed as specified*. Whether they *predict returns* is a separate question. It is answered only
by the procedure below.

---

## 1. Verdict taxonomy

Every factor carries exactly one verdict.

| Verdict | Meaning | What it takes |
|---|---|---|
| **Not testable** | The data to test the factor as V1 defines it does not exist here | The feasibility check (section 3) fails on a required input |
| **Testable, insufficient evidence** | Data exists, but no pre-registered return test has passed | Either no test has run, or a test ran and was positive but did not meet its own pass rule |
| **Failed** | A pre-registered test ran and the factor did not show an edge (or showed a reversed one) | A completed run under its pre-registration |
| **Passed historical validation** | A pre-registered test on historical point-in-time data met its pass rule | It also states whether the data had been **seen** before the rules were written |
| **Prospectively validated** | It passed on data that did not exist when the rules were written | Graded once, on the pre-set horizon, under rules committed before the window began |

**A verdict never moves up because of:**
- a software test;
- an exploratory cut;
- a re-run with changed settings;
- a test whose rules were written after its data were seen, unless that is stated in the verdict.

## 2. The procedure (every factor, in this order)

1. **Feasibility.** For each input the factor uses, three questions:
   - Does a **point-in-time** history exist? That means values as they were known on each date,
     not restated later.
   - Does it cover the universe at or above the coverage gate (80% unless the pre-registration
     argues otherwise **before** looking)?
   - Does it include companies that later delisted?

   Any "no" on a required input means **Not testable**, or a pre-registration that names the bias
   and limits the claim to match.
2. **Pre-registration, written and committed before any result exists.** It contains:
   - the hypothesis;
   - the signal, read from frozen code and not restated;
   - the universe and eligibility;
   - formation and execution timing;
   - the holding horizon;
   - portfolio construction;
   - the cost model and turnover definition;
   - the benchmark;
   - the statistic and its p-value;
   - the multiple-testing correction;
   - the pass, fail and insufficient rules;
   - the robustness checks, saying **which gate the verdict and which are description only**;
   - the wording of every outcome;
   - **what had already been seen.**
3. **Harness, committed before the run.**
   - It imports the frozen code and does not copy it.
   - It must pass leakage checks on synthetic data:
     - future-perturbation invariance;
     - a shuffled-signal null;
     - reconciliation with an existing series;
     - delisting handling;
     - corporate-action adjustment;
     - a freeze check of the spec hash.
4. **One run.** A technical failure allows one identical rerun, recorded. The output is saved with
   the commit, spec hash, data range and every count.
5. **Report everything.** That means gross and net, every robustness item, and failures. A
   deviation from the pre-registration is reported as a deviation, never folded in.
6. **Verdict.** Use the taxonomy above, then update `FACTOR_EVIDENCE_VERDICTS_*`.
7. **Recommendation.** Keep, re-label, or propose a change. A model change goes through a written
   proposal, owner approval and a new version. **A result never edits the model directly.**
8. **Prospective follow-up.** Register a held-out forward window, graded once on its horizon.

**Never:**
- invent missing history;
- change a hypothesis after seeing results;
- loosen a gate that failed;
- run every factor test at once.

## 3. Feasibility matrix

| Factor (V1 weight) | Inputs V1 uses | Point-in-time history here | Coverage | Delisted names | Feasible test | Verdict now |
|---|---|---|---|---|---|---|
| **Momentum** (35%) | Daily closes, 252-day window | **Yes.** NSE end-of-day 2011-07-04 to 2026-09-07 (3,744 days), adjusted for corporate actions, ISIN-resolved | The whole listed market | **Yes**, booked at −100% | Gross: done (factor test 1). **Net of costs: drafted** (`PREREG_MOMENTUM_NET_OF_COSTS_DRAFT_2026-10-15.md`) | **Passed historical validation, gross** (2011–2026; rules written before the run). Net of costs not yet tested |
| **Quality** (25%) | Piotroski F-score, ROE and FCF yield (FCF over market cap), 0.4/0.4/0.2, from Yahoo | **No.** Fundamentals are fetched live; Yahoo serves restated, recent years only | As-published annual-report pilot: **474 of 1,033 = 45.9%** (2026-10-14) against an 80% gate; estimated ceiling with every download 75–78% | No: Yahoo drops delisted companies | None at the approved gate. Factor test 2 was an approximation (restated, about 3 years, listed-today names): "no lead" | **Not testable** as V1 defines it |
| **Value** (15%) | P/E and P/B (0.6/0.4) against sector peers (3 used of up to 5 fetched) | **No.** Live fundamentals; no historical shares outstanding, so no historical market cap; the sector map is today's | As quality | No | As quality. The peer-methodology decision also changes what "value" measures for about 87% of stocks | **Not testable** as V1 defines it |
| **Sentiment** (25%) | FinBERT labels of recent headlines (14 days, recency-weighted) | **Partly.** The app's own stored headlines exist only from 2026-09-03, for about 47% of stocks (D-02). The **GDELT** archive is local (see note) | GDELT: 203 of the 204 names in its name list matched in a 254-day sample; heavily skewed (see note) | GDELT is not survivorship-filtered | A return test on GDELT titles, **after** a matcher-precision gate. It tests "FinBERT on GDELT titles", which is close to, not the same as, V1's live news source | **Testable, insufficient evidence.** The instrument is valid (factor test 3: macro-F1 0.734); predictive power is untested |
| Low risk (0%; shown, not scored) | Volatility, drawdown | Yes | Whole market | Yes | Done (factor test 1) | **Failed** (no demonstrated edge at any horizon) |
| 52-week high (not in V1) | Closes | Yes | Whole market | Yes | Done (factor test 4) | **Passed historical validation** at 3–12 months, beyond momentum (not at 1 month). Not a V1 factor |
| **Composite score and labels** | All four factors | **No.** Two inputs are live-only | — | — | Forward record only (first read due from 2026-12-27) | **Not testable historically**; prospective record accruing |

**GDELT note** (local archive, `~/quant_data/gdelt`): 5,147 files, 3.5 GB, 2019-09-01 to
2026-09-16. Titles exist only from 2019-09-22. In the 254-day matching sample
(`gdelt_match/match_stats.json`):
- 2.34 million titled rows were scanned, and 467,548 titles matched a company.
- **OIL alone took 225,686 matches,** the common-word leak already recorded for the live matcher.
- RECLTD never matched.

So the matcher's precision on GDELT is unmeasured, and it is visibly wrong for some names. A return
test before that is measured would test the matcher, not sentiment.

## 4. Recommendation per factor (order of work)

1. **Momentum: run the net-of-costs test** once the owner approves the draft pre-registration
   (revision 3). The owner chose a local, read-only run (mode L), with no deployment.
   - It is the only factor whose data supports a full point-in-time test, and it carries 35% of the
     score.
   - The honest expectation is stated in the draft: the 2011–2026 answer is largely predictable from
     results already seen. The new information is:
     - the break-even cost multiple;
     - both portfolios charged at one cost schedule;
     - drift-aware turnover;
     - the liquid-only result.

   Every 2011–2026 verdict is "historical, partly seen".
2. **Momentum, independent evidence.** No new prices are being stored: the last archive day is
   still 2026-09-07 (checked 2026-10-15).
   - **Owner decision (2026-10-15):** resume the **existing approved NSE pipeline**, after verifying
     collection, parsing, corporate-action handling and persistence. Do not switch sources, and do
     not mix Yahoo prices into the series.
   - The rules for the prospective window are fixed in the draft pre-registration, section 12.
   - Pre-2011 NSE history remains a separate option, not requested.
3. **Sentiment.** Two separate pre-registrations, in order:
   - **(a) a measurement gate:** hand- or blind-labelled precision of the GDELT company matcher on
     a random sample, with a fixed pass threshold, and with known leaks (OIL, the SBIN-type
     common-word cases) handled by a rule written before the sample is drawn;
   - **(b) the return test,** only if (a) passes. It uses FinBERT at the pinned revision with the
     approved failure policy.

   The FinBERT licence question stays with the owner's legal review. The test itself is research
   use.
4. **Quality and value.** No new test. Keep them labelled unvalidated.
   - The approved as-published gate (80%) failed and is not loosened.
   - A test becomes possible only if annual-report coverage reaches the gate.
   - Otherwise it needs a new pre-registration that states its survivorship and restatement bias, and
     claims no more than that design allows.
5. **Composite and labels.** Wait for the forward record's pre-set first read. Do not backtest; it
   cannot be computed historically.
6. **Low risk.** Stays shown and unscored. No retest.

## 5. Corrections this review found (wording only; no number changes)

1. **The liquidity floor is one day, not one month.**
   - Documents (factor test 1, momentum robustness, the Phase 0 methodology) say "Rs 1 crore
     monthly traded value".
   - The code measures close × volume **on the formation day alone** (`pit_validation._load`,
     `pit_backtest._panel`). Robustness H1's "Rs 10 crore a month" is likewise Rs 10 crore on one
     day.
   - The results are correct for the rule applied; the descriptions are wrong.
2. **"Accruing since 2026-09-07" is not true.**
   - `FACTOR_EVIDENCE_VERDICTS_2026-10-14.md` says a fresh out-of-sample momentum period has been
     accruing since then. Nothing is stored after 2026-09-07.
3. **The 0.415% cost's listed components do not add up to it.**
   - The Phase 0 table lists brokerage 0.03%, STT 0.1%, stamp duty 0.015%, exchange 0.00345% and
     GST. The total comes from the simulator's 0.1% brokerage each way plus 0.05% slippage each way,
     with STT on one side only.
   - Delivery STT is charged on both sides. At the itemised rates a round trip is about 0.29%, or
     0.39% with 0.05% slippage each side.
   - Revision 2 of the draft pre-registration states the derivation. It keeps the frozen 0.415%
     round trip and itemises it per side: 0.215% on the buy (statutory and broker 0.1546%, plus a
     0.0604% spread and impact allowance) and 0.200% on the sell (0.1396% plus 0.0604%).
   - Revision 3 treats "0.415% per side" (0.415% on each side, 0.83% a round trip) as a separate,
     named scenario with its own gate.

These corrections are proposed; none is applied in this commit.
