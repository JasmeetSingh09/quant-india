# Spec: what sentiment does when FinBERT fails on a headline

**Status: written before implementation.** The policy was approved in principle by the owner on
2026-10-14 as a separate, versioned change. It is implemented on local branch
`sentiment-failure-policy`, kept apart from the revision pin on `main`. It is not merged, pushed or
deployed.

## 1. Today (pinned by oracle checks S12 and S12b on `main`)

**What happens on a failure.** `sentiment.score_headline` catches any inference error and returns
`label "neutral", confidence 0.0` with an `error` key. `_compute_sentiment_factor` ignores the
`error` key: the headline enters the average as a zero signal with full recency weight w.

**How the score is built.** Score = (Σ signalᵢ·wᵢ ÷ Σwᵢ) × min(1, Σwᵢ ÷ 7). So a failed headline:
- **while Σw < 7:** cancels out of the score, but raises the reported coverage by w ÷ 7. In S12 the
  coverage doubles, from 0.113 to 0.227;
- **once Σw ≥ 7:** dilutes the score toward 0. In S12b it falls from 0.9 to 0.6 with 4 failures among
  12 headlines;
- **in every case:** is indistinguishable afterwards from a genuinely neutral headline.

## 2. The policy (owner-approved in principle)

| Case | Behaviour |
|---|---|
| A headline's inference fails (`score_headline` returns an `error`) | Skipped: it adds no weight, no signal and no coverage. Counted in `inference_failures` |
| A genuinely neutral prediction (no `error`, label neutral, confidence > 0) | Unchanged: counted as a zero signal with its weight, exactly as today |
| Every headline fails (one or more fetched, none scored) | Sentiment is **unavailable**: refused with score 0, confidence 0 and the reason "sentiment inference failed", with `inference_failures` = n. This is a refusal, so history stores NULL, not a neutral 0 |
| No headlines fetched | Unchanged: "no news found" |
| Untitled headlines (D-09) | Unchanged: skipped and counted in `untitled_articles_skipped`, a separate count |

`inference_failures` appears in the result only when it is above zero, so a normal result keeps
exactly its current fields. The spec field `sentiment_model.failure_policy` records the new rule,
which moves the spec hash. That is intended: the drift check must see it.

## 3. Expected effect on scores and coverage

| Situation | Sentiment score | Sentiment coverage | Composite |
|---|---|---|---|
| No failures (every stored cycle so far, as far as the stored half shows) | identical | identical | identical |
| Some failures, Σw of the scored headlines < 7 | identical | lower: now counts only scored headlines | alpha identical; coverage falls by 0.25 × Δ |
| Some failures, Σw ≥ 7 | larger in magnitude, the undiluted value | may fall below 1 | alpha moves by 25 × Δscore |
| All headlines fail | refused (0 at confidence 0) instead of 0 at positive confidence | 0 | alpha unchanged (0 either way); coverage falls; history stores NULL instead of 0 |

**Historical scores are not rewritten.** The policy applies from the version that adopts it.

**Measured prevalence.** 0 failure signatures (neutral at confidence 0) in 1,005,320 stored headline
scorings, across 42 cycles from 2026-09-03 to 10-14. Headlines are stored for only about 47% of
stocks (D-02), so this is evidence about the stored half only.

## 4. Tests (on the branch)

**Failure injection with stubs:**
- **S12:** cap not binding; the score and coverage now equal the "skipped" oracle.
- **S12b:** cap binding; no dilution.
- **S13:** all fail; refused with the reason, and history stores NULL.
- **S14:** a genuine neutral is still counted.
- **S15:** untitled headlines and failures are counted separately.

**Real FinBERT, local only** (`research/finbert_failure_injection.py`):
- the baseline cases go through the pinned model unchanged;
- one headline is made to raise inside the real pipeline;
- check that it is skipped and that the other headlines' result equals the baseline.

**Regression gates:** CI, the 339 behavioural snapshots and the oracle suite are unchanged except for
S12, S12b and the new S13–S15.

## 5. Version decision for the owner

This changes sentiment behaviour, though only on failure:
- **Spec:** the hash moves, so it needs a new frozen version at deploy (for example v1.6.1, or folded
  into the next release).
- **Stored rows:** the stamp `universe_scan.MODEL_VERSION` would need a bump so rows can be told
  apart. Bumping it mid-cycle makes the scan treat the cycle as new, so deploy outside the scan window.

Neither bump is made on the branch. Both are the owner's decision, alongside merging.

## 6. Pre-merge review (2026-10-15)

**Working identifier:** `sentiment-failure-policy` (owner, 2026-10-15). No final model version is
assigned, because the peer methodology may also need one and the release sequence is not settled.

**Evidence for the review:**

| Evidence | Result |
|---|---|
| Stub failure injection: oracle S12, S12b and S13–S15 | pass; no dilution, no inflated coverage, all-fail refusal, genuine neutral kept, separate counts |
| Real pinned FinBERT failure injection (`research/finbert_failure_injection.py`) | 9/9 under local libraries |
| Production-matched libraries (`finbert_prodmatch_comparison_2026-10-15.json`) | the inference error path behaves the same: non-string input raises `ValueError`, so `score_headline` reports an error, the one library-dependent input the policy reads; valid outputs identical |
| CI, behavioural snapshots, provenance audit, on the branch | 69/69, 339/339, 106/106 |

**Expected score and coverage impact:**
- **When no headline fails:** none. This is the only case observed so far: 0 failure signatures in
  1,005,320 stored scorings.
- **When some fail:**
  - **Sentiment coverage** falls to what the scored headlines support: by w ÷ 7 per failed headline
    while Σw < 7.
  - **Sentiment score:** unchanged while the cap does not bind; once it binds, it returns to the
    undiluted value. In S12b, 0.6 becomes 0.9.
  - **Composite:** alpha moves by 25 × Δsentiment, and coverage by 0.25 × Δsentiment coverage.
- **When all fail:** a refusal instead of 0 at positive confidence. Alpha is unchanged; coverage
  falls; history stores NULL.
- **Stored history:** untouched. The policy applies only to scores computed after it is adopted.

**Review limits:**
- The real-model injection ran under local libraries. It needs the app's other dependencies, and
  those were not part of the approved download.
- About 53% of stocks have no stored headlines (D-02), so the prevalence of failures is known only
  for the stored half.

**Merge:** conditionally approved by the owner on 2026-10-15, as a local merge only.

## 7. Review outcome and local merge (2026-10-15)

**Defects the diff review found and fixed** (commit `ccbd90e`, on the branch, before the merge):
1. **An empty error message passed as success.** The failure check was `s.get("error")`, which is
   falsy when an exception is raised without a message (`score_headline` stores `str(e)`, i.e. `""`).
   Such a failure would still have been scored as neutral at full weight. The check is now
   `"error" in s`.
2. **A stray counter on refusals.** The refusal path always returned `inference_failures`, 0 when
   none failed, against section 2. It is now present only when non-zero.

New oracle checks S16–S18 cover both, and S16 and S18 fail on the pre-fix commit `adf52d9`. The
real-model injection now also raises an empty-message exception inside the pinned pipeline: 10/10.

**One rule made explicit (S17).** Untitled and failed headlines with none scored give "no scorable
headlines", with both counts reported. "Sentiment inference failed" is used only when every fetched
headline failed inference.

**The owner's merge conditions, checked on the merged tree:**

| Condition | Result |
|---|---|
| Only the intended changes | 4 files: the sentiment function, the spec's failure-policy text, the oracle tests, the injection script |
| The production path uses the tested error signal | `alpha_model._compute_sentiment_factor` calls `sentiment.score_headline` only, whose failure branch sets the `error` key; nothing else scores V1 headlines |
| All-failed and partially failed cases behave as specified | S12–S18 and the 10/10 real-model injection |
| No historical scores rewritten | 0 storage statements added or removed; the change affects only scores computed after it runs |
| Regression suite and snapshots unchanged | CI 69/69; behavioural snapshots 339/339; provenance audit 106/106; oracle 204 pass, 3 fail (D-01, unrelated) |

**Status:** merged into local `main`, working identifier `sentiment-failure-policy`. Not pushed or
deployed, with no final model version assigned.

