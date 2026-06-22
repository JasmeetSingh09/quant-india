"""
rss_news.py — Near-real-time Indian financial news via RSS feeds.

Pulls directly from the publishers' own RSS feeds (Economic Times, Moneycontrol,
Mint, Business Standard). RSS updates within minutes — no 1-hour delay like the
free NewsAPI tier, and no API key or rate limit.

Reliability by design:
  - MULTIPLE feeds — if one is down or changes, the others still deliver
  - Each fetch is wrapped in try/except — a broken feed never crashes the rest
  - Short timeout so one slow feed doesn't hang the whole request
  - Returns "minutes ago" so the UI always shows freshness

This is the PRIMARY news source. news.py falls back to NewsAPI if RSS returns
nothing (belt and braces).
"""

import time
import requests
import feedparser
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Indian financial RSS feeds — markets/business focused
RSS_FEEDS = [
    {"name": "Economic Times",   "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"},
    {"name": "Economic Times",   "url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"},
    {"name": "Moneycontrol",     "url": "https://www.moneycontrol.com/rss/marketreports.xml"},
    {"name": "Moneycontrol",     "url": "https://www.moneycontrol.com/rss/business.xml"},
    {"name": "Moneycontrol",     "url": "https://www.moneycontrol.com/rss/latestnews.xml"},
    {"name": "Livemint",         "url": "https://www.livemint.com/rss/markets"},
    {"name": "Business Standard","url": "https://www.business-standard.com/rss/markets-106.rss"},
]


def _minutes_ago(struct_time) -> int:
    """Convert a feed's parsed time to 'minutes ago'."""
    if not struct_time:
        return -1
    try:
        published = datetime.fromtimestamp(time.mktime(struct_time), tz=timezone.utc)
        delta = datetime.now(timezone.utc) - published
        return max(0, int(delta.total_seconds() / 60))
    except Exception:
        return -1


def _fetch_feed(feed: dict) -> list:
    """Fetch and parse one RSS feed. Returns [] on any failure (never raises)."""
    try:
        resp = requests.get(feed["url"], headers=_HEADERS, timeout=8)
        parsed = feedparser.parse(resp.content)
        items = []
        for e in parsed.entries:
            title = (e.get("title") or "").strip()
            link  = (e.get("link") or "").strip()
            if not title or not link:
                continue
            mins = _minutes_ago(e.get("published_parsed") or e.get("updated_parsed"))
            desc = (e.get("summary") or "").strip()
            # strip HTML tags crudely from summary
            if "<" in desc:
                import re
                desc = re.sub(r"<[^>]+>", "", desc)
            items.append({
                "title":                 title,
                "description":           desc[:300],
                "url":                   link,
                "source":                feed["name"],
                "published_minutes_ago": mins,
                "via":                   "RSS",
            })
        return items
    except Exception:
        return []


def get_rss_market_news(limit: int = 25) -> list:
    """
    Aggregate near-real-time market news across all RSS feeds.
    Deduplicated by title, sorted newest-first.
    """
    all_items = []
    for feed in RSS_FEEDS:
        all_items.extend(_fetch_feed(feed))

    # Deduplicate by lowercased title
    seen, unique = set(), []
    for item in all_items:
        key = item["title"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    # Drop clearly-stale or bad-timestamp items (> 14 days old). Keep undated (-1).
    MAX_AGE = 14 * 24 * 60   # 14 days in minutes
    unique = [u for u in unique if u["published_minutes_ago"] <= MAX_AGE]

    # Sort by freshness (unknown times, -1, sink to the bottom)
    unique.sort(key=lambda x: x["published_minutes_ago"] if x["published_minutes_ago"] >= 0 else 9_999_999)
    return unique[:limit]


def get_rss_stock_news(company_name: str, ticker: str = "", limit: int = 20) -> list:
    """
    Filter the aggregated RSS feed for headlines mentioning a company.
    Matches on the company's key name words (e.g. 'Reliance', 'TCS', 'HDFC').
    """
    # Build match keywords from the company name + ticker
    base = company_name.lower()
    for suffix in (" limited", " ltd", " industries", " india", " corporation", " company"):
        base = base.replace(suffix, "")
    keywords = [w for w in base.split() if len(w) > 2]
    if ticker:
        keywords.append(ticker.replace(".NS", "").lower())

    market = get_rss_market_news(limit=120)
    matched = []
    for item in market:
        text = (item["title"] + " " + item["description"]).lower()
        if any(kw in text for kw in keywords):
            matched.append(item)

    return matched[:limit]


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Testing rss_news.py")
    print("=" * 60)

    print("\n1. Market news (RSS, near-real-time):")
    news = get_rss_market_news(limit=10)
    print(f"   Pulled {len(news)} headlines")
    for a in news[:6]:
        print(f"   [{a['published_minutes_ago']:>4}m] {a['source']:18s} {a['title'][:60]}")

    print("\n2. Reliance-specific RSS news:")
    rel = get_rss_stock_news("Reliance Industries", "RELIANCE.NS")
    print(f"   Found {len(rel)} Reliance headlines")
    for a in rel[:4]:
        print(f"   [{a['published_minutes_ago']:>4}m] {a['title'][:65]}")

    print("\n" + "=" * 60)
    print("rss_news.py test complete")
    print("=" * 60)
