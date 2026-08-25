"""
backtest_integrity.py — which of two very different things is this backtest?

A backtest over ten years and a backtest over eighteen months can both be
correct arithmetic and mean opposite amounts. The difference is not length. It
is whether the universe being traded is the one that existed at the time, or
today's survivors projected backwards.

So every backtest gets classified, automatically, from its own dates:

  POINT-IN-TIME VALIDATED
      The whole period sits inside the window where daily exchange files exist,
      so the companies traded are the ones that were actually listed. Survivors
      and failures both present. Conclusions about performance are defensible.

  RESEARCH ONLY
      The period reaches back before that window. The universe is today's
      listed set projected backwards, so every company in it is one that
      survived to now. Useful for studying how the machinery behaves. Not
      evidence of an investment edge.

The counter-intuitive part, and the reason this module exists: survivorship
COMPOUNDS with length. A ten-year run on today's survivors is more
contaminated than a two-year one, because a company that failed in 2018 is
absent from all 120 months rather than a handful. Longer is not stronger here;
it is weaker, and a reader who assumes otherwise will trust exactly the wrong
number.

Nothing here changes a result. It labels one.
"""

from datetime import datetime


def _pit_window():
    """The dates for which point-in-time exchange files actually exist."""
    try:
        from db import get_conn
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT MIN(day), MAX(day), COUNT(DISTINCT day) FROM bhavcopy_eod"
            ).fetchone()
        finally:
            conn.close()
        if not row or not row[0]:
            return None, None, 0
        return str(row[0])[:10], str(row[1])[:10], int(row[2] or 0)
    except Exception:
        return None, None, 0


def _parse(d):
    try:
        return datetime.strptime(str(d)[:10], "%Y-%m-%d")
    except Exception:
        return None


def classify(start: str, end: str = None, pit_universe_size: int = None) -> dict:
    """
    Label a backtest by the integrity of the universe it can actually use.

    `pit_universe_size` is the point-in-time liquidity screen the momentum
    backtest accepts. It removes look-ahead in universe SELECTION, which is a
    different and lesser thing than having the real historical universe — a
    screen applied to a list of survivors still only ever picks survivors. So
    it improves the grade but cannot earn the top one.
    """
    end = end or datetime.now().strftime("%Y-%m-%d")
    ds, de = _parse(start), _parse(end)
    pit_first, pit_last, pit_days = _pit_window()

    if ds is None:
        return {"mode": "UNKNOWN", "reason": f"Unreadable start date: {start!r}"}

    years = round((de - ds).days / 365.25, 2) if de else None

    if not pit_first:
        return {
            "mode": "RESEARCH ONLY",
            "label": "Research backtest — no point-in-time universe available",
            "period": f"{start} to {end}",
            "years": years,
            "pit_coverage": None,
            "survivorship": "uncorrected",
            "why": ("No daily exchange files are stored, so the universe can "
                    "only be today's listed set projected backwards."),
            "safe_to_claim": SAFE_RESEARCH,
        }

    pf, pl = _parse(pit_first), _parse(pit_last)
    fully_inside = pf is not None and ds >= pf
    covered_years = round((de - pf).days / 365.25, 2) if (de and pf) else None

    if fully_inside:
        return {
            "mode": "POINT-IN-TIME VALIDATED",
            "label": "Point-in-time validated backtest",
            "period": f"{start} to {end}",
            "years": years,
            "pit_coverage": {"first": pit_first, "last": pit_last,
                             "trading_days": pit_days},
            "survivorship": "corrected within this window",
            "why": ("Every date in this period has a daily exchange file, so "
                    "the companies traded are the ones that were listed at the "
                    "time — including those that have since delisted."),
            "safe_to_claim": SAFE_VALIDATED,
        }

    # Reaches back before the files exist.
    shortfall = round((pf - ds).days / 365.25, 2) if pf else None
    return {
        "mode": "RESEARCH ONLY",
        "label": "Research backtest — point-in-time integrity not guaranteed",
        "period": f"{start} to {end}",
        "years": years,
        "pit_coverage": {"first": pit_first, "last": pit_last,
                         "trading_days": pit_days},
        "uncovered_years": shortfall,
        "survivorship": "uncorrected before " + pit_first,
        "why": (f"This period starts {shortfall} years before the earliest "
                f"stored exchange file ({pit_first}). For everything before "
                f"that date the universe is today's survivors projected "
                f"backwards."),
        "longer_is_worse": (
            f"Survivorship compounds with length. Over {years} years a company "
            f"that failed early is missing from the whole run, so this result "
            f"is MORE contaminated than a shorter one — not better evidence "
            f"for being longer."),
        "how_to_get_a_clean_run": (
            f"Start on or after {pit_first}, which currently gives about "
            f"{covered_years} years of point-in-time history."
            if covered_years else ""),
        "safe_to_claim": SAFE_RESEARCH,
    }


SAFE_VALIDATED = (
    "Performance figures from this window may be discussed as historical "
    "results, with the usual caveats: one market, one period, and costs "
    "modelled rather than paid.")

SAFE_RESEARCH = (
    "Do NOT present these returns as evidence of an investment edge. They are "
    "valid for studying how the model behaves — factor relationships, optimiser "
    "behaviour, drawdown shape, sensitivity to assumptions — because those do "
    "not depend on the universe being complete. The RETURN LEVEL does.")


def annotate(result: dict, start: str, end: str = None,
             pit_universe_size: int = None) -> dict:
    """Attach the classification to a backtest result, in place."""
    try:
        result["integrity"] = classify(start, end, pit_universe_size)
    except Exception as e:
        result["integrity"] = {"mode": "UNKNOWN",
                               "reason": f"{type(e).__name__}"}
    return result
