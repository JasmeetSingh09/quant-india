"""
liquidity.py — can you actually buy it?

The scan rates 2,401 NSE stocks. A large part of that universe trades a few
lakh rupees a day, and some names sit in permanent circuit bands where almost
nothing changes hands. A STRONG BUY on one of those is arithmetically correct
and practically useless: the order that would express it cannot be filled at
anything like the quoted price, and any track record built on it is fiction.

This is the same class of error as scoring a company with negative equity as a
value stock — the number was right and the conclusion was not. So liquidity is
measured and reported alongside the signal rather than assumed.

Traded VALUE, not share count, is the measure. Ten lakh shares of a Rs 3 stock
is Rs 30 lakh of real interest; ten thousand shares of a Rs 3,000 stock is the
same. Volume alone would rank penny stocks as the most liquid names on the
exchange, which is exactly backwards.

Bhavcopy already stores daily volume from the exchange, so this costs one query
rather than a new data source.
"""

from statistics import median

# Rupee thresholds for a retail-sized order. These are deliberately modest —
# the question is not "could a fund trade this" but "could a person put a
# realistic amount in without moving the price against themselves".
FREELY_TRADEABLE = 5_00_00_000     # Rs 5 crore/day
TRADEABLE_SMALL  = 1_00_00_000     # Rs 1 crore/day
THIN             = 10_00_000       # Rs 10 lakh/day

_CACHE: dict = {}
_TTL = 6 * 3600


def _from_bhavcopy(ticker: str, days: int = 30):
    """Median daily traded value in rupees, from the exchange's own file."""
    try:
        from db import get_conn
        conn = get_conn()
        rows = conn.execute(
            "SELECT close, volume FROM bhavcopy_eod WHERE symbol = ? "
            "AND volume IS NOT NULL AND close IS NOT NULL "
            "ORDER BY day DESC LIMIT ?", (ticker.strip().upper(), int(days))).fetchall()
        conn.close()
        vals = [float(c) * float(v) for c, v in rows if c and v]
        return median(vals) if vals else None
    except Exception:
        return None


def _from_yahoo(ticker: str):
    """Fallback while bhavcopy history is still accumulating."""
    try:
        from data_fetcher import get_info
        info = get_info(ticker) or {}
        vol = info.get("averageVolume") or info.get("averageDailyVolume10Day")
        px = info.get("currentPrice") or info.get("previousClose")
        if vol and px:
            return float(vol) * float(px)
    except Exception:
        pass
    return None


def assess(ticker: str) -> dict:
    """
    How tradeable this stock actually is.

    Never raises and never guesses: when neither source can answer, the tier is
    "unknown" rather than a default that would quietly pass everything through.
    """
    import time
    key = ticker.strip().upper()
    hit = _CACHE.get(key)
    now = time.time()
    if hit and now - hit[0] < _TTL:
        return hit[1]

    value = _from_bhavcopy(key)
    source = "NSE bhavcopy"
    if value is None:
        value = _from_yahoo(key)
        source = "Yahoo average volume"

    if value is None:
        out = {"tier": "unknown", "tradeable": None, "daily_value": None,
               "source": None,
               "note": "No volume data — treat the signal with caution."}
    elif value >= FREELY_TRADEABLE:
        out = {"tier": "liquid", "tradeable": True, "daily_value": round(value),
               "source": source,
               "note": "Trades enough each day that a retail order will not move the price."}
    elif value >= TRADEABLE_SMALL:
        out = {"tier": "moderate", "tradeable": True, "daily_value": round(value),
               "source": source,
               "note": "Tradeable in modest size. A large order would move the price."}
    elif value >= THIN:
        out = {"tier": "thin", "tradeable": False, "daily_value": round(value),
               "source": source,
               "note": "Thinly traded. Getting in is easier than getting out — "
                       "exits are where illiquidity actually costs you."}
    else:
        out = {"tier": "illiquid", "tradeable": False, "daily_value": round(value),
               "source": source,
               "note": "Barely trades. A signal here is not something you could act on, "
                       "and any backtested return assumes a fill that would not happen."}

    if len(_CACHE) > 4000:
        _CACHE.clear()
    _CACHE[key] = (now, out)
    return out


def label(daily_value) -> str:
    """Short human form for a table cell: 'Rs 4.2 Cr/day'."""
    if daily_value is None:
        return "—"
    v = float(daily_value)
    if v >= 1e7:
        return f"Rs {v / 1e7:.1f} Cr/day"
    if v >= 1e5:
        return f"Rs {v / 1e5:.1f} L/day"
    return f"Rs {v:,.0f}/day"


def annotate(rows: list, ticker_key: str = "ticker") -> list:
    """
    Attach liquidity to a list of scan results.

    Deliberately annotates rather than filters. Silently dropping illiquid names
    would leave a user wondering where a stock went; showing it marked "barely
    trades" teaches them why it was never a real opportunity.
    """
    for r in rows or []:
        try:
            t = r.get(ticker_key)
            if not t:
                continue
            a = assess(t)
            r["liquidity"] = a["tier"]
            r["liquidity_note"] = a["note"]
            r["daily_value"] = a["daily_value"]
            r["daily_value_label"] = label(a["daily_value"])
            r["tradeable"] = a["tradeable"]
        except Exception:
            continue
    return rows
