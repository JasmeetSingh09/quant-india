"""
execution.py — what a paper trade would actually have cost.

The paper simulator credited you the full amount at the displayed price,
instantly, in whole rupees of stock, at any hour of any day. The historical
backtest already modelled brokerage, STT, stamp duty and slippage, so the two
halves of the same product disagreed about whether trading is free.

This closes that. It is deliberately a model rather than a market: there is no
order book behind it and no bid/ask feed available for NSE at this tier, so what
it does is charge the costs that are knowable and estimate the one that is not,
saying which is which.

Slippage is the estimated part. It scales with how large the order is against
the stock's own daily traded value, because that is what actually determines
whether an order moves the price — a lakh in Reliance is nothing and a lakh in a
stock that trades three lakh a day is most of the day's volume.
"""

from datetime import datetime, time as _time, timedelta, timezone

# NSE trades in IST. The server does not: Render runs UTC, so datetime.now()
# there is five and a half hours behind the exchange. Checking market hours
# against the host clock meant "open" spanned 14:45-21:00 IST — closed all
# morning and open all evening, exactly inverted for most of a trading day.
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    """Current time in IST regardless of where this process runs."""
    return datetime.now(timezone.utc).astimezone(IST)

# Statutory and broker charges on a delivery buy, as fractions of turnover.
# These are knowable, not estimated: they are published rates.
BROKERAGE_PCT   = 0.0003     # discount broker delivery, often zero — kept small and non-zero
STT_PCT         = 0.001      # securities transaction tax, delivery buy
STAMP_DUTY_PCT  = 0.00015    # 0.015%, buy side only
EXCHANGE_PCT    = 0.0000345  # NSE transaction charge
GST_ON_CHARGES  = 0.18       # on brokerage + exchange charges
SEBI_PCT        = 0.000001

# NSE continuous trading, IST.
MARKET_OPEN  = _time(9, 15)
MARKET_CLOSE = _time(15, 30)


def market_status(now: datetime = None) -> dict:
    """
    Whether the exchange is open, in plain terms.

    The simulator had no concept of market hours, so a trade could be "executed"
    at 2am on a Sunday against Friday's closing price and presented as though it
    had happened. It still books the trade — this is a learning tool and refusing
    the click teaches nothing — but it now says the fill is at the last close
    rather than pretending it was live.
    """
    now = now or now_ist()
    is_weekday = now.weekday() < 5
    in_hours = MARKET_OPEN <= now.time() <= MARKET_CLOSE
    open_now = bool(is_weekday and in_hours)
    if open_now:
        note = "Market open. Filled at the latest available price."
    elif is_weekday:
        note = ("Market closed for the day. Filled at the last close — a real order "
                "placed now would queue for the next session and could open at a "
                "different price.")
    else:
        note = ("Weekend. Filled at the last close. A real order would wait for "
                "Monday, and weekend news moves the opening price.")
    return {"open": open_now, "as_of": now.strftime("%Y-%m-%d %H:%M IST"), "note": note}


def estimate_slippage_pct(ticker: str, amount: float) -> dict:
    """
    Estimated price impact, as a fraction of the order.

    Uses the stock's median daily traded value from bhavcopy. An order that is a
    rounding error against daily turnover pays almost nothing; one that is a
    meaningful share of it pays real money, and one that exceeds a day's trading
    could not be filled at anything like the quoted price at all.

    Returned as an estimate and labelled as one. Without an order book this
    cannot be exact, and presenting it to three decimals would be false
    precision.
    """
    try:
        from liquidity import assess
        a = assess(ticker) or {}
        dv = a.get("daily_value")
    except Exception:
        dv = None

    if not dv or dv <= 0 or not amount or amount <= 0:
        return {"slippage_pct": 0.0005, "participation_pct": None, "basis": "default",
                "note": "No volume data — a nominal 5 bps is assumed."}

    participation = float(amount) / float(dv)
    # Square-root impact: a standard, deliberately simple market-impact shape.
    # Doubling the order roughly multiplies impact by 1.4, not by 2.
    slippage = 0.0005 + 0.01 * (participation ** 0.5)
    slippage = min(slippage, 0.05)     # cap the model rather than extrapolate wildly

    if participation > 1:
        note = (f"This order is {participation:.1f}x the stock's entire daily traded "
                f"value. In reality it could not be filled near this price at all.")
    elif participation > 0.1:
        note = (f"This order is {participation*100:.0f}% of a typical day's trading "
                f"in this stock. Expect to move the price against yourself.")
    else:
        note = "Order is small against daily turnover, so impact should be minor."

    return {"slippage_pct": round(slippage, 5),
            "participation_pct": round(participation * 100, 2),
            "basis": "median daily traded value (NSE bhavcopy)",
            "note": note}


def cost_breakdown(ticker: str, amount: float, side: str = "buy") -> dict:
    """
    Every charge on this trade, itemised, plus the estimated impact.

    Itemised on purpose. A single "costs: ₹247" figure is easy to ignore; seeing
    that STT alone is ₹100 on a ₹1 lakh trade is what makes the number stick, and
    the point of a teaching simulator is that it sticks.
    """
    amount = float(amount or 0)
    if amount <= 0:
        return {"error": "Amount must be positive."}

    brokerage = amount * BROKERAGE_PCT
    exch      = amount * EXCHANGE_PCT
    gst       = (brokerage + exch) * GST_ON_CHARGES
    stt       = amount * STT_PCT
    stamp     = amount * STAMP_DUTY_PCT if side == "buy" else 0.0
    sebi      = amount * SEBI_PCT

    slip_info = estimate_slippage_pct(ticker, amount)
    slippage  = amount * slip_info["slippage_pct"]

    charges = brokerage + exch + gst + stt + stamp + sebi
    total   = charges + slippage

    return {
        "amount": round(amount, 2),
        "side": side,
        "charges": {
            "brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "stamp_duty": round(stamp, 2),
            "exchange": round(exch, 2),
            "gst": round(gst, 2),
            "sebi": round(sebi, 2),
        },
        "statutory_total": round(charges, 2),
        "estimated_slippage": round(slippage, 2),
        "slippage_detail": slip_info,
        "total_cost": round(total, 2),
        "total_cost_pct": round(total / amount * 100, 3),
        "invested_after_costs": round(amount - total, 2),
        "note": ("Charges are published rates and are exact. Slippage is an "
                 "estimate from the stock's daily traded value — there is no "
                 "order book here, so it cannot be."),
    }


def units_for(amount_after_costs: float, price: float, allow_fractional: bool = False) -> dict:
    """
    How many shares that actually buys.

    NSE trades whole shares. The simulator divided rupees by price and kept the
    fraction, which quietly assumes a market that does not exist and makes every
    allocation land exactly on target — a small dishonesty that removes the real
    friction of not being able to buy 3.7 shares.
    """
    if not price or price <= 0:
        return {"error": "Invalid price."}
    raw = float(amount_after_costs) / float(price)
    if allow_fractional:
        return {"units": raw, "leftover_cash": 0.0, "fractional": True}
    whole = int(raw)
    return {
        "units": whole,
        "leftover_cash": round(float(amount_after_costs) - whole * float(price), 2),
        "fractional": False,
        "note": ("NSE trades whole shares. The remainder stays as uninvested cash, "
                 "which is what happens in a real account."),
    }
