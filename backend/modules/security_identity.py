"""
security_identity.py — which ticker changes are the same company.

A ticker is a label. ISIN is the security. When Zomato became Eternal the
symbol ZOMATO stopped appearing in the exchange files and ETERNAL started, and
a backtest keyed on symbols read that as a company ceasing to exist — it booked
a -100% loss on a firm that was trading normally under a new name the same day.

The obvious fix is to key on ISIN instead. That fixes renames and introduces
the mirror-image bug, which the live data then produced: between 2024-01-01 and
2026-08-28, 237 ISINs stopped appearing while only 183 symbols did. More
identifiers died than names. An ISIN is never reissued to a different company,
so those extra ones are not delistings — they are securities whose ISIN was
replaced under a stable ticker, which is what a face-value change, an
amalgamation or a scheme of arrangement does. Keying on ISIN books every one of
them as a total loss, exactly as keying on symbols did to Zomato.

Neither identifier is the company. So this resolves identity from both:

    ISINs are linked when they trade under the same symbol in sequence.
    A resolved identity is a chain of such links, and it is delisted only
    when the whole chain stops trading.

Sequence is what makes the link safe. Two ISINs under one symbol back to back
are one company continuing through a corporate action; the same symbol reused
years later is a recycled ticker, and merging those would erase a real
delisting. So a link requires the ranges to be adjacent, and anything that
overlaps substantially is left unmerged and reported as ambiguous — the
direction that keeps a delisting visible rather than the one that hides it.

Nothing here is hard-coded. If NSE renames or restructures something next month
it appears in the output without anyone editing this file.
"""

from datetime import datetime, date


# How far apart two ISINs under one symbol may sit and still be one company.
# A replacement ISIN from a corporate action starts within days of the old one
# ending. A ticker recycled for an unrelated company is separated by months.
LINK_MAX_GAP_DAYS = 45
# A little overlap is ragged data at the boundary, not two live securities.
# Beyond this the two were genuinely trading at once and are not merged.
LINK_MAX_OVERLAP_DAYS = 5


def _conn():
    from db import get_conn
    return get_conn()


def _d(v) -> date:
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def _pairs(conn):
    """Every (ISIN, symbol) the exchange has recorded, with its date range."""
    return conn.execute(
        "SELECT isin, symbol, MIN(day) AS first_day, MAX(day) AS last_day, "
        "       COUNT(DISTINCT day) AS days "
        "FROM bhavcopy_eod WHERE isin IS NOT NULL "
        "GROUP BY isin, symbol").fetchall()


def _resolve_pairs(rows):
    """
    Union-find over ISINs, linked by shared symbols that run in sequence.

    Returns (canonical, components, links, ambiguous) where canonical maps
    every ISIN to the identifier of its chain.
    """
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            # Lowest ISIN wins, so the canonical id is stable across runs
            # rather than depending on row order.
            lo, hi = (ra, rb) if ra <= rb else (rb, ra)
            parent[hi] = lo

    by_symbol = {}
    for isin, sym, first, last, days in rows:
        find(isin)
        by_symbol.setdefault(sym, []).append(
            {"isin": isin, "first": _d(first), "last": _d(last),
             "days": int(days or 0)})

    links, ambiguous = [], []
    for sym, entries in by_symbol.items():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda e: e["first"])
        for prev, nxt in zip(entries, entries[1:]):
            gap = (nxt["first"] - prev["last"]).days
            if -LINK_MAX_OVERLAP_DAYS <= gap <= LINK_MAX_GAP_DAYS:
                union(prev["isin"], nxt["isin"])
                links.append({"symbol": sym, "old_isin": prev["isin"],
                              "new_isin": nxt["isin"],
                              "old_last_seen": prev["last"].isoformat(),
                              "new_first_seen": nxt["first"].isoformat(),
                              "gap_days": gap})
            else:
                ambiguous.append({
                    "symbol": sym, "isin_a": prev["isin"], "isin_b": nxt["isin"],
                    "gap_days": gap,
                    "reason": ("the same ticker reused after a long gap — merging "
                               "these would hide a real delisting"
                               if gap > LINK_MAX_GAP_DAYS else
                               "both ISINs traded under this ticker at the same "
                               "time, so they are not one security continuing")})

    components = {}
    for isin in list(parent):
        components.setdefault(find(isin), set()).add(isin)
    canonical = {isin: find(isin) for isin in parent}
    return canonical, components, links, ambiguous


def resolve() -> dict:
    """
    The symbol/ISIN graph collapsed into continuing securities.

    This is what the backtest keys on. Neither a symbol nor an ISIN survives
    every corporate event; a chain of them does.
    """
    try:
        conn = _conn()
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}"}
    try:
        rows = _pairs(conn)
    except Exception as e:
        return {"available": False,
                "reason": (f"Could not read identities ({type(e).__name__}). "
                           f"The ISIN column may not be populated yet.")}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    canonical, components, links, ambiguous = _resolve_pairs(rows)
    multi = {k: v for k, v in components.items() if len(v) > 1}
    return {
        "available": True,
        "isins": len(canonical),
        "resolved_identities": len(components),
        "identities_spanning_multiple_isins": len(multi),
        "isin_changes": len(links),
        "ambiguous_not_merged": len(ambiguous),
        "examples": links[:10],
        "ambiguous_examples": ambiguous[:10],
        "canonical": canonical,
        "rule": (f"Two ISINs are the same security when they trade under one "
                 f"ticker in sequence — the new one starting within "
                 f"{LINK_MAX_GAP_DAYS} days of the old one ending. Ranges that "
                 f"overlap by more than {LINK_MAX_OVERLAP_DAYS} days, or sit "
                 f"further apart than that, are left separate and counted as "
                 f"ambiguous, because merging them would erase a delisting."),
    }


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
        rows = _pairs(conn)
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

    # The mirror case, reported alongside so neither is mistaken for the whole
    # problem: one ISIN under many symbols is a rename, one symbol under many
    # ISINs is a restructuring, and both break naive tracking.
    try:
        _, _, links, _ = _resolve_pairs(rows)
    except Exception:
        links = []

    return {
        "available": True,
        "isins_seen": len(by_isin),
        "renames": renames,
        "rename_count": len(renames),
        "isin_changes": links[:50],
        "isin_change_count": len(links),
        "how": ("Derived from the exchange's own files: an ISIN that has traded "
                "under more than one symbol was renamed, and a symbol whose "
                "ISIN was replaced in sequence was restructured. Nothing is "
                "hard-coded, so either kind of change next month appears here "
                "without an edit."),
    }


def true_delistings(as_of_last: str = None, as_of_first: str = None) -> dict:
    """
    Securities that stopped trading entirely, as opposed to changing label.

    Counted on resolved identities. Counting symbols inflates the number by
    every rename; counting ISINs inflates it by every restructuring. All three
    counts are reported so the difference is visible rather than asserted.
    """
    try:
        conn = _conn()
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}"}

    try:
        # Snap a requested date to a day the exchange actually traded, rather
        # than returning nothing because the caller named a Sunday.
        last = as_of_last and conn.execute(
            "SELECT MAX(day) FROM bhavcopy_eod WHERE day <= ?",
            (str(as_of_last)[:10],)).fetchone()[0]
        last = last or conn.execute(
            "SELECT MAX(day) FROM bhavcopy_eod").fetchone()[0]
        first = as_of_first and conn.execute(
            "SELECT MIN(day) FROM bhavcopy_eod WHERE day >= ?",
            (str(as_of_first)[:10],)).fetchone()[0]
        first = first or conn.execute(
            "SELECT MIN(day) FROM bhavcopy_eod").fetchone()[0]
        if not last or not first:
            conn.close()
            return {"available": False, "reason": "No exchange files stored."}

        start_isins = {r[0] for r in conn.execute(
            "SELECT DISTINCT isin FROM bhavcopy_eod WHERE day = ? "
            "AND isin IS NOT NULL", (first,)).fetchall()}
        end_isins = {r[0] for r in conn.execute(
            "SELECT DISTINCT isin FROM bhavcopy_eod WHERE day = ? "
            "AND isin IS NOT NULL", (last,)).fetchall()}

        s_start = {r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM bhavcopy_eod WHERE day = ?",
            (first,)).fetchall()}
        s_end = {r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM bhavcopy_eod WHERE day = ?",
            (last,)).fetchall()}
        sym_gone = len(s_start - s_end)

        pairs = _pairs(conn)
        canonical, components, links, ambiguous = _resolve_pairs(pairs)

        start_ids = {canonical.get(i, i) for i in start_isins}
        end_ids = {canonical.get(i, i) for i in end_isins}
        gone_ids = start_ids - end_ids
        gone_isins = start_isins - end_isins

        named = []
        for cid in list(gone_ids)[:50]:
            member = sorted(components.get(cid, {cid}))
            marks = ",".join("?" for _ in member)
            row = conn.execute(
                "SELECT symbol, MAX(day) FROM bhavcopy_eod WHERE isin IN "
                "(" + marks + ") GROUP BY symbol ORDER BY MAX(day) DESC",
                tuple(member)).fetchone()
            if row:
                named.append({"identity": cid, "isins": member,
                              "last_symbol": row[0],
                              "last_seen": str(row[1])[:10]})
    finally:
        try:
            conn.close()
        except Exception:
            pass

    rename_inflation = sym_gone - len(gone_ids)
    restructure_inflation = len(gone_isins) - len(gone_ids)

    return {
        "available": True,
        "window": {"first": str(first)[:10], "last": str(last)[:10]},
        "identities_at_start": len(start_ids),
        "identities_at_end": len(end_ids),
        "true_delistings": len(gone_ids),
        "true_delisting_pct": (round(len(gone_ids) / len(start_ids) * 100, 2)
                               if start_ids else None),
        "counted_by_symbol": sym_gone,
        "counted_by_isin": len(gone_isins),
        "inflation_from_renames": rename_inflation,
        "inflation_from_isin_changes": restructure_inflation,
        "isins_at_start": len(start_isins),
        "isins_at_end": len(end_isins),
        "ambiguous_not_merged": len(ambiguous),
        "examples": named[:10],
        "why_it_matters": (
            "Three ways of counting the same window give three answers. "
            "Symbols that disappeared: " + str(sym_gone) + ". ISINs that "
            "disappeared: " + str(len(gone_isins)) + ". Securities that "
            "actually stopped trading: " + str(len(gone_ids)) + ". Keying a "
            "backtest on symbols books " + str(rename_inflation) + " renamed "
            "companies as total losses; keying it on ISINs books " +
            str(restructure_inflation) + " restructured ones the same way. "
            "Only the third number is a delisting rate."),
        "caveat": (
            str(len(ambiguous)) + " symbol reuse(s) were left unmerged rather "
            "than assumed to be one company. That keeps the delisting count "
            "higher, which is the safe direction — the alternative silently "
            "removes losses from the record." if ambiguous else None),
    }


def symbol_to_isin(day: str = None) -> dict:
    """Current symbol -> ISIN on the nearest stored day at or before day."""
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
