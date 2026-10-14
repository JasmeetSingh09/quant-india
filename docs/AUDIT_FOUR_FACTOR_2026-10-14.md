# Four-factor model (V1): end-to-end audit, 2026-10-14

**Status: FAIL.** The no-score defects were fixed the same day (section 9); D-01 is still open.

The four formulas, the composite score and the labels all match the methodology.
That holds on synthetic cases and on every stock in the 2026-10-14 nightly scan. The status is still
FAIL for two reasons:
- **A P1 defect is open.** The sector map gives some stocks the wrong valuation peers (D-01).
- **The signed-in frontend check is blocked.** The app needs a sign-in, which only the owner can do.

**Scope.** Nothing in production was written. The methodology was not changed. No score-changing fix
was made.

Machine-readable results:
- `docs/audit/four_factor_audit_2026-10-14.json`: the whole audit.
- `docs/audit/four_factor_oracle_results_2026-10-14.json`: one row per check.

## 1. Summary

**What reconciles exactly** (2,462 scored stocks, cycle 2026-10-14):
- **Composite score:** 0 mismatches. The stored score equals 100 × (0.25 S + 0.35 M + 0.25 Q + 0.15 V)
  to within 0.01, which is storage rounding.
- **Labels and ranges:** every label matches its threshold. Every factor lies in [−1, 1]; every coverage
  figure in [0, 1].
- **Each factor from its own stored raw inputs:** 0 mismatches for all four.
  - Momentum: 2,290 measured.
  - Quality: 2,462.
  - Value: 2,462, recomputed from the stored peers.
  - Sentiment: the 1,158 stocks whose headlines were stored.
- **Scan table, history table and live API** agree on all five traced stocks. Refused factors are
  stored as NULL in history, never 0.

**What is wrong:**

| Id | Sev. | Defect | Changes a score if fixed? |
|---|---|---|---|
| D-01 | P1 | Sector map gives wrong value peers (see below) | Yes, needs owner approval and a version |
| D-02 | P2 | Headlines behind 1,302 of 2,460 news-bearing sentiment scores are never stored, so those scores cannot be reproduced or explained | No |
| D-05 | P2 | A factor that could not be measured is shown in the app as a measured 0 | No |
| D-06 | P2 | A peer's negative P/B enters the sector mean (Vodafone Idea, −3.88, for 72 stocks), though a stock's own negative multiples are dropped | Yes, approval |
| D-03 | P3 | Scan universe lists 3 stocks twice: 2,494 attempts for 2,491 stocks | No |
| D-04 | P3 | Value text drops "Valued on one measure only" and the distress note unless the score is above 0.4 (230 stocks tonight) | No |
| D-07 | P3 | Backtest momentum uses population std; live uses sample std. The docstring says "identical arithmetic". Difference about 0.0002 | Research only |
| D-08 | P3 | Momentum assumes the provider's dates are sorted and unique | No (latent) |
| D-09 | P3 | One headline without a title voids the whole sentiment factor | Only on bad input |
| D-10 | P3 | `behavioural_fixtures.py` snapshot predates a display-only field, so the suite fails | No |
| D-11 | P3 | Landing page always shows the fallback "2,704 stocks scored daily"; the live figure is 2,462 | No |
| D-12 | P3 | `version_provenance_audit.py` registry is stale (flags constants the spec does capture) | No |

D-01 in detail:
- Kalyan Jewellers and Edelweiss are valued against Tata Steel, JSW Steel and SAIL.
- KEYFINSERV, a financial-services firm, sits under Real_Estate.
- Three stocks sit in two sectors, and the first match wins.

## 2. Implementation map

| Check | Momentum | Sentiment | Quality | Value |
|---|---|---|---|---|
| Formula | `alpha_model._compute_momentum_factor` | `_compute_sentiment_factor` | `_compute_quality_factor` | `_compute_value_factor` |
| Spec | `docs/PHASE0_V1_METHODOLOGY_2026-09-14.md` (all four); weights in `FACTOR_WEIGHTS` | | | |
| Raw source | Yahoo daily closes, `auto_adjust` (`yf.download`, 430 days) | `news.get_stock_news` (14 days), FinBERT `sentiment.score_headline` | Yahoo `.info`, statements via `data_fetcher._derived_fundamentals`, `metrics.piotroski_score`, `_interest_coverage` | Yahoo `.info` P/E and P/B of the stock and of 3 peers from `data_fetcher.get_sector_peers` |
| Required inputs | ≥ 60 closes | headline, date | F-score, ROE, FCF, market cap, book value, net income, OCF, EBIT/interest | trailingPE, priceToBook |
| Normalisation | tanh(ratio ÷ 1.5) | confidence shrink | tanh, z ÷ 3 | tanh(z-mix ÷ 2) |
| Composite | `compute_alpha_score`, labels `signal_for_score` | | | |
| Storage | `universe_scan._save_result` → `alpha_scan2`; `factor_history.record` → `factor_history`; `factor_provenance.capture` → `factor_inputs`, `factor_input_peers`, `factor_input_articles` | | | |
| Cache | `_SCORE_CACHE` 15 min, `_INFO_CACHE` 24 h, `_COVERAGE_CACHE` 24 h, `/alpha/universe/top` SWR 300 s | | | |
| API | `/alpha/score`, `/alpha/explain`, `/alpha/universe/top`, `/alpha/universe/status`, `/alpha/signal-history`, `/factors/history`, `/factors/inputs` | | | |
| Frontend | `pages/StockExplorer.jsx` (factor rows), `components/WhySignal.jsx`, `components/CapTierPicks.jsx`, `pages/Landing.jsx` | | | |
| Scheduler | nightly `universe_scan._scan_loop` (00:07–03:11 UTC tonight) | | | |
| Tests before audit | `score_cache_test`, `unscoreable_reason_test`, `v150_fixes_test`, `test_core_properties` in CI; `bad_input_test`, `behavioural_fixtures`, `test_alpha_audit`, `full_audit` outside CI | | | |

Every stage exists and was traced: source, factor, composite, two tables, API, UI code.

## 3. Factor reports (independent oracle, synthetic inputs)

**About the oracle.** It is written in plain Python (math, statistics) from the methodology document.
It never calls a production function to obtain an expected value. Providers are stubbed.

| Factor | Cases | Covered | Result |
|---|---|---|---|
| Momentum | 20 | Normal; exactly 60 closes; 59; none; timeout; HTTP 429; NaN gaps; flat; decline; ×50 rally; high volatility; window boundaries at 253 and 274 closes; window dates; skipped month; identical inputs; out-of-order; duplicate dates; PIT vs live | **PASS** on the documented formula. Out-of-order and duplicate rows fail (D-08, latent). PIT std mismatch (D-07). |
| Sentiment | 11 | Mixed; none; undated (treated as 7 days old); unparseable date; future date; +05:30 timezone; `publishedAt`; all neutral; confidence cap; malformed article | **PASS** on the formula. Malformed article fails (D-09). |
| Quality | 17 | All parts; Piotroski only; statement fallback; no market cap; negative book value; loss and negative OCF; cover 1.2× and exactly 1.5× (strict); USD accounts with and without FX; Piotroski failure; nothing; ROE 300%; zero net income; F-score 0; helper exception | **PASS** |
| Value | 14 | 3 peers; 1 peer; mixed peer gaps; negative P/E; both negative (−0.5 at 0.6); both missing; identical peers (spread floors); 5 peers (first 3 used); absent P/E; P/E 0; P/E 900 | **PASS** on score and confidence. Interpretation text fails (D-04). |

**Composite.** 22 synthetic cases plus 12 rule checks, all PASS. They cover:
- favourable, unfavourable and mixed stocks;
- ±1 extremes;
- one or several factors missing;
- the exact boundaries 15, 40, −15 and −40, and just past each;
- identical inputs;
- refusal rules, ticker normalisation, the non-NSE suffix and custom weights;
- that the weights sum to 1 and match the spec.

**Unresolved specification questions** (reported, not decided):
- **Momentum confidence never exceeds 0.95.** The 231-day window is measured against 252.
- **NaN factor score.** A NaN would give a null score labelled NEUTRAL; the spec does not say what
  should happen.
- **Coarse peers for most of the universe.** About 2,250 of 2,462 stocks are not in the map and get
  peers through Yahoo's broad sector, for example "Consumer Cyclical" → Auto and "Basic Materials" →
  Steel_Metal.
- **Peers are always the first three names in a sector list.**
- **Aviation has one member**, so IndiGo always uses market averages.
- **Momentum refusals.** 45 of the 172 have 60 or more exchange closes in our own archive but fewer
  than 60 on Yahoo.

## 4. Extraction and completeness (cycle 2026-10-14)

| Stage | Count |
|---|---|
| Universe before scan | 2,494 entries; 3 are duplicates (D-03), plus 49 excluded for no market data |
| Rows written | 2,491 |
| Scored | 2,462 |
| Errors | 29, all "no market cap and fewer than 60 days of prices" |
| Momentum refused | 172 ("price history too short"; 162 listed since July 2025) |
| Value refused / P/E market fallback | 4 / 80 |
| Sentiment refused | 2 ("no news found") |
| Missing inputs | ROE 103, FCF 65, P/E 358, P/B 36 |
| Inputs fully stored (`raw_inputs_available`) | 2,041 |
| Headlines stored | 1,158 of 2,460 stocks with news (D-02; about 47% every night since 10-05, spread evenly over the run) |

**D-02 detail.**
- Peers were stored for 2,384 stocks in the same function, so the database itself is reachable.
- The headline insert fails per batch, and its exception is swallowed. Unlike `_write`, it has no
  row-by-row fallback.
- Duplicate headlines in one insert were ruled out on a temporary table.
- The cause is not established.

**Provider-side completeness is BLOCKED.** That would be what Yahoo and the news feeds hold versus what
was received, and there is no independent copy of their data.

## 5. Database and cache (temporary SQLite)

Checks D01–D14 all PASS:
- **Writes.** Re-saving keeps one row; stored values are exact. History keeps one row per stock per
  day, stores refusals as NULL, and a later partial write cannot erase a fuller one. Unknown models are
  rejected, and errors never reach history.
- **Tiers.** Only the last complete cycle is served. Errored and low-coverage rows are excluded. Tiers
  are ranks 1–100 and 101–250. Buys are in order, avoids never overlap buys, and contributions are
  weight × score × 100.

The score cache is covered by `score_cache_test` in CI.

**Not run:**
- concurrency;
- lock contention;
- database-outage injection;
- tests against Postgres itself.

No isolated Postgres exists, and production must not be used for them.

## 6. API and frontend

**API, through FastAPI's test client** (A01–A09, PASS):
- a valid request returns the oracle's score;
- a missing ticker gives 422;
- an unknown company gives 400 with the reason;
- a non-NSE symbol gives 400;
- `/alpha/universe/top` equals the stored tiers;
- `n=0` gives 422;
- history returns NULL refusals as null;
- an unknown history returns an empty list.

**Live production, read-only:**
- `/factors/history` for five stocks equals the database and the oracle (0.5–0.8 s).
- `/alpha/universe/top` took 31.8 s on a cold cache.

**Frontend:**
- **Build:** PASS.
- **Tests and linter:** none configured.
- **Signed-in pages:** BLOCKED (sign-in required).
- **Code review** found D-05: `StockExplorer.jsx:859-877` prints a refused factor as "0.0 pts" in green
  with an empty interpretation. `CapTierPicks.jsx:72` prints "+0", and `/alpha/universe/top` carries
  no refusal flag.
- **Public landing page:** D-11. `Landing.jsx:42` reads `scan.data.succeeded`, but the axios
  interceptor (`api.js:45`) already returns the body.

## 7. End-to-end traces (database → oracle → live API)

| Stock | Condition | Alpha | Momentum | Quality | Value | Sentiment | Reconciles |
|---|---|---|---|---|---|---|---|
| RELIANCE | full data | −2.57 | −0.2165 | 0.2991 | −0.3224 | 0.0946 | yes |
| IDEA | negative equity, valued on P/E only | 26.92 BUY | 0.8018 | −0.4621 (distress) | 0.6375 | 0.034 | yes |
| SBIFUNDS | momentum refused (new listing) | 2.15 | NULL (0 in composite) | 0.7432 | −1.0 | −0.0573 | yes |
| KALYANKJIL | wrong peers (D-01) | 8.35 | 0.3521 | 0.4278 | −0.9997 vs steel P/E 15.9 | 0.0131 | yes (to the defect) |
| PNCINFRA | no news | 14.57 | −0.638 | 0.968 | 0.8466 | NULL | yes |

The UI column is blocked (sign-in).

## 8. Tests and coverage

| Suite | Result |
|---|---|
| `run_ci.py` (67 suites, 170,339 checks) | PASS |
| `four_factor_oracle_test.py` (new) | 176 pass, 9 fail; every failure is a listed defect |
| `bad_input_test` 29/29, `consistency_test` CLEAN 14, `leak_test` CLEAN 5 + 4 known, `full_audit` 0 failures | PASS |
| `behavioural_fixtures` | FAIL (D-10) |
| `version_provenance_audit` | 5 gaps (D-12; 2 are from uncommitted 52-week work) |
| `test_alpha_audit`, `test_modules_integration` | BLOCKED: network-bound, stopped at the 400 s cap (the first had 0 failures at 30/60) |

**Coverage** is measured with stdlib `trace`, because coverage.py is not installed:
- four factor functions plus the composite: 88.6% of lines (333 of 376);
- `compute_alpha_score`: 82 of 83.

**Blocked tooling.** Branch coverage, lint, type checking and the dependency audit are blocked: the
tools are not installed, and installing them needs approval.

**Mutation check.** The new regression tests already fail against the current defective code
(U01–U04, V13, S11, M17–M19), so they are shown to detect the defects they target.

## 9. Changes made in this audit

**Added:**
- `backend/tests/four_factor_oracle_test.py`
- `docs/AUDIT_FOUR_FACTOR_2026-10-14.md`
- `docs/audit/four_factor_audit_2026-10-14.json`
- `docs/audit/four_factor_oracle_results_2026-10-14.json`

**Fixed the same day after owner approval** ("do the no-score fixes"). One commit each; no score,
ranking or contribution changed.

| Defect | Commit | Regression evidence |
|---|---|---|
| D-03 | `beb3735` | oracle U01 now passes |
| D-05 | `7b48397` | oracle D15/D16 pass |
| D-04 | `332389e` | oracle V13 passes |
| D-02 | `40c2b23` | oracle D17 passes. The cause is still to be read from the new log line after the next scan. |
| D-11 | `e117f0f` | local build against the live API shows 2,462 |
| D-10, D-12 | `cf7f32e` | `behavioural_fixtures` reports 339 cases identical; `version_provenance_audit` reports 102/102 captured |

**After the fixes:**
- Oracle suite: 181 pass, 7 fail. The remaining failures are D-01, D-07, D-08 and D-09, which are
  still open by decision.
- `run_ci.py`: 67/67.
- `version_provenance_audit`: still reports 4 drift self-test gaps (section 5). These existed before
  this audit and are untouched by it.

**Not fixed:**
- **D-09:** its fix can change a score when a headline lacks a title, so it was not counted as a
  no-score fix.
- **D-01, D-06:** score-changing; they wait for a written proposal.
- **D-07, D-08:** open.

The oracle suite is still outside CI, because it fails until those are decided.

## 10. Proposed fixes (each waits for owner approval)

**Display-only, no score changes:**
- **D-03:** de-duplicate the priority list in `universe_scan._universe`.
- **D-04:** parenthesise the interpretation expression.
- **D-05:** show "not measured: reason" for refused factors; add a per-factor refusal flag to
  `/alpha/universe/top`.
- **D-11:** read `scan?.succeeded`.
- **D-10:** re-record the snapshot.
- **D-12:** update the registry.

**Provenance, no score change:**
- **D-02:** log the exception type in `_write_articles` and fall back row by row, as `_write` does.
- **D-09:** skip a headline without a title rather than fail the factor. This changes a score only
  when such a headline exists.

**Score-changing (version bump, written proposal):**
- **D-01:** fix the sector map: Kalyan Jewellers to Consumer_Durables only; Edelweiss to NBFC;
  KEYFINSERV out of Real_Estate; one sector per stock.
- **D-06:** drop non-positive peer multiples, as is already done for the stock itself.

**Research:**
- **D-07:** correct the docstring, or align the std and re-run factor test 1 as a declared correction.

## 11. Reproduce

```
cd backend
python tests/run_ci.py
python tests/four_factor_oracle_test.py --report ../docs/audit/four_factor_oracle_results_2026-10-14.json
python -m trace --count --summary --missing --coverdir=%TEMP%/v1cov tests/four_factor_oracle_test.py
cd ../frontend && npm run build
```

The production reconciliation queries are read-only SQL against `alpha_scan2`, `factor_history`,
`factor_inputs`, `factor_input_peers` and `factor_input_articles` for cycle 2026-10-14. They are recorded
in this session.

## 12. Release gate

| Gate | Met |
|---|---|
| Four factors traced end to end | yes (UI by code review only) |
| Formulas verified, independent checks pass | yes |
| Inputs extracted and reconciled | yes on our side; provider side blocked; D-02 open |
| Types, units, identifiers, dates | yes |
| Missing data and short history | yes |
| Composite and rankings verified | yes |
| Database and cache | yes on SQLite; Postgres concurrency not run |
| API reconciles with storage | yes |
| Frontend shows correct values | **blocked** (sign-in); D-05 and D-11 found in code |
| No unresolved P0/P1 | **no** (D-01) |
| Lint, type check | **blocked** (not installed) |

**Decision: FAIL.**
