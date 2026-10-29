"""
account_deletion_test.py — DELETE /me/account erases one user and nobody else.

  1. every table that holds a user_id column is covered by USER_TABLES, so a
     new per-user table that nobody added to the deletion fails here;
  2. a signed-in user's rows go in every table, including thesis revisions
     reached through their theses; another user's identical rows stay;
  3. anonymous ('public') and unverified callers cannot delete anything, and
     the route refuses without {"confirm": "DELETE"};
  4. the Postgres cursor wrapper exposes rowcount (its absence made opt-out,
     share revoke and watchlist/holding removal return 500 after saving).

Offline: temporary SQLite, no network.

    cd backend && python tests/account_deletion_test.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
sys.path.insert(0, os.path.join(HERE, ".."))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="account_deletion_")
os.environ["QUANT_DATA_DIR"] = TMP
os.environ.pop("DATABASE_URL", None)

PASS = FAIL = 0


def ok(cond, label, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}  {detail}")


import db                                   # noqa: E402
import account_deletion as ad               # noqa: E402

A, B = "11111111-aaaa-4aaa-8aaa-111111111111", "22222222-bbbb-4bbb-8bbb-222222222222"

# db copies an existing local database into the data dir once, so the temp
# file may already hold these tables. Reset them -- only ever inside TMP.
assert str(db._SQLITE_PATH).startswith(TMP), db._SQLITE_PATH
conn = db.get_conn()
for table, _ in ad.USER_TABLES:
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    if table == "thesis_revisions":
        conn.execute("CREATE TABLE thesis_revisions (id INTEGER PRIMARY KEY, thesis_id INTEGER, reasons TEXT)")
    elif table == "theses":
        conn.execute("CREATE TABLE theses (id INTEGER PRIMARY KEY, user_id TEXT, ticker TEXT)")
    else:
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, user_id TEXT, v TEXT)")
for uid, tid in ((A, 1), (B, 2)):
    conn.execute("INSERT INTO theses (id, user_id, ticker) VALUES (?, ?, 'TCS')", (tid, uid))
    conn.execute("INSERT INTO thesis_revisions (thesis_id, reasons) VALUES (?, 'r1')", (tid,))
    conn.execute("INSERT INTO thesis_revisions (thesis_id, reasons) VALUES (?, 'r2')", (tid,))
    for table, _ in ad.USER_TABLES:
        if table not in ("theses", "thesis_revisions"):
            conn.execute(f"INSERT INTO {table} (user_id, v) VALUES (?, 'x')", (uid,))
conn.commit()
conn.close()

print("\n1. COVERAGE: every per-user table is in the deletion")
# The production schema's user_id tables (Supabase, 2026-10-29). A new one must
# be added both here and to USER_TABLES.
PROD_USER_ID_TABLES = {"portfolio_holdings", "portfolios", "product_events", "shared_portfolios",
                       "sim_positions", "sim_snapshots", "simulations", "theses",
                       "user_emails", "watchlist"}
covered = {t for t, _ in ad.USER_TABLES}
ok(PROD_USER_ID_TABLES <= covered, "all production user_id tables are deleted",
   str(PROD_USER_ID_TABLES - covered))
ok("thesis_revisions" in covered, "thesis revisions (linked by thesis_id) are deleted")

print("\n2. ONE USER IS ERASED, THE OTHER IS UNTOUCHED")
r = ad.delete_account(A)
ok(r.get("status") == "deleted", "delete_account returns deleted", str(r))
ok(r["rows_deleted"].get("thesis_revisions") == 2, "both of A's thesis revisions deleted", str(r))
conn = db.get_conn()
for table, where in ad.USER_TABLES:
    a_left = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", (A,)).fetchone()[0]
    b_left = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", (B,)).fetchone()[0]
    ok(a_left == 0, f"{table}: none of A's rows remain", str(a_left))
    ok(b_left >= 1, f"{table}: B's rows remain", str(b_left))
conn.close()

print("\n3. ANONYMOUS, UNVERIFIED AND UNCONFIRMED CALLS ARE REFUSED")
for uid in ("public", f"unverified:{B}", ""):
    ok("error" in ad.delete_account(uid), f"delete_account({uid!r}) refused")
conn = db.get_conn()
ok(conn.execute("SELECT COUNT(*) FROM watchlist WHERE user_id = ?", (B,)).fetchone()[0] == 1,
   "B still intact after refused calls")
conn.close()

from fastapi import HTTPException            # noqa: E402
import types                                  # noqa: E402


class _Stub(types.ModuleType):               # keep main's import offline (no FinBERT, no network)
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None


sys.modules["sentiment"] = _Stub("sentiment")
sys.modules["news"] = _Stub("news")
try:
    import main
    route = main.me_delete_account
    for body in ({}, {"confirm": "delete"}, None):
        try:
            route(body, user_id=B)
            ok(False, f"route refuses body {body!r}")
        except HTTPException as e:
            ok(e.status_code == 400, f"route refuses body {body!r} with 400", str(e.status_code))
    try:
        route({"confirm": "DELETE"}, user_id="public")
        ok(False, "route refuses anonymous caller")
    except HTTPException as e:
        ok(e.status_code == 401, "route refuses anonymous caller with 401", str(e.status_code))
except ImportError as e:
    ok(False, "main imports offline", str(e))

print("\n4. POSTGRES CURSOR WRAPPER HAS rowcount")
ok(isinstance(getattr(db._PgCursor, "rowcount", None), property), "_PgCursor.rowcount is a property")


class _Cur:
    rowcount = 3
ok(db._PgCursor(_Cur(), None).rowcount == 3, "_PgCursor.rowcount passes the driver's value through")

print(f"\nTOTAL: {PASS + FAIL}  FAILURES: {FAIL}")
sys.exit(1 if FAIL else 0)
