"""
run_ci_selftest.py — a gate nobody has seen fail is not a gate.

Builds small fake suites, each broken in exactly one way the gate must catch,
and asserts run_ci.py rejects each for the right reason. Then it runs the gate
end to end as CI does and checks the exit code: 1 when any suite fails, 0 only
when all pass. CI runs this before the real suites, so a gate that has quietly
stopped failing things is caught on the same push.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import run_ci  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""),
          flush=True)


FAKES = {
    "good.py": 'print("TOTAL CHECKS: 120\\nFAILURES:     0\\nALL CHECKS PASSED")',
    "good_passed_format.py": 'print("passed 12, failed 0")',
    "good_named_total.py": 'print("MARKET-VALIDATION CHECKS: 99\\nFAILURES:                 0")',
    "named_total_hides_failures.py": 'print("MARKET-VALIDATION CHECKS: 99\\nFAILURES: 2")',
    "exits_one.py": 'import sys; print("TOTAL CHECKS: 120\\nFAILURES: 0"); sys.exit(1)',
    "hides_failures.py": 'print("TOTAL CHECKS: 120\\nFAILURES: 3")',
    "hides_failures_passed_format.py": 'print("passed 10, failed 2")',
    "shrunk.py": 'print("TOTAL CHECKS: 41\\nFAILURES: 0")',
    "silent.py": 'print("all good, trust me")',
    "crashes.py": 'raise RuntimeError("boom")',
    "reaches_network.py": (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('query1.finance.yahoo.com', 443), timeout=3)\n"
        "except Exception:\n"
        "    pass\n"
        "print('TOTAL CHECKS: 120\\nFAILURES: 0')"),
    # yfinance's route: libcurl in C, invisible to a socket-level block. The
    # first version of the gate let this through and logged nothing.
    "reaches_network_via_curl.py": (
        "from curl_cffi import requests as cr\n"
        "try:\n"
        "    cr.get('https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS', timeout=5)\n"
        "except Exception:\n"
        "    pass\n"
        "print('TOTAL CHECKS: 120\\nFAILURES: 0')"),
    "hangs.py": "import time; time.sleep(30); print('TOTAL CHECKS: 120\\nFAILURES: 0')",
    "earlier_failure_later_pass.py": (
        'print("passed 3, failed 1")\n'
        'print("TOTAL CHECKS: 120\\nFAILURES: 0")'),
}

with tempfile.TemporaryDirectory() as tmp:
    for name, body in FAKES.items():
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
            fh.write(body + "\n")

    def run(name, floor=100, timeout=20):
        return run_ci.run_suite(os.path.join(tmp, name), floor, timeout, cwd=tmp)

    print("=" * 74 + "\nTHE GATE MUST PASS A GOOD SUITE\n" + "=" * 74)
    r = run("good.py")
    check("a suite with 120 checks, 0 failures, floor 100 passes", r["ok"], str(r["reasons"]))
    check("  ...and its count is read", r["checks"] == 120, str(r["checks"]))
    r = run("good_passed_format.py", floor=12)
    check("the 'passed N, failed 0' format is read too", r["ok"] and r["checks"] == 12,
          str(r["reasons"]))
    r = run("good_named_total.py", floor=99)
    check("a named total ('MARKET-VALIDATION CHECKS: 99') is read too",
          r["ok"] and r["checks"] == 99, f"{r['reasons']} checks={r['checks']}")
    r = run("named_total_hides_failures.py", floor=99)
    check("  ...and so are the failures printed under it",
          not r["ok"] and "reported 2 failure" in "; ".join(r["reasons"]),
          "; ".join(r["reasons"]) or "it passed")

    print("\n" + "=" * 74 + "\nTHE GATE MUST FAIL EACH OF THESE, FOR THE RIGHT REASON\n" + "=" * 74)
    # (fake suite, floor, time limit, words the reason must contain, plain description)
    cases = [
        ("exits_one.py", 100, 20, "exited 1", "a non-zero exit"),
        ("hides_failures.py", 100, 20, "reported 3 failure", "failures printed under exit 0"),
        ("hides_failures_passed_format.py", 10, 20, "reported 2 failure",
         "failures in the 'passed N, failed N' format"),
        ("shrunk.py", 100, 20, "below its floor", "too few checks"),
        ("silent.py", 100, 20, "no check count", "no count at all"),
        ("crashes.py", 100, 20, "exited 1", "a crash"),
        ("reaches_network.py", 100, 20, "tried to reach the network", "a network call"),
        ("reaches_network_via_curl.py", 100, 20, "tried to reach the network: curl_cffi",
         "a download through curl_cffi, the route yfinance uses"),
        ("hangs.py", 100, 3, "time limit", "a hang"),
    ]
    for name, floor, limit, why, plain in cases:
        r = run(name, floor, limit)
        said = "; ".join(r["reasons"])
        check(f"{name} fails", not r["ok"], said or "it passed")
        check(f"  ...and the reason given is {plain}", why in said, said)

    r = run("earlier_failure_later_pass.py", floor=100)
    check("a later full summary is what counts, not an earlier sub-total",
          r["ok"] and r["checks"] == 120, "; ".join(r["reasons"]) or str(r["checks"]))

    print("\n" + "=" * 74 + "\nEND TO END — THE EXIT CODE CI ACTUALLY READS\n" + "=" * 74)
    gate = os.path.join(HERE, "run_ci.py")

    def gate_exit(entries):
        m = os.path.join(tmp, "manifest.json")
        with open(m, "w", encoding="utf-8") as fh:
            json.dump([[os.path.join(tmp, n), f, t] for n, f, t in entries], fh)
        env = dict(os.environ, GITHUB_STEP_SUMMARY="")
        return subprocess.run([sys.executable, gate, "--manifest", m], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT).returncode

    check("every suite passing -> exit 0",
          gate_exit([("good.py", 100, 20), ("good_passed_format.py", 12, 20)]) == 0)
    check("one failing suite among passing ones -> exit 1",
          gate_exit([("good.py", 100, 20), ("hides_failures.py", 100, 20),
                     ("good_passed_format.py", 12, 20)]) == 1)
    check("an empty list of suites -> exit 1, not a pass", gate_exit([]) == 1)

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
