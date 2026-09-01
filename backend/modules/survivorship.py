"""
survivorship.py — which companies actually existed on a given day.

I said this needed a paid point-in-time database. That was wrong, and the reason
it was wrong is worth stating: bhavcopy IS a point-in-time universe. Every daily
file lists exactly the symbols that traded that day, so a file from 2019 names
the companies that existed in 2019 — including the ones that have since been
delisted, merged, or gone under, which is precisely the set survivorship bias
removes.

What that gives, in order of how much history is stored:

  * With any history at all: detect that a backtested ticker did not exist at
    the start date, and say so instead of silently pricing it from whenever it
    first appears.
  * With deep history: reconstruct the tradeable universe as of a date, so a
    strategy can be tested against the companies that were actually available
    rather than the ones that survived to today.

The correction is therefore real but bounded by coverage, and this module
reports its own coverage rather than implying more than it has. A survivorship
correction that overstates its depth is worse than an honest disclosure.
"""

from datetime import datetime


def coverage() -> dict:
    """How much point-in-time history exists, stated plainly."""
    try:
        from db import get_conn
        conn = get_conn()
        row = conn.execute(
            "SELECT MIN(day), MAX(day), COUNT(DISTINCT day) FROM bhavcopy_eod"
        ).fetchone()
        conn.close()
    except Exception:
        return {"days": 0, "earliest": None, "latest": None, "usable": False}
    if not row or not row[0]:
        return {"days": 0, "earliest": None, "latest": None, "usable": False}
    return {
        "earliest": row[0], "latest": row[1], "days": row[2],
        "usable": bool(row[2] and row[2] >= 2),
        "note": (f"Point-in-time universe available from {row[0]} to {row[1]} "
                 f"({row[2]} trading days). Backtests starting before {row[0]} "
                 f"cannot be survivorship-corrected — there is no record of who "
                 f"was listed then."),
    }


def universe_as_of(day: str) -> set:
    """
    Every symbol that traded on the nearest stored day at or before `day`.

    This is the honest answer to "what could I have bought then", because it is
    literally the exchange's own list for that date rather than today's list
    projected backwards.
    """
    try:
        from db import get_conn
        conn = get_conn()
        row = conn.execute(
            "SELECT MAX(day) FROM bhavcopy_eod WHERE day <= ?", (str(day)[:10],)
        ).fetchone()
        if not row or not row[0]:
            conn.close()
            return set()
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM bhavcopy_eod WHERE day = ?", (row[0],)
        ).fetchall()
        conn.close()
        return {r[0] for r in rows if r and r[0]}
    except Exception:
        return set()


def check_portfolio(tickers, start_date: str) -> dict:
    """
    Did these stocks exist at the start of the backtest?

    A ticker absent from the universe on the start date is not evidence the
    company failed — it may have listed later, or coverage may not reach that
    far. Both cases matter to a reader and neither is a silent problem, so both
    are reported rather than resolved into a single verdict.
    """
    cov = coverage()
    if not cov.get("usable"):
        return {"checked": False, "coverage": cov,
                "note": "No point-in-time history stored yet, so existence at the "
                        "start date cannot be verified."}

    if str(start_date)[:10] < str(cov["earliest"]):
        return {"checked": False, "coverage": cov,
                "note": (f"Backtest starts {str(start_date)[:10]}, before stored "
                         f"history begins ({cov['earliest']}). Survivorship cannot "
                         f"be checked for this window — results still carry the "
                         f"bias, uncorrected and unmeasured.")}

    present = universe_as_of(start_date)
    missing = [t for t in tickers if t.strip().upper() not in present]
    return {
        "checked": True,
        "coverage": cov,
        "universe_size_then": len(present),
        "not_listed_at_start": missing,
        "note": ((f"{len(missing)} of {len(tickers)} holdings were not trading on "
                  f"{str(start_date)[:10]}: {', '.join(t.replace('.NS','') for t in missing[:5])}"
                  f"{'…' if len(missing) > 5 else ''}. Their history begins later, so "
                  f"the backtest silently starts them mid-period.")
                 if missing else
                 f"All {len(tickers)} holdings were trading on {str(start_date)[:10]}."),
    }


def measure_bias(start_date: str) -> dict:
    """
    How many companies have vanished since a date — the size of the bias.

    This is the number that makes survivorship concrete. Saying "results may be
    optimistic" persuades nobody; saying "213 of the 2,700 companies listed then
    are gone, and none of them are in your universe" is a fact a reader can hold.
    """
    cov = coverage()
    then = universe_as_of(start_date)
    now = universe_as_of(cov.get("latest") or datetime.now().strftime("%Y-%m-%d"))
    if not then or not now:
        return {"measured": False, "coverage": cov,
                "note": "Not enough stored history to measure the gap."}

    gone = sorted(then - now)
    new = sorted(now - then)
    pct = round(len(gone) / max(1, len(then)) * 100, 2)

    # A symbol that stopped appearing has not necessarily stopped trading: it
    # may have been renamed, or had its ISIN replaced under the same ticker.
    # Both look identical here and both inflate this count, so the resolved
    # figure is computed alongside and leads the note.
    resolved = None
    try:
        from security_identity import true_delistings
        resolved = true_delistings(as_of_first=str(start_date)[:10])
        if not resolved.get("available"):
            resolved = None
    except Exception:
        resolved = None

    out = {
        "measured": True,
        "as_of": str(start_date)[:10],
        "listed_then": len(then),
        "listed_now": len(now),
        "symbols_gone": len(gone),
        "symbols_gone_pct": pct,
        "newly_listed_since": len(new),
        "examples": [t.replace(".NS", "") for t in gone[:10]],
    }

    if resolved:
        true_n = resolved["true_delistings"]
        true_pct = resolved["true_delisting_pct"]
        out.update({
            "delisted_since": true_n,
            "delisted_pct": true_pct,
            "counted_by_symbol": len(gone),
            "counted_by_isin": resolved["counted_by_isin"],
            "identity_resolved": True,
            "note": (f"{true_n} of {resolved['identities_at_start']} securities "
                     f"trading on {resolved['window']['first']} "
                     f"({true_pct}%) have actually stopped trading. Counting "
                     f"tickers instead gives {len(gone)} and counting ISINs "
                     f"gives {resolved['counted_by_isin']}; the surplus in each "
                     f"is companies that changed name or changed ISIN and are "
                     f"trading today. Every backtest run on today's stock list "
                     f"still silently excludes the {true_n} that are genuinely "
                     f"gone, and companies disappear disproportionately after "
                     f"doing badly — which is why survivorship bias makes "
                     f"historical results look better than they were."),
        })
    else:
        # Say which number this is rather than letting a ticker count pass as
        # a delisting count.
        out.update({
            "delisted_since": None,
            "delisted_pct": None,
            "identity_resolved": False,
            "note": (f"{len(gone)} of {len(then)} symbols trading on "
                     f"{str(start_date)[:10]} ({pct}%) are no longer in the "
                     f"current universe. This is a count of TICKERS, not of "
                     f"delistings — a renamed company appears in it too, so "
                     f"treat it as an upper bound. Identity could not be "
                     f"resolved for this window."),
        })
    return out
