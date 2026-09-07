"""
bounded_cache_test.py — the ceiling must hold, and nothing else may change.

A cache swap is a dangerous kind of edit: it touches ten modules, changes no
visible behaviour when it works, and when it is wrong it returns a value the
caller did not expect rather than raising. So this checks two things with equal
weight.

    1. The bound holds. Writing the whole exchange through a cache sized for a
       few hundred names leaves a few hundred entries, not a few thousand —
       under concurrent writers, which is how the scan actually runs.

    2. Within the bound, it is still a dict. Every call site uses `.get(k)`,
       `c[k] = v`, `len(c)` and `.clear()` on what it believes is a plain dict,
       and some of them are in the alpha path. A cache that quietly stops
       behaving like a dict would change scores.

The eviction ORDER is the part worth testing hardest. Insertion-order eviction
and least-recently-used eviction agree on every write-only workload and disagree
exactly where it matters: an entry read on every stock must not be discarded
because it happened to be written first.
"""

import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from bounded_cache import BoundedCache, registry  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


print("=" * 72)
print("THE CEILING HOLDS")
print("=" * 72)

c = BoundedCache(100, "t")
for i in range(10_000):
    c[f"k{i}"] = i
check("10,000 writes into a cache of 100 leave 100", len(c) == 100, f"len={len(c)}")
check("evictions are counted", c.evictions == 9900, f"evictions={c.evictions}")
check("the newest entry survived", c.get("k9999") == 9999)
check("the oldest entry is gone", c.get("k0") is None)

# The real shape: a full-universe scan against the production limit.
c = BoundedCache(512, "scan")
for i in range(2600):
    c[f"TICKER{i}.NS"] = {"info": "x" * 100}
check("a 2,600-stock scan leaves 512 entries, not 2,600",
      len(c) == 512, f"len={len(c)}")

c = BoundedCache(1, "one")
c["a"] = 1
c["b"] = 2
check("a cache of 1 holds exactly 1", len(c) == 1 and c.get("b") == 2)

c = BoundedCache(0, "zero")
c["a"] = 1
check("maxsize below 1 is clamped, not a divide-by-zero", len(c) == 1)

print()
print("=" * 72)
print("EVICTION ORDER IS LEAST-RECENTLY-USED, NOT FIRST-WRITTEN")
print("=" * 72)

c = BoundedCache(3, "lru")
c["a"], c["b"], c["c"] = 1, 2, 3
c.get("a")               # 'a' is now the most recently used
c["d"] = 4               # must evict 'b', the least recently used
check("a re-read entry survives eviction", c.get("a") == 1)
check("the least recently USED entry is evicted", c.get("b") is None)
check("untouched newer entries remain", c.get("c") == 3 and c.get("d") == 4)

c = BoundedCache(3, "lru2")
c["a"], c["b"], c["c"] = 1, 2, 3
_ = c["a"]               # bracket access must mark recency too, not just .get
c["d"] = 4
check("bracket access marks recency as well as .get()", c.get("a") == 1,
      "otherwise half the call sites silently get insertion-order eviction")

# The failure this prevents: the scan reads a hot entry on every stock while
# writing thousands of cold ones. Under insertion-order eviction the hot entry
# is dropped anyway.
c = BoundedCache(50, "hot")
c["HOT"] = "keep me"
for i in range(5000):
    c[f"cold{i}"] = i
    c.get("HOT")
check("a hot entry survives 5,000 cold writes", c.get("HOT") == "keep me")

print()
print("=" * 72)
print("IT IS STILL A DICT")
print("=" * 72)

c = BoundedCache(512, "dictlike")
check("isinstance(c, dict) holds", isinstance(c, dict))
c["k"] = 1
check("bracket set and get round-trip", c["k"] == 1)
check("get with a default", c.get("nope", "dflt") == "dflt")
check("get without a default returns None", c.get("nope") is None)
check("`in` works", "k" in c and "nope" not in c)
check("len works", len(c) == 1)
c["k"] = 2
check("overwriting does not grow the cache", len(c) == 1 and c["k"] == 2)
c.clear()
check("clear empties it", len(c) == 0)

c["x"] = (1.5, {"a": 1})
check("tuple/dict values survive intact", c["x"] == (1.5, {"a": 1}))
c[("RELIANCE.NS", "2024-01-01", None)] = "series"
check("tuple keys work (price caches use them)",
      c.get(("RELIANCE.NS", "2024-01-01", None)) == "series")

try:
    c["missing_key_raises"]
    ok = False
except KeyError:
    ok = True
check("a missing bracket lookup raises KeyError, as a dict does", ok)

# Equivalence against a plain dict, within the bound: the swap must not have
# changed a single value any caller reads.
plain, bound = {}, BoundedCache(1000, "eq")
import random  # noqa: E402

random.seed(7)
for _ in range(3000):
    k = f"k{random.randint(0, 400)}"
    if random.random() < 0.7:
        v = random.random()
        plain[k] = v
        bound[k] = v
    else:
        if plain.get(k) != bound.get(k):
            break
check("identical to a plain dict for 3,000 mixed ops within the bound",
      all(plain[k] == bound.get(k) for k in plain), f"n={len(plain)}")

print()
print("=" * 72)
print("CONCURRENCY — THE SCAN RUNS SIX WORKERS")
print("=" * 72)

c = BoundedCache(200, "threads")
errors = []


def hammer(worker):
    try:
        for i in range(3000):
            c[f"w{worker}-k{i}"] = i
            c.get(f"w{worker}-k{i // 2}")
    except Exception as e:            # an eviction race shows up as KeyError
        errors.append(f"{type(e).__name__}: {e}")


threads = [threading.Thread(target=hammer, args=(w,)) for w in range(6)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check("18,000 concurrent ops across 6 threads raise nothing", not errors,
      f"errors={errors[:2]}")
check("the bound still holds after concurrent eviction", len(c) == 200,
      f"len={len(c)}")

print()
print("=" * 72)
print("OBSERVABILITY")
print("=" * 72)

c = BoundedCache(10, "stats")
for i in range(20):
    c[f"k{i}"] = i
c.get("k19"), c.get("k19"), c.get("gone")
s = c.stats()
check("stats reports entries at the ceiling", s["entries"] == 10)
check("stats reports evictions", s["evictions"] == 10, f"{s['evictions']}")
check("stats reports a hit rate", s["hit_rate_pct"] is not None
      and 0 <= s["hit_rate_pct"] <= 100, f"{s['hit_rate_pct']}%")
check("stats flags a full cache", s["full"] is True)
check("a fresh cache reports no hit rate rather than 0%",
      BoundedCache(4, "fresh").stats()["hit_rate_pct"] is None)

print()
print("=" * 72)
print("THE PRODUCTION CACHES ARE ACTUALLY BOUNDED")
print("=" * 72)

import warnings  # noqa: E402

warnings.filterwarnings("ignore")
os.environ.setdefault("QUANT_DATA_DIR", os.environ.get("TEMP", "/tmp"))

MODULES = ["alpha_model", "data_fetcher", "metrics", "monte_carlo",
           "prediction_tracker", "benchmark", "liquidity", "regime_detector",
           "simulator", "auth"]
failed_imports = []
for m in MODULES:
    try:
        __import__(m)
    except Exception as e:
        failed_imports.append(f"{m}: {type(e).__name__}")
check("every patched module still imports", not failed_imports,
      f"{failed_imports}")

found = {f"{r['module']}.{r['attr']}" for r in registry()}
EXPECTED = [
    "alpha_model._INFO_CACHE", "alpha_model._COVERAGE_CACHE",
    "data_fetcher._INFO_CACHE", "data_fetcher._FUND_CACHE",
    "data_fetcher._PRICE_CACHE", "data_fetcher._LIVE_CACHE",
    "metrics._METRICS_CACHE", "monte_carlo._HIST_CACHE",
    "monte_carlo._PRICE_CACHE", "prediction_tracker._CLOSE_CACHE",
    "benchmark._CACHE", "liquidity._CACHE", "regime_detector._REGIME_CACHE",
    "simulator._SPLIT_CACHE", "simulator._DIV_CACHE", "auth._EMAIL_CACHE",
]
missing = [e for e in EXPECTED if e not in found]
check(f"all {len(EXPECTED)} scan-path caches are bounded", not missing,
      f"unbounded={missing}")

# The old guards must be gone. Left in place they fire at the same threshold the
# LRU uses and clear the whole cache -- strictly worse than before this change.
import glob  # noqa: E402
import io  # noqa: E402
import re  # noqa: E402

leftover = []
for f in glob.glob(os.path.join(os.path.dirname(__file__), "..", "modules", "*.py")):
    if os.path.basename(f) == "bounded_cache.py":
        continue
    src = io.open(f, encoding="utf-8").read()
    if re.search(r"if len\(_[A-Z_]*CACHE\) > \d+", src):
        leftover.append(os.path.basename(f))
check("no flush-at-threshold guard survives the swap", not leftover,
      f"found in {leftover}")

print()
print("=" * 72)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
