# Production dependency manifest and verification (2026-10-15)

**Status: prepared for review on branch `production-constraints`, not on `main`. Nothing is
applied.**
- The Dockerfile and `requirements.txt` are unchanged.
- Nothing is pushed or deployed.
- Production remains `cf9e3be`.

**Request:** the owner, 2026-10-15. Build an exact record of the 2026-10-06 production environment
from the Render build log, verify it, and document every exception.

**Files:**
- `backend/constraints-production-2026-10-06.txt`: 93 exact pins, with a header naming the runtime
  facts the file does not control.
- `docs/audit/production_dependency_manifest_2026-10-06.json`: the same set, plus the source log
  lines, step, timestamp and the verification data.

## 1. Where the versions come from

**Build.** Render deploy `dep-db2aqcmq1p3s73efcci0` (commit `cf9e3be`, 2026-10-06 08:11–08:15 UTC).
Its build log holds two `Successfully installed` lines, copied verbatim into the manifest:

| Step | Line | Packages |
|---|---|---|
| Dockerfile `pip install torch --index-url …/whl/cpu` | 08:12:30 UTC | 10, e.g. torch 2.14.1+cpu, sympy, networkx, filelock |
| `pip install -r requirements.txt` | 08:13:10 UTC | 83, direct and transitive |
| **Total** | | **93** |

**What else the log fixes:**
- **Base image:** `python:3.12-slim@sha256:ddb0207a…78fe74c`.
- **Python:** 3.12.15, from the live spec environment, which the digest fixes.
- **FinBERT:** pre-downloaded at 08:13, before the 2026-10-12 upstream change, so revision
  `4556d130`.

## 2. Differences from what the repository specifies today

| Item | Repository today | Production 2026-10-06 | Effect of a rebuild today |
|---|---|---|---|
| Base image | `FROM python:3.12-slim` (a moving tag) | the digest above | may get a newer 3.12.x and OS libraries |
| torch | unpinned (`pip install torch`) | 2.14.1+cpu | latest CPU torch |
| fastapi | unpinned | 0.142.2 | latest |
| uvicorn[standard] | unpinned | 0.54.0 (with uvloop 0.23.0, httptools 0.8.0, watchfiles 1.3.0, websockets 17.2) | latest |
| python-multipart | unpinned | 0.0.32 | latest |
| psycopg2-binary | unpinned | 2.9.13 | latest |
| PyJWT | unpinned | 2.15.1 | latest |
| python-dotenv | unpinned | 1.2.4 | latest |
| requests | unpinned | 2.34.2 | latest |
| transformers | unpinned | 5.18.0 | latest |
| apscheduler | unpinned | 3.11.3 | latest |
| quantstats | unpinned | 0.0.86 | latest |
| feedparser | unpinned | 6.0.14 | latest |
| arch | unpinned | 8.0.0 | latest |
| xgboost | unpinned | 3.4.1 | latest |
| psutil | unpinned | 7.2.2 | latest |
| yfinance, pandas, numpy, scipy, statsmodels | pinned | 1.7.0, 3.0.5, 1.26.4, 1.17.1, 0.15.0 | unchanged (the pins match) |
| 73 transitive packages | unconstrained | exact versions in the constraints file | each may move |
| FinBERT revision | pinned on local `main` only (`model_config`), not deployed | 4556d130 | the deployed `main` would download upstream main, but the local pin fixes that |

**So:** of the 19 direct requirements, 5 are pinned and match production, and 14 are not pinned.
torch, the base image and all 73 transitive packages are also free to move on every rebuild.

## 3. Verification

| Check | Method | Result |
|---|---|---|
| The constraints file equals the log | parsed from the two log lines; no hand edits | 93 = 93 |
| The resolver reproduces production's versions | `pip install --dry-run --report` targeting cp312 / manylinux x86_64, binary wheels only, `-r requirements.txt -c constraints` | 86 resolved; **84 of 84 comparable packages at production's exact version; 0 at a different version** |
| The remaining differences are explained | the packages' own `requires_dist` markers | all 4 are platform conditions of resolving *on Windows*: uvloop (uvicorn[standard], `sys_platform != 'win32'`) and nvidia-nccl-cu13 (xgboost, `platform_system == 'Linux'`) are absent here and present on Linux; colorama (tqdm, typer, Windows) and tzdata (pandas, tzlocal, Windows) are present here and absent on Linux. On Linux the set equals production's |
| No source builds | the wheel types chosen | 58 pure wheels and 28 cp312/abi3 manylinux wheels; **0 source distributions** |
| Sentiment baseline | `finbert_prodmatch_comparison_2026-10-15.json` (torch 2.14.1, transformers 5.18.0, tokenizers 0.23.2, huggingface-hub 1.33.0, safetensors 0.8.0, revision 4556d130) | identical to the recorded baseline: labels and 4-decimal confidences equal; largest raw difference 4.8e-07; the same failure error |
| Inference venv against production | its pip freeze compared with the manifest | 34 shared packages: 31 identical; typer 0.27.3 vs 0.27.2 and hf-xet 1.7.0 vs 1.6.0 (that venv was installed without constraints); numpy 2.5.4 vs 1.26.4 (see the exceptions) |

## 4. Exceptions: what could not be reproduced exactly

| Item | Why | Consequence |
|---|---|---|
| Python 3.12.15 runtime | Not installed here, and installing it was not part of the approval. There is no Docker or WSL to run the digest image | The sentiment comparison ran on Python 3.13.3 |
| numpy 1.26.4 | It has no build for Python 3.13, so the comparison venv used 2.5.4 | The sentiment outputs were identical anyway, but the full app is not verified under 1.26.4 here |
| Linux platform | The host is Windows | Resolution was checked for Linux wheel tags, but markers were evaluated as Windows (explained in section 3); nothing was executed on Linux |
| The base image's pip | Its version is not printed in the log | Not recorded; a rebuild from the digest gets the same pip |
| An end-to-end app test under the exact environment | Needs Python 3.12 and Linux (the digest image) | **Not done**. The full app has not been run under production's environment |
| Package sources | PyPI and download.pytorch.org can withdraw or replace files; versions are pinned but file hashes are not | A future build could fail to find a file; a hash-pinned lock (`--require-hashes`) would make that an error rather than a silent change. Not prepared |

## 5. What applying it would involve (not done; needs explicit authorisation)

1. `FROM python:3.12-slim@sha256:ddb0207a…` instead of the moving tag.
2. Both `pip install` steps given `-c constraints-production-2026-10-06.txt`. The torch step keeps
   the CPU index.
3. Keep `FINBERT_REVISION = 4556d130` (already on local `main`).
4. Before any deploy:
   - build the image and run the full test suite inside it;
   - run the FinBERT baseline inside it;
   - compare `pip freeze` inside the image with this manifest, expecting 93 identical.

This would be the first verification on Python 3.12 and Linux.

**What a constraints file does not do.** It restricts versions. It does not fix the base image,
package-file hashes or the model files: those are steps 1 and 3 and the hash note above.

## 6. Package hashes (added 2026-10-15)

**Exact files.** The build log's `Downloading` lines name the **exact file** production fetched for
each of the 93 packages. All 93 map one to one onto the installed set at the same version.
- **download.pytorch.org (4):** torch, jinja2, markupsafe, setuptools.
- **PyPI (89):** everything else.

**Their sha256 hashes:**

| Source of the hash | Files |
|---|---|
| PyPI JSON API: the published sha256 for that exact filename. A PyPI filename can never be re-uploaded with other contents | 89 |
| download.pytorch.org simple index: the published `#sha256=` (torch) | 1 |
| Hashed the file fetched from download.pytorch.org, which publishes no hash for these mirrored files (jinja2 134,899 bytes, markupsafe 22,947, setuptools 1,256,108). PyPI's published hash for the same filename **matches** for all 3 | 3 |

**Checks on the hashes:**
- **Cross-check:** on the 81 filenames shared with the earlier resolver report, 81 agree and 0
  disagree.
- **Hash-checked dry run:** `pip install --dry-run --require-hashes --no-deps` of the 83-package lock,
  targeting cp312 on manylinux, exits 0 with all 83 accepted. pip verifies each file it uses against
  its hash.
- **Disclosure:** pip took these files from this machine's shared pip cache (3.5 GB) and downloaded
  nothing in that run. The earlier quiet resolver run may have filled part of that cache; quiet mode
  does not list what it fetched.

**Lock files:**
- `backend/requirements-production-locked-torch-2026-10-06.txt` (10 entries);
- `backend/requirements-production-locked-2026-10-06.txt` (83 entries).

Each pins `==version` plus `--hash`. Installed with `--require-hashes --no-deps`, nothing is resolved
at all.

**Not hash-pinned:**
- the base image's OS packages (`apt-get install build-essential curl`), which the production
  Dockerfile also installs unpinned;
- the base image's own pip;
- the FinBERT files, which are pinned by revision; the hub serves them by that commit.

## 7. The isolated Linux / Python 3.12 build: prepared, not yet run

**Why not run here.** This machine has no Docker, no WSL and no Python 3.12.

**The build is prepared as files on this branch:**
- **`verify/Dockerfile.production-2026-10-06`:** `FROM` the base-image digest, both pip steps
  `--require-hashes --no-deps` from the lock files, `pip check`, FinBERT pre-downloaded at
  `4556d130`, and then the current code.
- **`verify/verify_production_image.sh`:** runs inside the image, printing PASS or FAIL for each check:
  1. Python is 3.12.15;
  2. `pip freeze` equals the 93-package manifest, and `pip check` passes;
  3. `run_ci` passes, the 339 behavioural snapshots are identical, and the oracle suite gives 204 pass
     and 3 fail (the open D-01);
  4. the FinBERT baseline is reproduced (`verify/finbert_baseline_check.py`) on Python 3.12, Linux and
     numpy 1.26.4, the combination never yet run;
  5. the app starts and answers `/`, as the production HEALTHCHECK does, plus `GET /openapi.json`,
     `/alpha/universe/status` and `/stock/universe/stats`.
- **`.github/workflows/verify-production-image.yml`:** builds the image on GitHub's Ubuntu runner and
  runs the script.
  - It is triggered only by a push to `production-constraints`, or by hand.
  - It uses no secrets, no database and no Render.
  - It keeps `build.log` and `verify.log` as artifacts.

**What running it needs: pushing this branch to GitHub.** Owner authorisation is required.
- **Render** deploys only `main` (`autoDeploy` on branch `main`), so it would not deploy this branch.
- **Vercel** would by default build a preview for any pushed branch. Its project settings could not
  be read: the API refused the scope. So this branch's `frontend/vercel.json` sets
  `git.deploymentEnabled.production-constraints = false`.
- **The repository's normal CI** (`ci.yml`) would also run on the push. It is read-only.

**Alternative:** the owner runs the same two commands on any machine with Docker:
`docker build -f verify/Dockerfile.production-2026-10-06 -t qi-verify backend`, then the `docker run`
line at the top of the script.

