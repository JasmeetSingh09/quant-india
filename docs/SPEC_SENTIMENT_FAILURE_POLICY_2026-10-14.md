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
