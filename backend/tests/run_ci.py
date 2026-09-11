"""
run_ci.py — the gate every push has to pass.

    cd backend
    python tests/run_ci.py                 # the suites listed in SUITES
    python tests/run_ci.py --manifest m.json   # another list (used by the self-test)

A suite fails the gate if ANY of these is true, and the reason is printed:

  1. it exits non-zero, or runs past its time limit;
  2. it prints a failure count above zero, whatever its exit code;
  3. it prints fewer checks than its floor, or no count at all;
  4. it tried to reach the network.

Rules 2 and 3 exist because of this week. A suite once printed a check mark the
Windows console could not encode and exited 1 while passing; another passed
while forty of its checks asserted nothing, because a cache made them vacuous.
An exit code alone would have waved the second one through. A floor on the
check count does not prove each check is meaningful, but a suite that silently
stops running most of its checks can no longer pass.

Rule 4 is enforced, not trusted: tests/ci/sitecustomize.py refuses every
outside connection and records the attempt.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
NETBLOCK = os.path.join(HERE, "ci")

# (file in tests/, minimum checks it must report, time limit in seconds)
# A floor of 0 means the suite prints no count and is judged on exit code and
# network use alone. Raise a floor when a suite gains checks; lowering one is a
# decision to accept that fewer things are being verified, so say why.
#
# Floors are the counts measured on 2026-09-11 in a clean checkout with the
# network blocked. What is NOT here, and why, is in tests/CI_SUITES.md.
SUITES = [
    ("test_core_properties.py",          81215, 600),
    ("test_new_algorithms_stress.py",    87173, 600),
    ("data_integrity_test.py",             109, 300),
    ("corporate_action_audit_test.py",      66, 120),
    ("pit_validation_e2e.py",               65, 300),
    ("corporate_actions_test.py",           55, 120),
    ("parse_subject_test.py",               54, 120),
    ("strategy_version_test.py",            48, 120),
    ("isin_split_diagnostic_test.py",       47, 120),
    ("metric_applicability_test.py",        44, 120),
    ("a5_gate_test.py",                     41, 120),
    ("a5_adjusted_series_test.py",          40, 120),
    ("factor_provenance_test.py",           39, 120),
    ("news_matching_test.py",               39, 120),
    ("piotroski_availability_test.py",      39, 120),
    ("false_zero_recording_test.py",        35, 120),
    ("bounded_cache_test.py",               34, 120),
    ("integrity_evidence_test.py",          34, 120),
    ("adjusted_prices_test.py",             33, 120),
    ("nse_collection_pause_test.py",        31, 120),
    ("lab_findings_test.py",                28, 120),
    ("cycle_audit_test.py",                 27, 120),
    ("db_batch_insert_test.py",             27, 120),
    ("piotroski_bitmap_test.py",            26, 120),
    ("scan_collection_test.py",             25, 120),
    ("cache_gate_test.py",                  24, 120),
    ("optimizer_properties_test.py",        24, 120),
    ("universe_filter_test.py",             24, 120),
    ("bhavcopy_gap_test.py",                22, 120),
    ("score_cache_test.py",                 21, 120),
    ("identity_resolution_test.py",         18, 120),
    ("provenance_gap_test.py",              18, 120),
    ("unpriced_holdings_test.py",           18, 120),
    ("closes_history_bound_test.py",        17, 120),
    ("pit_validation_test.py",              16, 120),
    ("production_safety_test.py",           15, 120),
    ("piotroski_invariant_test.py",         12, 120),
    ("pit_identity_ab_test.py",             11, 120),
    ("simulator_fresh_db_test.py",          11, 120),
    ("shadowed_import_test.py",              7, 120),
    ("market_validation_audit.py",          99, 120),
]
# run_ci_selftest.py is not listed: the workflow runs it as its own step first,
# so a gate that can no longer fail is reported before any suite is trusted.

_COUNT_PATTERNS = [
    # (regex, group for checks, group for failures)
    # "TOTAL CHECKS: N" and named totals such as "MARKET-VALIDATION CHECKS: 99",
    # each followed by "FAILURES: M".
    (re.compile(r"(?:TOTAL|[A-Z][A-Z-]*) CHECKS:\s*([\d,]+)\s*\n?\s*FAILURES:\s*([\d,]+)",
                re.I), 1, 2),
    (re.compile(r"TOTAL:\s*([\d,]+)\s+FAILURES:\s*([\d,]+)", re.I), 1, 2),
    (re.compile(r"passed\s+([\d,]+),\s*failed\s+([\d,]+)", re.I), 1, 2),
]
_FAILURES_ONLY = re.compile(r"FAILURES:\s*([\d,]+)", re.I)


def _int(s):
    return int(s.replace(",", ""))


def parse_counts(text):
    """(checks, failures) from the LAST summary a suite printed; None if absent."""
    best = None
    for rx, gc, gf in _COUNT_PATTERNS:
        for m in rx.finditer(text):
            if best is None or m.start() >= best[0]:
                best = (m.start(), _int(m.group(gc)), _int(m.group(gf)))
    if best:
        return best[1], best[2]
    m = list(_FAILURES_ONLY.finditer(text))
    return (None, _int(m[-1].group(1))) if m else (None, None)


def judge(rc, text, net_events, min_checks, timed_out=False):
    """Every reason this run fails the gate. Empty list means it passes."""
    reasons = []
    if timed_out:
        reasons.append("ran past its time limit")
    elif rc != 0:
        reasons.append(f"exited {rc}")
    checks, failures = parse_counts(text)
    if failures:
        reasons.append(f"reported {failures} failure(s)")
    if min_checks:
        if checks is None:
            reasons.append(f"printed no check count (floor {min_checks:,})")
        elif checks < min_checks:
            reasons.append(f"ran {checks:,} checks, below its floor of {min_checks:,}")
    hosts = sorted({e.split(":", 1)[1] for e in net_events if ":" in e})
    if hosts:
        reasons.append("tried to reach the network: " + ", ".join(hosts[:4]))
    return reasons, checks, failures


def run_suite(path, min_checks, timeout, cwd=BACKEND):
    with tempfile.TemporaryDirectory() as tmp:
        netlog = os.path.join(tmp, "net.log")
        env = dict(os.environ)
        for k in list(env):
            if re.match(r"^(DATABASE_URL|SUPABASE.*|PG(HOST|USER|PASSWORD|DATABASE))$", k):
                env.pop(k)                       # never a production database from CI
        env["PYTHONPATH"] = NETBLOCK + os.pathsep + env.get("PYTHONPATH", "")
        env["CI_NET_LOG"] = netlog
        env["PYTHONIOENCODING"] = "utf-8"
        # Each suite gets its own temp dir and its own SQLite data dir. Suites
        # name their scratch databases after themselves under TEMP, and several
        # modules write to the app database, so sharing either would let one
        # suite's leftovers decide whether the next one passes.
        for k in ("TEMP", "TMP", "TMPDIR"):
            env[k] = tmp
        env["QUANT_DATA_DIR"] = env["DATA_DIR"] = os.path.join(tmp, "data")
        t0 = time.time()
        timed_out = False
        try:
            p = subprocess.run([sys.executable, "-u", path], cwd=cwd, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=timeout)
            rc, out = p.returncode, p.stdout
        except subprocess.TimeoutExpired as e:
            rc, out, timed_out = None, e.stdout or b"", True
        text = out.decode("utf-8", "replace")
        events = open(netlog, encoding="utf-8").read().split() if os.path.exists(netlog) else []
    reasons, checks, failures = judge(rc, text, events, min_checks, timed_out)
    return {"suite": os.path.basename(path), "ok": not reasons, "reasons": reasons,
            "checks": checks, "failures": failures, "seconds": round(time.time() - t0, 1),
            "tail": text[-2500:]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", help="JSON list of [path, min_checks, timeout]")
    args = ap.parse_args(argv)
    if args.manifest:
        with open(args.manifest, encoding="utf-8") as fh:
            suites = [tuple(s) for s in json.load(fh)]
    else:
        suites = [(os.path.join("tests", f), n, t) for f, n, t in SUITES]
    if not suites:
        print("No suites listed. A gate with nothing in it passes everything, so this fails.")
        return 1

    results = []
    for path, floor, limit in suites:
        r = run_suite(path, floor, limit)
        results.append(r)
        mark = "PASS" if r["ok"] else "FAIL"
        count = f"{r['checks']:,} checks" if r["checks"] is not None else "no count"
        print(f"[{mark}] {r['suite']:<38} {count:>16}  {r['seconds']:>6}s"
              + ("" if r["ok"] else "  <- " + "; ".join(r["reasons"])), flush=True)

    failed = [r for r in results if not r["ok"]]
    total = sum(r["checks"] or 0 for r in results)
    print(f"\n{len(results) - len(failed)} of {len(results)} suites passed; "
          f"{total:,} checks counted.")
    for r in failed:
        print(f"\n----- {r['suite']}: {'; '.join(r['reasons'])} -----\n{r['tail']}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("| Suite | Result | Checks | Seconds |\n|---|---|---:|---:|\n")
            for r in results:
                res = "pass" if r["ok"] else "**FAIL** — " + "; ".join(r["reasons"])
                fh.write(f"| {r['suite']} | {res} | "
                         f"{r['checks'] if r['checks'] is not None else '—'} | {r['seconds']} |\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
