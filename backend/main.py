"""
main.py — FastAPI application for the Indian Stock Investor Intelligence Platform.

Endpoints:
  GET  /stock/price              — current price + change
  GET  /stock/metrics            — full financial metrics + health score
  GET  /stock/news               — company-specific news
  GET  /stock/sentiment          — FinBERT sentiment over recent news
  POST /watchlist/add            — add ticker to watchlist
  GET  /watchlist                — get full watchlist with live prices
  DELETE /watchlist/remove       — remove ticker from watchlist
  POST /simulator/backtest       — backtest a portfolio
  GET  /simulator/challenges     — list weekly challenges
  POST /simulator/challenge/submit — submit a challenge answer
  POST /alerts/test              — send a test Gmail alert
  GET  /news/macro               — macro news with causal chain
  GET  /news/market              — market-wide news

Run with: uvicorn main:app --reload --port 8000
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv(Path(__file__).parent / ".env")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Ensure modules directory is on the path
sys.path.insert(0, str(Path(__file__).parent / "modules"))

from data_fetcher import get_current_price, get_company_info, search_stock, get_all_nse_tickers, get_intraday_data
from stock_universe import (
    search_stocks, get_stock_by_symbol, get_all_symbols,
    get_universe_stats, ensure_universe_loaded, refresh_nse_stocks, refresh_bse_stocks,
)
from commodities import (
    get_commodity_price, get_all_commodities, get_commodity_history,
    get_commodities_by_category, get_mcx_summary, COMMODITIES,
)
from news import get_stock_news, get_macro_news, get_market_wide_news, start_news_scheduler
from sentiment import score_headline, summarise_sentiment
from watchlist import add_to_watchlist, remove_from_watchlist, get_watchlist
from alerts import send_test_alert, send_multi_signal_alert, start_alert_scheduler, run_watchlist_alert_check
from alpha_model import compute_alpha_score, scan_alpha, retrain_weights, explain_signal
from portfolio_optimizer import (
    mean_variance_optimize, black_litterman_optimize,
    efficient_frontier, optimize_with_alpha_views,
    hierarchical_risk_parity,
)
from regime_detector import detect_regime, regime_conditioned_alpha
from monte_carlo import simulate as mc_simulate, compare_methods as mc_compare
from garch_vol import forecast_vol as garch_forecast, test_vs_naive as garch_test
from screener import screen as run_screen, get_sectors, get_screener_status, ensure_screener_cache, build_screener_cache
from portfolio_tracker import add_holding, remove_holding, get_portfolio
from calculators import sip_calculator, lumpsum_calculator, capital_gains_tax
from pairs_trading import find_cointegrated_pairs, analyze_pair, backtest_pair
from fama_french import factor_regression, build_factors
from research import (
    sentiment_alpha_study, momentum_study, mean_reversion_study,
    correlation_study, macro_sector_signal_study, full_research_report,
)
from metrics import get_full_metrics, peer_comparison, dupont_analysis, financial_health_score
from simulator import (
    backtest, compare_scenarios,
    start_simulation, get_simulation_pnl, get_simulation_history,
    list_simulations, delete_simulation,
    get_challenges, submit_challenge,
    save_portfolio, load_portfolio, list_portfolios,
)

app = FastAPI(
    title="Indian Stock Investor Intelligence Platform",
    description="AI-powered NSE stock analysis with news, sentiment, alerts, and backtesting.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    """On startup: load full NSE+BSE universe and start news refresh scheduler."""
    import asyncio
    # Load stock universe in background so startup is not blocked
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, ensure_universe_loaded)
    loop.run_in_executor(None, ensure_screener_cache)   # build screener cache if empty
    start_news_scheduler()
    start_alert_scheduler(interval_minutes=30)   # auto-check watchlists for alerts


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class WatchlistAddRequest(BaseModel):
    ticker: str
    price_alert_pct: float = 5.0
    sentiment_alert: bool = True


class SimulationStartRequest(BaseModel):
    name: str
    holdings: dict
    initial_value: float = 100_000

class BacktestRequest(BaseModel):
    holdings: dict
    start_date: str
    end_date:   str = None
    initial_value: float = 100_000

class CompareRequest(BaseModel):
    scenarios: list          # [{name, holdings}, ...]
    start_date: str
    end_date:   str = None
    initial_value: float = 100_000


class PortfolioSaveRequest(BaseModel):
    name: str
    holdings: dict


class ChallengeSubmitRequest(BaseModel):
    challenge_id: str
    user_pick:    dict


class MomentumStudyRequest(BaseModel):
    tickers: list
    lookback_months: int = 6
    holding_months:  int = 1
    start_year:      int = 2019

class CorrelationStudyRequest(BaseModel):
    tickers: list
    start_date: str = None
    end_date:   str = None
    period_months: int = 12

class ScanRequest(BaseModel):
    tickers: list
    weights: dict = None

class MVORequest(BaseModel):
    tickers: list
    period_months: int = 24
    target: str = "max_sharpe"
    min_weight: float = 0.0
    max_weight: float = 1.0

class BLRequest(BaseModel):
    tickers: list
    sentiment_views: dict   # {ticker: [expected_excess, confidence]}
    period_months: int = 24
    tau: float = 0.05

class FrontierRequest(BaseModel):
    tickers: list
    period_months: int = 24
    n_points: int = 50

class AlphaViewsRequest(BaseModel):
    tickers: list
    period_months: int = 24

class PairsFindRequest(BaseModel):
    tickers: list
    period_months: int = 24

class PairAnalyzeRequest(BaseModel):
    stock_a: str
    stock_b: str
    period_months: int = 12
    entry_z: float = 2.0
    exit_z:  float = 0.5

class PairBacktestRequest(BaseModel):
    stock_a: str
    stock_b: str
    period_months: int = 36
    entry_z: float = 2.0
    exit_z:  float = 0.5

class MonteCarloRequest(BaseModel):
    holdings: dict
    initial_value: float = 100_000
    horizon_days:  int = 252
    n_simulations: int = 10_000
    method: str = "bootstrap"

class MacroSignalRequest(BaseModel):
    macro_keyword: str
    sector_ticker: str
    days_back:     int = 365
    forward_days:  int = 5

class MultiSignalAlertRequest(BaseModel):
    ticker: str
    company_name: str
    price_change_pct: float
    current_price: float
    sentiment_label: str
    confidence_pct: float
    headline: str


# ---------------------------------------------------------------------------
# Stock endpoints
# ---------------------------------------------------------------------------

@app.get("/stock/price")
def stock_price(ticker: str = Query(..., description="NSE ticker e.g. RELIANCE.NS")):
    """Get current price, daily change, and volume for an NSE stock."""
    result = get_current_price(ticker)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/stock/intraday")
def stock_intraday(
    ticker: str = Query(..., description="NSE ticker e.g. RELIANCE.NS"),
    interval: str = Query("5m", description="1m | 5m | 15m"),
    period: str = Query("1d", description="1d | 5d | 1mo"),
):
    """
    Intraday price bars for a moving chart. Falls back to daily candles
    if intraday data isn't available (market closed / rate limited).
    Poll this every ~30s on the frontend to make the chart update live.
    """
    result = get_intraday_data(ticker, interval=interval, period=period)
    if "error" in result and not result.get("candles"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/stock/volatility-forecast")
def stock_volatility_forecast(
    ticker: str = Query(..., description="NSE ticker e.g. RELIANCE.NS"),
    horizon: int = Query(5, description="Days to forecast"),
):
    """
    GARCH(1,1) volatility forecast — predicts upcoming risk by modelling
    volatility clustering. Beats naive trailing-std forecasts (validated OOS).
    """
    result = garch_forecast(ticker, horizon=horizon)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/stock/metrics")
def stock_metrics(ticker: str = Query(..., description="NSE ticker e.g. RELIANCE.NS")):
    """
    Full financial metrics including P/E, EV/EBITDA, ROE, DuPont analysis,
    Piotroski F-Score, and a 0-100 health score.
    """
    metrics  = get_full_metrics(ticker)
    health   = financial_health_score(ticker)
    dupont   = dupont_analysis(ticker)
    peers    = peer_comparison(ticker)
    return {
        "metrics":   metrics,
        "health":    health,
        "dupont":    dupont,
        "peers":     peers,
    }


@app.get("/stock/news")
def stock_news(
    ticker: str = Query(..., description="NSE ticker e.g. RELIANCE.NS"),
    days_back: int = Query(7, description="How many days of news to fetch"),
):
    """Fetch company-specific news headlines for an NSE ticker."""
    articles = get_stock_news(ticker, days_back=days_back)
    return {"ticker": ticker, "articles": articles, "count": len(articles)}


@app.get("/stock/sentiment")
def stock_sentiment(
    ticker: str = Query(..., description="NSE ticker e.g. RELIANCE.NS"),
    days_back: int = Query(7, description="How many days of news to score"),
):
    """
    Fetch company news and run FinBERT sentiment scoring.
    Returns per-article scores and an overall sentiment summary with trend.
    """
    articles = get_stock_news(ticker, days_back=days_back)
    if not articles:
        return {"ticker": ticker, "error": "No news found", "articles": []}
    summary  = summarise_sentiment(articles)
    return {"ticker": ticker, "summary": summary}


# ---------------------------------------------------------------------------
# Watchlist endpoints
# ---------------------------------------------------------------------------

@app.post("/watchlist/add")
def watchlist_add(req: WatchlistAddRequest):
    """Add an NSE ticker to the watchlist with price and sentiment alert settings."""
    result = add_to_watchlist(
        ticker=req.ticker,
        price_alert_pct=req.price_alert_pct,
        sentiment_alert=req.sentiment_alert,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/watchlist")
def watchlist_get(refresh: bool = Query(True, description="Refresh live prices")):
    """Return all watchlist entries with current prices and alert status."""
    return {"watchlist": get_watchlist(refresh_prices=refresh)}


@app.delete("/watchlist/remove")
def watchlist_remove(ticker: str = Query(..., description="NSE ticker to remove")):
    """Remove a ticker from the watchlist."""
    result = remove_from_watchlist(ticker)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Simulator — Real-time (paper trading)
# ---------------------------------------------------------------------------

@app.post("/simulator/realtime/start")
def sim_start(req: SimulationStartRequest):
    """
    Start a real-time paper trading simulation.

    Records today's live entry prices for each stock.
    Call GET /simulator/realtime/{name} anytime to see live P&L.

    Body example:
      {"name": "my_hdfc_bet", "holdings": {"HDFCBANK.NS": 60, "TCS.NS": 40}, "initial_value": 100000}
    """
    result = start_simulation(req.name, req.holdings, req.initial_value)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/simulator/realtime/{name}")
def sim_pnl(name: str):
    """
    Fetch live P&L for a running simulation.

    Returns per-stock: entry price, current price, ₹ gain/loss, % gain/loss.
    Also returns overall portfolio value and total P&L.
    """
    result = get_simulation_pnl(name)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/simulator/realtime/{name}/history")
def sim_history(name: str):
    """
    P&L snapshot history for a simulation — use to draw a portfolio value chart.
    A new snapshot is saved every time you call the /pnl endpoint.
    """
    result = get_simulation_history(name)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/simulator/realtime")
def sim_list():
    """List all active real-time simulations."""
    return {"simulations": list_simulations()}


@app.delete("/simulator/realtime/{name}")
def sim_delete(name: str):
    """Delete a real-time simulation and all its data."""
    result = delete_simulation(name)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Simulator — Historic backtest
# ---------------------------------------------------------------------------

@app.post("/simulator/historic")
def sim_historic(req: BacktestRequest):
    """
    Backtest a portfolio over a historical date range.

    start_date is required (e.g. "2019-01-01").
    Returns CAGR, Sharpe, max drawdown, monthly return heatmap,
    day-by-day chart data, and Nifty 50 comparison.

    Body example:
      {
        "holdings": {"HDFCBANK.NS": 100},
        "start_date": "2019-01-01",
        "end_date": "2022-12-31",
        "initial_value": 100000
      }
    """
    result = backtest(req.holdings, req.start_date, req.end_date, req.initial_value)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/simulator/compare")
def sim_compare(req: CompareRequest):
    """
    Compare multiple portfolio scenarios on the same historical period.

    Body example:
      {
        "scenarios": [
          {"name": "HDFC only", "holdings": {"HDFCBANK.NS": 100}},
          {"name": "IT mix",    "holdings": {"TCS.NS": 60, "INFY.NS": 40}}
        ],
        "start_date": "2019-01-01",
        "end_date": "2022-12-31"
      }
    """
    result = compare_scenarios(req.scenarios, req.start_date, req.end_date, req.initial_value)
    return result


# ---------------------------------------------------------------------------
# Simulator — Saved portfolios & challenges
# ---------------------------------------------------------------------------

@app.post("/simulator/portfolio/save")
def simulator_portfolio_save(req: PortfolioSaveRequest):
    """Save a named portfolio for future backtesting."""
    result = save_portfolio(req.name, req.holdings)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/simulator/portfolio/{name}")
def simulator_portfolio_load(name: str):
    """Load a previously saved portfolio."""
    result = load_portfolio(name)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/simulator/portfolios")
def simulator_portfolios():
    """List all saved portfolios."""
    return {"portfolios": list_portfolios()}


@app.get("/simulator/challenges")
def simulator_challenges():
    """Return the 5 active weekly learning challenges."""
    return {"challenges": get_challenges()}


@app.post("/simulator/challenge/submit")
def simulator_challenge_submit(req: ChallengeSubmitRequest):
    """Submit an answer to a weekly challenge."""
    result = submit_challenge(req.challenge_id, req.user_pick)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# News endpoints
# ---------------------------------------------------------------------------

@app.get("/news/macro")
def news_macro(days_back: int = Query(3, description="Days of news to fetch")):
    """
    Fetch macro news (RBI, crude, rupee, FII, inflation) with causal chain
    impact mapped to NSE sectors and stocks.
    """
    articles = get_macro_news(days_back=days_back)
    return {"articles": articles, "count": len(articles)}


@app.get("/news/market")
def news_market(days_back: int = Query(3, description="Days of news to fetch")):
    """Fetch broad Indian market news: Nifty moves, FII/DII, SEBI decisions."""
    articles = get_market_wide_news(days_back=days_back)
    return {"articles": articles, "count": len(articles)}


# ---------------------------------------------------------------------------
# Alert endpoints
# ---------------------------------------------------------------------------

@app.post("/alerts/test")
def alerts_test():
    """Send a test Gmail alert to verify credentials are configured correctly."""
    result = send_test_alert()
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.post("/alerts/run-check")
def alerts_run_check():
    """
    Manually trigger the watchlist alert check right now (same logic the
    background scheduler runs every 30 min). Returns what was sent or skipped.
    """
    return {"results": run_watchlist_alert_check()}


@app.post("/alerts/send")
def alerts_send(req: MultiSignalAlertRequest):
    """Manually trigger a multi-signal alert email for a stock."""
    result = send_multi_signal_alert(
        ticker=req.ticker,
        company_name=req.company_name,
        price_change_pct=req.price_change_pct,
        current_price=req.current_price,
        sentiment_label=req.sentiment_label,
        confidence_pct=req.confidence_pct,
        headline=req.headline,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Portfolio Tracker (real holdings)
# ---------------------------------------------------------------------------

class HoldingRequest(BaseModel):
    ticker: str
    quantity: float
    buy_price: float

@app.post("/portfolio/add")
def portfolio_add(req: HoldingRequest):
    """Add a real holding (ticker, quantity, buy price)."""
    result = add_holding(req.ticker, req.quantity, req.buy_price)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.get("/portfolio")
def portfolio_get(refresh: bool = Query(True)):
    """Get all holdings with live P&L, allocation, best/worst."""
    return get_portfolio(refresh=refresh)

@app.delete("/portfolio/remove")
def portfolio_remove(id: int = Query(..., description="Holding id to remove")):
    """Remove a holding by id."""
    result = remove_holding(id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Calculators (SIP / lumpsum / capital-gains tax)
# ---------------------------------------------------------------------------

class SIPRequest(BaseModel):
    monthly_investment: float
    annual_return_pct: float = 12.0
    years: float = 10

class LumpsumRequest(BaseModel):
    principal: float
    annual_return_pct: float = 12.0
    years: float = 10

class TaxRequest(BaseModel):
    buy_price: float
    sell_price: float
    quantity: float
    holding_months: float

@app.post("/calc/sip")
def calc_sip(req: SIPRequest):
    """SIP future-value calculator."""
    r = sip_calculator(req.monthly_investment, req.annual_return_pct, req.years)
    if "error" in r:
        raise HTTPException(status_code=400, detail=r["error"])
    return r

@app.post("/calc/lumpsum")
def calc_lumpsum(req: LumpsumRequest):
    """Lumpsum future-value calculator."""
    r = lumpsum_calculator(req.principal, req.annual_return_pct, req.years)
    if "error" in r:
        raise HTTPException(status_code=400, detail=r["error"])
    return r

@app.post("/calc/tax")
def calc_tax(req: TaxRequest):
    """Indian equity capital-gains tax (STCG/LTCG, post-2024 rules)."""
    r = capital_gains_tax(req.buy_price, req.sell_price, req.quantity, req.holding_months)
    if "error" in r:
        raise HTTPException(status_code=400, detail=r["error"])
    return r


# ---------------------------------------------------------------------------
# Screener
# ---------------------------------------------------------------------------

class ScreenRequest(BaseModel):
    filters: dict = {}
    sort_by: str = "market_cap"
    descending: bool = True
    limit: int = 50

@app.post("/screener")
def screener(req: ScreenRequest):
    """
    Filter the NSE universe by fundamentals.
    filters: {"pe_max":20,"roe_min":15,"market_cap_min":1e11,"sector":"IT"}
    """
    return run_screen(req.filters, req.sort_by, req.descending, req.limit)

@app.get("/screener/sectors")
def screener_sectors():
    """List sectors available for the screener filter."""
    return {"sectors": get_sectors()}

@app.get("/screener/status")
def screener_status():
    """How many stocks are cached + when last refreshed."""
    return get_screener_status()

@app.post("/screener/refresh")
def screener_refresh():
    """Force-rebuild the screener metrics cache (slow, ~5-10 min)."""
    return build_screener_cache()


# ---------------------------------------------------------------------------
# Stock search & universe
# ---------------------------------------------------------------------------

@app.get("/stock/search")
def stock_search(
    q: str = Query(..., description="Company name or partial ticker e.g. 'reliance', 'hdfc'"),
    exchange: str = Query("NSE", description="NSE | BSE | ALL"),
    limit: int = Query(20, description="Max results"),
):
    """
    Search all NSE + BSE listed stocks by name or symbol.
    Returns company name, exchange, and yfinance ticker ready to use.
    """
    results = search_stocks(q, exchange=exchange, limit=limit)
    return {"query": q, "exchange": exchange, "results": results, "count": len(results)}


@app.get("/stock/universe/stats")
def stock_universe_stats():
    """How many stocks are cached per exchange and when they were last refreshed."""
    return get_universe_stats()


@app.get("/stock/universe/{exchange}")
def stock_universe_list(
    exchange: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, le=500),
):
    """
    Paginated list of all cached stocks for an exchange.

    exchange: NSE or BSE
    page: page number (starts at 1)
    page_size: results per page (max 500)
    """
    all_syms = get_all_symbols(exchange.upper())
    start    = (page - 1) * page_size
    end      = start + page_size
    return {
        "exchange":   exchange.upper(),
        "total":      len(all_syms),
        "page":       page,
        "page_size":  page_size,
        "stocks":     all_syms[start:end],
    }


@app.post("/stock/universe/refresh")
def stock_universe_refresh(exchange: str = Query("NSE", description="NSE | BSE | ALL")):
    """Force-refresh the stock universe from NSE/BSE. Normally auto-refreshed daily."""
    results = {}
    if exchange.upper() in ("NSE", "ALL"):
        results["nse"] = refresh_nse_stocks(force=True)
    if exchange.upper() in ("BSE", "ALL"):
        results["bse"] = refresh_bse_stocks(force=True)
    return results


# ---------------------------------------------------------------------------
# Commodities
# ---------------------------------------------------------------------------

@app.get("/commodities")
def commodities_all():
    """
    Live prices for all commodities (gold, silver, crude, gas, metals, agri)
    grouped by category, with USD/INR rate and INR equivalent prices.
    """
    return get_all_commodities()


@app.get("/commodities/mcx")
def commodities_mcx():
    """Dashboard-style MCX summary: gold, silver, crude WTI, Brent, gas, copper, aluminium."""
    return get_mcx_summary()


@app.get("/commodities/{commodity_key}")
def commodity_single(commodity_key: str):
    """
    Get current price for a single commodity.

    commodity_key: gold | silver | crude_wti | crude_brent | natural_gas |
                   copper | aluminium | platinum | palladium | wheat | soybean |
                   cotton | gold_etf_india | silver_etf_india | oil_etf_india
    """
    result = get_commodity_price(commodity_key)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/commodities/{commodity_key}/history")
def commodity_history(
    commodity_key: str,
    period: str = Query("1mo", description="1d | 5d | 1mo | 3mo | 6mo | 1y | 2y | 5y"),
):
    """Historical OHLCV data for a commodity."""
    result = get_commodity_history(commodity_key, period=period)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/commodities/category/{category}")
def commodity_category(category: str):
    """
    Prices for all commodities in a category.

    category: precious_metals | energy | base_metals | agricultural | india_etf
    """
    return get_commodities_by_category(category)


# ---------------------------------------------------------------------------
# Alpha Model — proprietary four-factor scoring
# ---------------------------------------------------------------------------

@app.get("/alpha/score")
def alpha_score(ticker: str = Query(..., description="NSE ticker e.g. HDFCBANK.NS")):
    """
    Compute the proprietary alpha score for a stock.

    Combines four factors into a single -100 to +100 score:
      Sentiment (25%) — decay-weighted FinBERT on recent headlines
      Momentum  (35%) — cross-sectional rank vs sector peers
      Quality   (25%) — Piotroski F-Score + ROE + FCF yield
      Value     (15%) — P/E and P/B Z-score vs sector

    Returns score, signal (BUY/SELL/NEUTRAL), per-factor breakdown,
    and factor contributions in points.
    """
    result = compute_alpha_score(ticker)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/alpha/explain")
def alpha_explain(
    ticker: str = Query(..., description="NSE ticker e.g. HDFCBANK.NS"),
    factor_check: bool = Query(True, description="Run Fama-French validation (slower)"),
):
    """
    Fully-reasoned recommendation: WHY buy or sell this stock.

    Returns the alpha signal, a plain-English list of reasons (which factors
    drive it), and a Fama-French reality check — is the stock's track record
    genuine alpha, or just exposure to market/size/value factors?

    Slower (~30-60s) because of the factor regression. Set factor_check=false to skip.
    """
    result = explain_signal(ticker, run_factor_check=factor_check)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/alpha/scan")
def alpha_scan(req: ScanRequest):
    """
    Score and rank a list of tickers by alpha score.

    Use to screen a sector — e.g. pass all IT stocks and see which ranks highest.
    Body: {"tickers": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS"]}
    """
    return {"rankings": scan_alpha(req.tickers, weights=req.weights)}


@app.get("/alpha/regime-adjusted")
def alpha_regime_adjusted(ticker: str = Query(...)):
    """
    Regime-conditioned alpha score — the full original algorithm.

    Pipeline: Nifty HMM regime → adjust factor weights → recompute alpha.
    In a bear regime, quality and sentiment weighted more heavily.
    In a bull regime, momentum weighted more heavily.
    Returns both raw and regime-adjusted scores.
    """
    result = regime_conditioned_alpha(ticker)
    return result


@app.post("/alpha/retrain")
def alpha_retrain(
    tickers: list = None,
    start_date: str = Query("2019-01-01"),
    end_date:   str = Query("2022-12-31"),
):
    """
    Refit factor weights using OLS regression on historical NSE data.
    Returns fitted coefficients, R², t-statistics, and suggested new weights.
    """
    default_tickers = [
        "TCS.NS", "INFY.NS", "HDFCBANK.NS", "RELIANCE.NS",
        "ICICIBANK.NS", "SBIN.NS", "HINDUNILVR.NS", "MARUTI.NS",
        "SUNPHARMA.NS", "BHARTIARTL.NS",
    ]
    result = retrain_weights(tickers or default_tickers, start_date, end_date)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Portfolio Optimizer — MVO + Black-Litterman + Efficient Frontier
# ---------------------------------------------------------------------------

@app.post("/optimizer/mvo")
def optimizer_mvo(req: MVORequest):
    """
    Mean-Variance Optimisation (Markowitz 1952).

    Finds portfolio weights that maximise Sharpe ratio (or minimise variance).
    Returns optimal weights, expected return, volatility, and Sharpe.
    Compares against equal-weight baseline.

    Body: {"tickers": ["HDFCBANK.NS","TCS.NS","RELIANCE.NS"], "target": "max_sharpe"}
    """
    result = mean_variance_optimize(
        req.tickers, period_months=req.period_months,
        target=req.target, min_weight=req.min_weight, max_weight=req.max_weight,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/optimizer/black-litterman")
def optimizer_bl(req: BLRequest):
    """
    Black-Litterman optimiser with FinBERT sentiment views (He & Litterman 1999).

    Inject your sentiment views as Bayesian priors that shift equilibrium weights.
    High-confidence positive views increase allocation; negative views decrease it.

    sentiment_views format: {ticker: [expected_excess_return, confidence]}
    e.g. {"HDFCBANK.NS": [0.04, 0.8]}  means +4% excess return, 80% confident.

    Body:
      {
        "tickers": ["HDFCBANK.NS","TCS.NS","RELIANCE.NS"],
        "sentiment_views": {"HDFCBANK.NS": [0.04, 0.8], "TCS.NS": [-0.02, 0.7]}
      }
    """
    views = {k: tuple(v) for k, v in req.sentiment_views.items()}
    result = black_litterman_optimize(req.tickers, views, period_months=req.period_months, tau=req.tau)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/optimizer/frontier")
def optimizer_frontier(req: FrontierRequest):
    """
    Trace the full efficient frontier for a set of NSE stocks.

    Returns 50 (risk, return) combinations plus tangency portfolio,
    min-variance portfolio, and equal-weight position for comparison.
    Use the frontier array to draw the classic Markowitz curve.
    """
    result = efficient_frontier(req.tickers, period_months=req.period_months, n_points=req.n_points)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/optimizer/hrp")
def optimizer_hrp(req: FrontierRequest):
    """
    Hierarchical Risk Parity (López de Prado 2016).

    Modern alternative to Markowitz that uses correlation clustering instead
    of matrix inversion. Produces diversified, robust weights that hold up
    better out-of-sample. No expected-return estimates needed.

    Body: {"tickers": ["HDFCBANK.NS","TCS.NS","RELIANCE.NS","INFY.NS"]}
    """
    result = hierarchical_risk_parity(req.tickers, period_months=req.period_months)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/optimizer/auto")
def optimizer_auto(req: AlphaViewsRequest):
    """
    Full pipeline: Alpha scores → Black-Litterman → Optimal weights.

    Automatically computes alpha scores for all tickers, converts them
    to BL views, and runs the optimiser. No manual view input needed.

    Body: {"tickers": ["HDFCBANK.NS","TCS.NS","RELIANCE.NS","INFY.NS"]}
    """
    result = optimize_with_alpha_views(req.tickers, period_months=req.period_months)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Pairs Trading / Statistical Arbitrage
# ---------------------------------------------------------------------------

@app.post("/pairs/find")
def pairs_find(req: PairsFindRequest):
    """
    Scan a list of tickers for cointegrated pairs (suitable for pairs trading).
    Returns pairs ranked by cointegration p-value (lower = stronger).

    Body: {"tickers": ["HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","AXISBANK.NS"]}
    """
    result = find_cointegrated_pairs(req.tickers, period_months=req.period_months)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/pairs/analyze")
def pairs_analyze(req: PairAnalyzeRequest):
    """
    Analyse one pair: hedge ratio, cointegration, z-score, half-life, and the
    current trading signal (long/short/flat).

    Body: {"stock_a": "HDFCBANK.NS", "stock_b": "ICICIBANK.NS"}
    """
    result = analyze_pair(req.stock_a, req.stock_b, req.period_months, req.entry_z, req.exit_z)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/pairs/backtest")
def pairs_backtest(req: PairBacktestRequest):
    """
    Backtest a market-neutral pairs trading strategy on two stocks.
    Returns return, Sharpe, drawdown, number of trades, and equity curve.
    """
    result = backtest_pair(req.stock_a, req.stock_b, req.period_months, req.entry_z, req.exit_z)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Fama-French 3-factor model
# ---------------------------------------------------------------------------

@app.get("/factors/regression")
def factors_regression(
    ticker: str = Query(..., description="NSE ticker e.g. HDFCBANK.NS"),
    period_months: int = Query(36, description="Lookback window"),
):
    """
    Fama-French 3-factor regression for a stock.

    Decomposes the stock's return into alpha + market/size/value factor
    exposures, with t-stats and p-values. Tells you whether the stock has
    genuine alpha or is just factor exposure.
    """
    result = factor_regression(ticker, period_months=period_months)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Monte Carlo simulation
# ---------------------------------------------------------------------------

@app.post("/montecarlo/simulate")
def montecarlo_simulate(req: MonteCarloRequest):
    """
    Run a Monte Carlo simulation of a portfolio's future value.

    Methods: "normal" | "t" (fat-tailed) | "bootstrap" (historical resampling).
    Returns outcome percentiles, probability of loss, fan-chart bands,
    and a histogram of final values.

    Body: {"holdings": {"HDFCBANK.NS": 50, "TCS.NS": 50}, "method": "bootstrap"}
    """
    result = mc_simulate(
        req.holdings, req.initial_value, req.horizon_days,
        req.n_simulations, method=req.method,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/montecarlo/compare")
def montecarlo_compare(req: MonteCarloRequest):
    """
    Run all three Monte Carlo methods on the same portfolio and compare.
    Reveals how much the Normal distribution understates NSE crash risk
    vs fat-tailed and bootstrap methods.
    """
    result = mc_compare(req.holdings, req.initial_value, req.horizon_days, req.n_simulations)
    return result


# ---------------------------------------------------------------------------
# Regime Detector
# ---------------------------------------------------------------------------

@app.get("/regime")
def regime_current(
    ticker: str = Query("^NSEI", description="Index ticker (default: Nifty 50)"),
    lookback_days: int = Query(252, description="Days of history to fit HMM on"),
):
    """
    Detect current market regime using a 3-state Gaussian HMM.

    Fits a Hidden Markov Model on Nifty 50 daily returns and volatility.
    Returns: Bull | Bear | Sideways with probability, regime statistics,
    transition matrix, 90-day history, and factor weight adjustments.
    """
    result = detect_regime(ticker, lookback_days=lookback_days)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Research / Signal studies
# ---------------------------------------------------------------------------

@app.get("/research/sentiment-alpha")
def research_sentiment_alpha(
    ticker: str = Query(..., description="NSE ticker e.g. HDFCBANK.NS"),
    days_back: int = Query(120, description="How far back to look for news"),
):
    """
    STUDY: Does negative FinBERT sentiment predict negative next-day/week returns?

    Tests on real NSE price data + news headlines.
    Returns signal strength, win rate, t-statistic, and p-value.
    A p-value < 0.05 means the signal is statistically significant.
    """
    result = sentiment_alpha_study(ticker, days_back=days_back, forward_windows=[1, 5, 10])
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/research/momentum")
def research_momentum(req: MomentumStudyRequest):
    """
    STUDY: Do past NSE winners keep winning? (Momentum factor)

    Ranks provided tickers by trailing N-month return each month,
    long top third vs bottom third, measures next-month spread.
    Returns t-test result and monthly win rate.

    Body: {"tickers": ["TCS.NS","INFY.NS","HDFCBANK.NS",...], "lookback_months": 6}
    """
    result = momentum_study(
        req.tickers, req.lookback_months, req.holding_months, req.start_year
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/research/mean-reversion")
def research_mean_reversion(
    ticker: str = Query(..., description="NSE ticker"),
    threshold_pct: float = Query(3.0, description="Shock size to test e.g. 3.0 = ±3%"),
    forward_days:  int   = Query(5,   description="Days to measure reversal over"),
):
    """
    STUDY: Do large single-day moves in NSE stocks reverse within 5 days?

    Finds every day with abs(return) > threshold%, measures next N-day return.
    Tells you whether mean reversion is real and significant for this stock.
    """
    result = mean_reversion_study(ticker, threshold_pct, forward_days)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/research/correlation")
def research_correlation(req: CorrelationStudyRequest):
    """
    STUDY: Which stock combinations actually diversify risk?

    Returns pairwise correlation matrix, best/worst diversifier pairs,
    and how much volatility combining these stocks removes vs holding individually.

    Body: {"tickers": ["TCS.NS","HDFCBANK.NS","HINDUNILVR.NS",...]}
    """
    result = correlation_study(req.tickers, req.start_date, req.end_date, req.period_months)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/research/macro-signal")
def research_macro_signal(req: MacroSignalRequest):
    """
    STUDY: Does a macro news keyword predict sector returns?

    Example: does 'crude oil surge' in headlines predict negative BPCL/IndiGo returns?
    Tests on real news + price data with t-test significance.

    Body: {"macro_keyword": "crude oil", "sector_ticker": "INDIGO.NS"}
    """
    result = macro_sector_signal_study(
        req.macro_keyword, req.sector_ticker, req.days_back, req.forward_days
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/research/full-report")
def research_full_report(ticker: str = Query(..., description="NSE ticker")):
    """
    Run all research studies for a single stock and return a unified report.
    Includes sentiment alpha, mean reversion, and Sharpe vs benchmark.
    Takes 30-60 seconds.
    """
    result = full_research_report(ticker)
    return result


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "service": "Indian Stock Investor Intelligence Platform",
        "status":  "running",
        "docs":    "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
