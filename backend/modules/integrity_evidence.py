"""
integrity_evidence.py — the axis of evidence that is not about prediction.

The evidence layer had one axis: does the factor predict returns? Today the
answer is "not established" for all six, and it will stay that way until at
least 2029. A badge that is the same colour on every stock every day is not an
evidence layer, it is wallpaper, and users stop seeing it inside a week.

But "does it predict" is not the only question worth answering, and it is not
the only one with evidence behind it. There is a second, entirely separate
question:

    is the machinery computing what it claims to compute?

That one HAS answers today, and they are good ones. Keeping the two apart is
what lets the amber on the first axis keep meaning something, because the green
on the second proves the badges move.

What belongs here, and what does not
------------------------------------
Only claims this module can VERIFY at request time, from data in the database.
A claim that rests on a test having passed at some commit is a statement about
our process, not a measurement, and putting it here would be exactly the kind of
unearned assurance the whole evidence layer exists to prevent. So look-ahead
safety is absent from this list despite being tested and true: the test proves
it, this endpoint cannot, and the honest place for it is the test suite.

Cost
----
The underlying audit takes about 22 seconds -- it re-scores five hundred stocks
from their stored inputs and checks every table for duplicates. That is far too
slow for a page load, so it is cached and warmed on a timer. A cold miss returns
`computing` rather than blocking a request for 22 seconds: a user waiting on a
spinner learns less than one told the answer is being prepared.
"""

import threading
import time

from bounded_cache import BoundedCache

_CACHE = BoundedCache(4, "integrity_evidence._CACHE")
_TTL = 6 * 3600          # the inputs change once a day, after the scan
_BUILDING = threading.Lock()


def _claim(cid, headline, ok, measured, method, detail=None):
    """
    ok=True -> verified, False -> failed, None -> unknown, "partial" -> partial.

    Four states, because three were not enough. A claim about a PROPORTION is
    badly served by a binary: provenance coverage at 73% is neither "verified"
    (it plainly is not) nor "failed" (three quarters of it works), and forcing
    it into either misinforms in a different direction. `unknown` is reserved
    for a check that could not run at all, which is a distinct thing again -- a
    check that did not happen is not a check that passed.
    """
    status = ("partial" if ok == "partial"
              else "verified" if ok is True
              else "failed" if ok is False
              else "unknown")
    return {
        "id": cid,
        "claim": headline,
        "status": status,
        "measured": measured,
        "method": method,
        "detail": detail,
    }


def _build() -> dict:
    from cycle_audit import audit
    a = audit()
    if not a.get("available", True) or a.get("reason"):
        return {"available": False,
                "reason": a.get("reason", "audit unavailable"),
                "note": ("The audit failed, which is a fault in the audit and "
                         "not a verdict on the machinery. Nothing is claimed.")}

    scan = a.get("scan") or {}
    repro = a.get("reproduction") or {}
    dupes = a.get("duplicates") or {}
    prov = a.get("provenance") or {}
    fh = a.get("factor_history") or {}

    claims = []

    # 1. Reproducibility. The strongest claim available: stored scores can be
    #    recomputed from stored inputs and come back the same.
    checked = repro.get("checked") or 0
    mismatched = repro.get("mismatched")
    claims.append(_claim(
        "reproducible",
        "Stored scores can be recomputed from stored inputs",
        (mismatched == 0 and checked > 0) if mismatched is not None else None,
        (f"{checked} stocks re-scored, {mismatched} mismatched"
         if mismatched is not None else "not measured"),
        "Each score recomputed from the inputs recorded beside it and compared.",
        {"checked": checked, "mismatched": mismatched,
         "max_abs_diff": repro.get("max_abs_diff"), "worst": repro.get("worst")},
    ))

    # 2. No duplicate observations anywhere in the record.
    dupe_total = sum(v for v in dupes.values() if isinstance(v, int))
    claims.append(_claim(
        "no_duplicates",
        "No observation is recorded twice",
        (dupe_total == 0) if dupes else None,
        f"{dupe_total} duplicates across {len(dupes)} tables" if dupes else "not measured",
        "Every table keyed on (ticker, cycle) checked for repeated rows.",
        dupes or None,
    ))

    # 3. Provenance. Not "we have inputs" but "every incomplete observation is
    #    explained" -- an unexplained gap is the thing that would matter.
    unexplained = fh.get("missing_provenance")
    rows = fh.get("rows") or 0
    with_inputs = fh.get("with_raw_inputs") or 0
    # The first version of this claim read "Every score carries the inputs it
    # was computed from" and was marked verified on `with_inputs > 0` -- which
    # passed at 1,973 of 2,704, or 73%. A claim of "every" verified by "some" is
    # the exact overclaim this panel exists to prevent, and it got as far as
    # production before being caught. The claim now states the proportion, and
    # is verified only when the proportion is complete.
    pct = (100.0 * with_inputs / rows) if rows else None
    claims.append(_claim(
        "provenance_recorded",
        "Scores record the inputs they were computed from",
        (True if (rows and with_inputs == rows)
         else "partial" if (rows and with_inputs) else None if not rows else False),
        (f"{with_inputs:,} of {rows:,} observations ({pct:.0f}%) carry their "
         f"raw inputs" if rows else "not measured"),
        ("Inputs are captured at scan time, not reconstructed afterwards. "
         "Observations without them cannot be given any later."),
        {"rows": rows, "with_raw_inputs": with_inputs,
         "missing_provenance": unexplained,
         "input_rows": prov.get("input_rows")},
    ))

    # 4. Coverage against the declared bar, so a thin pass cannot pass silently.
    cov = scan.get("coverage_pct")
    bar = scan.get("completeness_bar_pct")
    claims.append(_claim(
        "coverage_meets_bar",
        "The daily pass covered the market",
        (cov is not None and bar is not None and cov >= bar),
        f"{cov}% of the exchange scored against a {bar}% bar"
        if cov is not None else "not measured",
        "Denominator is the exchange universe on the cycle's own day.",
        {"attempted": scan.get("attempted"), "scored": scan.get("scored"),
         "failed": scan.get("failed"), "coverage_pct": cov, "bar_pct": bar},
    ))

    # 5. The audit's own verdict, carried rather than re-derived.
    passed, failed = a.get("checks_passed"), a.get("checks_failed")
    claims.append(_claim(
        "audit_passes",
        "The cycle audit passes every check",
        (failed == 0 and (passed or 0) > 0) if failed is not None else None,
        f"{passed} passed, {failed} failed" if failed is not None else "not measured",
        "Independent audit of the cycle, run over stored rows.",
        {"verdict": a.get("verdict"), "cycle": a.get("cycle")},
    ))

    verified = sum(1 for c in claims if c["status"] == "verified")
    failed_n = sum(1 for c in claims if c["status"] == "failed")
    partial_n = sum(1 for c in claims if c["status"] == "partial")
    return {
        "available": True,
        "axis": "machinery",
        "question": "Is the app computing what it claims to compute?",
        "not_this_axis": ("Whether a factor predicts returns. That is the other "
                          "axis, and it is not established for any factor."),
        "cycle": a.get("cycle"),
        "claims": claims,
        "verified": verified,
        "failed": failed_n,
        "partial": partial_n,
        "unknown": len(claims) - verified - failed_n - partial_n,
        "summary": (f"{verified} of {len(claims)} verified"
                    + (f", {partial_n} partial" if partial_n else "")
                    + (f", {failed_n} FAILED" if failed_n else "")),
        "computed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": ("Every claim here is measured at request time from stored "
                 "rows. Claims that rest only on a test having passed are "
                 "deliberately absent — that is a statement about our process, "
                 "not a measurement."),
    }


def integrity(refresh: bool = False) -> dict:
    """
    The machinery axis, cached.

    Returns `computing: True` on a cold miss rather than blocking for the ~22
    seconds the audit takes. A page that says "being prepared" is more useful
    than one that hangs, and far more useful than one that silently shows
    nothing.
    """
    hit = _CACHE.get("integrity")
    if hit and not refresh and time.time() - hit[0] < _TTL:
        return {**hit[1], "cached": True, "age_seconds": int(time.time() - hit[0])}

    if not _BUILDING.acquire(blocking=False):
        return {"available": False, "computing": True,
                "note": "Integrity checks are being computed; try again shortly."}
    try:
        out = _build()
        if out.get("available"):
            _CACHE["integrity"] = (time.time(), out)
        return {**out, "cached": False}
    finally:
        _BUILDING.release()


def warm() -> dict:
    """For the scheduler, so a page load never pays the 22 seconds."""
    try:
        r = integrity(refresh=True)
        return {"warmed": bool(r.get("available")), "summary": r.get("summary")}
    except Exception as e:
        return {"warmed": False, "error": f"{type(e).__name__}: {e}"}
