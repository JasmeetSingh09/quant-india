# Production environment verification (isolated; deploys nothing)

**Question.** Does the exact Python environment production installed on 2026-10-06 (`cf9e3be`)
rebuild, install and run correctly on Linux with Python 3.12?

**Contents:**
- `backend/constraints-production-2026-10-06.txt`: 93 exact versions, read from Render's build log.
- `backend/requirements-production-locked-torch-2026-10-06.txt` and `…-locked-2026-10-06.txt`: the
  same 93 packages with the sha256 of the exact file production downloaded, one file per Dockerfile
  pip step.
- `docs/audit/production_dependency_manifest_2026-10-06.json`: versions, files, hashes and their
  sources.
- `verify/Dockerfile.production-2026-10-06`: `FROM` the pinned base-image digest, both steps
  `--require-hashes --no-deps`, FinBERT pre-downloaded at revision `4556d130`.
- `verify/verify_production_image.sh`: the checks below, run inside the image.
- `.github/workflows/verify-production-image.yml`: builds and runs it on GitHub's Ubuntu runner, only
  for this branch. It uses no secrets, no database and no Render.

**Code under test:** `d9b474a`, the commit this branch starts from, already on GitHub. Expected:
- `run_ci`: 67/67;
- behavioural snapshots: 339/339 identical;
- the oracle suite: 181 pass and 7 fail. Those are the documented open defects D-01, D-07, D-08 and
  D-09 at that commit.

**Acceptance criteria:**
1. Python 3.12.15.
2. All 93 packages at the manifest's version; the hashes verified at install (`--require-hashes`);
   `pip check` clean.
3. The test results above.
4. FinBERT reproduces the recorded baseline: labels and 4-decimal confidences equal, and the same
   failure path.
5. The app starts and answers `/`, `/openapi.json`, `/alpha/universe/status` and
   `/stock/universe/stats`.

A failure is diagnosed from the kept logs; constraints are never loosened to get a pass.

**Known and expected:**
- At `d9b474a`, the app loads FinBERT without a revision, so in the container its startup fetches
  upstream main.
- The FinBERT check (criterion 4) pins the revision explicitly.
- The base image's OS packages (`build-essential`, `curl`) are not hash-pinned, as in production.

**Deployment.** Render deploys only `main`. Vercel is told to skip this branch in
`frontend/vercel.json`.

**Note.** The manifest's `verification` notes cite local comparison files that are not on this
branch. Their results are restated in the criteria above.
