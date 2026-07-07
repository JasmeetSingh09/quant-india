import os
"""
news.py — Indian financial news fetcher with SQLite caching and APScheduler refresh.

Covers three news types:
  1. Macro news — RBI, crude oil, rupee, FII flows, inflation → maps to sectors/stocks
  2. Company-specific news — earnings, acquisitions, management changes for a given ticker
  3. Market-wide news — Nifty 50 moves, FII/DII activity, SEBI decisions

News is cached in SQLite and refreshed every 30 minutes via APScheduler background job.
NewsAPI free tier has ~1 hour delay; this is shown in the UI via published_minutes_ago.
"""

import os
import sqlite3
import requests
import json
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv(Path(__file__).parent.parent / ".env")

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
DB_PATH = Path(os.environ.get("QUANT_DATA_DIR", str(Path(__file__).parent.parent))) / "quant_platform.db"

# Indian financial news sources to prioritise in search
INDIAN_FINANCE_SOURCES = [
    "The Economic Times",
    "Mint",
    "Business Standard",
    "Moneycontrol",
    "The Financial Express",
]

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _init_db():
    """Create the news cache table if it does not exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_cache (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            cache_key   TEXT NOT NULL,
            articles    TEXT NOT NULL,
            fetched_at  TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_key ON news_cache(cache_key)")
    conn.commit()
    conn.close()


def _cache_get(cache_key: str, max_age_minutes: int = 30) -> list | None:
    """Return cached articles if they are fresh enough, else None."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT articles, fetched_at FROM news_cache WHERE cache_key = ? ORDER BY fetched_at DESC LIMIT 1",
        (cache_key,)
    ).fetchone()
    conn.close()

    if not row:
        return None

    fetched_at = datetime.fromisoformat(row[1])
    age_minutes = (datetime.now() - fetched_at).total_seconds() / 60
    if age_minutes > max_age_minutes:
        return None

    return json.loads(row[0])


def _cache_set(cache_key: str, articles: list):
    """Store articles in the cache."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO news_cache (cache_key, articles, fetched_at) VALUES (?, ?, ?)",
        (cache_key, json.dumps(articles), datetime.now().isoformat())
    )
    # Keep only the 5 most recent entries per key to avoid unbounded growth
    conn.execute("""
        DELETE FROM news_cache
        WHERE cache_key = ? AND id NOT IN (
            SELECT id FROM news_cache WHERE cache_key = ? ORDER BY fetched_at DESC LIMIT 5
        )
    """, (cache_key, cache_key))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Core NewsAPI fetch
# ---------------------------------------------------------------------------

def _minutes_ago(published_at: str) -> int:
    """Return how many minutes ago an article was published."""
    try:
        pub_time = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
        delta = datetime.utcnow() - pub_time
        return max(0, int(delta.total_seconds() / 60))
    except Exception:
        return -1


def _fetch_from_api(query: str, days_back: int = 3, page_size: int = 20) -> list:
    """
    Raw NewsAPI fetch. Returns list of article dicts with published_minutes_ago added.
    Does NOT do sentiment analysis — that is handled by sentiment.py.
    """
    if not NEWS_API_KEY:
        print("ERROR: NEWS_API_KEY not found in .env")
        return []

    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    params = {
        "q": query,
        "from": from_date,
        "sortBy": "publishedAt",
        "language": "en",
        "apiKey": NEWS_API_KEY,
        "pageSize": page_size,
    }

    try:
        response = requests.get("https://newsapi.org/v2/everything", params=params, timeout=10)
        data = response.json()

        if data.get("status") != "ok":
            print(f"NewsAPI error: {data.get('message', 'Unknown error')}")
            return []

        articles = []
        for art in data.get("articles", []):
            if not art.get("title") or not art.get("description"):
                continue
            articles.append({
                "title": art["title"],
                "description": art.get("description", ""),
                "url": art.get("url", ""),
                "source": art["source"]["name"],
                "published_at": art.get("publishedAt", ""),
                "published_minutes_ago": _minutes_ago(art.get("publishedAt", "")),
                "newsapi_delay_note": "Free tier has ~60 min delay",
            })

        return articles

    except Exception as e:
        print(f"Error fetching from NewsAPI: {e}")
        return []


# ---------------------------------------------------------------------------
# Macro impact mapping
# ---------------------------------------------------------------------------

# Maps keywords → sector impact descriptor
_MACRO_RULES = [
    {
        "keywords": ["crude", "oil", "opec", "brent", "petroleum", "hormuz", "wti"],
        "sector": "Oil & Gas / Aviation",
        "causal_chain": (
            "Crude price rise → higher input costs for refiners (BPCL, HPCL) "
            "→ margin compression unless pass-through allowed; "
            "aviation fuel surges → IndiGo, Air India cost pressure. "
            "ONGC/Reliance upstream benefits from higher realisations."
        ),
        "stocks": {
            "winners": ["ONGC.NS", "RELIANCE.NS"],
            "losers":  ["BPCL.NS", "HPCL.NS", "IOC.NS", "INDIGO.NS"],
        },
        "direction_if_price_rises": "mixed",
    },
    {
        "keywords": ["rbi", "repo rate", "interest rate", "monetary policy", "mpc"],
        "sector": "Banking & NBFC",
        "causal_chain": (
            "Rate hike → banks can charge more on loans (NIM widens short term) "
            "but bond portfolio marks down and loan growth slows. "
            "Rate cut → cheaper borrowing boosts credit growth and real-estate demand."
        ),
        "stocks": {
            "winners": ["HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS"],
            "losers":  ["BAJFINANCE.NS", "LICHSGFIN.NS"],
        },
        "direction_if_rate_hike": "mixed",
    },
    {
        "keywords": ["rupee", "inr", "usd/inr", "dollar", "forex", "currency depreciat"],
        "sector": "IT / Pharma exporters vs importers",
        "causal_chain": (
            "Rupee weakens → IT companies earn USD revenues, INR translation gain "
            "→ TCS/Infosys benefit. Pharma exporters (Sun, Dr Reddy) gain. "
            "Oil importers (airlines, refiners) and companies with USD debt lose."
        ),
        "stocks": {
            "winners": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "SUNPHARMA.NS"],
            "losers":  ["INDIGO.NS", "BPCL.NS", "HPCL.NS"],
        },
        "direction_if_rupee_falls": "mixed",
    },
    {
        "keywords": ["inflation", "cpi", "wpi", "price rise", "consumer price"],
        "sector": "FMCG / Consumer staples",
        "causal_chain": (
            "High inflation raises raw material costs for FMCG companies "
            "(palm oil, wheat, packaging). Volume growth slows as consumers trade down. "
            "HUL, Nestle margin pressure unless they hike prices."
        ),
        "stocks": {
            "winners": [],
            "losers":  ["HINDUNILVR.NS", "NESTLEIND.NS", "DABUR.NS", "MARICO.NS"],
        },
        "direction": "negative",
    },
    {
        "keywords": ["fii", "foreign institutional", "fpi sell", "capital outflow"],
        "sector": "Broader market / Banks",
        "causal_chain": (
            "FII selling → index-heavy stocks (banks, IT, HDFC twins) see outflows "
            "→ rupee weakens → further negative sentiment loop. "
            "DII buying can partially offset but FII flows dominate short-term direction."
        ),
        "stocks": {
            "winners": [],
            "losers":  ["HDFCBANK.NS", "ICICIBANK.NS", "TCS.NS", "RELIANCE.NS"],
        },
        "direction": "negative",
    },
    {
        "keywords": ["gst", "tax reform", "direct tax", "income tax"],
        "sector": "Consumer / Retail",
        "causal_chain": (
            "GST rate cuts on consumer goods → demand stimulus for FMCG and durables. "
            "Rate hikes on luxury goods → discretionary spend caution."
        ),
        "stocks": {
            "winners": ["HINDUNILVR.NS", "ITC.NS", "TITAN.NS"],
            "losers":  [],
        },
        "direction": "positive",
    },
]


def get_macro_impact_on_stocks(headline: str) -> list:
    """
    Given a macro news headline return a list of sector impact dicts.

    Each dict contains:
      - sector, causal_chain, winners, losers, direction, matched_keywords
    """
    headline_lower = headline.lower()
    impacts = []

    for rule in _MACRO_RULES:
        matched = [kw for kw in rule["keywords"] if kw in headline_lower]
        if matched:
            impacts.append({
                "sector": rule["sector"],
                "causal_chain": rule["causal_chain"],
                "winners": rule["stocks"].get("winners", []),
                "losers": rule["stocks"].get("losers", []),
                "direction": rule.get("direction", "mixed"),
                "matched_keywords": matched,
            })

    return impacts


# ---------------------------------------------------------------------------
# Public fetch functions (with cache)
# ---------------------------------------------------------------------------

def get_market_wide_news(days_back: int = 3) -> list:
    """
    Fetch broad Indian market news: Nifty 50 moves, FII/DII, SEBI decisions.

    PRIMARY source: RSS feeds (near-real-time, no 1-hour delay).
    FALLBACK: NewsAPI if RSS returns nothing. Cached ~10 min for freshness.
    """
    cache_key = "market_wide"
    cached = _cache_get(cache_key, max_age_minutes=10)
    if cached is not None:
        return cached

    # 1) Try RSS first (fast, fresh, reliable across multiple feeds)
    articles = []
    try:
        from rss_news import get_rss_market_news
        articles = get_rss_market_news(limit=25)
    except Exception as e:
        print(f"RSS market news failed, falling back to NewsAPI: {e}")

    # 2) Fallback to NewsAPI if RSS gave nothing
    if not articles:
        queries = [
            "Nifty 50 Indian stock market today",
            "FII DII India NSE BSE",
            "SEBI regulation India market",
        ]
        raw = []
        for q in queries:
            raw.extend(_fetch_from_api(q, days_back=days_back, page_size=10))
        seen = set()
        for a in raw:
            if a["url"] not in seen:
                seen.add(a["url"])
                articles.append(a)
        articles.sort(key=lambda x: x["published_minutes_ago"])

    if articles:
        _cache_set(cache_key, articles)
    return articles


def get_macro_news(days_back: int = 3) -> list:
    """
    Fetch macro economic news (RBI, crude oil, rupee, FII, inflation).
    Each article is enriched with sector impact via get_macro_impact_on_stocks.
    Results cached for 30 minutes.
    """
    cache_key = "macro"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    queries = [
        "RBI interest rate India monetary policy",
        "crude oil price India impact",
        "Indian rupee dollar forex",
        "India inflation CPI data",
        "FII foreign investment India sell buy",
    ]
    articles = []
    for q in queries[:3]:  # limit on free tier to avoid rate limits
        articles.extend(_fetch_from_api(q, days_back=days_back, page_size=8))

    seen = set()
    unique = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            impacts = get_macro_impact_on_stocks(a["title"])
            a["macro_impacts"] = impacts
            unique.append(a)

    unique.sort(key=lambda x: x["published_minutes_ago"])
    _cache_set(cache_key, unique)
    return unique


def get_stock_news(ticker: str, company_name: str = None, days_back: int = 7) -> list:
    """
    Fetch company-specific news for an NSE ticker.
    If company_name is not provided it is fetched from yfinance.
    Results cached per ticker for 30 minutes.
    """
    cache_key = f"stock_{ticker}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if not company_name:
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info
            company_name = info.get("longName", ticker.replace(".NS", ""))
        except Exception:
            company_name = ticker.replace(".NS", "")

    # 1) Try RSS first (near-real-time, filtered for this company)
    articles = []
    try:
        from rss_news import get_rss_stock_news
        articles = get_rss_stock_news(company_name, ticker, limit=20)
    except Exception as e:
        print(f"RSS stock news failed, falling back to NewsAPI: {e}")

    # 2) Fallback to NewsAPI if RSS found nothing for this company
    if not articles:
        clean_name = company_name
        for suffix in (" Limited", " Ltd.", " Ltd", " Industries Limited"):
            clean_name = clean_name.replace(suffix, "")
        clean_name = clean_name.strip()

        articles = _fetch_from_api(f"{clean_name} stock", days_back=days_back, page_size=20)
        if not articles:
            bare = ticker.replace(".NS", "")
            articles = _fetch_from_api(f"{bare} share price India", days_back=days_back, page_size=20)
        articles.sort(key=lambda x: x["published_minutes_ago"])

    if articles:
        _cache_set(cache_key, articles)
    return articles


# ---------------------------------------------------------------------------
# Background refresh scheduler
# ---------------------------------------------------------------------------

_scheduler = BackgroundScheduler()
_scheduler_started = False


def _refresh_macro():
    """Background job: refresh macro news cache."""
    _cache_set.__doc__  # noqa — just to avoid bare pass
    try:
        queries = [
            "RBI interest rate India monetary policy",
            "crude oil price India impact",
            "Indian rupee dollar forex",
        ]
        articles = []
        for q in queries:
            articles.extend(_fetch_from_api(q, days_back=3, page_size=8))
        seen = set()
        unique = []
        for a in articles:
            if a["url"] not in seen:
                seen.add(a["url"])
                a["macro_impacts"] = get_macro_impact_on_stocks(a["title"])
                unique.append(a)
        _cache_set("macro", unique)
        print(f"[APScheduler] Macro news refreshed at {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"[APScheduler] Macro refresh error: {e}")


def _refresh_market_wide():
    """Background job: refresh market-wide news cache."""
    try:
        queries = [
            "Nifty 50 Indian stock market today",
            "FII DII India NSE BSE",
        ]
        articles = []
        for q in queries:
            articles.extend(_fetch_from_api(q, days_back=3, page_size=10))
        seen = set()
        unique = []
        for a in articles:
            if a["url"] not in seen:
                seen.add(a["url"])
                unique.append(a)
        _cache_set("market_wide", unique)
        print(f"[APScheduler] Market-wide news refreshed at {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"[APScheduler] Market-wide refresh error: {e}")


def start_news_scheduler():
    """
    Start the APScheduler background job that refreshes news every 30 minutes.
    Safe to call multiple times — only starts once.
    """
    global _scheduler_started
    if _scheduler_started:
        return
    _init_db()
    _scheduler.add_job(_refresh_macro, "interval", minutes=30, id="macro_refresh")
    _scheduler.add_job(_refresh_market_wide, "interval", minutes=30, id="market_wide_refresh")
    _scheduler.start()
    _scheduler_started = True
    print("News background scheduler started (30-minute refresh interval)")


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _init_db()

    print("=" * 60)
    print("Testing news.py")
    print("=" * 60)

    print("\n1. Macro impact detection:")
    headlines = [
        "Strait of Hormuz blockade fears send crude oil prices surging",
        "RBI hikes repo rate by 25 bps in emergency MPC meeting",
        "Indian rupee falls to all-time low of 87 against US dollar",
        "India CPI inflation hits 7.2%, above RBI comfort zone",
    ]
    for h in headlines:
        impacts = get_macro_impact_on_stocks(h)
        print(f"\n  Headline: {h}")
        for imp in impacts:
            print(f"    Sector : {imp['sector']}")
            print(f"    Winners: {imp['winners']}")
            print(f"    Losers : {imp['losers']}")
            print(f"    Chain  : {imp['causal_chain'][:80]}...")

    print("\n2. Fetching market-wide news (may take a moment)...")
    news = get_market_wide_news(days_back=3)
    print(f"   Fetched {len(news)} articles")
    if news:
        a = news[0]
        print(f"   Latest: {a['title']}")
        print(f"   Source: {a['source']}  |  {a['published_minutes_ago']} min ago")
        print(f"   Note  : {a['newsapi_delay_note']}")

    print("\n3. Fetching macro news...")
    macro = get_macro_news(days_back=3)
    print(f"   Fetched {len(macro)} macro articles")
    if macro:
        a = macro[0]
        print(f"   Latest: {a['title']}")
        print(f"   Impacts detected: {len(a.get('macro_impacts', []))}")

    print("\n4. Fetching RELIANCE.NS company news...")
    stock_news = get_stock_news("RELIANCE.NS", company_name="Reliance Industries", days_back=7)
    print(f"   Fetched {len(stock_news)} articles for Reliance")
    if stock_news:
        print(f"   Latest: {stock_news[0]['title']}")

    print("\n" + "=" * 60)
    print("news.py test complete")
    print("=" * 60)
