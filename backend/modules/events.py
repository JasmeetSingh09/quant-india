"""
events.py — what has happened to this company recently.

The alpha model reads news as a sentiment score: one number between -1 and +1.
That is useful for ranking and useless for understanding, because it collapses
"reported strong results" and "faces a regulatory probe" into the same figure if
they happen to score alike.

This keeps the events themselves. It answers "what happened", not "is this good",
and it deliberately produces no score — the sentiment factor already has that
job, and a second number derived from the same headlines would be the same
opinion counted twice.

Earnings dates are included because they are the one genuinely forward-looking
fact available here. A stock two days from results carries a risk no factor
model captures: whatever the model thinks today, the picture may be different
on Thursday.
"""

from datetime import datetime, timedelta


def _upcoming_earnings(ticker: str):
    """Next reporting date, if the provider knows it."""
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
        if cal is None:
            return None
        dates = None
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date")
        elif hasattr(cal, "loc"):
            try:
                dates = cal.loc["Earnings Date"].tolist()
            except Exception:
                dates = None
        if not dates:
            return None
        if not isinstance(dates, (list, tuple)):
            dates = [dates]
        for d in dates:
            try:
                dt = d if isinstance(d, datetime) else datetime.fromisoformat(str(d)[:10])
                days = (dt.date() - datetime.now().date()).days
                if -7 <= days <= 60:
                    return {"date": dt.strftime("%Y-%m-%d"), "days_away": days}
            except Exception:
                continue
    except Exception:
        pass
    return None


def detect(ticker: str, days_back: int = 7) -> dict:
    """
    Recent events and any imminent earnings date.

    News volume is reported alongside the headlines because a jump in coverage is
    itself informative: a company in the news five times as often as usual has
    had something happen, whatever the tone of it.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return {"checked": False, "note": "No ticker given."}

    headlines, sentiment = [], None
    try:
        from data_fetcher import get_stock_news
        raw = get_stock_news(ticker, days_back=days_back) or []
        items = raw.get("articles") if isinstance(raw, dict) else raw
        for a in (items or [])[:8]:
            if not isinstance(a, dict):
                continue
            headlines.append({
                "title": a.get("title") or a.get("headline"),
                "source": a.get("source") or a.get("publisher"),
                "url": a.get("url") or a.get("link"),
                "published": a.get("published") or a.get("providerPublishTime"),
            })
    except Exception:
        headlines = []

    try:
        from sentiment_analyzer import analyze_ticker_sentiment
        s = analyze_ticker_sentiment(ticker, days_back=days_back)
        if isinstance(s, dict):
            sentiment = {"score": s.get("score"), "n_articles": s.get("n_articles")}
    except Exception:
        sentiment = None

    earnings = _upcoming_earnings(ticker)

    notes = []
    if earnings:
        d = earnings["days_away"]
        if d < 0:
            notes.append(f"Reported results {abs(d)} day(s) ago — the model's "
                         f"fundamentals may not reflect them yet.")
        elif d <= 7:
            notes.append(f"Reports results in {d} day(s). Whatever the model thinks "
                         f"today, the picture can change on the day.")
        else:
            notes.append(f"Next results in about {d} days.")
    if len(headlines) >= 6:
        notes.append(f"{len(headlines)} stories in the last {days_back} days — "
                     f"heavier coverage than a quiet week.")

    return {
        "ticker": ticker,
        "checked": True,
        "headlines": headlines,
        "n_headlines": len(headlines),
        "sentiment": sentiment,
        "earnings": earnings,
        "notes": notes,
        "summary": (notes[0] if notes else
                    ("No unusual news activity and no results due shortly."
                     if not headlines else
                     f"{len(headlines)} recent stories, nothing out of the ordinary.")),
        "this_is_not_a_signal": (
            "Context, not a recommendation. These are the events themselves rather "
            "than a score derived from them — the sentiment factor already scores "
            "the same headlines, and counting one opinion twice would not make it "
            "more reliable."),
    }
