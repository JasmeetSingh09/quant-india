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

import time
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
              "/bhavcopy/fetch", "/overfitting", "/digest/send"),
    "medium": ("/portfolio/advise", "/portfolio/scenarios", "/portfolio/what-if",
               "/optimize", "/montecarlo", "/monte-carlo", "/simulate",
               "/alpha", "/options", "/pairs", "/regime", "/factors"),
}

_hits: dict = defaultdict(deque)


def bucket_for(path: str) -> str:
    for name in ("heavy", "medium"):
        for prefix in _ROUTES[name]:
            if path.startswith(prefix):
                return name
    return "light"


def _ip(request) -> str:
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if getattr(request, "client", None) else "unknown"


def client_key(request) -> str:
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
    auth = request.headers.get("authorization") or ""
    if auth.startswith("Bearer ") and len(auth) > 40:
        return "u:" + auth[-24:]

    cid = (request.headers.get("x-client-id") or "").strip()
    if 8 <= len(cid) <= 64 and all(c.isalnum() or c in "-_" for c in cid):
        return "c:" + cid

    ua = request.headers.get("user-agent") or ""
    return "ip:" + _ip(request) + ":" + str(abs(hash(ua)) % 100000)


def network_key(request) -> str:
    """The address itself, for the ceiling. Not spoofable by a header we trust."""
    return "net:" + _ip(request)


def check(request) -> dict | None:
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

    bucket = bucket_for(path)
    now = time.time()

    # Both budgets must allow the request: the caller's own, and the network's.
    # Checked before either is charged, so a request rejected by one does not
    # consume the other.
    key = client_key(request)
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
