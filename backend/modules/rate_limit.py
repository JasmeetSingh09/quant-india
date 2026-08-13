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

# (requests, seconds). Expensive work gets a tight budget; reads get room.
LIMITS = {
    "heavy":  (5,   300),    # scans, backtests, full simulations
    "medium": (30,  60),     # optimisation, monte carlo, advice
    "light":  (120, 60),     # prices, lookups, page data
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


def client_key(request) -> str:
    """
    Identify the caller. A signed-in user is limited as themselves so that a
    shared office or college IP does not punish everyone behind it; anonymous
    callers fall back to IP.
    """
    auth = request.headers.get("authorization") or ""
    if auth.startswith("Bearer ") and len(auth) > 40:
        return "u:" + auth[-24:]
    fwd = request.headers.get("x-forwarded-for") or ""
    ip = fwd.split(",")[0].strip() if fwd else (
        request.client.host if request.client else "unknown")
    return "ip:" + ip


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
    limit, window = LIMITS[bucket]
    key = f"{client_key(request)}|{bucket}"
    now = time.time()

    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()

    if len(q) >= limit:
        retry = int(window - (now - q[0])) + 1
        return {"bucket": bucket, "limit": limit, "window": window,
                "retry_after": retry,
                "detail": (f"Too many requests. This endpoint allows {limit} every "
                           f"{window // 60 or 1} minute(s) — it does real computation, "
                           f"and the cap keeps the app responsive for everyone. "
                           f"Try again in {retry}s.")}

    q.append(now)
    if len(_hits) > 10_000:                 # bound memory on a long uptime
        for k in [k for k, v in _hits.items() if not v or now - v[-1] > 3600]:
            _hits.pop(k, None)
    return None
