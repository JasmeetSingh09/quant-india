"""
score_cache_test.py — caching a score must never change one.

/alpha/score recomputed from scratch on every request. Everything behind it was
already cached -- .info for 24 hours, interest coverage for 24 hours, the picks
list for six -- but the result was not, so two people opening the same stock a
second apart each paid a full round of Yahoo calls. Measured cold at 7.6 to 8.0
seconds, essentially all of it network.

A result cache is safe only if it is invisible, so that is what is tested:

    a hit must equal a miss, field for field, not merely in the headline score;
    an experiment must never be cached -- custom weights or an explicit peer
        list are not the frozen model and must not be served to someone who
        asked for the frozen model, nor the reverse;
    the entry must expire, so a stale score cannot outlive its TTL.

The first version of this change wrote to the cache from the wrong function --
the edit landed in explain_signal, where the guard variable did not exist -- and
the read path quietly reported zero hits forever. The cache statistics are
asserted here for that reason: a cache that silently never caches looks exactly
like a slow app.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("QUANT_DATA_DIR", os.environ.get("TEMP", "/tmp"))

import alpha_model as A  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


CALLS = {"n": 0}
_real_sent = A._compute_sentiment_factor


def _counting(ticker):
    CALLS["n"] += 1
    return {"score": 0.25, "confidence": 0.8, "interpretation": "stub"}


# Stub every factor so the test needs no network and the only thing under
# examination is the caching itself.
A._compute_sentiment_factor = _counting
A._compute_momentum_factor = lambda t, p=None: {"score": 0.1, "confidence": 0.9,
                                                "interpretation": "stub"}
A._compute_quality_factor = lambda t: {"score": -0.2, "confidence": 0.7,
                                       "interpretation": "stub"}
A._compute_value_factor = lambda t, p=None: {"score": 0.05, "confidence": 0.6,
                                             "interpretation": "stub"}
A._ticker_info = lambda t: {"marketCap": 1e11}

print("=" * 72)
print("A HIT MUST EQUAL A MISS")
print("=" * 72)

A._SCORE_CACHE.clear()
CALLS["n"] = 0
first = A.compute_alpha_score("TESTCO.NS")
after_first = CALLS["n"]
second = A.compute_alpha_score("TESTCO.NS")
after_second = CALLS["n"]

check("the first call computes", after_first == 1, f"{after_first} computation(s)")
check("the second call does NOT recompute", after_second == 1,
      f"{after_second} computation(s) total")
check("the cache actually holds the entry", len(A._SCORE_CACHE) == 1,
      f"entries={len(A._SCORE_CACHE)}")
check("and reports a hit", A._SCORE_CACHE.stats()["hits"] >= 1,
      f"{A._SCORE_CACHE.stats()}")
check("hit equals miss, whole response",
      first == second, "field for field, not just alpha_score")
for k in ("alpha_score", "signal", "confidence", "contributions", "factors"):
    check(f"  {k} identical", first.get(k) == second.get(k))

print()
print("=" * 72)
print("AN EXPERIMENT IS NOT THE FROZEN MODEL")
print("=" * 72)

A._SCORE_CACHE.clear()
CALLS["n"] = 0
A.compute_alpha_score("EXPCO.NS")
n_after_frozen = CALLS["n"]
custom = {"sentiment": 0.4, "momentum": 0.4, "quality": 0.1, "value": 0.1}
A.compute_alpha_score("EXPCO.NS", weights=custom)
check("custom weights are NOT served from the frozen cache",
      CALLS["n"] == n_after_frozen + 1,
      "it recomputed rather than returning the frozen score")
check("and are not written into it", len(A._SCORE_CACHE) == 1,
      f"entries={len(A._SCORE_CACHE)}")

CALLS["n"] = 0
A.compute_alpha_score("EXPCO.NS", peers=["FOO.NS"])
check("an explicit peer list is also not cached", CALLS["n"] == 1)
check("the frozen entry is still the only one cached",
      len(A._SCORE_CACHE) == 1, f"entries={len(A._SCORE_CACHE)}")

CALLS["n"] = 0
A.compute_alpha_score("EXPCO.NS")
check("and the frozen score is still served from cache", CALLS["n"] == 0)

print()
print("=" * 72)
print("IT EXPIRES")
print("=" * 72)

A._SCORE_CACHE.clear()
CALLS["n"] = 0
A.compute_alpha_score("TTLCO.NS")
stamp, payload = A._SCORE_CACHE.get("TTLCO.NS")
A._SCORE_CACHE["TTLCO.NS"] = (stamp - A._SCORE_TTL - 1, payload)
A.compute_alpha_score("TTLCO.NS")
check("an entry older than the TTL is recomputed", CALLS["n"] == 2,
      f"{CALLS['n']} computations")
check("the TTL is 15 minutes", A._SCORE_TTL == 900, f"{A._SCORE_TTL}s")

print()
print("=" * 72)
print("THE CACHE IS BOUNDED AND SEPARATE")
print("=" * 72)

from bounded_cache import BoundedCache  # noqa: E402

check("it is a BoundedCache, not a bare dict",
      isinstance(A._SCORE_CACHE, BoundedCache))
check("it is bounded", A._SCORE_CACHE.stats()["maxsize"] == 512)
check("it is registered for /health/caches",
      A._SCORE_CACHE.stats()["name"] == "alpha_model._SCORE_CACHE")

import inspect  # noqa: E402

src = inspect.getsource(A.explain_signal)
check("explain_signal does not reference the cache guard",
      "_cacheable" not in src,
      "the first attempt wrote the cache from inside this function")

A._compute_sentiment_factor = _real_sent

print()
print("=" * 72)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
