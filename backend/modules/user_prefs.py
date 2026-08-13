"""
user_prefs.py — the minimum stored to email someone who asked to be emailed.

Addresses live in the Supabase JWT, which only exists during a request, so a
weekly cron has nothing to address. This stores one row per user who explicitly
opted in — and nothing else. No name, no device, no marketing flags.

Consent rules this enforces rather than documents:
  * Nothing is stored until the user opts in. Merely visiting does not create a
    row.
  * The address comes from the verified JWT, never from a form field, so a user
    cannot subscribe somebody else.
  * Opting out DELETES the row rather than flipping a flag. "Unsubscribed but
    we kept your email" is the pattern people rightly resent.
"""

from datetime import datetime

from db import get_conn, IS_POSTGRES


def _init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_emails (
            user_id     TEXT PRIMARY KEY,
            email       TEXT NOT NULL,
            weekly      INTEGER DEFAULT 1,
            opted_in_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def opt_in(user_id: str, email: str) -> dict:
    """Record consent. The email must come from the caller's verified token."""
    if not user_id or user_id == "public":
        return {"error": "Sign in first."}
    if not email or "@" not in email:
        # We only ever store what the token gave us; a missing address means the
        # token had none, not that the user should type one. Say what to do
        # about it — an error that only states a fact leaves the user stuck.
        return {"error": "We could not read a verified email for your account. "
                         "Sign out, sign back in, and try again."}

    _init_db()
    now = datetime.now().isoformat()
    conn = get_conn()
    if IS_POSTGRES:
        conn.execute(
            "INSERT INTO user_emails (user_id, email, weekly, opted_in_at) "
            "VALUES (?,?,1,?) ON CONFLICT (user_id) DO UPDATE SET "
            "email = EXCLUDED.email, weekly = 1, opted_in_at = EXCLUDED.opted_in_at",
            (user_id, email, now))
    else:
        conn.execute(
            "INSERT OR REPLACE INTO user_emails (user_id, email, weekly, opted_in_at) "
            "VALUES (?,?,1,?)", (user_id, email, now))
    conn.commit()
    conn.close()
    return {"weekly": True, "email": email,
            "note": "You can turn this off any time — it deletes the address."}


def opt_out(user_id: str) -> dict:
    """Delete the row. Not a flag: unsubscribing should remove the data."""
    _init_db()
    conn = get_conn()
    cur = conn.execute("DELETE FROM user_emails WHERE user_id = ?", (user_id,))
    conn.commit()
    n = cur.rowcount
    conn.close()
    return {"weekly": False, "deleted": bool(n),
            "note": "Address removed. Nothing of yours is kept for email."}


def get_pref(user_id: str) -> dict:
    _init_db()
    conn = get_conn()
    row = conn.execute(
        "SELECT email, weekly, opted_in_at FROM user_emails WHERE user_id = ?",
        (user_id,)).fetchone()
    conn.close()
    if not row:
        return {"weekly": False, "asked": False}
    return {"weekly": bool(row[1]), "asked": True,
            "email": row[0], "since": row[2]}


def address_for(user_id: str):
    """The opted-in address for this user, or None. Used by the digest batch."""
    try:
        _init_db()
        conn = get_conn()
        row = conn.execute(
            "SELECT email FROM user_emails WHERE user_id = ? AND weekly = 1",
            (user_id,)).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None
