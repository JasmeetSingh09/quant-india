"""
data_failure_audit.py — what the app does when the data does not arrive.

The rule being tested: missing data must never become a number. Not a zero, not
a NEUTRAL, not a confident-looking score with nothing behind it. Either the
value is marked unavailable and coverage drops, or the call is refused.

Failures are simulated by monkeypatching the fetchers, because waiting for a
real 429 is not a test. Every patch is reverted afterwards so one failure mode
cannot leak into the next.
"""

import io
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

checks = 0
failures = []


def ok(cond, label, evidence=""):
    global checks
    checks += 1
    if not cond:
        failures.append(label + (f" — {evidence}" if evidence else ""))


class patched:
    """Swap an attribute for the duration of a block, then put it back."""

    def __init__(self, module, name, replacement):
        self.m, self.n, self.r = module, name, replacement
        self.original = None

    def __enter__(self):
        self.original = getattr(self.m, self.n, None)
        setattr(self.m, self.n, self.r)
        return self

    def __exit__(self, *a):
        if self.original is not None:
            setattr(self.m, self.n, self.original)
        return False


def boom(exc):
    def _f(*a, **k):
        raise exc
    return _f


def returns(value):
    def _f(*a, **k):
        return value
    return _f


# ---------------------------------------------------------------------------
print("=== price feed failures ===")
import portfolio_shock as ps

H = {"RELIANCE.NS": 40, "TCS.NS": 30, "INFY.NS": 30}

FEED_FAILURES = [
    ("timeout", boom(TimeoutError("timed out"))),
    ("HTTP 500", boom(RuntimeError("500 Internal Server Error"))),
    ("HTTP 429 rate limited", boom(RuntimeError("429 Too Many Requests"))),
    ("malformed JSON", boom(ValueError("Expecting value: line 1 column 1"))),
    ("empty frame", returns(None)),
]

for label, repl in FEED_FAILURES:
    with patched(ps, "_returns", repl):
        try:
            r = ps.shock(H, kind="market", magnitude_pct=-20, initial_value=100000)
            ok(isinstance(r, dict) and "error" in r,
               f"price feed {label}: refuses rather than returning a fake shock",
               str(r)[:80])
        except Exception as e:
            ok(False, f"price feed {label}: raised instead of refusing",
               f"{type(e).__name__}")

# A shock that cannot be computed must not report a change of 0%, which reads
# as "your portfolio is fine" rather than "we do not know".
with patched(ps, "_returns", returns(None)):
    r = ps.shock(H, kind="market", magnitude_pct=-30, initial_value=100000)
    ok("change_pct" not in r,
       "a failed shock reports no change figure at all", str(r.get("change_pct")))


# ---------------------------------------------------------------------------
print("=== fundamentals failures ===")
import scenario_valuation as sv

FUND_FAILURES = [
    ("empty dict", returns({})),
    ("None", returns(None)),
    ("error payload", returns({"error": "not found"})),
    ("missing P/E", returns({"revenue_growth": 0.1})),
    ("P/E is None", returns({"pe_ratio": None, "revenue_growth": 0.1})),
    ("negative P/E", returns({"pe_ratio": -12.0, "earnings_growth": 0.1})),
    ("zero P/E", returns({"pe_ratio": 0.0, "earnings_growth": 0.1})),
    ("P/E wrong type", returns({"pe_ratio": "cheap", "earnings_growth": 0.1})),
    ("raises", boom(RuntimeError("upstream exploded"))),
]

import metrics as _metrics_mod
for label, repl in FUND_FAILURES:
    with patched(_metrics_mod, "get_full_metrics", repl):
        # scenario_valuation imports the function inside the call, so patching
        # the module attribute is what a real failure would look like.
        try:
            r = sv.scenarios("TCS.NS", years=3)
            ok(r.get("available") is False,
               f"fundamentals {label}: scenario refused", str(r.get("available")))
            ok(bool(r.get("reason")),
               f"fundamentals {label}: says why it refused")
            ok("scenarios" not in r,
               f"fundamentals {label}: no scenario numbers are produced")
        except Exception as e:
            ok(False, f"fundamentals {label}: raised instead of refusing",
               type(e).__name__)


# ---------------------------------------------------------------------------
print("=== alpha with degraded inputs ===")
import alpha_v2 as av

# A ticker that does not exist must not produce a score.
r = av.compute_v2("NOTAREALTICKER" + str(os.getpid()) + ".NS")
ok("error" in r or r.get("alpha_score") is None,
   "a nonexistent ticker yields no alpha score", str(r.get("alpha_score")))

# Coverage must fall when factors are missing, and must never exceed 1.
real = av.compute_v2("TCS.NS")
if "error" not in real:
    cov = real.get("factor_coverage")
    ok(cov is None or 0.0 <= cov <= 1.0,
       "coverage stays a fraction", str(cov))
    score = real.get("alpha_score")
    ok(score is None or math.isfinite(score),
       "alpha score is finite or absent", str(score))


# ---------------------------------------------------------------------------
print("=== sentiment / news failures ===")
# The rule: no news must not read as neutral-good news. It must read as no data.
import factor_history as fh

# Stale/absent history must not become a zero change.
ghost = "GHOST" + str(os.getpid()) + ".NS"
c = fh.change(ghost, days=30)
ok(c.get("status") == "no_history",
   "no recorded history reports no_history, not zero change", str(c.get("status")))
ok(not c.get("factors"),
   "no factor deltas are fabricated for an unseen stock")

d = fh.divergences(ghost, days=30)
ok(d.get("divergences") == [],
   "no divergences are invented from absent history")


# ---------------------------------------------------------------------------
print("=== portfolio advice with broken inputs ===")
from portfolio_advisor import advise

BAD_PORTFOLIOS = [
    ({}, "empty"),
    ({"TCS.NS": 0}, "zero weight"),
    ({"NOTREAL" + str(os.getpid()) + ".NS": 100}, "unknown ticker only"),
    ({"TCS.NS": float("nan")}, "NaN weight"),
    ({"TCS.NS": float("inf")}, "infinite weight"),
]
for holdings, label in BAD_PORTFOLIOS:
    try:
        r = advise(holdings, initial_value=100000)
        ok(isinstance(r, dict), f"advise({label}) returns a dict")
        v = r.get("verdict")
        if v:
            # If it produced a verdict at all, every number in it must be real.
            for c_ in (v.get("concerns") or []):
                eff = c_.get("effect") or {}
                for k, val in eff.items():
                    if isinstance(val, float):
                        ok(math.isfinite(val),
                           f"advise({label}): no non-finite number in effects",
                           f"{k}={val}")
    except Exception as e:
        ok(False, f"advise({label}) raised", type(e).__name__)


# ---------------------------------------------------------------------------
print("=== secrets must not leak ===")
FRONT = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src")
SECRET_HINTS = ("NEWSAPI_KEY", "OPENAI_API_KEY", "SUPABASE_SERVICE",
                "SERVICE_ROLE", "DATABASE_URL", "JWT_SECRET")
leaked = []
for dirpath, _, files in os.walk(FRONT):
    for f in files:
        if not f.endswith((".js", ".jsx", ".ts", ".tsx")):
            continue
        path = os.path.join(dirpath, f)
        try:
            txt = io.open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for hint in SECRET_HINTS:
            if hint in txt:
                leaked.append(f"{os.path.relpath(path, FRONT)}: {hint}")
ok(not leaked, "no server-side secret name appears in frontend source",
   "; ".join(leaked[:4]))

# The anon Supabase key is *meant* to be public; the service key never is.
sup = os.path.join(FRONT, "supabaseClient.js")
if os.path.exists(sup):
    txt = io.open(sup, encoding="utf-8", errors="replace").read()
    ok("SERVICE_ROLE" not in txt and "service_role" not in txt,
       "the service-role key is not referenced in the browser client")


# ---------------------------------------------------------------------------
print("\n" + "=" * 66)
print(f"DATA-FAILURE CHECKS: {checks}")
print(f"FAILURES:            {len(failures)}")
for f in failures:
    print(f"   FAIL: {f}")
print("=" * 66)
sys.exit(1 if failures else 0)
