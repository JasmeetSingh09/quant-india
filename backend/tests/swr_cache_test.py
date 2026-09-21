"""
swr_cache_test.py — a cached answer comes back instantly, refreshes behind the
caller, and a failed refresh never replaces a good answer. No network.
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import swr_cache as sc  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


calls = []


def slow(value, delay=0.3):
    def fn():
        calls.append(value)
        time.sleep(delay)
        return value
    return fn


print("\n1. First call computes; repeats are served from memory")
sc.clear()
t0 = time.time()
ok(sc.cached("k", 60, slow("v1")) == "v1", "first call returns the computed answer")
ok(time.time() - t0 >= 0.3, "and the first caller waits for it")
t0 = time.time()
ok(sc.cached("k", 60, slow("v2")) == "v1", "a fresh entry is reused")
ok(time.time() - t0 < 0.05, "instantly")
ok(calls == ["v1"], "without recomputing")

print("\n2. A stale entry is served at once and refreshed in the background")
sc.clear(); calls.clear()
sc.cached("k", 0.1, slow("old", 0))
time.sleep(0.15)
t0 = time.time()
ok(sc.cached("k", 0.1, slow("new", 0.3)) == "old", "the stale answer is returned")
ok(time.time() - t0 < 0.05, "without waiting for the refresh")
ok(sc.cached("k", 0.1, slow("dup", 0.3)) == "old", "a second caller during the refresh also gets it")
time.sleep(0.5)
ok(calls.count("dup") == 0, "only one refresh runs at a time")
ok(sc.cached("k", 10, slow("x")) == "new", "after the refresh the new answer is served")

print("\n3. A failed refresh keeps the last good answer")
sc.clear()
sc.cached("k", 0.05, lambda: "good")
time.sleep(0.1)


def boom():
    raise RuntimeError("upstream down")


ok(sc.cached("k", 0.05, boom) == "good", "stale answer served while the refresh fails")
time.sleep(0.2)
ok(sc.cached("k", 60, boom) == "good", "the failure did not replace it")

print("\n4. Keys are independent and concurrent first calls are safe")
sc.clear()
ok(sc.cached("a", 60, lambda: 1) == 1 and sc.cached("b", 60, lambda: 2) == 2, "separate keys")
results = []
threads = [threading.Thread(target=lambda: results.append(sc.cached("c", 60, slow("c", 0.05))))
           for _ in range(8)]
[t.start() for t in threads]
[t.join() for t in threads]
ok(results == ["c"] * 8, "eight simultaneous first callers all get the answer")
ok(sc.age("c") is not None and sc.age("missing") is None, "age reports stored keys only")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
