import os
"""
simulator.py — Real-time paper trading + historic backtesting for NSE stocks.

TWO SIMULATION MODES:

1. REAL-TIME SIMULATION (paper trading)
   - Start a virtual portfolio at today's live prices
   - Come back anytime — fetches live prices and shows exact ₹ P&L per stock
   - Shows: entry price, current price, gain/loss %, absolute ₹ gain/loss
   - Persists in SQLite so you can track it over days/weeks
   - Example: "I bought HDFC at ₹1650 on June 15 — am I up or down today?"

2. HISTORIC SIMULATION (backtest)
   - Pick any date range e.g. 2019-01-01 to 2022-12-31
   - See exactly how your portfolio would have performed
   - Day-by-day portfolio value curve for charting
   - Compare vs Nifty 50 benchmark
   - Sharpe ratio, max drawdown, CAGR, best/worst month

Database: backend/quant_platform.db
"""

import json
import sqlite3
from db import get_conn, IntegrityError  # noqa: F401
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

DB_PATH = Path(os.environ.get("QUANT_DATA_DIR", str(Path(__file__).parent.parent))) / "quant_platform.db"
NIFTY_TICKER = "^NSEI"


# ---------------------------------------------------------------------------
# Database schema
# ---------------------------------------------------------------------------

def _init_db():
    conn = get_conn()

    # Real-time simulation sessions (per-user; a sim name is unique PER USER)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS simulations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         TEXT NOT NULL DEFAULT 'public',
            name            TEXT NOT NULL,
            initial_value   REAL NOT NULL,
            started_at      TEXT NOT NULL,
            last_checked    TEXT,
            status          TEXT DEFAULT 'active'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sim_positions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         TEXT NOT NULL DEFAULT 'public',
            sim_name        TEXT NOT NULL,
            ticker          TEXT NOT NULL,
            company_name    TEXT,
            allocation_pct  REAL NOT NULL,
            units           REAL NOT NULL,
            entry_price     REAL NOT NULL,
            entry_value     REAL NOT NULL,
            entry_date      TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sim_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT NOT NULL DEFAULT 'public',
            sim_name    TEXT NOT NULL,
            snapshot_at TEXT NOT NULL,
            total_value REAL NOT NULL,
            pnl_pct     REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      TEXT NOT NULL DEFAULT 'public',
            name         TEXT NOT NULL,
            holdings     TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            last_updated TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS challenge_entries (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id TEXT NOT NULL,
            user_pick    TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            result       TEXT
        )
    """)
    # migrate older tables that predate per-user support (best effort)
    for tbl in ("simulations", "sim_positions", "sim_snapshots", "portfolios"):
        try:
            conn.execute(f"ALTER TABLE {tbl} ADD COLUMN user_id TEXT NOT NULL DEFAULT 'public'")
        except Exception:
            pass

    # Old SQLite tables were created with a table-level UNIQUE(name) that blocks
    # two users from sharing a sim/portfolio name. ALTER can't drop it, so rebuild
    # the table without it. (Postgres deploys start fresh, so this only runs on
    # legacy local SQLite DBs.)
    import db as _db
    if not _db.IS_POSTGRES:
        _rebuild_if_global_unique(conn, "portfolios",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL DEFAULT 'public', "
            "name TEXT NOT NULL, holdings TEXT NOT NULL, created_at TEXT NOT NULL, last_updated TEXT",
            "id, user_id, name, holdings, created_at, last_updated")
        _rebuild_if_global_unique(conn, "simulations",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL DEFAULT 'public', "
            "name TEXT NOT NULL, initial_value REAL NOT NULL, started_at TEXT NOT NULL, "
            "last_checked TEXT, status TEXT DEFAULT 'active'",
            "id, user_id, name, initial_value, started_at, last_checked, status")

    # a sim name / portfolio name is unique per user (not globally)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_sim_user_name ON simulations(user_id, name)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_pf_user_name ON portfolios(user_id, name)")
    conn.commit()
    conn.close()


def _rebuild_if_global_unique(conn, table: str, columns_ddl: str, columns_csv: str):
    """SQLite only: if `table` was created with a table-level UNIQUE(name),
    rebuild it without that constraint, preserving all rows."""
    # An inline UNIQUE constraint (either `UNIQUE(name)` or `name ... UNIQUE`)
    # creates an sqlite_autoindex_* entry. The clean rebuilt table has none.
    has_autoindex = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND tbl_name=? "
        "AND name LIKE 'sqlite_autoindex_%' LIMIT 1", (table,)
    ).fetchone()
    if not has_autoindex:
        return
    conn.execute(f"ALTER TABLE {table} RENAME TO {table}_old_uq")
    conn.execute(f"CREATE TABLE {table} ({columns_ddl})")
    conn.execute(f"INSERT INTO {table} ({columns_csv}) SELECT {columns_csv} FROM {table}_old_uq")
    conn.execute(f"DROP TABLE {table}_old_uq")


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------

def _live_price(ticker: str) -> float | None:
    """
    Fetch the latest price for a ticker. Tries fast_info first, then falls back
    to recent history (more reliable for commodity futures and during yfinance
    hiccups). Returns None only if both fail.
    """
    tk = yf.Ticker(ticker)
    try:
        p = tk.fast_info.last_price
        if p and p == p and p > 0:           # not None, not NaN, positive
            return round(float(p), 4)
    except Exception:
        pass
    try:
        h = tk.history(period="5d")["Close"].dropna()
        if len(h):
            return round(float(h.iloc[-1]), 4)
    except Exception:
        pass
    return None


def _company_name(ticker: str) -> str:
    try:
        return yf.Ticker(ticker).info.get("shortName", ticker.replace(".NS", ""))
    except Exception:
        return ticker.replace(".NS", "")


def _download_prices(tickers: list, start: str, end: str) -> pd.DataFrame:
    """Download adjusted close prices for a list of tickers."""
    frames = {}
    for t in tickers:
        try:
            df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
            if not df.empty:
                frames[t] = df["Close"].squeeze()
        except Exception:
            pass
    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames).dropna(how="all")


# ---------------------------------------------------------------------------
# ── MODE 1: REAL-TIME SIMULATION ──────────────────────────────────────────
# ---------------------------------------------------------------------------

def start_simulation(
    name: str,
    holdings: dict,
    initial_value: float = 100_000,
    user_id: str = "public",
) -> dict:
    """
    Start a real-time paper trading simulation.

    Records TODAY'S live prices as entry prices. Every time you call
    get_simulation_pnl(name) it fetches live prices and shows you the
    exact profit/loss from those entry prices.

    name          — unique label e.g. "my_hdfc_bet"
    holdings      — {ticker: allocation_pct}  must sum to 100
    initial_value — virtual capital in ₹ (default ₹1,00,000)

    Returns the simulation summary with all entry prices recorded.
    """
    _init_db()

    total_alloc = sum(holdings.values())
    if abs(total_alloc - 100) > 0.01:
        return {"error": f"Allocations must sum to 100%, got {total_alloc:.1f}%"}
    for t in holdings:
        # Accept NSE/BSE stocks (.NS/.BO), commodity futures (=F), and indices (^)
        if not (t.endswith(".NS") or t.endswith(".BO") or "=F" in t or t.startswith("^")):
            return {"error": f"Unsupported ticker '{t}' (use .NS stocks or commodity futures like GC=F)"}

    now = datetime.now().isoformat()
    positions = []
    failed    = []

    for ticker, pct in holdings.items():
        price = _live_price(ticker)
        if price is None or price <= 0:
            failed.append(ticker)
            continue
        alloc_value = initial_value * pct / 100
        units       = alloc_value / price
        positions.append({
            "ticker":        ticker,
            "company_name":  _company_name(ticker),
            "allocation_pct":pct,
            "units":         units,
            "entry_price":   price,
            "entry_value":   alloc_value,
            "entry_date":    now,
        })

    if not positions:
        return {"error": "Could not fetch prices for any ticker. Check symbols."}
    if failed:
        return {"error": f"Could not fetch prices for: {failed}. Check ticker symbols."}

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO simulations (user_id, name, initial_value, started_at, last_checked, status) "
            "VALUES (?, ?, ?, ?, ?, 'active')",
            (user_id, name, initial_value, now, now)
        )
        for p in positions:
            conn.execute("""
                INSERT INTO sim_positions
                  (user_id, sim_name, ticker, company_name, allocation_pct, units,
                   entry_price, entry_value, entry_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, name, p["ticker"], p["company_name"], p["allocation_pct"],
                  p["units"], p["entry_price"], p["entry_value"], p["entry_date"]))
        conn.commit()
    except IntegrityError:
        conn.close()
        return {"error": f"Simulation '{name}' already exists. Use a different name or delete it first."}
    finally:
        conn.close()

    return {
        "status":        "started",
        "name":          name,
        "initial_value": initial_value,
        "started_at":    now,
        "positions":     positions,
        "note":          f"Call GET /simulator/realtime/{name} anytime to see your live P&L",
    }


def get_simulation_pnl(name: str, user_id: str = "public") -> dict:
    """
    Fetch live prices for all positions in a simulation and compute P&L.

    For each stock shows:
      entry_price    — price when simulation was started
      current_price  — live price right now
      units          — number of shares held
      entry_value    — ₹ invested in this stock
      current_value  — ₹ value right now
      pnl_inr        — absolute ₹ profit or loss
      pnl_pct        — % gain or loss from entry

    Overall portfolio shows total ₹ P&L and % vs initial capital.
    """
    _init_db()
    conn = get_conn()
    sim = conn.execute(
        "SELECT name, initial_value, started_at FROM simulations WHERE name = ? AND user_id = ?",
        (name, user_id)
    ).fetchone()
    if not sim:
        conn.close()
        return {"error": f"Simulation '{name}' not found"}

    positions_raw = conn.execute(
        "SELECT ticker, company_name, allocation_pct, units, entry_price, entry_value, entry_date "
        "FROM sim_positions WHERE sim_name = ? AND user_id = ?", (name, user_id)
    ).fetchall()
    conn.close()

    initial_value = sim[1]
    started_at    = sim[2]
    positions     = []
    total_current = 0.0
    total_entry   = 0.0

    for row in positions_raw:
        ticker, cname, alloc_pct, units, entry_price, entry_value, entry_date = row
        current_price = _live_price(ticker)
        if current_price is None:
            current_price = entry_price   # fallback

        current_value = units * current_price
        pnl_inr       = current_value - entry_value
        pnl_pct       = (pnl_inr / entry_value) * 100 if entry_value else 0

        total_current += current_value
        total_entry   += entry_value

        positions.append({
            "ticker":        ticker,
            "company_name":  cname,
            "allocation_pct":alloc_pct,
            "units":         round(units, 4),
            "entry_price":   entry_price,
            "current_price": current_price,
            "entry_value":   round(entry_value, 2),
            "current_value": round(current_value, 2),
            "pnl_inr":       round(pnl_inr, 2),
            "pnl_pct":       round(pnl_pct, 2),
            "status":        "profit" if pnl_inr >= 0 else "loss",
        })

    total_pnl_inr = total_current - initial_value
    total_pnl_pct = (total_pnl_inr / initial_value) * 100 if initial_value else 0

    # Save snapshot for P&L chart
    now = datetime.now().isoformat()
    conn2 = get_conn()
    conn2.execute(
        "INSERT INTO sim_snapshots (user_id, sim_name, snapshot_at, total_value, pnl_pct) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, now, round(total_current, 2), round(total_pnl_pct, 2))
    )
    conn2.execute("UPDATE simulations SET last_checked = ? WHERE name = ? AND user_id = ?",
                  (now, name, user_id))
    conn2.commit()
    conn2.close()

    # Sort positions: biggest winners first, then losers
    positions.sort(key=lambda x: x["pnl_pct"], reverse=True)

    return {
        "simulation":      name,
        "started_at":      started_at,
        "checked_at":      now,
        "initial_value":   initial_value,
        "current_value":   round(total_current, 2),
        "total_pnl_inr":   round(total_pnl_inr, 2),
        "total_pnl_pct":   round(total_pnl_pct, 2),
        "overall_status":  "profit" if total_pnl_inr >= 0 else "loss",
        "positions":       positions,
        "best_performer":  positions[0]["ticker"] if positions else None,
        "worst_performer": positions[-1]["ticker"] if positions else None,
    }


def get_simulation_history(name: str, user_id: str = "public") -> dict:
    """
    Return the P&L snapshot history for a simulation — use for a portfolio value chart.
    Each row is {snapshot_at, total_value, pnl_pct}.
    """
    _init_db()
    conn = get_conn()
    sim = conn.execute(
        "SELECT initial_value, started_at FROM simulations WHERE name = ? AND user_id = ?",
        (name, user_id)
    ).fetchone()
    if not sim:
        conn.close()
        return {"error": f"Simulation '{name}' not found"}
    rows = conn.execute(
        "SELECT snapshot_at, total_value, pnl_pct FROM sim_snapshots WHERE sim_name = ? AND user_id = ? ORDER BY snapshot_at",
        (name, user_id)
    ).fetchall()
    conn.close()
    return {
        "simulation":    name,
        "started_at":    sim[1],
        "initial_value": sim[0],
        "snapshots": [
            {"at": r[0], "value": r[1], "pnl_pct": r[2]} for r in rows
        ],
    }


def list_simulations(user_id: str = "public") -> list:
    """List all active real-time simulations for a user."""
    _init_db()
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, initial_value, started_at, last_checked, status FROM simulations "
        "WHERE user_id = ? ORDER BY started_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [
        {"name": r[0], "initial_value": r[1], "started_at": r[2],
         "last_checked": r[3], "status": r[4]}
        for r in rows
    ]


def add_position(sim_name: str, ticker: str, amount: float, user_id: str = "public") -> dict:
    """
    Add (buy) a stock into an ALREADY-RUNNING simulation at TODAY'S live price.

    This is honest paper trading: the new holding is booked at the current market
    price (so it starts at ~0 P&L, not the sim's original start price), funded by
    fresh capital. The simulation's invested capital grows by `amount`, so every
    existing position's P&L is completely unaffected.

    sim_name — the running simulation
    ticker   — stock/commodity to add (e.g. "INFY.NS", "GC=F")
    amount   — ₹ of new capital to invest in it
    """
    _init_db()
    ticker = ticker.upper()
    if not (ticker.endswith(".NS") or ticker.endswith(".BO") or "=F" in ticker or ticker.startswith("^")):
        return {"error": f"Unsupported ticker '{ticker}' (use .NS stocks or futures like GC=F)"}
    if amount is None or amount <= 0:
        return {"error": "Amount to invest must be a positive number."}

    conn = get_conn()
    sim = conn.execute(
        "SELECT initial_value FROM simulations WHERE name = ? AND user_id = ?", (sim_name, user_id)
    ).fetchone()
    if not sim:
        conn.close()
        return {"error": f"Simulation '{sim_name}' not found"}

    price = _live_price(ticker)
    if price is None or price <= 0:
        conn.close()
        return {"error": f"Could not fetch a live price for {ticker}."}

    now      = datetime.now().isoformat()
    buy_units = amount / price
    new_init  = sim[0] + amount

    existing = conn.execute(
        "SELECT units, entry_value FROM sim_positions WHERE sim_name = ? AND ticker = ? AND user_id = ?",
        (sim_name, ticker, user_id)
    ).fetchone()

    if existing:
        # Top up an already-held stock: dollar-cost-average into it, blending the
        # entry price so P&L stays honest. This RAISES the stock's share.
        old_units, old_entry_value = existing
        tot_units   = old_units + buy_units
        tot_entry   = old_entry_value + amount
        blended     = tot_entry / tot_units if tot_units else price
        alloc_pct   = round(tot_entry / new_init * 100, 2)
        conn.execute(
            "UPDATE sim_positions SET units = ?, entry_value = ?, entry_price = ?, allocation_pct = ? "
            "WHERE sim_name = ? AND ticker = ? AND user_id = ?",
            (tot_units, tot_entry, round(blended, 4), alloc_pct, sim_name, ticker, user_id)
        )
        status, note = "topped_up", (
            f"Added ₹{amount:,.0f} more of {ticker} at ₹{price}. "
            f"Blended entry now ₹{blended:,.2f}."
        )
    else:
        # Buy a brand-new holding.
        alloc_pct = round(amount / new_init * 100, 2)
        conn.execute("""
            INSERT INTO sim_positions
              (user_id, sim_name, ticker, company_name, allocation_pct, units,
               entry_price, entry_value, entry_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, sim_name, ticker, _company_name(ticker), alloc_pct, buy_units, price, amount, now))
        status, note = "added", f"Bought {ticker} at ₹{price} with ₹{amount:,.0f} of new capital."

    conn.execute("UPDATE simulations SET initial_value = ? WHERE name = ? AND user_id = ?",
                 (new_init, sim_name, user_id))
    conn.commit()
    conn.close()

    return {
        "status":       status,
        "sim_name":     sim_name,
        "ticker":       ticker,
        "entry_price":  price,
        "units":        round(buy_units, 4),
        "invested":     round(amount, 2),
        "new_capital":  round(new_init, 2),
        "note":         note,
    }


def remove_position(sim_name: str, ticker: str, user_id: str = "public") -> dict:
    """
    Remove (sell) a stock from a running simulation at TODAY'S live price.

    Locks in that position's realized profit/loss, then withdraws the position:
    its invested capital is subtracted from the simulation's capital so the
    remaining holdings' P&L stays correct. Reports the realized ₹ P&L to the user.
    """
    _init_db()
    ticker = ticker.upper()
    conn = get_conn()
    sim = conn.execute(
        "SELECT initial_value FROM simulations WHERE name = ? AND user_id = ?", (sim_name, user_id)
    ).fetchone()
    if not sim:
        conn.close()
        return {"error": f"Simulation '{sim_name}' not found"}
    pos = conn.execute(
        "SELECT units, entry_price, entry_value FROM sim_positions WHERE sim_name = ? AND ticker = ? AND user_id = ?",
        (sim_name, ticker, user_id)
    ).fetchone()
    if not pos:
        conn.close()
        return {"error": f"{ticker} is not in this simulation."}

    units, entry_price, entry_value = pos
    n_positions = conn.execute(
        "SELECT COUNT(*) FROM sim_positions WHERE sim_name = ? AND user_id = ?", (sim_name, user_id)
    ).fetchone()[0]
    if n_positions <= 1:
        conn.close()
        return {"error": "Can't remove the last holding — delete the whole simulation instead."}

    current_price = _live_price(ticker) or entry_price
    current_value = units * current_price
    realized_pnl  = current_value - entry_value
    new_init      = max(sim[0] - entry_value, 0.0)

    conn.execute("DELETE FROM sim_positions WHERE sim_name = ? AND ticker = ? AND user_id = ?",
                 (sim_name, ticker, user_id))
    conn.execute("UPDATE simulations SET initial_value = ? WHERE name = ? AND user_id = ?",
                 (new_init, sim_name, user_id))
    conn.commit()
    conn.close()

    return {
        "status":        "removed",
        "sim_name":      sim_name,
        "ticker":        ticker,
        "sell_price":    round(current_price, 4),
        "realized_pnl":  round(realized_pnl, 2),
        "realized_pct":  round(realized_pnl / entry_value * 100, 2) if entry_value else 0,
        "new_capital":   round(new_init, 2),
        "note":          f"Sold {ticker} at ₹{current_price}. Realized P&L ₹{realized_pnl:,.2f}.",
    }


def delete_simulation(name: str, user_id: str = "public") -> dict:
    """Delete a simulation and all its positions/snapshots (only if owned by this user)."""
    _init_db()
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM simulations WHERE name = ? AND user_id = ?",
                         (name, user_id)).fetchone()[0]
    if not count:
        conn.close()
        return {"error": f"Simulation '{name}' not found"}
    conn.execute("DELETE FROM sim_positions WHERE sim_name = ? AND user_id = ?", (name, user_id))
    conn.execute("DELETE FROM sim_snapshots WHERE sim_name = ? AND user_id = ?", (name, user_id))
    conn.execute("DELETE FROM simulations WHERE name = ? AND user_id = ?", (name, user_id))
    conn.commit()
    conn.close()
    return {"status": "deleted", "name": name}


# ---------------------------------------------------------------------------
# ── MODE 2: HISTORIC SIMULATION (BACKTEST) ────────────────────────────────
# ---------------------------------------------------------------------------

def _compute_sharpe(returns: pd.Series, risk_free: float = 0.065) -> float:
    if len(returns) < 2 or returns.std() == 0:
        return 0.0
    daily_rf = risk_free / 252
    return round(float((returns - daily_rf).mean() / returns.std() * (252 ** 0.5)), 4)


def _compute_sortino(returns: pd.Series, risk_free: float = 0.065) -> float:
    """Sortino ratio — penalises only downside volatility, not upside."""
    if len(returns) < 2:
        return 0.0
    daily_rf      = risk_free / 252
    excess        = returns - daily_rf
    downside_std  = returns[returns < 0].std()
    if downside_std == 0:
        return 0.0
    return round(float(excess.mean() / downside_std * (252 ** 0.5)), 4)


def _compute_calmar(returns: pd.Series, cum: pd.Series, years: float) -> float:
    """Calmar ratio — CAGR divided by max drawdown. Higher = better risk-adjusted."""
    cagr = ((float(cum.iloc[-1]) / float(cum.iloc[0])) ** (1 / max(years, 0.001)) - 1) * 100
    mdd  = abs(_compute_max_drawdown(cum))
    return round(cagr / mdd, 4) if mdd != 0 else 0.0


def _compute_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Value at Risk — worst daily loss at given confidence level (%)."""
    return round(float(np.percentile(returns, (1 - confidence) * 100)) * 100, 2)


def _compute_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """Conditional VaR (Expected Shortfall) — average loss beyond VaR (%)."""
    var = np.percentile(returns, (1 - confidence) * 100)
    return round(float(returns[returns <= var].mean()) * 100, 2)


def _compute_max_drawdown(cum: pd.Series) -> float:
    roll_max = cum.cummax()
    dd       = (cum - roll_max) / roll_max
    return round(float(dd.min() * 100), 2)


def _compute_cagr(start_val: float, end_val: float, years: float) -> float:
    if years <= 0 or start_val <= 0:
        return 0.0
    return round(((end_val / start_val) ** (1 / years) - 1) * 100, 2)


def _apply_transaction_costs(
    daily_returns: pd.Series,
    rebalance_freq: str = "quarterly",
    brokerage_pct: float = 0.001,
    slippage_pct:  float = 0.0005,
    stt_pct:       float = 0.001,
    stamp_duty_pct:float = 0.00015,
) -> pd.Series:
    """
    Deduct realistic Indian market transaction costs on rebalance dates.

    Indian cost structure per rebalance (buy + sell):
      Brokerage  : 0.10% each way (discount broker like Zerodha)
      Slippage   : 0.05% market impact on entry/exit
      STT        : 0.10% on sell side only
      Stamp duty : 0.015% on buy side
      Total round-trip: ~0.30-0.35%
    """
    total_cost_per_rebalance = (2 * brokerage_pct) + (2 * slippage_pct) + stt_pct + stamp_duty_pct

    freq_map = {
        "monthly":   "MS",
        "quarterly": "QS",
        "yearly":    "YS",
    }
    resample_freq = freq_map.get(rebalance_freq, "QS")

    # Get rebalance dates (first trading day of each period)
    rebalance_dates = daily_returns.resample(resample_freq).first().index

    adjusted = daily_returns.copy()
    for date in rebalance_dates:
        if date in adjusted.index:
            adjusted[date] -= total_cost_per_rebalance

    return adjusted


def _t_test_vs_benchmark(port_returns: pd.Series, bench_returns: pd.Series) -> dict:
    """
    Test whether portfolio alpha vs benchmark is statistically significant.
    Uses paired t-test on daily excess returns.

    Returns t-statistic, p-value, and whether alpha is significant at 95% confidence.
    """
    from scipy import stats
    excess = port_returns.values - bench_returns.reindex(port_returns.index).fillna(0).values
    t_stat, p_value = stats.ttest_1samp(excess, 0)
    return {
        "t_statistic":        round(float(t_stat), 4),
        "p_value":            round(float(p_value), 4),
        "alpha_significant":  bool(p_value < 0.05),
        "confidence_level":   "95%",
        "interpretation": (
            "Alpha is statistically significant — unlikely to be random luck."
            if p_value < 0.05
            else "Alpha is NOT statistically significant — could be random variation."
        ),
    }


def backtest(
    holdings: dict,
    start_date: str,
    end_date: str = None,
    initial_value: float = 100_000,
    include_costs: bool = True,
    rebalance_freq: str = "quarterly",
    out_of_sample_split: float = 0.7,
) -> dict:
    """
    Backtest a portfolio over any historical date range with full quant rigour.

    holdings             — {ticker: allocation_pct}, must sum to 100
    start_date           — "YYYY-MM-DD"  e.g. "2019-01-01"
    end_date             — "YYYY-MM-DD"  (default: today)
    initial_value        — starting capital in ₹
    include_costs        — deduct Indian brokerage, STT, slippage (default True)
    rebalance_freq       — "monthly" | "quarterly" | "yearly"
    out_of_sample_split  — fraction of period used for in-sample (0.7 = first 70%)

    Returns:
      - In-sample vs out-of-sample performance split (avoids overfitting)
      - Transaction-cost-adjusted returns
      - Sharpe, Sortino, Calmar, VaR 95%, CVaR 95%
      - Statistical significance test (t-test vs Nifty)
      - Day-by-day chart, monthly heatmap, per-stock contribution
    """
    end   = end_date or datetime.now().strftime("%Y-%m-%d")
    start = start_date

    total_alloc = sum(holdings.values())
    if abs(total_alloc - 100) > 0.01:
        return {"error": f"Allocations must sum to 100%, got {total_alloc:.1f}%"}

    tickers = list(holdings.keys())
    weights = {t: holdings[t] / 100 for t in tickers}

    all_tickers = tickers + [NIFTY_TICKER]
    prices_raw  = _download_prices(all_tickers, start, end)

    if prices_raw.empty:
        return {"error": "No price data found. Check tickers and date range."}

    prices = prices_raw.ffill()

    port_tickers = [t for t in tickers if t in prices.columns]
    if not port_tickers:
        return {"error": "None of the portfolio tickers had data in this date range."}

    port_weights = {t: weights[t] for t in port_tickers}
    total_w      = sum(port_weights.values())
    port_weights = {t: v / total_w for t, v in port_weights.items()}

    port_prices  = prices[port_tickers]
    nifty_prices = prices[NIFTY_TICKER] if NIFTY_TICKER in prices.columns else None

    # Daily returns
    port_returns = port_prices.pct_change().fillna(0)
    w_array      = np.array([port_weights[t] for t in port_tickers])
    port_daily   = pd.Series(
        (port_returns.values * w_array).sum(axis=1),
        index=port_prices.index
    )

    # Apply Indian transaction costs
    if include_costs:
        port_daily = _apply_transaction_costs(port_daily, rebalance_freq)

    cum_port = (1 + port_daily).cumprod() * initial_value

    # ── In-sample / Out-of-sample split ──────────────────────────────────
    split_idx    = int(len(port_daily) * out_of_sample_split)
    is_returns   = port_daily.iloc[:split_idx]
    oos_returns  = port_daily.iloc[split_idx:]
    is_cum       = (1 + is_returns).cumprod() * initial_value
    oos_cum      = (1 + oos_returns).cumprod() * is_cum.iloc[-1]

    is_metrics = {
        "period":      f"{str(is_returns.index[0].date())} → {str(is_returns.index[-1].date())}",
        "label":       "In-sample (training period)",
        "sharpe":      _compute_sharpe(is_returns),
        "cagr":        _compute_cagr(float(is_cum.iloc[0]), float(is_cum.iloc[-1]),
                                     len(is_returns) / 252),
        "max_drawdown":_compute_max_drawdown(is_cum),
    }
    oos_metrics = {
        "period":      f"{str(oos_returns.index[0].date())} → {str(oos_returns.index[-1].date())}",
        "label":       "Out-of-sample (unseen test period)",
        "sharpe":      _compute_sharpe(oos_returns),
        "cagr":        _compute_cagr(float(oos_cum.iloc[0]), float(oos_cum.iloc[-1]),
                                     len(oos_returns) / 252),
        "max_drawdown":_compute_max_drawdown(oos_cum),
    }
    overfitting_warning = (
        oos_metrics["sharpe"] < is_metrics["sharpe"] * 0.5
        and is_metrics["sharpe"] > 0.5
    )

    # ── Full period metrics ───────────────────────────────────────────────
    final_val    = float(cum_port.iloc[-1])
    total_ret    = round((final_val - initial_value) / initial_value * 100, 2)
    years        = (pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25
    cagr         = _compute_cagr(initial_value, final_val, years)
    sharpe       = _compute_sharpe(port_daily)
    sortino      = _compute_sortino(port_daily)
    calmar       = _compute_calmar(port_daily, cum_port, years)
    max_dd       = _compute_max_drawdown(cum_port)
    var_95       = _compute_var(port_daily, 0.95)
    cvar_95      = _compute_cvar(port_daily, 0.95)
    volatility   = round(float(port_daily.std() * (252 ** 0.5) * 100), 2)
    win_days_pct = round((port_daily > 0).sum() / len(port_daily) * 100, 1)

    # ── Per-stock contribution ────────────────────────────────────────────
    stock_contributions = []
    for ticker in port_tickers:
        s_start = float(port_prices[ticker].iloc[0])
        s_end   = float(port_prices[ticker].iloc[-1])
        s_ret   = (s_end - s_start) / s_start * 100 if s_start else 0
        s_vol   = round(float(port_returns[ticker].std() * (252 ** 0.5) * 100), 2)
        stock_contributions.append({
            "ticker":           ticker,
            "start_price":      round(s_start, 2),
            "end_price":        round(s_end, 2),
            "return_pct":       round(s_ret, 2),
            "weight":           round(port_weights[ticker] * 100, 1),
            "contribution_pct": round(s_ret * port_weights[ticker], 2),
            "volatility_pct":   s_vol,
        })
    stock_contributions.sort(key=lambda x: x["contribution_pct"], reverse=True)

    # ── Monthly heatmap ───────────────────────────────────────────────────
    monthly_ret  = port_daily.resample("ME").apply(lambda r: (1 + r).prod() - 1)
    monthly_data = [
        {
            "year":       idx.year,
            "month":      idx.month,
            "month_name": idx.strftime("%b %Y"),
            "return_pct": round(float(val) * 100, 2),
        }
        for idx, val in monthly_ret.items()
    ]
    best_month  = max(monthly_data, key=lambda x: x["return_pct"]) if monthly_data else None
    worst_month = min(monthly_data, key=lambda x: x["return_pct"]) if monthly_data else None

    # ── Chart data ────────────────────────────────────────────────────────
    chart_series = cum_port.resample("W").last() if years > 1 else cum_port
    daily_chart  = [
        {"date": str(dt.date()), "value": round(float(val), 2)}
        for dt, val in chart_series.items()
    ]

    # ── Nifty benchmark ───────────────────────────────────────────────────
    benchmark      = {}
    significance   = {}
    if nifty_prices is not None:
        nifty_daily = nifty_prices.pct_change().fillna(0)
        cum_nifty   = (1 + nifty_daily).cumprod() * initial_value
        nifty_final = float(cum_nifty.iloc[-1])
        benchmark   = {
            "nifty_final_value":  round(nifty_final, 2),
            "nifty_total_return": round((nifty_final - initial_value) / initial_value * 100, 2),
            "nifty_cagr":         _compute_cagr(initial_value, nifty_final, years),
            "nifty_sharpe":       _compute_sharpe(nifty_daily),
            "nifty_sortino":      _compute_sortino(nifty_daily),
            "nifty_max_drawdown": _compute_max_drawdown(cum_nifty),
            "alpha":              round(total_ret - (nifty_final - initial_value) / initial_value * 100, 2),
            "information_ratio":  round(
                float((port_daily - nifty_daily.reindex(port_daily.index).fillna(0)).mean() /
                      (port_daily - nifty_daily.reindex(port_daily.index).fillna(0)).std() * (252 ** 0.5))
                if (port_daily - nifty_daily.reindex(port_daily.index).fillna(0)).std() != 0 else 0, 4
            ),
            "nifty_chart": [
                {"date": str(dt.date()), "value": round(float(v), 2)}
                for dt, v in (cum_nifty.resample("W").last() if years > 1 else cum_nifty).items()
            ],
        }
        try:
            significance = _t_test_vs_benchmark(
                port_daily,
                nifty_daily.reindex(port_daily.index).fillna(0)
            )
        except Exception:
            significance = {"note": "scipy not installed — skipping significance test"}

    return {
        "mode":              "historic",
        "start_date":        start,
        "end_date":          end,
        "period_years":      round(years, 2),
        "initial_value":     initial_value,
        "final_value":       round(final_val, 2),
        "total_return_pct":  total_ret,
        "cagr_pct":          cagr,
        # Risk-adjusted metrics
        "sharpe_ratio":      sharpe,
        "sortino_ratio":     sortino,
        "calmar_ratio":      calmar,
        "max_drawdown_pct":  max_dd,
        "volatility_pct":    volatility,
        "var_95_daily_pct":  var_95,
        "cvar_95_daily_pct": cvar_95,
        "win_days_pct":      win_days_pct,
        # Cost info
        "costs_included":    include_costs,
        "rebalance_freq":    rebalance_freq,
        # In/out of sample
        "in_sample":         is_metrics,
        "out_of_sample":     oos_metrics,
        "overfitting_warning":overfitting_warning,
        # Detail
        "best_month":        best_month,
        "worst_month":       worst_month,
        "stock_contributions":stock_contributions,
        "monthly_returns":   monthly_data,
        "portfolio_chart":   daily_chart,
        "benchmark":         benchmark,
        "significance_test": significance,
        "tickers_used":      port_tickers,
        "missing_tickers":   [t for t in tickers if t not in port_tickers],
    }


def compare_scenarios(
    scenarios: list,
    start_date: str,
    end_date: str = None,
    initial_value: float = 100_000,
) -> dict:
    """
    Compare multiple portfolio scenarios on the same historic period.

    scenarios: list of dicts, each with "name" and "holdings"
    e.g. [
        {"name": "All HDFC", "holdings": {"HDFCBANK.NS": 100}},
        {"name": "IT heavy", "holdings": {"TCS.NS": 60, "INFY.NS": 40}},
    ]

    Returns side-by-side comparison of all metrics.
    """
    results = []
    for sc in scenarios:
        bt = backtest(sc["holdings"], start_date, end_date, initial_value)
        if "error" in bt:
            results.append({"name": sc["name"], "error": bt["error"]})
        else:
            results.append({
                "name":             sc["name"],
                "total_return_pct": bt["total_return_pct"],
                "cagr_pct":         bt["cagr_pct"],
                "sharpe_ratio":     bt["sharpe_ratio"],
                "max_drawdown_pct": bt["max_drawdown_pct"],
                "volatility_pct":   bt["volatility_pct"],
                "final_value":      bt["final_value"],
                "alpha_vs_nifty":   bt["benchmark"].get("alpha"),
                "chart":            bt["portfolio_chart"],
            })
    # Rank by total return
    valid = [r for r in results if "error" not in r]
    for r in valid:
        r["rank"] = sorted(valid, key=lambda x: x["total_return_pct"], reverse=True).index(r) + 1
    return {
        "start_date":    start_date,
        "end_date":      end_date or datetime.now().strftime("%Y-%m-%d"),
        "initial_value": initial_value,
        "scenarios":     results,
    }


# ---------------------------------------------------------------------------
# Saved portfolios
# ---------------------------------------------------------------------------

def save_portfolio(name: str, holdings: dict, user_id: str = "public") -> dict:
    _init_db()
    total = sum(holdings.values())
    if abs(total - 100) > 0.01:
        return {"error": f"Allocations must sum to 100%, got {total:.1f}%"}
    now = datetime.now().isoformat()
    import db as _db
    conn = get_conn()
    try:
        if _db.IS_POSTGRES:
            sql = ("INSERT INTO portfolios (user_id, name, holdings, created_at, last_updated) "
                   "VALUES (?,?,?,?,?) ON CONFLICT (user_id, name) DO UPDATE SET "
                   "holdings = EXCLUDED.holdings, last_updated = EXCLUDED.last_updated")
            conn.execute(sql, (user_id, name, json.dumps(holdings), now, now))
        else:
            # SQLite: delete-then-insert per user (INSERT OR REPLACE can't target a
            # composite index cleanly across old schemas)
            conn.execute("DELETE FROM portfolios WHERE user_id = ? AND name = ?", (user_id, name))
            conn.execute("INSERT INTO portfolios (user_id, name, holdings, created_at, last_updated) "
                         "VALUES (?,?,?,?,?)", (user_id, name, json.dumps(holdings), now, now))
        conn.commit()
        return {"status": "saved", "name": name, "holdings": holdings}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def load_portfolio(name: str, user_id: str = "public") -> dict:
    _init_db()
    conn = get_conn()
    row  = conn.execute(
        "SELECT name, holdings, created_at FROM portfolios WHERE name = ? AND user_id = ?",
        (name, user_id)
    ).fetchone()
    conn.close()
    if not row:
        return {"error": f"Portfolio '{name}' not found"}
    return {"name": row[0], "holdings": json.loads(row[1]), "created_at": row[2]}


def list_portfolios(user_id: str = "public") -> list:
    _init_db()
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, created_at FROM portfolios WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [{"name": r[0], "created_at": r[1]} for r in rows]


# ---------------------------------------------------------------------------
# Weekly challenges
# ---------------------------------------------------------------------------

CHALLENGES = [
    {
        "id": "macro_event",
        "type": "macro_event",
        "title": "Macro Event Challenge",
        "description": (
            "The RBI has just cut the repo rate by 50 bps. "
            "Pick the ONE sector you believe will benefit most in the next 2 weeks."
        ),
        "options": ["Banking & NBFCs", "Real Estate", "Auto & Consumer Durables", "IT & Tech", "FMCG"],
        "correct_sector": "Banking & NBFCs",
        "explanation": (
            "Rate cuts immediately widen NIMs for banks and lower borrowing costs, "
            "boosting loan demand and NBFC books."
        ),
        "expires_at": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
    },
    {
        "id": "sector_rotation",
        "type": "sector_rotation",
        "title": "Sector Rotation Challenge",
        "description": (
            "Crude oil has surged 20% in a month. "
            "Rank these sectors from most-impacted-negatively to least."
        ),
        "options": ["Aviation", "IT", "Pharma", "Oil & Gas upstream"],
        "correct_ranking": ["Aviation", "Oil & Gas upstream", "Pharma", "IT"],
        "explanation": "Aviation bears highest cost pain. IT earns in USD and is largely insulated.",
        "expires_at": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
    },
    {
        "id": "stock_picking",
        "type": "stock_picking",
        "title": "Stock Picking Challenge",
        "description": (
            "Pick the one stock you expect to outperform Nifty 50 by the most over the next month."
        ),
        "options": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "SUNPHARMA.NS"],
        "expires_at": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
        "note": "Compare your pick vs index after 1 month using /simulator/historic.",
    },
    {
        "id": "risk_management",
        "type": "risk_management",
        "title": "Risk Management Challenge",
        "description": (
            "Design a 3-stock portfolio that minimises drawdown while targeting >12% annual return. "
            "Your Sharpe ratio must be > 0.8. Test it with /simulator/historic."
        ),
        "constraints": {"min_stocks": 3, "max_single_pct": 50, "target_return": 12, "min_sharpe": 0.8},
        "expires_at": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
    },
    {
        "id": "earnings_prediction",
        "type": "earnings_prediction",
        "title": "Earnings Prediction Challenge",
        "description": (
            "TCS reports Q4 results next Friday. "
            "Predict: revenue growth YoY (%), net margin (%), and whether guidance is positive or cautious."
        ),
        "inputs_required": ["revenue_growth_pct", "net_margin_pct", "guidance"],
        "guidance_options": ["Positive", "Cautious", "Neutral"],
        "expires_at": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
    },
]


def get_challenges() -> list:
    return CHALLENGES


def submit_challenge(challenge_id: str, user_pick: dict) -> dict:
    _init_db()
    challenge = next((c for c in CHALLENGES if c["id"] == challenge_id), None)
    if not challenge:
        return {"error": f"Challenge '{challenge_id}' not found"}
    now = datetime.now().isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO challenge_entries (challenge_id, user_pick, submitted_at) VALUES (?,?,?)",
        (challenge_id, json.dumps(user_pick), now)
    )
    conn.commit()
    conn.close()
    feedback = {}
    if challenge_id == "macro_event" and "sector" in user_pick:
        correct = challenge["correct_sector"]
        feedback = {
            "correct": user_pick["sector"] == correct,
            "message": (
                f"Correct! {challenge['explanation']}" if user_pick["sector"] == correct
                else f"The best answer was '{correct}'. {challenge['explanation']}"
            ),
        }
    return {
        "status": "submitted", "challenge_id": challenge_id,
        "submitted_at": now,
        "feedback": feedback or {"message": "Check back after the challenge expires for results."},
    }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Testing simulator.py")
    print("=" * 60)

    # ── Real-time simulation ──
    print("\n── REAL-TIME SIMULATION ──")
    print("\n1. Starting paper trade: HDFC 60% + TCS 40% with ₹1,00,000")
    result = start_simulation(
        name="test_rt_sim",
        holdings={"HDFCBANK.NS": 60, "TCS.NS": 40},
        initial_value=100_000,
    )
    if "error" in result:
        print(f"   Error: {result['error']}")
    else:
        print(f"   Started at {result['started_at']}")
        for p in result["positions"]:
            print(f"   {p['ticker']:15s}  entry ₹{p['entry_price']}  units={p['units']:.2f}")

    print("\n2. Checking live P&L...")
    pnl = get_simulation_pnl("test_rt_sim")
    if "error" not in pnl:
        print(f"   Portfolio value : ₹{pnl['current_value']:,.2f}")
        print(f"   Total P&L       : ₹{pnl['total_pnl_inr']:+,.2f} ({pnl['total_pnl_pct']:+.2f}%)")
        print(f"   Status          : {pnl['overall_status'].upper()}")
        for p in pnl["positions"]:
            arrow = "▲" if p["pnl_inr"] >= 0 else "▼"
            print(f"   {arrow} {p['ticker']:15s}  ₹{p['pnl_inr']:+,.2f}  ({p['pnl_pct']:+.2f}%)")

    # ── Historic simulation ──
    print("\n── HISTORIC SIMULATION ──")
    print("\n3. Backtesting HDFC 100% from 2019 to 2022...")
    bt = backtest(
        holdings={"HDFCBANK.NS": 100},
        start_date="2019-01-01",
        end_date="2022-12-31",
        initial_value=100_000,
    )
    if "error" in bt:
        print(f"   Error: {bt['error']}")
    else:
        print(f"   Period     : {bt['start_date']} → {bt['end_date']} ({bt['period_years']} years)")
        print(f"   ₹1L grew to: ₹{bt['final_value']:,.2f}")
        print(f"   Total return : {bt['total_return_pct']}%")
        print(f"   CAGR         : {bt['cagr_pct']}%")
        print(f"   Sharpe ratio : {bt['sharpe_ratio']}")
        print(f"   Max drawdown : {bt['max_drawdown_pct']}%")
        print(f"   Best month   : {bt['best_month']}")
        print(f"   Worst month  : {bt['worst_month']}")
        if bt["benchmark"]:
            bm = bt["benchmark"]
            print(f"   Nifty return : {bm['nifty_total_return']}%")
            print(f"   Alpha        : {bm['alpha']}%")

    print("\n4. Comparing 2 scenarios (2020–2023)...")
    comp = compare_scenarios(
        scenarios=[
            {"name": "HDFC only",   "holdings": {"HDFCBANK.NS": 100}},
            {"name": "TCS + Infy",  "holdings": {"TCS.NS": 60, "INFY.NS": 40}},
        ],
        start_date="2020-01-01",
        end_date="2023-12-31",
        initial_value=100_000,
    )
    for sc in comp["scenarios"]:
        if "error" not in sc:
            print(f"   #{sc['rank']} {sc['name']:20s}  return={sc['total_return_pct']}%  "
                  f"CAGR={sc['cagr_pct']}%  Sharpe={sc['sharpe_ratio']}")
    
    # Cleanup
    delete_simulation("test_rt_sim")
    print("\n" + "=" * 60)
    print("simulator.py test complete")
    print("=" * 60)
