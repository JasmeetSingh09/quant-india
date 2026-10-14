# Value-factor peer methodology: decision document (2026-10-14)

**Status:** for owner decision. Nothing is implemented, nothing is deployed, and the current map,
fallback and formula are unchanged.

**What this replaces.** It supersedes the classification choices in
`PROPOSAL_V161_SECTOR_MAP_2026-10-14.md`, whose options A and B the owner did not approve.

**How to reproduce it.** Every number comes from `research/sector_map_costing_2026-10-14.sql`, which
is read-only, against production cycle 2026-10-14. The inputs are fingerprinted (query 6):

| Table | Rows | md5 |
|---|---|---|
| alpha_scan2 | 2,491 | `df7c3957b6155540cc8cbeec9f611763` |
| factor_inputs (value) | 22,162 | `a062761bb3e64f77af3aa9ad79d626e5` |
| factor_input_peers | 7,152 | `c0ee393d7c70cf549836386697ac7e44` |

These rows are written once per cycle and not rewritten. A re-run that reproduces the fingerprints
is reading the same inputs.

## 1. What the methodology says and what the code does

**The methodology** (`PHASE0_V1_METHODOLOGY_2026-09-14.md`) describes value as P/E and P/B
"compared with up to 3 sector peers".

**The code:**
1. If the stock is in the hand-written `NSE_SECTORS`, its peers are the first 3 other members of the
   first sector listing it.
2. Otherwise, Yahoo's sector for the stock is mapped through an 11-entry table to one of ours, and
   its peers are that sector's first 3 members.
3. If neither applies, the stock gets no peers and the market averages 22 ± 8 and 3.2 ± 1.5 are
   used.

## 2. Census: how every scored stock was valued (query 4)

| Peer source | Stocks |
|---|---|
| Hand-written map (`NSE_SECTORS`, 236 listed) | 234 |
| Yahoo fallback: Industrials → Capital_Goods (BHEL, LT, SIEMENS) | 470 |
| Yahoo fallback: Consumer Cyclical → Auto (M&M, MARUTI, TMPV) | 425 |
| Yahoo fallback: Basic Materials → Steel_Metal (JSWSTEEL, SAIL, TATASTEEL) | 367 |
| Yahoo fallback: Financial Services → Banking (HDFCBANK, ICICIBANK, SBIN) | 210 |
| Yahoo fallback: Technology → IT | 169 |
| Yahoo fallback: Healthcare → Pharma | 153 |
| Yahoo fallback: Consumer Defensive → FMCG | 151 |
| Yahoo fallback: Real Estate | 85 |
| Yahoo fallback: Communication Services → Telecom | 66 |
| Yahoo fallback: Utilities → Power | 28 |
| Yahoo fallback: Energy → Oil_Gas | 27 |
| No peer comparison: 64 distress (both multiples ≤ 0, scored −0.5), 4 refused, 9 on market averages | 77 |
| **Total scored** | **2,462** |

**What the census shows:**
- **Most stocks use the fallback.** 2,151 stocks (87%) take their peers through the fallback, and
  every one of them is compared with the three largest names of a broad Yahoo sector.
- **Corrections to earlier figures.** Revision 2 of the proposal gave 479/440/376/226 and "78 with no
  peers". Those were peer-set counts that included mapped members, and the "78" was mostly distress
  cases that never use peers.
- **Status.** This is a methodology-validity question, not a data defect: the code does what it is
  written to do, but the comparison it produces is not the one the methodology describes.

## 3. Classification source: requirements, and what is known

| Requirement | NSE industry classification | Yahoo `sector` / `industry` |
|---|---|---|
| Authority | The exchange's own (macro sector → sector → industry → basic industry) | A data vendor's |
| Coverage of our 2,462 | Expected to cover every NSE equity; **unverified here** | Fetched for 120 candidates only; not stored for the universe |
| Licensing and terms | **Unknown: the owner must check** | Use governed by Yahoo's terms; the app already depends on it |
| Update frequency | **Unknown: the owner must check** | Changes without notice |
| Access from the app | Not allowed (the app must not fetch nseindia.com); a file would be supplied by the owner and versioned in the repo | Already fetched live |
| Quality seen so far | — | Noisy: "Capital Markets" includes investment-holding firms and a power exchange (IEX) |

**Recommendation:** NSE's classification as the source, supplied as a versioned file, with Yahoo
industry as a cross-check only. A disagreement between them is listed, not resolved silently.

## 4. Candidate rules (written before any of section 5 was computed)

These are to be judged on definition, not on what they do to scores.

| Element | Rule R (recommended for owner review) |
|---|---|
| Peer group | Stocks sharing the source's **basic industry**. |
| Small groups | Fewer than *k* valid peers in the basic industry: widen to **industry**, then stop. No wider fallback. *k* = 3 proposed, matching today's three peers. |
| Insufficient peers | After widening, still fewer than 2 valid peers for a multiple: that multiple is **not measured**. Neither multiple measured: value is **not measured**, with the reason "too few classified peers". No market-average substitute. |
| Valid peer | Has the multiple and it is positive. This also settles D-06: a negative peer multiple is excluded, the same rule as the stock's own. |
| Conglomerates | Take the source's classification. Not decided by score impact. |
| Peer choice within a group | Kept as today's structure (the first 3 by a stated deterministic order), with the order defined as market cap descending, ties broken by ticker. "Nearest in size" is a separate methodology choice and not part of rule R. |
| Missing data | A missing own multiple: that leg is not measured. This differs from today, where it sits at the peer mean (inventory item L2). Owner decision. |
| Within-cycle consistency | Each peer's multiples are read once per cycle and reused. Today the same peer can carry two values in one night (DLF, GODREJPROP and OBEROIRLTY on 2026-10-14). |
| Determinism | Same inputs, same peers, same order. Covered by a test. |

## 5. Costing (sections 3–4 fixed first; source-independent alternatives only)

**What can and cannot be costed now.** Rule R cannot be costed until the classification file exists,
because no industry is stored for the universe. Two alternatives that need no source can be costed
now (query 5). Under the methodology, a not-measured factor contributes 0 and the weights are not
rescaled; coverage falls by 0.15 × the value confidence; tiers keep their 0.3 coverage floor.

| | Status quo | Alt 2: no value without a classified group (fallback removed) | Alt 3: no value when no multiple has ≥ 2 valid peers |
|---|---|---|---|
| Stocks whose value becomes not measured | 0 | 2,160 (the 2,151 fallback + 9 on market averages; the 64 distress judgements use no peers and are kept) | 10 |
| Mean absolute alpha change, affected stocks | — | 9.75 points | 6.86 points |
| Label flips | — | 705 (247 out of Buy/Strong Buy, 225 into Buy) | 3 (none to or from Buy) |
| Newly below the 0.3 coverage floor (drop out of tiers) | — | 144 | 0 |
| Top-10 buy slots changed (of 30, across the three tiers) | — | 14 | 0 |

**Reading the table:**
- **Alt 2** is the honest-today position: no value score without a defensible peer group. It is a
  large change, removing 15% of the score for 88% of the universe (2,160 of 2,462) until a classification exists.
  Under rule R, many of those stocks would regain value against proper peers.
- **Alt 3** is small, because the market-average path is rare (10 stocks). It is a clean,
  independent decision.
- **Rule R's cost** follows once the source exists: each stock is costed from the same frozen
  inputs, with peers re-derived.

**The capital-markets sector** costed earlier (49 Yahoo "Capital Markets" stocks, 12 flips,
KEYFINSERV 1.76) is kept only as an illustration of what a classified group changes. It is **not**
proposed as a membership.

## 6. Implementation plan, after the rule is approved

1. **The classification file** is supplied, committed and versioned (date, source, hash), and its
   coverage of the scored universe is reported.
2. **The rule** is implemented as a new model version, with the peer configuration in the frozen spec.
   The map, counts and fallback are already captured (`65c3fc9`); the classification file's hash
   would be added.
3. **Before/after** on frozen inputs (the fingerprinted cycle): every changed score, label and rank
   is listed.
4. **Tests:** rule determinism; minimum-peer and not-measured paths; no wider fallback; negative peer
   multiples excluded; an oracle check of value against independently derived peers.
5. **Freeze, deploy** (separately authorised), and verify the live commit and the drift check.
6. **Rollback:** revert to the prior version, whose spec is frozen. Rows carry the model-version
   stamp, so studies can exclude either side.

## 7. Round 3: owner decisions and what has been established (2026-10-14)

**Owner decisions:**
- **Source:** the NSE Indices classification is the preferred source, subject to obtaining the
  actual file and its terms. The owner verified the published methodology: a four-level hierarchy
  (12 macro-economic sectors, 22 sectors, 59 industries, 197 basic industries), reviewed annually
  and on corporate events. The owner could not verify a downloadable company-level file or terms
  covering this use. It is not to be scraped or redistributed on the assumption that public means
  unrestricted.
- **Rule R:** approved as the candidate to cost and test, with two clarifications: metric-specific
  eligibility, and an explicit rule for a missing own measure. K = 3 and the 2-peer minimum need a
  rationale and a sensitivity analysis.
- **Market averages → "not measured":** approved for a separately versioned change after
  validation. Not deployed.
- **The 2,160 fallback stocks:** current behaviour kept temporarily and marked as a methodology
  limitation. No universe-wide removal without a replacement rule.
- **No refactor, push or deployment.**

### 7.1 Scores reported by peer basis, not pooled (cycle 2026-10-14)

| Peer basis | Stocks | Mean value | SD | Below 0.3 coverage | No market cap | Buy / Sell labels |
|---|---|---|---|---|---|---|
| Hand-written map peers | 233 | −0.048 | 0.675 | 0 | 0 | 75 / 35 |
| **Broad-sector fallback (methodology-limited)** | 2,151 | −0.047 | 0.718 | 21 | 7 | 572 / 517 |
| Market averages (no valid comparison) | 10 | −0.165 | 0.539 | 1 | 8 | 1 / 3 |
| Distress (no peers needed) | 64 | −0.500 | 0 | 1 | 1 | 0 / 59 |
| No valuation data | 4 | 0 | 0 | 1 | 0 | 0 / 2 |

The two large groups have near-identical means and spreads. That does not make them comparable: the
fallback group's peers are three mega-caps of a broad sector, so its distribution answers a
different question.

### 7.2 The 10 market-average cases, validated against the fingerprinted cycle

| Stock | Valued on | Value | Alpha now → if not measured | Label |
|---|---|---|---|---|
| AARNAV | P/B only | 0.3095 | 14.87 → 10.23 | Neutral |
| ARTEMISMED | both | −0.9998 | 18.03 → 33.03 | Buy |
| DISAQ | P/B only | −0.2952 | 4.75 → 9.18 | Neutral |
| **ELCIDIN** | P/B only | 0.3765 | −12.74 → −18.39 | **Neutral → Sell** |
| GUJRAFFIA | both | 0.1386 | 6.18 → 4.10 | Neutral |
| **INDIGO** | P/B only (26.62 against a market 3.2, z = 15.6) | −0.9961 | −48.79 → −33.85 | **Strong Sell → Sell** |
| SILLYMONKS | P/B only | 0.2317 | −19.14 → −22.62 | Sell |
| SINGERIND | P/B only | 0.0717 | 12.40 → 11.32 | Neutral |
| TCC | P/B only | 0.3310 | −3.33 → −8.29 | Neutral |
| **ZODIAC** | both | −0.8208 | −19.86 → −7.55 | **Sell → Neutral** |

What this shows:
- **The three label changes reproduce.**
- **Why these stocks lack peers.** Eight of the 10 have no market cap on Yahoo, which is also why they
  had no Yahoo sector and so no peers. INDIGO has peers in neither the map nor the fallback: it is
  alone in Aviation.
- **Distress cases are untouched.** None of the 64 uses market averages.

### 7.3 Metric-specific eligibility (today's peer groups)

Of the 2,384 stocks with peers:
- **P/E:** 2 have fewer than 2 valid P/E peers; 283 have no valid own P/E.
- **P/B:** 0 have fewer than 2 valid P/B peers; 32 have no valid own P/B.
- **Negative peers:** 72 have a negative peer counted today (Vodafone Idea's P/B, D-06). Under
  per-measure eligibility it would be excluded.
- **By measure:** both measures measurable 2,067; exactly one 317; neither 0.

### 7.4 Missing own measure: an explicit rule

**Today's behaviour.** A missing measure "sits at the peer mean". Across all 322 single-measure stocks
(290 P/B only, 32 P/E only), today's value equals tanh((−0.6 z_PE − 0.4 z_PB) ÷ 2) with the missing
z set to 0, to within 0.0001. So today's behaviour already *is* "the missing measure contributes
nothing, and its weight is kept"; it is just not described that way.

| Option | Rule | Cost on the 322 |
|---|---|---|
| Kept | The missing measure is reported "not measured"; it contributes 0 and its weight is kept | No score change; reporting only |
| Renormalise | Value is computed on the measured measure alone (weights rescaled to 1) | Mean change 3.95 alpha points; 55 label flips |

Owner decision pending. The costing harness runs both.

### 7.5 K = 3 and the 2-peer minimum: rationale and sensitivity

**Rationale, stated as hypotheses:**
- K = 3 matches the number of peers the factor already compares against (`VALUE_PEERS_USED`). A
  basic industry with fewer than 3 eligible peers cannot supply a full comparison set.
- 2 is the smallest number that gives a non-degenerate spread. With one peer the population SD is
  0 and the floor (1 or 0.5) decides the z-score alone.

**Sensitivity harness.** `research/peer_rule_costing.py` generates one read-only statement over the
fingerprinted cycle:
- **Grid:** K ∈ {2, 3, 4, 5} × minimum ∈ {2, 3} × {kept, renormalise}.
- **Per-setting categories:** classified with both measures, one measure or too few peers;
  unclassified; distress; no data.
- **Per-setting changes:** widened, scores changed, label flips into and out of Buy, tier exits,
  top-10 slots, and tier-rank changes.

It was smoke-tested on a 50-stock *toy* file (Yahoo industry standing in for basic industry): it ran,
and its categories summed to 2,462. **The toy numbers are not results.** Real sensitivity needs the
NSE file.

**Assumptions to confirm:**
- **A1:** widening is decided per measure.
- **A2:** each peer's stored multiple for the cycle is used, one value per peer per cycle.

### 7.6 FinBERT: what is and is not fixed today

**Not fixed:**
- **The model** is loaded as `"ProsusAI/finbert"` with **no revision**. The Docker build downloads
  whatever upstream `main` is at build time, so production's revision is whatever existed when
  `cf9e3be` was built, and it is not recorded anywhere. The local cache's `main` is
  `0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031`.
- **`transformers` and `torch` are unpinned.** Unlike numpy, pandas and scipy, they are absent from
  the spec's environment block.

**Configuration:**
- **Preprocessing:** text is cut to 512 *characters* (the comment says tokens).
- **Inference:** the most probable label is taken, with its probability as confidence, rounded to 4
  places.
- **Runtime:** CPU, one thread.

**A missing-as-zero path.** If inference raises, the headline is returned as neutral with confidence
0. It still enters the weighted average with full recency weight, so it pulls the score toward 0.

**Required before any sentiment or constant refactor:**
- pin the revision and record it, with the transformers and torch versions, in the spec;
- record baseline outputs for quality, value and sentiment.

### 7.7 Marking the fallback as methodology-limited (proposed, not built)

Every value result would carry `peer_basis`, one of:
- `map`
- `broad_sector_fallback`
- `market_average`
- `distress`
- `none`

The provenance record would store it, and the stock page would show "Valued against broad-sector
leaders, not industry peers" for the fallback. Scores would not change. It needs owner approval
before any code.

## 8. Round 4: owner decisions and what was done (2026-10-14)

**Owner decisions:**
- **Missing own measure:** keep the weight; do not renormalise.
- **A1 and A2:** approved.
- **`peer_basis`:** approved in principle as its own display-only change.
- **FinBERT:** pinning and version recording approved for controlled preparation.
- **No scoring change, push or deploy.**

### 8.1 Missing own measure, as an explicit, tested rule

**Rule.** If a stock has only one valid valuation measure, the missing measure contributes nothing
and the weights are not redistributed: value = tanh((−0.6 z_PE − 0.4 z_PB) ÷ 2), with the missing z
taken as 0 *because it is absent*, not because it was measured at the mean. This is today's
behaviour exactly (7.4), so no score changes.

**Oracle checks:**
- **V15:** the rule holds.
- **V15b:** the weight is not renormalised.
- **V16:** a measured z of 0 and a missing measure give the same score.
- **V16b:** they are told apart by `legs_used`, `valued_on` and the halved confidence.
- **V16c:** pins the remaining reporting gap. A missing P/E still reports `pe_z_score` 0.0, and the
  `peer_basis` change (`SPEC_PEER_BASIS_DISPLAY_2026-10-14.md` §2) adds an honest per-measure `z`.

### 8.2 A1 and A2 in the harness and in a future implementation

- **A1 (per-measure widening):** implemented in `research/peer_rule_costing.py`.
- **A2 (one peer snapshot per scan):** the harness reads each peer's own stored value for the
  cycle. A production implementation must do the same, because today's code can read a peer twice
  in one night with different values (DLF, GODREJPROP, OBEROIRLTY on 2026-10-14). That would be a
  per-cycle cache of peer multiples, part of the rule-R version.
- **Thresholds:** remain hypotheses until the grid runs on the real file.

### 8.3 FinBERT: pinned, recorded and baselined (local, not deployed)

**Pin.** `model_config.FINBERT_REVISION = 4556d130…`:
- `sentiment.py` passes it to the pipeline (model and tokenizer), and the Dockerfile pre-downloads
  the same revision.
- The spec records `sentiment_model`: repo, revision, character cut, task, label rule, confidence
  rule and failure policy.
- The environment block records the transformers, torch and tokenizers versions.
- `finbert_pin_test` (13 checks) proves the pin is the same everywhere and moves the spec hash.

**Why that revision.** Upstream `main` changed on **2026-10-12**: four commits added safetensors
weights and a licence statement. Production was built on 2026-10-06, so it runs `4556d130`, which
was main from 2023-05-23 until then. This is inferred from the commit history, not read from the
server. Without the pin, the next deploy would have switched weight files.

**What the two revisions do on the baseline:** identical labels; probabilities within 4.8 × 10⁻⁷.

**Licence (a matter for the owner).** The model card now declares **CC BY-NC-SA 4.0**: copyright MIH
AI B.V., non-commercial use only, with share-alike for adaptations. The previous card declared no
licence, and the training data (Financial PhraseBank) is noted as CC BY-NC-SA 3.0. Whether Quant
India's use is non-commercial is not something this audit can decide.

**Baseline** (`docs/audit/finbert_baseline_2026-10-14.json`). It covers:
- **valid cases:** positive, negative, neutral, mixed, and Hindi, which is scored *neutral 0.92*
  because the model is English-only;
- **malformed cases:** 960 characters cut to 512 (66 tokens); an empty string, scored neutral 0.42;
- **failed cases:** `None` and an integer, which raise and become neutral at confidence 0.

It records the tokenizer (BertTokenizer, lower-case, 512-token maximum), versions (transformers
5.12.1, torch 2.12.1 locally) and the inference settings. Loading the pinned `sentiment.py`
reproduces it exactly.

**Library pinning is deliberately deferred.** Production's transformers and torch versions are
unknown. Pinning to the local versions could itself change production. The next authorised deploy
records them in the spec, and the pin then follows those.

### 8.4 FinBERT failure policy: defined, not yet changed

**Today.** An inference error becomes neutral at confidence 0, at full recency weight. The oracle
checks S12 and S12b pin its exact effect. The sentiment score is
(weighted mean) × min(1, Σweights ÷ 7):
- **while the cap does not bind:** a failure leaves the score unchanged but inflates the reported
  coverage (in the test, 0.113 → 0.227);
- **once the cap binds:** failures dilute the score (in the test, 0.9 → 0.6 with 4 failures among
  12 headlines).

**Proposed policy:**
1. A headline whose inference fails is skipped and counted (`inference_failures`), exactly like an
   untitled headline.
2. If every headline fails, sentiment is refused with the reason "sentiment inference failed", not
   "no news".
3. The count is recorded in provenance.

**Impact assessment.**
- **Stored history:** across 1,005,320 stored headline scorings (42 cycles, 2026-09-03 to 10-14),
  the failure signature (neutral, confidence 0) occurs **0 times**; the lowest real confidence is
  0.338. So the policy would have changed no recorded score.
- **Caveat:** headlines are stored for only about 47% of stocks (D-02), so the unstored half cannot
  be checked.
- **Version:** if adopted, it is a behavioural change to sentiment and gets its own version and
  impact note.

## 9. Status after round 4

| # | Item | Status |
|---|---|---|
| 1 | NSE company-level classification file and terms | **Blocked on the source** (the owner) |
| 2 | Rule-R sensitivity grid | Harness ready; waits for 1 |
| 3 | This decision document | Complete up to the classification results |
| 4 | `peer_basis` display change | Specified (`SPEC_PEER_BASIS_DISPLAY_2026-10-14.md`); 2 wording points open; not built |
| 5 | FinBERT pin and baselines | Done locally; library pins wait for production versions; failure policy defined, adoption pending |
| 6 | Investment evidence for each factor | Separate track, still required |

**Decisions still open:**
- the classification file (1);
- the `peer_basis` wording points (4);
- adopting the FinBERT failure policy (8.4);
- the FinBERT licence question (8.3).

## 10. Round 5 (2026-10-14): licence facts, production's stack, failure policy, labels

### 10.1 FinBERT licence: facts only, no conclusion

**At the pinned revision `4556d130`:**
- The repository holds `README.md`, `config.json`, the PyTorch, Flax and TF weight files, and the
  tokenizer files.
- It has **no LICENSE file**, and the model card has **no `license` field and no licence text**.
- The card states the model was fine-tuned on Financial PhraseBank (Malo et al., 2014).

**At upstream `main` (2026-10-12):**
- The model card declares `license: cc-by-nc-sa-4.0`, with "Copyright © MIH AI B.V.".
- It states that the licence "restricts commercial use", that adaptations must be shared alike, and
  that Prosus makes no representation that any use is permitted.
- It notes Financial PhraseBank as CC BY-NC-SA 3.0.

**The GitHub code repository `ProsusAI/finBERT`:**
- It is still Apache-2.0; its LICENSE file has been unchanged since 2019-10-30.
- On 2026-10-12 it merged PR #77, `license-remediation-2026-10-09`, which adds a README notice that
  the Apache-2.0 licence covers **only the training code and not the pre-trained weights**, and
  points to the Hugging Face card for the weights' terms.

**What this does not settle:**
- whether the 2026-10-12 terms apply to weights obtained from the 2023 revision;
- whether Quant India's use is non-commercial;
- what follows from the training data's own licence.

These are for the owner and legal advice. The pin is a reproducibility safeguard, not a licence.
The newer revision is not introduced.

### 10.2 Production's inference stack, from the Render build log of 2026-10-06 (`cf9e3be`)

| Package | Production | Local baseline |
|---|---|---|
| torch | **2.14.1+cpu** | 2.12.1 |
| transformers | **5.18.0** | 5.12.1 |
| tokenizers | **0.23.2** | 0.22.2 |
| huggingface-hub | 1.33.0 | — |
| safetensors | 0.8.0 | — |

The FinBERT pre-download ran at 08:13 UTC on 2026-10-06, before the upstream change. That confirms
production runs `4556d130`.

**The controlled pin, prepared but not applied:**
- **What it would add:** `torch==2.14.1` (CPU index) in the Dockerfile; `transformers==5.18.0`,
  `tokenizers==0.23.2` and `huggingface-hub==1.33.0` in requirements.
- **What has to happen first:** the FinBERT baseline must be re-run under exactly those versions and
  compared output by output with the recorded baseline (local 5.12.1 / 2.12.1).
- **The download:** that comparison needs those versions installed in a scratch environment, about
  200 MB for torch from download.pytorch.org, plus transformers and tokenizers from PyPI. It waits
  for the owner's approval of the download.

### 10.3 Sentiment failure policy

- **Specification:** `SPEC_SENTIMENT_FAILURE_POLICY_2026-10-14.md`, written before the code.
- **Implementation:** branch `sentiment-failure-policy` (one commit, unmerged).
- **Tests:** oracle S12, S12b and S13–S15; real-FinBERT failure injection 9/9
  (`research/finbert_failure_injection.py`); CI 69/69; snapshots 339/339.
- **Open:** the version decision and the merge.

### 10.4 `peer_basis`

`SPEC_PEER_BASIS_DISPLAY_2026-10-14.md` revision 2 carries the owner's five labels, with market
average per measure. No open points; not implemented.

### 10.5 Factor evidence

`FACTOR_EVIDENCE_VERDICTS_2026-10-14.md`:
- momentum demonstrated (35% of the score);
- value, quality and sentiment's predictive power not established (65%);
- the composite untested.

