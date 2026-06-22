"""
commodities.py — Live prices for gold, silver, crude oil, natural gas,
copper, aluminium, and other commodities relevant to Indian investors.

Data source: yfinance (COMEX/NYMEX futures + Indian commodity ETFs on NSE).
MCX India prices closely track these international benchmarks.

Commodity tickers used:
  GC=F   — Gold futures (COMEX, USD/troy oz)
  SI=F   — Silver futures (COMEX, USD/troy oz)
  CL=F   — Crude Oil WTI (NYMEX, USD/barrel)
  BZ=F   — Brent Crude (ICE, USD/barrel)
  NG=F   — Natural Gas (NYMEX, USD/MMBtu)
  HG=F   — Copper (COMEX, USD/lb)
  ALI=F  — Aluminium (COMEX, USD/lb)
  PA=F   — Palladium (COMEX, USD/troy oz)
  PL=F   — Platinum (COMEX, USD/troy oz)
  ZW=F   — Wheat (CBOT, USD/bushel)
  ZS=F   — Soybean (CBOT, USD/bushel)

Indian NSE commodity ETFs (priced in INR):
  GOLDBEES.NS     — Nippon India Gold ETF
  HDFCGOLD.NS     — HDFC Gold ETF
  SILVERETF.NS    — Nippon Silver ETF
  OILIETF.NS      — ICICI Prudential Oil ETF (tracks crude)
"""

import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Commodity catalogue
# ---------------------------------------------------------------------------

COMMODITIES = {
    # Precious metals
    "gold":        {"ticker": "GC=F",  "name": "Gold",          "unit": "USD/troy oz",  "category": "precious_metals"},
    "silver":      {"ticker": "SI=F",  "name": "Silver",        "unit": "USD/troy oz",  "category": "precious_metals"},
    "platinum":    {"ticker": "PL=F",  "name": "Platinum",      "unit": "USD/troy oz",  "category": "precious_metals"},
    "palladium":   {"ticker": "PA=F",  "name": "Palladium",     "unit": "USD/troy oz",  "category": "precious_metals"},
    # Energy
    "crude_wti":   {"ticker": "CL=F",  "name": "Crude Oil WTI", "unit": "USD/barrel",   "category": "energy"},
    "crude_brent": {"ticker": "BZ=F",  "name": "Brent Crude",   "unit": "USD/barrel",   "category": "energy"},
    "natural_gas": {"ticker": "NG=F",  "name": "Natural Gas",   "unit": "USD/MMBtu",    "category": "energy"},
    # Base metals
    "copper":      {"ticker": "HG=F",  "name": "Copper",        "unit": "USD/lb",       "category": "base_metals"},
    "aluminium":   {"ticker": "ALI=F", "name": "Aluminium",     "unit": "USD/lb",       "category": "base_metals"},
    # Agricultural
    "wheat":       {"ticker": "ZW=F",  "name": "Wheat",         "unit": "USD/bushel",   "category": "agricultural"},
    "soybean":     {"ticker": "ZS=F",  "name": "Soybean",       "unit": "USD/bushel",   "category": "agricultural"},
    "cotton":      {"ticker": "CT=F",  "name": "Cotton",        "unit": "USD/lb",       "category": "agricultural"},
    # Indian NSE ETFs (INR-denominated)
    "gold_etf_india":   {"ticker": "GOLDBEES.NS",   "name": "Gold ETF (India)",   "unit": "INR/unit", "category": "india_etf"},
    "silver_etf_india": {"ticker": "SILVERETF.NS",  "name": "Silver ETF (India)", "unit": "INR/unit", "category": "india_etf"},
    "oil_etf_india":    {"ticker": "OILIETF.NS",    "name": "Oil ETF (India)",    "unit": "INR/unit", "category": "india_etf"},
}

# USD/INR rate ticker
USDINR_TICKER = "INR=X"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_usd_inr() -> float:
    """Fetch current USD/INR exchange rate."""
    try:
        rate = yf.Ticker(USDINR_TICKER).fast_info.last_price
        return round(float(rate), 2)
    except Exception:
        return 84.0   # fallback approximate rate


def _fetch_commodity_price(ticker: str) -> dict:
    """Fetch current price and daily change for a commodity ticker."""
    try:
        info = yf.Ticker(ticker).fast_info
        price     = float(info.last_price)
        prev      = float(info.previous_close)
        change    = price - prev
        change_pct= (change / prev) * 100 if prev else 0
        return {
            "price":      round(price, 4),
            "prev_close": round(prev, 4),
            "change":     round(change, 4),
            "change_pct": round(change_pct, 2),
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_commodity_price(commodity_key: str) -> dict:
    """
    Get current price for a single commodity by key.

    commodity_key: one of the keys in COMMODITIES dict
                   e.g. "gold", "crude_wti", "silver"

    Returns price in original unit + INR equivalent for international commodities.
    """
    if commodity_key not in COMMODITIES:
        return {"error": f"Unknown commodity '{commodity_key}'. Valid keys: {list(COMMODITIES.keys())}"}

    meta   = COMMODITIES[commodity_key]
    result = _fetch_commodity_price(meta["ticker"])

    if "error" in result:
        return {"commodity": commodity_key, **meta, **result}

    output = {
        "commodity":  commodity_key,
        "name":       meta["name"],
        "ticker":     meta["ticker"],
        "unit":       meta["unit"],
        "category":   meta["category"],
        **result,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Add INR equivalent for international (USD-priced) commodities
    if meta["category"] != "india_etf":
        usd_inr = _get_usd_inr()
        output["usd_inr_rate"] = usd_inr
        output["price_inr"]    = round(result["price"] * usd_inr, 2)

    return output


def get_all_commodities() -> dict:
    """
    Fetch current prices for all commodities grouped by category.

    Returns a dict keyed by category, each containing a list of commodity prices.
    Also includes the current USD/INR rate.
    """
    usd_inr = _get_usd_inr()
    results = {"usd_inr_rate": usd_inr, "categories": {}, "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    for key, meta in COMMODITIES.items():
        price_data = _fetch_commodity_price(meta["ticker"])
        entry = {
            "key":      key,
            "name":     meta["name"],
            "ticker":   meta["ticker"],
            "unit":     meta["unit"],
            **price_data,
        }
        if meta["category"] != "india_etf" and "error" not in price_data:
            entry["price_inr"] = round(price_data.get("price", 0) * usd_inr, 2)

        cat = meta["category"]
        results["categories"].setdefault(cat, []).append(entry)

    return results


def get_commodity_history(commodity_key: str, period: str = "1mo") -> dict:
    """
    Fetch historical price data for a commodity.

    period: "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"

    Returns OHLCV data as a list of dicts.
    """
    if commodity_key not in COMMODITIES:
        return {"error": f"Unknown commodity '{commodity_key}'"}

    meta = COMMODITIES[commodity_key]
    try:
        df = yf.Ticker(meta["ticker"]).history(period=period)
        if df.empty:
            return {"error": "No historical data returned"}

        history = []
        for date, row in df.iterrows():
            history.append({
                "date":   str(date.date()),
                "open":   round(float(row["Open"]),  4),
                "high":   round(float(row["High"]),  4),
                "low":    round(float(row["Low"]),   4),
                "close":  round(float(row["Close"]), 4),
                "volume": int(row.get("Volume", 0)),
            })

        return {
            "commodity": commodity_key,
            "name":      meta["name"],
            "ticker":    meta["ticker"],
            "unit":      meta["unit"],
            "period":    period,
            "history":   history,
        }
    except Exception as e:
        return {"error": str(e)}


def get_commodities_by_category(category: str) -> list:
    """
    Get prices for all commodities in a specific category.

    Categories: precious_metals, energy, base_metals, agricultural, india_etf
    """
    keys = [k for k, v in COMMODITIES.items() if v["category"] == category]
    if not keys:
        return [{"error": f"Unknown category '{category}'"}]

    usd_inr = _get_usd_inr()
    results = []
    for key in keys:
        meta  = COMMODITIES[key]
        price = _fetch_commodity_price(meta["ticker"])
        entry = {"key": key, "name": meta["name"], "unit": meta["unit"], **price}
        if category != "india_etf" and "error" not in price:
            entry["price_inr"] = round(price.get("price", 0) * usd_inr, 2)
        results.append(entry)
    return results


def get_mcx_summary() -> dict:
    """
    Return a dashboard-style summary of the most-watched commodities
    on Indian MCX: gold, silver, crude oil (both benchmarks), natural gas,
    copper, and aluminium — all with INR equivalent prices.
    """
    mcx_keys = ["gold", "silver", "crude_wti", "crude_brent", "natural_gas", "copper", "aluminium"]
    usd_inr  = _get_usd_inr()
    summary  = {"usd_inr_rate": usd_inr, "commodities": []}

    for key in mcx_keys:
        meta  = COMMODITIES[key]
        price = _fetch_commodity_price(meta["ticker"])
        if "error" not in price:
            summary["commodities"].append({
                "name":       meta["name"],
                "key":        key,
                "unit":       meta["unit"],
                "price_usd":  price["price"],
                "price_inr":  round(price["price"] * usd_inr, 2),
                "change_pct": price["change_pct"],
                "direction":  "up" if price["change_pct"] > 0 else ("down" if price["change_pct"] < 0 else "flat"),
            })

    summary["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return summary


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Testing commodities.py")
    print("=" * 60)

    print(f"\nUSD/INR rate: {_get_usd_inr()}")

    print("\n1. Single commodity — Gold:")
    gold = get_commodity_price("gold")
    print(f"   Price : ${gold.get('price')} {gold.get('unit')}")
    print(f"   INR   : ₹{gold.get('price_inr')}")
    print(f"   Change: {gold.get('change_pct')}%")

    print("\n2. Single commodity — Brent Crude:")
    brent = get_commodity_price("crude_brent")
    print(f"   Price : ${brent.get('price')} {brent.get('unit')}")
    print(f"   INR   : ₹{brent.get('price_inr')}")
    print(f"   Change: {brent.get('change_pct')}%")

    print("\n3. MCX Dashboard Summary:")
    mcx = get_mcx_summary()
    print(f"   USD/INR: {mcx['usd_inr_rate']}")
    for c in mcx["commodities"]:
        arrow = "▲" if c["direction"] == "up" else ("▼" if c["direction"] == "down" else "─")
        print(f"   {c['name']:20s}  ${c['price_usd']:>10.3f}  ₹{c['price_inr']:>10.2f}  {arrow} {c['change_pct']:+.2f}%")

    print("\n4. All precious metals:")
    metals = get_commodities_by_category("precious_metals")
    for m in metals:
        if "error" not in m:
            print(f"   {m['name']:12s}  ${m.get('price')}  ₹{m.get('price_inr')}")

    print("\n5. Gold price history (1 month, last 3 rows):")
    hist = get_commodity_history("gold", period="1mo")
    if "history" in hist:
        for row in hist["history"][-3:]:
            print(f"   {row['date']}  Close: ${row['close']}")

    print("\n" + "=" * 60)
    print("commodities.py test complete")
    print("=" * 60)
