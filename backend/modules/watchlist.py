import os
"""
watchlist.py — SQLite-backed user stock watchlist for NSE tickers.

Each watchlist entry stores:
  - ticker              NSE symbol e.g. RELIANCE.NS
  - added_price         price when the user added the stock
  - current_price       last fetched price (updated on read)
  - price_alert_pct     trigger alert if price moves ± this % from added_price
  - sentiment_alert     boolean — also alert on strong negative sentiment shift

Database: backend/quant_platform.db
"""

import sqlite3
from db import get_conn, IntegrityError  # noqa: F401
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

DB_PATH = Path(os.environ.get("QUANT_DATA_DIR", str(Path(__file__).parent.parent))) / "quant_platform.db"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _init_db():
    """Create watchlist table if it does not exist (per-user)."""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          TEXT NOT NULL DEFAULT 'public',
            ticker           TEXT NOT NULL,
            company_name     TEXT,
            added_price      REAL,
            current_price    REAL,
            price_alert_pct  REAL DEFAULT 5.0,
            sentiment_alert  INTEGER DEFAULT 1,
            added_at         TEXT NOT NULL,
            last_updated     TEXT
        )
    """)
    # migrate an older table that predates per-user support (best effort)
    try:
        conn.execute("ALTER TABLE watchlist ADD COLUMN user_id TEXT NOT NULL DEFAULT 'public'")
    except Exception:
        pass
    # a stock is unique PER USER, not globally
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_watchlist_user_ticker "
                 "ON watchlist(user_id, ticker)")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def _get_current_price(ticker: str) -> float | None:
    """Fetch live price using data_fetcher; returns None on failure."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from data_fetcher import get_current_price
        result = get_current_price(ticker)
        return result.get("price")
    except Exception:
        try:
            import yfinance as yf
            price = yf.Ticker(ticker).fast_info.last_price
            return round(float(price), 2)
        except Exception:
            return None


def _get_company_name(ticker: str) -> str:
    """Fetch company name from yfinance."""
    try:
        import yfinance as yf
        return yf.Ticker(ticker).info.get("longName", ticker.replace(".NS", ""))
    except Exception:
        return ticker.replace(".NS", "")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_to_watchlist(
    ticker: str,
    price_alert_pct: float = 5.0,
    sentiment_alert: bool = True,
    user_id: str = "public",
) -> dict:
    """
    Add an NSE ticker to the watchlist.

    ticker           — must end in .NS e.g. "RELIANCE.NS"
    price_alert_pct  — alert threshold in percent (default 5 %)
    sentiment_alert  — whether to alert on negative sentiment shift

    Returns the created watchlist entry or an error dict.
    """
    _init_db()

    ticker = ticker.upper()
    if not ticker.endswith(".NS"):
        return {"error": f"Ticker must end with .NS, got: {ticker}"}

    current_price = _get_current_price(ticker)
    if current_price is None:
        return {"error": f"Could not fetch price for {ticker}. Check the ticker symbol."}

    company_name = _get_company_name(ticker)
    now = datetime.now().isoformat()

    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO watchlist
              (user_id, ticker, company_name, added_price, current_price,
               price_alert_pct, sentiment_alert, added_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, ticker, company_name, current_price, current_price,
              price_alert_pct, int(sentiment_alert), now, now))
        conn.commit()
        return {
            "status": "added",
            "ticker": ticker,
            "company_name": company_name,
            "added_price": current_price,
            "price_alert_pct": price_alert_pct,
            "sentiment_alert": sentiment_alert,
            "added_at": now,
        }
    except IntegrityError:
        return {"error": f"{ticker} is already in your watchlist"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def remove_from_watchlist(ticker: str, user_id: str = "public") -> dict:
    """Remove a ticker from the watchlist. Returns status."""
    _init_db()
    ticker = ticker.upper()
    conn = get_conn()
    cursor = conn.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
                          (user_id, ticker))
    conn.commit()
    conn.close()
    if cursor.rowcount:
        return {"status": "removed", "ticker": ticker}
    return {"error": f"{ticker} not found in watchlist"}


def get_watchlist(refresh_prices: bool = True, user_id: str = "public") -> list:
    """
    Return all watchlist entries for a user.

    If refresh_prices is True, fetches the latest price for each ticker
    and updates the stored current_price.
    """
    _init_db()
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, ticker, company_name, added_price, current_price,
               price_alert_pct, sentiment_alert, added_at, last_updated
        FROM watchlist WHERE user_id = ? ORDER BY added_at DESC
    """, (user_id,)).fetchall()
    conn.close()

    entries = []
    for row in rows:
        entry = {
            "id":               row[0],
            "ticker":           row[1],
            "company_name":     row[2],
            "added_price":      row[3],
            "current_price":    row[4],
            "price_alert_pct":  row[5],
            "sentiment_alert":  bool(row[6]),
            "added_at":         row[7],
            "last_updated":     row[8],
        }

        if refresh_prices:
            live = _get_current_price(row[1])
            if live is not None:
                entry["current_price"] = live
                change_pct = ((live - row[3]) / row[3]) * 100 if row[3] else 0
                entry["change_from_add_pct"] = round(change_pct, 2)
                entry["alert_triggered"] = abs(change_pct) >= row[5]

                conn2 = get_conn()
                conn2.execute(
                    "UPDATE watchlist SET current_price = ?, last_updated = ? WHERE id = ?",
                    (live, datetime.now().isoformat(), row[0])
                )
                conn2.commit()
                conn2.close()
            else:
                entry["change_from_add_pct"] = None
                entry["alert_triggered"] = False
        else:
            change_pct = ((row[4] - row[3]) / row[3]) * 100 if row[3] else 0
            entry["change_from_add_pct"] = round(change_pct, 2)
            entry["alert_triggered"] = abs(change_pct) >= row[5]

        entries.append(entry)

    return entries


def update_alert_settings(
    ticker: str,
    price_alert_pct: float = None,
    sentiment_alert: bool = None,
    user_id: str = "public",
) -> dict:
    """Update alert thresholds for an existing watchlist entry."""
    _init_db()
    ticker = ticker.upper()

    updates = []
    values = []
    if price_alert_pct is not None:
        updates.append("price_alert_pct = ?")
        values.append(price_alert_pct)
    if sentiment_alert is not None:
        updates.append("sentiment_alert = ?")
        values.append(int(sentiment_alert))

    if not updates:
        return {"error": "No fields to update"}

    values.extend([user_id, ticker])
    conn = get_conn()
    cursor = conn.execute(
        f"UPDATE watchlist SET {', '.join(updates)} WHERE user_id = ? AND ticker = ?", values
    )
    conn.commit()
    conn.close()

    if cursor.rowcount:
        return {"status": "updated", "ticker": ticker}
    return {"error": f"{ticker} not found in watchlist"}


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Testing watchlist.py")
    print("=" * 60)

    print("\n1. Adding RELIANCE.NS to watchlist...")
    result = add_to_watchlist("RELIANCE.NS", price_alert_pct=5.0, sentiment_alert=True)
    print(f"   {result}")

    print("\n2. Adding TCS.NS to watchlist...")
    result = add_to_watchlist("TCS.NS", price_alert_pct=3.0)
    print(f"   {result}")

    print("\n3. Adding RELIANCE.NS again (should show duplicate error)...")
    result = add_to_watchlist("RELIANCE.NS")
    print(f"   {result}")

    print("\n4. Fetching watchlist (refreshing prices)...")
    watchlist = get_watchlist(refresh_prices=True)
    print(f"   {len(watchlist)} items in watchlist:")
    for entry in watchlist:
        print(f"   {entry['ticker']:15s} added @ ₹{entry['added_price']:.2f}  "
              f"current ₹{entry.get('current_price', 'N/A')}  "
              f"change {entry.get('change_from_add_pct', 'N/A')}%  "
              f"alert triggered: {entry.get('alert_triggered')}")

    print("\n5. Updating alert threshold for TCS.NS...")
    result = update_alert_settings("TCS.NS", price_alert_pct=7.5)
    print(f"   {result}")

    print("\n6. Removing TCS.NS...")
    result = remove_from_watchlist("TCS.NS")
    print(f"   {result}")

    print("\n7. Final watchlist:")
    watchlist = get_watchlist(refresh_prices=False)
    for entry in watchlist:
        print(f"   {entry['ticker']:15s} alert_pct={entry['price_alert_pct']}%")

    print("\n" + "=" * 60)
    print("watchlist.py test complete")
    print("=" * 60)
