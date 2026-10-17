# Security audit: authentication and access control (2026-10-17)

**Prompted by** the external review of `d9b474a`. **Scope:** `backend/modules/auth.py` and every
route in `backend/main.py`, on local `main`.

**`main.py` is identical** in production (`cf9e3be`), public `d9b474a` and local `main`. No waiting
commit touches it. **Every finding below therefore applies to the live app today.**

**Method:**
- read the code;
- read production's public `GET /`;
- run read-only database queries.

**No write request was sent to production to test anything.** Nothing has been changed. The fix in
section 4 is a proposal awaiting approval.

## 1. What is fine

- **Production verifies tokens.** `GET /` reports `auth.verified: true`, with modes
  `HS256 (legacy secret)` and `ES256/RS256 (JWKS)`.
  - The "unverified `sub`" stopgap the reviewer flagged applies **only** when neither secret nor URL
    is set. That is not the case in production.
  - A token that fails verification is namespaced `unverified:<sub>`, so it can never address a
    verified user's rows.
- **User-owned writes take the caller's identity.** Theses, watchlist, portfolio, real-time
  simulations, share links, email preference and digest preview/send all use
  `Depends(current_user_id)`.
  - An anonymous caller shares one `"public"` bucket. That is a documented design choice: anyone
    can edit the public watchlist and portfolio. It is noted in section 3, not as a defect.
- **The integrity records are intact.**
  - `strategy_versions` holds exactly the 10 expected versions (v1.0 … v1.6.0), with the expected
    hashes. v1.6.0 is still `54ced1e2c8af0a77`.
  - The only retraction is v1.2's, on 2026-09-01, which is in the project history.
- **NSE and BSE collection routes are blocked** by the pause guards (`nse_access`, `bse_access`),
  whoever calls them.
- **No external caller** uses any write route.
  - The background jobs call their functions directly inside the server.
  - The nightly GitHub check only reads `/alpha/universe/status`.
  - The frontend calls none of the routes in section 2.

  Locking those routes breaks nothing that runs automatically.

## 2. Findings

**There is no global access control.**
- CORS allows every origin. The CORS comment calls the API "public read-only", which is no longer
  true.
- The only middleware is the rate limiter, which deliberately fails open.
- So a route without its own dependency is open to anyone who can reach the URL.

| # | Severity | Route(s) | What anyone can do today | Evidence |
|---|---|---|---|---|
| **F1** | **High, exploitable now** | `POST /strategy/freeze`, `POST /strategy/retract` | **Retract any frozen version**, including v1.6.0, or **freeze any version name first**. Freeze refuses to overwrite, so someone could take the name "v1.6.1" before the owner freezes it | No dependency on either route (`main.py:1853`, `:2235`). Not abused so far: the table holds only the expected rows |
| **F2** | **High, latent** (0 recipients today) | `POST /digest/run-now` | Trigger the weekly digest to **every opted-in user**, as often as they like. It falls in the "light" rate bucket: 180 a minute per caller, 1,200 per network. That means spam to real users, and a likely suspension of the sending Gmail account | No dependency (`main.py:2775`). `user_emails` has **0 rows** today, so nothing would send yet. It becomes live the moment anyone opts in |
| **F3** | Medium | `POST /alpha/universe/scan?force=true`, `POST /screener/refresh`, `POST /alerts/run-check`, `POST /alpha/retrain` | Start the most expensive background work at will: a full universe scan, a 5–10 minute screener rebuild, an alert pass. On a 2 GB instance with an OOM history (`render-oom-2026-09`), that is a denial-of-service lever. A forced scan can also collide with the nightly cycle | No dependencies. Only `/universe/scan` is in the "heavy" rate bucket |
| **F4** | Medium | `POST /simulator/seed-demos?replace=true` | **Delete and recreate** the leaderboard's example portfolios | No dependency (`main.py:2440`) |
| **F5** | Medium | `GET /health/corporate-action-audit?part=apply&confirm=APPLY-REPARSE` | **Write the corporate-action reparse**, the step that awaits the owner's separate approval. The writes are additive only (ON CONFLICT DO NOTHING), but they change research prices once the rights code is live. **The route's own docstring says "Nothing here writes"**, which is false for `part=apply` | The token is a fixed string printed in the public repo, so it guards against accidents, not people. A GET route that writes is also reachable by any link or crawler |
| **F6** | Low | `POST /predictions/seal`, `POST /predictions/snapshot` | Trigger work that is already idempotent: sealing skips sealed days; snapshot rows use `INSERT OR IGNORE` | No dependency. Low impact, but these write the track record and should not be public |
| **F7** | Low, blocked today | `POST /bhavcopy/fetch`, `/bhavcopy/backfill`, `/bhavcopy/backfill-range`, `POST /actions/backfill`, `POST /stock/universe/refresh` | Would start NSE or BSE downloads, but **the pause guards refuse**. If the pause were lifted, anyone could start backfills | No dependency; protected only by the pause |
| **F8** | Low, latent | `auth.current_user_email` | If `SUPABASE_JWT_SECRET` were unset while `SUPABASE_URL` is set, a token that **fails** verification still gives its claimed email. `POST /alerts/test` and `/alerts/send` send mail to that address, so the server could be made to email arbitrary people | `auth.py`: the fallback checks `not _JWT_SECRET` instead of "no verification configured at all". Production has the secret set, so it is not reachable today |

**Other reviewer items:**
- **Rate limiter fails open.** Confirmed and deliberate: an exception in the limiter serves the
  request. For routes moved behind admin (section 4) this stops mattering. Logging limiter
  failures is proposed.
- **`render.yaml` defines a Render frontend; the live frontend is Vercel.** Confirmed as an
  ambiguity in the file. Whether a Render frontend service actually exists has not been checked
  yet; that is a read-only follow-up.

## 3. Design questions for the owner (not defects)

- **Anonymous shared data:** should anonymous visitors be able to write the shared `"public"`
  watchlist, portfolio and theses at all, or only read them?
- **The pure calculators** (SIP, tax, optimisers, Monte Carlo, options, pairs, backtests) are public
  by design and rate-limited. They write nothing, and that seems right.

## 4. Proposed fix (not implemented; awaiting approval)

**A. An admin guard, `auth.require_admin`, that fails closed.** A request is admin only if one of
these holds:
1. it carries a token that **verifies** (the real check, never the unverified fallback) and whose
   `sub` is in `ADMIN_USER_IDS`, a comma-separated list held in the environment; or
2. it carries an `X-Admin-Token` header equal, by constant-time comparison, to `ADMIN_TOKEN`, held in
   the environment, at least 32 characters.

If neither variable is set, every admin route answers **403 "admin actions are not configured"**.
Missing configuration means locked, never open.

**B. Put behind it:**
- F1: freeze and retract;
- F2: digest run-now;
- F3: universe scan, screener refresh, alert run-check, retrain;
- F4: seed-demos;
- F5: corporate-action **`part=apply` only**; the read-only parts stay public;
- F6: seal and snapshot;
- F7: the five collection routes.

The background jobs are unaffected, because they call the functions directly. The F5 docstring is
corrected.

**C. F8:** `current_user_email` returns an email **only from a verified token**. With verification
configured, the unverified fallback is removed.

**D. Rate limiter:** move `/digest`, `/alerts`, `/screener/refresh` and `/alpha/retrain` to "heavy",
and log when the limiter fails. It stays fail-open for everything else, so a limiter bug can't take
the site down.

**E. A guard that stays fixed:** a new CI suite, `access_control_test.py`, that:
- checks every non-GET route (and the writing GET) against an explicit classification: public
  computation, user-owned, or admin. **A new route that is not classified fails CI**, so this can't
  quietly recur;
- uses FastAPI's TestClient to check that each admin route returns 403 without admin, with a forged
  token, and with `ADMIN_TOKEN` unset, and works with a valid admin token;
- runs unit tests of the F8 email fallback.

**What the owner would need to do** (secrets never go into chat):
- set `ADMIN_TOKEN` (a long random string), and optionally `ADMIN_USER_IDS` (your Supabase user
  id), in Render's environment;
- use the token for the v1.6.1 freeze after deploy:
  `curl -X POST -H "X-Admin-Token: …" …/strategy/freeze`.

**Release placement (recommendation):**
- **This ships with or before the v1.6.1 deploy.** The freeze of v1.6.1 is the first moment where F1
  can do real harm (name squatting, or a retraction during the release).
- It is a software change, not a methodology change, so v1.6.1's methodology record is unaffected.
- It would join `release-2026-10-A`, and the release gates are re-run.

## 5. Not covered by this audit

- **Supabase-side policies** (row-level security on the tables), and whether the database is reachable
  other than through the backend.
- **Frontend handling of tokens.**
- **Render and Vercel account settings.**
- **Dependency vulnerabilities.** The locked set has not been scanned against advisories.

Each is a candidate for a follow-up review.
