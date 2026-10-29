"""
Delete a signed-in user's account and every row that belongs to them.

India's DPDP Act 2023 gives a user the right to have their personal data erased.
Before this module the app had no way to do that: a user could sign out, but
their portfolios, watchlist, theses, simulations and email address stayed.

What is deleted: every row keyed by the user's id in the tables below, then the
Supabase sign-in record itself (auth.users), all in ONE transaction, so a
failure part-way leaves nothing half-deleted.

What is kept, and why:
  * advice_log stores only a hash of (holdings, user id), never the holdings
    or the id themselves (advice_log.portfolio_key). Recomputing it needs the
    holdings, which this deletion erases, so no row can be found or linked
    back to the person afterwards.
  * challenge_entries has no user column at all.
  * Model-level tables (predictions, factor_history, ...) hold no personal data.
"""
from __future__ import annotations

from db import get_conn, IS_POSTGRES
from auth import PUBLIC_USER

# (table, WHERE clause). Children before parents: thesis_revisions is reached
# through theses, so it must go first. There are no foreign keys in public
# (checked 2026-10-29), so order matters only for that subquery.
USER_TABLES = [
    ("thesis_revisions",   "thesis_id IN (SELECT id FROM theses WHERE user_id = ?)"),
    ("theses",             "user_id = ?"),
    ("watchlist",          "user_id = ?"),
    ("portfolio_holdings", "user_id = ?"),
    ("portfolios",         "user_id = ?"),
    ("sim_positions",      "user_id = ?"),
    ("sim_snapshots",      "user_id = ?"),
    ("simulations",        "user_id = ?"),
    ("shared_portfolios",  "user_id = ?"),   # also kills any public share links
    ("product_events",     "user_id = ?"),
    ("user_emails",        "user_id = ?"),
]


def _existing_tables(conn) -> set[str]:
    if IS_POSTGRES:
        rows = conn.execute("SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = 'public'").fetchall()
    else:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r[0] for r in rows}


def deletable(user_id: str) -> bool:
    """Only a verified, signed-in user can delete. 'public' is the shared
    anonymous bucket, and an 'unverified:' id came from a token that failed
    verification, so neither may erase anything."""
    return bool(user_id) and user_id != PUBLIC_USER and not user_id.startswith("unverified:")


def delete_account(user_id: str) -> dict:
    """Erase the user's rows and sign-in record. Returns per-table counts."""
    if not deletable(user_id):
        return {"error": "Sign in to delete your account."}
    conn = get_conn()
    try:
        present = _existing_tables(conn)
        counts = {}
        for table, where in USER_TABLES:
            if table not in present:
                continue
            cur = conn.execute(f"DELETE FROM {table} WHERE {where}", (user_id,))
            counts[table] = cur.rowcount
        # The sign-in record. The backend connects as the database owner, which
        # may delete from auth.users; Supabase removes sessions and identities
        # with it. SQLite (local dev) has no auth schema.
        if IS_POSTGRES:
            cur = conn.execute("DELETE FROM auth.users WHERE id::text = ?", (user_id,))
            counts["auth.users"] = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"status": "deleted", "rows_deleted": counts}
