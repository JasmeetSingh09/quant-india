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
import threading
from db import get_conn, IntegrityError, legacy_add_column  # noqa: F401
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

_DB_READY = False
_DB_INIT_LOCK = threading.Lock()


def _init_db():
    """
    Create/migrate the schema — ONCE per process.

    This used to run on EVERY simulator call (12 call sites), issuing ~10 DDL
    statements (CREATE TABLE / ALTER / CREATE INDEX). Those are all WRITES, so
    every read request was taking write locks and contending with the background
    Top Picks scan, prediction snapshots and the news cache. Under that
    contention reads hit SQLite's 30s lock timeout and the endpoint 500'd —
    which looked like "my simulations vanished".

    The schema does not change at runtime, so do it once and let reads be reads.
    """
    global _DB_READY
    if _DB_READY:
        return
    with _DB_INIT_LOCK:
        if _DB_READY:            # another thread won the race
            return
        _init_db_locked()
        _DB_READY = True


def _init_db_locked():
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
            status          TEXT DEFAULT 'active',
            -- Demo portfolios are REAL simulations tracked against live prices;
            -- the flag exists only so the leaderboard can label them honestly
            -- rather than passing them off as another anonymous user's result.
            is_demo         INTEGER DEFAULT 0
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
    # migrate older SQLite tables that predate per-user support (best effort;
    # no-ops on Postgres — see db.legacy_add_column).
    import db as _db
    for tbl in ("simulations", "sim_positions", "sim_snapshots", "portfolios"):
        legacy_add_column(conn, tbl, "user_id")

    # Old SQLite tables were created with a table-level UNIQUE(name) that blocks
    # two users from sharing a sim/portfolio name. ALTER can't drop it, so rebuild
    # the table without it. (Postgres deploys start fresh, so this only runs on
    # legacy local SQLite DBs.)
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

    conn = get_conn()
    try:
        if _db.IS_POSTGRES:
            conn.execute("ALTER TABLE simulations ADD COLUMN IF NOT EXISTS is_demo INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE simulations ADD COLUMN IF NOT EXISTS cash REAL DEFAULT 0")
        else:
            conn.execute("ALTER TABLE simulations ADD COLUMN is_demo INTEGER DEFAULT 0")
            try:

                conn.execute("ALTER TABLE simulations ADD COLUMN cash REAL DEFAULT 0")

            except Exception:

                pass          # already present
        conn.commit()
    except Exception:
        pass          # already present
    finally:
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

_SPLIT_CACHE: dict = {}
_SPLIT_TTL = 6 * 3600


def _split_factor_since(ticker: str, entry_date) -> float:
    """
    Cumulative share multiplier from splits and bonus issues since entry.

    A position is stored as fixed units bought at an entry price, and valued as
    units x current price. That holds until the company splits its stock: the
    price halves in a 1:2 split, the stored units do not, and the simulator
    reports a 50% loss that never happened. Bonus issues do the same, and in
    this market they are common enough that this is not an edge case.

    Returns 1.0 on any failure — never a number that would silently rewrite a
    portfolio on bad data.
    """
    import time
    if not ticker or not entry_date:
        return 1.0
    key = (ticker, str(entry_date)[:10])
    hit = _SPLIT_CACHE.get(key)
    now = time.time()
    if hit and now - hit[0] < _SPLIT_TTL:
        return hit[1]

    factor = 1.0
    try:
        import yfinance as yf
        import pandas as pd
        splits = yf.Ticker(ticker).splits
        if splits is not None and len(splits):
            d0 = pd.Timestamp(str(entry_date)[:10])
            idx = splits.index
            try:
                if getattr(idx, "tz", None) is not None:
                    d0 = d0.tz_localize(idx.tz)
            except Exception:
                pass
            for r in splits[idx > d0].values:
                r = float(r)
                if r > 0:
                    factor *= r
    except Exception:
        factor = 1.0

    if len(_SPLIT_CACHE) > 2000:
        _SPLIT_CACHE.clear()
    _SPLIT_CACHE[key] = (now, factor)
    return factor


_DIV_CACHE: dict = {}
_DIV_TTL = 6 * 3600


def _dividends_since(ticker: str, entry_date, units: float) -> float:
    """
    Cash dividends paid on a holding since it was bought.

    The backtest uses split- and dividend-adjusted prices, so it reports TOTAL
    return. The live simulator tracked price only, so the same portfolio gave two
    different answers in two halves of the same product — and the half users
    spend most time in was the one understating income.

    Paid as cash rather than reinvested: that is what actually lands in a demat
    account, and silently reinvesting would overstate returns in the other
    direction.

    Returns 0.0 on any failure. A dividend that cannot be verified must not be
    credited.
    """
    import time
    if not ticker or not entry_date or not units:
        return 0.0
    key = (ticker, str(entry_date)[:10])
    hit = _DIV_CACHE.get(key)
    now = time.time()
    total = None
    if hit and now - hit[0] < _DIV_TTL:
        total = hit[1]
    if total is None:
        total = 0.0
        try:
            import yfinance as yf
            import pandas as pd
            div = yf.Ticker(ticker).dividends
            if div is not None and len(div):
                d0 = pd.Timestamp(str(entry_date)[:10])
                idx = div.index
                try:
                    if getattr(idx, "tz", None) is not None:
                        d0 = d0.tz_localize(idx.tz)
                except Exception:
                    pass
                total = float(div[idx > d0].sum())
        except Exception:
            total = 0.0
        if len(_DIV_CACHE) > 2000:
            _DIV_CACHE.clear()
        _DIV_CACHE[key] = (now, total)
    return float(total) * float(units)


def _live_price(ticker: str) -> float | None:
    """
    Fetch the latest price for a ticker.

    Prefers the shared cached price feed (data_fetcher.get_current_price), which
    caches for 45s-15min and serves stale on a Yahoo throttle. Starting a
    simulation calls this once PER HOLDING, and raw yfinance fast_info/history
    have no timeout and hang for 10s+ each on Render's throttled IP — five
    holdings ran past the 60s request timeout. Fall back to raw yfinance only if
    the cached feed has nothing.
    """
    try:
        from data_fetcher import get_current_price
        r = get_current_price(ticker)
        p = r.get("price")
        if p and p > 0:
            return round(float(p), 4)
    except Exception:
        pass
    # Fallbacks (used mainly for commodity futures the cache may not hold)
    tk = yf.Ticker(ticker)
    try:
        p = tk.fast_info.last_price
        if p and p == p and p > 0:
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
    # Use the shared CACHED .info (data_fetcher.get_info) rather than a fresh
    # yf.Ticker(...).info per call — the latter is a full, slow fetch just for a
    # cosmetic name, and starting a sim called it once per holding.
    try:
        from data_fetcher import get_info
        nm = (get_info(ticker) or {}).get("shortName")
        if nm:
            return nm
    except Exception:
        pass
    return ticker.replace(".NS", "").replace(".BO", "")


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

def _price_on(ticker: str, date_str: str):
    """Closing price on (or the first trading day after) `date_str`.

    Used to start a simulation in the past so it has REAL performance from day
    one — the return is genuine NSE price history, not an invented number.
    Returns None if no bar exists, and the caller drops that holding rather than
    substituting a live price, which would silently misstate the entry.
    """
    try:
        d = datetime.fromisoformat(date_str)
        end = (d + timedelta(days=12)).strftime("%Y-%m-%d")
        df = yf.download(ticker, start=d.strftime("%Y-%m-%d"), end=end,
                         progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        s_ = df["Close"].squeeze().dropna()
        return round(float(s_.iloc[0]), 2) if len(s_) else None
    except Exception:
        return None


def start_simulation(
    name: str,
    holdings: dict,
    initial_value: float = 100_000,
    user_id: str = "public",
    is_demo: bool = False,
    entry_date: str = None,
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

    # The name becomes a URL path segment on every later call (pnl, history,
    # add, remove, delete), so normalise it at the source. A trailing space —
    # "Example " was live in production — made every one of those lookups miss,
    # so the simulation could be created but never deleted.
    name = (name or "").strip()
    if not name:
        return {"error": "Simulation name is required"}
    if "/" in name or "\\" in name:
        return {"error": "Simulation name cannot contain slashes"}
    if len(name) > 60:
        return {"error": "Simulation name must be 60 characters or fewer"}

    # Rounded per-stock weights rarely sum to exactly 100: 40 + 29.1 + 22.2 +
    # 6.69 + 2 = 99.99, whose difference from 100 evaluates to
    # 0.010000000000005 in floating point and tripped a 0.01 tolerance. The
    # message then printed 99.99 as "100.0", so it read as "must sum to 100%,
    # got 100.0%". Allow a sane rounding tolerance, report the real number to
    # 2dp, and renormalise so downstream maths still uses exact weights.
    total_alloc = sum(holdings.values())
    if abs(total_alloc - 100) > 0.5:
        return {"error": f"Allocations must sum to 100%, got {total_alloc:.2f}%"}
    if total_alloc > 0 and abs(total_alloc - 100) > 1e-9:
        holdings = {t: v * 100.0 / total_alloc for t, v in holdings.items()}
    for t in holdings:
        # Accept NSE/BSE stocks (.NS/.BO), commodity futures (=F), and indices (^)
        if not (t.endswith(".NS") or t.endswith(".BO") or "=F" in t or t.startswith("^")):
            return {"error": f"Unsupported ticker '{t}' (use .NS stocks or commodity futures like GC=F)"}

    now = datetime.now().isoformat()
    started = entry_date if entry_date else now
    positions = []
    failed    = []

    # Resolve every holding's live price + name IN PARALLEL. Doing this
    # sequentially meant N slow (throttled) network round-trips back-to-back,
    # which pushed a 5-stock sim past the 60s request timeout. Now the wall time
    # is roughly one fetch, not the sum.
    import concurrent.futures as _cf
    def _resolve(t):
        # A dated start prices the entry from history; otherwise today's live price.
        px = _price_on(t, entry_date) if entry_date else _live_price(t)
        return t, px, _company_name(t)
    resolved = {}
    with _cf.ThreadPoolExecutor(max_workers=min(8, len(holdings) * 2 or 1)) as _ex:
        for t, p, nm in _ex.map(_resolve, list(holdings.keys())):
            resolved[t] = (p, nm)

    from execution import cost_breakdown, units_for
    # Kept apart from `failed`: "we could not price this" and "this allocation
    # cannot buy a share" are different problems with different fixes.
    too_small = []
    # Costs are genuinely spent; the remainder that could not buy a whole share
    # is still the user's money and becomes the opening cash balance.
    opening_cost = 0.0
    opening_cash = 0.0
    for ticker, pct in holdings.items():
        price, cname = resolved.get(ticker, (None, ticker))
        if price is None or price <= 0:
            failed.append(ticker)
            continue
        # Starting a simulation is buying, and buying costs money. This path
        # skipped the cost model entirely while add_position applied it, so a
        # brand-new portfolio opened at exactly break-even — flattering, and
        # inconsistent with the same purchase made a minute later through /add.
        alloc_value = initial_value * pct / 100
        _c = cost_breakdown(ticker, alloc_value, side="buy")
        _spend = _c.get("invested_after_costs", alloc_value) if "error" not in _c else alloc_value
        _u = units_for(_spend, price)
        units = _u.get("units", 0) if "error" not in _u else 0
        if units <= 0:
            # The price fetched fine — this allocation simply cannot buy one
            # whole share. Reporting it as a price-fetch failure blamed the
            # user's ticker for something the ticker had nothing to do with,
            # and told them to check a symbol that was never wrong.
            _need_pct = price / float(initial_value) * 100 * 1.01
            too_small.append({
                "ticker": ticker, "price": round(price, 2),
                "allocated": round(alloc_value, 2),
                "min_pct_needed": round(_need_pct, 2),
                "min_capital_needed": round(price * 100.0 / max(pct, 0.01), 0),
            })
            continue
        invested_value = units * price
        opening_cost += (_c.get("total_cost", 0.0) if "error" not in _c else 0.0)
        opening_cash += (_u.get("leftover_cash", 0.0) if "error" not in _u else 0.0)
        positions.append({
            "ticker":        ticker,
            "company_name":  cname,
            "allocation_pct":pct,
            "units":         units,
            "entry_price":   price,
            # Entry value is what was actually put into the stock. Recording the
            # pre-cost figure would hide the cost inside a phantom loss on day
            # one instead of showing it as the cost it is.
            "entry_value":   invested_value,
            "entry_date":    now,
        })

    if failed:
        return {"error": f"Could not fetch prices for: {failed}. Check ticker symbols."}
    if too_small:
        _t = too_small[0]
        _name = _t["ticker"].replace(".NS", "")
        _all = ", ".join(
            f"{x['ticker'].replace('.NS','')} needs {x['min_pct_needed']:.1f}%"
            for x in too_small)
        return {"error": (
            f"{_name} costs Rs {_t['price']:,.0f} a share, but {_t['allocated']:,.0f} "
            f"rupees was allocated to it — not enough for one whole share. "
            f"NSE does not trade fractions. Either raise the weight ({_all}), or "
            f"increase capital to about Rs {_t['min_capital_needed']:,.0f}."),
            "too_small": too_small}
    if not positions:
        return {"error": "Could not fetch prices for any ticker. Check symbols."}

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO simulations (user_id, name, initial_value, started_at, last_checked, status, is_demo) "
            "VALUES (?, ?, ?, ?, ?, 'active', ?)",
            (user_id, name, initial_value, started, now, 1 if is_demo else 0)
        )
        # Seed the balance with what could not be invested, so capital is
        # conserved: stock + cash + costs = the money paid in.
        _ensure_cash_column()
        try:
            conn.execute("UPDATE simulations SET cash = ? WHERE name = ? AND user_id = ?",
                         (round(opening_cash, 2), name, user_id))
        except Exception:
            pass
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


def _days_since(iso) -> int | None:
    """Whole days since an ISO timestamp, or None if it cannot be parsed."""
    try:
        from datetime import datetime as _dt
        return max(0, (_dt.now() - _dt.fromisoformat(str(iso)[:19])).days)
    except Exception:
        return None

def _market_note(positions: list) -> str | None:
    """
    Explain a flat portfolio when the explanation is 'the market was shut'.

    Returns None when anything has actually moved, because a note that appears
    every time is a note nobody reads.
    """
    if not positions:
        return None
    moved = [p for p in positions if abs(p.get("pnl_pct") or 0) > 0.001]
    if moved:
        return None
    try:
        from data_fetcher import is_market_open
        if is_market_open():
            # Flat while open is unusual enough to be worth flagging as odd
            # rather than explaining away.
            return ("Every holding is showing exactly its entry price while the "
                    "market is open. That is unusual — prices may be stale.")
    except Exception:
        pass
    day = datetime.now().strftime("%A")
    weekend = day in ("Saturday", "Sunday")
    return (f"NSE is closed{' for the weekend' if weekend else ''}, so the last "
            f"traded price is still the one you bought at. Nothing has moved "
            f"because nothing has traded — this is not a stalled feed. Any "
            f"difference from your starting capital is the cost of opening the "
            f"positions, shown in the breakdown above.")


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

    # Resolve every position's live price in parallel — same fix as
    # start_simulation's _resolve() below; a sim with several holdings was
    # re-hitting the serial-fetch timeout on every P&L check.
    import concurrent.futures as _cf
    live_by_ticker = {}
    if positions_raw:
        tickers = [row[0] for row in positions_raw]
        with _cf.ThreadPoolExecutor(max_workers=min(8, len(tickers) * 2 or 1)) as _ex:
            for t, p in zip(tickers, _ex.map(_live_price, tickers)):
                live_by_ticker[t] = p

    for row in positions_raw:
        ticker, cname, alloc_pct, units, entry_price, entry_value, entry_date = row
        current_price = live_by_ticker.get(ticker)
        if current_price is None:
            current_price = entry_price   # fallback

        # Adjusted for splits and bonuses since entry: a 1:2 split
        # halves the price while stored units stay put, which would
        # otherwise read as a 50% loss that never happened.
        units = units * _split_factor_since(ticker, entry_date)
        current_value = units * current_price
        # Dividends received, as cash. Without this the live simulator reports
        # price return while the backtest reports total return, so the same
        # portfolio gives two different answers in one product.
        dividends_inr = _dividends_since(ticker, entry_date, units)
        pnl_inr       = (current_value + dividends_inr) - entry_value
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
            "dividends_inr": round(dividends_inr, 2),
            "pnl_pct":       round(pnl_pct, 2),
            "status":        "profit" if pnl_inr >= 0 else "loss",
        })

    # Uninvested cash is part of the portfolio. Leaving it out would report a
    # loss the moment money sits idle, and would make a portfolio look better
    # simply for being fully invested — which is cash drag arriving as a bug.
    # A fresh connection: the one above was closed before the prices were
    # fetched. Reading cash on the closed handle raised, and _get_cash swallowed
    # it into 0.0 — so the balance silently disappeared from the portfolio
    # instead of failing loudly. A helper that returns a plausible number on
    # error hides exactly this.
    _ensure_cash_column()
    _cconn = get_conn()
    try:
        _cash_bal = _get_cash(_cconn, name, user_id)
    finally:
        _cconn.close()
    total_current = total_current + _cash_bal
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
        # How long the money has actually been at work. The coach needs it to
        # tell short-term from long-term capital gains, which is a 7.5-point
        # difference in the tax rate rather than a detail.
        "days_running":    _days_since(started_at),
        "initial_value":   initial_value,
        "current_value":   round(total_current, 2),
        "cash":            round(_cash_bal, 2),
        "total_pnl_inr":   round(total_pnl_inr, 2),
        "total_pnl_pct":   round(total_pnl_pct, 2),
        # Split so "-Rs 209" is attributable. Without this a user reasonably
        # concludes their stocks lost money on day one, when the whole figure is
        # the cost of buying them.
        "pnl_breakdown": {
            "market_inr": round(sum(p["pnl_inr"] for p in positions), 2),
            "costs_inr": round(total_pnl_inr - sum(p["pnl_inr"] for p in positions), 2),
            "net_inr": round(total_pnl_inr, 2),
            "note": ("Market is how the holdings moved. Costs are brokerage, STT, "
                     "stamp duty, GST and estimated impact, plus any rupees that "
                     "could not buy a whole share."),
        },
        # A simulation opened on a Friday and checked on a Sunday shows the
        # same price it opened at, a flat line, and 0.00% on every holding —
        # which is indistinguishable from a broken price feed, and gets read as
        # one. The prices are right; nothing has traded. Saying so is the whole
        # fix, and it costs one sentence.
        "market_note":     _market_note(positions),
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


def _ensure_cash_column():
    """
    Add the cash balance to existing simulations.

    Runs on its own connection: a failed ALTER poisons the whole transaction on
    Postgres, which is what previously 500'd unrelated endpoints.

    Existing simulations get cash = 0, which is the honest migration. Under the
    old model every rupee deposited was immediately fully invested, so zero
    uninvested cash is exactly what those portfolios held — nobody's recorded
    position changes value because of this.
    """
    conn = get_conn()
    try:
        if IS_POSTGRES:
            conn.execute("ALTER TABLE simulations ADD COLUMN IF NOT EXISTS cash REAL DEFAULT 0")
        else:
            conn.execute("ALTER TABLE simulations ADD COLUMN cash REAL DEFAULT 0")
        conn.commit()
    except Exception:
        pass          # already present
    finally:
        conn.close()


def _get_cash(conn, sim_name: str, user_id: str) -> float:
    try:
        row = conn.execute(
            "SELECT cash FROM simulations WHERE name = ? AND user_id = ?",
            (sim_name, user_id)).fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0
    except Exception:
        return 0.0


def _set_cash(conn, sim_name: str, user_id: str, amount: float):
    conn.execute("UPDATE simulations SET cash = ? WHERE name = ? AND user_id = ?",
                 (round(float(amount), 2), sim_name, user_id))


def deposit(sim_name: str, amount: float, user_id: str = "public") -> dict:
    """Pay money into the simulation. It sits as cash until it buys something."""
    _init_db(); _ensure_cash_column()
    if amount is None or amount <= 0:
        return {"error": "Deposit must be positive."}
    conn = get_conn()
    row = conn.execute("SELECT initial_value FROM simulations WHERE name = ? AND user_id = ?",
                       (sim_name, user_id)).fetchone()
    if not row:
        conn.close()
        return {"error": f"Simulation '{sim_name}' not found"}
    cash = _get_cash(conn, sim_name, user_id) + float(amount)
    _set_cash(conn, sim_name, user_id, cash)
    conn.execute("UPDATE simulations SET initial_value = ? WHERE name = ? AND user_id = ?",
                 (float(row[0]) + float(amount), sim_name, user_id))
    conn.commit(); conn.close()
    return {"status": "deposited", "amount": round(float(amount), 2),
            "cash": round(cash, 2),
            "note": f"Rs {amount:,.0f} added. Cash balance is now Rs {cash:,.0f}."}


def withdraw(sim_name: str, amount: float, user_id: str = "public") -> dict:
    """
    Take money out — but only money that is actually there.

    Refusing an over-withdrawal is the whole point of having a balance. A
    simulator that lets you spend what you do not have teaches the one lesson
    investing never does.
    """
    _init_db(); _ensure_cash_column()
    if amount is None or amount <= 0:
        return {"error": "Withdrawal must be positive."}
    conn = get_conn()
    row = conn.execute("SELECT initial_value FROM simulations WHERE name = ? AND user_id = ?",
                       (sim_name, user_id)).fetchone()
    if not row:
        conn.close()
        return {"error": f"Simulation '{sim_name}' not found"}
    cash = _get_cash(conn, sim_name, user_id)
    if float(amount) > cash + 1e-9:
        conn.close()
        return {"error": (f"Not enough cash. You have Rs {cash:,.2f} uninvested and "
                          f"asked for Rs {amount:,.2f}. Sell a holding first.")}
    cash -= float(amount)
    _set_cash(conn, sim_name, user_id, cash)
    conn.execute("UPDATE simulations SET initial_value = ? WHERE name = ? AND user_id = ?",
                 (max(float(row[0]) - float(amount), 0.0), sim_name, user_id))
    conn.commit(); conn.close()
    return {"status": "withdrawn", "amount": round(float(amount), 2),
            "cash": round(cash, 2),
            "note": f"Rs {amount:,.0f} withdrawn. Cash balance is now Rs {cash:,.0f}."}


def buy_from_cash(sim_name: str, ticker: str, amount: float,
                  user_id: str = "public") -> dict:
    """
    Buy using money already in the simulation, refusing to overspend.

    add_position() deposits fresh capital and buys with it, which is convenient
    and is how every existing portfolio was built — so it stays. This is the
    realistic path: a fixed pot, and every purchase competes with every other
    for it. That constraint is most of what makes allocation a decision rather
    than a wish list.
    """
    _init_db(); _ensure_cash_column()
    if amount is None or amount <= 0:
        return {"error": "Amount must be positive."}
    conn = get_conn()
    exists = conn.execute("SELECT 1 FROM simulations WHERE name = ? AND user_id = ?",
                          (sim_name, user_id)).fetchone()
    if not exists:
        conn.close()
        return {"error": f"Simulation '{sim_name}' not found"}
    cash = _get_cash(conn, sim_name, user_id)
    conn.close()

    if float(amount) > cash + 1e-9:
        return {"error": (f"Not enough cash. You have Rs {cash:,.2f} uninvested and "
                          f"tried to spend Rs {amount:,.2f}. Deposit more, or sell "
                          f"something first — a real account works the same way."),
                "cash": round(cash, 2)}

    res = add_position(sim_name, ticker, amount, user_id=user_id, _from_cash=True)
    return res

def add_position(sim_name: str, ticker: str, amount: float, user_id: str = "public",
                 _from_cash: bool = False) -> dict:
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

    now = datetime.now().isoformat()

    # Charge what the trade would actually cost, and buy whole shares with what
    # is left. Previously the full amount bought stock at the displayed price in
    # fractional units, instantly, at any hour — so the paper simulator and the
    # historical backtest disagreed about whether trading is free. Slippage is
    # scaled by the order's size against the stock's own daily turnover, which is
    # what decides whether an order moves the price.
    from execution import cost_breakdown, units_for, market_status
    _mkt  = market_status()
    _cost = cost_breakdown(ticker, amount, side="buy")
    if "error" in _cost:
        conn.close()
        return {"error": _cost["error"]}
    _net   = _cost["invested_after_costs"]
    _units = units_for(_net, price)
    if "error" in _units:
        conn.close()
        return {"error": _units["error"]}
    if _units["units"] <= 0:
        conn.close()
        return {"error": (f"Rs {amount:,.0f} is not enough to buy one share of "
                          f"{ticker} at Rs {price:,.2f} after costs.")}

    _ensure_cash_column()
    buy_units = _units["units"]
    # Capital actually put to work: the shares bought. Costs and the leftover
    # rupees that could not buy a whole share are both real and both excluded.
    invested  = buy_units * price
    amount    = invested
    new_init  = sim[0] + invested

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
            f"Bought {buy_units} more share(s) of {ticker} at ₹{price:,.2f} "
            f"(₹{invested:,.0f} invested). Costs ₹{_cost['total_cost']:,.0f}, "
            f"₹{_units['leftover_cash']:,.0f} left uninvested. "
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
        status, note = "added", (
            f"Bought {buy_units} share(s) of {ticker} at ₹{price:,.2f} "
            f"(₹{invested:,.0f} invested). Costs ₹{_cost['total_cost']:,.0f}, "
            f"₹{_units['leftover_cash']:,.0f} could not buy a whole share.")

    # Money that did not buy a whole share does not evaporate — it stays as cash,
    # which is what a real account does and what makes the balance meaningful.
    _leftover = float(_units.get("leftover_cash") or 0.0)
    _cash = _get_cash(conn, sim_name, user_id)
    if _from_cash:
        # Spending an existing balance: the whole order amount leaves cash, and
        # the unspendable remainder comes back. Capital does not grow.
        _cash = _cash - float(_cost["amount"]) + _leftover
        new_init = sim[0]
    else:
        # Fresh capital: only the invested part counts toward capital, and the
        # remainder is held as cash rather than quietly vanishing.
        _cash = _cash + _leftover
        new_init = sim[0] + invested + _leftover
    _set_cash(conn, sim_name, user_id, max(_cash, 0.0))
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
        # Returned so the interface can show what the trade cost and when it
        # would really have filled, rather than only what the user typed.
        "execution": {
            "executed_at": now,
            "market": _mkt,
            "costs": _cost,
            "shares": buy_units,
            "leftover_cash": _units["leftover_cash"],
        },
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
        "SELECT units, entry_price, entry_value, entry_date FROM sim_positions WHERE sim_name = ? AND ticker = ? AND user_id = ?",
        (sim_name, ticker, user_id)
    ).fetchone()
    if not pos:
        conn.close()
        return {"error": f"{ticker} is not in this simulation."}

    units, entry_price, entry_value, entry_date = pos
    n_positions = conn.execute(
        "SELECT COUNT(*) FROM sim_positions WHERE sim_name = ? AND user_id = ?", (sim_name, user_id)
    ).fetchone()[0]
    if n_positions <= 1:
        conn.close()
        return {"error": "Can't remove the last holding — delete the whole simulation instead."}

    current_price = _live_price(ticker) or entry_price
    # Adjusted for splits and bonuses since entry: a 1:2 split
    # halves the price while stored units stay put, which would
    # otherwise read as a 50% loss that never happened.
    _ensure_cash_column()
    units = units * _split_factor_since(ticker, entry_date)
    current_value = units * current_price
    _divs         = _dividends_since(ticker, entry_date, units)
    realized_pnl  = (current_value + _divs) - entry_value
    # Proceeds land as cash, which is what selling actually does. Previously the
    # position simply vanished along with its capital, so a sale could not be
    # followed by a purchase without depositing again.
    _proceeds     = current_value + _divs
    # Capital stays put: the money did not leave the simulation, it changed form
    # from stock into cash. Reducing capital by the entry value AND crediting the
    # proceeds would double-count the sale.
    new_init      = sim[0]

    conn.execute("DELETE FROM sim_positions WHERE sim_name = ? AND ticker = ? AND user_id = ?",
                 (sim_name, ticker, user_id))
    _set_cash(conn, sim_name, user_id, _get_cash(conn, sim_name, user_id) + _proceeds)
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
        # Rows created before names were trimmed can carry stray whitespace
        # (e.g. "Example "), which no exact match will ever hit. Fall back to a
        # trimmed comparison so those remain deletable.
        row = conn.execute(
            "SELECT name FROM simulations WHERE TRIM(name) = TRIM(?) AND user_id = ?",
            (name, user_id)).fetchone()
        if not row:
            conn.close()
            return {"error": f"Simulation '{name}' not found"}
        name = row[0]
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


def _simulate_with_drift(port_returns, target_w, rebalance_freq: str,
                         include_costs: bool):
    """
    Daily portfolio returns where holdings drift and are reset on schedule.

    Cost is charged on ACTUAL turnover rather than as a flat per-rebalance fee.
    A portfolio that has barely moved costs almost nothing to realign; one that
    has run hard costs more. Charging a fixed fee regardless made the cheap case
    look expensive and the expensive case look cheap.

    Turnover is the one-way traded fraction: sum(|current - target|) / 2.
    """
    import numpy as _np
    import pandas as _pd

    freq_map = {"monthly": "MS", "quarterly": "QS", "yearly": "YS"}
    rule = freq_map.get(rebalance_freq, "QS")
    try:
        rebal_dates = set(port_returns.resample(rule).first().index)
    except Exception:
        rebal_dates = set()

    # Round-trip cost of moving 100% of the book: buy + sell brokerage and
    # slippage, plus STT and stamp duty. Same figures as the flat model used.
    cost_per_unit_turnover = (2 * 0.001) + (2 * 0.0005) + 0.001 + 0.00015

    w = target_w.copy()
    if w.sum() > 0:
        w = w / w.sum()

    out = []
    for date, row in zip(port_returns.index, port_returns.values):
        r = _np.nan_to_num(row, nan=0.0)
        day_ret = float((w * r).sum())

        # Positions grow by their own return; weights drift as a result.
        w = w * (1.0 + r)
        tot = w.sum()
        if tot > 0:
            w = w / tot

        if date in rebal_dates:
            turnover = float(_np.abs(w - target_w).sum()) / 2.0
            if include_costs and turnover > 0:
                day_ret -= turnover * cost_per_unit_turnover
            w = target_w.copy()
            if w.sum() > 0:
                w = w / w.sum()

        out.append(day_ret)

    return _pd.Series(out, index=port_returns.index)

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

    # Daily returns, with weights that DRIFT between rebalance dates.
    #
    # This previously multiplied every day's returns by the same fixed weight
    # vector. That is not a quarterly-rebalanced portfolio — holding weights
    # constant every single day is daily rebalancing, silently, and the cost
    # model was charging for quarterly. It modelled continuous management and
    # paid for occasional management, which flatters the result twice: a winner
    # gets trimmed back daily (understating its compounding) while the trading
    # needed to do that is never charged for.
    #
    # Now positions grow with their own returns and are only reset to target on
    # an actual rebalance date, which is what a real portfolio does.
    port_returns = port_prices.pct_change().fillna(0)
    target_w     = np.array([port_weights[t] for t in port_tickers], dtype=float)
    port_daily   = _simulate_with_drift(port_returns, target_w, rebalance_freq,
                                        include_costs)

    cum_port = (1 + port_daily).cumprod() * initial_value

    # Could these positions actually have been traded at this size? The live
    # simulator charges impact scaled by daily turnover; the backtest did not,
    # so the same order was frictionless here and cost 5% there. One app should
    # not hold two views on whether a trade is possible.
    liquidity_check = None
    try:
        from execution import estimate_slippage_pct
        _flags, _worst = [], 0.0
        for _t, _w in port_weights.items():
            _size = float(initial_value) * float(_w)
            _sl = estimate_slippage_pct(_t, _size)
            _part = _sl.get("participation_pct")
            if _part is not None and _part > 10:
                _flags.append({"ticker": _t, "position": round(_size, 2),
                               "participation_pct": _part, "note": _sl["note"]})
                _worst = max(_worst, _part)
        if _flags:
            liquidity_check = {
                "tradeable_at_this_size": False,
                "flagged": sorted(_flags, key=lambda f: -f["participation_pct"]),
                "note": (f"{len(_flags)} holding(s) would be a large share of their "
                         f"own daily turnover at this portfolio size — the worst is "
                         f"{_worst:,.0f}% of a typical day. This backtest fills them "
                         f"at the quoted price anyway, so its return is optimistic "
                         f"by an amount it cannot measure."),
            }
        else:
            liquidity_check = {
                "tradeable_at_this_size": True,
                "flagged": [],
                "note": "Every holding is small against its own daily turnover at "
                        "this portfolio size, so fills at the quoted price are "
                        "a reasonable assumption.",
            }
    except Exception:
        liquidity_check = None

    # Which of these actually existed at the start? A holding that listed later
    # is quietly started mid-period, which flatters the result and is invisible.
    survivorship = None
    try:
        from survivorship import check_portfolio
        survivorship = check_portfolio(list(port_weights), start_date)
    except Exception:
        survivorship = None

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
        # Reported alongside the result, not in a footnote: a backtest whose
        # holdings did not all exist at the start is measuring something
        # other than what it claims.
        "survivorship":      survivorship,
        "liquidity":         liquidity_check,
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
