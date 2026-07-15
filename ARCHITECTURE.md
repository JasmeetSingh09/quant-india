# Quant India — Deployment Architecture

## Overview
Quant India is deployed as two independent services — a **frontend** (the user
interface) and a **backend** (all computation) — that communicate over HTTPS.
Separating them lets each be built, deployed, and scaled on its own.

```
                     User
                       │
                www.quantindia.app
                       │
                    DNS (registrar)
                       │
                   Vercel CDN
                       │
            React + Vite Frontend  ──►  Supabase (login / JWT)
                       │
              HTTPS API requests (JWT attached)
                       │
          Render Web Service (Backend)
                       │
             FastAPI + Python quant engine
                       │
       yfinance (NSE data) + FinBERT + RSS news
```

## 1. Domain
- **Domain:** `quantindia.app` (served at `https://www.quantindia.app`).
- The registrar's DNS points the domain at Vercel; Vercel issues the HTTPS
  certificate automatically.

## 2. Frontend hosting — Vercel
- **Framework:** **React + Vite** (a client-side single-page app). *Not Next.js —
  there is no server-side rendering; Vite builds static assets that Vercel's CDN
  serves.*
- **Language:** JavaScript (JSX).
- Screens: Landing (public), Login, Dashboard, Stocks/Screener, My Stocks,
  Simulator, Portfolio Lab, Research, Markets, Calculators.
- Advantages: global CDN, automatic HTTPS, fast loads, auto-deploy from GitHub.

## 3. Authentication — Supabase
- Email/password auth via **Supabase**. On login, Supabase issues a **JWT**.
- The frontend attaches that JWT (`Authorization: Bearer …`) to every API call.
- The backend verifies the JWT locally (HS256, `SUPABASE_JWT_SECRET`) and scopes
  each user's watchlist, portfolio, and simulations to their own account.
  Anonymous requests fall back to a shared "public" account.
- A **public landing page** is crawlable/SEO-visible; the app tools sit behind login.

## 4. Backend hosting — Render
- **Framework:** Python + **FastAPI**, run with a **single Uvicorn worker**
  (FinBERT is ~1.5 GB in memory, so one copy fits the 2 GB instance).
- Server-side computation: FinBERT sentiment, 4-factor alpha model, portfolio
  optimisation (Markowitz / Black-Litterman / HRP), Monte Carlo simulation,
  Fama-French regression, risk analytics, news aggregation, market-data processing.
- The frontend performs no heavy computation — it sends a request, the backend
  computes, and returns JSON that the frontend renders as charts/tables.

## 5. Data sources
- **Market data:** `yfinance` (NSE prices, fundamentals, history).
- **News:** RSS feeds (Economic Times, Moneycontrol, Google News search) with a
  NewsAPI fallback; scored by FinBERT.
- **Persistence:** SQLite by default, or Supabase Postgres when `DATABASE_URL` is set.

## 6. GitHub → CI/CD
```
Local commit ──► GitHub ──┬──► Vercel   (auto-deploy frontend)
                          └──► Render   (auto-deploy backend)
```
Every push to `main` auto-deploys both services — no manual uploads.

## 7. Request flow (example: Monte Carlo)
```
User clicks "Run Simulation"
        │
Frontend POST /montecarlo/simulate  (JWT attached)
        │
Render FastAPI → Python runs 10,000 simulated paths
        │
Returns JSON (percentiles, probabilities, fan chart)
        │
Frontend renders charts
```

## 8. Technology stack
| Layer | Technology | Hosting |
|-------|-----------|---------|
| Frontend | React + Vite, JavaScript (JSX) | Vercel |
| Auth | Supabase (JWT) | Supabase |
| Backend | Python, FastAPI (Uvicorn) | Render |
| AI/Quant | FinBERT, factor models, statistical/quant algorithms | Render |
| Data | yfinance (NSE), RSS/NewsAPI | — |

## 9. Deployment challenges encountered
- Connecting the custom domain and resolving DNS propagation / redirects.
- Deploying the FastAPI backend separately on Render and wiring the frontend to it.
- **Render memory limits:** FinBERT is heavy — running a single Uvicorn worker
  (one FinBERT copy) fixed out-of-memory restarts.
- Yahoo/`yfinance` rate-limiting from cloud IPs — mitigated with caching,
  per-call timeouts, and background pre-computation of heavy scans.
- CORS configuration between the Vercel frontend and Render backend.

---
*This architecture — a static SPA frontend on a CDN, talking to a computation
backend over a REST API — is a standard production pattern: it separates
presentation from computation so each can scale and be maintained independently.*
