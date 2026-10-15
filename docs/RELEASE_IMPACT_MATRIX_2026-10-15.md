# Release change-impact matrix (2026-10-15)

**Purpose:** the owner asked for this before any version label is assigned. Every change waiting
for the backend (`cf9e3be` → `5705d95`, inventoried in `RELEASE_DECISION_PREP_2026-10-15.md`) is
classified, and the evidence required for its class is gathered.

**Nothing was deployed or written.** The evidence comes from:
- local tests;
- read-only production queries;
- a read-only Yahoo sample (the same download call the live momentum factor makes).

**v1.6.0 remains the frozen model** until a new version is approved.

## 1. The matrix

| Change (commit) | Class | Evidence required | Evidence obtained | Result | Gap |
|---|---|---|---|---|---|
| **Sentiment failure policy** (`adf52d9`, `ccbd90e`) | Failure handling; changes scoring semantics in the failure case | Failure-injection tests, plus verified historical behaviour | **Injection:** 10/10 against the real pinned FinBERT (one failure, an empty-message failure, all failing). Oracle suite cases pass. **History:** production stores a failed inference as label "neutral" with confidence **exactly 0.0**; a real FinBERT output can't be 0 (the top probability is at least 1/3). Across **all 1,024,064 stored headlines** (cycles 2026-09-03 to 2026-10-15), **0 have confidence 0.0**, and every label is positive, neutral or negative | **No stored score would have differed**, because no stored headline failed | Only about 47% of sentiment scores had their headlines stored (D-02), so the other 53% are unobserved. Nothing suggests failures concentrate there; the write failures were storage-side |
| **S11: untitled headline skipped instead of voiding sentiment** (`6e07521`) | Failure handling; changes semantics in an edge case | Before/after on affected records | **0 untitled** among 1,024,064 stored headlines. All 2,410 recorded sentiment refusals since 2026-09-04 read "no news found" (commit note) | No observed record affected | As above (47% stored) |
| **M17/M18: closes sorted, one row per date, before the momentum window** (`04a5f1c`) | Calculation input handling | Score-difference and label-flip analysis on the affected path | **Live path, 2026-10-15:** `yf.download` exactly as `_compute_momentum_factor` calls it, for **150 randomly chosen stocks** from the 2026-10-14 scan (deterministic order: md5(ticker ‖ 20261015)). **150/150 already sorted, 0 with repeated dates.** The new rule is the identity on such a series, so the score difference is 0 and there are **0 label flips** in the sample. 339/339 behavioural snapshots identical | Score-neutral on every observed series | A sample, not the whole universe. 95% upper bound on the affected share, by the rule of three: 3/150 = **2%**. A full 2,462-stock check is possible (about 20 minutes of Yahoo calls) if the owner wants it |
| **FinBERT revision pin** (`d70287d`, Dockerfile and `sentiment.py`) | Dependency / model pin | Reproducibility and compatibility | The pinned `4556d130` reproduces `finbert_baseline_2026-10-14.json` exactly. Under production-matched libraries (torch 2.14.1, transformers 5.18.0) outputs are identical (`finbert_prodmatch_comparison_2026-10-15.json`). Production already runs `4556d130` (built 2026-10-06; upstream main changed only on 2026-10-12). `finbert_pin_test` 13/13 | **No change to any score;** it removes a future silent change | Linux / Python 3.12 run of the pinned build not yet done (`verify-production-env`, unpushed) |
| **Spec coverage: `sector_map`, `sentiment_model`, library versions** (`67d52f7`, `65c3fc9`, `d70287d`) | Documentation of the frozen record | Identical scoring outputs | 339/339 identical. The spec diff against `d9b474a` **only adds** two fields; no captured value changes. Constants promoted unchanged | Neutral. Drift will report a coverage gap, not behavioural drift | — |
| **Rights-issue adjustment** (`63d84d0`) | Data handling for **research prices only** (`pit_validation`, `pit_backtest`); the live score uses Yahoo prices | Before/after on affected records | The code is **inert until the stored rights lines are re-parsed**: 0 rows of kind `rights` today; 12,778 `other` rows are unparsed. The plan (`CORRECTION_RERUN_FACTOR_TEST1_RIGHTS_2026-10-14.md`) needs, after deploy and each with separate approval: (1) dry-run reparse, expected about 310 ADD, 0 CONFLICT, 0 DROP; (2) apply; (3) factor test 1 re-run unchanged. `rights_adjustment_test` 7/7 | **No live score change.** Research prices change only after the reparse | The before/after research comparison doesn't exist yet. It is a later, separately approved step and must not be bundled into this release's verdict |
| **Provenance: failed headline batch retried row by row** (`40c2b23`) | Data handling (records only) | Before/after on affected records | **Before:** headlines stored for 1,158 of 2,462 scanned stocks (47.0%, cycle 2026-10-14); the batch was dropped whole on failure. **After:** can only be measured on the first cycle after deploy | No score change; more provenance stored | The after-count is a post-deploy check, which should go in the verification checklist |
| **`not_measured` flag in scan rows** (`7b48397`, backend half) | Presentation (additive field) | Identical scoring outputs | 339/339 identical. The live frontend (`d9b474a`) already reads it with a safe fallback | Neutral | — |
| **Scan universe: each stock once** (`beb3735`) | Data handling (scheduling) | Before/after on affected records | **Before:** 3 stocks (KALYANKJIL, ADANIGREEN, ADANIENT) were scored twice a night (2,494 attempts for 2,491 stocks). The stored results table `alpha_scan2` has **no duplicate rows** in any cycle since 2026-09-15 (checked), so each stock keeps one stored result per cycle | No stored score changes; removes 3 redundant scorings a night | — |
| **Value interpretation text** (`332389e`) | Presentation | Identical scoring outputs | 339/339 identical | Neutral | — |
| **Docstring and test-only commits** (`7b013ba`, `99bf7dd`, `cf7f32e`, `d9b474a` and the docs) | Documentation and tests | — | `run_ci` 69/69; oracle 204/3 (all D-01, not in this release) | Neutral | — |

## 2. What the evidence says

- **On every record observed, no change in this release alters a stored score or label.**
- **Four changes alter the rules,** and therefore what a score means, even though no observed case
  triggered them:
  - the sentiment failure policy;
  - S11;
  - M17/M18;
  - the FinBERT revision becoming part of the specification.
- Under the frozen-model rule, a change in rules needs a new methodology version, even when it is
  output-neutral on the data seen so far.

## 3. Proposed labels: two identifiers, kept separate

| Identifier | Proposal | What it identifies |
|---|---|---|
| **Scoring methodology version** | **v1.6.1:** "v1.6.0 plus the sentiment failure policy, S11, M17/M18 and the pinned FinBERT revision" | The rules that produce a score. It is frozen in `strategy_versions` at deploy, which is a production write and needs approval then |
| **Software release identifier** | **`release-2026-10-A`**, mapped to the backend commit that is deployed | The code shipped, including the changes in section 1 that are not methodology changes: rights code (inert), provenance retry, scan de-duplication, `not_measured`, text |
| `MODEL_VERSION` stamp (on every score; now `v1.5.0-statement-inputs`) | The owner's choice. Proposed: **`v1.6.1-sentiment-failure-policy`** | Which methodology produced a stored score |

**Consequences:**
- The draft sector-map proposal, currently titled "v1.6.1", would be renamed **v1.6.2** before it is
  decided. It is a draft, so nothing approved changes.
- **v1.6.0 stays the frozen model until v1.6.1 is approved and frozen.**

## 4. Still required before any release decision

1. **Linux / Python 3.12 image verification** (`verify-production-env`). Then the same check on the
   release commit.
2. **The environment decision:** the locked 2026-10-06 library set, or a stated, separate upgrade.
3. **The owner's review of this matrix and of the labels in section 3.**
4. Optional: **M17/M18 over the full universe** (2,462 stocks, read-only Yahoo) instead of the
   150-stock sample.
