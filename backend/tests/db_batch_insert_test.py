"""
db_batch_insert_test.py — executemany must actually batch, and only when safe.

psycopg2's executemany is not a batch. It sends one statement per row over the
wire; the library's own documentation says it is "not faster than executing
execute() in a loop". A comment in bhavcopy claimed switching to it had cut
~2,400 round-trips per day to one, which was never true — it removed the Python
loop, not the network. Measured on the historical walk: 2-3 minutes per trading
day, which put a 3,060-day backfill at 34 hours.

So _PgConn.executemany now rewrites a single-tuple INSERT into the form
execute_values wants, and sends one multi-row statement instead.

The rewrite is the dangerous part, because it edits SQL with a regular
expression and every caller in the app goes through it. Two failure modes are
tested with equal weight:

  it must batch what it can        — or the fix does nothing, silently, and the
                                     only symptom is that things stay slow;
  it must refuse what it cannot    — an UPDATE (watchlist sends one), a tail
                                     carrying its own placeholder, a literal %.
                                     Batching one of those would corrupt the
                                     statement rather than fail it.

An earlier version of this regex is exactly why the second half matters: the
`\\b` word boundaries were written into the file as literal backspace bytes, so
the pattern matched nothing at all. Every statement fell back, the batching
never happened, and nothing anywhere would have said so.
"""

import io
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# db.py connects to Postgres at import time when DATABASE_URL is set, so lift
# the two pure helpers out rather than importing the module.
_SRC = io.open(os.path.join(os.path.dirname(__file__), "..", "modules", "db.py"),
               encoding="utf-8").read()
_ns = {"re": re}
exec(_SRC[_SRC.index("_INSERT_VALUES = re.compile"):
          _SRC.index("class _PgCursor:")], _ns)
template = _ns["_as_values_template"]

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


print("=" * 72)
print("NO BACKSPACES: THE PATTERN IS THE ONE WE MEANT TO WRITE")
print("=" * 72)

pat = _ns["_INSERT_VALUES"].pattern
check("the pattern contains no control characters",
      not any(ord(c) < 32 and c != "\n" for c in pat),
      f"{[hex(ord(c)) for c in pat if ord(c) < 32 and c != chr(10)]}")
check("word boundaries survived as regex syntax, not as backspace",
      "\\b" in pat, repr(pat[:44]))

print()
print("=" * 72)
print("WHAT MUST BE BATCHED")
print("=" * 72)

BHAV = ("INSERT INTO bhavcopy_eod (symbol, day, open, high, low, close, "
        "volume, isin) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (symbol, day) DO UPDATE SET close = EXCLUDED.close, "
        "isin = COALESCE(EXCLUDED.isin, bhavcopy_eod.isin)")
t = template(BHAV)
check("the real bhavcopy statement is batched", t is not None)
if t:
    check("exactly one placeholder remains for the values list",
          t.count("%s") == 1, f"count={t.count('%s')}")
    check("the ON CONFLICT tail is preserved verbatim",
          "ON CONFLICT (symbol, day) DO UPDATE SET close = EXCLUDED.close" in t)
    check("the column list is preserved",
          "(symbol, day, open, high, low, close, volume, isin)" in t)
    check("VALUES is followed by the placeholder",
          re.search(r"VALUES\s+%s", t) is not None, t[-90:])

for name, sql in [
    ("a plain two-column insert", "INSERT INTO t (a, b) VALUES (%s, %s)"),
    ("ON CONFLICT DO NOTHING", "INSERT INTO t (a) VALUES (%s) ON CONFLICT DO NOTHING"),
    ("a single column", "INSERT INTO t (a) VALUES (%s)"),
    ("lower case keywords", "insert into t (a, b) values (%s, %s)"),
    ("leading whitespace and newlines",
     "\n        INSERT INTO t\n          (a, b)\n        VALUES (%s, %s)\n"),
    ("generous inner spacing", "INSERT INTO t (a, b) VALUES ( %s , %s )"),
    ("many columns", "INSERT INTO t (a,b,c,d,e,f,g,h,i,j,k) VALUES "
                     "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"),
]:
    check(name, template(sql) is not None, sql[:56].replace("\n", " "))

print()
print("=" * 72)
print("WHAT MUST NOT BE BATCHED")
print("=" * 72)

for name, sql in [
    ("an UPDATE (watchlist sends one)",
     "UPDATE watchlist SET current_price = %s, last_updated = %s WHERE id = %s"),
    ("a DELETE", "DELETE FROM t WHERE id = %s"),
    ("a tail carrying its own placeholder",
     "INSERT INTO t (a) VALUES (%s) ON CONFLICT (a) DO UPDATE SET b = %s"),
    ("a literal % in the tail",
     "INSERT INTO t (a) VALUES (%s) ON CONFLICT DO NOTHING -- 50% done"),
    ("an INSERT ... SELECT with no VALUES tuple",
     "INSERT INTO t (a) SELECT x FROM y"),
    ("a VALUES tuple holding an expression, not a placeholder",
     "INSERT INTO t (a, b) VALUES (%s, now())"),
]:
    check(name + " falls back", template(sql) is None, sql[:56])

print()
print("=" * 72)
print("DISPATCH: THE RIGHT PATH IS TAKEN")
print("=" * 72)


class _FakeCur:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=()):
        self.log.append(("execute", sql))

    def executemany(self, sql, seq):
        self.log.append(("executemany", sql, len(list(seq))))


class _FakeRaw:
    def __init__(self, log):
        self.log = log

    def cursor(self):
        return _FakeCur(self.log)


# Rebuild _PgConn.executemany's decision without importing db (which would
# connect). This mirrors the method body: template found -> execute_values,
# otherwise -> cur.executemany.
def dispatch(sql, rows, execute_values_available=True):
    translated = sql.replace("?", "%s")
    tmpl = template(translated) if rows else None
    if tmpl is not None and execute_values_available:
        return ("execute_values", tmpl, len(rows))
    return ("executemany", translated, len(rows))


rows2 = [(1, 2), (3, 4), (5, 6)]
d = dispatch("INSERT INTO t (a, b) VALUES (?, ?)", rows2)
check("an INSERT goes to execute_values", d[0] == "execute_values", f"{d[0]}")
check("all rows are handed over in one call", d[2] == 3, f"{d[2]}")

d = dispatch("UPDATE t SET a = ? WHERE id = ?", rows2)
check("an UPDATE goes to the per-row path", d[0] == "executemany", f"{d[0]}")

d = dispatch("INSERT INTO t (a, b) VALUES (?, ?)", [])
check("an empty row list never tries to batch", d[0] == "executemany", f"{d[0]}")

d = dispatch("INSERT INTO t (a, b) VALUES (?, ?)", rows2,
             execute_values_available=False)
check("without psycopg2.extras it falls back rather than raising",
      d[0] == "executemany", f"{d[0]}")

check("? placeholders are translated before matching",
      template("INSERT INTO t (a, b) VALUES (?, ?)") is None
      and template("INSERT INTO t (a, b) VALUES (?, ?)".replace("?", "%s"))
      is not None,
      "the rewrite runs on translated SQL, never on the sqlite form")

print()
print("=" * 72)
print("THE CALLERS IN THIS REPO")
print("=" * 72)

MODULES = os.path.join(os.path.dirname(__file__), "..", "modules")
callers = []
for fn in sorted(os.listdir(MODULES)):
    if not fn.endswith(".py"):
        continue
    src = io.open(os.path.join(MODULES, fn), encoding="utf-8").read()
    if ".executemany(" in src and fn != "db.py":
        callers.append(fn)
check("every executemany caller is accounted for",
      set(callers) >= {"bhavcopy.py", "factor_provenance.py"},
      f"{callers}")

print()
print("=" * 72)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
