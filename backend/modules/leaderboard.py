"""
leaderboard.py — anonymous top simulator results, for social proof.

Shows that real people use the simulator and how their paper portfolios did,
without exposing who they are or what they hold.

Anonymity is not just "hide the email". With a pilot of 10-20 classmates, a
holdings list or a user-typed simulation name ("eda", "dad's money") identifies
someone immediately. So the payload carries a rank, a return, a duration and a
position count — nothing else leaves this module.
"""

import hashlib
from datetime import datetime

from db import get_conn

# A one-day-old simulation that caught a single lucky move is not a result worth
# putting at the top of a leaderboard.
MIN_DAYS      = 3
MIN_POSITIONS = 2


def _label(user_id: str, name: str) -> str:
    """Stable pseudonym. Hashed so the same person keeps the same label across
    refreshes, and so nothing about the real id or name can be read back out."""
    h = hashlib.sha256(f"{user_id}|{name}".encode()).hexdigest()
    return f"Investor #{int(h[:6], 16) % 900 + 100}"


def top_simulations(n: int = 5) -> dict:
    """Best n paper portfolios by percentage return, anonymised."""
    from simulator import _init_db, get_simulation_pnl
    _init_db()

    conn = get_conn()
    rows = conn.execute(
        "SELECT user_id, name, initial_value, started_at, COALESCE(is_demo, 0) "
        "FROM simulations WHERE status = 'active'"
    ).fetchall()
    conn.close()

    results = []
    demo_seen = 0
    for user_id, name, initial, started, is_demo in rows:
        try:
            days = (datetime.now() - datetime.fromisoformat(started)).days
        except Exception:
            days = 0
        if days < MIN_DAYS:
            continue
        try:
            p = get_simulation_pnl(name, user_id=user_id)
        except Exception:
            continue
        if not p or "error" in p:
            continue
        positions = p.get("positions") or []
        if len(positions) < MIN_POSITIONS:
            continue
        ret = p.get("total_pnl_pct")
        if ret is None:
            continue
        if is_demo:
            demo_seen += 1
            # Named, not pseudonymised. A demo shown as "Investor #247" would be
            # indistinguishable from a real user's result — fabricated social
            # proof, and the opposite of what this platform claims to be.
            label = f"Example portfolio {demo_seen}"
        else:
            label = _label(user_id, name)
        results.append({
            "label": label,
            "is_demo": bool(is_demo),
            "return_pct": round(float(ret), 2),
            "days_running": days,
            "n_positions": len(positions),
        })

    results.sort(key=lambda r: -r["return_pct"])
    for i, r in enumerate(results[:n], 1):
        r["rank"] = i

    return {
        "top": results[:n],
        "total_qualifying": len(results),
        "rules": (f"Active paper portfolios with at least {MIN_POSITIONS} stocks, "
                  f"running {MIN_DAYS}+ days. Ranked by percentage return."),
        "privacy": "Names, holdings and identities are never published.",
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# Diversified, defensible example portfolios. These are REAL simulations tracked
# against live NSE prices — nothing is fabricated. They exist so the leaderboard
# and demos are not empty before the pilot, and they are labelled as examples so
# no one mistakes them for another user's result.
DEMO_PORTFOLIOS = [
    ("Large-cap core",   {"HDFCBANK.NS": 25, "TCS.NS": 20, "RELIANCE.NS": 20,
                          "ICICIBANK.NS": 20, "ITC.NS": 15}),
    ("Spread across sectors", {"SBIN.NS": 18, "SUNPHARMA.NS": 18, "LT.NS": 18,
                               "MARUTI.NS": 16, "NTPC.NS": 15, "TITAN.NS": 15}),
    ("Equal weight eight",    {"INFY.NS": 12.5, "AXISBANK.NS": 12.5, "TATASTEEL.NS": 12.5,
                               "HINDUNILVR.NS": 12.5, "BHARTIARTL.NS": 12.5,
                               "ASIANPAINT.NS": 12.5, "COALINDIA.NS": 12.5, "WIPRO.NS": 12.5}),
]


def seed_demos(initial_value: float = 100000) -> dict:
    """Create the example portfolios if they do not already exist. Idempotent."""
    from simulator import start_simulation, list_simulations
    existing = {s.get("name") for s in (list_simulations(user_id="demo") or [])}
    created, skipped = [], []
    for name, holdings in DEMO_PORTFOLIOS:
        if name in existing:
            skipped.append(name); continue
        r = start_simulation(name, holdings, initial_value=initial_value,
                             user_id="demo", is_demo=True)
        (created if "error" not in r else skipped).append(name)
    return {"created": created, "skipped": skipped,
            "note": "Real simulations tracked against live prices, labelled as examples."}
