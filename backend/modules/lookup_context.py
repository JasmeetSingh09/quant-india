"""
lookup_context.py — is this company-info lookup part of the nightly scan?

From 2026-09-11 Yahoo answered the scan's burst of company-info requests with
empty or truncated payloads, while the same lookups worked from the same server
outside the scan. On 2026-09-12 the value factor scored for 84 of 2,573 stocks.

Inside the scan such an answer is worth waiting for and asking again: the scan
has hours, and a score built without the data is worse than a slower pass.
Outside it a person is waiting for a page, so a lookup answers at once.

Thread-local, because the scan's workers and a user's request run in the same
process at the same time and must not change each other's behaviour.
"""

import threading
from contextlib import contextmanager

# Seconds to wait before each retry. Two retries at most, so a stock whose data
# really is incomplete (an ETF has no revenue) costs about seven seconds once.
RETRY_WAITS = (2.0, 5.0)

_LOCAL = threading.local()


@contextmanager
def scan_lookups():
    """Mark lookups on this thread as part of the nightly scan."""
    previous = getattr(_LOCAL, "scan", False)
    _LOCAL.scan = True
    try:
        yield
    finally:
        _LOCAL.scan = previous


def retry_waits() -> tuple:
    """The waits before each retry for a lookup on this thread; none outside the scan."""
    return tuple(RETRY_WAITS) if getattr(_LOCAL, "scan", False) else ()
