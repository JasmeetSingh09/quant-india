# AGENTS.md: rules for any AI agent working on Quant India

Read this before changing anything. It applies to every agent: Claude Code,
Codex, or anything else. The owner is Seeraj; the project is his son
Jasmeet's capstone, and it is entered in research competitions (ISEF, the
Wharton Global Investment Competition). Honesty of the research matters more
than features.

## What this is

An NSE quant research platform.

- **Backend:** FastAPI in `backend/` (`main.py`, `modules/`), deployed on
  Render as a Docker service. Postgres (Supabase) in production; SQLite
  locally.
- **Frontend:** React and Vite in `frontend/`, deployed on Vercel.
- **Live model:** V1, the four-factor model in `backend/modules/alpha_model.py`:
  momentum 35%, quality 25%, sentiment 25%, value 15%. V2 (six factors) is
  research only.
- **Research scripts:** `research/`. **Decision records and results:** `docs/`.

## Hard rules: never break these

1. **No NSE data collection.** NSE downloads have been paused since 2026-09-08
   under a written commitment to NSE. Never add or run code that fetches from
   nseindia.com, and never use third-party copies of NSE data.
2. **No automated downloading from BSE** (bseindia.com). Its terms forbid it
   without BSE's written consent, which has not been given. People may
   download by hand.
3. **The v1.4.1 model is frozen** (frozen 2026-09-14; spec hash
   `ab840c874bbd7923`). Do not change factor formulas, weights, thresholds,
   signal cut-offs, portfolio construction or validation gates. Any
   behavioural change needs a written proposal, the owner's approval and a new
   version. `GET /strategy/drift/v1.4.1` must keep reporting
   `behavioural_drift: false`.
4. **Pushing to `main` deploys to production** (Render for the backend, Vercel
   for the frontend). Only push or merge to `main` with the owner's explicit
   approval.
   - **Never deploy between 00:02 and 03:00 UTC** (05:32–08:30 IST), while
     the nightly scan runs.
   - Never deploy while a backfill is running.
5. **No production changes without approval.** That covers any POST that
   writes, freezes, refreshes or backfills. Read-only GETs are fine.
6. **Credentials.** Never ask for, store or paste secrets: DATABASE_URL, the
   Supabase keys, the Render dashboard, API keys. Dashboard actions are the
   owner's.
7. **Research integrity.**
   - Never fabricate data or fill missing values with zero.
   - Never tune a model to look good on a backtest.
   - Never claim predictive power without an out-of-sample, point-in-time
     test.
   - Write a test's rules down and commit them (`docs/PREREG_*.md`) before
     computing it, then record the result whether it passes or fails.
8. **No scope creep.** Big new features (new optimisers, ML models, options
   tools) come after validation, in the owner's order: freeze → data →
   integrity → validation → robustness → V2 → product → research → advanced.
   Propose them; do not build them unasked.

## What is proven, and what is not (keep all wording consistent with this)

| Factor | Status | Record |
|---|---|---|
| Momentum (12-1, volatility-adjusted) | **Passed** pre-registered point-in-time tests, 2011–2026. Not shown among the largest, most liquid stocks. | `docs/FACTOR_TEST1_RESULT_2026-09-13.md`, `docs/MOMENTUM_ROBUSTNESS_RESULT_2026-09-18.md` |
| Low risk (V2 only) | Tested, **did not pass** | `docs/FACTOR_TEST1_RESULT_2026-09-13.md` |
| Value, quality | Our scores **untested**; the ideas are supported by academic data | `docs/IIMA_FACTOR_CHECK_RESULT_2026-09-17.md`, `docs/FRENCH_QUALITY_VALUE_RESULT_2026-09-17.md` |
| Sentiment | Untested; the GDELT test is in progress | `research/gdelt_stream.py` |
| Combined score and labels | **Untested** | — |

The single source for this in the app is `backend/modules/factor_evidence.py`.
Signals are shown as ranks ("Top ranked" … "Bottom ranked", in
`frontend/src/signalLabel.js`), never as recommendations.

## How to check your work

- **Backend gate (must pass before any merge):**
  `cd backend && python tests/run_ci.py`. It runs 52 suites, needs no network,
  and takes about 5 minutes. A new test file must be added to `SUITES` in
  `tests/run_ci.py`.
- **Frontend:** `cd frontend && npx vite build` must succeed.
- **Production, read-only, after a deploy:**
  - `GET /strategy/drift/v1.4` gives the live commit;
  - `GET /strategy/drift/v1.4.1` must show no behavioural drift;
  - `GET /health/caches` gives memory (the plan is 2 GB; keep it under about
    1.6 GB at idle).
- **Server memory:** the backend runs FinBERT (about 800 MB) plus nightly
  scans. Don't add unbounded caches; use `modules/bounded_cache.py` or
  `modules/swr_cache.py`.

## How agents work together

- **Branches:** each agent works on its own branch or git worktree, never
  directly on `main`. The folder is synced by OneDrive, so two agents editing
  the same checkout will clash.
- **Merging:** one agent (Claude Code, by default) merges to `main` and runs
  the post-deploy checks, only after the owner approves.
- **Reviewing:** the reviewing agent runs the backend gate and the frontend
  build on the other's branch and reports findings before any merge.
- **Handing off:** keep changes small, with a commit message saying what
  changed, why, and what was tested. End commit messages with the agent's
  attribution line.
- **Code style:** match the surrounding code. Comments explain *why* a change
  was made, citing dates and measured numbers.

## Where things are

| Need | Look in |
|---|---|
| Model and scoring | `backend/modules/alpha_model.py` (V1), `alpha_v2.py` (V2) |
| Nightly scan | `backend/modules/universe_scan.py`; scheduler in `backend/main.py` |
| Point-in-time tests | `backend/modules/pit_validation.py`, `pit_backtest.py` |
| Frozen spec and drift | `backend/modules/strategy_version.py` |
| Decisions and results | `docs/` (dated file names) |
| Dashboard | `frontend/src/pages/Dashboard.jsx` |
