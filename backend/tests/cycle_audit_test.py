"""
cycle_audit_test.py — the audit can fail, and fails for the right reason.

An audit that only ever passes is a green light with no bulb behind it. So each
check is run twice: once against a cycle built to be correct, and once against
the same cycle with one specific thing broken. If the broken run still passes,
that check is decoration.

The corruption is deliberate and surgical — one defect at a time — because an
audit that fails everything on a mangled database has not demonstrated it can
find any particular fault.
"""

import math
import os
import sqlite3
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


DB = os.path.join(os.environ.get("TEMP", "/tmp"), "cycle_audit_test.db")
CYCLE, PREV = "2026-09-03", "2026-09-02"


def build(scored=2600, failed=200, universe=2872, complete=True,
          with_provenance=True, break_repro=False, dupe=False,
          orphan=False, promote_failure=False):
    if os.path.exists(DB):
        os.remove(DB)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE alpha_scan2 (ticker TEXT, alpha_score REAL,
        signal TEXT, confidence REAL, market_cap REAL, momentum REAL,
        quality REAL, value REAL, sentiment REAL, error TEXT, cycle TEXT,
        scanned_at TEXT, model_version TEXT)""")
    c.execute("""CREATE TABLE alpha_scan_state (id INTEGER PRIMARY KEY,
        cycle TEXT, started_at TEXT, finished_at TEXT, done INTEGER,
        total INTEGER, status TEXT, last_complete_cycle TEXT, last_error TEXT)""")
    c.execute("""CREATE TABLE factor_history (ticker TEXT, captured_at TEXT,
        model TEXT, alpha_score REAL, momentum REAL, quality REAL, growth REAL,
        value REAL, sentiment REAL, low_risk REAL, price REAL,
        raw_inputs_available INTEGER DEFAULT 0, cycle_id TEXT,
        cycle_complete INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE factor_inputs (ticker TEXT, isin TEXT,
        cycle_id TEXT, observed_at TEXT, factor TEXT, input_name TEXT,
        value_num REAL, value_text TEXT, category TEXT, source TEXT,
        missing INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE factor_input_peers (ticker TEXT, cycle_id TEXT,
        peer_ticker TEXT, peer_pe REAL, peer_pb REAL, source TEXT,
        observed_at TEXT)""")
    c.execute("""CREATE TABLE factor_input_articles (ticker TEXT, cycle_id TEXT,
        title_hash TEXT, title TEXT, published_at TEXT, finbert_label TEXT,
        finbert_confidence REAL, weight REAL, observed_at TEXT)""")
    c.execute("CREATE TABLE bhavcopy_eod (symbol TEXT, day TEXT, close REAL)")
    c.execute("CREATE TABLE predictions (ticker TEXT, snapshot_date TEXT)")

    for i in range(universe):
        c.execute("INSERT INTO bhavcopy_eod VALUES (?,?,?)",
                  (f"S{i:05d}.NS", CYCLE, 100.0))

    risk_adj = 0.45
    score = round(math.tanh(risk_adj / 1.5), 4)
    for i in range(scored):
        tk = f"S{i:05d}.NS"
        c.execute("INSERT INTO alpha_scan2 (ticker, alpha_score, cycle, "
                  "scanned_at, momentum) VALUES (?,?,?,?,?)",
                  (tk, 5.0, CYCLE, f"{CYCLE}T10:00:00", score))
        c.execute("INSERT INTO factor_history (ticker, captured_at, model, "
                  "alpha_score, momentum, price, raw_inputs_available, "
                  "cycle_id, cycle_complete) VALUES (?,?,?,?,?,?,?,?,?)",
                  (tk, CYCLE, "v1", 5.0, score, 100.0,
                   1 if with_provenance else 0, CYCLE, 1 if complete else 0))
        if with_provenance and not (orphan and i == 0):
            ra = risk_adj if not (break_repro and i == 0) else 9.99
            c.execute("INSERT INTO factor_inputs (ticker, cycle_id, factor, "
                      "input_name, value_num, missing, observed_at) "
                      "VALUES (?,?,?,?,?,?,?)",
                      (tk, CYCLE, "momentum", "risk_adj", ra, 0, CYCLE))
            c.execute("INSERT INTO factor_input_peers VALUES (?,?,?,?,?,?,?)",
                      (tk, CYCLE, "P1.NS", 20.0, 2.0, "Yahoo", CYCLE))
        c.execute("INSERT INTO predictions VALUES (?,?)", (tk, CYCLE))

    for i in range(failed):
        tk = f"F{i:05d}.NS"
        c.execute("INSERT INTO alpha_scan2 (ticker, alpha_score, error, cycle, "
                  "scanned_at) VALUES (?,?,?,?,?)",
                  (tk, None, f"No market data found for '{tk}'", CYCLE,
                   f"{CYCLE}T10:00:00"))
        if promote_failure:
            c.execute("INSERT INTO factor_history (ticker, captured_at, model, "
                      "cycle_id, cycle_complete) VALUES (?,?,?,?,?)",
                      (tk, CYCLE, "v1", CYCLE, 1))

    if dupe:
        c.execute("INSERT INTO factor_inputs (ticker, cycle_id, factor, "
                  "input_name, value_num, missing) VALUES (?,?,?,?,?,?)",
                  ("S00000.NS", CYCLE, "momentum", "risk_adj", risk_adj, 0))

    # a previous cycle to compare against
    for i in range(2590):
        c.execute("INSERT INTO alpha_scan2 (ticker, alpha_score, cycle, "
                  "scanned_at) VALUES (?,?,?,?)",
                  (f"S{i:05d}.NS", 5.0, PREV, f"{PREV}T10:00:00"))

    c.execute("INSERT INTO alpha_scan_state VALUES (1,?,?,?,?,?,?,?,NULL)",
              (CYCLE, f"{CYCLE}T08:00:00", f"{CYCLE}T11:00:00",
               scored + failed, universe, "complete",
               CYCLE if complete else PREV))
    c.commit()
    c.close()


def run():
    fake = types.ModuleType("db")
    fake.get_conn = lambda: sqlite3.connect(DB)
    fake.IS_POSTGRES = False
    sys.modules["db"] = fake
    for m in ("cycle_audit",):
        sys.modules.pop(m, None)
    import cycle_audit
    return cycle_audit.audit(CYCLE)


print("\n1. A clean cycle passes")
build()
r = run()
ok(r["verdict"] == "PASS", f"verdict PASS (got {r['verdict']}: {r['anomalies']})")
ok(r["scan"]["scored"] == 2600, f"scored counted ({r['scan']['scored']})")
ok(r["scan"]["failed"] == 200, f"failed counted ({r['scan']['failed']})")
ok(r["scan"]["universe_that_day"] == 2872,
   f"universe from that day ({r['scan']['universe_that_day']})")
ok(abs(r["scan"]["coverage_pct"] - 90.53) < 0.1,
   f"coverage {r['scan']['coverage_pct']}%")
ok(r["failure_taxonomy"].get("no market data") == 200,
   f"failures grouped ({r['failure_taxonomy']})")
ok(r["factor_history"]["research_grade"] == 2600,
   f"graded rows ({r['factor_history']['research_grade']})")
ok(r["provenance"]["input_rows"] == 2600,
   f"provenance rows ({r['provenance']['input_rows']})")
ok(r["reproduction"]["checked"] > 0 and r["reproduction"]["mismatched"] == 0,
   f"reproduction clean ({r['reproduction']})")
ok(len(r["previous_cycles"]) == 1, "previous cycle compared")
ok(all(v is not None for v in r["query_latency_ms"].values()),
   f"latency measured ({len(r['query_latency_ms'])} queries)")

print("\n2. Coverage below the bar FAILS")
build(scored=1200, failed=200, complete=False)
r = run()
ok(r["verdict"] == "FAIL", "a 42% pass is failed")
ok(any("coverage" in a for a in r["anomalies"]),
   f"and the reason names coverage ({r['anomalies'][:1]})")

print("\n3. Grading that contradicts coverage FAILS")
build(scored=1200, failed=200, complete=True)      # marked complete, isn't
r = run()
ok(r["verdict"] == "FAIL", "a partial pass marked complete is failed")
ok(any("marked" in a or "coverage" in a for a in r["anomalies"]),
   "and the contradiction is named")

print("\n4. Broken reproduction FAILS — the check that matters most")
build(break_repro=True)
r = run()
ok(r["reproduction"]["mismatched"] == 1,
   f"the one tampered risk_adj is caught ({r['reproduction']})")
ok(r["verdict"] == "FAIL", "and it fails the cycle")

print("\n5. Duplicates FAIL")
build(dupe=True)
r = run()
ok(r["duplicates"]["factor_inputs"] > 0,
   f"duplicate provenance row detected ({r['duplicates']})")
ok(r["verdict"] == "FAIL", "and it fails the cycle")

print("\n6. A row claiming provenance it does not have FAILS")
build(orphan=True)
r = run()
ok(r["verdict"] == "FAIL", "orphaned provenance claim is caught")
ok(any("provenance" in a.lower() for a in r["anomalies"]),
   f"and named ({r['anomalies'][:1]})")

print("\n7. A failed stock promoted into history FAILS")
build(promote_failure=True)
r = run()
ok(r["verdict"] == "FAIL", "a stock that never scored must not be in history")
ok(any("failed stock" in a for a in r["anomalies"]),
   f"and named ({[a for a in r['anomalies'] if 'failed' in a][:1]})")

print("\n8. A pre-provenance cycle is reported, not failed")
build(with_provenance=False)
r = run()
ok(r["provenance"]["pre_provenance_cycle"] is True,
   "a cycle with no inputs is identified as pre-provenance")
ok(r["verdict"] == "PASS",
   "and is NOT failed for it — it predates the deployment, which is not a fault")

try:
    os.remove(DB)
except Exception:
    pass

print("\n" + "=" * 66)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
