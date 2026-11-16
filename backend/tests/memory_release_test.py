"""
memory_release_test.py — the scan hands its memory back when it ends (2026-11-16).

Each nightly scan left resident memory higher than before (1.62 GB to 1.82 GB
over 15-29 Oct 2026, 2 GB limit). The fix: universe_scan.release_memory() runs
gc and glibc malloc_trim(0) when the scan loop ends, and the Dockerfile sets
MALLOC_ARENA_MAX=2. This suite checks that:

  1. release_memory never raises, on Windows/musl as well as glibc;
  2. it runs whether the scan finishes or crashes;
  3. the Dockerfile still sets MALLOC_ARENA_MAX=2.

Offline: temporary SQLite, the scan body is replaced by a stub.

    cd backend && python tests/memory_release_test.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ["QUANT_DATA_DIR"] = tempfile.mkdtemp(prefix="memory_release_")
os.environ.pop("DATABASE_URL", None)

import universe_scan as us                                    # noqa: E402

PASS = FAIL = 0


def ok(cond, label, detail=""):
    global PASS, FAIL
    PASS += bool(cond)
    FAIL += not cond
    print(f"  {'PASS' if cond else 'FAIL'}  {label}  {'' if cond else detail}")


print("\n1. RELEASE")
r = us.release_memory()
ok(isinstance(r.get("gc_collected"), int), "gc pass runs", str(r))
ok(r.get("malloc_trim") in (None, True, False), "malloc_trim is attempted or skipped, never raises", str(r))

print("\n2. RUNS AT THE END OF EVERY SCAN")
calls = []
real_release, real_inner, real_set = us.release_memory, us._scan_loop_inner, us._set_state
us.release_memory = lambda: calls.append(1) or {}
us._set_state = lambda **kw: None
try:
    us._scan_loop_inner = lambda: None
    us._scan_loop()
    ok(calls == [1], "after a scan that finishes", str(calls))

    def boom():
        raise RuntimeError("scan died")
    us._scan_loop_inner = boom
    try:
        us._scan_loop()
    except RuntimeError:
        pass
    ok(calls == [1, 1], "after a scan that crashes", str(calls))
finally:
    us.release_memory, us._scan_loop_inner, us._set_state = real_release, real_inner, real_set

print("\n3. DOCKERFILE")
with open(os.path.join(HERE, "..", "Dockerfile"), encoding="utf-8") as f:
    ok("ENV MALLOC_ARENA_MAX=2" in f.read(), "Dockerfile sets MALLOC_ARENA_MAX=2")

print(f"\nTOTAL: {PASS + FAIL}  FAILURES: {FAIL}")
sys.exit(1 if FAIL else 0)
