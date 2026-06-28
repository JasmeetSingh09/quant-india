"""
calculators.py — Investment planning calculators (pure math, no external data).

  1. SIP calculator      — monthly investing future value
  2. Lumpsum calculator  — one-time investment growth
  3. Capital gains tax   — Indian equity STCG/LTCG (post-July-2024 budget rules)

All India-specific and self-contained, so they're fast and never depend on
flaky data feeds.
"""

# ── Indian equity capital-gains rules (post-July 2024 budget) ──
STCG_RATE      = 0.20      # short-term (held <= 12 months): 20%
LTCG_RATE      = 0.125     # long-term  (held >  12 months): 12.5%
LTCG_EXEMPTION = 125_000   # LTCG exemption: first ₹1.25 lakh of gains per year


def sip_calculator(monthly_investment: float, annual_return_pct: float,
                   years: float) -> dict:
    """
    Future value of a monthly SIP (contributions at the start of each month).

    FV = P * [((1+r)^n - 1) / r] * (1+r)     where r = monthly rate, n = months
    """
    try:
        P = float(monthly_investment); ar = float(annual_return_pct); yrs = float(years)
    except (TypeError, ValueError):
        return {"error": "all inputs must be numbers"}
    if P <= 0 or yrs <= 0:
        return {"error": "monthly_investment and years must be greater than 0"}

    n = int(round(yrs * 12))
    r = ar / 100 / 12
    invested = P * n
    if r == 0:
        fv = P * n                      # 0% return edge case
    else:
        fv = P * (((1 + r) ** n - 1) / r) * (1 + r)
    gains = fv - invested

    return {
        "monthly_investment": round(P, 2),
        "annual_return_pct":  round(ar, 2),
        "years":              yrs,
        "months":             n,
        "total_invested":     round(invested, 2),
        "future_value":       round(fv, 2),
        "estimated_gains":    round(gains, 2),
        "gain_multiple":      round(fv / invested, 2) if invested else 0,
        "interpretation": (
            f"Investing ₹{P:,.0f}/month for {yrs:g} years at {ar:g}% could grow to "
            f"₹{fv:,.0f} — you put in ₹{invested:,.0f} and gain ~₹{gains:,.0f}."
        ),
    }


def lumpsum_calculator(principal: float, annual_return_pct: float,
                       years: float) -> dict:
    """Future value of a one-time investment: FV = P*(1+r)^years."""
    try:
        P = float(principal); ar = float(annual_return_pct); yrs = float(years)
    except (TypeError, ValueError):
        return {"error": "all inputs must be numbers"}
    if P <= 0 or yrs <= 0:
        return {"error": "principal and years must be greater than 0"}

    fv = P * (1 + ar / 100) ** yrs
    return {
        "principal":         round(P, 2),
        "annual_return_pct": round(ar, 2),
        "years":             yrs,
        "future_value":      round(fv, 2),
        "estimated_gains":   round(fv - P, 2),
        "interpretation": (
            f"₹{P:,.0f} invested for {yrs:g} years at {ar:g}% could grow to ₹{fv:,.0f}."
        ),
    }


def capital_gains_tax(buy_price: float, sell_price: float, quantity: float,
                      holding_months: float) -> dict:
    """
    Indian equity capital-gains tax (post-July-2024 rules):
      - Short-term (held <= 12 months): 20% of the gain
      - Long-term  (held >  12 months): 12.5% of gains above ₹1.25 lakh/year
    Losses are not taxed.
    """
    try:
        buy = float(buy_price); sell = float(sell_price)
        qty = float(quantity);  hm = float(holding_months)
    except (TypeError, ValueError):
        return {"error": "all inputs must be numbers"}
    if buy <= 0 or sell <= 0 or qty <= 0:
        return {"error": "prices and quantity must be greater than 0"}

    invested = buy * qty
    proceeds = sell * qty
    gain     = proceeds - invested
    is_long  = hm > 12

    if gain <= 0:
        tax = 0.0
        taxable = 0.0
        note = "No tax — this is a capital loss (which you may be able to offset elsewhere)."
    elif is_long:
        taxable = max(0.0, gain - LTCG_EXEMPTION)
        tax = taxable * LTCG_RATE
        note = (f"Long-term (held {hm:g} months > 12). First ₹{LTCG_EXEMPTION:,.0f} of gains "
                f"is tax-free; {LTCG_RATE*100:g}% applies to the rest.")
    else:
        taxable = gain
        tax = taxable * STCG_RATE
        note = f"Short-term (held {hm:g} months ≤ 12). Taxed at {STCG_RATE*100:g}%."

    return {
        "term":            "long" if is_long else "short",
        "invested":        round(invested, 2),
        "proceeds":        round(proceeds, 2),
        "gain":            round(gain, 2),
        "taxable_gain":    round(taxable, 2),
        "tax":             round(tax, 2),
        "net_after_tax":   round(proceeds - tax, 2),
        "net_profit":      round(gain - tax, 2),
        "effective_rate_pct": round(tax / gain * 100, 2) if gain > 0 else 0.0,
        "note":            note,
    }


if __name__ == "__main__":
    print("=" * 55)
    print("Testing calculators.py")
    print("=" * 55)

    print("\n1. SIP — ₹5,000/mo, 12%, 10 yrs:")
    print("  ", sip_calculator(5000, 12, 10)["interpretation"])
    print("\n2. SIP edge — 0% return (should = invested):")
    s = sip_calculator(5000, 0, 10); print(f"   invested {s['total_invested']} == FV {s['future_value']}? {s['total_invested']==s['future_value']}")
    print("\n3. SIP bad input:", sip_calculator(-100, 12, 10).get("error"))

    print("\n4. Lumpsum — ₹1,00,000, 12%, 10 yrs:")
    print("  ", lumpsum_calculator(100000, 12, 10)["interpretation"])

    print("\n5. Tax — STCG (held 6 mo), big gain:")
    t = capital_gains_tax(100, 150, 1000, 6)
    print(f"   gain ₹{t['gain']:,} | {t['term']} | tax ₹{t['tax']:,} ({t['effective_rate_pct']}%)")
    print("\n6. Tax — LTCG (held 18 mo), gain ₹2L (₹1.25L exempt):")
    t = capital_gains_tax(100, 150, 4000, 18)
    print(f"   gain ₹{t['gain']:,} | taxable ₹{t['taxable_gain']:,} | tax ₹{t['tax']:,}")
    print("\n7. Tax — a LOSS (sell below buy):")
    t = capital_gains_tax(150, 100, 100, 6)
    print(f"   gain ₹{t['gain']:,} | tax ₹{t['tax']} | {t['note'][:40]}")
    print("\n8. Tax bad input:", capital_gains_tax(0, 100, 10, 6).get("error"))
    print("\nDone.")
