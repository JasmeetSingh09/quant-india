"""
nse_access.py — one switch that stops this app collecting from NSE.

On 2026-09-08 a written request went to NSE Data and Analytics asking for
permission, as a Non-Commercial User, to collect and retain published NSE data
for a student research project. That email states:

    "We have paused further collection pending your response."

This module is what makes that sentence true. It is not a feature flag and it is
not a rate limiter. It exists so that a commitment made in writing to the
exchange is enforced by the code rather than by anyone remembering.

Default: PAUSED
----------------
Collection is off unless NSE_COLLECTION is explicitly set to on. The default is
deliberately the restrictive one: a deployment that forgets to configure
anything must end up honouring the commitment, not breaking it. The failure mode
of a wrong default here is a stale archive, which is recoverable. The failure
mode of the other default is telling an exchange you have stopped while your
scheduler carries on.

    NSE_COLLECTION=on      collect (set this only once permission is granted,
                           or if the commitment is withdrawn)
    unset / off / paused   do not collect

What it stops, and what it does not
-----------------------------------
It stops NEW retrieval from nseindia.com: the nightly bhavcopy fetch, the recent
gap repair, the backwards resume walk, corporate action months and the equity
list download.

It does not delete, hide or stop serving anything already stored. The archive
remains readable and every endpoint that reads it keeps working, because the
request was about collection and retention going forward, and quietly degrading
the product would not make the email any more true.
"""

import os

_ON = ("1", "on", "yes", "true", "enable", "enabled", "collect")
_OFF = ("0", "off", "no", "false", "pause", "paused", "stop", "disabled")

# Why the request was made, carried here so anyone reading a "paused" response
# in a log or an API payload can find out why without hunting for context.
REASON = ("Collection is paused pending NSE Data and Analytics' response to a "
          "written Non-Commercial User permission request sent 2026-09-08. The "
          "request states that collection has been paused; this switch enforces "
          "that. Stored data is unaffected and still served.")


def collection_paused() -> bool:
    """True when this app must not retrieve anything new from NSE."""
    v = (os.getenv("NSE_COLLECTION") or "").strip().lower()
    if v in _ON:
        return False
    if v in _OFF or v == "":
        return True
    # An unrecognised value is treated as paused. A typo in an environment
    # variable must not silently resume collection.
    return True


def status() -> dict:
    """Readable state, for a health endpoint."""
    raw = (os.getenv("NSE_COLLECTION") or "").strip()
    paused = collection_paused()
    return {
        "nse_collection_paused": paused,
        "env_NSE_COLLECTION": raw or "(unset)",
        "recognised": (raw.lower() in _ON + _OFF) if raw else True,
        "reason": REASON if paused else None,
        "stored_data_still_served": True,
        "to_resume": "set NSE_COLLECTION=on (only once permission is granted)",
    }


def paused_result(what: str) -> dict:
    """The response a collection entry point returns while paused."""
    return {"paused": True, "collected": 0, "what": what, "reason": REASON}
