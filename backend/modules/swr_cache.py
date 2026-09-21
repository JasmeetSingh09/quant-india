"""
swr_cache.py — serve the last answer instantly, refresh it behind the scenes.

Some dashboard endpoints recompute the same global answer on every page load:
the leaderboard marks every active paper portfolio to market (about 10.7 s on
production, 2026-09-18) and the tiered top picks take about 3 s. Every visitor
paid that wait, although the answers change only when prices or the nightly
scan do.

Stale-while-revalidate: the first call computes and stores. Later calls get the
stored answer at once; if it is older than `ttl` seconds, one background thread
recomputes it while the caller still gets the previous answer. A failed refresh
keeps the last good answer rather than replacing it with an error.

Only for answers that are the same for every visitor. Nothing user-specific may
go through here.
"""

import threading
import time

_STORE = {}              # key -> (computed_at, value)
_REFRESHING = set()
_LOCK = threading.Lock()


def _refresh(key, fn):
    try:
        value = fn()
        with _LOCK:
            _STORE[key] = (time.time(), value)
    except Exception:
        pass                                   # keep serving the last good answer
    finally:
        with _LOCK:
            _REFRESHING.discard(key)


def cached(key, ttl, fn):
    """The stored answer for `key`, computing it with `fn` on first use."""
    with _LOCK:
        hit = _STORE.get(key)
        stale = hit is not None and time.time() - hit[0] >= ttl
        start = stale and key not in _REFRESHING
        if start:
            _REFRESHING.add(key)
    if hit is None:
        value = fn()                           # first call: the caller waits once
        with _LOCK:
            _STORE[key] = (time.time(), value)
        return value
    if start:
        threading.Thread(target=_refresh, args=(key, fn), daemon=True,
                         name=f"swr-{key}").start()
    return hit[1]


def age(key):
    """Seconds since `key` was computed, or None."""
    with _LOCK:
        hit = _STORE.get(key)
    return None if hit is None else time.time() - hit[0]


def clear():
    with _LOCK:
        _STORE.clear()
        _REFRESHING.clear()
