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


# --------------------------------------------------------------------- news

def news_integrity(cycle: str = None, sample_offenders: int = 10) -> dict:
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
        rows = conn.execute(
            "SELECT ticker, title, published_at FROM factor_input_articles "
            "WHERE cycle_id = ?" if not IS_POSTGRES else
            "SELECT ticker, title, published_at FROM factor_input_articles "
            "WHERE cycle_id = %s", (cycle,)).fetchall()
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
    ]
    worst = sorted(((t, v[1], v[0]) for t, v in per_ticker.items() if v[1]),
                   key=lambda x: -x[1])[:sample_offenders]
    failed = [x for x in findings if x["status"] == "FAIL"]
    return {
        "domain": "news",
        "status": "FAIL" if failed else "PASS",
        "cycle": cycle,
        "examined": {"articles": n, "securities": len(per_ticker)},
        "seconds": round(time.time() - t0, 1),
        "findings": findings,
        "relevance_pct": round(100.0 * (n - off_n) / n, 1),
        "worst_securities": [t + ": " + str(b) + "/" + str(s) + " off-topic"
                             for t, b, s in worst],
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

        rows = conn.execute(
            "SELECT factor, "
            "       COUNT(*) AS inputs, "
            "       SUM(CASE WHEN missing = 1 THEN 1 ELSE 0 END) AS missing_n, "
            "       COUNT(DISTINCT ticker) AS tickers "
            "FROM factor_inputs WHERE cycle_id = ? GROUP BY factor",
            (cycle,)).fetchall()

        refusals = conn.execute(
            "SELECT factor, COUNT(DISTINCT ticker) FROM factor_inputs "
            "WHERE cycle_id = ? AND input_name = 'refusal_reason' "
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

    per = []
    for factor, inputs, missing_n, tickers in rows:
        per.append({
            "factor": factor,
            "securities": tickers,
            "inputs_recorded": inputs,
            "inputs_missing": missing_n or 0,
            "securities_that_refused": refusal_by_factor.get(factor, 0),
            "pct_inputs_missing": round(100.0 * (missing_n or 0) / max(inputs, 1), 2),
        })
    return {
        "domain": "missing_data",
        "status": "PASS" if per else "UNMEASURED",
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
    domains = [price_integrity(), identity_integrity(),
               news_integrity(), missing_data_audit()]
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
