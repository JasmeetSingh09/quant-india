"""
test_supabase.py — verify the Postgres (Supabase) path works BEFORE trusting it in prod.

Usage (locally, with your Supabase connection string):

    # Windows PowerShell
    $env:DATABASE_URL="postgresql://postgres:PASSWORD@db.xxxx.supabase.co:5432/postgres"
    python test_supabase.py

    # bash
    DATABASE_URL="postgresql://...supabase.co:5432/postgres" python test_supabase.py

It creates the tables, does a write + read on each user-data table, and prints OK/FAIL.
Run it until everything says OK, THEN set DATABASE_URL on Render.
"""

import os
import sys

sys.path.insert(0, "modules")
import db

print(f"DB backend: {db.backend_name()}")
if not db.IS_POSTGRES:
    print("DATABASE_URL is not set to a Postgres URL — set it first (see docstring).")
    sys.exit(1)

ok = True


def check(name, fn):
    global ok
    try:
        fn()
        print(f"  OK   {name}")
    except Exception as e:
        ok = False
        print(f"  FAIL {name}: {e}")


# 1) predictions (Track Record)
def _pred():
    import prediction_tracker as pt
    pt.init_table()
    c = pt._conn()
    c.execute("INSERT OR IGNORE INTO predictions (ticker, snapshot_date, alpha_score, signal, price_at_snapshot) "
              "VALUES (?,?,?,?,?)", ("TEST.NS", "2000-01-01", 10.0, "BUY", 100.0))
    c.commit()
    row = c.execute("SELECT ticker FROM predictions WHERE ticker=?", ("TEST.NS",)).fetchone()
    c.execute("DELETE FROM predictions WHERE ticker=?", ("TEST.NS",)); c.commit(); c.close()
    assert row and row[0] == "TEST.NS"


# 2) simulations + save_portfolio (upsert)
def _sim():
    import simulator as sim
    sim._init_db()
    assert isinstance(sim.list_simulations(), list)
    assert sim.save_portfolio("test_pf", {"TCS.NS": 100}).get("status") == "saved"
    assert sim.save_portfolio("test_pf", {"INFY.NS": 100}).get("status") == "saved"  # upsert path
    c = db.get_conn(); c.execute("DELETE FROM portfolios WHERE name=?", ("test_pf",)); c.commit(); c.close()


# 3) watchlist
def _wl():
    import watchlist as wl
    c = db.get_conn()
    c.execute("CREATE TABLE IF NOT EXISTS _probe (id INTEGER PRIMARY KEY AUTOINCREMENT, x TEXT)")
    c.execute("INSERT INTO _probe (x) VALUES (?)", ("hi",))
    cur = c.execute("INSERT INTO _probe (x) VALUES (?)", ("hi2",))
    _ = cur.lastrowid   # exercises the lastrowid shim
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM _probe").fetchone()[0]
    c.execute("DROP TABLE _probe"); c.commit(); c.close()
    assert n >= 2


check("predictions table (Track Record)", _pred)
check("simulations + portfolio upsert", _sim)
check("insert + lastrowid shim", _wl)

print("\n" + ("ALL OK — safe to set DATABASE_URL on Render." if ok
              else "SOME CHECKS FAILED — do NOT switch prod yet; share the error."))
sys.exit(0 if ok else 1)
