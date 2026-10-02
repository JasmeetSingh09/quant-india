"""
thesis_records_test.py — the rules of thesis records (#4 in
docs/PROPOSAL_PRODUCT_ADDITIONS_2026-09-23.md).

Offline, and only ever against a SQLite file this test creates. Prices and
scans are replaced with fixed series, so every trigger is checked against a
known answer.
"""
import ast
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp()
open(os.path.join(TMP, "quant_platform.db"), "wb").close()
os.environ["QUANT_DATA_DIR"] = TMP
os.environ.pop("DATABASE_URL", None)

import thesis_records as T  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


def refused(fn, *a, kind=T.ThesisError):
    try:
        fn(*a)
        return False
    except kind:
        return True


STATE = {"price": 100.0, "signal": "BUY"}
T.SNAPSHOT = lambda ticker: {"price": STATE["price"], "signal": STATE["signal"], "taken_at": "now"}
PRICES = []
SCANS = []
T.PRICE_HISTORY = lambda ticker, since: list(PRICES)
T.SCAN_HISTORY = lambda ticker, since: list(SCANS)

GOOD = {"ticker": "tcs", "stance": "expect to outperform", "horizon_months": 12,
        "reasons": "Deal wins and margin recovery.", "evidence": "Q1 order book up 16%.",
        "bear_case": "AI shrinks services spending faster than expected.", "risks": "Rupee strength.",
        "invalidation": [{"text": "Price closes below 3,000", "kind": "price_below", "level": 3000},
                         "Two quarters of falling order book"]}

print("\n1. Opening needs a reason, a bear case and a trigger")
for field in ("reasons", "bear_case"):
    ok(refused(T.create, "u1", {**GOOD, field: "  "}), f"refused without {field}")
ok(refused(T.create, "u1", {**GOOD, "invalidation": []}), "refused without a 'what would make me wrong' trigger")
ok(refused(T.create, "u1", {**GOOD, "stance": "strong buy"}), "only the three stances are accepted")
ok(refused(T.create, "u1", {**GOOD, "horizon_months": 0}), "horizon must be 1 to 60 months")
ok(refused(T.create, "u1", {**GOOD, "invalidation": [{"text": "x", "kind": "price_below", "level": -5}]}),
   "a price trigger needs a positive level")
ok(refused(T.create, "u1", {**GOOD, "invalidation": [{"text": "x", "kind": "rank_at_or_below", "level": "Sell"}]}),
   "a rank trigger needs a rank word")
t = T.create("u1", GOOD)
ok(t["ticker"] == "TCS.NS" and t["status"] == "open" and len(t["revisions"]) == 1, "a complete thesis opens")
tid = t["id"]

print("\n2. Revisions are added, never edited")
ok(refused(T.revise, "u1", tid, {**GOOD, "what_changed": ""}), "a second revision without 'what changed' is refused")
first = T.get("u1", tid, with_triggers=False)["revisions"][0]
STATE.update(price=120.0, signal="NEUTRAL")
T.revise("u1", tid, {**GOOD, "reasons": "Margins recovered; deal wins slowed.", "what_changed": "Q2 deal wins fell"})
revs = T.get("u1", tid, with_triggers=False)["revisions"]
ok(len(revs) == 2, "the revision is a new record")
ok(revs[0] == first, "the first revision reads back unchanged")
ok(revs[1]["what_changed"] == "Q2 deal wins fell", "the change is recorded")
ok(not any(n for n in dir(T) if n.startswith(("edit", "update_revision"))), "there is no way to edit a revision")

print("\n3. Snapshots hold what was known at writing time")
ok(revs[0]["snapshot"]["price"] == 100.0 and revs[0]["snapshot"]["signal"] == "BUY",
   "the first revision keeps price 100 and BUY, not today's values")
ok(revs[1]["snapshot"]["price"] == 120.0 and revs[1]["snapshot"]["signal"] == "NEUTRAL",
   "the second revision keeps its own values")

import sqlite3  # noqa: E402
DBFILE = os.path.join(TMP, "quant_platform.db")


def _snapshot_needing_the_db(ticker):
    # The real snapshot reads the scan tables on a second connection. Taking a
    # write lock with a short timeout fails if the save already holds one.
    c = sqlite3.connect(DBFILE, timeout=0.5)
    c.execute("BEGIN IMMEDIATE")
    c.rollback()
    c.close()
    return {"price": 1.0, "taken_at": "now"}


T.SNAPSHOT = _snapshot_needing_the_db
try:
    lock_ok = T.create("u3", {**GOOD, "ticker": "INFY"})["status"] == "open"
except Exception:
    lock_ok = False
ok(lock_ok, "the snapshot is taken outside the save's write transaction (no lock wait)")
T.SNAPSHOT = lambda ticker: {"price": STATE["price"], "signal": STATE["signal"], "taken_at": "now"}

print("\n4. Triggers flag; they never act")
trig = {"text": "Price closes below 3,000", "kind": "price_below", "level": 3000}
PRICES[:] = [("2099-01-02", 3100.0), ("2099-01-03", 3000.0)]
ok(T.trigger_status("TCS.NS", trig, "2099-01-01")["met"] is False, "a close AT the level is not below it")
PRICES.append(("2099-01-04", 2999.5))
st = T.trigger_status("TCS.NS", trig, "2099-01-01")
ok(st["met"] and st["met_on"] == "2099-01-04", f"flagged on the first close below ({st.get('met_on')})")
PRICES[:] = [("2098-12-30", 2500.0)]
ok(T.trigger_status("TCS.NS", trig, "2099-01-01")["met"] is False, "a close before the revision does not count")
rk = {"text": "Rank falls", "kind": "rank_at_or_below", "level": "Ranked low"}
SCANS[:] = [("2099-01-02T01:00", "NEUTRAL")]
ok(T.trigger_status("TCS.NS", rk, "2099-01-01")["met"] is False, "Middle is above Ranked low")
SCANS.append(("2099-01-05T01:00", "SELL"))
ok(T.trigger_status("TCS.NS", rk, "2099-01-01")["met_on"] == "2099-01-05", "SELL (Ranked low) meets it")
PRICES[:] = [("2099-01-04", 10.0)]
full = T.get("u1", tid)
ok(full["status"] == "open", "a met trigger never closes the thesis")

def _boom(ticker, since):
    raise RuntimeError("price source down")


T.PRICE_HISTORY = _boom
g = T.get("u1", tid)
ok(g["status"] == "open" and g["trigger_status"][0]["met"] is None and "could not" in g["trigger_status"][0]["detail"],
   "a trigger that cannot be checked says so, and the thesis still reads")
T.PRICE_HISTORY = lambda ticker, since: list(PRICES)
import pandas as pd  # noqa: E402
import data_fetcher  # noqa: E402
_real_dc = data_fetcher.download_close
data_fetcher.download_close = lambda t, start, end=None: pd.Series([2075.0], index=pd.to_datetime(["2099-01-05"])).squeeze()
ok(T._price_history("TCS.NS", "2099-01-05") == [], "a single-row price download (a bare number) is handled")
data_fetcher.download_close = lambda t, start, end=None: pd.Series([2100.0, 2075.0], index=pd.to_datetime(["2099-01-02", "2099-01-05"]))
ok(T._price_history("TCS.NS", "2099-01-05") == [("2099-01-05", 2075.0)], "only closes from the revision date on are used")
data_fetcher.download_close = _real_dc

print("\n5. Each user sees only their own")
ok(refused(T.get, "u2", tid, kind=T.NotFound), "another user cannot read it")
ok(refused(T.revise, "u2", tid, {**GOOD, "what_changed": "x"}, kind=T.NotFound), "or revise it")
ok(refused(T.close, "u2", tid, "mine now", kind=T.NotFound), "or close it")
ok(refused(T.delete, "u2", tid, kind=T.NotFound), "or delete it")
ok(T.list_for("u2") == [] and len(T.list_for("u1")) == 1, "lists are per user")

print("\n6. Closing and deleting")
ok(refused(T.close, "u1", tid, ""), "closing needs a reason")
c = T.close("u1", tid, "horizon reached")
ok(c["status"] == "closed" and c["close_reason"] == "horizon reached", "closed with its reason")
ok(len(T.get("u1", tid, with_triggers=False)["revisions"]) == 2, "a closed thesis stays readable")
ok(refused(T.revise, "u1", tid, {**GOOD, "what_changed": "late"}), "a closed thesis cannot be revised")
T.delete("u1", tid)
ok(refused(T.get, "u1", tid, kind=T.NotFound), "deleting removes it")
import sqlite3  # noqa: E402
n = sqlite3.connect(os.path.join(TMP, "quant_platform.db")).execute(
    "SELECT COUNT(*) FROM thesis_revisions WHERE thesis_id = ?", (tid,)).fetchone()[0]
ok(n == 0, "and all its revisions")

print("\n7. The two databases create alike, and every route needs sign-in")
ok(len(T._PG_DDL) == len(T._SQLITE_DDL) and
   all(a.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY") == b for a, b in zip(T._SQLITE_DDL, T._PG_DDL)),
   "the Postgres schema differs from SQLite only in the id type")
tree = ast.parse(open(os.path.join(HERE, "..", "main.py"), encoding="utf-8").read())
routes = [f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name.startswith("thesis_")]
ok(len(routes) == 6, f"six thesis routes ({len(routes)})")
ok(all(any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_thesis_user" for n in ast.walk(f)) for f in routes),
   "every thesis route refuses anonymous visitors")
words = " ".join(ast.get_docstring(f) or "" for f in routes).lower() + " " + (T.__doc__ or "").lower()
ok("suggest" in words and "never" in words, "the module states it never suggests a thesis")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
