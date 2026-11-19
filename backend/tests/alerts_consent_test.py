"""
alerts_consent_test.py — who the automatic alerts job may mail, and when a
product event may be stored (decisions of 19 Nov 2026: V4-04 / R4 option (a),
V4-02 option (a), and the "not investment advice" line in every e-mail).

  1. send_email has no fallback inbox: without a recipient nothing is sent,
     even with GMAIL_RECEIVER set in the environment;
  2. a threshold must be a finite number above 0 (helpers, the watchlist
     module and the API);
  3. the alerts job mails only users who opted in to alerts, each about their
     own watchlist, each at their own stored address; the anonymous "public"
     list and unverified ids never cause mail; a 0% threshold never fires;
     a per-user cooldown holds;
  4. the alert opt-in is verified + confirmed only, never returns the address,
     and opting out deletes it; account deletion covers it;
  5. /events/track stores an event only for a verified account whose sign-up
     confirmed 18+ (user_metadata flag); anonymous, unverified and unflagged
     callers store nothing;
  6. every alert e-mail carries "Educational research tool, not investment
     advice; not SEBI-registered."

Offline: temporary SQLite, no network, no model, no mail leaves the process.

    cd backend && python tests/alerts_consent_test.py
"""
import os
import secrets
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
sys.path.insert(0, os.path.join(HERE, ".."))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="alerts_consent_")
os.environ["QUANT_DATA_DIR"] = TMP
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)
os.environ.pop("ADMIN_USER_IDS", None)
# Set on purpose: the old code fell back to this inbox. Nothing may reach it.
os.environ["GMAIL_RECEIVER"] = "owner@example.com"
TEST_SECRET = "alerts-consent-test-secret-" + secrets.token_hex(16)
os.environ["SUPABASE_JWT_SECRET"] = TEST_SECRET


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
import user_prefs               # noqa: E402
import watchlist                # noqa: E402
import account_deletion         # noqa: E402
import db                       # noqa: E402
from fastapi.testclient import TestClient   # noqa: E402

PASS, FAIL = [], []


def ok(cond, label, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))


def token(sub, secret=TEST_SECRET, meta=None, exp_in=600):
    claims = {"sub": sub, "aud": "authenticated", "exp": int(time.time()) + exp_in}
    if meta is not None:
        claims["user_metadata"] = meta
    return jwt.encode(claims, secret, algorithm="HS256")


def bearer(t):
    return {"Authorization": "Bearer " + t}


USERS = {
    "u-alice": {"id": "u-alice", "email": "alice@example.com", "email_confirmed_at": "2026-11-01T00:00:00Z"},
    "u-bob":   {"id": "u-bob", "email": "bob@example.com", "email_confirmed_at": "2026-11-01T00:00:00Z"},
    "u-unconf": {"id": "u-unconf", "email": "new@example.com", "email_confirmed_at": None},
}
auth._auth_user = lambda t: USERS.get((jwt.decode(t, options={"verify_signature": False}) or {}).get("sub"))

SENT = []   # (recipient, message)


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
        SENT.append((recipient, msg))


alerts.smtplib.SMTP_SSL = FakeSMTP
alerts.GMAIL_SENDER, alerts.GMAIL_PASSWORD = "sender@example.com", "app-password"
import data_fetcher             # noqa: E402
data_fetcher.get_financial_metrics = lambda t: {}
rate_limit.check = lambda request: None
client = TestClient(M.app)
assert str(db._SQLITE_PATH).startswith(TMP), db._SQLITE_PATH

NOT_ADVICE = "Educational research tool, not investment advice; not SEBI-registered."

print("\n1. NO FALLBACK INBOX")
SENT.clear()
r = alerts.send_email("s", "<p>b</p>")
ok("error" in r and not SENT, "send_email without a recipient sends nothing", r)
r = alerts.send_email("s", "<p>b</p>", to_email="   ")
ok("error" in r and not SENT, "a blank recipient sends nothing", r)
r = alerts.send_test_alert()
ok("error" in r and not SENT, "the test alert without a recipient sends nothing", r)
r = alerts.send_multi_signal_alert("INFY.NS", "Infosys", 6.0, 10.0, "neutral", 0.0, "h")
ok("error" in r and not SENT, "a multi-signal alert without a recipient sends nothing", r)
ok(not hasattr(alerts, "GMAIL_RECEIVER"), "GMAIL_RECEIVER is no longer read at all")
ok(alerts.check_and_send_watchlist_alerts(
    [{"ticker": "INFY.NS", "alert_triggered": True, "price_alert_pct": 5}]) == [] and not SENT,
   "check_and_send_watchlist_alerts without an address sends nothing")

print("\n2. THRESHOLDS MUST BE ABOVE 0")
for bad in (0, 0.0, -1, float("nan"), float("inf"), None, "x"):
    ok(not alerts.threshold_ok(bad) and not watchlist._threshold_ok(bad), f"threshold {bad!r} refused")
for good in (0.5, 5, "2.5"):
    ok(alerts.threshold_ok(good) and watchlist._threshold_ok(good), f"threshold {good!r} accepted")
ok("error" in watchlist.add_to_watchlist("INFY.NS", price_alert_pct=0, user_id="u-alice"),
   "watchlist.add_to_watchlist refuses 0% before any lookup")
ok("error" in watchlist.update_alert_settings("INFY.NS", price_alert_pct=-2, user_id="u-alice"),
   "watchlist.update_alert_settings refuses a negative threshold")
for bad in (0, -5):
    r = client.post("/watchlist/add", json={"ticker": "INFY.NS", "price_alert_pct": bad},
                    headers=bearer(token("u-alice")))
    ok(r.status_code == 422, f"POST /watchlist/add with price_alert_pct={bad} is refused (422)", r.status_code)
r = client.post("/watchlist/add", json={"ticker": "INFY.NS", "price_alert_pct": 0})
ok(r.status_code == 422, "the anonymous public list cannot store a 0% threshold either", r.status_code)

print("\n3. THE ALERTS JOB: OPTED-IN, VERIFIED RECIPIENTS ONLY, OWN WATCHLIST")
WATCHLISTS = {
    "public": [{"ticker": "PUB.NS", "alert_triggered": True, "price_alert_pct": 0,
                "change_from_add_pct": 9.0, "current_price": 1.0}],
    "u-alice": [
        {"ticker": "INFY.NS", "company_name": "Infosys", "alert_triggered": True,
         "price_alert_pct": 5.0, "change_from_add_pct": 6.2, "current_price": 1500.0},
        {"ticker": "ZERO.NS", "alert_triggered": True, "price_alert_pct": 0,
         "change_from_add_pct": 0.1, "current_price": 10.0},
        {"ticker": "CALM.NS", "alert_triggered": False, "price_alert_pct": 5.0,
         "change_from_add_pct": 1.0, "current_price": 10.0},
    ],
    "u-bob": [{"ticker": "TCS.NS", "alert_triggered": True, "price_alert_pct": 3.0,
               "change_from_add_pct": -4.0, "current_price": 3000.0}],
    "unverified:u-alice": [{"ticker": "X.NS", "alert_triggered": True, "price_alert_pct": 1,
                            "change_from_add_pct": 5.0, "current_price": 1.0}],
}
LOADED = []


def fake_watchlist(uid):
    LOADED.append(uid)
    return WATCHLISTS.get(uid, [])


alerts._load_watchlist = fake_watchlist

# Opt-in storage refuses the shared bucket and unverified ids outright.
ok("error" in user_prefs.alert_opt_in("public", "owner@example.com"), "the public bucket cannot opt in")
ok("error" in user_prefs.alert_opt_in("unverified:u-x", "x@example.com"), "an unverified id cannot opt in")
ok(user_prefs.alert_recipients() == [], "nobody receives alerts before opting in")

SENT.clear(); LOADED.clear()
res = alerts.run_watchlist_alert_check()
ok(not SENT and not LOADED, "with no opt-ins the job reads no watchlist and sends nothing", (SENT, LOADED))

# Alice opts in (through the store); Bob does not.
user_prefs.alert_opt_in("u-alice", "alice@example.com")
# A row planted directly for the public bucket (as an old bug might have) is ignored.
conn = db.get_conn()
conn.execute("INSERT INTO alert_emails (user_id, email, opted_in_at) VALUES ('public', 'owner@example.com', 'x')")
conn.execute("INSERT INTO alert_emails (user_id, email, opted_in_at) VALUES ('unverified:u-alice', 'owner@example.com', 'x')")
conn.commit(); conn.close()
ok(user_prefs.alert_recipients() == [("u-alice", "alice@example.com")],
   "recipients: only real, opted-in ids", user_prefs.alert_recipients())

SENT.clear(); LOADED.clear()
res = alerts.run_watchlist_alert_check()
to = [s[0] for s in SENT]
ok(to == ["alice@example.com"], "one alert, to Alice's own address only", to)
ok(LOADED == ["u-alice"], "only Alice's own watchlist was read (not public, not Bob)", LOADED)
ok("owner@example.com" not in to and "bob@example.com" not in to,
   "neither the owner inbox nor a non-opted-in user is mailed")
ok([r.get("ticker") for r in res if r.get("status") == "sent"] == ["INFY.NS"],
   "the 0% ZERO.NS row and the untriggered row never fire", res)
ok(all("@" not in str(r) for r in res), "the job's result carries no address", res)
ok(SENT and NOT_ADVICE in SENT[0][1], "the alert e-mail says it is not investment advice")

SENT.clear()
res = alerts.run_watchlist_alert_check()
ok(not SENT and any(r.get("status") == "skipped (cooldown)" for r in res),
   "a second run within the cooldown sends nothing", res)

# Bob opting in starts his own alerts; Alice's cooldown is hers alone.
user_prefs.alert_opt_in("u-bob", "bob@example.com")
SENT.clear()
alerts.run_watchlist_alert_check()
ok([s[0] for s in SENT] == ["bob@example.com"], "Bob's cooldown is separate from Alice's", [s[0] for s in SENT])

r = user_prefs.alert_opt_out("u-bob")
ok(r.get("deleted") is True and ("u-bob", "bob@example.com") not in user_prefs.alert_recipients(),
   "opting out deletes the address")

print("\n4. THE ALERT OPT-IN API")
r = client.post("/me/alert-pref")
ok(r.status_code == 401, "anonymous: refused", r.status_code)
forged = bearer(token("u-bob", secret="not-the-secret-" + secrets.token_hex(8)))
r = client.post("/me/alert-pref", headers=forged)
ok(r.status_code == 401, "forged token: refused", r.status_code)
r = client.post("/me/alert-pref", headers=bearer(token("u-unconf")))
ok(r.status_code == 403, "unconfirmed address: refused", r.status_code)
r = client.post("/me/alert-pref", headers=bearer(token("u-bob")))
ok(r.status_code == 200 and ("u-bob", "bob@example.com") in user_prefs.alert_recipients(),
   "verified + confirmed: stored with the account's own address", r.status_code)
r = client.get("/me/alert-pref", headers=bearer(token("u-bob")))
ok(r.status_code == 200 and r.json().get("alerts") is True and "@" not in r.text,
   "GET says yes without returning the address", r.text[:120])
r = client.get("/me/alert-pref")
ok(r.status_code == 200 and r.json().get("alerts") is False, "anonymous GET: no alerts", r.text[:80])
r = client.delete("/me/alert-pref", headers=bearer(token("u-bob")))
ok(r.status_code == 200 and ("u-bob", "bob@example.com") not in user_prefs.alert_recipients(),
   "DELETE removes the address", r.status_code)
ok(any(t == "alert_emails" for t, _ in account_deletion.USER_TABLES),
   "account deletion erases the alert opt-in")

print("\n5. PRODUCT EVENTS ONLY AFTER THE 18+ CONFIRMATION")


def n_events():
    conn = db.get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM product_events").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


body = {"event": "simulation_started", "props": {"n_stocks": 3}}
base = n_events()
r = client.post("/events/track", json=body)
ok(r.status_code == 200 and n_events() == base, "anonymous: answered, nothing stored", (r.status_code, n_events()))
r = client.post("/events/track", json=body, headers=bearer(token("u-old")))
ok(r.status_code == 200 and n_events() == base,
   "an existing account without the flag (no backfill): nothing stored")
r = client.post("/events/track", json=body, headers=bearer(token("u-str", meta={"age_18_confirmed": "true"})))
ok(n_events() == base, "a string 'true' is not the flag")
r = client.post("/events/track", json=body,
                headers=bearer(token("u-adult", secret="forged-" + secrets.token_hex(8),
                                     meta={"age_18_confirmed": True})))
ok(n_events() == base, "a forged token with the flag: nothing stored")
r = client.post("/events/track", json=body, headers=bearer(token("u-adult", meta={"age_18_confirmed": True})))
ok(r.status_code == 200 and n_events() == base + 1, "a verified account that confirmed 18+: stored",
   (r.status_code, n_events()))
ok(auth.adult_confirmed_claims({"user_metadata": {"age_18_confirmed": True}})
   and not auth.adult_confirmed_claims({"user_metadata": {}})
   and not auth.adult_confirmed_claims(None), "adult_confirmed_claims reads only a true flag")
saved = (auth._JWT_SECRET, auth._SUPABASE_URL)
try:
    auth._JWT_SECRET, auth._SUPABASE_URL = "", ""
    before = n_events()
    client.post("/events/track", json=body, headers=bearer(token("u-adult", meta={"age_18_confirmed": True})))
    ok(n_events() == before, "no verification configured: nothing stored (fails closed)")
finally:
    auth._JWT_SECRET, auth._SUPABASE_URL = saved

print("\n6. EVERY ALERT E-MAIL CARRIES THE NOT-ADVICE LINE")
ok(alerts.NOT_ADVICE == NOT_ADVICE, "the wording is exactly the decided line")
for name, html in (
    ("price", alerts._build_price_alert_html("A", "B", 1.0, 2.0, 5.0, 5.0, {})),
    ("sentiment", alerts._build_sentiment_alert_html("A", "B", "negative", 1.0, "h", 1.0)),
    ("multi-signal", alerts._build_multi_signal_alert_html("A", "B", 1.0, 2.0, "neutral", 0.0, "h", {})),
):
    ok(NOT_ADVICE in html, f"{name} alert HTML")
SENT.clear()
alerts.send_test_alert(to_email="alice@example.com")
ok(SENT and NOT_ADVICE in SENT[0][1] and "sender@example.com" not in SENT[0][1].split("\n\n", 1)[-1],
   "the test alert carries it (and no longer prints the sender settings)")
import inspect                  # noqa: E402
import weekly_digest            # noqa: E402
ok("_not_advice()" in inspect.getsource(weekly_digest.build_digest), "the weekly summary carries it")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
