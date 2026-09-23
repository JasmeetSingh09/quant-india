"""
bse_access.py: one switch that stops this app collecting from BSE.

BSE's website terms prohibit "systematic or automated data collection
activities (including scraping, data mining, data extraction and data
harvesting)" without BSE's express written consent. No consent has been given.
Until 2026-09-23, stock_universe.refresh_bse_stocks contacted bseindia.com and
api.bseindia.com at every server start. It was failing anyway: production held
only the 42-stock built-in list.

Default: PAUSED, for the same reason nse_access defaults to paused. A
deployment that forgets to configure anything must honour the terms.

    BSE_COLLECTION=on      collect (only once BSE has given written consent)
    unset / off / paused   do not collect

Stored data is still read and served. Downloading by hand, in a browser, is not
automated collection and is unaffected.
"""

import os

_ON = ("1", "on", "yes", "true", "enable", "enabled", "collect")

REASON = ("Automated collection from BSE is paused: BSE's terms of use require "
          "its express written consent, which has not been given. Stored data "
          "is unaffected and still served.")


def collection_paused() -> bool:
    """True unless BSE_COLLECTION is explicitly on. Any other value is paused."""
    return (os.getenv("BSE_COLLECTION") or "").strip().lower() not in _ON


def paused_result(what: str) -> dict:
    """The response a collection entry point returns while paused."""
    return {"paused": True, "collected": 0, "what": what, "reason": REASON}
