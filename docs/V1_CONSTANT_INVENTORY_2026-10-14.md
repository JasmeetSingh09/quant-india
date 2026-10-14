# V1 constant inventory: quality, value and sentiment (2026-10-14)

**Audit scope expansion, approved by the owner on 2026-10-14.** This document inventories; it changes
nothing.

**Why it is needed.** `version_provenance_audit.py` scans for unregistered literals only in
`_compute_momentum_factor`, `compute_alpha_score`, `signal_for_score` and V2. Its "103/103 captured"
certificate is true within that scope only. The quality, value and sentiment functions were never
scanned, so their numbers are not protected by the frozen spec hash. A change to any of them would
alter scores with no drift reported.

**Reproduce:** `python research/v1_constant_inventory.py --json out.json`. It parses the source; the
line numbers below are for commit `65c3fc9`.

**Scope:**
- `alpha_model._compute_sentiment_factor`
- `alpha_model._compute_quality_factor`
- `alpha_model._compute_value_factor`
- `alpha_model._interest_coverage`
- `metrics.piotroski_score`
- `data_fetcher.get_sector_peers`

Together they hold 149 numeric literals.

## 1. Model parameters: change one and a score or label changes

| # | Function | Value(s) | Unit | Purpose | Captured today |
|---|---|---|---|---|---|
| S1 | sentiment | 14 | days | headline window (`days_back` default) | no |
| S2 | sentiment | 0.5 × window = 7 | days | age given to an undated headline | no |
| S3 | sentiment | window × 0.5 = 7 | weight | confidence denominator: min(1, Σw ÷ 7) | no |
| S4 | sentiment | 1.0 | — | confidence cap | no |
| S5 | sentiment | ln 2 ÷ half-life | — | decay (half-life already captured as `SENTIMENT_HALF_LIFE_DAYS`) | half-life only |
| S6 | sentiment | 0.4 / 0.1 | score | interpretation bands (label text) | no |
| Q1 | quality | 9 | points | F-score scale (F ÷ 9) | no |
| Q2 | quality | 0.12, 0.08 | fraction | ROE reference mean and spread | no |
| Q3 | quality | 0.035, 0.04 | fraction | FCF-yield reference mean and spread | no |
| Q4 | quality | 0.4 / 0.4 / 0.2 | weight | Piotroski / ROE / FCF part weights | no |
| Q5 | quality | ÷ 3 | — | z-score scaling of ROE and FCF parts | no |
| Q6 | quality | 0.5 | score | negative-equity penalty | no |
| Q7 | quality | 1.5 | × | interest-cover threshold (strict <) | no |
| Q8 | quality | 0.25 × 3 | score | low-cover, loss and negative-OCF penalties | no |
| Q9 | quality | 0 (cap) | score | composite capped at 0 before penalties | no |
| Q10 | quality | 0.85 | — | confidence scale (0.85 × weight present) | no |
| Q11 | quality | 0.4 / 0.1 | score | interpretation bands | no |
| P1 | Piotroski | 0.05 | fraction | "ROA > 5%" proxy for improving ROA (F3) | no |
| P2 | Piotroski | 0.5 | ratio | low-leverage threshold (F5) | no |
| P3 | Piotroski | 1.0 | ratio | current-ratio threshold (F6) | no |
| P4 | Piotroski | 0.20 | fraction | gross-margin threshold (F8) | no |
| P5 | Piotroski | 1 | point | F7 "no dilution" is always awarded (an assumption) | no |
| P6 | Piotroski | 7 / 4 | points | Strong / Moderate bucket labels | no |
| V1 | value | 0 | multiple | a non-positive P/E or P/B is dropped as distress | no |
| V2 | value | −0.5, 0.6 | score, confidence | both multiples non-positive (64 stocks on 2026-10-14) | no |
| V3 | value | 2 | peers | minimum peers before the market average is used | no |
| V4 | value | 22.0, 8.0 | × | P/E market mean and spread (fallback) | no |
| V5 | value | 3.2, 1.5 | × | P/B market mean and spread (fallback) | no |
| V6 | value | 1, 0.5 | × | floors on the peer spread (P/E, P/B) | no |
| V7 | value | −0.6 / −0.4 | weight | P/E and P/B z-score weights | no |
| V8 | value | ÷ 2 | — | tanh scaling | no |
| V9 | value | 0.5 + 0.1 × peers, cap 1.0 | — | confidence | no |
| V10 | value | × 0.5 | — | confidence halved on one leg | no |
| V11 | value | 0.4 / 0.1 | score | interpretation bands | no |
| G1 | peers | 5, 3, fallback table | — | peers fetched, peers used, Yahoo fallback | **yes**, since `65c3fc9` |

## 2. Policies encoded in logic rather than a number (behaviour-affecting)

| # | Where | Policy | Effect |
|---|---|---|---|
| L1 | `piotroski_score` | `info.get(x) or der.get(x) or 0`: a missing ROA, CFO, current ratio, gross margin or revenue growth is read as 0 | The F-score signal fails rather than being "unknown", so missing data lowers quality. This is the missing-as-zero pattern the owner asked to avoid. |
| L2 | `_compute_value_factor` | A missing own multiple sits at the peer mean (`pe_self or pe_mean`) | That leg contributes z = 0, with confidence halved. |
| L3 | `_compute_value_factor` | Peer multiples are taken if truthy, so negative peer values are kept (D-06) | Asymmetric with the stock's own multiples. |
| L4 | `_compute_quality_factor` | `f_result.get("f_score", 4)`: the default 4 is computed but then excluded | Dead value; no effect today. Harmless, but misleading. |
| L5 | `compute_alpha_score` | An unmeasured factor contributes 0; weights are not rescaled | Already documented in the methodology. |

## 3. Implementation literals: not parameters

These are 0/1 counters and initialisers, `round(…, n)` digits for display and storage, unit
conversions (86,400 seconds per day, × 100 for percent), `0.0`/`0` in refusal return values, and
`sys.path` index 0. Rounding digits do feed the stored score (`round(score, 4)`), so they are listed
as stored-precision settings, not as model parameters.

## 4. Not capturable as a constant today

| Item | Why it matters | What capture would need |
|---|---|---|
| FinBERT model, loaded as `"ProsusAI/finbert"` with no revision pin | An upstream model update changes every sentiment score, with no drift reported | **Done locally 2026-10-14, not deployed.** Pinned to `4556d130…` (`model_config.FINBERT_REVISION`), used by sentiment.py and the Dockerfile, and captured as `sentiment_model` (`finbert_pin_test`, 13 checks). Upstream changed on 2026-10-12: safetensors weights, numerically equivalent on the baseline (4.8e-07), and a **CC BY-NC-SA 4.0 non-commercial licence** declared, a licensing matter for the owner (`docs/audit/finbert_baseline_2026-10-14.json`). |
| `transformers` and `torch` versions (both unpinned; absent from the spec's environment block) | A rebuild can change tokenisation or inference | **Recorded locally** in the spec environment (`transformers_version`, `torch_version`, `tokenizers_version`). **Not yet pinned:** production's versions are unknown until the next deploy records them, and pinning to local versions (5.12.1 / 2.12.1) could itself change production. Pin to the recorded production versions after that deploy. |
| FinBERT failure path: an exception returns neutral at confidence 0, and the headline still counts with full weight | A failed inference pulls sentiment toward 0, silently | A policy decision: skip the headline and count it, as was done for untitled headlines |
| Input cut at 512 characters (the comment says tokens) | Long titles are cut by character count | Name it, and correct the comment |
| Yahoo field semantics (`trailingPE`, `priceToBook`, `returnOnEquity`, `freeCashflow`) | The provider defines them and can change them | Not capturable; can only be documented and monitored |
| Statement row names in `_interest_coverage` ("ebit", "operating income", "interest expense") | Strings, not numbers; a renamed row silently removes the coverage test | Promote to a named tuple and capture it |
| News sources and matching | Already captured (`news_matching` block in the spec) | — |

## 5. What promotion would require (the owner's conditions; not started)

1. **This inventory approved,** including the parameter-versus-literal split above.
2. **Promote** each section 1 and section 2 item to a named constant, unchanged in value, and add it
   to `current_spec()`.
3. **Add the three functions to the scan's `CRITICAL_FUNCS`,** so new literals are caught from then on.
4. **Hash test:** changing any registered parameter changes the spec hash, as `sector_map_spec_test`
   already does for the peer settings.
5. **Identity proof:** 339/339 behavioural snapshots identical, and the oracle suite unchanged.
   The snapshots do not exercise quality, value or sentiment directly, so the identity proof must
   add recorded outputs for those three functions *before* the refactor. That is what v1.4 did for
   momentum.
6. **Gaps:** any item that cannot be captured is listed, as in section 4.
7. **Freeze a new version.** The drift check will then report these fields as newly covered, not as
   behavioural drift.

Passing these checks would show the parameters are protected. It would say nothing about whether
they are right, and nothing about predictive power.
