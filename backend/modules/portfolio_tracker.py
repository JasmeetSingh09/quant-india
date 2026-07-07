import os
"""
portfolio_tracker.py — Track a user's REAL holdings (qty + buy price) with
live P&L, allocation, and best/worst performers.

Different from:
  - watchlist.py  (just alerts on tickers, no quantities)
  - simulator.py  (paper trading / backtests, not your real money)

This is the "home base" view: what you actually own and how it's doing.
Stored in SQLite (table: portfolio_holdings).
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

DB_PATH = Path(os.environ.get("QUANT_DATA_DIR", str(Path(__file__).parent.parent))) / "quant_platform.db"
sys.path.insert(0, str(Path(__file__).parent))


def _init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_holdings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker       TEXT NOT NULL,
            company_name TEXT,
            quantity     REAL NOT NULL,
            buy_price    REAL NOT NULL,
            added_at     TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _live_price(ticker: str) -> float | None:
    try:
        from data_fetcher import get_current_price
        r = get_current_price(ticker)
        return r.get("price")
    except Exception:
        try:
            import yfinance as yf
            return round(float(yf.Ticker(ticker).fast_info.last_price), 2)
        except Exception:
            return None


def _company_name(ticker: str) -> str:
    try:
        import yfinance as yf
        return yf.Ticker(ticker).info.get("shortName", ticker.replace(".NS", ""))
    except Exception:
        return ticker.replace(".NS", "")


def add_holding(ticker: str, quantity: float, buy_price: float) -> dict:
    """Add a holding. quantity > 0, buy_price > 0, ticker must end .NS."""
    _init_db()
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return {"error": "Ticker is required"}
    if not ticker.endswith(".NS"):
        ticker = ticker + ".NS"      # be forgiving — auto-append the NSE suffix
    try:
        quantity  = float(quantity)
        buy_price = float(buy_price)
    except (TypeError, ValueError):
        return {"error": "quantity and buy_price must be numbers"}
    if quantity <= 0 or buy_price <= 0:
        return {"error": "quantity and buy_price must be greater than 0"}

    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO portfolio_holdings (ticker, company_name, quantity, buy_price, added_at) "
        "VALUES (?,?,?,?,?)",
        (ticker, _company_name(ticker), quantity, buy_price, now)
    )
    conn.commit()
    hid = cur.lastrowid
    conn.close()
    return {"status": "added", "id": hid, "ticker": ticker,
            "quantity": quantity, "buy_price": buy_price}


def remove_holding(holding_id: int) -> dict:
    """Remove a holding by its id."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("DELETE FROM portfolio_holdings WHERE id = ?", (holding_id,))
    conn.commit()
    conn.close()
    if cur.rowcount:
        return {"status": "removed", "id": holding_id}
    return {"error": f"No holding with id {holding_id}"}


def get_portfolio(refresh: bool = True) -> dict:
    """
    Return all holdings with live P&L plus portfolio totals and allocation.
    """
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, ticker, company_name, quantity, buy_price, added_at "
        "FROM portfolio_holdings ORDER BY added_at DESC"
    ).fetchall()
    conn.close()

    holdings = []
    total_invested = 0.0
    total_current  = 0.0

    for hid, ticker, cname, qty, buy, added in rows:
        invested = qty * buy
        live = _live_price(ticker) if refresh else buy
        if live is None:
            live = buy   # fall back so we never crash
        current = qty * live
        pnl = current - invested
        pnl_pct = (pnl / invested * 100) if invested else 0.0
        total_invested += invested
        total_current  += current
        holdings.append({
            "id": hid, "ticker": ticker, "company_name": cname,
            "quantity": round(qty, 4), "buy_price": round(buy, 2),
            "current_price": round(live, 2),
            "invested": round(invested, 2), "current_value": round(current, 2),
            "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
            "status": "profit" if pnl >= 0 else "loss",
        })

    # Allocation % (by current value) — done after totals are known
    for h in holdings:
        h["allocation_pct"] = round(h["current_value"] / total_current * 100, 2) if total_current else 0.0

    total_pnl = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0.0

    # Best / worst by % (only if we have holdings)
    best = max(holdings, key=lambda x: x["pnl_pct"]) if holdings else None
    worst = min(holdings, key=lambda x: x["pnl_pct"]) if holdings else None

    return {
        "holdings": holdings,
        "count": len(holdings),
        "total_invested": round(total_invested, 2),
        "total_current_value": round(total_current, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "overall_status": "profit" if total_pnl >= 0 else "loss",
        "best_performer": {"ticker": best["ticker"], "pnl_pct": best["pnl_pct"]} if best else None,
        "worst_performer": {"ticker": worst["ticker"], "pnl_pct": worst["pnl_pct"]} if worst else None,
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


if __name__ == "__main__":
    print("=" * 55)
    print("Testing portfolio_tracker.py")
    print("=" * 55)
    # clean slate for the test
    _init_db()
    conn = sqlite3.connect(DB_PATH); conn.execute("DELETE FROM portfolio_holdings"); conn.commit(); conn.close()

    print("\n1. Validation (bad inputs):")
    print("   no .NS :", add_holding("RELIANCE", 10, 100).get("error"))
    print("   qty<=0 :", add_holding("RELIANCE.NS", 0, 100).get("error"))
    print("   bad num:", add_holding("RELIANCE.NS", "abc", 100).get("error"))

    print("\n2. Add holdings:")
    a = add_holding("RELIANCE.NS", 10, 1200); print("   ", a)
    b = add_holding("TCS.NS", 5, 3000); print("   ", b)

    print("\n3. Portfolio with live P&L:")
    p = get_portfolio()
    print(f"   invested ₹{p['total_invested']:,} | current ₹{p['total_current_value']:,} | P&L ₹{p['total_pnl']:,} ({p['total_pnl_pct']}%)")
    for h in p["holdings"]:
        print(f"   {h['ticker']:13s} qty {h['quantity']} @ ₹{h['buy_price']} -> ₹{h['current_price']}  P&L ₹{h['pnl']} ({h['pnl_pct']}%)  alloc {h['allocation_pct']}%")
    print(f"   best: {p['best_performer']} | worst: {p['worst_performer']}")

    print("\n4. Remove + empty-portfolio safety:")
    if a.get("id"): print("   remove:", remove_holding(a["id"]))
    if b.get("id"): print("   remove:", remove_holding(b["id"]))
    empty = get_portfolio()
    print(f"   empty -> count {empty['count']}, total_pnl {empty['total_pnl']}, best {empty['best_performer']} (no crash)")
    print("   remove missing:", remove_holding(99999).get("error"))
    print("\nDone.")
