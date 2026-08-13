"""
data_health.py — know when the data source is failing, before users do.

Every number in this app comes from one free endpoint with no contract. Yahoo
already throttles this IP, already omits returnOnEquity for ~82% of NSE names,
and can change or disappear without notice. That is the single largest business
risk here and it is not fixable by writing more code against the same source.

This module does the honest half: measure the dependency continuously so a
degradation is visible as a number rather than as confused users. It checks
whether prices, fundamentals and history are actually coming back, and records
each probe so the trend is inspectable.

It explicitly does NOT claim to solve the problem. A real fix is a second
provider behind an interface — and if the fallback reads from the same upstream
it is decoration, not redundancy. What this buys is early warning and evidence:
when someone asks "what happens if Yahoo pulls the plug", the answer becomes a
measurement instead of a shrug.
"""

from datetime import datetime, timedelta

from db import get_conn

PROBE_TICKERS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]


def _init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_health (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at  TEXT NOT NULL,
            day         TEXT NOT NULL,
            price_ok    INTEGER,
            history_ok  INTEGER,
            fundamentals_pct REAL,
            detail      TEXT
        )
    """)
    conn.commit()
    conn.close()


def probe(record: bool = True) -> dict:
    """One health check across the three things the app actually depends on."""
    _init_db()
    price_ok = history_ok = 0
    fund_have = fund_total = 0
    notes = []

    # 1. live price — the most visible failure
    try:
        from data_fetcher import get_current_price
        for t in PROBE_TICKERS:
            r = get_current_price(t)
            if r and r.get("price"):
                price_ok += 1
        if price_ok < len(PROBE_TICKERS):
            notes.append(f"prices {price_ok}/{len(PROBE_TICKERS)}")
    except Exception as e:
        notes.append(f"price probe failed: {type(e).__name__}")

    # 2. price history — everything quantitative depends on this
    try:
        import yfinance as yf
        df = yf.download(PROBE_TICKERS[0], period="1mo", progress=False,
                         auto_adjust=True)
        history_ok = 1 if (df is not None and not df.empty and len(df) > 10) else 0
        if not history_ok:
            notes.append("history empty or too short")
    except Exception as e:
        notes.append(f"history probe failed: {type(e).__name__}")

    # 3. fundamentals coverage — the field that silently vanished before
    try:
        from alpha_model import _ticker_info
        for t in PROBE_TICKERS:
            i = _ticker_info(t) or {}
            fund_total += 1
            if i.get("marketCap"):
                fund_have += 1
    except Exception as e:
        notes.append(f"fundamentals probe failed: {type(e).__name__}")

    fund_pct = round(fund_have / fund_total * 100, 1) if fund_total else 0.0
    healthy = price_ok == len(PROBE_TICKERS) and history_ok and fund_pct >= 66

    now = datetime.now()
    if record:
        try:
            conn = get_conn()
            conn.execute(
                "INSERT INTO data_health (checked_at, day, price_ok, history_ok, "
                "fundamentals_pct, detail) VALUES (?,?,?,?,?,?)",
                (now.isoformat(), now.strftime("%Y-%m-%d"), price_ok, history_ok,
                 fund_pct, "; ".join(notes) or "ok"))
            conn.commit()
            conn.close()
        except Exception:
            pass

    return {
        "healthy": healthy,
        "prices_ok": f"{price_ok}/{len(PROBE_TICKERS)}",
        "history_ok": bool(history_ok),
        "fundamentals_coverage_pct": fund_pct,
        "notes": notes or ["all probes passed"],
        "risk": ("Every figure in this app comes from one free endpoint with no "
                 "contract. This detects degradation; it does not remove the "
                 "dependency. A real fix is a second provider behind an "
                 "interface — and a fallback reading the same upstream would be "
                 "decoration, not redundancy."),
        "checked_at": now.strftime("%Y-%m-%d %H:%M"),
    }


def history(days: int = 14) -> dict:
    """Recent probes, so degradation shows as a trend rather than one bad moment."""
    _init_db()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_conn()
    rows = conn.execute(
        "SELECT checked_at, price_ok, history_ok, fundamentals_pct, detail "
        "FROM data_health WHERE day >= ? ORDER BY checked_at DESC", (since,)
    ).fetchall()
    conn.close()
    probes = [{"at": r[0], "prices_ok": r[1], "history_ok": bool(r[2]),
               "fundamentals_pct": r[3], "detail": r[4]} for r in rows]
    bad = [p for p in probes
           if p["prices_ok"] < len(PROBE_TICKERS) or not p["history_ok"]]
    return {
        "window_days": days, "probes": len(probes),
        "degraded_probes": len(bad),
        "degraded_pct": round(len(bad) / len(probes) * 100, 1) if probes else 0.0,
        "recent": probes[:20],
    }
