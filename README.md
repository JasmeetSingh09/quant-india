# Quant India

A full-stack NSE stock intelligence platform. Combines live market data, quantitative alpha scoring, news sentiment analysis, and portfolio tools in a single dark-mode dashboard.

**Validation:** the quantitative models are covered by **~168,000 property/edge-case
assertions** (currently passing) — put-call parity, optimiser weight constraints,
Black-Litterman view responsiveness, HRP clustering behaviour, Monte Carlo
percentile ordering, and more. The suites are deterministic and offline:

```bash
cd backend
python tests/test_core_properties.py         # ~81,000 assertions
python tests/test_new_algorithms_stress.py   # ~87,000 assertions
python tests/test_modules_integration.py     # import-safety + integration
```

See **[VALIDATION.md](VALIDATION.md)** for each model's formulation, how it was
validated, its assumptions, and its known limitations — and
**[RESEARCH_momentum.md](RESEARCH_momentum.md)** for an honest backtest write-up
(where correcting a look-ahead flaw erased half the measured edge).

---

## Features

| Section | What it does |
|---|---|
| **Dashboard** | Live Nifty 50 prices, MCX commodities, market news, top picks (alpha model), regime analysis, and prediction track record |
| **Stocks** | Screener table across the NSE universe with P/E / ROE / market cap / sector filters — click any row for full analysis |
| **Stock Detail** | Company intro, 52-week range, intraday chart, full valuation & balance sheet metrics, 4-factor alpha score with AI explanation, GARCH volatility forecast, news sentiment |
| **My Stocks** | Personal watchlist with live prices and P&L |
| **Simulator** | Paper-trade against real NSE prices (realtime) or replay historical data |
| **Portfolio Lab** | Mean-variance optimisation, Black-Litterman, HRP, efficient frontier |
| **Research** | Sentiment-alpha backtest, mean-reversion, momentum studies, pairs trading |
| **Markets** | MCX commodities, macro news, market regime (3-state Gaussian HMM) |
| **Calculators** | SIP, lumpsum, STCG/LTCG tax |

### Alpha model
Ranks every large liquid NSE stock on four quantitative factors — **momentum**, **quality**, **value**, and **sentiment** — then explains each signal with a Fama-French reality check.

---

## Tech stack

**Backend** — Python 3.11, FastAPI, yfinance, FinBERT (sentiment), GARCH (arch), XGBoost, scipy/statsmodels, APScheduler

**Frontend** — React 18, Vite, Tailwind CSS, Recharts, TanStack Query, React Router v6

---

## Local setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- A free [NewsAPI](https://newsapi.org) key

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/quant-india.git
cd quant-india
```

### 2. Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your NEWS_API_KEY
```

> **GPU note:** `requirements.txt` installs the CPU build of PyTorch. If you have an NVIDIA GPU, replace the `torch` line with:
> ```
> pip install torch --index-url https://download.pytorch.org/whl/cu124
> ```

```bash
uvicorn main:app --reload --port 8000
```

Backend is live at `http://localhost:8000`. First startup downloads FinBERT (~420 MB).

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend is live at `http://localhost:5173`. The Vite dev server proxies `/api` to `localhost:8000` automatically.

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `NEWS_API_KEY` | Yes | [newsapi.org](https://newsapi.org) free key |
| `GMAIL_ADDRESS` | No | Gmail address for price/signal alerts |
| `GMAIL_APP_PASSWORD` | No | Gmail app password (not your main password) |
| `GMAIL_RECEIVER` | No | Email address to receive alerts |
| `FRONTEND_URL` | No | Set in production for CORS (your Vercel URL) |

---

## Deployment

Full step-by-step in [DEPLOY.md](DEPLOY.md).

**Quick summary:**
- Backend → [Render](https://render.com) (Docker, Standard plan — 2 GB RAM needed for FinBERT)
- Frontend → [Vercel](https://vercel.com) (free, auto-detects Vite)

```bash
# After any change
git add -A
git commit -m "your message"
git push
# Render and Vercel redeploy automatically
```

---

## Project structure

```
quant-india/
├── backend/
│   ├── main.py              # FastAPI app, all route definitions
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .env.example
│   └── modules/
│       ├── alpha_model.py       # 4-factor alpha scoring + XGBoost
│       ├── metrics.py           # Valuation, Piotroski, DuPont, health score
│       ├── sentiment.py         # FinBERT news sentiment
│       ├── regime_detector.py   # Gaussian HMM market regime
│       ├── garch_vol.py         # GARCH volatility forecasting
│       ├── screener.py          # NSE universe screener
│       ├── portfolio_optimizer.py  # MVO, Black-Litterman, HRP
│       ├── simulator.py         # Paper trading engine
│       ├── news.py / rss_news.py   # NewsAPI + RSS feed aggregation
│       └── ...
└── frontend/
    ├── src/
    │   ├── App.jsx              # Routes
    │   ├── api.js               # All Axios calls
    │   ├── pages/
    │   │   ├── Dashboard.jsx
    │   │   ├── StockExplorer.jsx   # Stocks list + detail (combined)
    │   │   ├── MyStocks.jsx
    │   │   ├── Simulator.jsx
    │   │   ├── PortfolioLab.jsx
    │   │   ├── QuantResearch.jsx
    │   │   ├── Markets.jsx
    │   │   └── Calculators.jsx
    │   └── components/
    │       ├── Sidebar.jsx
    │       ├── AlphaMeter.jsx
    │       ├── StatCard.jsx
    │       └── ...
    └── vite.config.js
```

---

## Known limitations

- **Ephemeral storage on Render** — watchlist and saved simulations reset on redeploy. Add a persistent disk to fix.
- **NSE stock-list download** may be blocked from some cloud IPs; a built-in fallback covers the major stocks.
- **~30-60 s cold start** after the backend idles (FinBERT reload). Top Picks specifically warns about this.
- Data is sourced from yfinance (delayed ~15 min during market hours) and NewsAPI. Not for live trading.

---

## Disclaimer

This project is for educational and research purposes only. Nothing here constitutes financial advice. Past model performance does not predict future returns.
