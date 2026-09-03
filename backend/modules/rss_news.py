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

import re
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


def _iso_from_struct(struct_time) -> str:
    """Convert a feed's parsed time to an ISO-8601 UTC string (or '' if missing).
    Downstream consumers (alpha sentiment, news endpoint) expect this format."""
    if not struct_time:
        return ""
    try:
        dt = datetime.fromtimestamp(time.mktime(struct_time), tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


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
            st   = e.get("published_parsed") or e.get("updated_parsed")
            mins = _minutes_ago(st)
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
                "published_at":          _iso_from_struct(st),   # ISO date for downstream (sentiment etc.)
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


def _fetch_google_news(query: str, limit: int = 20) -> list:
    """Per-company news via Google News RSS search (India, English). Well-dated and
    far higher per-company coverage than filtering the general market feeds."""
    from urllib.parse import quote_plus
    url = (f"https://news.google.com/rss/search?q={quote_plus(query)}"
           f"&hl=en-IN&gl=IN&ceid=IN:en")
    items = _fetch_feed({"name": "Google News", "url": url})
    # Google News titles look like "Headline - Publisher"; surface the publisher.
    for it in items:
        if " - " in it["title"]:
            head, _, pub = it["title"].rpartition(" - ")
            if head and pub:
                it["title"] = head.strip()
                it["source"] = pub.strip()
    return items[:limit]


# Grammar words. These must never appear in a match phrase, and never identify
# a company on their own. "and" is here because the previous filter kept every
# token longer than two characters — so Adani Ports and ONGC, whose legal names
# contain "and", matched essentially every headline ever published.
_STOPWORDS = frozenset("""
and the for not new its has was are with with from you all can may will
""".split())

# Words that name an industry or a corporate group rather than a company.
# "bank" made every banking story a State Bank of India story; "coal" made
# Bharat Coking Coal into Coal India; "tata" is shared by six listed companies.
# A company whose name reduces entirely to these is matched on its full name or
# its ticker instead.
_SECTOR_TOKENS = frozenset("""
bank banks banking oil gas natural power steel motors motor auto autos coal
services service finance financial cement pharma pharmaceutical
pharmaceuticals chemicals chemical energy petroleum telecom textiles paper
sugar metals metal mining port ports zone special economic state national
international global group holdings enterprises products technologies
technology consumer retail housing insurance life capital investments
investment infrastructure projects construction engineering electric
electricals electronics foods food agro seeds fertilisers fertilizers labs
laboratories healthcare hospital hospitals hotels resorts media
entertainment communications networks systems solutions trading exports
imports overseas india indian bharat
tata adani bajaj birla aditya mahindra godrej reliance hero hindustan
""".split())

_GENERIC_TOKENS = _STOPWORDS | _SECTOR_TOKENS

# Legal-form words only. " india" is deliberately NOT stripped: it is part of
# the name in Coal India and Nestle India, and removing it turned the first into
# the commodity "coal" — which then matched every Bharat Coking Coal headline.
_LEGAL_SUFFIXES = (" limited", " ltd", " corporation", " company", " industries",
                   " plc", " inc")

# A single token shorter than this is too easy to hit by accident.
_MIN_TOKEN_LEN = 4
# How much of a phrase's final word must appear. "Sun Pharmaceutical" is filed
# under "Sun Pharma" by every Indian outlet, so an exact phrase match loses the
# company's own news.
_PHRASE_STEM = 6


def _clean_tokens(company_name: str) -> list:
    """The company name reduced to its words, legal form removed.

    Only legal-form words go. " india" stays: it is part of the name in Coal
    India and Nestle India, and stripping it turned the first into the commodity
    "coal" and left State Bank of India as the fragment "state bank of" — which
    was then used verbatim as a news search query.
    """
    base = " ".join(re.sub(r"[^a-z0-9& ]+", " ", (company_name or "").lower()).split())
    for suffix in _LEGAL_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
        base = base.replace(suffix + " ", " ")
    return [t for t in base.split() if t]


def _identity_terms(company_name: str, ticker: str):
    """
    How to recognise this company in a headline.

    Returns (words, phrase_patterns). A word matches on a whole-word boundary
    only. A phrase matches as a contiguous run whose final word may continue —
    so "sun pharmaceutical" also finds "Sun Pharma". Either is sufficient, but a
    sector word is never a word on its own: a company whose name is entirely
    generic is identified by its full name or its ticker, never by "bank".
    """
    tokens = _clean_tokens(company_name)
    while tokens and tokens[-1] in _STOPWORDS:
        tokens.pop()

    words = {w for w in tokens
             if len(w) >= _MIN_TOKEN_LEN and w not in _GENERIC_TOKENS}
    bare = re.sub(r"[^a-z0-9]", "", (ticker or "").replace(".NS", "").lower())
    if bare and bare not in _GENERIC_TOKENS and len(bare) >= 3:
        words.add(bare)

    # A company whose whole name is a group name has nothing else to be called.
    # Reliance Industries is "Reliance" everywhere, and blocking the group token
    # outright left it with no identifying term at all — 17 of its own articles
    # went unmatched. The block still holds for Reliance Power and Reliance
    # Infrastructure, which have a second token and so are matched on the phrase
    # "reliance power" instead. Only the company that IS the group name falls
    # back to it.
    if not words:
        words = {w for w in tokens if len(w) >= _MIN_TOKEN_LEN}

    candidates = []
    if len(tokens) >= 2:
        candidates.append(tokens)                       # the full name
        if not any(t in _STOPWORDS for t in tokens[:2]):
            candidates.append(tokens[:2])               # "adani ports", "coal india"
    patterns, seen_pat = [], set()
    for toks in candidates:
        if tuple(toks) in seen_pat:
            continue
        seen_pat.add(tuple(toks))
        stem = toks[-1][:_PHRASE_STEM] if len(toks[-1]) > _PHRASE_STEM else toks[-1]
        patterns.append(re.compile(
            r"\b" + r"\s+".join(re.escape(t) for t in toks[:-1] + [stem])
            + r"\w*\b"))
    return words, patterns


def _mentions(text: str, words, patterns) -> bool:
    """Whole-word / whole-phrase containment, never substring.

    Substring matching had ITC's ticker matching the word "switch". Padding with
    spaces makes every word test a boundary test without a regex per token.
    """
    t = " ".join(re.sub(r"[^a-z0-9& ]+", " ", (text or "").lower()).split())
    for pat in patterns:
        if pat.search(t):
            return True
    padded = f" {t} "
    for w in words:
        if f" {w} " in padded:
            return True
    return False


def get_rss_stock_news(company_name: str, ticker: str = "", limit: int = 20) -> list:
    """
    Company-specific news, combining:
      1) a Google News RSS search for the company (primary — good coverage + dates), and
      2) headlines from the general market feeds that actually name the company.
    Deduplicated by title, sorted newest-first.

    Step 2 used to admit any article containing any name token over two
    characters. Measured on the 2026-09-03 cycle, only 57% of the articles
    scored were about the company at all, and the median stock drew 85% of its
    sentiment weight from articles about someone else. Worse, the intruders were
    general market stories published that morning, so their time-decay weight
    was near 1.0 while genuine company news sat older and lighter: SBIN and ONGC
    each reported sentiment confidence 1.00 on zero relevant articles, while
    NESTLEIND, with 100% relevant articles, reported 0.0001. The model was
    most certain exactly where it knew least.
    """
    words, phrases = _identity_terms(company_name, ticker)
    # The query used to be built from a name with " india" cut out of it, which
    # asked Google News for "state bank of stock NSE" and got back nothing
    # usable. With step 2 correctly rejecting other companies' news, that left
    # SBIN with no articles at all rather than the wrong ones.
    base = " ".join(_clean_tokens(company_name))
    bare = ticker.replace(".NS", "").lower()

    combined = []

    # 1) Google News search for this company (primary)
    try:
        query = f"{base or bare} stock NSE"
        combined.extend(_fetch_google_news(query, limit=limit))
    except Exception:
        pass

    # 2) Company mentions in the general market feeds (secondary)
    try:
        market = get_rss_market_news(limit=120)
        for item in market:
            if _mentions(item.get("title", "") + " " + item.get("description", ""),
                         words, phrases):
                combined.append(item)
    except Exception:
        pass

    # Deduplicate by lowercased title, keep newest-first (undated -1 sinks to bottom)
    seen, unique = set(), []
    for item in combined:
        key = item["title"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    unique.sort(key=lambda x: x["published_minutes_ago"] if x.get("published_minutes_ago", -1) >= 0 else 9_999_999)

    return unique[:limit]


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
