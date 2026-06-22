# Deployment Guide — Quant India

Deploys as two parts:
- **Backend** (FastAPI + FinBERT) → Render (needs ~2 GB RAM → Standard plan, ~$25/mo)
- **Frontend** (React) → Vercel (free)

The code is already committed to git and all config files are ready
(`Dockerfile`, `render.yaml`, `vercel.json`, `.env.example`). Your real `.env`
is gitignored and will NOT be uploaded.

---

## Step 1 — Push to GitHub (5 min)

1. Create a free account at https://github.com
2. Create a new **empty** repository (e.g. `quant-india`). Do NOT add a README.
3. In your terminal, from the project folder, run (replace YOUR_USERNAME):

```bash
git remote add origin https://github.com/YOUR_USERNAME/quant-india.git
git branch -M main
git push -u origin main
```

(GitHub will ask you to log in / paste a personal access token the first time.)

---

## Step 2 — Deploy the Backend on Render (10 min)

1. Sign up at https://render.com (connect your GitHub).
2. **New + → Web Service →** pick your `quant-india` repo.
3. Render auto-detects `render.yaml`. Confirm:
   - Root directory: `backend`
   - Runtime: Docker
   - Plan: **Standard (2 GB)** — required for FinBERT. The free/starter plans
     (512 MB) will crash on model load.
4. Add your secrets under **Environment** (these are NOT in the repo):
   - `NEWS_API_KEY` = your NewsAPI key
   - `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `GMAIL_RECEIVER` (optional, for alerts)
   - `FRONTEND_URL` = leave blank for now; fill in after Step 3
5. Click **Create**. First build takes ~10 min (it downloads FinBERT).
6. When live, copy the URL, e.g. `https://quant-india-backend.onrender.com`.
   Test it: open `<that URL>/` — you should see the JSON status message.

---

## Step 3 — Deploy the Frontend on Vercel (5 min)

1. Sign up at https://vercel.com (connect GitHub).
2. **Add New → Project →** pick your `quant-india` repo.
3. Set **Root Directory** to `frontend`.
4. Under **Environment Variables**, add:
   - `VITE_API_URL` = your Render backend URL from Step 2
     (e.g. `https://quant-india-backend.onrender.com`)
5. Click **Deploy**. ~2 min. You get a public URL like
   `https://quant-india.vercel.app` — **this is your shareable link.**

---

## Step 4 — Connect them (CORS) (2 min)

1. Go back to Render → your backend → Environment.
2. Set `FRONTEND_URL` = your Vercel URL (e.g. `https://quant-india.vercel.app`).
3. Save — Render redeploys automatically.

Done. Your site is live at the Vercel URL, talking to the Render backend.

---

## Known limitations (fine for a demo)

- **Database resets on redeploy.** Render's free disk is ephemeral, so the
  watchlist / saved simulations reset when the backend redeploys. News and
  market data are unaffected (they re-fetch). To make it permanent, add a
  Render persistent disk later.
- **First request after idle is slow.** If the backend sleeps, the first hit
  takes ~30-60 s to wake + reload FinBERT.
- **NSE stock-list download** may be blocked from cloud IPs; a built-in
  fallback list covers the major stocks.

---

## Updating the live site later

Any time you change code:
```bash
git add -A
git commit -m "your change"
git push
```
Render and Vercel both auto-redeploy on push. No manual steps.
