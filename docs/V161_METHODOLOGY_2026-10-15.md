# v1.6.1: scoring methodology record (approved 2026-10-15; not yet frozen)

**Owner decision, 2026-10-15:** "yes lock the libraries and use v1.6.1".

**Status.** Approved as a label. **v1.6.0 stays the frozen model** until v1.6.1 is frozen in
`strategy_versions`. That freeze happens at deploy, and it is a production write that needs its
own approval at the time. Nothing has been deployed, pushed or frozen.

## What v1.6.1 is

v1.6.1 is v1.6.0 with four rule changes. **None changed a stored score or label on any record
checked** (`RELEASE_IMPACT_MATRIX_2026-10-15.md`).

| Change | The rule now | Evidence of no score change |
|---|---|---|
| **Sentiment failure policy** | A headline whose FinBERT inference fails is skipped and counted (`inference_failures`). If every headline fails, sentiment is refused ("sentiment inference failed"). Genuine neutral results are unchanged | 0 of 1,024,064 stored headlines carry the old failure signature (neutral at confidence exactly 0.0) |
| **S11** | A headline with no title is skipped instead of voiding sentiment | 0 untitled headlines stored |
| **M17/M18** | Closes are sorted by date, and one row per date is kept, before the 12-1 window | 0 of 2,462 live Yahoo series out of order or with repeated dates |
| **FinBERT pinned** | `ProsusAI/finbert` at revision `4556d13015211d73dccd3fdd39d39232506f3e43`, recorded in the spec (`sentiment_model`) | The baseline reproduces exactly; production already runs this revision |

**The spec also records, for the first time, values that were already in use:**
- `sector_map`: the map, its order, peer counts and the Yahoo fallback;
- the sentiment model details;
- library versions.

Weights, thresholds, labels and factor formulas are **unchanged** from v1.6.0.

## Version stamps

| Stamp | Before | After | Why |
|---|---|---|---|
| Frozen methodology label | v1.6.0 | **v1.6.1** (at freeze) | The owner's decision |
| `alpha_model.MODEL_VERSION`, stamped on every score result | `alpha-v5-statement-inputs` | **`v1.6.1-sentiment-failure-policy`** | Its rule: "bumped whenever a change alters what a score means". The rules changed |
| `universe_scan.MODEL_VERSION`, on scan rows | `v1.5.0-statement-inputs` | **Unchanged** | Its rule: "bump when the alpha model changes in a way that **invalidates stored scores**". Rows with an older stamp are re-scored. No stored score is invalidated (impact matrix), so a bump would force a full, needless re-scan of about 2,462 stocks on deploy |

**Correction.** `RELEASE_IMPACT_MATRIX_2026-10-15.md` proposed `v1.6.1-sentiment-failure-policy` for
"MODEL_VERSION (now `v1.5.0-statement-inputs`)". That merged two different constants. The intended
stamp is on the per-score constant. The scan constant stays as it is, for the reason above.

## The software environment (owner decision: locked)

`backend/Dockerfile` now installs exactly the stack production installed on 2026-10-06:
- the base image is pinned by digest (`python:3.12-slim@sha256:ddb0207a…`);
- 93 packages are hash-locked (`requirements-production-locked*-2026-10-06.txt`), with
  `--require-hashes --no-deps`, then `pip check`;
- FinBERT is pre-downloaded at the pinned revision.

All 19 direct dependencies in `requirements.txt`, plus torch, are in the locked set. A later
library upgrade has to be a reviewed change to the lock files.

**Not yet verified:** that this image builds and runs on Linux with Python 3.12. That is
`verify-production-env`'s job (unpushed), and it must pass before any deploy.

## Not in v1.6.1

- the sector map change (the draft is renumbered v1.6.2, not approved);
- the 52-week display (v1.7.0 proposal);
- the rights reparse, which is data, not methodology, and separately approved;
- any weight or threshold change.

## Before deploy (each needs the owner)

1. ~~`verify-production-env` passes on GitHub's Linux runner.~~ **PASSED 2026-10-23.**
   - Run 39971464918, branch pushed by the owner's instruction, commit `0c0eda4`.
   - Every step succeeded, including the in-image verification, whose script exits non-zero on any
     failed check. That covers Python 3.12.15, the 93 hash-locked packages, `pip check`, the test
     suites, the FinBERT baseline, and app startup with its endpoints.
   - Evidence artifact `production-image-verification` (sha256 `5cf5fc0a…`) can be downloaded while
     signed in. Annotations: only the Node 20 deprecation and the runner-label notice.
   - **Note:** this verified the locked environment with `d9b474a`'s code; `main`'s code has passed the
     same suites locally.
2. A deploy window: outside 00:02–03:00 UTC, after the nightly scan finishes (about 03:30 UTC), and
   no backfill running.
3. After deploy, the v1.6.1 freeze. Then check `/strategy/drift/v1.6.1` (`behavioural_drift: false`)
   and the live commit.
