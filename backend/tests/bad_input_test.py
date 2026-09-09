"""
bad_input_test.py — a bad ticker must be refused, not crash.

Found by adversarially testing the live API: 238 requests across 17
ticker-taking endpoints and 14 input classes produced twelve HTTP 500s.

    /alpha/explain              10 of 14 inputs -> 500
    /stock/volatility-forecast   2 of 14 inputs -> 500

The /alpha/explain case is the instructive one. compute_alpha_score already
refuses a ticker nothing resolves for and returns {"error": ...} -- that guard
was added deliberately, after "ZZZQQQ123.NS" once scored -5.27 NEUTRAL. But
explain_signal calls it and then immediately reads alpha["contributions"],
so the refusal became a KeyError and the refusal became a 500.

A guard is only as good as its callers. That is what these tests are for.

Included in the failing set: "RELIANCE" with no .NS suffix, and "ZOMATO.NS",
which was renamed to ETERNAL. Neither is abuse -- the first is a user typing a
ticker the ordinary way and the second is a real company. Both returned 500.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("QUANT_DATA_DIR", os.environ.get("TEMP", "/tmp"))

import alpha_model as A  # noqa: E402
import garch_vol as G  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


# The exact inputs that produced 500s in production, plus the empty cases.
BAD = [
    ("empty", ""),
    ("whitespace", "   "),
    ("nonexistent", "ZZZQQQ123.NS"),
    ("html", "<script>alert(1)</script>"),
    ("very long", "A" * 300),
    ("unicode", "\u0930\u093f\u0932\u093e\u092f\u0902\u0938"),
    ("path traversal", "../../etc/passwd"),
    ("null byte", "RELIANCE\x00.NS"),
    ("sql-ish", "'; DROP TABLE x;--"),
]

print("=" * 72)
print("explain_signal MUST NOT RAISE")
print("=" * 72)

# Stub the factors so this needs no network: the point is the error path, and
# a refusal must survive it whatever the factors say.
A._compute_sentiment_factor = lambda t: {"score": 0.0, "confidence": 0.0,
                                         "reason": "stub"}
A._compute_momentum_factor = lambda t, p=None: {"score": 0.0, "confidence": 0.0,
                                                "reason": "stub"}
A._compute_quality_factor = lambda t: {"score": 0.0, "confidence": 0.0,
                                       "reason": "stub"}
A._compute_value_factor = lambda t, p=None: {"score": 0.0, "confidence": 0.0,
                                             "reason": "stub"}
A._ticker_info = lambda t: {}          # no marketCap -> the symbol does not resolve
A._SCORE_CACHE.clear()

for label, val in BAD:
    try:
        r = A.explain_signal(val, run_factor_check=False)
        ok = isinstance(r, dict) and "error" in r
        check(f"{label:<16} returns an error dict", ok,
              f"{str(r)[:60]}" if not ok else "")
    except Exception as e:
        check(f"{label:<16} returns an error dict", False,
              f"RAISED {type(e).__name__}: {e}")

print()
print("=" * 72)
print("forecast_vol MUST NOT RAISE ON A BLANK TICKER")
print("=" * 72)

for label, val in (("empty", ""), ("whitespace", "   "), ("null byte", "\x00")):
    try:
        r = G.forecast_vol(val)
        ok = isinstance(r, dict) and "error" in r
        check(f"{label:<16} returns an error dict", ok, f"{str(r)[:60]}")
    except Exception as e:
        check(f"{label:<16} returns an error dict", False,
              f"RAISED {type(e).__name__}: {e}")

print()
print("=" * 72)
print("THE GUARD'S CALLERS, NOT JUST THE GUARD")
print("=" * 72)

r = A.compute_alpha_score("ZZZQQQ123.NS")
check("compute_alpha_score still refuses a fake ticker",
      isinstance(r, dict) and "error" in r,
      "this guard already existed; the bug was that a caller ignored it")

import inspect  # noqa: E402

src = inspect.getsource(A.explain_signal)
check("explain_signal checks for the error before unpacking",
      'if "error" in' in src or "'error' in" in src,
      "reading alpha['contributions'] off a refusal is the KeyError that 500ed")

print()
print("=" * 72)
print("THE UNIVERSE GUARD — RESOLVING IS NOT BELONGING")
print("=" * 72)

# The adversarial sweep tested symbols that do not resolve. It missed the worse
# case: symbols that resolve perfectly and are not ours. The old guard asked
# "does this have a marketCap", which AAPL, SPY and BTC-USD all do, so the app
# scored them -- AAPL BUY +33, SPY BUY +27, BTC-USD NEUTRAL -13. Every number
# meaningless: value compares against NSE sector peers, the benchmark is NIFTY,
# USD prices are read as rupees, and Bitcoin has no fundamentals at all.
# The guard has two layers and they must be tested separately, because a stub
# that makes everything resolve disables the second one. That mistake was made
# here first: with marketCap always present, "AAPL.NS" looked like a real NSE
# stock and the test failed against correct code.
#
#   layer 1  an explicit foreign suffix is refused outright
#   layer 2  a bare symbol becomes SYMBOL.NS, which then fails to resolve

# --- layer 1: everything resolves, so only the suffix rule can act ---------
A._ticker_info = lambda t: {"marketCap": 1e12}
A._SCORE_CACHE.clear()

for sym in ("RELIANCE.BO", "VOD.L", "7203.T", "BRK.B"):
    r = A.compute_alpha_score(sym)
    check(f"{sym:<12} (foreign suffix) refused on the suffix alone",
          "error" in r and "NSE" in str(r.get("error")),
          str(r.get("error"))[:52] if "error" in r else f"SCORED {r.get('alpha_score')}")

for sym in ("AAPL", "SPY", "BTC-USD", "MSFT"):
    r = A.compute_alpha_score(sym)
    check(f"{sym:<12} is normalised to .NS before anything else",
          r.get("ticker", "").endswith(".NS"),
          f"became {r.get('ticker')}")

# --- layer 2: nothing resolves, which is the truth for AAPL.NS ------------
A._ticker_info = lambda t: {}
A._SCORE_CACHE.clear()
for sym in ("AAPL", "SPY", "BTC-USD", "MSFT", "TSLA", "AAAA"):
    r = A.compute_alpha_score(sym)
    check(f"{sym:<12} is refused once .NS fails to resolve", "error" in r,
          f"scored {r.get('alpha_score')}" if "error" not in r else "")

check("the guard is about the SUFFIX, not about resolving",
      "endswith" in inspect.getsource(A.compute_alpha_score),
      "marketCap was the wrong question — AAPL has one")

print()
print("=" * 72)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
