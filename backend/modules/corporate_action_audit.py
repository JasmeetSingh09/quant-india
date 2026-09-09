"""
corporate_action_audit.py — what the 12,778 unparsed actions actually are.

The Step 3 audit found that 12,778 of 32,964 corporate actions (38.8%) carry
`parsed = 0`. That number has been sitting in the report as an open risk, and
the first job here is to stop it being read as "12,778 defects".

What `parsed = 0` actually means
--------------------------------
`corporate_actions.parse_subject()` returns a list of price-affecting events
found in the subject line. When it returns nothing, `store()` writes the row
with `kind = 'other'` and `parsed = 0` -- deliberately, because "we did not
recognise this line" and "this line does nothing to the price" are different
claims and the code refuses to conflate them.

So an Annual General Meeting is unparsed AND inert. That is the parser working.
A 1:2 bonus written in a format the regex misses would be unparsed AND
price-affecting. That is a defect. Both land in the same 12,778, and the whole
point of this module is to separate them.

The raw `subject` text is stored (400 chars), which is what makes the separation
possible at all: the evidence needed to reclassify these rows is already in the
database and no refetch is required.

Read-only. Nothing here writes, repairs, reparses into storage, or recalculates
a score.
"""

import re
import time

try:
    from db import get_conn, IS_POSTGRES
except Exception:                                   # pragma: no cover
    from .db import get_conn, IS_POSTGRES


def _ph():
    return "%s" if IS_POSTGRES else "?"


# ---------------------------------------------------------------- taxonomy
#
# Ordered. The first bucket that matches wins, so the price-affecting tests are
# asked BEFORE the inert ones -- "AGM / Dividend Rs 2" is a dividend that also
# mentions a meeting, not a meeting.

_MONEY = r"(?:r[se]\.?|inr)\s*[0-9]"

BUCKETS = [
    # --- potentially price-affecting, and the parser missed it --------------
    ("split", re.compile(r"\bsplit|sub-?divis|face\s*value", re.I)),
    ("bonus", re.compile(r"\bbonus\b", re.I)),
    ("dividend", re.compile(r"\bdividend\b", re.I)),
    ("consolidation", re.compile(r"consolidat|reverse\s*split", re.I)),
    ("demerger", re.compile(r"demerg|de-merg|spin-?off|scheme\s+of\s+arrange", re.I)),
    ("rights", re.compile(r"\brights?\s+(issue|entitle)", re.I)),
    ("buyback", re.compile(r"buy-?back", re.I)),
    ("capital_reduction", re.compile(r"reduction\s+of\s+capital|capital\s+reduction", re.I)),
    ("amalgamation", re.compile(r"amalgamat|merger\b", re.I)),
    # --- inert by nature ----------------------------------------------------
    ("meeting", re.compile(
        r"annual\s+general|extra-?ordinary\s+general|\bagm\b|\begm\b|"
        r"board\s+meeting|postal\s+ballot|e-?voting|court\s+convened", re.I)),
    ("listing_admin", re.compile(
        r"change\s+in\s+name|name\s+change|symbol\s+change|"
        r"change\s+of\s+(?:name|face)|sub-?division\s+of\s+shares|"
        r"record\s+date|book\s+closure|suspension|delisting|"
        r"revocation|shifting|transfer\s+to", re.I)),
    ("interest_debt", re.compile(
        r"interest\s+payment|redemption|debenture|\bncd\b|coupon", re.I)),
]

# Buckets whose members could move a price and therefore need explanation.
PRICE_AFFECTING = {"split", "bonus", "dividend", "consolidation", "demerger",
                   "rights", "buyback", "capital_reduction", "amalgamation"}

# Of those, the ones the current multiplier model can actually express.
MODELLED = {"split", "bonus", "dividend"}

_RATIO = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*:\s*([0-9]+(?:\.[0-9]+)?)")
_AMOUNT = re.compile(_MONEY + r"*(?:[0-9]+(?:\.[0-9]+)?)", re.I)
_FV = re.compile(r"from\s+r[se]\.?\s*([0-9]+(?:\.[0-9]+)?)\s*.*?to\s+r[se]\.?\s*"
                 r"([0-9]+(?:\.[0-9]+)?)", re.I)


def classify(subject: str) -> str:
    s = (subject or "").strip()
    if not s:
        return "empty_subject"
    for name, rx in BUCKETS:
        if rx.search(s):
            return name
    return "unrecognised"


def reconstructible(bucket: str, subject: str):
    """
    Could a multiplier be recovered from the text that is already stored?

    Returns (bool, why). This is the difference between "the feed never told us"
    and "the feed told us and the regex did not listen" -- the second is a
    parser defect and is fixable without fetching anything.
    """
    s = subject or ""
    if bucket not in MODELLED:
        return False, f"{bucket} is not expressible as a single price multiplier"
    if bucket == "split":
        if _FV.search(s):
            return True, "face values present ('from Rs X to Rs Y')"
        if _RATIO.search(s):
            return True, "a ratio is present"
        return False, "no face values and no ratio in the text"
    if bucket == "bonus":
        if _RATIO.search(s):
            return True, "a ratio is present"
        return False, "no ratio in the text"
    if bucket == "dividend":
        if re.search(_MONEY, s, re.I):
            return True, "an amount is present"
        return False, "no amount in the text"
    return False, "unknown"


def taxonomy(sample_per_bucket: int = 6, max_rows: int = 40000) -> dict:
    """
    Characterise the whole unparsed population from the stored subject text.

    Every count here is accompanied by what it was drawn from, and the sample
    subjects are real strings from production so the classification can be
    checked rather than trusted.
    """
    ph = _ph()
    conn = get_conn()
    t0 = time.time()
    try:
        tot = conn.execute("SELECT COUNT(*) FROM corporate_actions").fetchone()[0]
        unp = conn.execute(
            "SELECT COUNT(*) FROM corporate_actions WHERE parsed = 0").fetchone()[0]
        rows = conn.execute(
            "SELECT isin, ex_date, subject FROM corporate_actions "
            f"WHERE parsed = 0 ORDER BY ex_date LIMIT {int(max_rows)}").fetchall()

        # Price coverage per ISIN, so an action outside the archive can be told
        # apart from one sitting on top of real observations.
        cover = {}
        for isin, lo, hi in conn.execute(
                "SELECT isin, MIN(day), MAX(day) FROM bhavcopy_eod "
                "WHERE isin IS NOT NULL GROUP BY isin").fetchall():
            cover[str(isin)] = (str(lo)[:10], str(hi)[:10])

        # Which (isin, ex_date) already carry a PARSED action -- an unparsed row
        # beside a parsed one for the same event is redundant, not missing.
        parsed_events = set()
        for isin, ex in conn.execute(
                "SELECT DISTINCT isin, ex_date FROM corporate_actions "
                "WHERE parsed = 1").fetchall():
            parsed_events.add((str(isin), str(ex)[:10]))
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"audit": "corporate_action_taxonomy", "status": "UNMEASURED",
                "reason": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()

    buckets = {}
    samples = {}
    n_price = n_inert = 0
    recon_yes = recon_no = 0
    redundant = 0
    outside = 0
    in_coverage_price_affecting = []

    for isin, ex, subject in rows:
        isin = str(isin)
        ex = str(ex)[:10]
        b = classify(subject)
        d = buckets.setdefault(b, {"n": 0, "price_affecting": b in PRICE_AFFECTING,
                                   "modelled": b in MODELLED,
                                   "reconstructible": 0, "not_reconstructible": 0,
                                   "redundant_with_parsed": 0,
                                   "outside_price_coverage": 0,
                                   "inside_price_coverage": 0})
        d["n"] += 1
        samples.setdefault(b, [])
        if len(samples[b]) < sample_per_bucket and subject:
            samples[b].append(str(subject)[:150])

        if b in PRICE_AFFECTING:
            n_price += 1
        else:
            n_inert += 1

        dup = (isin, ex) in parsed_events
        if dup:
            d["redundant_with_parsed"] += 1
            redundant += 1

        lo_hi = cover.get(isin)
        inside = bool(lo_hi and lo_hi[0] <= ex <= lo_hi[1])
        if inside:
            d["inside_price_coverage"] += 1
        else:
            d["outside_price_coverage"] += 1
            outside += 1

        if b in PRICE_AFFECTING:
            ok, why = reconstructible(b, subject)
            if ok:
                d["reconstructible"] += 1
                recon_yes += 1
            else:
                d["not_reconstructible"] += 1
                recon_no += 1
            # The population that actually matters: price-affecting, not
            # already covered by a parsed row, and sitting on real prices.
            if inside and not dup:
                in_coverage_price_affecting.append(
                    {"isin": isin, "ex_date": ex, "bucket": b,
                     "reconstructible": ok, "why": why,
                     "subject": str(subject)[:120]})

    ordered = dict(sorted(buckets.items(), key=lambda kv: -kv[1]["n"]))
    return {
        "audit": "corporate_action_taxonomy",
        "read_only": True,
        "seconds": round(time.time() - t0, 1),
        "examined": {
            "corporate_actions_total": tot,
            "unparsed_total": unp,
            "unparsed_rows_read": len(rows),
            "complete": len(rows) >= unp,
            "isins_with_price_coverage": len(cover),
        },
        "headline": {
            "price_affecting_bucket": n_price,
            "inert_bucket": n_inert,
            "reconstructible_from_stored_text": recon_yes,
            "not_reconstructible": recon_no,
            "redundant_with_an_already_parsed_action": redundant,
            "outside_price_coverage": outside,
            "price_affecting_inside_coverage_and_not_redundant":
                len(in_coverage_price_affecting),
        },
        "by_bucket": ordered,
        "sample_subjects": samples,
        "candidates": in_coverage_price_affecting[:80],
        "note": ("parsed = 0 means the subject line was not recognised, NOT "
                 "that the action is inert. A meeting is unparsed and harmless; "
                 "a bonus in an unexpected format is unparsed and a defect. "
                 "Both are in the 12,778 and this splits them apart."),
    }


# ------------------------------------------------------- specific events

def _actions_for(conn, isin, lo, hi):
    ph = _ph()
    out = []
    for r in conn.execute(
        "SELECT isin, ex_date, kind, num, den, amount, parsed, subject "
        f"FROM corporate_actions WHERE isin = {ph} AND ex_date >= {ph} "
        f"AND ex_date <= {ph} ORDER BY ex_date", (isin, lo, hi)).fetchall():
        out.append({"isin": str(r[0]), "ex_date": str(r[1])[:10], "kind": r[2],
                    "num": r[3], "den": r[4], "amount": r[5],
                    "parsed": int(r[6] or 0), "subject": str(r[7] or "")[:200]})
    return out


def event_reconstruction(symbol: str, ex_date: str, window_days: int = 20) -> dict:
    """
    Take one event apart: every action on record near it, parsed or not, the
    prices either side, and the multiplier the prices themselves imply.

    The implied multiplier is the evidence that does not depend on the feed.
    If the recorded multipliers multiply to the implied one, the record is
    complete; if they fall short by a clean factor, something is missing and
    the shortfall says what.
    """
    from datetime import date as _date
    ph = _ph()
    conn = get_conn()
    t0 = time.time()
    try:
        base = _date.fromisoformat(ex_date)
        lo = (base - __import__("datetime").timedelta(days=window_days)).isoformat()
        hi = (base + __import__("datetime").timedelta(days=window_days)).isoformat()

        isins = [str(r[0]) for r in conn.execute(
            "SELECT DISTINCT isin FROM bhavcopy_eod "
            f"WHERE symbol = {ph} AND isin IS NOT NULL", (symbol,)).fetchall()]

        acts = []
        for i in isins:
            acts.extend(_actions_for(conn, i, lo, hi))
        acts.sort(key=lambda a: (a["ex_date"], a["kind"]))

        pre = conn.execute(
            "SELECT day, close FROM bhavcopy_eod "
            f"WHERE symbol = {ph} AND day < {ph} AND close > 0 "
            "ORDER BY day DESC LIMIT 1", (symbol, ex_date)).fetchone()
        post = conn.execute(
            "SELECT day, close FROM bhavcopy_eod "
            f"WHERE symbol = {ph} AND day >= {ph} AND close > 0 "
            "ORDER BY day ASC LIMIT 1", (symbol, ex_date)).fetchone()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"audit": "event_reconstruction", "status": "UNMEASURED",
                "reason": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()

    pre_d = {"day": str(pre[0])[:10], "close": float(pre[1])} if pre else None
    post_d = {"day": str(post[0])[:10], "close": float(post[1])} if post else None
    implied = None
    if pre_d and post_d and pre_d["close"]:
        implied = round(post_d["close"] / pre_d["close"], 6)

    import corporate_actions as CA
    recorded = 1.0
    applied = []
    for a in acts:
        if a["ex_date"] != ex_date or not a["parsed"]:
            continue
        try:
            m = CA.price_multiplier({"kind": a["kind"], "num": a["num"],
                                     "den": a["den"], "amount": a["amount"]},
                                    prev_close=(pre_d or {}).get("close"))
        except Exception:
            m = None
        if m and abs(m - 1.0) > 1e-9:
            recorded *= m
            applied.append(dict(a, multiplier=round(m, 6)))

    shortfall = None
    verdict = "cannot determine"
    if implied and recorded:
        shortfall = round(recorded / implied, 4)
        # A shortfall near 1 means the record explains the move. A clean
        # integer or simple fraction means a whole action is missing.
        if 0.9 <= shortfall <= 1.1:
            verdict = "record explains the move"
        else:
            near = None
            for cand, name in ((2.0, "a further halving (1:1 bonus, or 10->5 split)"),
                               (5.0, "a further 5x (10->2 split)"),
                               (10.0, "a further 10x (10->1 split)"),
                               (1.5, "a 1:2 bonus"),
                               (4.0, "a further 4x"),
                               (3.0, "a further 3x")):
                if abs(shortfall - cand) / cand < 0.06:
                    near = name
                    break
            verdict = (f"record falls short by a factor of {shortfall}"
                       + (f" -- consistent with {near}" if near else ""))

    # Was anything unparsed sitting on the very same date?
    unparsed_same_day = [a for a in acts
                         if a["ex_date"] == ex_date and not a["parsed"]]

    return {
        "audit": "event_reconstruction",
        "read_only": True,
        "symbol": symbol,
        "ex_date": ex_date,
        "seconds": round(time.time() - t0, 1),
        "isins_for_symbol": isins,
        "actions_in_window": acts,
        "actions_applied_at_ex_date": applied,
        "unparsed_actions_on_the_ex_date": unparsed_same_day,
        "last_close_before_ex": pre_d,
        "first_close_on_or_after_ex": post_d,
        "implied_multiplier_from_prices": implied,
        "recorded_multiplier": round(recorded, 6),
        "recorded_over_implied": shortfall,
        "verdict": verdict,
        "note": ("The implied multiplier comes from the prices and owes nothing "
                 "to the feed. Where the recorded multipliers fall short of it "
                 "by a clean factor, an action is missing and the factor names "
                 "which kind."),
    }


def boundary_reconstruction(cases: list = None, window_days: int = 120) -> dict:
    """
    The three indeterminate transitions from Step 3B, examined against the raw
    subject text rather than the parsed flag.

    An E becomes an A/B/C/D only if the stored text actually settles it. Where
    it does not, it stays E.
    """
    cases = cases or [("MBECL.NS", "2024-09-27", "2026-09-01"),
                      ("DSKULKARNI.NS", "2018-03-20", "2026-08-03"),
                      ("EASTSILK.NS", "2024-03-06", "2025-08-18")]
    from datetime import date as _date, timedelta as _td
    ph = _ph()
    conn = get_conn()
    t0 = time.time()
    out = []
    try:
        for sym, last_a, first_b in cases:
            lo = (_date.fromisoformat(last_a) - _td(days=window_days)).isoformat()
            hi = (_date.fromisoformat(first_b) + _td(days=window_days)).isoformat()
            isins = [str(r[0]) for r in conn.execute(
                "SELECT DISTINCT isin FROM bhavcopy_eod "
                f"WHERE symbol = {ph} AND isin IS NOT NULL", (sym,)).fetchall()]
            acts = []
            for i in isins:
                acts.extend(_actions_for(conn, i, lo, hi))
            acts.sort(key=lambda a: a["ex_date"])

            unparsed = [a for a in acts if not a["parsed"]]
            buckets = {}
            for a in unparsed:
                b = classify(a["subject"])
                buckets[b] = buckets.get(b, 0) + 1
            price_affecting = [a for a in unparsed
                               if classify(a["subject"]) in PRICE_AFFECTING]

            if price_affecting:
                recon = [reconstructible(classify(a["subject"]), a["subject"])[0]
                         for a in price_affecting]
                verdict = "B" if any(recon) else "E"
                why = ("the unparsed action near the boundary IS price-affecting "
                       "and its multiplier is recoverable from the stored text"
                       if any(recon) else
                       "the unparsed action may be price-affecting but the "
                       "stored text does not carry enough to reconstruct it")
            elif unparsed:
                verdict = "D"
                why = ("every unparsed action near the boundary is inert by "
                       "nature (" + ", ".join(sorted(buckets)) + "), so nothing "
                       "needs adjusting across it")
            else:
                verdict = "D"
                why = "no unparsed action near the boundary at all"

            out.append({
                "symbol": sym,
                "boundary": {"last_day_isin_a": last_a, "first_day_isin_b": first_b},
                "actions_in_window": len(acts),
                "unparsed_in_window": len(unparsed),
                "unparsed_buckets": buckets,
                "price_affecting_unparsed": [
                    {"ex_date": a["ex_date"], "subject": a["subject"][:140]}
                    for a in price_affecting][:6],
                "sample_unparsed_subjects": [a["subject"][:110]
                                             for a in unparsed[:6]],
                "revised_verdict": verdict,
                "why": why,
            })
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"audit": "boundary_reconstruction", "status": "UNMEASURED",
                "reason": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()

    return {"audit": "boundary_reconstruction", "read_only": True,
            "seconds": round(time.time() - t0, 1), "cases": out,
            "note": ("An E is revised only where the stored text settles it. "
                     "Where it does not, E stands.")}
