"""
share.py — a portfolio result that can travel.

Growth loops need an artifact someone can post. Everything here is currently
locked behind a login, so nothing leaves the app and every new user has to be
recruited by hand.

Sharing is OPT-IN and per-simulation. Nothing becomes public because a user
pressed something adjacent, and a share can be revoked, after which the link
404s rather than quietly continuing to serve. The token is random rather than
derived from the simulation name, so one public link never reveals another and
the URL leaks nothing about who made it.

What a share exposes is a deliberate subset: holdings, weights, per-stock
returns and the total. It does NOT expose the owner's identity, their email,
their other portfolios, or the rupee amounts — percentages travel fine and
"₹4,20,000" is nobody else's business.
"""

import secrets
from datetime import datetime

from db import get_conn


def _init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shared_portfolios (
            token      TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            sim_name   TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked    INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def create_share(sim_name: str, user_id: str = "public") -> dict:
    """Publish one simulation. Re-sharing the same one returns the same link."""
    _init_db()
    from simulator import get_simulation_pnl
    p = get_simulation_pnl(sim_name, user_id=user_id)
    if not p or "error" in p:
        return {"error": f"No simulation called '{sim_name}'."}

    conn = get_conn()
    row = conn.execute(
        "SELECT token FROM shared_portfolios WHERE user_id = ? AND sim_name = ? "
        "AND revoked = 0", (user_id, sim_name)).fetchone()
    if row:
        conn.close()
        return {"token": row[0], "reused": True}

    token = secrets.token_urlsafe(9)          # ~72 bits, not guessable
    conn.execute(
        "INSERT INTO shared_portfolios (token, user_id, sim_name, created_at) "
        "VALUES (?,?,?,?)", (token, user_id, sim_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"token": token, "reused": False,
            "note": "Anyone with this link can see the holdings and returns. "
                    "Your name, email and other portfolios stay private."}


def revoke_share(sim_name: str, user_id: str = "public") -> dict:
    _init_db()
    conn = get_conn()
    cur = conn.execute(
        "UPDATE shared_portfolios SET revoked = 1 WHERE user_id = ? AND sim_name = ?",
        (user_id, sim_name))
    conn.commit()
    n = cur.rowcount
    conn.close()
    return {"revoked": bool(n), "detail": "The link now 404s." if n else "Nothing shared."}


def get_shared(token: str) -> dict:
    """Public read. No auth — the token IS the credential."""
    _init_db()
    conn = get_conn()
    row = conn.execute(
        "SELECT user_id, sim_name, created_at FROM shared_portfolios "
        "WHERE token = ? AND revoked = 0", (token,)).fetchone()
    conn.close()
    if not row:
        return {"error": "This link is not valid, or the owner revoked it."}

    user_id, sim_name, created = row
    from simulator import get_simulation_pnl
    p = get_simulation_pnl(sim_name, user_id=user_id)
    if not p or "error" in p:
        return {"error": "That portfolio no longer exists."}

    # Percentages only. Rupee amounts are the owner's business, not the reader's.
    holdings = sorted(
        [{"name": (x.get("ticker") or "").replace(".NS", ""),
          "weight_pct": round(float(x.get("allocation_pct") or 0), 1),
          "return_pct": round(float(x.get("pnl_pct") or 0), 2)}
         for x in (p.get("positions") or [])],
        key=lambda h: -h["weight_pct"])

    try:
        days = (datetime.now() - datetime.fromisoformat(p.get("started_at", created))).days
    except Exception:
        days = None

    return {
        "name": sim_name,
        "return_pct": round(float(p.get("total_pnl_pct") or 0), 2),
        "days_running": days,
        "holdings": holdings,
        "n_positions": len(holdings),
        "shared_at": created,
        "disclaimer": "Paper trading — simulated with real NSE prices, no real money.",
    }
