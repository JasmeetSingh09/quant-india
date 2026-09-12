"""
data_integrity.py — what is actually in the data, counted rather than assumed.

Built to run after every production scan, not once.

The governing rule
------------------
Every check reports what it EXAMINED alongside what it found, and the two come
from the same query. This is not decoration. Over the course of this hardening
phase the test machinery itself has been wrong three times: a tolerance derived
at one volatility and applied at another, an exception handler that turned HTTP
429 into "no data" and quietly shrank the sample, and a stub that disabled the
guard layer it was meant to be testing. Each time the harness reported a clean
result on a sample it had silently narrowed.

So a check here may not say "prices verified". It says "6,598,053 rows examined,
0 with a close outside its own high-low range". If the row count is wrong the
reader can see that it is wrong, which is not true of a bare verdict.

No single score
---------------
There is deliberately no "Data Health: 98/100". The components measure different
things in different units -- a duplicate row and an undated article are not
commensurable -- and averaging them would invent a number that means nothing and
hides which half is broken. The report is a set of counts and a PASS/PARTIAL/
FAIL per domain.

What PARTIAL means
------------------
Not "mostly fine". It means the check could not examine everything it set out
to, and the shortfall is stated. A domain that could not be measured is never
reported as passing.
"""

import datetime as _dt
import re
import time

try:
    from db import get_conn, IS_POSTGRES
except Exception:                                   # pragma: no cover
    from .db import get_conn, IS_POSTGRES


def _future_boundary() -> str:
    """
    The latest day that is not "the future".

    Deliberately one day beyond today. Render runs UTC and NSE trading days are
    IST (UTC+5:30), so after 18:30 UTC the current Mumbai trading day is already
    tomorrow by the server's clock. A strict `day > today` test would report the
    most recent legitimate bhavcopy as a future observation every evening. That
    exact confusion has already produced one false alarm in this project -- a
    "missing Monday" that was never missing -- so the slack is explicit and
    stated in the finding rather than hidden here.
    """
    return (_dt.datetime.utcnow().date() + _dt.timedelta(days=1)).isoformat()


def _ph():
    """The parameter marker for whichever database is behind get_conn()."""
    return "%s" if IS_POSTGRES else "?"


def _one(conn, sql, args=(), default=None):
    """A single row, with the failure surfaced rather than flattened to zero."""
    try:
        r = conn.execute(sql, args).fetchone()
        return r if r is not None else default
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"_err": f"{type(e).__name__}: {e}"}


def _finding(check, examined, bad, detail=None, offenders=None):
    """
    One measurement. `examined` is mandatory and comes from the same pass that
    produced `bad`, so the two cannot drift apart.
    """
    if isinstance(examined, dict) or isinstance(bad, dict):     # an _err slipped through
        return {"check": check, "status": "UNMEASURED",
                "examined": None, "bad": None,
                "detail": "the query failed; nothing is claimed"}
    return {
        "check": check,
        "status": "PASS" if bad == 0 else "FAIL",
        "examined": int(examined),
        "bad": int(bad),
        "detail": detail,
        # Named records, so a warning can be investigated rather than admired.
        "offenders": offenders or [],
    }


# ------------------------------------------------------------------- prices

def price_integrity(sample_offenders: int = 8) -> dict:
    """
    Every structural property of the price archive, in ONE pass.

    Six separate WHERE clauses would be six full scans of six and a half million
    rows. Conditional aggregates get the same answers from one, and -- more
    usefully -- the row count and every defect count come from the same scan, so
    "examined" cannot disagree with "found".
    """
    conn = get_conn()
    t0 = time.time()
    try:
        row = _one(conn, """
            SELECT COUNT(*)                                                    AS n,
                   COUNT(DISTINCT symbol)                                      AS syms,
                   COUNT(DISTINCT day)                                         AS days,
                   SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END)              AS null_close,
                   SUM(CASE WHEN open IS NULL OR high IS NULL
                              OR low IS NULL THEN 1 ELSE 0 END)                AS null_ohlc,
                   SUM(CASE WHEN close <= 0 THEN 1 ELSE 0 END)                 AS nonpositive_close,
                   SUM(CASE WHEN high IS NOT NULL AND low IS NOT NULL
                              AND high < low THEN 1 ELSE 0 END)                AS high_lt_low,
                   SUM(CASE WHEN close IS NOT NULL AND high IS NOT NULL
                              AND low IS NOT NULL
                              AND (close > high OR close < low)
                            THEN 1 ELSE 0 END)                                 AS close_outside_range,
                   SUM(CASE WHEN volume < 0 THEN 1 ELSE 0 END)                 AS negative_volume,
                   SUM(CASE WHEN isin IS NULL THEN 1 ELSE 0 END)               AS null_isin,
                   SUM(CASE WHEN day > {ph} THEN 1 ELSE 0 END)                 AS future_day
            FROM bhavcopy_eod
        """.replace("{ph}", "%s" if IS_POSTGRES else "?"), (_future_boundary(),))
        if isinstance(row, dict) or row is None:
            return {"domain": "prices", "status": "UNMEASURED",
                    "reason": (row or {}).get("_err", "query failed"),
                    "findings": []}

        (n, syms, days, null_close, null_ohlc, nonpos, hi_lt_lo,
         outside, neg_vol, null_isin, future_day) = [x or 0 for x in row]

        findings = [
            _finding("close is present", n, null_close),
            _finding("open/high/low are present", n, null_ohlc,
                     "a null OHLC is a day that is stored and unusable"),
            _finding("close is positive", n, nonpos),
            _finding("high >= low", n, hi_lt_lo),
            _finding("close lies within its own high-low range", n, outside,
                     "the strongest single check on a price row's internal consistency"),
            _finding("volume is not negative", n, neg_vol),
            _finding("every row carries an ISIN", n, null_isin,
                     "identity is what the corporate-action join is keyed on"),
            _finding("no observation is dated in the future", n, future_day,
                     f"boundary {_future_boundary()}; one day of slack because the "
                     "server clock is UTC and NSE trading days are IST, so today "
                     "in Mumbai can look like tomorrow to the server"),
        ]

        # Duplicates are prevented by the primary key, so this is a check that
        # the constraint is actually there rather than a hunt for rows.
        dupe = _one(conn, """
            SELECT COUNT(*) FROM (
                SELECT symbol, day FROM bhavcopy_eod
                GROUP BY symbol, day HAVING COUNT(*) > 1
            ) t
        """)
        if not isinstance(dupe, dict) and dupe is not None:
            findings.append(_finding("no duplicate (symbol, day)", n, dupe[0] or 0,
                                     "enforced by the primary key; checked anyway"))

        # Name the offenders for anything that failed, so a count becomes a lead.
        for f in findings:
            if f["status"] != "FAIL" or not f["bad"]:
                continue
            clause = {
                "close is present": "close IS NULL",
                "open/high/low are present": "open IS NULL OR high IS NULL OR low IS NULL",
                "close is positive": "close <= 0",
                "high >= low": "high < low",
                "close lies within its own high-low range":
                    "close > high OR close < low",
                "volume is not negative": "volume < 0",
                "every row carries an ISIN": "isin IS NULL",
                "no observation is dated in the future":
                    f"day > '{_future_boundary()}'",
            }.get(f["check"])
            if not clause:
                continue
            got = None
            try:
                got = conn.execute(
                    f"SELECT symbol, day FROM bhavcopy_eod WHERE {clause} "
                    f"LIMIT {int(sample_offenders)}").fetchall()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
            if got:
                f["offenders"] = [f"{r[0]}@{str(r[1])[:10]}" for r in got]
    finally:
        conn.close()

    failed = [f for f in findings if f["status"] == "FAIL"]
    unmeasured = [f for f in findings if f["status"] == "UNMEASURED"]
    return {
        "domain": "prices",
        "status": ("FAIL" if failed else "PARTIAL" if unmeasured else "PASS"),
        "examined": {"rows": n, "securities": syms, "trading_days": days},
        "seconds": round(time.time() - t0, 1),
        "findings": findings,
        "failed": len(failed),
        "unmeasured": len(unmeasured),
    }


# ----------------------------------------------------------------- identity

def identity_integrity(sample_offenders: int = 8) -> dict:
    """
    Whether a symbol still means the same security it meant last year.

    This is the domain where a silent error is worst, because nothing looks
    wrong. A ticker reassigned to a different company keeps producing a price
    series, a momentum score and a chart -- the series is simply two companies
    glued end to end, and the 12-1 momentum computed across the join is a
    confident number about nothing.

    Two directions, and they are NOT the same defect:

      one symbol -> several ISINs   ticker reuse. A defect. The archive is
                                    asserting a continuity the identity system
                                    cannot support.

      one ISIN  -> several symbols  a rename. LEGITIMATE and expected --
                                    ZOMATO became ETERNAL and the security did
                                    not change. Counted and listed, never
                                    failed. Failing it would train the reader
                                    to ignore the audit, which is worse than
                                    not running it.
    """
    conn = get_conn()
    t0 = time.time()
    findings = []
    try:
        row = _one(conn, "SELECT COUNT(*), COUNT(DISTINCT symbol), "
                         "COUNT(DISTINCT isin) FROM bhavcopy_eod "
                         "WHERE isin IS NOT NULL")
        if isinstance(row, dict) or row is None:
            return {"domain": "identity", "status": "UNMEASURED",
                    "reason": (row or {}).get("_err", "query failed"),
                    "findings": []}
        rows_with_isin, n_syms, n_isins = [x or 0 for x in row]

        reuse_n = _one(conn, "SELECT COUNT(*) FROM (SELECT symbol FROM bhavcopy_eod "
                             "WHERE isin IS NOT NULL GROUP BY symbol "
                             "HAVING COUNT(DISTINCT isin) > 1) t")
        reused = conn.execute(
            "SELECT symbol, COUNT(DISTINCT isin) c FROM bhavcopy_eod "
            "WHERE isin IS NOT NULL GROUP BY symbol HAVING COUNT(DISTINCT isin) > 1 "
            "ORDER BY c DESC LIMIT " + str(int(sample_offenders))).fetchall()
        findings.append(_finding(
            "one symbol means one security", n_syms,
            0 if isinstance(reuse_n, dict) else (reuse_n[0] or 0),
            "a symbol carrying two ISINs is two companies in one series",
            [str(r[0]) + " (" + str(r[1]) + " ISINs)" for r in reused]))

        malformed = ("isin IS NOT NULL AND (LENGTH(isin) <> 12 "
                     "OR isin NOT LIKE 'IN%')")
        bad_isin = _one(conn, "SELECT COUNT(*) FROM bhavcopy_eod WHERE " + malformed)
        if not isinstance(bad_isin, dict) and bad_isin is not None:
            mal = conn.execute(
                "SELECT DISTINCT isin FROM bhavcopy_eod WHERE " + malformed +
                " LIMIT " + str(int(sample_offenders))).fetchall()
            findings.append(_finding(
                "every ISIN is well formed", rows_with_isin, bad_isin[0] or 0,
                "12 characters, INE/INF/IN9 prefix",
                [str(r[0]) for r in mal]))

        renamed = conn.execute(
            "SELECT isin, COUNT(DISTINCT symbol) c FROM bhavcopy_eod "
            "WHERE isin IS NOT NULL GROUP BY isin HAVING COUNT(DISTINCT symbol) > 1 "
            "ORDER BY c DESC LIMIT " + str(int(sample_offenders))).fetchall()

        # A rename is SEQUENTIAL: symbol A up to a date, symbol B after it. An
        # accidental merge is SIMULTANEOUS: two symbols sharing one ISIN on the
        # SAME day, which no rename can produce. Separating them is the whole
        # point -- otherwise every legitimate rename in the archive reads as
        # corruption and the finding gets ignored.
        merge_n = _one(conn, """
            SELECT COUNT(*) FROM (
                SELECT isin, day FROM bhavcopy_eod WHERE isin IS NOT NULL
                GROUP BY isin, day HAVING COUNT(DISTINCT symbol) > 1
            ) t
        """)
        merged = conn.execute("""
            SELECT isin, day, COUNT(DISTINCT symbol) c FROM bhavcopy_eod
            WHERE isin IS NOT NULL
            GROUP BY isin, day HAVING COUNT(DISTINCT symbol) > 1
            ORDER BY c DESC LIMIT """ + str(int(sample_offenders))).fetchall()
        if not isinstance(merge_n, dict) and merge_n is not None:
            findings.append(_finding(
                "one ISIN trades under one symbol on any given day",
                rows_with_isin, merge_n[0] or 0,
                "two symbols sharing an ISIN on the same day is a merge error, "
                "not a rename -- a rename is sequential and this is not",
                [f"{r[0]}@{str(r[1])[:10]} ({r[2]} symbols)" for r in merged]))
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"domain": "identity", "status": "UNMEASURED",
                "reason": f"{type(e).__name__}: {e}", "findings": []}
    finally:
        conn.close()

    failed = [x for x in findings if x["status"] == "FAIL"]
    unmeasured = [x for x in findings if x["status"] == "UNMEASURED"]
    return {
        "domain": "identity",
        "status": ("FAIL" if failed else "PARTIAL" if unmeasured else "PASS"),
        "examined": {"rows_with_isin": rows_with_isin,
                     "symbols": n_syms, "distinct_isins": n_isins},
        "seconds": round(time.time() - t0, 1),
        "findings": findings,
        "renames_observed": [str(r[0]) + " -> " + str(r[1]) + " symbols"
                             for r in renamed],
        "note": ("A rename (one ISIN, several symbols) is normal and is counted, "
                 "not failed. Ticker reuse (one symbol, several ISINs) is the "
                 "defect, because it fabricates a continuous history."),
        "failed": len(failed),
    }


# ---------------------------------------------------------------- continuity

def continuity_integrity(move_pct: float = 40.0, sample_offenders: int = 12,
                         gap_days: int = 5, resume_days: int = 10) -> dict:
    """
    Jumps in a price series, and whether a corporate action explains them.

    A 50% overnight fall is either a real event, a split that was never applied,
    or two different companies sharing a ticker. Those are very different
    things, and only the first one is data. An unexplained jump of that size is
    the single most damaging defect in this archive, because momentum is
    computed across it and comes out enormous and confident.

    So the check is not "are there big moves" -- there are, and they are real.
    It is "are there big moves with no corporate action on or near that date".
    A move WITH an action is reported separately and does not fail: that is the
    adjustment layer doing its job and being seen to do it.

    Separately: gaps. A run of more than `gap_days` calendar days with no stored
    trading day is either a market holiday or a hole in the archive. Holidays
    are not enumerable from the data, so this reports the spans and does not
    fail on them. A count that needs a human is honest; a PASS that guessed is
    not.
    """
    ph = "%s" if IS_POSTGRES else "?"
    conn = get_conn()
    t0 = time.time()
    findings = []
    examined = {}
    try:
        # One window pass for the jumps. LAG partitioned by symbol is a sort of
        # the archive; it is the expensive query in this module and it is why
        # continuity is its own domain rather than part of prices.
        jump_sql = f"""
            WITH stepped AS (
                SELECT symbol, day, close,
                       LAG(close) OVER (PARTITION BY symbol ORDER BY day) AS prev
                FROM bhavcopy_eod
                WHERE close IS NOT NULL AND close > 0
            ),
            moves AS (
                SELECT symbol, day, close, prev,
                       100.0 * (close - prev) / prev AS pct
                FROM stepped
                WHERE prev IS NOT NULL AND prev > 0
            )
            SELECT COUNT(*) AS steps,
                   SUM(CASE WHEN ABS(pct) >= {ph} THEN 1 ELSE 0 END) AS big
            FROM moves
        """
        row = _one(conn, jump_sql, (move_pct,))
        if isinstance(row, dict) or row is None:
            return {"domain": "continuity", "status": "UNMEASURED",
                    "reason": (row or {}).get("_err", "window query failed"),
                    "findings": []}
        steps, big = [x or 0 for x in row]
        examined["day_over_day_steps"] = steps

        # Which of those jumps has a corporate action within +/- 3 days on the
        # same ISIN? Anything left over is a jump nobody has explained.
        explained = unexplained = None
        offenders = []
        try:
            # The +/- 3 day window is expressed in SQL-portable string dates by
            # comparing against the day itself; a date function differs between
            # SQLite and Postgres, so the window is applied in Python below.
            # `prev_day` matters as much as `prev`. LAG returns the previous
            # STORED day, which for a suspended stock can be years earlier. A
            # security that stopped trading in 2015 and resumed in 2020 shows
            # here as one enormous "overnight" move, and calling that a data
            # defect would be wrong -- nothing about the price is incorrect,
            # the two observations are simply not adjacent in time.
            rows = conn.execute(f"""
                WITH stepped AS (
                    SELECT symbol, isin, day, close,
                           LAG(close) OVER (PARTITION BY symbol ORDER BY day) AS prev,
                           LAG(day)   OVER (PARTITION BY symbol ORDER BY day) AS prev_day
                    FROM bhavcopy_eod
                    WHERE close IS NOT NULL AND close > 0
                )
                SELECT symbol, isin, day, prev_day,
                       100.0 * (close - prev) / prev AS pct
                FROM stepped
                WHERE prev IS NOT NULL AND prev > 0
                  AND ABS(100.0 * (close - prev) / prev) >= {ph}
                ORDER BY ABS(100.0 * (close - prev) / prev) DESC
                LIMIT 5000
            """, (move_pct,)).fetchall()

            actions = set()
            try:
                for isin, ex in conn.execute(
                        "SELECT isin, ex_date FROM corporate_actions").fetchall():
                    actions.add((str(isin), str(ex)[:10]))
            except Exception:
                actions = None

            if actions is None:
                findings.append({"check": "a large move has a corporate action",
                                 "status": "UNMEASURED", "examined": None,
                                 "bad": None,
                                 "detail": "corporate_actions unreadable",
                                 "offenders": []})
            else:
                explained = unexplained = stale = 0
                stale_eg = []
                for sym, isin, day, prev_day, pct in rows:
                    d = str(day)[:10]
                    # Not adjacent in time -> not an overnight move at all.
                    apart = None
                    if prev_day:
                        try:
                            apart = (_dt.date.fromisoformat(d)
                                     - _dt.date.fromisoformat(str(prev_day)[:10])).days
                        except Exception:
                            apart = None
                    if apart is not None and apart > resume_days:
                        stale += 1
                        if len(stale_eg) < sample_offenders:
                            stale_eg.append(f"{sym}@{d} {pct:+.1f}% after {apart}d silent")
                        continue
                    near = False
                    if isin:
                        base = _dt.date.fromisoformat(d)
                        for k in range(-3, 4):
                            if (str(isin), (base + _dt.timedelta(days=k)).isoformat()) in actions:
                                near = True
                                break
                    if near:
                        explained += 1
                    else:
                        unexplained += 1
                        if len(offenders) < sample_offenders:
                            offenders.append(f"{sym}@{d} {pct:+.1f}%")
                adjacent = len(rows) - stale
                findings.append(_finding(
                    "a large overnight move is explained by a corporate action",
                    adjacent, unexplained,
                    f"moves of at least {move_pct}% between CONSECUTIVE trading "
                    f"days no more than {resume_days} days apart; a corporate "
                    f"action on the same ISIN within 3 days counts as explained. "
                    f"{explained} explained, {unexplained} not. A further {stale} "
                    f"large moves were excluded as resumptions after a long "
                    f"silence -- those are not overnight moves and are reported "
                    f"separately rather than counted as defects.",
                    offenders))
                examined["large_moves_examined"] = len(rows)
                examined["large_moves_total"] = big
                examined["large_moves_adjacent"] = adjacent
                examined["large_moves_after_long_silence"] = stale
                examined["resumption_examples"] = stale_eg[:6]
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            findings.append({"check": "a large move is explained by a corporate action",
                             "status": "UNMEASURED", "examined": None, "bad": None,
                             "detail": f"{type(e).__name__}: {e}", "offenders": []})

        # Calendar gaps between consecutive stored trading days. Reported, not
        # failed: NSE holidays are not derivable from this table.
        spans = []
        try:
            days = [str(r[0])[:10] for r in conn.execute(
                "SELECT DISTINCT day FROM bhavcopy_eod ORDER BY day").fetchall()]
            examined["distinct_days"] = len(days)
            if days:
                examined["first_day"], examined["last_day"] = days[0], days[-1]
            for a, b in zip(days, days[1:]):
                delta = (_dt.date.fromisoformat(b) - _dt.date.fromisoformat(a)).days
                if delta > gap_days:
                    spans.append(f"{a} -> {b} ({delta}d)")
        except Exception as e:
            spans = None
            examined["distinct_days"] = f"unreadable: {type(e).__name__}"
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"domain": "continuity", "status": "UNMEASURED",
                "reason": f"{type(e).__name__}: {e}", "findings": []}
    finally:
        conn.close()

    failed = [f for f in findings if f["status"] == "FAIL"]
    unmeasured = [f for f in findings if f["status"] == "UNMEASURED"]
    return {
        "domain": "continuity",
        "status": ("FAIL" if failed else "PARTIAL" if unmeasured else "PASS"),
        "examined": examined,
        "seconds": round(time.time() - t0, 1),
        "findings": findings,
        "calendar_gaps_over_%dd" % gap_days: (
            spans[:40] if spans is not None else "unmeasured"),
        "calendar_gap_count": (len(spans) if spans is not None else None),
        "gap_note": ("Gaps are listed, not failed. NSE holidays are not "
                     "derivable from this table, so a holiday and a hole look "
                     "identical here and a human has to tell them apart."),
    }


# ------------------------------------------------------- fundamentals / PIT

def fundamentals_pit_integrity() -> dict:
    """
    Point-in-time: was every input knowable on the date it is attached to?

    The headline finding is structural and is stated first, because it is the
    one that matters: THERE IS NO STORED FUNDAMENTALS HISTORY. Fundamentals are
    fetched live from Yahoo at scoring time -- a balance sheet as it reads
    today, not as it read on the date being scored. So a historical
    fundamentals PIT audit is not merely failing here, it is not possible, and
    reporting it as PASS because no violation was found in an empty table would
    be the worst answer available.

    What IS measurable is reported honestly:
      - corporate actions, which ARE stored with ex-dates and are the PIT
        backbone for prices;
      - the observation timestamps on stored factor inputs.
    """
    conn = get_conn()
    t0 = time.time()
    findings = []
    examined = {}
    boundary = _future_boundary()
    try:
        # Corporate actions: the part of the PIT layer that genuinely exists.
        row = _one(conn, "SELECT COUNT(*), COUNT(DISTINCT isin), "
                         "MIN(ex_date), MAX(ex_date) FROM corporate_actions")
        if isinstance(row, dict) or row is None:
            findings.append({"check": "corporate actions are readable",
                             "status": "UNMEASURED", "examined": None,
                             "bad": None,
                             "detail": (row or {}).get("_err", "unreadable"),
                             "offenders": []})
            ca_n = 0
        else:
            ca_n, ca_isins, ca_min, ca_max = [x if x is not None else 0 for x in row]
            examined["corporate_actions"] = ca_n
            examined["corporate_action_isins"] = ca_isins
            examined["ex_date_span"] = f"{ca_min} .. {ca_max}"

            if ca_n:
                bad_isin = _one(conn, "SELECT COUNT(*) FROM corporate_actions "
                                      "WHERE isin IS NULL OR isin = ''")
                if not isinstance(bad_isin, dict) and bad_isin:
                    findings.append(_finding(
                        "every corporate action carries an ISIN", ca_n,
                        bad_isin[0] or 0,
                        "an action with no ISIN cannot be joined to a price "
                        "series, so it silently never applies"))

                ph = "%s" if IS_POSTGRES else "?"
                fut = _one(conn, f"SELECT COUNT(*) FROM corporate_actions "
                                 f"WHERE ex_date > {ph}", (boundary,))
                if not isinstance(fut, dict) and fut:
                    # A future ex-date is legitimate: an announced action has an
                    # ex-date ahead of today. Counted, not failed.
                    examined["announced_future_ex_dates"] = fut[0] or 0

                unparsed = _one(conn, "SELECT COUNT(*) FROM corporate_actions "
                                      "WHERE parsed = 0")
                if not isinstance(unparsed, dict) and unparsed:
                    findings.append(_finding(
                        "every corporate action was parsed into a multiplier",
                        ca_n, unparsed[0] or 0,
                        "an unparsed action is stored, visible, and has no "
                        "effect on any price"))

        # Factor input observation timestamps.
        obs = _one(conn, "SELECT COUNT(*), SUM(CASE WHEN observed_at IS NULL "
                         "THEN 1 ELSE 0 END) FROM factor_inputs")
        if isinstance(obs, dict) or obs is None:
            findings.append({"check": "factor inputs carry an observation time",
                             "status": "UNMEASURED", "examined": None,
                             "bad": None, "detail": "factor_inputs unreadable",
                             "offenders": []})
        else:
            fi_n, fi_null = [x or 0 for x in obs]
            examined["factor_inputs"] = fi_n
            if fi_n:
                findings.append(_finding(
                    "every factor input carries an observation time", fi_n,
                    fi_null,
                    "without one there is no way to say what was knowable when"))
                ph = "%s" if IS_POSTGRES else "?"
                fut = _one(conn, f"SELECT COUNT(*) FROM factor_inputs "
                                 f"WHERE observed_at > {ph}",
                           (boundary + "T23:59:59",))
                if not isinstance(fut, dict) and fut:
                    findings.append(_finding(
                        "no factor input was observed in the future", fi_n,
                        fut[0] or 0, f"boundary {boundary} (UTC/IST slack)"))
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"domain": "fundamentals_pit", "status": "UNMEASURED",
                "reason": f"{type(e).__name__}: {e}", "findings": []}
    finally:
        conn.close()

    failed = [f for f in findings if f["status"] == "FAIL"]
    unmeasured = [f for f in findings if f["status"] == "UNMEASURED"]
    return {
        "domain": "fundamentals_pit",
        # PARTIAL is not a softened PASS. The fundamentals half of this domain
        # cannot be measured at all, and that is the finding.
        "status": ("FAIL" if failed else "PARTIAL"),
        "examined": examined,
        "seconds": round(time.time() - t0, 1),
        "findings": findings,
        "fundamentals_history": {
            "stored": False,
            "status": "UNMEASURED",
            "reason": ("No point-in-time fundamentals table exists. Valuation "
                       "and quality inputs are fetched live from Yahoo at "
                       "scoring time, which returns the statement as it reads "
                       "today, not as it read on the date being scored."),
            "consequence": ("No historical fundamentals PIT audit is possible, "
                            "and no backtest using these factors can claim to "
                            "be point-in-time. Only the price and corporate-"
                            "action layer is PIT."),
        },
        "unmeasured": len(unmeasured),
        "failed": len(failed),
    }


# --------------------------------------------------------------------- news

def news_integrity(cycle: str = None, sample_offenders: int = 10,
                   max_articles: int = 120000) -> dict:
    """
    Whether the articles that fed a sentiment score were about that company.

    Re-runs the PRODUCTION matcher over the stored articles rather than a fresh
    implementation of the same idea. A second implementation would test whether
    two functions agree, which is not the question. The question is whether the
    function the app actually ships accepts what the app actually stored.

    The failure being guarded against is on record. On the 2026-09-03 cycle only
    57% of scored articles were about the company at all, and the intruders were
    same-morning market stories whose time-decay weight sat near 1.0 -- so SBIN
    and ONGC reported sentiment confidence 1.00 on zero relevant articles. The
    model was most certain exactly where it knew least.
    """
    try:
        from rss_news import _identity_terms, _mentions
    except Exception:
        try:
            from .rss_news import _identity_terms, _mentions
        except Exception as e:
            return {"domain": "news", "status": "UNMEASURED",
                    "reason": f"matcher unavailable: {e}", "findings": []}
    try:
        from stock_universe import get_stock_by_symbol
    except Exception:
        try:
            from .stock_universe import get_stock_by_symbol
        except Exception:
            get_stock_by_symbol = None

    boundary = _future_boundary()
    conn = get_conn()
    t0 = time.time()
    try:
        if not cycle:
            r = _one(conn, "SELECT MAX(cycle_id) FROM factor_input_articles")
            cycle = r[0] if r and not isinstance(r, dict) else None
        if not cycle:
            return {"domain": "news", "status": "UNMEASURED",
                    "reason": "no article cycle recorded", "findings": []}
        ph = "%s" if IS_POSTGRES else "?"
        total = _one(conn, "SELECT COUNT(*) FROM factor_input_articles "
                           f"WHERE cycle_id = {ph}", (cycle,))
        total = 0 if isinstance(total, dict) or not total else (total[0] or 0)
        # Bounded. This app has been killed by an unbounded query before, and a
        # read-only audit that takes production down is not an improvement. If
        # the bound bites, the report says so rather than quietly describing a
        # sample as if it were the whole.
        rows = conn.execute(
            "SELECT ticker, title, published_at FROM factor_input_articles "
            f"WHERE cycle_id = {ph} ORDER BY ticker LIMIT {int(max_articles)}",
            (cycle,)).fetchall()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"domain": "news", "status": "UNMEASURED",
                "reason": f"{type(e).__name__}: {e}", "findings": []}
    finally:
        conn.close()

    n = len(rows)
    if not n:
        return {"domain": "news", "status": "UNMEASURED",
                "reason": f"no articles stored for cycle {cycle}", "findings": []}

    terms, offtopic, future, undated = {}, [], 0, 0
    per_ticker = {}
    for ticker, title, published_at in rows:
        t = str(ticker)
        per_ticker.setdefault(t, [0, 0])
        per_ticker[t][0] += 1

        if not published_at:
            undated += 1
        elif str(published_at)[:10] > boundary:
            future += 1

        if t not in terms:
            name = t.replace(".NS", "")
            if get_stock_by_symbol:
                try:
                    rec = get_stock_by_symbol(name)
                    if rec and rec.get("company_name"):
                        name = rec["company_name"]
                except Exception:
                    pass
            terms[t] = _identity_terms(name, t)
        words, patterns = terms[t]
        if title and not _mentions(title, words, patterns):
            per_ticker[t][1] += 1
            if len(offtopic) < sample_offenders:
                offtopic.append(t + ": " + str(title)[:56])

    # One article scored for many companies is the signature of a market-wide
    # story leaking into company sentiment -- the exact 2026-09-03 defect. A
    # genuine article can name two or three companies; it does not name thirty.
    by_title = {}
    for ticker, title, _ in rows:
        if title:
            by_title.setdefault(str(title).strip().lower(), set()).add(str(ticker))
    SHARED_MAX = 5
    overshared = sorted(((t, len(v)) for t, v in by_title.items()
                         if len(v) > SHARED_MAX), key=lambda x: -x[1])
    dup_titles = sum(1 for v in by_title.values() if len(v) > 1)

    # The known SBIN leak, MEASURED rather than asserted. The two-token name
    # shortening yields the phrase "state bank", which matches any state bank
    # anywhere. This counts how many stored articles actually exploit it.
    sbin_leak = [t for t in by_title
                 if "state bank" in t and "state bank of india" not in t]

    off_n = sum(v[1] for v in per_ticker.values())
    findings = [
        _finding("every scored article names the company it was scored for",
                 n, off_n,
                 "re-run through the production matcher, not a copy of it",
                 offtopic),
        _finding("no article is published in the future", n, future,
                 "boundary " + boundary + " (UTC/IST slack)"),
        _finding("every article carries a publication date", n, undated,
                 "an undated article cannot be time-decayed, so its weight is "
                 "a guess"),
        _finding(f"no article is scored for more than {SHARED_MAX} companies",
                 len(by_title), len(overshared),
                 "a headline attached to dozens of securities is a market "
                 "story wearing a company's name",
                 [f"{t[:44]} ({c} companies)" for t, c in overshared[:sample_offenders]]),
    ]
    worst = sorted(((t, v[1], v[0]) for t, v in per_ticker.items() if v[1]),
                   key=lambda x: -x[1])[:sample_offenders]
    failed = [x for x in findings if x["status"] == "FAIL"]
    return {
        "domain": "news",
        "status": "FAIL" if failed else "PASS",
        "cycle": cycle,
        "examined": {"articles": n, "securities": len(per_ticker),
                     "articles_in_cycle": total,
                     "complete": (n >= total),
                     "truncated_by_bound": (total > n)},
        "seconds": round(time.time() - t0, 1),
        "findings": findings,
        "relevance_pct": round(100.0 * (n - off_n) / n, 1),
        "worst_securities": [t + ": " + str(b) + "/" + str(s) + " off-topic"
                             for t, b, s in worst],
        "distinct_titles": len(by_title),
        "titles_shared_by_more_than_one_security": dup_titles,
        "known_defect_sbin_state_bank": {
            "mechanism": "CONFIRMED",
            "articles_matching_state_bank_not_india": len(sbin_leak),
            "examples": sbin_leak[:5],
            "note": ("Not fixed in this run. Changing the matcher changes which "
                     "articles feed sentiment, which changes scores, and V1.4 "
                     "is frozen."),
        },
    }


# ------------------------------------------------------------ missing data

def missing_data_audit(cycle: str = None) -> dict:
    """
    Per factor: complete, partial, refused, unavailable, unexplained.

    These are five different things and the app has already been bitten by
    treating them as one -- 286 refusals were once stored as 0.0, which reads as
    "average" rather than "we could not tell". The categories are kept apart
    here for the same reason.

    `unexplained` is the number that matters. A missing input with a recorded
    reason is a limitation; a missing input with no reason is a defect.
    """
    conn = get_conn()
    try:
        if not cycle:
            r = _one(conn, "SELECT MAX(cycle_id) FROM factor_inputs")
            cycle = r[0] if r and not isinstance(r, dict) else None
        if not cycle:
            return {"domain": "missing_data", "status": "UNMEASURED",
                    "reason": "no cycle recorded"}

        ph = "%s" if IS_POSTGRES else "?"
        # Five states, kept apart deliberately. They are NOT degrees of the same
        # thing, and pooling them is how 286 refusals once became 0.0 -- which
        # reads to a model as "average" rather than "we could not tell".
        #
        #   present      a real number arrived
        #   genuine zero the value IS zero. Zero debt is not missing debt.
        #   null         no value, and the row admits it (missing = 1)
        #   refused      no value, WITH a recorded reason -- a limitation
        #   unexplained  no value and no reason, or a null not flagged missing.
        #                This is the only one that is a defect.
        rows = conn.execute(
            "SELECT factor, "
            "       COUNT(*) AS inputs, "
            "       SUM(CASE WHEN missing = 1 THEN 1 ELSE 0 END) AS missing_n, "
            "       SUM(CASE WHEN missing = 0 AND value_num = 0 THEN 1 ELSE 0 END) "
            "           AS genuine_zero, "
            "       SUM(CASE WHEN missing = 0 AND value_num IS NULL "
            "                 AND value_text IS NULL THEN 1 ELSE 0 END) "
            "           AS null_unflagged, "
            "       COUNT(DISTINCT ticker) AS tickers "
            f"FROM factor_inputs WHERE cycle_id = {ph} GROUP BY factor",
            (cycle,)).fetchall()

        refusals = conn.execute(
            "SELECT factor, COUNT(DISTINCT ticker) FROM factor_inputs "
            f"WHERE cycle_id = {ph} AND input_name = 'refusal_reason' "
            "GROUP BY factor", (cycle,)).fetchall()
        refusal_by_factor = {r[0]: r[1] for r in refusals}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"domain": "missing_data", "status": "UNMEASURED",
                "reason": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()

    per, unexplained_total = [], 0
    for (factor, inputs, missing_n, genuine_zero, null_unflagged,
         tickers) in rows:
        missing_n = missing_n or 0
        null_unflagged = null_unflagged or 0
        unexplained_total += null_unflagged
        per.append({
            "factor": factor,
            "securities": tickers,
            "inputs_recorded": inputs,
            "present": inputs - missing_n - null_unflagged,
            "genuine_zero": genuine_zero or 0,
            "flagged_missing": missing_n,
            "securities_that_refused": refusal_by_factor.get(factor, 0),
            "unexplained": null_unflagged,
            "pct_inputs_missing": round(100.0 * missing_n / max(inputs, 1), 2),
        })
    findings = [_finding(
        "no input is missing without saying why",
        sum(p["inputs_recorded"] for p in per), unexplained_total,
        "a value that is absent, not flagged missing and carries no refusal "
        "reason is the only one of the five states that is a defect")]
    return {
        "domain": "missing_data",
        "status": ("FAIL" if unexplained_total else "PASS") if per else "UNMEASURED",
        "findings": findings,
        "cycle": cycle,
        "examined": {"factors": len(per),
                     "input_rows": sum(p["inputs_recorded"] for p in per)},
        "per_factor": per,
        "note": ("A missing input with a recorded reason is a limitation. One "
                 "without a reason is a defect. Zero, NULL, refusal and "
                 "unavailable are four different things and are not pooled."),
    }


def audit() -> dict:
    """Everything, with each domain's own examined-count carried through."""
    t0 = time.time()
    domains = [price_integrity(), continuity_integrity(), identity_integrity(),
               fundamentals_pit_integrity(), news_integrity(),
               missing_data_audit()]
    statuses = [d.get("status") for d in domains]
    overall = ("FAIL" if "FAIL" in statuses
               else "PARTIAL" if ("PARTIAL" in statuses or "UNMEASURED" in statuses)
               else "PASS")
    return {
        "report": "STEP 3 — DATA INTEGRITY",
        "overall": overall,
        "domains": domains,
        "seconds": round(time.time() - t0, 1),
        "no_single_score": ("Deliberately absent. The components are not "
                            "commensurable -- a duplicate row and an undated "
                            "article are different units -- and averaging them "
                            "would hide which half is broken."),
    }


# ------------------------------------------------- why the scan skips stocks

_ERR_NOISE = re.compile(r"[A-Z0-9&.\-]{2,}\.NS|\b\d{4}-\d{2}-\d{2}\b|\b\d+\b")


def _err_signature(err: str) -> str:
    """
    Collapse an error to its shape, so 188 messages become a handful of causes.

    Ticker names, dates and numbers are stripped: "no price data for ABC.NS"
    and "no price data for XYZ.NS" are one cause, not two. Without this the
    grouping just re-lists the failures.
    """
    s = (err or "").strip()
    if not s:
        return "(no error recorded)"
    s = _ERR_NOISE.sub("<x>", s)
    return " ".join(s.split())[:120]


def scan_failures(cycle: str = None, sample: int = 10) -> dict:
    """
    The securities the daily alpha scan does not score, and why.

    188 of 2,895 fail every day. They are recorded in `alpha_scan2.error` and
    surfaced nowhere -- not on the landing page, not in the app. A number that
    nobody reads is the same as a number nobody measured, so this reads it.

    Two questions matter more than the count. Is the failing set STABLE across
    cycles -- which would mean a systematic cause like delisting or a data gap,
    something a universe filter should exclude -- or does it move, which would
    mean throttling and a different fix entirely. And are the failures
    concentrated in securities anyone would trade.
    """
    conn = get_conn()
    t0 = time.time()
    ph = _ph()
    try:
        if not cycle:
            r = _one(conn, "SELECT MAX(cycle) FROM alpha_scan2")
            cycle = r[0] if r and not isinstance(r, dict) else None
        if not cycle:
            return {"audit": "scan_failures", "status": "UNMEASURED",
                    "reason": "no scan cycle recorded"}

        rows = conn.execute(
            "SELECT ticker, error, market_cap FROM alpha_scan2 "
            f"WHERE cycle = {ph} AND alpha_score IS NULL", (cycle,)).fetchall()
        total = _one(conn, f"SELECT COUNT(*) FROM alpha_scan2 WHERE cycle = {ph}",
                     (cycle,))
        total = 0 if isinstance(total, dict) or not total else (total[0] or 0)

        # Is it the same set every day? That is the difference between a
        # systematic exclusion and a transient one, and it decides the fix.
        cycles = [str(r[0]) for r in conn.execute(
            "SELECT DISTINCT cycle FROM alpha_scan2 ORDER BY cycle DESC "
            "LIMIT 4").fetchall()]
        overlap = None
        if len(cycles) > 1:
            prev = {str(r[0]) for r in conn.execute(
                "SELECT ticker FROM alpha_scan2 "
                f"WHERE cycle = {ph} AND alpha_score IS NULL",
                (cycles[1],)).fetchall()}
            now = {str(r[0]) for r in rows}
            # "Recovered" has to mean tried and scored. Since the no-market-data
            # filter, a ticker can also leave the failure list by not being
            # attempted at all, and counting that as recovery listed 3BBLACKBIO,
            # AASTHA and the rest as fixed when they had only been skipped.
            attempted = {str(r[0]) for r in conn.execute(
                f"SELECT ticker FROM alpha_scan2 WHERE cycle = {ph}",
                (cycle,)).fetchall()}
            if prev:
                overlap = {
                    "previous_cycle": cycles[1],
                    "failed_then": len(prev),
                    "failed_now": len(now),
                    "in_both": len(prev & now),
                    "pct_of_today_also_failed_yesterday":
                        round(100.0 * len(prev & now) / max(len(now), 1), 1),
                    "new_today": sorted(now - prev)[:sample],
                    "recovered_today": sorted((prev - now) & attempted)[:sample],
                    "not_attempted_today": len(prev - attempted),
                    "not_attempted_examples": sorted(prev - attempted)[:sample],
                }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"audit": "scan_failures", "status": "UNMEASURED",
                "reason": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()

    causes = {}
    for ticker, err, mcap in rows:
        sig = _err_signature(err)
        d = causes.setdefault(sig, {"n": 0, "examples": [], "with_market_cap": 0})
        d["n"] += 1
        if mcap:
            d["with_market_cap"] += 1
        if len(d["examples"]) < sample:
            d["examples"].append(str(ticker))

    ordered = dict(sorted(causes.items(), key=lambda kv: -kv[1]["n"]))
    no_reason = sum(v["n"] for k, v in causes.items()
                    if k == "(no error recorded)")

    # Stocks that found no market data twice running. Those that never scored
    # are one night from the universe filter. Those that were scoring are
    # protected from it, and dozens of them at once is a data problem on our side
    # (the nights of 2026-09-11 and 12). The nightly production check reads both;
    # UNMEASURED if it cannot be computed.
    try:
        from universe_scan import at_risk_of_exclusion
        _c = get_conn()
        try:
            at_risk = at_risk_of_exclusion(_c, today=str(cycle)[:10], sample=sample)
        finally:
            _c.close()
    except Exception as e:
        at_risk = {"status": "UNMEASURED", "reason": f"{type(e).__name__}: {e}",
                   "at_risk": None}

    return {
        "audit": "scan_failures",
        "read_only": True,
        "cycle": cycle,
        "seconds": round(time.time() - t0, 1),
        "examined": {"tickers_in_cycle": total, "failed": len(rows)},
        "failed_without_a_recorded_reason": no_reason,
        "causes": ordered,
        "stability_vs_previous_cycle": overlap,
        "at_risk_of_exclusion": at_risk,
        "note": ("A failure with no recorded reason is the only one that is a "
                 "defect in the scan itself; the rest are the scan correctly "
                 "reporting that a security cannot be scored."),
    }
