"""
tax.py — the return you keep, not the return you made.

Indian equity taxation is not a rounding error and it is not the same as the US
rules every foreign-built app assumes:

  Short-term (held under 12 months):  20% on the gain
  Long-term  (held 12 months or more): 12.5% on the gain above Rs 1.25 lakh
                                       of long-term gains in the financial year

So a portfolio up 18% after eleven months is really up about 14.4%, and holding
four more weeks can change the bill materially. Showing only the pre-tax number
teaches people to celebrate money they do not get to keep.

This computes the arithmetic and shows the boundary. It is not tax advice and
does not try to be: no set-off of losses across heads, no surcharge or cess
bands, no relief for a specific person's situation. Those depend on facts this
app does not have and should not ask for.
"""

from datetime import datetime, timedelta

STCG_RATE = 0.20            # under 12 months
LTCG_RATE = 0.125           # 12 months or more
LTCG_EXEMPTION = 1_25_000   # per financial year, on long-term gains
LONG_TERM_DAYS = 365


def _days_held(bought_on) -> int | None:
    try:
        d0 = datetime.fromisoformat(str(bought_on)[:10])
        return max(0, (datetime.now() - d0).days)
    except Exception:
        return None


def on_gain(gain: float, days_held: int, ltcg_used: float = 0.0) -> dict:
    """
    Tax on one realised gain.

    ltcg_used is long-term gain already realised this financial year, so the
    Rs 1.25 lakh exemption is not silently granted twice.
    """
    gain = float(gain or 0)
    if gain <= 0:
        return {"tax": 0.0, "rate": 0.0, "kind": "loss",
                "note": "A loss is not taxed. It can be set off against other "
                        "capital gains under rules this app does not model."}

    if days_held < LONG_TERM_DAYS:
        return {"tax": round(gain * STCG_RATE, 2), "rate": STCG_RATE,
                "kind": "short-term",
                "note": f"Held {days_held} days — under a year, so 20% applies."}

    remaining = max(0.0, LTCG_EXEMPTION - float(ltcg_used or 0))
    taxable = max(0.0, gain - remaining)
    return {"tax": round(taxable * LTCG_RATE, 2), "rate": LTCG_RATE,
            "kind": "long-term", "exempt_used": round(min(gain, remaining), 2),
            "note": (f"Held {days_held} days — over a year, so 12.5% applies, and "
                     f"the first Rs {remaining:,.0f} of long-term gain is exempt "
                     f"this financial year.")}


def after_tax(initial_value: float, current_value: float, bought_on=None,
              days_held: int = None) -> dict:
    """
    The headline number, honestly. Returns both figures side by side so the
    difference is visible rather than buried.
    """
    try:
        iv, cv = float(initial_value), float(current_value)
    except Exception:
        return {"error": "Values must be numbers."}
    if iv <= 0:
        return {"error": "Initial value must be positive."}

    d = days_held if days_held is not None else _days_held(bought_on)
    if d is None:
        return {"error": "Need a purchase date or holding period."}

    gain = cv - iv
    t = on_gain(gain, d)
    net_gain = gain - t["tax"]

    out = {
        "gross_return_pct": round((cv / iv - 1) * 100, 2),
        "net_return_pct": round((iv + net_gain) / iv * 100 - 100, 2),
        "gain": round(gain, 2),
        "tax": t["tax"],
        "net_gain": round(net_gain, 2),
        "kind": t["kind"],
        "rate_pct": round(t["rate"] * 100, 2),
        "days_held": d,
        "note": t["note"],
        "disclaimer": ("Indicative only. Ignores loss set-off, surcharge and cess, "
                       "and your other income. Not tax advice."),
    }

    # The decision this actually informs: is the boundary close enough to matter?
    if gain > 0 and d < LONG_TERM_DAYS:
        days_to_go = LONG_TERM_DAYS - d
        would_be = on_gain(gain, LONG_TERM_DAYS)
        saving = round(t["tax"] - would_be["tax"], 2)
        if saving > 0:
            out["long_term_in_days"] = days_to_go
            out["long_term_date"] = (datetime.now() + timedelta(days=days_to_go)).strftime("%Y-%m-%d")
            out["potential_saving"] = saving
            out["boundary_note"] = (
                f"Holding {days_to_go} more day(s) would move this from 20% to 12.5% "
                f"and save about Rs {saving:,.0f} at today's gain — "
                f"{'worth weighing' if days_to_go <= 60 else 'a long wait, and the price can move against you in that time'}.")
    return out


def portfolio_after_tax(positions: list) -> dict:
    """
    Whole-portfolio view. positions: [{ticker, invested, current_value,
    bought_on or days_held}].

    The exemption is applied once across all long-term gains rather than per
    position, which is how it actually works — applying it to each holding would
    understate the bill, and an app that flatters the number is worse than one
    that omits it.
    """
    if not positions:
        return {"error": "No positions."}

    gross_gain = 0.0
    st_gain = 0.0
    lt_gain = 0.0
    invested = 0.0
    for p in positions:
        try:
            iv = float(p.get("invested") or 0)
            cv = float(p.get("current_value") or 0)
            d = p.get("days_held")
            if d is None:
                d = _days_held(p.get("bought_on"))
            if d is None:
                continue
            g = cv - iv
            invested += iv
            gross_gain += g
            if g > 0:
                if d >= LONG_TERM_DAYS:
                    lt_gain += g
                else:
                    st_gain += g
        except Exception:
            continue

    if invested <= 0:
        return {"error": "No valid positions."}

    st_tax = st_gain * STCG_RATE
    lt_taxable = max(0.0, lt_gain - LTCG_EXEMPTION)
    lt_tax = lt_taxable * LTCG_RATE
    total_tax = st_tax + lt_tax
    net = gross_gain - total_tax

    return {
        "invested": round(invested, 2),
        "gross_gain": round(gross_gain, 2),
        "gross_return_pct": round(gross_gain / invested * 100, 2),
        "short_term_gain": round(st_gain, 2),
        "long_term_gain": round(lt_gain, 2),
        "exemption_applied": round(min(lt_gain, LTCG_EXEMPTION), 2),
        "short_term_tax": round(st_tax, 2),
        "long_term_tax": round(lt_tax, 2),
        "total_tax": round(total_tax, 2),
        "net_gain": round(net, 2),
        "net_return_pct": round(net / invested * 100, 2),
        "lesson": ("Short-term gains are taxed at 20% and long-term at 12.5%, so "
                   "the same profit is worth noticeably more when it is held past "
                   "a year. Trading frequently costs you tax as well as brokerage "
                   "— the tax bill is usually the larger of the two."),
        "disclaimer": ("Indicative only. Ignores loss set-off, surcharge and cess, "
                       "and your other income. Not tax advice."),
    }
