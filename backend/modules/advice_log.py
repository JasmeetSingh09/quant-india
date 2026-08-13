"""
advice_log.py — recording what the coach said, so it can later be proved wrong.

An advisor that never checks its own advice is indistinguishable from one that
guesses well. Every suggestion this platform makes is written down here with the
numbers that triggered it and the state of the portfolio at the time, so that
weeks later we can ask the only question that matters: did the portfolios that
followed this advice actually do better?

The answer is allowed to be no. That is the entire point — a logged suggestion
is a falsifiable claim, and a rule that turns out not to help should be removed
the same way the debt-to-equity penalty was removed when 660 stocks showed it
carried no signal.

What this deliberately does NOT store: holdings, rupee amounts, or anything
identifying. A suggestion kind, the trigger number, and a portfolio fingerprint
are enough to measure whether advice works, and no more than that is anyone's
business.
"""

import hashlib
import json
from datetime import datetime

from db import get_conn, IS_POSTGRES


def _init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS advice_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            issued_at     TEXT NOT NULL,
            portfolio_key TEXT NOT NULL,
            kind          TEXT NOT NULL,
            severity      TEXT,
            trigger_value REAL,
            downside_pct  REAL,
            n_holdings    INTEGER,
            followed      INTEGER,
            outcome_pct   REAL,
            checked_at    TEXT
        )
    """)
    conn.commit()
    conn.close()


if IS_POSTGRES:
    # Postgres has no AUTOINCREMENT; a failed statement also aborts the whole
    # transaction, so this runs on its own connection like every other DDL here.
    def _init_db():                                    # noqa: F811
        conn = get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS advice_log (
                    id            SERIAL PRIMARY KEY,
                    issued_at     TEXT NOT NULL,
                    portfolio_key TEXT NOT NULL,
                    kind          TEXT NOT NULL,
                    severity      TEXT,
                    trigger_value REAL,
                    downside_pct  REAL,
                    n_holdings    INTEGER,
                    followed      INTEGER,
                    outcome_pct   REAL,
                    checked_at    TEXT
                )
            """)
            conn.commit()
        except Exception:
            pass
        conn.close()


def portfolio_key(holdings: dict, user_id: str = None) -> str:
    """
    A stable fingerprint for "this portfolio, these weights".

    Hashed rather than stored: it lets us tell whether a portfolio changed after
    advice was given, without the log ever holding what someone owns.
    """
    payload = json.dumps(
        {"h": sorted((str(t).upper(), round(float(v), 2)) for t, v in holdings.items()),
         "u": (user_id or "anon")[:64]},
        sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def record(suggestions: list, holdings: dict, downside_pct=None,
           user_id: str = None) -> int:
    """Write one row per suggestion. Never raises — advice must still render if
    logging fails."""
    if not suggestions:
        return 0
    try:
        _init_db()
        key = portfolio_key(holdings, user_id)
        now = datetime.now().isoformat()
        conn = get_conn()
        n = 0
        for s in suggestions:
            try:
                trigger = None
                payoff = s.get("payoff") or {}
                if payoff.get("improvement_pts") is not None:
                    trigger = float(payoff["improvement_pts"])
                conn.execute(
                    "INSERT INTO advice_log (issued_at, portfolio_key, kind, severity, "
                    "trigger_value, downside_pct, n_holdings, followed, outcome_pct, "
                    "checked_at) VALUES (?,?,?,?,?,?,?,NULL,NULL,NULL)",
                    (now, key, s.get("kind", "unknown"), s.get("severity"),
                     trigger, downside_pct, len(holdings)))
                n += 1
            except Exception:
                continue
        conn.commit()
        conn.close()
        return n
    except Exception:
        return 0


def effectiveness(min_samples: int = 20) -> dict:
    """
    What the log can honestly say so far.

    Reports "not enough data yet" rather than a number built on five rows.
    Publishing a 3-sample result would be exactly the overfitting this platform
    spends the rest of its code avoiding.
    """
    try:
        _init_db()
        conn = get_conn()
        rows = conn.execute(
            "SELECT kind, COUNT(*), AVG(outcome_pct), "
            "SUM(CASE WHEN followed = 1 THEN 1 ELSE 0 END) "
            "FROM advice_log GROUP BY kind").fetchall()
        total = conn.execute("SELECT COUNT(*) FROM advice_log").fetchone()[0]
        since = conn.execute("SELECT MIN(issued_at) FROM advice_log").fetchone()[0]
        conn.close()
    except Exception as e:
        return {"error": f"advice log unavailable: {type(e).__name__}"}

    by_kind = [{"kind": r[0], "times_given": r[1],
                "avg_outcome_pct": round(r[2], 2) if r[2] is not None else None,
                "times_followed": r[3] or 0} for r in rows]
    by_kind.sort(key=lambda k: -k["times_given"])

    measurable = [k for k in by_kind if (k["times_followed"] or 0) >= min_samples]
    return {
        "total_suggestions": total,
        "logging_since": since,
        "by_kind": by_kind,
        "verdict": (
            f"{total} suggestions logged. Not yet enough followed-and-measured "
            f"cases to claim any rule works — that needs {min_samples}+ per rule, "
            f"and reporting a number before then would be the overfitting this "
            f"platform exists to avoid."
            if not measurable else
            f"{len(measurable)} rule(s) now have {min_samples}+ measured cases."),
        "honest_note": (
            "This log exists to let the advice be proved wrong. A rule that does "
            "not help gets removed, the way the debt-to-equity penalty was removed "
            "when testing showed it carried no signal."),
    }
