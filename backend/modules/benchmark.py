"""
benchmark.py — what Nifty did over the same period, including when it won.

Every return figure in this app has been quoted on its own so far, which is the
most flattering way to present one and the least useful. Up 12% feels like skill
until you learn the index made 18% while you took more risk to get less. A
product that teaches has to say that part out loud; leaving it out is how retail
apps keep people happy and uninformed.

So this module exists to answer one question wherever a return is shown: did you
actually beat just buying the index? The answer is allowed to be no, and when it
is no we say so plainly rather than burying it.

Nifty 50 (^NSEI) is the reference because it is the benchmark Indian investors
are implicitly choosing against when they pick stocks themselves.
"""

from datetime import datetime, timedelta

BENCHMARK = "^NSEI"
BENCHMARK_NAME = "Nifty 50"

# One index, refetched at most every few hours. The comparison appears on
# several screens, and none of them justify a fresh download each time.
_CACHE: dict = {}
_TTL_SECONDS = 3 * 3600


def _series(days: int):
    """Daily closes for the index over the last `days` days, or None."""
    import time
    key = int(days)
    hit = _CACHE.get(key)
    now = time.time()
    if hit and now - hit[0] < _TTL_SECONDS:
        return hit[1]

    closes = None
    try:
        import yfinance as yf
        end = datetime.now()
        start = end - timedelta(days=int(days) + 10)
        df = yf.download(BENCHMARK, start=start.strftime("%Y-%m-%d"),
                         end=end.strftime("%Y-%m-%d"), progress=False,
                         auto_adjust=True)
        if df is not None and len(df) > 1:
            col = df["Close"]
            # yfinance returns a DataFrame for Close when given a list, a Series
            # when given one symbol — depends on version, so handle both.
            if hasattr(col, "columns"):
                col = col.iloc[:, 0]
            closes = col.dropna()
            if len(closes) < 2:
                closes = None
    except Exception:
        closes = None

    if closes is not None:
        _CACHE[key] = (now, closes)
    return closes


def index_return(days: int = 365) -> dict | None:
    """
    Nifty's total return over the last `days` days.

    Returns None rather than a zero when the data is unavailable — a missing
    benchmark must never render as "the index made 0%", which would turn every
    portfolio into a winner by accident.
    """
    closes = _series(days)
    if closes is None:
        return None
    try:
        first, last = float(closes.iloc[0]), float(closes.iloc[-1])
        if first <= 0:
            return None
        return {
            "benchmark": BENCHMARK_NAME,
            "return_pct": round((last / first - 1) * 100, 2),
            "from": str(closes.index[0])[:10],
            "to": str(closes.index[-1])[:10],
            "days": len(closes),
        }
    except Exception:
        return None


def compare(portfolio_return_pct: float, days: int = 365) -> dict | None:
    """
    Put a portfolio's return next to the index's over the same window.

    The verdict is deliberately blunt. "Behind the index" is the finding people
    most need and least want, so it gets stated in the same plain language as a
    win rather than softened into "broadly in line".
    """
    idx = index_return(days)
    if idx is None or portfolio_return_pct is None:
        return None

    diff = round(float(portfolio_return_pct) - idx["return_pct"], 2)
    if diff > 1:
        verdict, plain = "ahead", f"You beat {BENCHMARK_NAME} by {abs(diff):.1f} points."
    elif diff < -1:
        verdict, plain = "behind", (
            f"You are {abs(diff):.1f} points behind {BENCHMARK_NAME}. Simply buying "
            f"the index would have done better over this period, with less work "
            f"and less single-company risk.")
    else:
        verdict, plain = "matched", (
            f"You roughly matched {BENCHMARK_NAME} ({diff:+.1f} points). Picking "
            f"stocks took more risk than the index to arrive at the same place.")

    return {
        "benchmark": BENCHMARK_NAME,
        "benchmark_return_pct": idx["return_pct"],
        "portfolio_return_pct": round(float(portfolio_return_pct), 2),
        "difference_pct": diff,
        "verdict": verdict,
        "plain": plain,
        "period": f"{idx['from']} to {idx['to']}",
        "lesson": ("The index is the free alternative. Beating it is the only reason "
                   "to pick individual stocks at all — if you cannot, buying the "
                   "index is the rational choice, and knowing that is worth more "
                   "than a flattering number."),
    }


def annualised_since(start_date: str, portfolio_return_pct: float = None) -> dict | None:
    """Index return since a given date — used to benchmark a running simulation."""
    try:
        d0 = datetime.fromisoformat(str(start_date)[:10])
    except Exception:
        return None
    days = max(1, (datetime.now() - d0).days)
    if portfolio_return_pct is None:
        return index_return(days)
    return compare(portfolio_return_pct, days)
