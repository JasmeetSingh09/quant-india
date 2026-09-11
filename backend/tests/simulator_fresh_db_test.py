"""
simulator_fresh_db_test.py — a new SQLite database must be able to hold cash.

Found by the CI gate on its first clean-checkout run. Every developer database
had been created before the cash balance existed and was migrated long ago, so
nothing local could show this: on a brand-new SQLite file the simulations table
never got its cash column, and the first deposit raised "no such column: cash".

Two faults stacked:
  - _init_db's SQLite branch put the cash ALTER in the same block as an is_demo
    ALTER that always fails on a new table (CREATE TABLE already has is_demo),
    so the failure skipped cash;
  - _ensure_cash_column tested IS_POSTGRES, a name simulator.py never imported,
    and swallowed the NameError, so its own ALTER never ran on any backend.

Production runs Postgres, whose _init_db branch uses ADD COLUMN IF NOT EXISTS
and was never affected. The last check pins that the fix did not put a DDL
statement on every deposit, which is what _init_db's docstring says once made
reads time out.

Offline, and only ever against SQLite files this test creates.
"""
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp()
FRESH = os.path.join(TMP, "quant_platform.db")
open(FRESH, "wb").close()          # present, so db.py does not copy a developer DB in
os.environ["QUANT_DATA_DIR"] = TMP
os.environ.pop("DATABASE_URL", None)

import db                           # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""),
          flush=True)


def safely(fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as e:
        return {"crashed": f"{type(e).__name__}: {e}"}


def columns(path):
    c = sqlite3.connect(path)
    try:
        return [r[1] for r in c.execute("PRAGMA table_info(simulations)")]
    finally:
        c.close()


print("=" * 74 + "\nSAFETY — THIS TEST ONLY TOUCHES FILES IT CREATED\n" + "=" * 74)
check("running on SQLite, not a real database", db.IS_POSTGRES is False)
check("  ...on the brand-new file this test made",
      os.path.abspath(str(db._SQLITE_PATH)) == os.path.abspath(FRESH), str(db._SQLITE_PATH))
if FAIL:
    print("\nRefusing to continue against a database this test did not create.")
    sys.exit(1)

import simulator as S               # noqa: E402

print("\n" + "=" * 74 + "\nA NEW DATABASE\n" + "=" * 74)
S._DB_READY = False
safely(S._init_db)
cols = columns(FRESH)
check("a new database gets the cash column", "cash" in cols, str(cols))
check("  ...and keeps is_demo", "is_demo" in cols, str(cols))

conn = db.get_conn()
conn.execute("INSERT INTO simulations (user_id, name, initial_value, started_at) "
             "VALUES ('public', 'FreshDB', 1000, '2026-09-11T00:00:00')")
conn.commit()
conn.close()

r = safely(S.deposit, "FreshDB", 250.0)
check("the first deposit on a new database works", "crashed" not in r and "error" not in r,
      str(r)[:120])
check("  ...and the balance is what was paid in", r.get("cash") == 250.0, str(r.get("cash")))
r = safely(S.deposit, "FreshDB", 100.0)
check("a second deposit adds to it", r.get("cash") == 350.0, str(r)[:120])

print("\n" + "=" * 74 + "\nAN OLD DATABASE FROM BEFORE is_demo AND cash\n" + "=" * 74)
LEGACY = os.path.join(TMP, "legacy.db")
c = sqlite3.connect(LEGACY)
c.execute("""CREATE TABLE simulations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL DEFAULT 'public',
    name TEXT NOT NULL, initial_value REAL NOT NULL, started_at TEXT NOT NULL,
    last_checked TEXT, status TEXT DEFAULT 'active')""")
c.execute("INSERT INTO simulations (user_id, name, initial_value, started_at) "
          "VALUES ('public', 'Old', 5000, '2025-01-01T00:00:00')")
c.commit()
c.close()
db._SQLITE_PATH = LEGACY
S._DB_READY = False
safely(S._init_db)
cols = columns(LEGACY)
check("an old table gains is_demo", "is_demo" in cols, str(cols))
check("  ...and cash", "cash" in cols, str(cols))
c = sqlite3.connect(LEGACY)
row = c.execute("SELECT initial_value, cash FROM simulations WHERE name = 'Old'").fetchone()
c.close()
check("  ...its existing simulation is kept, with cash 0", row == (5000.0, 0.0), str(row))

print("\n" + "=" * 74 + "\nNO DDL ON EVERY DEPOSIT\n" + "=" * 74)
seen = []
real_get_conn = S.get_conn


class _Spy:
    def __init__(self, inner):
        self._inner = inner

    def execute(self, sql, *a, **k):
        seen.append(str(sql))
        return self._inner.execute(sql, *a, **k)

    def __getattr__(self, name):
        return getattr(self._inner, name)


S.get_conn = lambda: _Spy(real_get_conn())
try:
    safely(S._ensure_cash_column)
    safely(S.deposit, "Old", 10.0)
finally:
    S.get_conn = real_get_conn
ddl = [s for s in seen if s.strip().upper().startswith(("ALTER", "CREATE"))]
check("a deposit after start-up issues no ALTER or CREATE", not ddl, str(ddl)[:120])

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
