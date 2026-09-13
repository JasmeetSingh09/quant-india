"""
statement_factors.py — quality, value and growth rebuilt from annual statements.

For factor test 2 (docs/PREREG_FACTOR_TEST2_2026-09-13.md). Each function copies
the live factor as closely as annual statements allow, and says where it cannot:

  quality  alpha_model._compute_quality_factor and metrics.piotroski_score
  value    alpha_model._compute_value_factor, on the model's own market fallback
  growth   alpha_v2._growth_factor, fiscal year over fiscal year

A statement is a dict {field name as Yahoo labels it: value} for one fiscal
year. Nothing here fetches anything, so the arithmetic can be pinned by tests
(backend/tests/statement_factors_test.py) before any result exists.
"""

import calendar
import math
from datetime import date, timedelta

# SEBI's deadline for annual results. A fiscal year is treated as public from
# the first month-end at least this many days after it closes.
FILING_LAG_DAYS = 60

# The live model's constants, copied rather than imported so this runs without
# the app.
ROE_MEAN, ROE_STD = 0.12, 0.08
FCF_MEAN, FCF_STD = 0.035, 0.04
PE_MEAN, PE_STD = 22.0, 8.0
PB_MEAN, PB_STD = 3.2, 1.5
GROWTH_REVENUE_DIVISOR = 0.30
GROWTH_EARNINGS_DIVISOR = 0.50


def _day(s):
    return date.fromisoformat(str(s)[:10])


def _month_end(d):
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _get(statement, field):
    v = (statement or {}).get(field)
    return float(v) if isinstance(v, (int, float)) and v == v else None


def available_from(period_end: str) -> str:
    """The first month-end at which this fiscal year's statements were public."""
    return _month_end(_day(period_end) + timedelta(days=FILING_LAG_DAYS)).isoformat()


def usable_period(periods, formation: str):
    """The latest fiscal year already public at `formation`, or None."""
    f = _day(formation)
    public = [p for p in periods if _day(available_from(p)) <= f]
    return max(public, key=_day) if public else None


def piotroski_proxy(cur: dict, prev: dict = None) -> int:
    """
    The nine signals metrics.piotroski_score awards, from statements.

    F4 (cash flow beats ROA) and F5 (low leverage) are always 0: the live code
    reads total assets and shareholders' equity only from Yahoo's summary, which
    never carries them for NSE stocks, so it never awards either point. F7 (no
    dilution) is always 1, as it is live. Rebuilding F4 and F5 from the balance
    sheet would test a different score from the one the app gives.
    """
    ni, ta = _get(cur, "Net Income"), _get(cur, "Total Assets")
    roa = (ni / ta) if (ni is not None and ta) else 0.0
    cfo = _get(cur, "Operating Cash Flow") or 0.0
    ca, cl = _get(cur, "Current Assets"), _get(cur, "Current Liabilities")
    current_ratio = (ca / cl) if (ca is not None and cl) else 0.0
    rev, gp = _get(cur, "Total Revenue"), _get(cur, "Gross Profit")
    gross_margin = (gp / rev) if (gp is not None and rev) else 0.0
    prev_rev = _get(prev, "Total Revenue")
    revenue_growth = (rev / prev_rev - 1) if (rev is not None and prev_rev) else 0.0
    return ((1 if roa > 0 else 0)
            + (1 if cfo > 0 else 0)
            + (1 if roa > 0.05 else 0)
            + 0                                 # F4: never awarded live
            + 0                                 # F5: never awarded live
            + (1 if current_ratio > 1.0 else 0)
            + 1                                 # F7: fixed live
            + (1 if gross_margin > 0.20 else 0)
            + (1 if revenue_growth > 0 else 0))


def quality_score(cur: dict, prev: dict, price: float):
    """Live quality composite, or None when there is no statement to score."""
    if not cur:
        return None
    ni, equity = _get(cur, "Net Income"), _get(cur, "Stockholders Equity")
    roe = (ni / equity) if (ni is not None and equity) else None
    ocf, capex = _get(cur, "Operating Cash Flow"), _get(cur, "Capital Expenditure")
    shares = _get(cur, "Ordinary Shares Number")
    market_value = (price * shares) if (price and shares) else None
    fcf = (ocf + (capex or 0.0)) if ocf is not None else None     # capex is negative
    fcf_yield = (fcf / market_value) if (fcf is not None and market_value) else None

    parts, wsum = [(0.4, piotroski_proxy(cur, prev) / 9)], 0.4
    if roe is not None:
        parts.append((0.4, ((roe - ROE_MEAN) / ROE_STD) / 3)); wsum += 0.4
    if fcf_yield is not None:
        parts.append((0.2, ((fcf_yield - FCF_MEAN) / FCF_STD) / 3)); wsum += 0.2
    raw = sum(w * v for w, v in parts) / wsum

    penalty, flagged = 0.0, False
    if equity is not None and equity < 0:
        penalty += 0.5; flagged = True
    op_income, interest = _get(cur, "Operating Income"), _get(cur, "Interest Expense")
    cover = (op_income / abs(interest)) if (op_income is not None and interest) else None
    if cover is not None and cover < 1.5:
        penalty += 0.25; flagged = True
    if ni is not None and ni < 0:
        penalty += 0.25; flagged = True
    if ocf is not None and ocf < 0:
        penalty += 0.25; flagged = True
    if flagged:
        raw = min(raw, 0.0) - penalty
    return math.tanh(raw)


def value_score(cur: dict, price: float):
    """Live value composite on the market fallback; None when nothing can be valued."""
    eps, equity = _get(cur, "Diluted EPS"), _get(cur, "Stockholders Equity")
    shares = _get(cur, "Ordinary Shares Number")
    pe = (price / eps) if (price and eps) else None
    book_per_share = (equity / shares) if (equity is not None and shares) else None
    pb = (price / book_per_share) if (price and book_per_share) else None
    distressed = False
    if pe is not None and pe <= 0:
        pe, distressed = None, True
    if pb is not None and pb <= 0:
        pb, distressed = None, True
    if pe is None and pb is None:
        return -0.5 if distressed else None
    pe_z = ((pe if pe is not None else PE_MEAN) - PE_MEAN) / PE_STD
    pb_z = ((pb if pb is not None else PB_MEAN) - PB_MEAN) / PB_STD
    return math.tanh((-0.6 * pe_z - 0.4 * pb_z) / 2)


def growth_score(cur: dict, prev: dict):
    """Mean of the revenue and earnings growth legs that can be computed; None if neither."""
    if not prev:
        return None
    rev, prev_rev = _get(cur, "Total Revenue"), _get(prev, "Total Revenue")
    ni, prev_ni = _get(cur, "Net Income"), _get(prev, "Net Income")
    legs = []
    if rev is not None and prev_rev is not None and prev_rev > 0:
        legs.append(math.tanh((rev / prev_rev - 1) / GROWTH_REVENUE_DIVISOR))
    if ni is not None and prev_ni is not None and prev_ni > 0:
        legs.append(math.tanh((ni / prev_ni - 1) / GROWTH_EARNINGS_DIVISOR))
    return sum(legs) / len(legs) if legs else None
