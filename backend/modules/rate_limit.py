"""
rate_limit.py — one person cannot take the server down for everyone else.

Nothing here was needed while the only user was the person building it. With
pilot users and a demo audience arriving, a single tab left refreshing a Monte
Carlo run can exhaust a 2 GB Render instance and every other visitor sees a
dead app. That is a boring failure and a completely avoidable one.

Limits are per-endpoint-class rather than global, because the endpoints are not
equally expensive: a price lookup is cheap and a full-universe scan is not.
Cheap reads stay generous so ordinary browsing never trips a limit.

In-memory on purpose. A shared Redis would survive restarts and cover multiple
instances, but this runs as one process and an in-memory window costs nothing.
The honest limitation: a restart clears the counters, and the fix if this ever
runs on two instances is a shared store, not a bigger dictionary.
"""

import asyncio
import threading
import time
import weakref
from collections import defaultdict, deque

# (requests, seconds) per CALLER. Expensive work gets a tight budget; reads get
# room, because a single dashboard load fires several of them.
LIMITS = {
    "heavy":  (5,   300),    # scans, backtests, full simulations
    "medium": (30,  60),     # optimisation, monte carlo, advice
    "light":  (180, 60),     # prices, lookups, page data
}

# A second, per-NETWORK ceiling.
#
# Without it the per-caller limit is trivially defeated: an anonymous caller is
# identified partly by a header it sends itself, so rotating that header would
# buy an unlimited budget. With it, one machine cannot flood regardless.
#
# The numbers are set for the case that actually happens — a classroom or office
# where thirty people share one address. Thirty people browsing hard is a few
# hundred light requests a minute; a runaway script is thousands. The ceiling
# sits between those, so real users never meet it.
IP_CEILING = {
    "heavy":  (40,   300),
    "medium": (200,  60),
    "light":  (1200, 60),
}

# Longest prefix wins, so /portfolio/advise can be "medium" while /portfolio is
# not listed at all and falls through to "light".
_ROUTES = {
    "heavy": ("/universe/scan", "/scan/start", "/backtest", "/momentum/backtest",
              "/bhavcopy/fetch", "/overfitting", "/digest/send",
              # Anything that sends mail or starts a long rebuild (access-control
              # audit, 2026-10-17). /alpha/retrain overrides the "/alpha" medium
              # prefix because the longest prefix wins.
              "/digest", "/alerts", "/screener/refresh", "/alpha/retrain",
              # The real scan route. "/universe/scan" above never matched it,
              # because matching is by prefix, so the scan sat in "medium".
              "/alpha/universe/scan"),
    "medium": ("/portfolio/advise", "/portfolio/scenarios", "/portfolio/what-if",
               "/optimize", "/montecarlo", "/monte-carlo", "/simulate",
               "/alpha", "/options", "/pairs", "/regime", "/factors",
               "/stock/compare", "/stock/fundamentals-history", "/stock/technicals"),
}

_hits: dict = defaultdict(deque)
# Budgets are checked and charged as one step under this lock, so two requests
# can never both take the last slot.
_LOCK = threading.Lock()


def bucket_for(path: str) -> str:
    for name in ("heavy", "medium"):
        for prefix in _ROUTES[name]:
            if path.startswith(prefix):
                return name
    return "light"


def _ip(request) -> str:
    """
    The caller's address, from a source the caller cannot set (V4-16, 18 Nov
    2026). The first X-Forwarded-For hop is whatever the client wrote, so
    rotating it bought a fresh network budget per request.

    Render is served through Cloudflare (responses carry `server: cloudflare`
    and a CF-Ray id), and Cloudflare sets CF-Connecting-IP to the address it
    accepted the connection from, replacing any value the client sent. Without
    it (local runs, another host) the right-most X-Forwarded-For hop is the one
    the nearest proxy appended, and the socket address is the last resort.
    """
    cf = (request.headers.get("cf-connecting-ip") or "").strip()
    if cf:
        return cf
    fwd = request.headers.get("x-forwarded-for") or ""
    hops = [h.strip() for h in fwd.split(",") if h.strip()]
    if hops:
        return hops[-1]
    return request.client.host if getattr(request, "client", None) else "unknown"


# ---------------------------------------------------------------- verification
# A token is checked before its caller is treated as signed in (V4-16), and the
# checking must not become the outage (Codex review R1, 18 Nov 2026):
#   * it runs in a worker thread, never on the event loop, because a key-server
#     fetch can block for seconds;
#   * at most VERIFY_CONCURRENCY run at once; a request that cannot get a slot
#     quickly is simply treated as unverified (network ceiling applies);
#   * each network may start VERIFY_ADMIT new verifications a minute; beyond
#     that, tokens are not checked at all and the network ceiling applies;
#   * when the key server is unreachable, verification pauses for
#     VERIFY_BACKOFF seconds instead of retrying on every request;
#   * results are cached by the full token, positive ones only until the
#     token's own expiry (Codex review R5).
_VERIFIED: dict = {}                     # token -> (sub or None, valid_until)
_VERIFIED_TTL = 300
_VERIFIED_MAX = 5000
VERIFY_CONCURRENCY = 4
VERIFY_WAIT = 0.5                        # seconds to wait for a slot
VERIFY_ADMIT = (30, 60)                  # new verifications per network per window
VERIFY_BACKOFF = 60
_backoff_until = 0.0
_SEMAPHORES = weakref.WeakKeyDictionary()   # one per event loop


def _bearer_token(request) -> str | None:
    auth_header = request.headers.get("authorization") or ""
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    return token if len(token) >= 20 else None


def _cached(token: str, now: float):
    """(True, sub) when the cache has a live answer for this token."""
    with _LOCK:
        hit = _VERIFIED.get(token)
        if hit and hit[1] > now:
            return True, hit[0]
        if hit:
            _VERIFIED.pop(token, None)
    return False, None


def _remember(token: str, sub, payload, now: float) -> None:
    until = now + _VERIFIED_TTL
    exp = (payload or {}).get("exp")
    if sub and isinstance(exp, (int, float)):
        until = min(until, float(exp))          # never past the token's own expiry
    with _LOCK:
        if len(_VERIFIED) >= _VERIFIED_MAX:
            for k in [k for k, v in _VERIFIED.items() if v[1] <= now]:
                _VERIFIED.pop(k, None)
            if len(_VERIFIED) >= _VERIFIED_MAX:
                _VERIFIED.clear()
        _VERIFIED[token] = (sub, until)


def _admit_verification(request, now: float) -> bool:
    """Charge this network's verification budget; False when it is spent."""
    limit, window = VERIFY_ADMIT
    with _LOCK:
        q = _hits[f"verify|{network_key(request)}"]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def _semaphore():
    loop = asyncio.get_running_loop()
    sem = _SEMAPHORES.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(VERIFY_CONCURRENCY)
        _SEMAPHORES[loop] = sem
    return sem


def _verify_blocking(token: str):
    """Runs in a worker thread. ("ok"|"invalid"|"unavailable", payload)."""
    try:
        from auth import verify_status
        return verify_status(token)
    except Exception:
        return ("unavailable", None)


async def verified_sub(request) -> str | None:
    """The `sub` of a token that VERIFIES, else None. Never blocks the loop."""
    global _backoff_until
    token = _bearer_token(request)
    if not token:
        return None
    now = time.time()
    found, sub = _cached(token, now)
    if found:
        return sub
    if now < _backoff_until or not _admit_verification(request, now):
        return None
    sem = _semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=VERIFY_WAIT)
    except asyncio.TimeoutError:
        return None
    try:
        status, payload = await asyncio.get_running_loop().run_in_executor(
            None, _verify_blocking, token)
    finally:
        sem.release()
    if status == "unavailable":
        _backoff_until = time.time() + VERIFY_BACKOFF
        return None                              # not cached: it was not checked
    sub = payload.get("sub") if (status == "ok" and payload) else None
    _remember(token, sub, payload, time.time())
    return sub


def client_key(request, sub: str | None = None) -> str:
    """
    Identify the caller as narrowly as is honest.

    A signed-in user is limited as themselves. Anonymous callers used to fall
    back to bare IP, which meant thirty people on one school network shared a
    single budget and the last few to open the app got a 429 — the exact
    situation a demo creates.

    So anonymous callers are separated by a client id the browser generates and
    keeps, falling back to IP plus a user-agent fingerprint when there is none
    (an older cached bundle, or a direct API call). Neither is trustworthy on its
    own, which is why the per-network ceiling above exists: this key decides how
    finely honest users are separated, not how much total damage one machine can
    do.
    """
    # Only a token that verifies makes a caller "signed in" (V4-16, 18 Nov
    # 2026): `sub` comes from verified_sub(). Any long Bearer header used to
    # count, which let a made-up token skip the network ceiling below.
    if sub:
        return "u:" + sub

    cid = (request.headers.get("x-client-id") or "").strip()
    if 8 <= len(cid) <= 64 and all(c.isalnum() or c in "-_" for c in cid):
        return "c:" + cid

    ua = request.headers.get("user-agent") or ""
    return "ip:" + _ip(request) + ":" + str(abs(hash(ua)) % 100000)


def network_key(request) -> str:
    """The address itself, for the ceiling. From _ip, which reads only headers
    the caller cannot set."""
    return "net:" + _ip(request)


async def check(request) -> dict | None:
    """
    None when allowed. When over the limit, returns what the caller needs to
    know: which budget, and how long until it frees up. An error that does not
    say when to retry just produces an immediate retry.
    """
    path = request.url.path
    # Health and static reads must never be throttled — a limiter that can take
    # the health check down defeats its own purpose.
    if path in ("/", "/health", "/healthz", "/docs", "/openapi.json"):
        return None
    # CORS preflights carry no token or client id, so throttling them put every
    # signed-in user behind one address into the anonymous budget, and a 429 on
    # a preflight is a CORS failure in the browser. CORSMiddleware answers them
    # without running any route (Codex review R7, 18 Nov 2026).
    if getattr(request, "method", "GET") == "OPTIONS":
        return None

    bucket = bucket_for(path)

    # Both budgets must allow the request: the caller's own, and the network's.
    # Checked before either is charged, so a request rejected by one does not
    # consume the other.
    key = client_key(request, await verified_sub(request))
    now = time.time()
    gates = [(f"{key}|{bucket}", *LIMITS[bucket], "caller")]

    # The network ceiling exists because an anonymous caller's identity is a
    # header it sends itself, so rotating it would otherwise buy an unlimited
    # budget. A signed-in user is not self-asserted — the token is verified —
    # so they are accountable individually and keep their own budget regardless
    # of how busy the network around them is. Blocking a pilot user because
    # thirty strangers share their school's address is the exact failure this
    # ceiling was added to prevent, not an acceptable side effect of it.
    if not key.startswith("u:"):
        gates.append((f"{network_key(request)}|{bucket}", *IP_CEILING[bucket], "network"))

    with _LOCK:
        return _charge(gates, bucket, now)


def _charge(gates, bucket, now) -> dict | None:
    """Check every gate, then charge them all; called under _LOCK."""
    for key, limit, window, scope in gates:
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            retry = int(window - (now - q[0])) + 1
            mins = window // 60 or 1
            return {"bucket": bucket, "limit": limit, "window": window,
                    "scope": scope, "retry_after": retry,
                    "detail": (
                        f"Too many requests. This endpoint allows {limit} every "
                        f"{mins} minute(s) — it does real computation, and the cap "
                        f"keeps the app responsive for everyone. Try again in "
                        f"{retry}s."
                        if scope == "caller" else
                        f"This network has made {limit} requests in {mins} minute(s), "
                        f"which is above what a group of people browsing normally "
                        f"produces. Signing in raises your own limit. Try again in "
                        f"{retry}s.")}

    for key, _, _, _ in gates:
        _hits[key].append(now)

    if len(_hits) > 20_000:                 # bound memory on a long uptime
        for k in [k for k, v in _hits.items() if not v or now - v[-1] > 3600]:
            _hits.pop(k, None)
    return None
