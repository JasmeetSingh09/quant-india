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
api.interceptors.request.use(async config => {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  r => r.data,
  e => Promise.reject(e?.response?.data?.detail || e.message || 'API error')
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
export const getSimulationPnl  = name => api.get(`/simulator/realtime/${name}`)
export const getSimulations    = () => api.get('/simulator/realtime')
export const deleteSimulation  = name => api.delete(`/simulator/realtime/${name}`)
export const getSimHistory     = name => api.get(`/simulator/realtime/${name}/history`)
export const addSimPosition    = (name, ticker, amount) => api.post(`/simulator/realtime/${name}/add`, { ticker, amount })
export const removeSimPosition = (name, ticker) => api.post(`/simulator/realtime/${name}/remove`, { ticker })

// Simulator - historic
export const runBacktest    = body => api.post('/simulator/historic', body)
export const compareScenarios = body => api.post('/simulator/compare', body)
export const getChallenges  = () => api.get('/simulator/challenges')

// Alpha model
export const getAlphaScore  = ticker => api.get(`/alpha/score?ticker=${ticker}`)
export const scanAlpha      = body => api.post('/alpha/scan', body)
export const getTopPicks    = () => api.get('/alpha/top-picks', { timeout: 150000 })
export const getRegimeAlpha = ticker => api.get(`/alpha/regime-adjusted?ticker=${ticker}`)
export const explainAlpha   = ticker => api.get(`/alpha/explain?ticker=${ticker}`)
export const getPredictionTrack = (minDays = 7) => api.get(`/predictions/track?min_days=${minDays}`)

// Optimizer
export const runMVO         = body => api.post('/optimizer/mvo', body)
export const runBL          = body => api.post('/optimizer/black-litterman', body)
export const getFrontier    = body => api.post('/optimizer/frontier', body)
export const autoOptimize   = body => api.post('/optimizer/auto', body)
export const runHRP         = body => api.post('/optimizer/hrp', body)

// Regime
export const getRegime      = () => api.get('/regime')

// Monte Carlo
export const runMonteCarlo  = body => api.post('/montecarlo/simulate', body)
export const compareMonteCarlo = body => api.post('/montecarlo/compare', body)

// Options Lab — Black-Scholes
export const runBlackScholes = body => api.post('/options/black-scholes', body)
export const runImpliedVol   = body => api.post('/options/implied-vol', body)
export const optionsAutofill = ticker => api.get(`/options/autofill?ticker=${ticker}`)

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


