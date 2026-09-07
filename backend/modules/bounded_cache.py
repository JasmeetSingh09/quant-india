"""
bounded_cache.py — a dict that cannot grow without limit.

Every cache in this app was a module-level dict with a TTL and no size bound.
That is correct for a process serving a few dozen tickers and wrong for one that
walks the whole exchange: the universe scan touches ~2,600 stocks in a pass, and
each leaves entries behind in half a dozen dicts that nothing ever removes. The
TTL does not help — it decides whether a HIT is fresh, and a stale entry nobody
asks for again is simply never looked at, never expired, and never freed.

Measured, this is worth roughly 200 MB across a full scan on a 2 GB instance:
real, but far short of the multi-gigabyte leak first suspected. The dominant
cost is elsewhere (FinBERT resident at ~810 MB), so this buys headroom rather
than fixing a crash. It is worth doing because it is cheap and because a bound
that grows with the size of the exchange is not a bound.

Why LRU rather than flush-at-threshold
--------------------------------------
Four caches here already had a size guard of the form

    if len(_CACHE) > 2000:
        _CACHE.clear()

which does bound memory, but throws away two thousand warm entries to make room
for one. During a scan that is a periodic cliff where every cached value is lost
at once. An LRU holds the same ceiling and discards only the entry that has gone
longest unused, so the working set survives and only the tail is dropped.

TTL and LRU do not interact
---------------------------
Callers store (timestamp, value) and check freshness themselves. Eviction is
independent of that: an entry may be dropped while still fresh, which costs one
recomputation, or kept past its TTL, which the caller already rejects. So this
class deliberately knows nothing about time — mixing the two policies in one
place is how a cache starts returning values it should not.

Sizing
------
The bound must exceed the LIVE working set or the cache thrashes and becomes a
slower way of not caching. The scan runs 6 workers, and one stock can pull its
own info plus three sector peers, so ~24 entries are genuinely in flight. The
defaults here are one to two orders of magnitude above that. `evictions` is
exposed so a bound that turns out to be too small is visible as a number rather
than as unexplained slowness.
"""

import threading
from collections import OrderedDict

# Entries, not bytes. Byte accounting would need a deep sizer on every write,
# which costs more than the memory it saves. Per-entry cost is measured once and
# folded into the chosen limit instead.
DEFAULT_MAXSIZE = 512


class BoundedCache(OrderedDict):
    """
    An LRU dict with a hard entry ceiling.

    Subclasses OrderedDict (and so dict) on purpose: every call site already
    treats these as plain dicts — `.get(k)`, `c[k] = v`, `len(c)`, `.clear()` —
    and an isinstance check or a stray `.items()` somewhere must keep working.
    Swapping the declaration is the whole change at each site.

    Thread-safe. The scan writes from six worker threads, and eviction is a
    read-then-delete that can otherwise race two threads into a KeyError on the
    same oldest key.
    """

    def __init__(self, maxsize: int = DEFAULT_MAXSIZE, name: str = ""):
        super().__init__()
        self._maxsize = max(1, int(maxsize))
        self._name = name or "cache"
        self._lock = threading.RLock()
        self.evictions = 0
        self.hits = 0
        self.misses = 0

    # -- writes ------------------------------------------------------------
    def __setitem__(self, key, value):
        with self._lock:
            if key in self:
                OrderedDict.__delitem__(self, key)
            OrderedDict.__setitem__(self, key, value)
            while len(self) > self._maxsize:
                # popitem(last=False) is the oldest by insertion/use order.
                OrderedDict.popitem(self, last=False)
                self.evictions += 1

    # -- reads: touching an entry makes it recently used --------------------
    def get(self, key, default=None):
        with self._lock:
            if OrderedDict.__contains__(self, key):
                OrderedDict.move_to_end(self, key)
                self.hits += 1
                return OrderedDict.__getitem__(self, key)
            self.misses += 1
            return default

    def __getitem__(self, key):
        with self._lock:
            value = OrderedDict.__getitem__(self, key)
            OrderedDict.move_to_end(self, key)
            self.hits += 1
            return value

    def clear(self):
        with self._lock:
            OrderedDict.clear(self)

    # -- observability -----------------------------------------------------
    def stats(self) -> dict:
        """
        What the bound is actually doing.

        `evictions` climbing while `hit_rate` falls means the ceiling is below
        the working set and the cache is costing more than it saves. That is the
        number to read before raising a limit — not a guess about how much
        memory an entry takes.
        """
        with self._lock:
            total = self.hits + self.misses
            return {
                "name": self._name,
                "entries": len(self),
                "maxsize": self._maxsize,
                "evictions": self.evictions,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate_pct": round(100.0 * self.hits / total, 1) if total else None,
                "full": len(self) >= self._maxsize,
            }


def registry() -> list:
    """
    Every bounded cache in the process, for a health endpoint.

    Discovered by walking loaded modules rather than by a registration call, so
    a cache added later cannot be forgotten here — the failure mode of an
    explicit register() is that the one cache nobody registered is the one that
    grows.
    """
    import sys

    out, seen = [], set()
    for mod in list(sys.modules.values()):
        if not mod or not getattr(mod, "__name__", "").split(".")[-1]:
            continue
        try:
            items = list(vars(mod).items())
        except Exception:
            continue
        for attr, val in items:
            if isinstance(val, BoundedCache) and id(val) not in seen:
                seen.add(id(val))
                s = val.stats()
                s["module"] = mod.__name__
                s["attr"] = attr
                out.append(s)
    return sorted(out, key=lambda r: (-r["entries"], r["module"]))
