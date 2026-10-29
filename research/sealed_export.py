"""
sealed_export.py — the monthly sealed export the forward tests rely on.

Both forward pre-registrations (value/quality, section 7; sentiment, section 7)
grade only rows whose hash was committed at the time:

    "At each month's formation date, the formation cycle's rows (ticker, score,
     inputs, price) are exported and their sha256 is committed to
     docs/audit/forward_vq/. Grading uses only rows whose hash matches."

Sentiment forms weekly and enters/exits 1 and 5 trading days after formation,
so it needs prices from nearly every night. The export therefore seals EVERY
nightly cycle of the month, not just the formation cycles, and hashes each
cycle separately so a later edit can be pinned to the cycle it touched.

It is also the backup that outlives Supabase's 7-day window: the .csv.gz files
are a complete copy of the month's record.

What one month's export holds
  per-cycle (cycle_id in the month), hashed per cycle and per file:
    factor_history         scores + stored nightly price (P0); pre-September rows
                           with no cycle_id are keyed by their captured_at date
    factor_inputs          every input behind every score (n_articles, legs_used...)
    factor_input_articles  the headlines sentiment read
    factor_input_peers     the peer P/E and P/B behind value
    predictions            the logged signal snapshots (keyed by snapshot_date)
  whole-table snapshots, as of the export (they grow, so their hash changes
  month to month; they are copies, not seals):
    corporate_actions, accounts_observed, prediction_seals, strategy_versions

How it stays honest
  * One REPEATABLE READ, READ ONLY transaction: every file is the same instant,
    and the script cannot write to production even by mistake.
  * The seal is a per-cycle sha256 the database computes over the cycle's rows
    as text, sorted bytewise, with a pinned extra_float_digits: the same rows
    always give the same hash, whatever order they were written in.
  * The .csv.gz files carry a second hash, of their CSV bytes (not the .gz,
    which gzip would time-stamp; they are written with mtime 0 anyway), so
    check-files can prove a local copy is intact.
  * A month that has not ended (UTC) is refused, and an existing manifest is
    never overwritten. Exports more than 7 days after the month ends are marked
    sealed_late: their hash proves nothing about edits before the seal date.

Usage (owner; reads production, writes nothing to it)
    python -m pip install psycopg2-binary==2.9.13        # once
    $env:DATABASE_URL = "<the Supabase connection string from Render>"
    python research/sealed_export.py export 2026-10       # writes files + manifest
    python research/sealed_export.py verify 2026-10       # re-reads production, compares
    python research/sealed_export.py check-files 2026-10  # re-hashes the local .gz files

Then commit docs/audit/forward_vq/<month>.json. The .csv.gz files go to
QUANT_DATA (default ~/quant_data/sealed_exports/<month>/); keep a second copy
off this machine.
"""
from __future__ import annotations

import argparse
import calendar
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = ROOT / "docs" / "audit" / "forward_vq"
DATA_ROOT = Path(os.getenv("QUANT_DATA", Path.home() / "quant_data")) / "sealed_exports"
SEAL_LATE_DAYS = 7

# (table, the expression that gives a row's cycle). Order inside a cycle is by
# every column, so ties cannot reorder between runs.
PER_CYCLE = [
    ("factor_history",        "COALESCE(cycle_id, LEFT(captured_at, 10))"),
    ("factor_inputs",         "cycle_id"),
    ("factor_input_articles", "cycle_id"),
    ("factor_input_peers",    "cycle_id"),
    ("predictions",           "snapshot_date"),
]
SNAPSHOT = ["corporate_actions", "accounts_observed", "prediction_seals", "strategy_versions"]


def month_bounds(month: str):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise SystemExit(f"month must be YYYY-MM, got {month!r}")   # it is put into SQL text
    y, m = (int(x) for x in month.split("-"))
    last = calendar.monthrange(y, m)[1]
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=last)          # first instant of next month
    return start, end


def check_month(month: str, now: datetime):
    start, end = month_bounds(month)
    if now < end:
        raise SystemExit(f"{month} has not ended (UTC). Its last cycle may still run; export after "
                         f"{end:%Y-%m-%d} ~03:30 UTC.")
    return start, end


class HashingSink:
    """File-like target for COPY: hashes the CSV bytes and, on export, gzips them."""
    def __init__(self, gz=None):
        self.h = hashlib.sha256()
        self.gz = gz
        self.nbytes = 0

    def write(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.h.update(data)
        self.nbytes += len(data)
        if self.gz is not None:
            self.gz.write(data)
        return len(data)


def columns(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position", (table,))
    return [r[0] for r in cur.fetchall()]


# The seal itself is computed by the database: per cycle, the sha256 of that
# cycle's rows as text, sorted bytewise and joined by newlines. One pass per
# table (the cycle columns are not indexed, so a query per cycle would scan a
# 1 GB table thirty times), and verify needs no data transfer at all.
_ROW_HASH = ("encode(sha256(convert_to(string_agg(r::text, E'\\n' ORDER BY r::text COLLATE \"C\"), "
             "'UTF8')), 'hex')")


def seal_hashes(cur, table, key, month):
    """{cycle: {rows, sha256}} for a per-cycle table, or {rows, sha256} for a snapshot."""
    if key is None:
        cur.execute(f"SELECT COUNT(*), {_ROW_HASH} FROM {table} r")
        n, h = cur.fetchone()
        return {"rows": n, "sha256": h}
    cur.execute(f"SELECT k, COUNT(*), {_ROW_HASH} FROM "
                f"(SELECT {key} AS k, r FROM {table} r WHERE {key} LIKE %s) s GROUP BY k ORDER BY k",
                (f"{month}-%",))
    return {k: {"rows": n, "sha256": h} for k, n, h in cur.fetchall()}


def dump_table(cur, table, key, month, gz):
    """Seal one table and, when `gz` is given, stream its rows into it as CSV.
    Returns the manifest record. `gz=None` (verify) fetches only the seal."""
    cols = columns(cur, table)
    if not cols:
        return {"table": table, "missing": True}
    rec = {"table": table, "columns": cols}
    seal = seal_hashes(cur, table, key, month)
    if key is None:
        rec.update(rows=seal["rows"], content_sha256=seal["sha256"])
    else:
        rec.update(cycle_key=key, cycles=seal, rows=sum(c["rows"] for c in seal.values()))
    if gz is not None:
        order = ", ".join(str(i + 1) for i in range(len(cols)))
        where = "" if key is None else f" WHERE {key} LIKE '{month}-%'"
        lead = "" if key is None else f"{key}, "
        sink = HashingSink(gz)
        cur.copy_expert(f"COPY (SELECT * FROM {table}{where} ORDER BY {lead}{order}) "
                        f"TO STDOUT WITH (FORMAT csv, HEADER)", sink)
        rec.update(file_sha256=sink.h.hexdigest(), bytes=sink.nbytes)
    return rec


def cycle_status(cur, month):
    """Completeness per cycle, from the scores themselves (the formation rules key on it)."""
    cur.execute("SELECT cycle_id, MAX(cycle_complete), COUNT(*) FROM factor_history "
                "WHERE cycle_id LIKE %s AND model = 'v1' GROUP BY 1 ORDER BY 1", (f"{month}-%",))
    return {c: {"complete": bool(done), "v1_rows": n} for c, done, n in cur.fetchall()}


def open_snapshot(dsn):
    import psycopg2
    conn = psycopg2.connect(dsn)
    conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
    cur = conn.cursor()
    cur.execute("SET extra_float_digits = 1")       # shortest exact text for real/double
    cur.execute("SET TIME ZONE 'UTC'")
    cur.execute("SELECT now()")
    return conn, cur, cur.fetchone()[0].isoformat()


def git_commit():
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return None


def run(cur, month, out_dir=None):
    """Dump every table. With out_dir, write <table>.csv.gz files; without, hash only."""
    files = []
    for table, key in PER_CYCLE + [(t, None) for t in SNAPSHOT]:
        if out_dir is not None:
            path = out_dir / f"{table}.csv.gz"
            tmp = path.with_suffix(".gz.part")
            with open(tmp, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
                rec = dump_table(cur, table, key, month, gz)
            os.replace(tmp, path)
            rec["file"] = path.name
        else:
            rec = dump_table(cur, table, key, month, None)
        files.append(rec)
        print(f"  {table:24s} {rec.get('rows', 0):>10,} rows")
    return files


def manifest_path(month):
    return MANIFEST_DIR / f"{month}.json"


def cmd_export(month, dsn, now=None):
    now = now or datetime.now(timezone.utc)
    _, end = check_month(month, now)
    mpath = manifest_path(month)
    if mpath.exists():
        raise SystemExit(f"{mpath} already exists: a seal is never overwritten. Use verify.")
    out_dir = DATA_ROOT / month
    out_dir.mkdir(parents=True, exist_ok=True)
    conn, cur, snap = open_snapshot(dsn)
    try:
        status = cycle_status(cur, month)
        files = run(cur, month, out_dir)
    finally:
        conn.rollback()
        conn.close()
    manifest = {
        "month": month,
        "exported_at": now.isoformat(),
        "db_snapshot_at": snap,
        "sealed_late": now > end + timedelta(days=SEAL_LATE_DAYS),
        "script_commit": git_commit(),
        "data_dir": str(out_dir),
        "cycles": status,
        "files": files,
    }
    body = json.dumps(manifest, indent=1, sort_keys=True)
    manifest["manifest_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nSealed {month}: {len(status)} cycles, manifest {mpath}"
          + ("  [sealed late]" if manifest["sealed_late"] else ""))
    print("Commit the manifest now; copy the data folder somewhere off this machine.")
    return manifest


def compare(manifest, files):
    """Every difference between a sealed manifest and a fresh read, per cycle."""
    seal = {f["table"]: f for f in manifest["files"]}
    diffs = []
    for f in files:
        s = seal.get(f["table"])
        if s is None or s.get("missing") or f.get("missing"):
            continue
        if "cycles" not in s:                       # snapshot tables are copies, not seals
            if s.get("content_sha256") != f.get("content_sha256"):
                diffs.append(f"{f['table']}: snapshot differs (expected as it grows; not a seal)")
            continue
        for cyc, old in s["cycles"].items():
            new = f["cycles"].get(cyc)
            if new is None:
                diffs.append(f"{f['table']} {cyc}: cycle gone")
            elif new["sha256"] != old["sha256"]:
                diffs.append(f"{f['table']} {cyc}: changed ({old['rows']} -> {new['rows']} rows)")
        for cyc in set(f["cycles"]) - set(s["cycles"]):
            diffs.append(f"{f['table']} {cyc}: new cycle not in the seal")
    return diffs


def cmd_verify(month, dsn):
    manifest = json.loads(manifest_path(month).read_text(encoding="utf-8"))
    conn, cur, _ = open_snapshot(dsn)
    try:
        files = run(cur, month, None)
    finally:
        conn.rollback()
        conn.close()
    diffs = compare(manifest, files)
    print("\nverify:", "every sealed cycle matches" if not diffs else f"{len(diffs)} difference(s)")
    for d in diffs:
        print("  ", d)
    return diffs


def cmd_check_files(month):
    manifest = json.loads(manifest_path(month).read_text(encoding="utf-8"))
    bad = []
    for f in manifest["files"]:
        if f.get("missing"):
            continue
        path = Path(manifest["data_dir"]) / f["file"]
        h = hashlib.sha256()
        with gzip.open(path, "rb") as g:
            for chunk in iter(lambda: g.read(1 << 20), b""):
                h.update(chunk)
        ok = h.hexdigest() == f["file_sha256"]
        print(f"  {f['table']:24s} {'ok' if ok else 'MISMATCH'}")
        if not ok:
            bad.append(f["table"])
    return bad


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("command", choices=["export", "verify", "check-files"])
    p.add_argument("month", help="YYYY-MM")
    a = p.parse_args(argv)
    if a.command == "check-files":
        sys.exit(1 if cmd_check_files(a.month) else 0)
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn.startswith("postgres"):
        raise SystemExit("Set DATABASE_URL to the production Postgres connection string first.")
    if a.command == "export":
        cmd_export(a.month, dsn)
    else:
        sys.exit(1 if cmd_verify(a.month, dsn) else 0)


if __name__ == "__main__":
    main()
