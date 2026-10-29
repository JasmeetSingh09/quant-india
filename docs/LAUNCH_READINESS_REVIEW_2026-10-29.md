# Launch readiness: database security and claims review (2026-10-29)

Both checks were read-only. Nothing was changed in Supabase, the code, or production.
Every fix below needs the owner's approval.

## 1. Supabase database security (project uoiielbtcfasjzpflimz)

### What was checked
- Supabase security advisors.
- Table privileges and RLS state for every table in `public`.
- The one flagged function's definition.
- Every use of the Supabase client in `frontend/src`.

### Findings

| # | Finding | Risk | Evidence |
|---|---|---|---|
| S1 | All 31 `public` tables have RLS **on** with **no policies**, so the public API (anon or signed-in key) can read or write nothing | None. This is the safe state | Advisor `rls_enabled_no_policy` (INFO) ×31 |
| S2 | The frontend uses Supabase **only for sign-in** (`supabase.auth.*` in `AuthContext.jsx` and `api.js`). It makes no `.from()`, `.rpc()` or storage calls. All data goes through the backend, which connects as the owner role | None. It confirms S1 does not break the app | grep of `frontend/src` |
| S3 | `public.rls_auto_enable()` is `SECURITY DEFINER` and can be called by `anon` and `authenticated` at `/rest/v1/rpc/rls_auto_enable` | Low. It is an event-trigger function (`RETURNS event_trigger`, owner `postgres`), so a direct call should error rather than run. It is still an unneeded door | Advisor (WARN) and function definition |
| S4 | `anon` and `authenticated` still hold table privileges (SELECT, INSERT, …) on the `public` tables. RLS is the only barrier | Low today. If someone ever adds a careless policy, or turns RLS off on one table, that table opens to the internet | Privilege query |
| S5 | Leaked-password protection is **off**: sign-up accepts passwords already published in breaches | Medium for user accounts | Advisor (WARN) |

### Proposed fixes (none applied)

**F1 (S3):** a one-line migration. The function keeps working as an event trigger.
```sql
revoke execute on function public.rls_auto_enable() from anon, authenticated, public;
```

**F2 (S4), defence in depth:** remove the API roles' table privileges, because nothing uses them (S2).
```sql
revoke all on all tables in schema public from anon, authenticated;
alter default privileges in schema public revoke all on tables from anon, authenticated;
```
Before applying it, confirm in the Render logs that the backend's `DATABASE_URL` uses the
`postgres` owner role and not an API key. Otherwise this would cut the backend off.

**F3 (S5):** owner, in the dashboard: Authentication → Policies/Settings → enable *Leaked password
protection*. This is a dashboard toggle, not code.

## 2. Claims review: wording that implies the signals are proven

**Scope:** the landing page, all pages and components in `frontend/src`, `index.html` meta tags,
backend text shown in the UI, and `README.md`.

**Overall:** most of the app is already careful. The evidence panel says "not established", the
WhySignal box says "Experimental", the glossary explains that confidence means data coverage,
and Monte Carlo says it "does not predict". The problems are concentrated in **marketing copy and the
README**, which were written before the validation work.

### Findings, most important first

| # | Where | Now says | Problem | Proposed wording |
|---|---|---|---|---|
| C1 | `Landing.jsx:24` (Track record card) | "Nobody else does this, and it is the reason you can trust the other numbers." | It is an unverifiable superlative, and it claims trust that the evidence does not give. Most factors are untested | "We publish the model's past calls with their real returns, including where the evidence is weak or missing, so you can judge the other numbers yourself." |
| C2 | `Landing.jsx:139` (Honesty card) | "the top fifth beat the bottom fifth by 1.5% a month" | The figure is **before trading costs**. The net-of-costs test (momentum rev3) has not run, so a reader will take it as an achievable return | Add "before trading costs (a net-of-costs test is pre-registered and not yet run)". |
| C3 | `RiskLab.jsx:56` | "Institutional-grade rigor" | It is a marketing claim with no standard behind it | "Is a result real or luck, and how much should you bet?" |
| C4 | `Landing.jsx` hero h1 | "The maths quant desks use, across the NSE" | It is borderline: true of the formulas, but it suggests professional-grade results | Optional: "The maths behind quant portfolios, applied to the NSE". |
| C5 | `README.md:5` | "**Validation:** … ~168,000 property/edge-case assertions" | These tests check that the **maths is computed correctly**, not that the signals predict returns. The heading reads as model validation | Rename it **"Correctness tests:"** and add one sentence: "These check the implementations, not whether any signal predicts returns. See the Evidence panel and the research write-ups for that." |
| C6 | `README.md` Features and file tree (Markets row, `regime_detector.py`) | "market regime (3-state Gaussian HMM)" | That regime model **failed its test and was replaced** in the app by the market-risk reading. The landing page already says so | "market-risk reading (the earlier HMM regime model failed its test and is retired)". |
| C7 | `README.md` Stock Detail row and `alpha_model.py` comment | "4-factor alpha score with **AI explanation**" / "+ XGBoost" | "AI explanation" suggests a learned model explaining the score. The score is a fixed, hand-weighted sum (`FACTOR_WEIGHTS`, unchanged since the first commit), and `alpha_model.py` contains no XGBoost at all | "4-factor score (fixed, hand-set weights) with each factor's contribution shown". |
| C8 | `README.md` Alpha model section | "Ranks every large liquid NSE stock …" | Momentum's measured edge **did not appear** among the largest, most liquid stocks (the landing page says so). The wording points the reader at exactly the place there is no evidence | "Ranks NSE stocks on four factors. Only momentum has been tested; see RESEARCH_momentum.md." |
| C9 | `WalkForward.jsx:68` | Win rate turns green above 55% | Green reads as "good / proven", with no significance test behind the threshold | Optional: keep the number and drop the colour, or colour only when the panel's own significance test passes. |

### Not a wording fix: for the owner and the SEBI consultation
- **"Top Picks", BUY / SELL / Strong Buy labels, and the price/signal alerts.** These are
  presented as signals, not advice, and every one carries "Not financial advice". Whether a
  public, free app that labels named stocks BUY/SELL needs SEBI Research Analyst registration is a
  **legal question**, already on the list for the SEBI consultation. The wording cannot settle it.
  Renaming (for example "Top Picks" → "Highest model scores", "BUY" → "Model: high score") would
  lower the risk, but it is a product decision for the owner.

### What is already fine (no change proposed)
- the `index.html` meta description ("including where it shows no edge");
- `EvidencePanel` ("not established" unless a factor is significant at 5%);
- `WhySignal` ("Experimental … has not been shown to predict");
- the backend `action_note` and `disclaimer`;
- the glossary entries for confidence, backtest, r_squared and regime;
- the Dashboard track-record caveats;
- the Monte Carlo and PortfolioCoach disclaimers;
- the Research page entries, which are phrased as questions.

## Deploy note
C1–C4 and C9 are frontend changes, and Vercel deploys them on push. C5–C8 are README only, and
pushing a README-only commit costs a Render build (memory: build minutes ran out on 2026-09-13).
Bundle them with the v1.6.1 deploy.
