"""
integrity.py — make the prediction history tamper-evident.

The track record is the one asset here that cannot be rebuilt. Anyone can clone
nine optimisers in a month; nobody can clone two years of timestamped public
predictions scored honestly. Its whole value rests on the claim that yesterday's
call is still exactly what was recorded yesterday — including the ones that were
wrong. A single quiet edit, whether from a bug, a bad migration, or a temptation
to improve a bad week, destroys that permanently and silently.

So: a hash chain over the daily snapshots. Each day's seal covers that day's
rows AND the previous day's seal, which means altering an old prediction breaks
every seal after it, not just its own. Verification recomputes the whole chain
from the raw rows and reports the first day that disagrees.

This detects tampering; it does not prevent it — anyone with database access can
rewrite both a row and its seal. Preventing that needs an append-only store or
publishing the seals somewhere you do not control. Detection is the honest first
step, and it is what makes "we never edit history" a checkable claim rather than
a promise.
"""

import hashlib
from datetime import datetime

from db import get_conn, IS_POSTGRES

GENESIS = "0" * 64


def _init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prediction_seals (
            day        TEXT PRIMARY KEY,
            row_count  INTEGER NOT NULL,
            day_hash   TEXT NOT NULL,
            prev_hash  TEXT NOT NULL,
            sealed_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _day_rows(conn, day: str):
    """The immutable content of one day, in a fixed order so the hash is stable."""
    return conn.execute(
        "SELECT ticker, alpha_score, signal, price_at_snapshot "
        "FROM predictions WHERE snapshot_date = ? ORDER BY ticker", (day,)
    ).fetchall()


def _hash_day(day: str, rows, prev_hash: str) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode())
    h.update(day.encode())
    for ticker, alpha, signal, price in rows:
        # Fixed formatting: float repr differences would otherwise produce
        # spurious mismatches between machines or Python versions.
        h.update(f"{ticker}|{float(alpha or 0):.4f}|{signal or ''}|"
                 f"{float(price or 0):.4f}\n".encode())
    return h.hexdigest()


def seal(up_to: str = None) -> dict:
    """
    Seal every unsealed day. Idempotent: days already sealed are left alone,
    because re-sealing is exactly the operation that would launder a change.
    """
    _init_db()
    conn = get_conn()
    days = [r[0] for r in conn.execute(
        "SELECT DISTINCT snapshot_date FROM predictions ORDER BY snapshot_date"
    ).fetchall()]
    if up_to:
        days = [d for d in days if d <= up_to]
    sealed = {r[0]: r[1] for r in conn.execute(
        "SELECT day, day_hash FROM prediction_seals").fetchall()}

    prev = GENESIS
    new = []
    for d in days:
        if d in sealed:
            prev = sealed[d]
            continue
        rows = _day_rows(conn, d)
        dh = _hash_day(d, rows, prev)
        conn.execute(
            "INSERT INTO prediction_seals (day, row_count, day_hash, prev_hash, sealed_at) "
            "VALUES (?,?,?,?,?)",
            (d, len(rows), dh, prev, datetime.now().isoformat()))
        new.append({"day": d, "rows": len(rows)})
        prev = dh
    conn.commit()
    conn.close()
    return {"newly_sealed": new, "days_sealed_total": len(days),
            "head": prev,
            "note": "Sealed days are never re-sealed — that would launder a change."}


def verify() -> dict:
    """
    Recompute the chain from the raw rows and compare against the stored seals.
    Reports the FIRST day that disagrees, since everything after it is suspect
    by construction.
    """
    _init_db()
    conn = get_conn()
    seals = conn.execute(
        "SELECT day, row_count, day_hash, prev_hash FROM prediction_seals ORDER BY day"
    ).fetchall()
    if not seals:
        conn.close()
        return {"status": "unsealed", "sealed_days": 0,
                "detail": "No seals yet — run POST /predictions/seal to start the chain."}

    prev = GENESIS
    problems = []
    for day, count, stored, stored_prev in seals:
        rows = _day_rows(conn, day)
        recomputed = _hash_day(day, rows, prev)
        if stored_prev != prev:
            problems.append({"day": day, "issue": "chain break",
                             "detail": "this day's recorded predecessor is not the "
                                       "previous day's hash — a day was inserted, "
                                       "removed or resealed"})
        elif recomputed != stored:
            problems.append({"day": day, "issue": "content changed",
                             "detail": f"rows now: {len(rows)}, sealed with: {count}"
                                       if len(rows) != count else
                                       "same row count but different values"})
        if problems:
            break                      # everything after the first break is suspect
        prev = stored
    conn.close()

    ok = not problems
    return {
        "status": "intact" if ok else "TAMPERED",
        "sealed_days": len(seals),
        "first_day": seals[0][0], "last_day": seals[-1][0],
        "head": prev if ok else None,
        "problems": problems,
        "detail": ("Every sealed day still hashes to what was recorded. The track "
                   "record has not been edited." if ok else
                   "A sealed day no longer matches its seal. Treat the published "
                   "track record as unverified until this is explained."),
        "limitation": "Detects tampering; does not prevent it. Anyone with database "
                      "access could rewrite a row and its seal together.",
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
