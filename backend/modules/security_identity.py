"""
security_identity.py — which ticker changes are the same company.

A ticker is a label. ISIN is the security. When Zomato became Eternal the
symbol ZOMATO stopped appearing in the exchange files and ETERNAL started, and
a backtest keyed on symbols read that as a company ceasing to exist — it booked
a -100% loss on a firm that was trading normally under a new name the same day.

ISIN survives the rename, so the two cases separate cleanly:

  rename     the ISIN keeps trading, under a different symbol
  delisting  the ISIN stops appearing anywhere

Both look identical if you only track tickers, and they mean opposite things to
a portfolio. This module derives the mapping from the exchange's own files
rather than from a hand-maintained table, which is the difference between
fixing today's five known cases and fixing the class.

Nothing here is hard-coded. If NSE renames something next month it appears in
the output without anyone editing this file.
"""

from datetime import datetime


def _conn():
    from db import get_conn
    return get_conn()


def transitions(min_gap_days: int = 0) -> dict:
    """
    Every ISIN whose ticker changed, with the dates on each side.

    Works by asking, per ISIN, which symbols it has traded under and when. An
    ISIN with more than one symbol has been renamed; the last day of the old
    symbol and the first day of the new one bracket the change.
    """
    try:
        conn = _conn()
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}"}

    try:
        rows = conn.execute(
            "SELECT isin, symbol, MIN(day) AS first_day, MAX(day) AS last_day, "
            "       COUNT(DISTINCT day) AS days "
            "FROM bhavcopy_eod WHERE isin IS NOT NULL "
            "GROUP BY isin, symbol").fetchall()
    except Exception as e:
        conn.close()
        return {"available": False,
                "reason": (f"Could not read identities ({type(e).__name__}). "
                           f"The ISIN column may not be populated yet.")}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    by_isin = {}
    for isin, sym, first, last, days in rows:
        by_isin.setdefault(isin, []).append(
            {"symbol": sym, "first_day": str(first)[:10],
             "last_day": str(last)[:10], "days": int(days or 0)})

    renames = []
    for isin, entries in by_isin.items():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda e: e["first_day"])
        for older, newer in zip(entries, entries[1:]):
            renames.append({
                "isin": isin,
                "old_symbol": older["symbol"],
                "new_symbol": newer["symbol"],
                "old_last_seen": older["last_day"],
                "new_first_seen": newer["first_day"],
                "old_days": older["days"],
                "new_days": newer["days"],
            })

    renames.sort(key=lambda r: r["new_first_seen"])
    return {
        "available": True,
        "isins_seen": len(by_isin),
        "renames": renames,
        "rename_count": len(renames),
        "how": ("Derived from the exchange's own files: an ISIN that has traded "
                "under more than one symbol was renamed. Nothing is hard-coded, "
                "so a rename next month appears here without an edit."),
    }


def true_delistings(as_of_last: str = None) -> dict:
    """
    ISINs that stopped trading entirely, as opposed to changing label.

    This is the number a survivorship correction actually needs. Counting
    symbols instead inflates it by every rename.
    """
    try:
        conn = _conn()
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}"}

    try:
        last = as_of_last or conn.execute(
            "SELECT MAX(day) FROM bhavcopy_eod").fetchone()[0]
        first = conn.execute("SELECT MIN(day) FROM bhavcopy_eod").fetchone()[0]
        if not last:
            conn.close()
            return {"available": False, "reason": "No exchange files stored."}

        # ISINs present at the start, absent at the end.
        start_isins = {r[0] for r in conn.execute(
            "SELECT DISTINCT isin FROM bhavcopy_eod WHERE day = ? "
            "AND isin IS NOT NULL", (first,)).fetchall()}
        end_isins = {r[0] for r in conn.execute(
            "SELECT DISTINCT isin FROM bhavcopy_eod WHERE day = ? "
            "AND isin IS NOT NULL", (last,)).fetchall()}

        gone = start_isins - end_isins
        # Name them by the last symbol each traded under.
        named = []
        for isin in list(gone)[:50]:
            row = conn.execute(
                "SELECT symbol, MAX(day) FROM bhavcopy_eod WHERE isin = ? "
                "GROUP BY symbol ORDER BY MAX(day) DESC", (isin,)).fetchone()
            if row:
                named.append({"isin": isin, "last_symbol": row[0],
                              "last_seen": str(row[1])[:10]})
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # Symbol-level count, for the comparison that shows why this matters.
    sym_gone = None
    try:
        conn = _conn()
        s_start = {r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM bhavcopy_eod WHERE day = ?",
            (first,)).fetchall()}
        s_end = {r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM bhavcopy_eod WHERE day = ?",
            (last,)).fetchall()}
        sym_gone = len(s_start - s_end)
        conn.close()
    except Exception:
        pass

    return {
        "available": True,
        "window": {"first": str(first)[:10], "last": str(last)[:10]},
        "isins_at_start": len(start_isins),
        "isins_at_end": len(end_isins),
        "true_delistings": len(gone),
        "true_delisting_pct": (round(len(gone) / len(start_isins) * 100, 2)
                               if start_isins else None),
        "symbols_disappeared": sym_gone,
        "inflation_from_renames": ((sym_gone - len(gone))
                                   if sym_gone is not None else None),
        "examples": named[:10],
        "why_it_matters": (
            f"Counting SYMBOLS that disappeared gives {sym_gone}. Counting "
            f"ISINs gives {len(gone)}. The difference is renames — companies "
            f"that never stopped trading. A backtest keyed on symbols books "
            f"every one of them as a total loss."
            if sym_gone is not None else ""),
    }


def symbol_to_isin(day: str = None) -> dict:
    """Current symbol -> ISIN on the nearest stored day at or before `day`."""
    try:
        conn = _conn()
    except Exception:
        return {}
    try:
        if day:
            row = conn.execute("SELECT MAX(day) FROM bhavcopy_eod WHERE day <= ?",
                               (str(day)[:10],)).fetchone()
        else:
            row = conn.execute("SELECT MAX(day) FROM bhavcopy_eod").fetchone()
        if not row or not row[0]:
            return {}
        rows = conn.execute(
            "SELECT symbol, isin FROM bhavcopy_eod WHERE day = ? "
            "AND isin IS NOT NULL", (row[0],)).fetchall()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def coverage() -> dict:
    """How much of the stored history carries an identity yet."""
    try:
        conn = _conn()
        total_days = conn.execute(
            "SELECT COUNT(DISTINCT day) FROM bhavcopy_eod").fetchone()[0]
        with_isin = conn.execute(
            "SELECT COUNT(*) FROM (SELECT day FROM bhavcopy_eod "
            "GROUP BY day HAVING COUNT(isin) > 0) t").fetchone()[0]
        rows_total = conn.execute("SELECT COUNT(*) FROM bhavcopy_eod").fetchone()[0]
        rows_isin = conn.execute(
            "SELECT COUNT(*) FROM bhavcopy_eod WHERE isin IS NOT NULL").fetchone()[0]
        conn.close()
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}"}
    return {
        "available": True,
        "days_total": total_days,
        "days_with_isin": with_isin,
        "days_pct": round(with_isin / total_days * 100, 1) if total_days else 0,
        "rows_total": rows_total,
        "rows_with_isin": rows_isin,
        "complete": with_isin >= total_days and total_days > 0,
        "note": ("Until this is complete the point-in-time backtest cannot tell "
                 "a rename from a delisting, and its survivorship figure is an "
                 "upper bound rather than a measurement."),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
