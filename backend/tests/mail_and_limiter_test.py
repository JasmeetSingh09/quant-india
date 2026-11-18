"""
mail_and_limiter_test.py — who can make the server send mail, and whether the
rate limit holds for everyone without becoming the outage (bug hunt v4,
V4-03 / V4-14 / V4-16, and the Codex review R1-R3, R5-R7, 18 Nov 2026).

  1. /alerts/test, /alerts/send, /digest/send and the e-mail opt-in accept only
     a token that verifies (fail closed when verification is not configured)
     and only the account's own CONFIRMED address from the auth server (never
     user_metadata); replies follow a fixed public schema with no recipient,
     no nested transport result and no SMTP text — SMTP is mocked at the
     transport, so the real wrappers run;
  2. ticker, company name and headline are escaped in alert HTML, and a mail
     subject cannot carry a line break;
  3. the limiter counts a caller as signed in only when the token verifies;
     verification runs off the event loop, with bounded concurrency, a
     per-network admission budget and a backoff when keys are unreachable; a
     cached verification ends at the token's own expiry; the network key
     ignores the client-set first X-Forwarded-For hop;
  4. CORS preflights are never throttled and do not use up a budget; a real
     429 keeps its CORS header;
  5. GET /events/funnel reaches the pilot scorecard and is owner-only.

Offline: temporary SQLite, no network, no model, no mail leaves the process.

    cd backend && python tests/mail_and_limiter_test.py
"""
import asyncio
import os
import secrets
import smtplib
import sys
import tempfile
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
sys.path.insert(0, os.path.join(HERE, ".."))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="mail_limiter_")
os.environ["QUANT_DATA_DIR"] = TMP
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)
os.environ.pop("ADMIN_USER_IDS", None)
os.environ["GMAIL_RECEIVER"] = "owner@example.com"
TEST_SECRET = "mail-limiter-test-secret-" + secrets.token_hex(16)
os.environ["SUPABASE_JWT_SECRET"] = TEST_SECRET   # read by auth at import


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None


sys.modules["sentiment"] = _Stub("sentiment")
sys.modules["news"] = _Stub("news")

import jwt                      # noqa: E402
import auth                     # noqa: E402
import alerts                   # noqa: E402
import rate_limit               # noqa: E402
import main as M                # noqa: E402
import weekly_digest            # noqa: E402
import user_prefs               # noqa: E402
from fastapi.testclient import TestClient   # noqa: E402

PASS, FAIL = [], []


def ok(cond, label, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))


def token(sub, secret=TEST_SECRET, email=None, meta_email=None, exp_in=600):
    claims = {"sub": sub, "aud": "authenticated", "exp": int(time.time()) + exp_in}
    if email:
        claims["email"] = email
    if meta_email:
        claims["user_metadata"] = {"email": meta_email}
    return jwt.encode(claims, secret, algorithm="HS256")


def bearer(t):
    return {"Authorization": "Bearer " + t}


class Req:
    """Just enough of a Starlette request for rate_limit."""
    def __init__(self, path="/stock/price", headers=None, host="10.0.0.9", method="GET"):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.url = types.SimpleNamespace(path=path)
        self.client = types.SimpleNamespace(host=host)
        self.method = method


# ---------------------------------------------------------------- the world
# The auth server's user records, by id. Only these say whether an address is
# confirmed; the token's own claims never decide where mail goes.
USERS = {
    "u-real":  {"id": "u-real", "email": "me@example.com", "email_confirmed_at": "2026-11-01T00:00:00Z"},
    "u-unconf": {"id": "u-unconf", "email": "new@example.com", "email_confirmed_at": None},
    "u-noaddr": {"id": "u-noaddr", "email": None, "user_metadata": {"email": "victim@example.com"}},
}
auth._auth_user = lambda t: USERS.get((jwt.decode(t, options={"verify_signature": False}) or {}).get("sub"))

# SMTP is mocked at the transport: the real send_email / send_digest /
# send_test_alert / send_multi_signal_alert all run.
SENT = []
SMTP_RAISE = []


class FakeSMTP:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, *a):
        pass

    def sendmail(self, sender, recipient, msg):
        if SMTP_RAISE:
            raise SMTP_RAISE[0]
        SENT.append(recipient)


alerts.smtplib.SMTP_SSL = FakeSMTP
alerts.GMAIL_SENDER, alerts.GMAIL_PASSWORD = "sender@example.com", "app-password"
import data_fetcher             # noqa: E402
data_fetcher.get_financial_metrics = lambda t: {}
weekly_digest.build_digest = lambda uid: {"subject": "Your week", "html": "<p>week</p>", "n_portfolios": 1}

REAL_CHECK = rate_limit.check
rate_limit.check = lambda request: None     # sections 1-2 measure access, not throttling
client = TestClient(M.app)
ALERT = {"ticker": "INFY", "company_name": "Infosys", "price_change_pct": 1.0,
         "current_price": 10.0, "sentiment_label": "positive", "confidence_pct": 90.0,
         "headline": "x"}
PUBLIC_KEYS = {"sent", "skipped", "n_portfolios"}

print("\n1. MAIL: A VERIFIED TOKEN AND THE ACCOUNT'S OWN CONFIRMED ADDRESS ONLY")
forged = bearer(token("u-real", secret="not-the-secret-" + secrets.token_hex(8), email="victim@example.com"))
for path, body in (("/alerts/test", None), ("/alerts/send", ALERT), ("/digest/send", None)):
    SENT.clear()
    r = client.post(path, json=body)
    ok(r.status_code == 401 and not SENT, f"{path}: anonymous caller refused, nothing sent", r.status_code)
    r = client.post(path, json=body, headers=forged)
    ok(r.status_code == 401 and not SENT, f"{path}: forged token refused, nothing sent", r.status_code)
    r = client.post(path, json=body, headers=bearer(token("u-noaddr", meta_email="victim@example.com")))
    ok(r.status_code == 403 and not SENT,
       f"{path}: an address only in user_metadata is never used", (r.status_code, SENT))
    r = client.post(path, json=body, headers=bearer(token("u-unconf", email="new@example.com")))
    ok(r.status_code == 403 and not SENT, f"{path}: an unconfirmed address gets no mail", r.status_code)
    r = client.post(path, json=body, headers=bearer(token("u-real", email="claimed@example.com")))
    ok(r.status_code == 200 and SENT == ["me@example.com"],
       f"{path}: a verified caller is mailed at the account's confirmed address, not the token's claim",
       (r.status_code, SENT))
    body_json = r.json() if r.status_code == 200 else {}
    ok(set(body_json) <= PUBLIC_KEYS and body_json.get("sent") is True
       and "@" not in r.text and "result" not in body_json,
       f"{path}: the reply is the public schema only (no recipient, no transport result)", r.text[:120])

    SENT.clear()
    SMTP_RAISE.append(smtplib.SMTPRecipientsRefused({"me@example.com": (550, b"no such user me@example.com")}))
    r = client.post(path, json=body, headers=bearer(token("u-real")))
    SMTP_RAISE.clear()
    ok(r.status_code == 500 and "@" not in r.text, f"{path}: an SMTP failure is reported without addresses", r.text[:120])

print("\n   ...and closed when verification is not configured (R2)")
saved = (auth._JWT_SECRET, auth._SUPABASE_URL)
try:
    auth._JWT_SECRET, auth._SUPABASE_URL = "", ""
    unverifiable = bearer(token("u-real", secret="anything-" + secrets.token_hex(8), email="victim@example.com"))
    SENT.clear()
    codes = [client.post(p, json=b, headers=unverifiable).status_code
             for p, b in (("/alerts/test", None), ("/alerts/send", ALERT), ("/digest/send", None))]
    ok(all(c == 503 for c in codes) and not SENT, "no verification configured: every mail route refuses", codes)
    r = client.post("/me/email-pref", headers=unverifiable)
    ok(r.status_code == 503, "and the e-mail opt-in refuses too", r.status_code)
finally:
    auth._JWT_SECRET, auth._SUPABASE_URL = saved

print("\n   ...and the same rule for a stored opt-in (R2/R3)")
r = client.post("/me/email-pref", headers=forged)
ok(r.status_code == 401 and user_prefs.address_for("u-real") is None, "a forged token cannot opt in", r.status_code)
r = client.post("/me/email-pref", headers=bearer(token("u-noaddr", meta_email="victim@example.com")))
ok(r.status_code == 403 and user_prefs.address_for("u-noaddr") is None,
   "a user_metadata address is never stored", r.status_code)
r = client.post("/me/email-pref", headers=bearer(token("u-real", email="claimed@example.com")))
ok(r.status_code == 200 and user_prefs.address_for("u-real") == "me@example.com",
   "a verified opt-in stores the account's confirmed address", (r.status_code, user_prefs.address_for("u-real")))

print("\n2. E-MAIL HTML IS ESCAPED, SUBJECTS ARE ONE LINE")
html = alerts._build_multi_signal_alert_html(
    "<b>INFY</b>", '<a href="https://evil.example">click</a>', 1.0, 10.0, "negative", 90.0,
    "<script>alert(1)</script>", {"pe_ratio": "<i>9</i>"})
ok("<script>" not in html and "&lt;script&gt;" in html, "a headline cannot inject markup")
ok('<a href="https://evil.example">' not in html, "a company name cannot inject a link")
ok("<b>INFY</b>" not in html and "<i>9</i>" not in html, "ticker and valuation values are escaped")
html = alerts._build_sentiment_alert_html("X", "<img src=x>", "negative", 1.0, "<b>h</b>", 1.0)
ok("<img src=x>" not in html and "<b>h</b>" not in html, "the sentiment alert escapes too")
ok(alerts._one_line("a\r\nBcc: x@example.com") == "a Bcc: x@example.com",
   "a subject cannot add a mail header")

print("\n3. THE LIMITER TRUSTS ONLY WHAT IT CAN CHECK, WITHOUT STALLING")
rate_limit.check = REAL_CHECK


def reset():
    rate_limit._hits.clear()
    rate_limit._VERIFIED.clear()
    rate_limit._backoff_until = 0.0


def run(coro):
    return asyncio.run(coro)


reset()
real = Req(headers=bearer(token("alice")))
ok(rate_limit.client_key(real, run(rate_limit.verified_sub(real))) == "u:alice",
   "a verified token is a signed-in caller")
fake = Req(headers={"Authorization": "Bearer " + "x" * 120})
ok(run(rate_limit.verified_sub(fake)) is None, "a made-up long Bearer header is not")
bad = Req(headers=bearer(token("alice", secret="wrong-" + secrets.token_hex(8))))
ok(run(rate_limit.verified_sub(bad)) is None, "a token with the wrong signature is not")

# R5: a cached verification ends at the token's own expiry.
reset()
short = Req(headers=bearer(token("bob", exp_in=2)))
first = run(rate_limit.verified_sub(short))
until = rate_limit._VERIFIED.get(short.headers["authorization"].split(" ", 1)[1], (None, 0))[1]
time.sleep(2.6)
ok(first == "bob" and until <= time.time() and run(rate_limit.verified_sub(short)) is None,
   "a token verified just before expiry is not signed in after it expires", (first, round(until - time.time(), 1)))

# R1: verification never runs on the event loop's thread; concurrency is bounded;
# each network gets a verification budget; an unreachable key server backs off.
real_verify = auth.verify_status
seen = {"threads": set(), "active": 0, "peak": 0, "calls": 0}
lock = threading.Lock()


def slow_verify(t):
    with lock:
        seen["calls"] += 1
        seen["active"] += 1
        seen["peak"] = max(seen["peak"], seen["active"])
        seen["threads"].add(threading.get_ident())
    time.sleep(0.2)
    with lock:
        seen["active"] -= 1
    return ("invalid", None)


auth.verify_status = slow_verify
reset()
rate_limit.VERIFY_WAIT = 5.0


async def burst(n, net="198.51.100.20"):
    loop_thread = threading.get_ident()
    reqs = [Req(headers={**bearer("x" * 30 + secrets.token_hex(10)), "CF-Connecting-IP": net}) for _ in range(n)]
    await asyncio.gather(*(rate_limit.verified_sub(r) for r in reqs))
    return loop_thread


loop_thread = run(burst(12))
ok(loop_thread not in seen["threads"] and seen["threads"], "token verification runs off the event loop")
ok(seen["peak"] <= rate_limit.VERIFY_CONCURRENCY, "at most VERIFY_CONCURRENCY verifications at once", seen["peak"])
seen.update(calls=0)
run(burst(rate_limit.VERIFY_ADMIT[0] + 10, net="198.51.100.21"))
ok(seen["calls"] <= rate_limit.VERIFY_ADMIT[0],
   "one network cannot start more than its verification budget", seen["calls"])
rate_limit.VERIFY_WAIT = 0.5


def unreachable(t):
    seen["calls"] += 1
    return ("unavailable", None)


auth.verify_status = unreachable
reset()
seen.update(calls=0)
for _ in range(5):
    run(rate_limit.verified_sub(Req(headers=bearer("y" * 30 + secrets.token_hex(10)))))
ok(seen["calls"] == 1 and rate_limit._backoff_until > time.time(),
   "an unreachable key server is tried once, then backed off", seen["calls"])
auth.verify_status = real_verify
reset()

spoof = Req(headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.7"})
ok(rate_limit.network_key(spoof) == "net:203.0.113.7",
   "the network key is the right-most X-Forwarded-For hop, not the client's own first hop",
   rate_limit.network_key(spoof))
cf = Req(headers={"CF-Connecting-IP": "198.51.100.5", "X-Forwarded-For": "1.2.3.4, 172.70.0.1"})
ok(rate_limit.network_key(cf) == "net:198.51.100.5", "Cloudflare's CF-Connecting-IP wins when present")
ok(rate_limit.network_key(Req(host="192.0.2.1")) == "net:192.0.2.1", "the socket address is the last resort")

reset()
limit = rate_limit.IP_CEILING["heavy"][0]
blocked = None
for i in range(limit + 5):
    r = Req(path="/backtest/x", headers={
        "Authorization": "Bearer " + secrets.token_hex(40),
        "X-Forwarded-For": f"10.{i % 250}.0.1, 203.0.113.9",
        "X-Client-Id": "client-" + secrets.token_hex(6)})
    if run(rate_limit.check(r)):
        blocked = i
        break
ok(blocked is not None and blocked <= limit,
   "made-up tokens and rotated first hops from one network still hit the network ceiling", blocked)

print("\n4. PREFLIGHTS ARE NOT THROTTLED; A 429 KEEPS ITS CORS HEADER")
reset()
c2 = TestClient(M.app)
PRE = {"Origin": "https://www.quantindia.app", "Access-Control-Request-Method": "GET",
       "Access-Control-Request-Headers": "authorization"}
pre = [c2.options("/backtest/does-not-exist", headers=PRE) for _ in range(rate_limit.LIMITS["heavy"][0] + 3)]
ok(all(p.status_code == 200 and p.headers.get("access-control-allow-origin") for p in pre),
   "preflights always pass, with CORS headers", [p.status_code for p in pre])
me = {"Origin": "https://www.quantindia.app", **bearer(token("carol"))}
r = c2.get("/backtest/does-not-exist", headers=me)
ok(r.status_code != 429, "preflights used none of the signed-in caller's budget", r.status_code)
reset()
statuses = []
for _ in range(rate_limit.LIMITS["heavy"][0] + 1):
    resp = c2.get("/backtest/does-not-exist", headers={"Origin": "https://www.quantindia.app",
                                                        "X-Client-Id": "cors-check-1234"})
    statuses.append(resp.status_code)
ok(statuses[-1] == 429, "the sixth heavy call is refused", statuses)
ok(resp.headers.get("access-control-allow-origin") == "*", "the 429 carries Access-Control-Allow-Origin")
ok(resp.headers.get("retry-after") is not None, "and says when to retry")

print("\n5. /events/funnel IS REACHABLE, OWNER-ONLY")
rate_limit.check = lambda request: None
import analytics                # noqa: E402
analytics.funnel = lambda days=42: {"funnel": True, "days": days}
r = client.get("/events/funnel")
ok(r.status_code == 403 and "FUNNEL" not in r.text, "anonymous: refused (not the events for 'FUNNEL')", r.status_code)
os.environ["ADMIN_TOKEN"] = secrets.token_urlsafe(40)
r = client.get("/events/funnel", headers={"X-Admin-Token": os.environ["ADMIN_TOKEN"]}, params={"days": 7})
ok(r.status_code == 200 and r.json() == {"funnel": True, "days": 7}, "the owner reads the pilot scorecard", r.text[:80])
os.environ.pop("ADMIN_TOKEN", None)
paths = [getattr(rt, "path", "") for rt in M.app.routes]
ok(paths.index("/events/funnel") < paths.index("/events/{ticker}"), "registered before /events/{ticker}")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
