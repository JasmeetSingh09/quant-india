"""
access_control_test.py — who may call what (access-control audit, 2026-10-17).

docs/SECURITY_AUDIT_ACCESS_CONTROL_2026-10-17.md found that freezing and
retracting strategy versions, mailing every user, the heavy background jobs and
the corporate-action write were open to anyone. This suite keeps them closed:

  1. every write route (and the one GET that writes) is classified as admin,
     user-owned or public computation; a NEW route that nobody classified fails
     here, so the gap cannot quietly come back;
  2. each admin route refuses when admin is not configured, without a token,
     with a wrong token, and with a forged login naming the admin; and lets a
     real admin through;
  3. alert/digest mail only ever goes to an address from a verified token (F8);
  4. the mail and rebuild routes sit in the heavy rate-limit bucket.

Offline: temporary SQLite, no network, no model; the rate limiter is switched
off inside this process so the checks measure access control, not throttling.

    cd backend && python tests/access_control_test.py
"""
import os
import secrets
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
sys.path.insert(0, os.path.join(HERE, ".."))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="access_control_")
os.environ["QUANT_DATA_DIR"] = TMP
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)
os.environ.pop("ADMIN_USER_IDS", None)
TEST_SECRET = "access-control-test-secret-" + secrets.token_hex(16)
os.environ["SUPABASE_JWT_SECRET"] = TEST_SECRET   # read by auth at import

# The model and the news fetcher are replaced before main imports them, as the
# oracle suite does: access control needs neither, and CI must stay offline
# (importing the real sentiment module downloads FinBERT).
import types                    # noqa: E402


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None


sys.modules["sentiment"] = _Stub("sentiment")
sys.modules["news"] = _Stub("news")

import jwt                      # noqa: E402
import auth                     # noqa: E402
import rate_limit               # noqa: E402
import main as M                # noqa: E402
from fastapi.routing import APIRoute        # noqa: E402
from fastapi.testclient import TestClient   # noqa: E402

rate_limit.check = lambda request: None     # measure access control, not throttling

PASS, FAIL = [], []


def ok(cond, label, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))


def token(sub, secret=TEST_SECRET, email=None):
    claims = {"sub": sub, "aud": "authenticated", "exp": int(time.time()) + 600}
    if email:
        claims["email"] = email
    return jwt.encode(claims, secret, algorithm="HS256")


# ---------------------------------------------------------------- the policy
# Owner-only. Each takes Depends(require_admin).
ADMIN = {
    ("POST", "/strategy/freeze"), ("POST", "/strategy/retract"),
    ("POST", "/digest/run-now"),
    ("POST", "/alpha/universe/scan"), ("POST", "/screener/refresh"),
    ("POST", "/alerts/run-check"), ("POST", "/alpha/retrain"),
    ("POST", "/simulator/seed-demos"),
    ("POST", "/predictions/seal"), ("POST", "/predictions/snapshot"),
    ("POST", "/bhavcopy/fetch"), ("POST", "/bhavcopy/backfill"),
    ("POST", "/bhavcopy/backfill-range"), ("POST", "/actions/backfill"),
    ("POST", "/stock/universe/refresh"),
}
# Pure calculation or analysis: writes nothing, rate-limited, public by design.
# /simulator/challenge/submit records an anonymous answer to the weekly quiz.
PUBLIC_COMPUTE = {
    "/simulator/historic", "/simulator/compare", "/simulator/challenge/submit",
    "/calc/sip", "/calc/lumpsum", "/calc/tax", "/risk/position-size", "/risk/decomposition",
    "/screener", "/alpha/scan", "/tax/after-tax", "/optimizer/stability",
    "/portfolio/suggest-fix", "/portfolio/fit", "/portfolio/shock/compare", "/portfolio/shock/multi",
    "/models/compare", "/portfolio/shock", "/portfolio/shock/presets",
    "/portfolio/correlation-over-time", "/strategy/compare", "/portfolio/what-if",
    "/portfolio/scenarios", "/portfolio/build",
    "/optimizer/mvo", "/optimizer/black-litterman", "/optimizer/frontier", "/optimizer/hrp",
    "/optimizer/regime-adaptive", "/optimizer/risk-parity", "/optimizer/max-diversification",
    "/optimizer/min-cvar", "/optimizer/auto",
    "/pairs/find", "/pairs/analyze", "/pairs/backtest",
    "/montecarlo/simulate", "/montecarlo/compare",
    "/options/black-scholes", "/options/implied-vol",
    "/research/momentum", "/research/correlation", "/research/macro-signal",
}
# A GET route that writes in one mode; that mode is admin-only, checked inline.
WRITING_GET = {"/health/corporate-action-audit"}


def dep_calls(route):
    seen, stack = set(), [route.dependant]
    while stack:
        d = stack.pop()
        if d.call is not None:
            seen.add(d.call)
        stack.extend(d.dependencies)
    return seen


print("\n1. EVERY WRITE ROUTE IS CLASSIFIED")
routes = [r for r in M.app.routes if isinstance(r, APIRoute)]
writes = [(m, r) for r in routes for m in sorted(r.methods) if m != "GET" and m != "HEAD"]
unclassified, wrong_admin, wrong_user = [], [], []
for m, r in writes:
    calls = dep_calls(r)
    is_admin = auth.require_admin in calls
    is_user = auth.current_user_id in calls or auth.current_user_email in calls
    if (m, r.path) in ADMIN:
        if not is_admin:
            wrong_admin.append(f"{m} {r.path}")
    elif is_user:
        pass                                  # user-owned: takes the caller's identity
    elif r.path in PUBLIC_COMPUTE:
        if is_admin:
            wrong_user.append(f"{m} {r.path} (admin but listed public)")
    else:
        unclassified.append(f"{m} {r.path}")
ok(not unclassified, "no write route is unclassified (a new one must be added to this policy)",
   ", ".join(unclassified))
ok(not wrong_admin, "every admin route depends on require_admin", ", ".join(wrong_admin))
ok(not wrong_user, "no public route is accidentally admin", ", ".join(wrong_user))
present = {(m, r.path) for m, r in writes}
ok(ADMIN <= present, "every admin route in the policy exists", sorted(ADMIN - present))
ok(all(any(r.path == p for r in routes) for p in WRITING_GET), "the writing GET exists")
ok(len(ADMIN) == 15, "15 admin write routes, as audited", len(ADMIN))

client = TestClient(M.app)
BODY = {"/strategy/freeze": {"version": "vTEST", "notes": "x"},
        "/strategy/retract": {"version": "vTEST", "reason": "x"}}
PARAMS = {"/bhavcopy/backfill-range": {"start": "2020-01-01", "end": "2020-01-02"}}


def call(method, path, headers=None):
    return client.request(method, path, json=BODY.get(path), params=PARAMS.get(path),
                          headers=headers or {})


print("\n2. ADMIN ROUTES ARE CLOSED")
# 2a. nothing configured: closed for everyone, even a perfectly valid admin-looking token
res = {(m, p): call(m, p, {"X-Admin-Token": "x" * 40}) for m, p in sorted(ADMIN)}
ok(all(r.status_code == 403 and "not configured" in r.text for r in res.values()),
   "with no admin configured, all 15 refuse (fails closed)",
   {f"{m} {p}": r.status_code for (m, p), r in res.items() if r.status_code != 403})

ADMIN_TOKEN = secrets.token_urlsafe(40)
OWNER = "owner-" + secrets.token_hex(8)
os.environ["ADMIN_TOKEN"] = ADMIN_TOKEN
os.environ["ADMIN_USER_IDS"] = OWNER
cases = {
    "no credentials": {},
    "wrong admin token": {"X-Admin-Token": secrets.token_urlsafe(40)},
    "forged login naming the owner (wrong signing key)":
        {"Authorization": "Bearer " + token(OWNER, secret="not-the-secret-" + secrets.token_hex(8))},
    "a real login that is not the owner": {"Authorization": "Bearer " + token("someone-else")},
}
for name, hdr in cases.items():
    bad = {f"{m} {p}": r.status_code for m, p in sorted(ADMIN) if (r := call(m, p, hdr)).status_code != 403}
    ok(not bad, f"refused: {name}", bad)

r = client.get("/health/corporate-action-audit", params={"part": "apply", "confirm": "APPLY-REPARSE"})
ok(r.status_code == 403, "the corporate-action write refuses the public confirm token alone", r.status_code)

print("\n3. A REAL ADMIN GETS THROUGH")
ok(auth.require_admin(None, ADMIN_TOKEN) == "admin:token", "the admin token is accepted")
ok(auth.require_admin("Bearer " + token(OWNER), None) == f"admin:{OWNER}",
   "a verified login whose id is in ADMIN_USER_IDS is accepted")
os.environ["ADMIN_TOKEN"] = "short"
try:
    auth.require_admin(None, "short")
    ok(False, "a token under 32 characters is never accepted")
except Exception as e:
    ok(getattr(e, "status_code", None) == 403, "a token under 32 characters is never accepted")
os.environ["ADMIN_TOKEN"] = ADMIN_TOKEN
# End to end through two cheap, local-only routes (temporary SQLite, no network):
r = call("POST", "/predictions/seal", {"X-Admin-Token": ADMIN_TOKEN})
ok(r.status_code != 403, "POST /predictions/seal runs for the admin", r.status_code)
r = client.get("/health/corporate-action-audit", params={"part": "apply"},
               headers={"X-Admin-Token": ADMIN_TOKEN})
ok(r.status_code != 403, "the corporate-action apply path is reachable for the admin "
   "(it then refuses without its confirm token)", r.status_code)
r = client.get("/health/corporate-action-audit", params={"part": "nonsense-read"})
ok(r.status_code != 403, "the read-only parts of that route stay public", r.status_code)
st = auth.auth_status()
ok(st.get("admin_configured") is True and ADMIN_TOKEN not in str(st) and OWNER not in str(st),
   "/ reports admin_configured as yes/no only, never a value")

print("\n4. MAIL GOES ONLY TO A VERIFIED ADDRESS (F8)")
ok(auth.current_user_email("Bearer " + token("u1", email="real@example.com")) == "real@example.com",
   "a verified token's email is used")
forged = "Bearer " + token("u1", secret="not-the-secret-" + secrets.token_hex(8), email="victim@example.com")
ok(auth.current_user_email(forged) is None, "a forged token's email is never used (HS256 configured)")
saved = (auth._JWT_SECRET, auth._SUPABASE_URL, auth._jwks_client)
try:
    auth._JWT_SECRET, auth._SUPABASE_URL = "", "https://example.invalid"
    auth._jwks_client = lambda: None          # no network: JWKS "configured" but unreachable
    ok(auth.current_user_email(forged) is None,
       "a forged token's email is never used when only JWKS is configured (the F8 hole)")
finally:
    auth._JWT_SECRET, auth._SUPABASE_URL, auth._jwks_client = saved

print("\n5. MAIL AND REBUILD ROUTES ARE HEAVY")
for p in ("/digest/run-now", "/digest/send", "/alerts/test", "/alerts/send", "/screener/refresh",
          "/alpha/retrain", "/alpha/universe/scan"):
    ok(rate_limit.bucket_for(p) == "heavy", f"{p} is in the heavy bucket", rate_limit.bucket_for(p))
ok(rate_limit.bucket_for("/alpha/universe/status") == "medium", "reading scan status is not throttled as heavy")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
