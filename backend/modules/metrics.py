"""
metrics.py — Financial metrics, peer comparison, DuPont analysis, and
Piotroski F-Score health scoring for NSE stocks.

All data sourced from yfinance.  Imports helper functions from data_fetcher.

Key functions:
  get_full_metrics(ticker)        -> comprehensive metric snapshot
  peer_comparison(ticker)         -> side-by-side with sector peers
  dupont_analysis(ticker)         -> ROE decomposed into 3 drivers
  piotroski_score(ticker)         -> 0-9 F-Score + health bucket
  financial_health_score(ticker)  -> 0-100 composite score
"""

import sys
import yfinance as yf
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))
from data_fetcher import (
    get_financial_metrics,
    get_sector_peers,
    get_company_info,
    format_large_number,
)


# ---------------------------------------------------------------------------
# Full metrics snapshot
# ---------------------------------------------------------------------------

_METRICS_CACHE: dict = {}     # ticker -> (timestamp, data)
_METRICS_TTL = 900            # 15 min — metrics barely move intraday


def get_full_metrics(ticker: str) -> dict:
    """
    Return a comprehensive financial metrics snapshot for an NSE ticker.

    Cached for 15 min. If yfinance is rate-limiting (returns empty data), serve
    the last good snapshot instead of a blank page — important for live demos.
    """
    import time
    now = time.time()
    cached = _METRICS_CACHE.get(ticker)
    if cached and now - cached[0] < _METRICS_TTL:
        return cached[1]
    try:
        data = _compute_full_metrics(ticker)
    except Exception:
        if cached:
            return cached[1]
        raise
    # only cache a genuinely populated snapshot; otherwise fall back to stale
    if data.get("pe_ratio") is not None or data.get("market_cap") is not None:
        _METRICS_CACHE[ticker] = (now, data)
        return data
    return cached[1] if cached else data


def _compute_full_metrics(ticker: str) -> dict:
    """
    Combines data_fetcher.get_financial_metrics with additional yfinance fields
    for a complete valuation, profitability, and balance-sheet view.
    """
    base = get_financial_metrics(ticker)
    info = get_company_info(ticker)

    try:
        raw = yf.Ticker(ticker).info
        # Yahoo omits pegRatio for many NSE names; data_fetcher computes a
        # P/E ÷ earnings-growth fallback, so prefer that when Yahoo has nothing.
        peg              = raw.get("pegRatio") or base.get("peg_ratio")
        quick_ratio      = raw.get("quickRatio")
        gross_margin     = raw.get("grossMargins")
        operating_margin = raw.get("operatingMargins")
        total_revenue    = raw.get("totalRevenue")
        ebitda           = raw.get("ebitda")
        total_debt       = raw.get("totalDebt")
        cash             = raw.get("totalCash")
        beta             = raw.get("beta")
        book_value       = raw.get("bookValue")
    except Exception:
        peg = quick_ratio = gross_margin = operating_margin = None
        total_revenue = ebitda = total_debt = cash = beta = book_value = None

    return {
        "ticker":             ticker,
        "company_name":       info.get("name"),
        "sector":             info.get("sector"),
        "industry":           info.get("industry"),
        "market_cap":         info.get("market_cap"),
        "market_cap_fmt":     format_large_number(info.get("market_cap")),
        # Valuation
        "pe_ratio":           base.get("pe_ratio"),
        "forward_pe":         base.get("forward_pe"),
        "peg_ratio":          peg,
        "ev_ebitda":          base.get("ev_ebitda"),
        "enterprise_value":   base.get("enterprise_value"),
        "enterprise_value_fmt": format_large_number(base.get("enterprise_value")),
        "price_to_book":      base.get("price_to_book"),
        "price_to_sales":     base.get("price_to_sales"),
        # Profitability
        "roe":                base.get("roe"),
        "roa":                base.get("roa"),
        "gross_margin":       gross_margin,
        "operating_margin":   operating_margin,
        "profit_margin":      base.get("profit_margin"),
        # Growth
        "revenue_growth":     base.get("revenue_growth"),
        "earnings_growth":    base.get("earnings_growth"),
        # Balance sheet
        "debt_to_equity":     base.get("debt_to_equity"),
        "current_ratio":      base.get("current_ratio"),
        "quick_ratio":        quick_ratio,
        "total_revenue":      total_revenue,
        "total_revenue_fmt":  format_large_number(total_revenue),
        "ebitda":             base.get("ebitda"),
        "ebitda_fmt":         format_large_number(base.get("ebitda")),
        "total_debt":         total_debt,
        "total_debt_fmt":     format_large_number(total_debt),
        "cash":               cash,
        "cash_fmt":           format_large_number(cash),
        "free_cashflow":      base.get("free_cashflow"),
        "free_cashflow_fmt":  format_large_number(base.get("free_cashflow")),
        # Market data
        "dividend_yield":     base.get("dividend_yield"),
        "beta":               beta,
        "week_52_high":       base.get("week_52_high"),
        "week_52_low":        base.get("week_52_low"),
        "book_value":         book_value,
        # Company profile
        "description":        info.get("description", ""),
        "website":            info.get("website", ""),
        "employees":          info.get("employees", None),
        "as_of":              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Peer comparison
# ---------------------------------------------------------------------------

def peer_comparison(ticker: str, peers: list = None) -> dict:
    """
    Compare key metrics of ticker against its sector peers.

    peers: optional list of tickers; if None, uses get_sector_peers().

    Returns:
      target  — slim metric dict for the given ticker
      peers   — list of peer metric dicts
      ranking — rank of target on key metrics vs peers
    """
    if peers is None:
        peers = get_sector_peers(ticker)

    def _slim(t: str) -> dict:
        try:
            raw = yf.Ticker(t).info
            de = raw.get("debtToEquity")
            ev = raw.get("enterpriseToEbitda")
            return {
                "ticker":        t,
                "name":          raw.get("shortName", t),
                "pe_ratio":      raw.get("trailingPE"),
                "ev_ebitda":     ev if (ev is not None and 0 < ev <= 100) else None,
                "roe":           raw.get("returnOnEquity"),
                "profit_margin": raw.get("profitMargins"),
                "revenue_growth":raw.get("revenueGrowth"),
                "debt_to_equity":round(de / 100, 2) if de is not None else None,
                "market_cap":    raw.get("marketCap"),
                "market_cap_fmt":format_large_number(raw.get("marketCap")),
            }
        except Exception:
            return {"ticker": t, "error": "fetch failed"}

    target_metrics = _slim(ticker)
    peer_metrics   = [_slim(p) for p in peers]
    all_metrics    = [target_metrics] + peer_metrics

    # Rank target vs peers (lower PE is better; higher everything else is better)
    ranking = {}
    for field, lower_is_better in [
        ("pe_ratio", True),
        ("roe", False),
        ("profit_margin", False),
        ("revenue_growth", False),
    ]:
        values = [
            (m["ticker"], m[field])
            for m in all_metrics
            if m.get(field) is not None
        ]
        if not values:
            continue
        ranked = sorted(values, key=lambda x: x[1], reverse=not lower_is_better)
        rank   = next((i + 1 for i, (t, _) in enumerate(ranked) if t == ticker), None)
        ranking[field] = {"rank": rank, "out_of": len(ranked)}

    return {
        "target":  target_metrics,
        "peers":   peer_metrics,
        "ranking": ranking,
    }


# ---------------------------------------------------------------------------
# DuPont analysis
# ---------------------------------------------------------------------------

def dupont_analysis(ticker: str) -> dict:
    """
    Decompose ROE using the 3-step DuPont formula:
      ROE = Net Profit Margin x Asset Turnover x Equity Multiplier

    Each component is returned with an interpretation label.
    """
    try:
        raw = yf.Ticker(ticker).info

        net_profit_margin = raw.get("profitMargins")
        total_assets      = raw.get("totalAssets")
        total_revenue     = raw.get("totalRevenue")
        book_value        = raw.get("bookValue", 1) or 1
        shares_out        = raw.get("sharesOutstanding", 1) or 1
        total_equity      = book_value * shares_out
        roe_reported      = raw.get("returnOnEquity")

        asset_turnover = (
            round(total_revenue / total_assets, 4)
            if total_revenue and total_assets else None
        )
        equity_multiplier = (
            round(total_assets / total_equity, 4)
            if total_assets and total_equity else None
        )
        dupont_roe = (
            round(net_profit_margin * asset_turnover * equity_multiplier, 4)
            if net_profit_margin and asset_turnover and equity_multiplier else None
        )

        def _margin_label(m):
            if m is None: return "N/A"
            if m > 0.20:  return "Strong (>20%)"
            if m > 0.10:  return "Average (10-20%)"
            return "Weak (<10%)"

        def _turnover_label(t):
            if t is None: return "N/A"
            if t > 1.0:   return "Efficient (>1x)"
            if t > 0.5:   return "Moderate (0.5-1x)"
            return "Asset-heavy (<0.5x)"

        def _leverage_label(l):
            if l is None: return "N/A"
            if l > 3.0:   return "High leverage — elevated risk"
            if l > 1.5:   return "Moderate leverage"
            return "Conservative (<1.5x)"

        return {
            "ticker":            ticker,
            "formula":           "ROE = Net Profit Margin x Asset Turnover x Equity Multiplier",
            "roe_reported":      roe_reported,
            "roe_dupont":        dupont_roe,
            "net_profit_margin": net_profit_margin,
            "asset_turnover":    asset_turnover,
            "equity_multiplier": equity_multiplier,
            "interpretation": {
                "margin":   _margin_label(net_profit_margin),
                "turnover": _turnover_label(asset_turnover),
                "leverage": _leverage_label(equity_multiplier),
            },
        }

    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


# ---------------------------------------------------------------------------
# Piotroski F-Score
# ---------------------------------------------------------------------------

def piotroski_score(ticker: str) -> dict:
    """
    Calculate Piotroski F-Score (0-9) using 9 binary signals across:
      Profitability (4), Leverage & Liquidity (3), Operating Efficiency (2).

    Uses available yfinance data as proxies where exact year-over-year
    statements are not provided.
    """
    try:
        info = yf.Ticker(ticker).info

        roa           = info.get("returnOnAssets", 0) or 0
        cfo           = info.get("operatingCashflow", 0) or 0
        total_assets  = info.get("totalAssets", 1) or 1
        long_term_debt= info.get("longTermDebt", 0) or 0
        total_equity  = info.get("totalStockholderEquity", 1) or 1
        current_ratio = info.get("currentRatio", 0) or 0
        gross_margin  = info.get("grossMargins", 0) or 0
        revenue_growth= info.get("revenueGrowth", 0) or 0

        # Profitability
        f1_roa_positive   = 1 if roa > 0 else 0
        f2_cfo_positive   = 1 if cfo > 0 else 0
        f3_roa_strong     = 1 if roa > 0.05 else 0      # proxy: ROA > 5 %
        f4_cfo_beats_roa  = 1 if (cfo / total_assets) > roa else 0

        # Leverage & Liquidity
        leverage_ratio    = long_term_debt / total_equity if total_equity else 0
        f5_low_leverage   = 1 if leverage_ratio < 0.5 else 0
        f6_good_liquidity = 1 if current_ratio > 1.0 else 0
        # Share dilution proxy: we assume no dilution (yfinance lacks prior-year share count easily)
        f7_no_dilution    = 1

        # Operating Efficiency
        f8_high_margin    = 1 if gross_margin > 0.20 else 0
        f9_revenue_growth = 1 if revenue_growth > 0 else 0

        signals = {
            "roa_positive":        f1_roa_positive,
            "cfo_positive":        f2_cfo_positive,
            "roa_above_5pct":      f3_roa_strong,
            "cfo_beats_roa":       f4_cfo_beats_roa,
            "low_leverage":        f5_low_leverage,
            "current_ratio_above_1":f6_good_liquidity,
            "no_dilution":         f7_no_dilution,
            "gross_margin_above_20pct": f8_high_margin,
            "positive_revenue_growth":  f9_revenue_growth,
        }

        total = sum(signals.values())
        bucket = "Strong" if total >= 7 else ("Moderate" if total >= 4 else "Weak")

        return {
            "ticker":        ticker,
            "f_score":       total,
            "max_score":     9,
            "health_bucket": bucket,
            "signals":       signals,
            "note": (
                "Some signals use yfinance proxies (e.g. ROA > 5% as proxy for "
                "increasing ROA) because year-over-year balance sheet data is not "
                "always available via yfinance."
            ),
        }

    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


# ---------------------------------------------------------------------------
# Composite health score 0-100
# ---------------------------------------------------------------------------

def financial_health_score(ticker: str) -> dict:
    """
    Generate a 0-100 financial health score combining:
      Piotroski F-Score     — 40 pts
      Profitability quality — 30 pts
      Valuation             — 20 pts
      Dividend / FCF        — 10 pts

    Returns score, point breakdown, and letter grade A-F.
    """
    try:
        raw   = yf.Ticker(ticker).info
        piotr = piotroski_score(ticker)

        # Piotroski component (0-40)
        piotr_pts = round((piotr.get("f_score", 0) / 9) * 40)

        # Profitability component (0-30)
        roe    = raw.get("returnOnEquity", 0) or 0
        margin = raw.get("profitMargins",  0) or 0
        prof_pts = 0
        if roe > 0.20:     prof_pts += 15
        elif roe > 0.10:   prof_pts += 8
        if margin > 0.15:  prof_pts += 15
        elif margin > 0.07:prof_pts += 8

        # Valuation component (0-20) — lower P/E scores higher
        pe = raw.get("trailingPE")
        val_pts = 0
        if pe is not None:
            if pe < 15:   val_pts = 20
            elif pe < 25: val_pts = 14
            elif pe < 40: val_pts = 8
            else:         val_pts = 3

        # Dividend & FCF component (0-10)
        div_yield = raw.get("dividendYield", 0) or 0
        fcf       = raw.get("freeCashflow",  0) or 0
        div_pts   = 0
        if div_yield > 0.03: div_pts += 5
        elif div_yield > 0:  div_pts += 3
        if fcf > 0:          div_pts += 5

        total = piotr_pts + prof_pts + val_pts + div_pts
        grade = (
            "A" if total >= 80 else
            "B" if total >= 65 else
            "C" if total >= 50 else
            "D" if total >= 35 else "F"
        )

        return {
            "ticker":       ticker,
            "health_score": total,
            "grade":        grade,
            "breakdown": {
                "piotroski_component":     piotr_pts,
                "profitability_component": prof_pts,
                "valuation_component":     val_pts,
                "dividend_fcf_component":  div_pts,
            },
            "piotroski_detail": piotr,
        }

    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    TICKER = "RELIANCE.NS"

    print("=" * 60)
    print(f"Testing metrics.py with {TICKER}")
    print("=" * 60)

    print("\n1. Full metrics snapshot:")
    m = get_full_metrics(TICKER)
    skip = {"company_name", "sector", "industry", "as_of"}
    for k, v in m.items():
        if "_fmt" not in k and k not in skip:
            print(f"   {k:25s}: {v}")

    print("\n2. DuPont Analysis:")
    d = dupont_analysis(TICKER)
    print(f"   Formula   : {d.get('formula')}")
    print(f"   ROE report : {d.get('roe_reported')}")
    print(f"   ROE DuPont : {d.get('roe_dupont')}")
    print(f"   Margin     : {d.get('net_profit_margin')}  → {d['interpretation']['margin']}")
    print(f"   Turnover   : {d.get('asset_turnover')}  → {d['interpretation']['turnover']}")
    print(f"   Leverage   : {d.get('equity_multiplier')}  → {d['interpretation']['leverage']}")

    print("\n3. Piotroski F-Score:")
    p = piotroski_score(TICKER)
    print(f"   F-Score : {p.get('f_score')}/9  — {p.get('health_bucket')}")
    for signal, val in p.get("signals", {}).items():
        print(f"   {'✅' if val else '❌'}  {signal}")

    print("\n4. Financial Health Score:")
    h = financial_health_score(TICKER)
    print(f"   Score : {h.get('health_score')}/100  Grade: {h.get('grade')}")
    for k, v in h.get("breakdown", {}).items():
        print(f"   {k:35s}: {v} pts")

    print("\n5. Peer comparison (HDFCBANK.NS):")
    pc = peer_comparison("HDFCBANK.NS")
    print(f"   Target: {pc['target'].get('name')}")
    for peer in pc["peers"]:
        if "error" not in peer:
            print(f"   Peer  : {peer.get('name', peer['ticker']):35s}  PE={peer.get('pe_ratio')}")
    print(f"   Rankings: {pc['ranking']}")

    print("\n" + "=" * 60)
    print("metrics.py test complete")
    print("=" * 60)
