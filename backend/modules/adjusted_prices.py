"""
adjusted_prices.py — bhavcopy closes, corrected for corporate actions.

The archive stores what the exchange printed. A 1:1 bonus halves the quoted
price overnight and a 10-to-1 face-value split divides it by ten, so a return
computed across either from raw closes is measuring the corporate action rather
than the company.

Measured on a real event: VSTIND's 10:1 bonus printed 4456.45 on 2024-09-05 and
481.25 the next day, a fall of 89.20% in which nothing happened to the company.
The stock in fact rose 18.79% that day, and this module recovers exactly that —
removing the artificial move while preserving the real one, which is the harder
half.

Dividends are the smaller but more persistent term: across 20 twelve-month
windows, 15 differed by more than 10% between yfinance's dividend-adjusted and
unadjusted closes, and ITC's 2018-2026 return flipped from +36.6% to -1.4%.
That comparison isolates DIVIDENDS only — yfinance adjusts splits in both modes
— and an earlier version of this note wrongly described it as covering splits
as well. bhavcopy is unadjusted for both, so the archive's true distortion is
the two compounded.

This applies the correction at READ time. Nothing writes back to
`bhavcopy_eod`, so the archive remains a record of the printed price and any
error here is a bug to fix rather than damage already committed to nine million
rows.

The convention
--------------
For a date t the cumulative factor is the product of the price multipliers of
every action with an ex-date AFTER t:

    adjusted(t) = close(t) * PROD( multiplier(a) for a where a.ex_date > t )

so the most recent price is unadjusted and history is scaled to meet it — the
same convention as yfinance's auto_adjust. The choice of reference point does
not affect a RETURN: the factor cancels in adjusted(t2)/adjusted(t1) except for
the actions falling between t1 and t2, which is exactly what should survive.

What it refuses
---------------
A dividend needs the close on the last trading day before its ex-date to become
a multiplier. Where that close is missing the action is skipped and counted in
`unapplied` rather than approximated. A skipped action is a known, reported gap;
an approximated one is an invisible error in every earlier price.
"""

from bisect import bisect_left

import corporate_actions as CA

try:
    from db import get_conn, IS_POSTGRES
except Exception:                                   # pragma: no cover
    from .db import get_conn, IS_POSTGRES


def _closes(isin: str, start: str = None, end: str = None):
    """Raw closes for one security by ISIN, oldest first."""
    conn = get_conn()
    try:
        sql = ("SELECT day, close, symbol FROM bhavcopy_eod "
               "WHERE isin = ? AND close IS NOT NULL")
        args = [isin]
        if start:
            sql += " AND day >= ?"; args.append(start)
        if end:
            sql += " AND day <= ?"; args.append(end)
        sql += " ORDER BY day"
        rows = conn.execute(sql, tuple(args)).fetchall()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        rows = []
    finally:
        conn.close()
    return [(str(r[0])[:10], float(r[1]), r[2]) for r in rows if r[1] is not None]


def price_series(isin: str, start: str = None, end: str = None,
                 adjusted: bool = True) -> dict:
    """
    One security's close series, optionally corrected for corporate actions.

    Returns days, closes, the cumulative factor applied to each, and an account
    of every action considered — including the ones that could not be applied.
    A caller that wants the raw series passes adjusted=False and gets factors of
    exactly 1.0, so the two paths stay comparable.
    """
    rows = _closes(isin, start, end)
    out = {
        "isin": isin, "adjusted": bool(adjusted),
        "days": [r[0] for r in rows],
        "raw_close": [r[1] for r in rows],
        "symbol": rows[-1][2] if rows else None,
        "actions_applied": [], "unapplied": [], "n": len(rows),
    }
    if not rows:
        out["close"] = []
        out["factor"] = []
        out["note"] = "no prices stored for this ISIN in the requested range"
        return out
    if not adjusted:
        out["close"] = list(out["raw_close"])
        out["factor"] = [1.0] * len(rows)
        return out

    days = out["days"]
    closes = out["raw_close"]
    last_day = days[-1]

    # Actions strictly inside the window. One at or before the first price
    # cannot move anything we hold; one after the last price scales the whole
    # series equally and so cancels out of every return.
    acts = [a for a in CA.actions_for(isin, start=days[0], end=last_day)
            if a["ex_date"] > days[0]]

    # Multiplier per action, in ex-date order. A dividend needs the close on
    # the last trading day BEFORE the ex-date.
    resolved = []
    for a in acts:
        prev_close = None
        if a["kind"] == CA.DIVIDEND:
            i = bisect_left(days, a["ex_date"]) - 1
            if i >= 0:
                prev_close = closes[i]
        m = CA.price_multiplier(a, prev_close=prev_close)
        if m is None or not (0 < m <= 1.0000001):
            out["unapplied"].append({
                "ex_date": a["ex_date"], "kind": a["kind"],
                "subject": (a.get("subject") or "")[:90],
                "why": ("no close before the ex-date" if a["kind"] == CA.DIVIDEND
                        and prev_close is None else "multiplier not computable"),
            })
            continue
        resolved.append((a["ex_date"], float(m), a))
        out["actions_applied"].append({
            "ex_date": a["ex_date"], "kind": a["kind"], "multiplier": round(m, 8),
            "subject": (a.get("subject") or "")[:90],
        })
    resolved.sort(key=lambda x: x[0])

    # Walk backwards accumulating: factor(t) is the product over actions with
    # ex_date > t. Done in one pass rather than a product per day, because the
    # per-day version is O(n*m) and the archive is nine million rows.
    factor = [1.0] * len(days)
    running = 1.0
    j = len(resolved) - 1
    for i in range(len(days) - 1, -1, -1):
        while j >= 0 and resolved[j][0] > days[i]:
            running *= resolved[j][1]
            j -= 1
        factor[i] = running

    out["factor"] = factor
    out["close"] = [c * f for c, f in zip(closes, factor)]
    out["note"] = ("Adjusted at read time; bhavcopy_eod is unchanged. The most "
                   "recent close is unadjusted and history is scaled to meet it.")
    return out


def continuity_check(isin: str, ex_date: str, window: int = 3) -> dict:
    """
    Does the adjusted series go continuous across a known corporate action?

    The trust gate for the whole adjustment layer. A 1:1 bonus should show a
    roughly -50% one-day move in the raw series and a small ordinary move in
    the adjusted one. If the adjusted jump is still large, the multiplier is
    wrong and nothing downstream should be run.

    Returns both jumps and the ratio between them, so a caller can judge rather
    than being handed a pass/fail with the threshold buried inside.
    """
    ser = price_series(isin, adjusted=True)
    days, raw, adj = ser["days"], ser["raw_close"], ser["close"]
    if not days:
        return {"available": False, "reason": "no prices for this ISIN"}
    i = bisect_left(days, ex_date)
    if i <= 0 or i >= len(days):
        return {"available": False, "reason": f"ex-date {ex_date} outside the "
                                              f"stored range {days[0]}..{days[-1]}"}

    def jump(series, k):
        return (series[k] / series[k - 1] - 1.0) if series[k - 1] else None

    raw_jump, adj_jump = jump(raw, i), jump(adj, i)
    near = [{"day": days[k], "raw": round(raw[k], 2), "adj": round(adj[k], 2),
             "factor": round(ser["factor"][k], 6)}
            for k in range(max(0, i - window), min(len(days), i + window + 1))]
    applied = [a for a in ser["actions_applied"] if a["ex_date"] == days[i]
               or a["ex_date"] == ex_date]
    return {
        "available": True, "isin": isin, "symbol": ser.get("symbol"),
        "ex_date": ex_date, "matched_trading_day": days[i],
        "raw_jump_pct": None if raw_jump is None else round(raw_jump * 100, 3),
        "adjusted_jump_pct": None if adj_jump is None else round(adj_jump * 100, 3),
        "improvement": (None if not raw_jump or adj_jump is None
                        else round(abs(raw_jump) / max(abs(adj_jump), 1e-9), 1)),
        "actions_on_that_date": applied,
        "window": near,
    }
