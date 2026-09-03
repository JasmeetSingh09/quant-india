"""
provenance_gap.py — why an observation has no complete provenance.

Read-only. It writes nothing, re-fetches nothing, and scores nothing. Every
number here comes from rows already in the database.

`factor_history.raw_inputs_available` is set from `factor_provenance.capture()`
returning complete, which is true only when every factor that produced a score
also produced all of its declared inputs. That is a strict test, so a 70% rate
is not by itself a fault — it could be the honest result of stocks that have no
news to read or no peers to compare against. It could equally be a capture bug.
Averages cannot tell those apart, so this queries the actual rows.

Four outcomes are distinguished per factor:

  legitimate_missing    the factor scored, its input rows exist, and some are
                        flagged missing — the value genuinely was not there
                        (a company with no P/E because it has no earnings)
  not_applicable        the factor never scored, so nothing is held against it
  capture_failure       the factor scored but NO input rows were written at all
                        — provenance was supposed to run and did not
  scoring_mismatch      the factor scored but EVERY declared input is missing —
                        a score computed from nothing, which is a real defect
"""

import time

from db import get_conn, IS_POSTGRES
from factor_provenance import CAPTURE_MAP

# factor_history columns holding a per-factor score. growth and low_risk are
# absent from CAPTURE_MAP, so they are not part of the completeness test and
# are not examined here.
SCORE_COLUMN = {"momentum": "momentum", "quality": "quality",
                "value": "value", "sentiment": "sentiment"}

SAMPLE_LIMIT = 8


def _q(conn, sql, args=(), one=True, default=0):
    """Query, and leave the connection usable if it fails.

    On Postgres a failed statement aborts the whole transaction, so without the
    rollback one missing table makes every later query report an error about
    tables that are perfectly fine. Learned the hard way in cycle_audit.
    """
    try:
        rows = conn.execute(sql, args).fetchall()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return default if one else []
    if not one:
        return rows
    return rows[0][0] if rows else default


def analyze(cycle: str) -> dict:
    t0 = time.time()
    out = {"available": True, "cycle": cycle, "read_only": True}
    conn = get_conn()
    try:
        total = _q(conn, "SELECT COUNT(*) FROM factor_history WHERE cycle_id=?",
                   (cycle,))
        complete = _q(conn, "SELECT COUNT(*) FROM factor_history "
                            "WHERE cycle_id=? AND raw_inputs_available=1", (cycle,))
        incomplete = total - complete
        out["observations"] = {
            "total": total, "with_complete_inputs": complete,
            "incomplete": incomplete,
            "incomplete_pct": round(100.0 * incomplete / total, 2) if total else 0.0,
        }

        # Observations with no provenance rows AT ALL — distinct from a partial
        # capture. It would mean capture() never stored anything for them.
        no_rows = _q(conn,
                     "SELECT COUNT(*) FROM factor_history fh WHERE fh.cycle_id=? "
                     "AND fh.raw_inputs_available=0 AND NOT EXISTS "
                     "(SELECT 1 FROM factor_inputs fi WHERE fi.ticker=fh.ticker "
                     "AND fi.cycle_id=fh.cycle_id)", (cycle,))
        out["observations"]["incomplete_with_no_inputs_at_all"] = no_rows

        factors, attribution = {}, {}
        for factor, keys in CAPTURE_MAP.items():
            col = SCORE_COLUMN.get(factor)
            if not col:
                continue
            marks = ",".join("?" for _ in keys)

            scored = _q(conn, "SELECT COUNT(*) FROM factor_history "
                              "WHERE cycle_id=? AND " + col + " IS NOT NULL",
                        (cycle,))
            not_scored = total - scored

            # Stocks where this factor scored but at least one declared input is
            # flagged missing. Restricted to scored stocks: an unscored factor
            # is not held against the observation.
            blocked = _q(conn,
                         "SELECT COUNT(DISTINCT fi.ticker) FROM factor_inputs fi "
                         "JOIN factor_history fh ON fh.ticker=fi.ticker "
                         "AND fh.cycle_id=fi.cycle_id "
                         "WHERE fi.cycle_id=? AND fi.factor=? AND fi.missing=1 "
                         "AND fi.input_name IN (" + marks + ") "
                         "AND fh." + col + " IS NOT NULL", (cycle, factor, *keys))

            # Scored, but provenance wrote nothing at all for this factor.
            cap_fail = _q(conn,
                          "SELECT COUNT(*) FROM factor_history fh "
                          "WHERE fh.cycle_id=? AND fh." + col + " IS NOT NULL "
                          "AND NOT EXISTS (SELECT 1 FROM factor_inputs fi "
                          "WHERE fi.ticker=fh.ticker AND fi.cycle_id=fh.cycle_id "
                          "AND fi.factor=?)", (cycle, factor))

            # Scored, but every declared input missing — a score from nothing.
            mismatch = _q(conn,
                          "SELECT COUNT(*) FROM (SELECT fi.ticker "
                          "FROM factor_inputs fi JOIN factor_history fh "
                          "ON fh.ticker=fi.ticker AND fh.cycle_id=fi.cycle_id "
                          "WHERE fi.cycle_id=? AND fi.factor=? "
                          "AND fh." + col + " IS NOT NULL "
                          "AND fi.input_name IN (" + marks + ") "
                          "GROUP BY fi.ticker "
                          "HAVING SUM(fi.missing)=COUNT(*)) x",
                          (cycle, factor, *keys))

            per_input = _q(conn,
                           "SELECT fi.input_name, COUNT(*) FROM factor_inputs fi "
                           "JOIN factor_history fh ON fh.ticker=fi.ticker "
                           "AND fh.cycle_id=fi.cycle_id "
                           "WHERE fi.cycle_id=? AND fi.factor=? AND fi.missing=1 "
                           "AND fh." + col + " IS NOT NULL "
                           "GROUP BY fi.input_name ORDER BY COUNT(*) DESC",
                           (cycle, factor), one=False)

            samples = _q(conn,
                         "SELECT DISTINCT fi.ticker FROM factor_inputs fi "
                         "JOIN factor_history fh ON fh.ticker=fi.ticker "
                         "AND fh.cycle_id=fi.cycle_id "
                         "WHERE fi.cycle_id=? AND fi.factor=? AND fi.missing=1 "
                         "AND fh." + col + " IS NOT NULL "
                         "LIMIT " + str(SAMPLE_LIMIT), (cycle, factor), one=False)

            factors[factor] = {
                "scored": scored,
                "did_not_score": not_scored,
                "scored_pct": round(100.0 * scored / total, 2) if total else 0.0,
                "blocking_completeness": blocked,
                "blocking_pct_of_all": round(100.0 * blocked / total, 2) if total else 0.0,
                "capture_failure": cap_fail,
                "scoring_mismatch": mismatch,
                "missing_by_input": [
                    {"input": r[0], "stocks": r[1],
                     "pct_of_scored": round(100.0 * r[1] / scored, 2) if scored else 0.0}
                    for r in per_input],
                "examples": [r[0] for r in samples],
            }
            attribution[factor] = blocked

        out["factors"] = factors

        # Do the missing inputs account for every incomplete observation?
        explained = _q(conn,
                       "SELECT COUNT(DISTINCT fi.ticker) FROM factor_inputs fi "
                       "JOIN factor_history fh ON fh.ticker=fi.ticker "
                       "AND fh.cycle_id=fi.cycle_id "
                       "WHERE fi.cycle_id=? AND fi.missing=1 "
                       "AND fh.raw_inputs_available=0", (cycle,))
        out["attribution"] = {
            "incomplete": incomplete,
            "explained_by_a_missing_input": explained,
            "no_inputs_at_all": no_rows,
            "unexplained": incomplete - explained - no_rows,
            "by_factor_not_mutually_exclusive": attribution,
        }

        # Peers and articles are the two inputs that legitimately do not exist
        # for every stock, so their coverage bounds what is achievable.
        out["evidence_sources"] = {
            "stocks_with_peers": _q(conn, "SELECT COUNT(DISTINCT ticker) FROM "
                                          "factor_input_peers WHERE cycle_id=?",
                                    (cycle,)),
            "stocks_with_articles": _q(conn, "SELECT COUNT(DISTINCT ticker) FROM "
                                             "factor_input_articles WHERE cycle_id=?",
                                       (cycle,)),
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass

    defects = sum(v["capture_failure"] + v["scoring_mismatch"]
                  for v in out["factors"].values())
    out["defects_found"] = defects
    out["verdict"] = ("CLEAN" if defects == 0
                      and out["attribution"]["unexplained"] == 0 else "DEFECT")
    out["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
    out["dialect"] = "postgres" if IS_POSTGRES else "sqlite"
    return out


def report(cycle: str) -> dict:
    """Public entry point. Returns its own failure instead of raising one."""
    try:
        return analyze(cycle)
    except Exception as e:
        import traceback
        return {"available": False, "cycle": cycle,
                "reason": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[-1500:]}
