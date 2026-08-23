import axios from 'axios'
import { supabase } from './supabaseClient'

// In local dev, calls go to '/api' (Vite proxies to localhost:8000).
// In production, set VITE_API_URL to your deployed backend URL (e.g. Render/Railway).
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 60000,
})

// Attach the Supabase JWT so the backend can scope data (watchlist, portfolio,
// simulations, alerts) to the signed-in user. Anonymous users send no token and
// fall back to the shared 'public' account on the backend.
// A stable per-browser id, used only so the rate limiter can tell two anonymous
// visitors apart. Without it everyone on one school or office network shares a
// single budget and the last few people to open the app get a 429 — which is
// precisely what a classroom demo produces. It is random, carries nothing about
// the person, and is never used to identify anyone: the server treats it as a
// hint for fairness, with a per-network ceiling behind it that no header can lift.
const CLIENT_ID_KEY = 'app.clientId'
function clientId() {
  try {
    let id = localStorage.getItem(CLIENT_ID_KEY)
    if (!id) {
      id = (crypto.randomUUID?.() ||
            Math.random().toString(36).slice(2) + Date.now().toString(36))
      localStorage.setItem(CLIENT_ID_KEY, id)
    }
    return id
  } catch {
    return null      // private mode with storage disabled — fall back to IP
  }
}

api.interceptors.request.use(async config => {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (token) config.headers.Authorization = `Bearer ${token}`
  const cid = clientId()
  if (cid) config.headers['X-Client-Id'] = cid
  return config
})

api.interceptors.response.use(
  r => r.data,
  e => {
    // FastAPI returns `detail` as a STRING for HTTPException but as a LIST of
    // error objects for 422 validation failures. Passing that list straight
    // through meant the UI rendered "[object Object]" instead of a message.
    const d = e?.response?.data?.detail
    if (typeof d === 'string') return Promise.reject(d)
    if (Array.isArray(d)) {
      return Promise.reject(
        d.map(x => x?.msg ? `${(x.loc || []).slice(-1)[0] ?? ''}: ${x.msg}` : JSON.stringify(x))
         .join('; ') || 'Invalid request')
    }
    if (d) return Promise.reject(typeof d === 'object' ? JSON.stringify(d) : String(d))
    return Promise.reject(e?.message || 'API error')
  }
)

// Stock
export const getPrice       = ticker => api.get(`/stock/price?ticker=${ticker}`)
export const getMetrics     = ticker => api.get(`/stock/metrics?ticker=${ticker}`)
export const getStockNews   = (ticker, days=7) => api.get(`/stock/news?ticker=${ticker}&days_back=${days}`)
export const getIntraday    = (ticker, interval='5m', period='1d') => api.get(`/stock/intraday?ticker=${ticker}&interval=${interval}&period=${period}`)
export const getVolForecast = ticker => api.get(`/stock/volatility-forecast?ticker=${ticker}`)
export const getSentiment   = ticker => api.get(`/stock/sentiment?ticker=${ticker}`)
export const searchStocks   = (q, exchange='NSE') => api.get(`/stock/search?q=${q}&exchange=${exchange}`)

// Commodities
export const getMCX         = () => api.get('/commodities/mcx')
export const getAllCommodities = () => api.get('/commodities')
export const getCommodity   = key => api.get(`/commodities/${key}`)
export const getCommodityHistory = (key, period='3mo') => api.get(`/commodities/${key}/history?period=${period}`)

// News
export const getMacroNews   = () => api.get('/news/macro')
export const getMarketNews  = () => api.get('/news/market')

// Watchlist
export const getWatchlist   = () => api.get('/watchlist')
export const addToWatchlist = body => api.post('/watchlist/add', body)
export const removeFromWatchlist = ticker => api.delete(`/watchlist/remove?ticker=${ticker}`)

// Simulator - realtime
export const startSimulation   = body => api.post('/simulator/realtime/start', body)
// Simulation names are user-typed and go in the URL PATH, so they must be
// encoded. A name like "Example " (trailing space) or one containing a slash
// or '#' silently reached the backend altered, so delete/history/add/remove
// all looked up a name that did not exist and appeared to do nothing.
export const getSimulationPnl  = name => api.get(`/simulator/realtime/${encodeURIComponent(name)}`)
export const getSimulations    = () => api.get('/simulator/realtime')
export const deleteSimulation  = name => api.delete(`/simulator/realtime/${encodeURIComponent(name)}`)
export const getSimHistory     = name => api.get(`/simulator/realtime/${encodeURIComponent(name)}/history`)
export const addSimPosition    = (name, ticker, amount) => api.post(`/simulator/realtime/${encodeURIComponent(name)}/add`, { ticker, amount })
export const removeSimPosition = (name, ticker) => api.post(`/simulator/realtime/${encodeURIComponent(name)}/remove`, { ticker })

// Simulator - historic
export const runBacktest    = body => api.post('/simulator/historic', body)
export const compareScenarios = body => api.post('/simulator/compare', body)
export const getChallenges  = () => api.get('/simulator/challenges')

// Alpha model
export const getAlphaScore  = ticker => api.get(`/alpha/score?ticker=${ticker}`)
export const scanAlpha      = body => api.post('/alpha/scan', body)
export const getTopPicks    = () => api.get('/alpha/top-picks', { timeout: 150000 })
// Full-universe scan (all 2,401 NSE names), split by SEBI cap tier
// Guided flow: five answers -> a portfolio plus a downside verdict
// Fire-and-forget product analytics. Never awaited and never surfaced: a
// failed metric must not interrupt, slow, or error the action being measured.
export const getEmailPref  = () => api.get('/me/email-pref')
export const optInEmail    = () => api.post('/me/email-pref')
export const optOutEmail   = () => api.delete('/me/email-pref')

export const createShare = sim_name => api.post('/share/create', { sim_name })
export const revokeShare = sim_name => api.post('/share/revoke', { sim_name })
export const getShared   = token => api.get(`/share/${encodeURIComponent(token)}`)

export const trackEvent = (event, props = {}) => {
  try { api.post('/events/track', { event, props }).catch(() => {}) } catch { /* ignore */ }
}

export const suggestFix        = body => api.post('/portfolio/suggest-fix', body, { timeout: 180000 })
export const getAlphaV2        = ticker => api.get(`/alpha/v2?ticker=${encodeURIComponent(ticker)}`, { timeout: 120000 })
export const getAnomaly        = t => api.get(`/anomaly/${encodeURIComponent(t)}`)
export const getEvents         = t => api.get(`/events/${encodeURIComponent(t)}`)
export const getPortfolioFit   = body => api.post('/portfolio/fit', body, { timeout: 120000 })
export const getWalkForward    = () => api.get('/validation/walk-forward', { timeout: 240000 })
export const getRegimeWeights  = () => api.get('/regime/weights')
export const getFactorChange     = (t, days=30) => api.get(`/factors/change?ticker=${encodeURIComponent(t)}&days=${days}`)
export const getFactorDivergence = (t, days=30) => api.get(`/factors/divergence?ticker=${encodeURIComponent(t)}&days=${days}`)
export const getFactorCoverage   = () => api.get('/factors/coverage')
export const shockPortfolio  = body => api.post('/portfolio/shock', body, { timeout: 180000 })
export const shockPresets    = body => api.post('/portfolio/shock/presets', body, { timeout: 60000 })
export const compareStrategies = body => api.post('/strategy/compare', body, { timeout: 240000 })
export const getMethodology    = tool => api.get(`/methodology/${tool}`)
export const getBenchmark      = (days = 365) => api.get('/benchmark', { params: { days } })
export const advisePortfolio   = body => api.post('/portfolio/advise', body, { timeout: 120000 })
export const portfolioWhatIf = body => api.post('/portfolio/what-if', body, { timeout: 120000 })
export const portfolioScenarios = body => api.post('/portfolio/scenarios', body, { timeout: 180000 })
export const getLeaderboard     = (n=5) => api.get(`/simulator/leaderboard?n=${n}`)
export const buildPortfolio = body => api.post('/portfolio/build', body, { timeout: 120000 })
export const getUniverseTop  = (n = 10) => api.get(`/alpha/universe/top?n=${n}`)
export const getScanStatus   = () => api.get('/alpha/universe/status')
// This stock's own signal over time — today, yesterday, 5 days ago
export const getSignalHistory = (ticker, limit = 30) =>
  api.get(`/alpha/signal-history?ticker=${encodeURIComponent(ticker)}&limit=${limit}`)
export const getRegimeAlpha = ticker => api.get(`/alpha/regime-adjusted?ticker=${ticker}`)
export const explainAlpha   = ticker => api.get(`/alpha/explain?ticker=${ticker}`)
export const getPredictionTrack = (minDays = 7) => api.get(`/predictions/track?min_days=${minDays}`)

// Optimizer
export const runMVO         = body => api.post('/optimizer/mvo', body)
export const runBL          = body => api.post('/optimizer/black-litterman', body)
export const getFrontier    = body => api.post('/optimizer/frontier', body)
// Runs FinBERT over every ticker before it optimises anything, so it is
// nowhere near the 60s default — it aborted mid-pipeline and surfaced as a
// spinner that never resolved. Every other alpha-backed call already
// carries its own timeout; this one was missed.
export const autoOptimize   = body => api.post('/optimizer/auto', body, { timeout: 240000 })
export const runHRP         = body => api.post('/optimizer/hrp', body)
export const runRiskParity  = body => api.post('/optimizer/risk-parity', body)
export const runMaxDiversification = body => api.post('/optimizer/max-diversification', body)
export const runMinCVaR      = body => api.post('/optimizer/min-cvar', body)
export const runRegimeAdaptive = body => api.post('/optimizer/regime-adaptive', body)

// Regime
export const getRegime      = () => api.get('/regime')

// Monte Carlo
export const runMonteCarlo  = body => api.post('/montecarlo/simulate', body)
export const compareMonteCarlo = body => api.post('/montecarlo/compare', body)

// Options Lab — Black-Scholes
export const runBlackScholes = body => api.post('/options/black-scholes', body)
export const runImpliedVol   = body => api.post('/options/implied-vol', body)
export const optionsAutofill = ticker => api.get(`/options/autofill?ticker=${ticker}`)

// Research — honest momentum backtest
export const getMomentumBacktest = (top=0.2, start='2019-01-01') =>
  api.get(`/research/momentum-backtest?top_fraction=${top}&start=${start}`)

// Risk decomposition (which holding drives portfolio risk)
export const getRiskDecomposition = holdings => api.post('/risk/decomposition', { holdings })

// Research — low-vol factor backtest + seasonality
export const getLowVolBacktest = (bottom=0.2, start='2019-01-01') =>
  api.get(`/research/low-vol-backtest?bottom_fraction=${bottom}&start=${start}`)
export const getSeasonality = (ticker='^NSEI', years=20) =>
  api.get(`/research/seasonality?ticker=${encodeURIComponent(ticker)}&years=${years}`)

// Pairs trading
export const findPairs      = body => api.post('/pairs/find', body)
export const analyzePair    = body => api.post('/pairs/analyze', body)
export const backtestPair   = body => api.post('/pairs/backtest', body)

// Fama-French
export const getFactorRegression = ticker => api.get(`/factors/regression?ticker=${ticker}`)

// Screener
export const runScreener     = body => api.post('/screener', body)
export const getScreenerSectors = () => api.get('/screener/sectors')
export const getScreenerStatus  = () => api.get('/screener/status')

// Portfolio tracker
export const getPortfolio    = () => api.get('/portfolio')
export const addHolding      = body => api.post('/portfolio/add', body)
export const removeHolding   = id => api.delete(`/portfolio/remove?id=${id}`)

// Calculators
export const calcSIP         = body => api.post('/calc/sip', body)
export const calcLumpsum     = body => api.post('/calc/lumpsum', body)
export const calcTax         = body => api.post('/calc/tax', body)

// Risk Lab
export const getDeflatedSharpe = (ticker, nTrials) => api.get(`/risk/deflated-sharpe?ticker=${ticker}&n_trials=${nTrials}`)
export const getPositionSize   = body => api.post('/risk/position-size', body)

// Research
export const getSentimentAlpha  = (ticker, days=120) => api.get(`/research/sentiment-alpha?ticker=${ticker}&days_back=${days}`)
export const getMeanReversion   = ticker => api.get(`/research/mean-reversion?ticker=${ticker}`)
export const runMomentumStudy   = body => api.post('/research/momentum', body)
export const runCorrelation     = body => api.post('/research/correlation', body)

// Alerts
export const sendTestAlert  = () => api.post('/alerts/test')


