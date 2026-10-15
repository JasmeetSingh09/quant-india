# Release decision preparation (2026-10-15)

**A recommendation only. Nothing has been deployed, pushed or written to production.** Every
production fact below comes from read-only queries and the public `GET /strategy/drift/v1.6.0`.

## 1. Where things stand

| | Commit | How established |
|---|---|---|
| **Backend running on Render** | `cf9e3be` | `/strategy/drift/v1.6.0`: environment `code_commit` |
| **Frontend live on Vercel** | `d9b474a` | Vercel deployed it on 2026-10-14 |
| `origin/main` (GitHub, public) | `d9b474a` | `git fetch` |
| **Local `main`** | `5705d95` | 20 commits ahead of `origin/main`. Not pushed |

**Live drift for v1.6.0** (2026-10-15):
- `behavioural_drift: false`;
- `environment_drift: true`. Only the code commit differs: frozen `61c2289`, live `cf9e3be`.

**The backend release is everything from `cf9e3be` to `5705d95`, not just the 20 local commits.**
`d9b474a` and the 15 commits before it were pushed. Render did not build them, because the tip
commit touched only ignored paths. So **two tranches** of backend code are waiting.

## 2. Inventory of changes that reach the running app

### Tranche 1: `cf9e3be..d9b474a` (public, never built by Render)

| Commit | Change | Effect on scores | Evidence |
|---|---|---|---|
| `63d84d0` | Rights issues adjusted at the theoretical ex-rights price | Point-in-time research prices only. The live score uses Yahoo prices | `rights_adjustment_test` 7/7. **The stored rights rows are still unparsed (kind `other`); the reparse write is a separate step awaiting approval** |
| `beb3735` | Scan universe lists each stock once | No score change; removes duplicate rows | Audit 2026-10-14 |
| `7b48397` | Unmeasured factors flagged `not_measured` in scan rows | No score change; adds a field | The frontend already reads it (section 4) |
| `332389e` | Value interpretation keeps the distress and one-measure notes in every band | Text only | Audit |
| `40c2b23` | Provenance: a failed headline batch is retried row by row and the reason logged | Provenance records only | Audit |
| `cf7f32e`, `d9b474a` | Tests, the re-recorded baseline, the audit | None | — |

### Tranche 2: `d9b474a..5705d95` (local only)

| Commit | Change | Effect on scores | Evidence |
|---|---|---|---|
| `04a5f1c` | M17/M18: closes sorted, one row per date, before the momentum window | None observed: Yahoo series are already sorted and unique | 339/339 snapshots identical |
| `6e07521` | S11 (D-09): an untitled headline is skipped instead of voiding sentiment | None so far | All 2,410 sentiment refusals since 2026-09-04 were "no news found". 0 untitled headlines stored on 2026-10-14 |
| `7b013ba` | D-07: docstring corrected; calculation unchanged | None | — |
| `67d52f7`, `65c3fc9` | The spec captures `sector_map`; peer constants promoted unchanged | None | 339/339; `sector_map_spec_test` 15/15 |
| `d70287d` | FinBERT pinned to `4556d130` (sentiment.py and the **Dockerfile**); the spec records `sentiment_model` and library versions | None: production already runs `4556d130` | Baseline reproduced exactly; `finbert_pin_test` 13/13 |
| `adf52d9`, `ccbd90e` (merged `39cbc74`) | **Sentiment failure policy.** A headline whose inference fails is skipped and counted; if all fail, sentiment is refused | **Changes a score only when FinBERT raises.** How often that happens in production cannot be measured: the old code averaged failures in as zeros without recording them | Real-model injection 10/10; oracle suite |
| `99bf7dd` and the docs | Tests and documents | None | — |

**No tranche-2 commit touches `frontend/`.**

## 3. Regression gates

Measured 2026-10-15 on a **clean checkout of `5705d95`** (the uncommitted 52-week work set aside),
Windows, Python 3.13:

| Gate | Result | Expected |
|---|---|---|
| `run_ci` | **69/69 suites**, 170,367 checks | 69/69 |
| Behavioural snapshots | **339/339 identical** | Identical |
| Four-factor oracle | **204 pass, 3 fail**, all D-01 (sector map) | D-01 stays open until the v1.6.1 sector-map proposal is decided. It is **not** in this release |
| Spec, local main vs public `d9b474a` | **Two fields added** (`sector_map`, `sentiment_model`); **no captured value changed** | Only additions |

**Interpreter note.** The project venv (`venv/`) lacks `feedparser`, so three suites fail under it.
They pass under the interpreter every baseline was measured with. Production's `requirements.txt`
includes `feedparser`, so this is a stale local venv, not a code fault.

**What the drift check should report after a deploy:**
- `behavioural_drift: false`;
- `coverage_gap: [sector_map, sentiment_model]`, meaning the v1.6.0 hash never covered those
  fields.

The failure policy changes behaviour without changing a captured value. That is the reason it
needs its own version (section 5).

**Not yet verified:**
- **The Linux / Python 3.12 production image.** The `verify-production-env` branch is unpublished,
  and it tests the environment with `d9b474a`'s code, not `5705d95`'s.
- **An end-to-end start of `5705d95` in that image.** Covering this means running the same
  verification against `5705d95`, which would publish the audit documents to the public repo. The
  alternative is Docker on a machine that has it.

## 4. Frontend and backend compatibility

- **Today.** The live frontend (`d9b474a`) already expects `not_measured` in scan rows, and the
  live backend (`cf9e3be`) doesn't send it. The frontend checks for it with
  `r.not_measured?.includes(k)` and **falls back to the old display**. Nothing is broken; the feature
  is half-delivered.
- **After a backend deploy.**
  - `not_measured` arrives and the feature completes.
  - The refusal reason "sentiment inference failed" is shown by the existing
    `Not measured: {reason}` path (`factorRefusal.isRefused`: a reason plus zero confidence).
  - The new keys `inference_failures` and `untitled_articles_skipped` are additive and unread.
  - **No incompatibility found.**
- **No frontend deploy is needed** for this release.

## 5. Sentiment methodology and the version label

- The failure policy and S11 are sentiment **behaviour** changes. They were approved under the
  working identifier `sentiment-failure-policy`, with no final version.
- Under the frozen-model rule they need a **new version**, frozen at deploy. That freeze is a
  production write and needs approval at the time.
- **The label is the owner's decision. Options:**
  - **(a) Recommended: v1.6.1** = "sentiment failure policy, FinBERT pin, data-integrity fixes,
    spec coverage". The draft sector-map proposal currently titled v1.6.1 would be renamed v1.6.2
    before it is decided. It is only a draft, so renaming it changes nothing that has been approved.
  - **(b)** Keep v1.6.1 for the sector map and label this release v1.6.2. Releases would then land
    out of number order.
- **`MODEL_VERSION`** (the string stamped on every score, currently `v1.5.0-statement-inputs`) is also
  the owner's to set. The commit note left it alone on purpose.

## 6. The main release risk: an uncontrolled environment change

The production `Dockerfile` installs **unpinned** packages:
- `torch` from the CPU index, with no version;
- `transformers`, `fastapi`, `uvicorn`, `requests`, `apscheduler`, `quantstats`, `arch`, `xgboost`,
  and others.

Its base image is the floating tag `python:3.12-slim`.

**Any rebuild today installs whatever is newest**, not the set production installed on
2026-10-06. A deploy would therefore change **the code and the library environment at once**. If
anything moved, the cause could not be attributed to either.

**The mitigation is already prepared and verified offline:** the 93-package hash-locked set on the
`production-constraints` branch. Applying it to the production `Dockerfile` is an **owner
decision**, and it was deliberately not taken. ("Keep it separate from main and do not apply it
yet.")

## 7. Recommendation

1. **Do not deploy yet.** Three things come first:
   - **(i)** the isolated image build passes (push `verify-production-env`);
   - **(ii)** the owner decides whether the release builds with the locked environment (section 6);
   - **(iii)** the owner picks the sentiment version label and `MODEL_VERSION` (section 5).
2. **When those are settled, release both tranches together** as one versioned backend deploy:
   - outside 00:02–03:00 UTC (the nightly scan ran to about 03:11 UTC on 2026-10-14, so after
     about 03:30 UTC);
   - not during a backfill;
   - then freeze the new version;
   - then confirm the live commit and drift from `/strategy/drift/<new version>`.
3. **Prefer the locked environment for this release.** The code changes are then the only changes,
   and the drift record's environment block matches 2026-10-06. Upgrading libraries, if wanted, is a
   later release of its own.
4. **Keep the following separate from this release:**
   - the v1.6.1/v1.6.2 sector map;
   - the 52-week display (v1.7.0);
   - the rights reparse write;
   - library upgrades;
   - any research run.
