"""
sealed_export_selftest.py — offline checks of sealed_export.py's own logic.

No database: a fake cursor answers the script's queries. The database-side hash
itself was checked against production on 2026-10-29: the same cycle gave the
same hash twice, and a full month of factor_inputs (1.9M rows) hashed in one
read-only query.

    python research/sealed_export_selftest.py
"""
import gzip
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sealed_export as se                                    # noqa: E402

PASS = FAIL = 0


def ok(cond, label, detail=""):
    global PASS, FAIL
    PASS += bool(cond)
    FAIL += not cond
    print(f"  {'PASS' if cond else 'FAIL'}  {label}  {'' if cond else detail}")


def raises(fn, label):
    try:
        fn()
        ok(False, label, "did not refuse")
    except SystemExit:
        ok(True, label)


class FakeCursor:
    """Answers columns / seal / copy queries from an in-memory table set."""
    def __init__(self, tables, tamper=None):
        self.tables, self.tamper, self._res = tables, tamper or {}, None

    def execute(self, sql, params=None):
        if "information_schema.columns" in sql:
            t = self.tables.get(params[0])
            self._res = [(c,) for c in t["cols"]] if t else []
        elif "GROUP BY k" in sql:
            table = sql.split(" FROM ")[2].split()[0]
            cycles = sorted({r[0] for r in self.tables[table]["rows"]})
            self._res = [(c, sum(1 for r in self.tables[table]["rows"] if r[0] == c),
                          self.tamper.get((table, c), f"h-{table}-{c}")) for c in cycles]
        elif "SELECT COUNT(*)" in sql:
            table = sql.split(" FROM ")[1].split()[0]
            self._res = [(len(self.tables[table]["rows"]), f"h-{table}")]
        elif "cycle_complete" in sql:
            self._res = [("2026-09-29", 1, 2), ("2026-09-30", 0, 1)]

    def fetchall(self):
        return self._res

    def fetchone(self):
        return self._res[0]

    def copy_expert(self, sql, sink):
        table = sql.split(" FROM ")[1].split()[0]
        t = self.tables[table]
        sink.write(",".join(t["cols"]) + "\n")
        for r in t["rows"]:
            sink.write(",".join(map(str, r)) + "\n")


TABLES = {
    "factor_history": {"cols": ["cycle_id", "ticker", "price"],
                       "rows": [("2026-09-29", "TCS", 1), ("2026-09-29", "INFY", 2), ("2026-09-30", "TCS", 3)]},
    "factor_inputs": {"cols": ["cycle_id", "ticker"], "rows": [("2026-09-29", "TCS")]},
    "factor_input_articles": {"cols": ["cycle_id", "title"], "rows": [("2026-09-29", "a")]},
    "factor_input_peers": {"cols": ["cycle_id", "peer"], "rows": [("2026-09-30", "x")]},
    "predictions": {"cols": ["snapshot_date", "ticker"], "rows": [("2026-09-29", "TCS")]},
    "corporate_actions": {"cols": ["isin"], "rows": [("INE1",)]},
    "accounts_observed": {"cols": ["ticker"], "rows": []},
    "prediction_seals": {"cols": ["day"], "rows": [("2026-09-29",)]},
    "strategy_versions": {"cols": ["version"], "rows": [("v1.6.0",)]},
}

tmp = Path(tempfile.mkdtemp(prefix="sealed_export_"))
se.MANIFEST_DIR = tmp / "manifests"
se.DATA_ROOT = tmp / "data"
se.git_commit = lambda: "test"

print("\n1. MONTH RULES")
raises(lambda: se.month_bounds("2026-13"), "an invalid month is refused")
raises(lambda: se.month_bounds("2026-09'; drop"), "a month carrying SQL is refused")
raises(lambda: se.check_month("2026-10", datetime(2026, 10, 31, 23, tzinfo=timezone.utc)),
       "a month that has not ended (UTC) is refused")
s, e = se.check_month("2026-09", datetime(2026, 10, 1, tzinfo=timezone.utc))
ok(e == datetime(2026, 10, 1, tzinfo=timezone.utc), "September ends at 1 October 00:00 UTC")

print("\n2. EXPORT")
se.open_snapshot = lambda dsn: (type("C", (), {"rollback": lambda s: None, "close": lambda s: None})(),
                                FakeCursor(TABLES), "2026-10-01T04:00:00+00:00")
m = se.cmd_export("2026-09", "postgres://fake", now=datetime(2026, 10, 1, 4, tzinfo=timezone.utc))
ok(not m["sealed_late"], "an export the day after the month ends is not late")
fh = next(f for f in m["files"] if f["table"] == "factor_history")
ok(set(fh["cycles"]) == {"2026-09-29", "2026-09-30"}, "factor_history sealed per cycle", str(fh["cycles"]))
ok(fh["rows"] == 3, "row count comes from the database, not from line counts", str(fh["rows"]))
ok(m["cycles"]["2026-09-30"]["complete"] is False, "an incomplete cycle is recorded as incomplete")
ok(all((se.DATA_ROOT / "2026-09" / f["file"]).exists() for f in m["files"]), "every table has a .csv.gz")
ok(not list((se.DATA_ROOT / "2026-09").glob("*.part")), "no partial files left behind")
with gzip.open(se.DATA_ROOT / "2026-09" / "factor_history.csv.gz", "rt") as g:
    ok(g.readline().strip() == "cycle_id,ticker,price", "the file starts with its header")
on_disk = json.loads(se.manifest_path("2026-09").read_text())
ok(on_disk["manifest_sha256"] == m["manifest_sha256"], "manifest written with its own hash")
raises(lambda: se.cmd_export("2026-09", "postgres://fake", now=datetime(2026, 10, 2, tzinfo=timezone.utc)),
       "an existing seal is never overwritten")

late_tables = dict(TABLES)
se.open_snapshot = lambda dsn: (type("C", (), {"rollback": lambda s: None, "close": lambda s: None})(),
                                FakeCursor(late_tables), "x")
late = se.cmd_export("2026-08", "postgres://fake", now=datetime(2026, 10, 29, tzinfo=timezone.utc))
ok(late["sealed_late"], "an export weeks after the month ends is marked sealed_late")

print("\n3. FILE CHECK")
ok(se.cmd_check_files("2026-09") == [], "fresh files match their recorded hashes")
p = se.DATA_ROOT / "2026-09" / "predictions.csv.gz"
with gzip.open(p, "wt") as g:
    g.write("snapshot_date,ticker\n2026-09-29,WIPRO\n")
ok(se.cmd_check_files("2026-09") == ["predictions"], "an edited local file is caught")

print("\n4. VERIFY AGAINST PRODUCTION")
seal = json.loads(se.manifest_path("2026-09").read_text())
fresh = se.run(FakeCursor(TABLES), "2026-09", None)
ok(se.compare(seal, fresh) == [], "unchanged data verifies clean")
tampered = se.run(FakeCursor(TABLES, tamper={("factor_history", "2026-09-29"): "other"}), "2026-09", None)
d = se.compare(seal, tampered)
ok(len(d) == 1 and "factor_history 2026-09-29: changed" in d[0], "an edit is pinned to its table and cycle", str(d))
gone = {k: v for k, v in TABLES.items()}
gone["factor_input_peers"] = {"cols": ["cycle_id", "peer"], "rows": []}
d = se.compare(seal, se.run(FakeCursor(gone), "2026-09", None))
ok(any("factor_input_peers 2026-09-30: cycle gone" in x for x in d), "a deleted cycle is caught", str(d))
ok(all(f.get("file_sha256") is None for f in fresh), "verify transfers no row data")

print(f"\nTOTAL: {PASS + FAIL}  FAILURES: {FAIL}")
sys.exit(1 if FAIL else 0)
