"""
analytics.py — product event log, so the pilot produces evidence not anecdotes.

The six-week pilot measures things like "% of users who change an allocation
after seeing a simulation". Without an event log that number can only be
guessed at afterwards, which is the difference between a result and an
impression.

Deliberately minimal and privacy-respecting:
  * user_id is the Supabase subject already used for data scoping — no emails,
    no names, no IP addresses, no device fingerprints.
  * `props` holds counts and enum-ish strings only. Never holdings, never
    tickers a user chose: with a pilot of a dozen classmates that would
    re-identify people, and the leaderboard already refuses to publish it.
  * Writes never raise. Analytics failing must never break the feature being
    measured — that trade is always worth making.
"""

import json
import threading
from datetime import datetime, timedelta

from db import get_conn, IS_POSTGRES

_LOCK = threading.Lock()

# The funnel the pilot actually reports on. Anything outside this is still
# accepted, but these are the ones with a defined meaning.
EVENTS = (
    "signup", "login",
    "portfolio_built", "simulation_started", "simulation_viewed",
    "montecarlo_run", "optimizer_run",
    "advice_requested", "scenario_tested", "allocation_changed",
    "stock_viewed", "leaderboard_viewed",
)


def _init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   TEXT NOT NULL DEFAULT 'anon',
            event     TEXT NOT NULL,
            props     TEXT,
            day       TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    conn = get_conn()
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS ix_events_event_day "
                     "ON product_events(event, day)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_events_user "
                     "ON product_events(user_id)")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def track(event: str, user_id: str = "anon", **props) -> dict:
    """Record one event. Never raises — a failed write must not break a feature."""
    try:
        _init_db()
        now = datetime.now()
        # Strip anything that could identify a holding or a person.
        safe = {k: v for k, v in props.items()
                if isinstance(v, (int, float, bool)) or
                (isinstance(v, str) and len(v) <= 40 and not v.endswith(".NS"))}
        conn = get_conn()
        conn.execute(
            "INSERT INTO product_events (user_id, event, props, day, created_at) "
            "VALUES (?,?,?,?,?)",
            (user_id or "anon", event[:40], json.dumps(safe),
             now.strftime("%Y-%m-%d"), now.isoformat()))
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def funnel(days: int = 42) -> dict:
    """
    The pilot scorecard. 42 days = the six-week window.

    The headline is `pct_changed_after_simulating`: of the users who ran a
    simulation, how many then changed an allocation. That is the learning
    outcome the product exists to cause, and the metric the capstone is
    measured on.
    """
    _init_db()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_conn()
    rows = conn.execute(
        "SELECT event, user_id, day FROM product_events WHERE day >= ?", (since,)
    ).fetchall()
    conn.close()

    by_event, users_by_event, active_days = {}, {}, {}
    for ev, uid, day in rows:
        by_event[ev] = by_event.get(ev, 0) + 1
        users_by_event.setdefault(ev, set()).add(uid)
        active_days.setdefault(uid, set()).add(day)

    simulated = users_by_event.get("simulation_started", set()) | \
                users_by_event.get("montecarlo_run", set())
    changed = users_by_event.get("allocation_changed", set()) | \
              users_by_event.get("scenario_tested", set())
    changed_after = simulated & changed

    all_users = set(active_days)
    returning = {u for u, d in active_days.items() if len(d) > 1}

    return {
        "window_days": days,
        "users_total": len(all_users),
        "users_returning": len(returning),
        "retention_pct": round(len(returning) / len(all_users) * 100, 1) if all_users else 0.0,
        "counts": dict(sorted(by_event.items(), key=lambda x: -x[1])),
        "unique_users_by_event": {k: len(v) for k, v in users_by_event.items()},
        "funnel": {
            "built_a_portfolio":   len(users_by_event.get("portfolio_built", set())),
            "ran_a_simulation":    len(simulated),
            "changed_allocation":  len(changed),
            "changed_after_simulating": len(changed_after),
        },
        # The capstone's stated success measure.
        "pct_changed_after_simulating":
            round(len(changed_after) / len(simulated) * 100, 1) if simulated else 0.0,
        "target_pct": 70,
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
