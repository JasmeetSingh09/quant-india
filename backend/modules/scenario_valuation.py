"""
scenario_valuation.py — bull, base and bear, with the assumptions on the page.

This is arithmetic, not a forecast. Given an earnings growth rate and an exit
multiple, there is exactly one implied value, and this computes it. The reason
to show three of them is that the honest answer to "what is this worth" is a
range whose width comes from assumptions the user can see and change.

    EPS today   = price / P/E
    EPS in N yrs = EPS today x (1 + g)^N
    value       = EPS in N yrs x exit multiple

Every number in that chain is either observed (price, P/E) or an assumption the
user set. Nothing is fitted, so nothing can be overfitted.

Where it refuses to answer
--------------------------
A company with negative earnings has no meaningful P/E, and dividing by one
produces a number that looks like a valuation and means nothing. The same
applies when the multiple or the price is missing. In those cases this returns
`available: False` with the specific field that was missing, rather than
substituting a zero and carrying it through three scenarios.

That refusal is the feature. Loss-making companies are exactly where a
confident-looking valuation does the most damage.
"""

import math
from datetime import datetime


# Multipliers applied to the BASE case to build the other two. Stated here so a
# reader can see the spread is a convention rather than a measurement — nothing
# in the data says a bull case is 1.25x the base multiple.
BULL = {"growth_add_pct": 8.0, "multiple_mult": 1.25}
BEAR = {"growth_add_pct": -8.0, "multiple_mult": 0.75}

# Compounding an annual growth rate for many years is where this kind of model
# stops being arithmetic and starts being fiction. Five years is already a long
# way out for an Indian mid-cap.
MAX_YEARS = 10
# Nobody's earnings compound at 80% for five years. Clamping is honest as long
# as the clamp is disclosed, which it is in the output.
GROWTH_CLAMP_PCT = 40.0


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def scenarios(ticker: str, years: int = 3,
              base_growth_pct: float = None,
              base_multiple: float = None,
              bull_growth_pct: float = None, bull_multiple: float = None,
              bear_growth_pct: float = None, bear_multiple: float = None) -> dict:
    """
    Three scenarios from explicit assumptions, or an explicit refusal.

    Any assumption left as None is derived from the stock's own current data
    and reported back, so the caller can see what it was given before changing
    it.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return {"available": False, "reason": "No ticker supplied."}
    try:
        years = int(years)
    except Exception:
        return {"available": False, "reason": "Years must be a whole number."}
    if not 1 <= years <= MAX_YEARS:
        return {"available": False,
                "reason": f"Horizon must be between 1 and {MAX_YEARS} years."}

    missing = []
    try:
        from metrics import get_full_metrics
        m = get_full_metrics(ticker) or {}
    except Exception as e:
        return {"available": False,
                "reason": f"Could not load fundamentals ({type(e).__name__})."}
    if not m or "error" in m:
        return {"available": False,
                "reason": f"No fundamentals available for {ticker}."}

    try:
        from data_fetcher import get_current_price
        price = (get_current_price(ticker) or {}).get("price")
    except Exception:
        price = None
    try:
        price = None if price is None else float(price)
    except (TypeError, ValueError):
        price = None
    if not price or not math.isfinite(price) or price <= 0:
        missing.append("current price")

    # A negative or absent P/E means negative or unknown earnings. EPS derived
    # from it would be negative, and compounding a negative EPS at a growth rate
    # produces a confident-looking number with no meaning behind it.
    #
    # The type check is not paranoia: an upstream field arriving as a string
    # crashed this with a TypeError instead of refusing, which turns a data
    # problem into a broken page.
    pe = m.get("pe_ratio")
    try:
        pe = None if pe is None else float(pe)
    except (TypeError, ValueError):
        pe = None
    if pe is None or not math.isfinite(pe) or pe <= 0:
        missing.append("a positive P/E (the company's earnings are negative or unreported)")

    if missing:
        return {
            "available": False,
            "ticker": ticker,
            "missing": missing,
            "reason": (f"Scenario unavailable — required data missing: "
                       f"{'; '.join(missing)}."),
            "why_it_matters": (
                "A company with negative earnings has no meaningful price/"
                "earnings multiple. Substituting zero or an average would "
                "produce three scenarios that look precise and mean nothing, "
                "which is worse than showing nothing at all."),
        }

    # Derive EPS from the ROUNDED price and P/E, because those are the two
    # numbers the page displays. Computing it from the unrounded pair left a
    # reader who divides the two figures in front of them with a different
    # answer from the third figure in front of them — small (0.03 on TCS) but
    # it is the first arithmetic anyone checks, and every downstream scenario
    # value is built on this number.
    price = round(float(price), 2)
    pe = round(float(pe), 2)
    eps_now = round(price / pe, 2)

    # Defaults come from the stock's own numbers, and every one of them is
    # returned so the user can see what they are about to override.
    raw_growth = m.get("earnings_growth")
    if raw_growth is None:
        raw_growth = m.get("revenue_growth")
    try:
        derived_growth = (float(raw_growth) * 100.0) if raw_growth is not None else 8.0
        if not math.isfinite(derived_growth):
            derived_growth = 8.0
    except (TypeError, ValueError):
        derived_growth = 8.0
    growth_source = ("reported earnings growth" if m.get("earnings_growth") is not None
                     else "reported revenue growth" if m.get("revenue_growth") is not None
                     else "an 8% placeholder, because neither growth figure was reported")
    clamped = abs(derived_growth) > GROWTH_CLAMP_PCT
    derived_growth = _clamp(derived_growth, -GROWTH_CLAMP_PCT, GROWTH_CLAMP_PCT)

    b_growth = derived_growth if base_growth_pct is None else float(base_growth_pct)
    b_mult = float(pe) if base_multiple is None else float(base_multiple)

    def _case(name, g, mult):
        g = _clamp(float(g), -95.0, 200.0)
        # Round the multiple BEFORE using it, for the same reason the EPS is
        # rounded first: every number shown has to be the number used, or a
        # reader multiplying the two displayed figures gets a third answer.
        mult = round(max(0.1, float(mult)), 2)
        # Round EPS first, then value it. Computing the value from the
        # unrounded EPS meant a reader multiplying the two displayed numbers
        # got a different answer from the displayed value — small, but it is
        # exactly the reconciliation a careful user checks first.
        eps_end = round(eps_now * ((1 + g / 100.0) ** years), 2)
        value = eps_end * mult
        return {
            "scenario": name,
            "growth_pct": round(g, 2),
            "exit_multiple": round(mult, 2),
            "eps_now": eps_now,
            "eps_end": eps_end,
            "implied_value": round(value, 2),
            "change_pct": round((value / price - 1) * 100, 2),
            "annualised_pct": round(((value / price) ** (1 / years) - 1) * 100, 2),
        }

    cases = [
        _case("Bear",
              b_growth + BEAR["growth_add_pct"] if bear_growth_pct is None else bear_growth_pct,
              b_mult * BEAR["multiple_mult"] if bear_multiple is None else bear_multiple),
        _case("Base", b_growth, b_mult),
        _case("Bull",
              b_growth + BULL["growth_add_pct"] if bull_growth_pct is None else bull_growth_pct,
              b_mult * BULL["multiple_mult"] if bull_multiple is None else bull_multiple),
    ]

    by_name = {c["scenario"]: c for c in cases}
    # An invariant worth stating rather than assuming: with the default spread,
    # bull must exceed base must exceed bear. A user who sets their own
    # assumptions can legitimately break that, so it is reported rather than
    # enforced.
    ordered = (by_name["Bull"]["implied_value"] >= by_name["Base"]["implied_value"]
               >= by_name["Bear"]["implied_value"])

    return {
        "available": True,
        "ticker": ticker,
        "current_price": price,
        "current_pe": pe,
        "eps_now": eps_now,
        "years": years,
        "scenarios": cases,
        "assumptions_used": {
            "base_growth_pct": round(b_growth, 2),
            "base_multiple": round(b_mult, 2),
            "growth_source": growth_source,
            "growth_was_clamped": clamped,
            "spread": {"bull": BULL, "bear": BEAR},
        },
        "ordered": ordered,
        "order_note": (None if ordered else
                       "Your assumptions put the bull case below the base case. "
                       "That is arithmetic, not an error — you set a lower "
                       "growth rate or multiple for it."),
        "method": (f"EPS today is price / P/E = {price:.2f} / {pe:.2f} = "
                   f"{eps_now:.2f}. Each scenario compounds that at its growth "
                   f"rate for {years} years and applies its exit multiple. "
                   f"Nothing here is fitted to data, so nothing is optimised."),
        "not_a_forecast": (
            "Scenario estimate based on these assumptions, not a prediction. "
            "Change any assumption and the number changes with it — that is "
            "the point of showing three. The model has no view on which of "
            "them happens, and compounding any growth rate for several years "
            "is a strong assumption in itself."),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
