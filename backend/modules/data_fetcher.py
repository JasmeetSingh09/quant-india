import yfinance as yf
import pandas as pd
import time
from datetime import datetime
from functools import lru_cache

# ---------------------------------------------------------------------------
# Shared price cache
# ---------------------------------------------------------------------------
# Many modules (optimizer, pairs, GARCH, research) download the same tickers.
# Without a cache, requesting RELIANCE across five endpoints hits yfinance five
# times. This module-level cache stores each (ticker, start, end) price series
# for a short TTL so repeat requests are served from memory — one download layer
# shared by all algorithms.

_PRICE_CACHE: dict = {}
_PRICE_TTL = 600   # seconds (10 minutes)


def download_close(ticker: str, start: str, end: str = None) -> pd.Series:
    """
    Cached daily adjusted-close series for one ticker. Served from memory if
    fetched within the last 10 minutes; otherwise downloaded and cached.
    Returns an empty Series on failure (never raises).
    """
    key = (ticker, start, end)
    now = time.time()
    hit = _PRICE_CACHE.get(key)
    if hit and (now - hit[0] < _PRICE_TTL):
        return hit[1]
    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        series = df["Close"].squeeze() if not df.empty else pd.Series(dtype=float)
    except Exception:
        series = pd.Series(dtype=float)
    _PRICE_CACHE[key] = (now, series)
    return series


def clear_price_cache():
    """Empty the shared price cache (e.g. for a forced refresh)."""
    _PRICE_CACHE.clear()

# ---------------------------------------------------------------------------
# Complete NSE stock universe — grouped by sector for easy lookup
# Any ticker not in this list still works via yfinance; this is used for
# sector-peer mapping and the search function.
# ---------------------------------------------------------------------------

NSE_SECTORS = {
    "Banking": [
        "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS",
        "BANKBARODA.NS", "BANKINDIA.NS", "CANBK.NS", "UNIONBANK.NS", "PNB.NS",
        "IDFCFIRSTB.NS", "FEDERALBNK.NS", "INDUSINDBK.NS", "YESBANK.NS", "AUBANK.NS",
        "RBLBANK.NS", "BANDHANBNK.NS", "DCBBANK.NS", "LAKSHVILAS.NS", "KARURVYSYA.NS",
    ],
    "NBFC": [
        "BAJFINANCE.NS", "BAJAJFINSV.NS", "MUTHOOTFIN.NS", "MANAPPURAM.NS",
        "CHOLAFIN.NS", "LTFH.NS", "POONAWALLA.NS", "LICHSGFIN.NS", "CANFINHOME.NS",
        "RECLTD.NS", "PFC.NS", "IRFC.NS", "HUDCO.NS",
    ],
    "IT": [
        "TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS",
        "LTIM.NS", "MPHASIS.NS", "COFORGE.NS", "PERSISTENT.NS", "OFSS.NS",
        "HEXAWARE.NS", "NIITTECH.NS", "KPITTECH.NS", "TATAELXSI.NS", "CYIENT.NS",
        "MASTEK.NS", "HAPPSTMNDS.NS", "SONATSOFTW.NS", "RATEGAIN.NS", "ZENSARTECH.NS",
    ],
    "Oil_Gas": [
        "RELIANCE.NS", "ONGC.NS", "BPCL.NS", "HPCL.NS", "IOC.NS",
        "GAIL.NS", "PETRONET.NS", "OIL.NS", "MGL.NS", "IGL.NS", "GUJGASLTD.NS",
        "AEGASIND.NS", "CASTROLIND.NS", "GULFOILLUB.NS",
    ],
    "Pharma": [
        "SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "APOLLOHOSP.NS",
        "AUROPHARMA.NS", "LUPIN.NS", "BIOCON.NS", "ALKEM.NS", "TORNTPHARM.NS",
        "GLENMARK.NS", "IPCA.NS", "NATCOPHARM.NS", "ABBOTINDIA.NS", "PFIZER.NS",
        "GLAXO.NS", "SANOFI.NS", "AJANTPHARM.NS", "GRANULES.NS", "LAURUSLABS.NS",
        "ZYDUSLIFE.NS", "ERIS.NS", "JB.NS",
    ],
    "Auto": [
        "MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS",
        "EICHERMOT.NS", "TVSMOTOR.NS", "ASHOKLEY.NS", "ESCORTS.NS", "BALKRISIND.NS",
        "BOSCHLTD.NS", "MOTHERSON.NS", "BHARATFORG.NS", "APOLLOTYRE.NS", "MRF.NS",
        "CEATLTD.NS", "EXIDEIND.NS", "AMARARAJA.NS",
    ],
    "FMCG": [
        "HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "DABUR.NS", "MARICO.NS",
        "GODREJCP.NS", "COLPAL.NS", "EMAMILTD.NS", "BAJAJCON.NS", "TATACONSUM.NS",
        "BRITANNIA.NS", "RADICO.NS", "UNITDSPR.NS", "MCDOWELL-N.NS", "VBL.NS",
        "HATSUN.NS", "JUBLLFOOD.NS", "DEVYANI.NS",
    ],
    "Cement": [
        "ULTRACEMCO.NS", "AMBUJACEM.NS", "ACC.NS", "SHREECEM.NS", "DALMIACEME.NS",
        "JKCEMENT.NS", "HEIDELBERG.NS", "RAMCOCEM.NS", "ORIENTCEM.NS", "STAR.NS",
        "BIRLACORPN.NS",
    ],
    "Steel_Metal": [
        "TATASTEEL.NS", "JSWSTEEL.NS", "SAIL.NS", "HINDALCO.NS", "VEDL.NS",
        "NMDC.NS", "COALINDIA.NS", "NATIONALUM.NS", "MOIL.NS", "RATNAMANI.NS",
        "KALYANKJIL.NS", "EDELWEISS.NS",
    ],
    "Telecom": [
        "BHARTIARTL.NS", "IDEA.NS", "TATACOMM.NS", "INDIAMART.NS",
        "TEJASNET.NS", "HFCL.NS", "STLTECH.NS",
    ],
    "Real_Estate": [
        "DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "PHOENIXLTD.NS", "PRESTIGE.NS",
        "SOBHA.NS", "BRIGADE.NS", "MAHLIFE.NS", "SUNTECK.NS", "KEYFINSERV.NS",
    ],
    "Power": [
        "NTPC.NS", "POWERGRID.NS", "TATAPOWER.NS", "ADANIPOWER.NS", "CESC.NS",
        "TORNTPOWER.NS", "RPOWER.NS", "JSW ENERGY.NS", "NHPC.NS", "SJVN.NS",
        "ADANIGREEN.NS",
    ],
    "Capital_Goods": [
        "LT.NS", "BHEL.NS", "SIEMENS.NS", "ABB.NS", "HAVELLS.NS",
        "CROMPTON.NS", "VOLTAS.NS", "BLUESTARCO.NS", "THERMAX.NS", "CG.NS",
        "AIAENG.NS", "GRINDWELL.NS",
    ],
    "Consumer_Durables": [
        "TITAN.NS", "WHIRLPOOL.NS", "BATA.NS", "VIP.NS", "RELAXO.NS",
        "SYMPHONY.NS", "ORIENTELEC.NS", "BAJAJELECTR.NS", "VEDANT.NS",
        "KALYANKJIL.NS", "SENCO.NS", "PCJEWELLER.NS",
    ],
    "Aviation": [
        "INDIGO.NS", "SPICEJET.NS",
    ],
    "Insurance": [
        "SBILIFE.NS", "HDFCLIFE.NS", "ICICIGI.NS", "ICICIPRULI.NS", "LICI.NS",
        "STARHEALTH.NS", "NIACL.NS", "GICRE.NS",
    ],
    "Infra": [
        "ADANIENT.NS", "ADANIPORTS.NS", "ADANIGREEN.NS", "NHAI.NS",
        "IRB.NS", "KNR.NS", "GPPL.NS",
    ],
    "Chemicals": [
        "PIDILITIND.NS", "ASIANPAINT.NS", "BERGER.NS", "KANSAINER.NS",
        "NOCIL.NS", "DEEPAKNTR.NS", "AARTI.NS", "NAVINFLUOR.NS",
        "ALKYLAMINE.NS", "VINATIORGA.NS", "CLEAN.NS", "GALAXYSURF.NS",
    ],
    "Retail": [
        "DMART.NS", "ABFRL.NS", "TRENT.NS", "SHOPERSTOP.NS", "VMART.NS",
        "NYKAA.NS", "ZOMATO.NS", "PAYTM.NS", "POLICYBZR.NS",
    ],
    "Diversified": [
        "ADANIENT.NS", "BAJAJHLDNG.NS", "TATAINVEST.NS", "GODREJIND.NS",
        "JSWHOLDING.NS",
    ],
}

# Flat name→ticker lookup for search
NSE_NAME_INDEX = {
    # A
    "ABB": "ABB.NS",
    "ACC": "ACC.NS",
    "ADANI ENTERPRISES": "ADANIENT.NS",
    "ADANI PORTS": "ADANIPORTS.NS",
    "ADANI GREEN": "ADANIGREEN.NS",
    "ADANI POWER": "ADANIPOWER.NS",
    "AJANTA PHARMA": "AJANTPHARM.NS",
    "ALKEM": "ALKEM.NS",
    "AMBUJA CEMENT": "AMBUJACEM.NS",
    "APOLLO HOSPITALS": "APOLLOHOSP.NS",
    "APOLLO TYRES": "APOLLOTYRE.NS",
    "ASIAN PAINTS": "ASIANPAINT.NS",
    "AU SMALL FINANCE": "AUBANK.NS",
    "AUBANK": "AUBANK.NS",
    "AUROPHARMA": "AUROPHARMA.NS",
    "AXIS BANK": "AXISBANK.NS",
    # B
    "BAJAJ AUTO": "BAJAJ-AUTO.NS",
    "BAJAJ FINANCE": "BAJFINANCE.NS",
    "BAJAJ FINSERV": "BAJAJFINSV.NS",
    "BALKRISHNA INDUSTRIES": "BALKRISIND.NS",
    "BANDHAN BANK": "BANDHANBNK.NS",
    "BANK OF BARODA": "BANKBARODA.NS",
    "BANK OF INDIA": "BANKINDIA.NS",
    "BATA": "BATA.NS",
    "BERGER PAINTS": "BERGER.NS",
    "BHARAT ELECTRONICS": "BEL.NS",
    "BHARAT FORGE": "BHARATFORG.NS",
    "BHARAT PETROLEUM": "BPCL.NS",
    "BHARTI AIRTEL": "BHARTIARTL.NS",
    "BHEL": "BHEL.NS",
    "BIOCON": "BIOCON.NS",
    "BOSCH": "BOSCHLTD.NS",
    "BRITANNIA": "BRITANNIA.NS",
    # C
    "CANARA BANK": "CANBK.NS",
    "CEAT": "CEATLTD.NS",
    "CESC": "CESC.NS",
    "CIPLA": "CIPLA.NS",
    "COAL INDIA": "COALINDIA.NS",
    "COFORGE": "COFORGE.NS",
    "COLGATE": "COLPAL.NS",
    "CROMPTON": "CROMPTON.NS",
    # D
    "DABUR": "DABUR.NS",
    "DALMIA BHARAT": "DALMIACEME.NS",
    "DEEPAK NITRITE": "DEEPAKNTR.NS",
    "DIVI'S LAB": "DIVISLAB.NS",
    "DLF": "DLF.NS",
    "DMART": "DMART.NS",
    "DR REDDY": "DRREDDY.NS",
    # E
    "EICHER MOTORS": "EICHERMOT.NS",
    "ESCORTS": "ESCORTS.NS",
    "EXIDE": "EXIDEIND.NS",
    # F
    "FEDERAL BANK": "FEDERALBNK.NS",
    # G
    "GAIL": "GAIL.NS",
    "GLENMARK": "GLENMARK.NS",
    "GODREJ CONSUMER": "GODREJCP.NS",
    "GODREJ PROPERTIES": "GODREJPROP.NS",
    "GRANULES": "GRANULES.NS",
    "GUJARAT GAS": "GUJGASLTD.NS",
    # H
    "HAVELLS": "HAVELLS.NS",
    "HCL TECH": "HCLTECH.NS",
    "HDFC BANK": "HDFCBANK.NS",
    "HDFC LIFE": "HDFCLIFE.NS",
    "HERO MOTO": "HEROMOTOCO.NS",
    "HINDALCO": "HINDALCO.NS",
    "HINDUSTAN UNILEVER": "HINDUNILVR.NS",
    "HUL": "HINDUNILVR.NS",
    "HPCL": "HPCL.NS",
    # I
    "ICICI BANK": "ICICIBANK.NS",
    "ICICI LOMBARD": "ICICIGI.NS",
    "ICICI PRUDENTIAL": "ICICIPRULI.NS",
    "IDFC FIRST": "IDFCFIRSTB.NS",
    "INDIA CEMENT": "INDIACEM.NS",
    "INDIGO": "INDIGO.NS",
    "INDUSIND BANK": "INDUSINDBK.NS",
    "INFOSYS": "INFY.NS",
    "IOC": "IOC.NS",
    "IRFC": "IRFC.NS",
    "ITC": "ITC.NS",
    # J
    "JSW STEEL": "JSWSTEEL.NS",
    # K
    "KOTAK BANK": "KOTAKBANK.NS",
    # L
    "L&T": "LT.NS",
    "LARSEN AND TOUBRO": "LT.NS",
    "LAURUS LABS": "LAURUSLABS.NS",
    "LIC": "LICI.NS",
    "LUPIN": "LUPIN.NS",
    # M
    "MAHINDRA": "M&M.NS",
    "M&M": "M&M.NS",
    "MARICO": "MARICO.NS",
    "MARUTI": "MARUTI.NS",
    "MARUTI SUZUKI": "MARUTI.NS",
    "MOTHERSON": "MOTHERSON.NS",
    "MRF": "MRF.NS",
    "MUTHOOT FINANCE": "MUTHOOTFIN.NS",
    # N
    "NAVINFLUORINE": "NAVINFLUOR.NS",
    "NESTLÉ": "NESTLEIND.NS",
    "NESTLE": "NESTLEIND.NS",
    "NMDC": "NMDC.NS",
    "NTPC": "NTPC.NS",
    "NYKAA": "NYKAA.NS",
    # O
    "OBEROI REALTY": "OBEROIRLTY.NS",
    "ONGC": "ONGC.NS",
    "ORACLE FINANCIAL": "OFSS.NS",
    # P
    "PAYTM": "PAYTM.NS",
    "PERSISTENT": "PERSISTENT.NS",
    "PETRONET": "PETRONET.NS",
    "PFC": "PFC.NS",
    "PHOENIX MILLS": "PHOENIXLTD.NS",
    "PIDILITE": "PIDILITIND.NS",
    "PNB": "PNB.NS",
    "POWER FINANCE": "PFC.NS",
    "POWER GRID": "POWERGRID.NS",
    # R
    "RBL BANK": "RBLBANK.NS",
    "REC": "RECLTD.NS",
    "RELIANCE": "RELIANCE.NS",
    "RELIANCE INDUSTRIES": "RELIANCE.NS",
    # S
    "SAIL": "SAIL.NS",
    "SBI": "SBIN.NS",
    "SBI LIFE": "SBILIFE.NS",
    "SIEMENS": "SIEMENS.NS",
    "SOBHA": "SOBHA.NS",
    "STAR HEALTH": "STARHEALTH.NS",
    "STATE BANK": "SBIN.NS",
    "SUN PHARMA": "SUNPHARMA.NS",
    # T
    "TATA CONSULTANCY": "TCS.NS",
    "TATA CONSUMER": "TATACONSUM.NS",
    "TATA MOTORS": "TATAMOTORS.NS",
    "TATA POWER": "TATAPOWER.NS",
    "TATA STEEL": "TATASTEEL.NS",
    "TCS": "TCS.NS",
    "TECH MAHINDRA": "TECHM.NS",
    "THERMAX": "THERMAX.NS",
    "TITAN": "TITAN.NS",
    "TORRENT PHARMA": "TORNTPHARM.NS",
    "TORRENT POWER": "TORNTPOWER.NS",
    "TRENT": "TRENT.NS",
    "TVS MOTOR": "TVSMOTOR.NS",
    # U
    "ULTRATECH CEMENT": "ULTRACEMCO.NS",
    "UNION BANK": "UNIONBANK.NS",
    # V
    "VEDANTA": "VEDL.NS",
    "VOLTAS": "VOLTAS.NS",
    # W
    "WIPRO": "WIPRO.NS",
    # Y
    "YES BANK": "YESBANK.NS",
    # Z
    "ZOMATO": "ZOMATO.NS",
    "ZYDUS": "ZYDUSLIFE.NS",
}

def get_stock_data(ticker: str, period: str = "1mo") -> pd.DataFrame:
    """
    Fetch historical price data for a stock.
    
    ticker: NSE stock symbol e.g. "RELIANCE.NS" or "TCS.NS"
    period: how far back to go - "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"
    
    Returns a DataFrame with Date, Open, High, Low, Close, Volume columns.
    """
    stock = yf.Ticker(ticker)
    df = stock.history(period=period)
    df.index = pd.to_datetime(df.index)
    return df


def get_intraday_data(ticker: str, interval: str = "5m", period: str = "1d") -> dict:
    """
    Fetch intraday price bars so charts move during the trading day.

    interval: "1m" (last ~7 days), "5m" / "15m" (last ~60 days)
    period:   "1d", "5d", "1mo"

    Reliability: if intraday data is unavailable (market closed, rate limit,
    or interval not supported), gracefully falls back to daily candles so the
    chart is never blank. Returns a 'resolution' field so the UI knows which.
    """
    stock = yf.Ticker(ticker)
    resolution = interval
    try:
        df = stock.history(period=period, interval=interval)
        if df.empty:
            raise ValueError("empty intraday")
    except Exception:
        # Fallback to daily over 1 month
        try:
            df = stock.history(period="1mo", interval="1d")
            resolution = "1d (intraday unavailable)"
        except Exception as e:
            return {"ticker": ticker, "error": str(e), "candles": []}

    df = df.dropna()
    candles = []
    for idx, row in df.iterrows():
        candles.append({
            "time":  idx.strftime("%Y-%m-%d %H:%M"),
            "price": round(float(row["Close"]), 2),
            "volume": int(row.get("Volume", 0) or 0),
        })

    return {
        "ticker":      ticker,
        "interval":    interval,
        "resolution":  resolution,
        "candles":     candles,
        "last_price":  candles[-1]["price"] if candles else None,
        "fetched_at":  datetime.now().strftime("%H:%M:%S"),
    }


def _ist_now():
    from datetime import timezone as _tz, timedelta as _td
    return datetime.now(_tz(_td(hours=5, minutes=30)))


def is_market_open() -> bool:
    """
    Is the NSE regular session open right now? Mon-Fri, 09:15-15:30 IST.
    (Exchange holidays are not accounted for — a holiday will read as 'open'
    by time, but yfinance simply won't have new ticks, so the price stays flat.)
    """
    ist = _ist_now()
    if ist.weekday() >= 5:                      # Saturday / Sunday
        return False
    minutes = ist.hour * 60 + ist.minute
    return (9 * 60 + 15) <= minutes <= (15 * 60 + 30)


def is_feed_active() -> bool:
    """
    Should the UI keep polling? True during the session AND for ~15 min after
    close, so the ~15-min-DELAYED yfinance feed's final ticks (3:15-3:30 trades)
    can still arrive and the true closing price shows up before we freeze.
    """
    ist = _ist_now()
    if ist.weekday() >= 5:
        return False
    minutes = ist.hour * 60 + ist.minute
    return (9 * 60 + 15) <= minutes <= (15 * 60 + 45)


def get_current_price(ticker: str) -> dict:
    """
    Get the current price and today's change for a stock.
    """
    stock = yf.Ticker(ticker)
    info = stock.fast_info

    try:
        current_price = info.last_price
        previous_close = info.previous_close
        change = current_price - previous_close
        change_pct = (change / previous_close) * 100
        volume = info.three_month_average_volume

        return {
            "ticker": ticker,
            "price": round(current_price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "volume": volume,
            "market_open": is_market_open(),
            "feed_active": is_feed_active(),   # keep polling ~15 min past close (delayed feed)
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def get_company_info(ticker: str) -> dict:
    """
    Get company metadata - name, sector, industry, market cap.
    """
    stock = yf.Ticker(ticker)
    info = stock.info
    
    return {
        "name": info.get("longName", ticker),
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry", "Unknown"),
        "market_cap": info.get("marketCap", 0),
        "description": info.get("longBusinessSummary", "")[:300],
        "website": info.get("website", ""),
        "employees": info.get("fullTimeEmployees", 0)
    }


@lru_cache(maxsize=32)
def _fx_rate(from_cur: str, to_cur: str) -> float | None:
    """Spot FX rate (1 unit of from_cur in to_cur). Cached per session."""
    if not from_cur or not to_cur or from_cur == to_cur:
        return 1.0
    try:
        r = yf.Ticker(f"{from_cur}{to_cur}=X").info.get("regularMarketPrice")
        return float(r) if r else None
    except Exception:
        return None


def _ev_ebitda(info: dict, ev, ebitda_inr):
    """
    EV/EBITDA, currency-corrected. Uses yfinance's value if sane, else recomputes
    enterpriseValue / EBITDA (both already in the price currency).
    """
    val = info.get("enterpriseToEbitda")
    if val is not None and 0 < val <= 100:
        return round(val, 1)
    if not ev or not ebitda_inr:
        return None
    computed = ev / ebitda_inr
    return round(computed, 1) if 0 < computed <= 100 else None


def get_financial_metrics(ticker: str) -> dict:
    """
    Get key financial metrics for valuation analysis.
    """
    stock = yf.Ticker(ticker)
    info = stock.info

    # yfinance reports debtToEquity as a PERCENTAGE (e.g. 9.83 = 9.83%);
    # convert to the conventional ratio (0.10).
    de = info.get("debtToEquity", None)
    debt_to_equity = round(de / 100, 2) if de is not None else None

    # EV & EBITDA: yfinance reports enterpriseValue in the price currency (INR)
    # but ebitda in the FINANCIAL currency (USD for INFY/TCS/WIPRO). Convert
    # EBITDA to INR so both — and the EV/EBITDA ratio — are consistent.
    enterprise_value = info.get("enterpriseValue")
    ebitda_raw = info.get("ebitda")
    fx = _fx_rate(info.get("financialCurrency"), info.get("currency"))
    ebitda = round(ebitda_raw * fx) if (ebitda_raw and fx) else None
    ev_ebitda = _ev_ebitda(info, enterprise_value, ebitda)

    return {
        "pe_ratio": info.get("trailingPE", None),
        "forward_pe": info.get("forwardPE", None),
        "ev_ebitda": ev_ebitda,
        "enterprise_value": enterprise_value,
        "ebitda": ebitda,
        "price_to_book": info.get("priceToBook", None),
        "price_to_sales": info.get("priceToSalesTrailing12Months", None),
        "roe": info.get("returnOnEquity", None),
        "roa": info.get("returnOnAssets", None),
        "profit_margin": info.get("profitMargins", None),
        "revenue_growth": info.get("revenueGrowth", None),
        "earnings_growth": info.get("earningsGrowth", None),
        "debt_to_equity": debt_to_equity,
        "current_ratio": info.get("currentRatio", None),
        "free_cashflow": info.get("freeCashflow", None),
        "dividend_yield": info.get("dividendYield", None),
        "week_52_high": info.get("fiftyTwoWeekHigh", None),
        "week_52_low": info.get("fiftyTwoWeekLow", None),
    }


def get_sector_peers(ticker: str) -> list:
    """
    Get peer companies in the same NSE sector.

    Looks up which sector the ticker belongs to in NSE_SECTORS and returns
    the other stocks in that sector (up to 5 peers, excluding the ticker itself).
    Falls back to yfinance sector field for tickers not in the map.
    """
    ticker = ticker.upper()
    for sector, members in NSE_SECTORS.items():
        if ticker in members:
            peers = [t for t in members if t != ticker]
            return peers[:5]   # return top 5 peers to avoid too many API calls

    # Fallback: try to match by yfinance sector label
    try:
        info   = yf.Ticker(ticker).info
        sector = info.get("sector", "")
        # Map yfinance sector strings to our sector groups
        sector_map = {
            "Technology":           "IT",
            "Financial Services":   "Banking",
            "Consumer Defensive":   "FMCG",
            "Healthcare":           "Pharma",
            "Consumer Cyclical":    "Auto",
            "Energy":               "Oil_Gas",
            "Basic Materials":      "Steel_Metal",
            "Industrials":          "Capital_Goods",
            "Communication Services":"Telecom",
            "Real Estate":          "Real_Estate",
            "Utilities":            "Power",
        }
        mapped = sector_map.get(sector, "")
        if mapped and mapped in NSE_SECTORS:
            peers = [t for t in NSE_SECTORS[mapped] if t != ticker]
            return peers[:5]
    except Exception:
        pass
    return []


def get_all_nse_tickers() -> dict:
    """
    Return the full NSE stock universe grouped by sector.
    Useful for building sector screeners or dropdown menus.
    """
    return NSE_SECTORS


def search_stock(query: str) -> list:
    """
    Search for an NSE stock by company name or partial ticker.

    query: e.g. "reliance", "tcs", "hdfc bank", "pharma"

    Returns a list of matching dicts with ticker, name, and sector.
    Searches both the name index and tickers in NSE_SECTORS.
    """
    query_upper = query.upper().strip()
    matches = {}

    # 1. Exact or partial match in the name index
    for name, ticker in NSE_NAME_INDEX.items():
        if query_upper in name:
            matches[ticker] = {"ticker": ticker, "matched_name": name}

    # 2. Partial ticker match across all sectors
    for sector, tickers in NSE_SECTORS.items():
        for ticker in tickers:
            base = ticker.replace(".NS", "")
            if query_upper in base:
                if ticker not in matches:
                    matches[ticker] = {"ticker": ticker, "matched_name": base}
                matches[ticker]["sector"] = sector

    # Add sector info to name-matched results
    for ticker in matches:
        if "sector" not in matches[ticker]:
            for sector, members in NSE_SECTORS.items():
                if ticker in members:
                    matches[ticker]["sector"] = sector
                    break

    return list(matches.values())[:20]   # cap at 20 results


def format_large_number(num: float) -> str:
    """
    Format large numbers into readable Indian format.
    1000000 -> 10 Lakh
    10000000 -> 1 Crore
    """
    if num is None:
        return "N/A"
    if num >= 1e12:
        return f"₹{num/1e12:.2f}L Cr"
    elif num >= 1e7:
        return f"₹{num/1e7:.2f} Cr"
    elif num >= 1e5:
        return f"₹{num/1e5:.2f} Lakh"
    else:
        return f"₹{num:.2f}"


if __name__ == "__main__":
    # Test the module
    # Run this file directly to test: python backend/modules/data_fetcher.py
    
    print("=" * 50)
    print("Testing data fetcher with RELIANCE.NS")
    print("=" * 50)
    
    print("\n1. Current price:")
    price = get_current_price("RELIANCE.NS")
    for key, value in price.items():
        print(f"   {key}: {value}")
    
    print("\n2. Company info:")
    info = get_company_info("RELIANCE.NS")
    for key, value in info.items():
        if key != "description":
            print(f"   {key}: {value}")
    
    print("\n3. Financial metrics:")
    metrics = get_financial_metrics("RELIANCE.NS")
    for key, value in metrics.items():
        print(f"   {key}: {value}")
    
    print("\n4. Sector peers:")
    peers = get_sector_peers("RELIANCE.NS")
    print(f"   {peers}")
    
    print("\n" + "=" * 50)
    print("Data fetcher working correctly if you see numbers above")
    print("=" * 50)