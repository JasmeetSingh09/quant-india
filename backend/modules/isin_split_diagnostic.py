"""
isin_split_diagnostic.py — does a new ISIN break the corporate-action join?

One question, and nothing else:

    When a corporate action such as a stock split causes a new ISIN to be
    issued, does the adjustment layer still connect that action to the
    historical price observations that need adjusting?

Why the question exists
-----------------------
The Step 3 production audit found 549 symbols carrying more than one ISIN. That
is NOT ticker reuse: in India a face-value change mints a new ISIN for the same
company, so ASTRAL and AJANTPHARM holding three ISINs across fifteen years is
what a stock split looks like. But corporate actions are stored keyed by ISIN,
and price rows before the split carry the OLD ISIN. If the action is filed under
the NEW one, a naive join would miss exactly the rows that need correcting --
and momentum computed across the split would be wrong while looking fine.

What this does NOT do
---------------------
It does not change the adjustment layer, recompute a score, or write anything.
Every statement here is a SELECT. It reproduces the resolver and the join the
way `pit_validation._apply_adjustment` performs them, and reports what it finds.

Classification, per transition
------------------------------
    A  correctly linked       the action reaches the pre-transition prices
    B  action exists, unlinked the action is on record but cannot reach them
    C  linked to wrong security the resolver merged identities it should not have
    D  no adjustment required  no price-affecting action at the transition
    E  unable to determine     not enough information to say

D is a real answer, not a shrug: an ISIN can change for reasons that do not
move the price, and calling that a defect would be wrong.
"""

import time

try:
    from db import get_conn, IS_POSTGRES
except Exception:                                   # pragma: no cover
    from .db import get_conn, IS_POSTGRES


def _ph():
    return "%s" if IS_POSTGRES else "?"


def _d(s):
    from datetime import date
    return date.fromisoformat(str(s)[:10])


def diagnose(symbols: list = None, max_symbols: int = 12,
             window_days: int = 30) -> dict:
    """
    Walk real multi-ISIN symbols and report, per ISIN transition, whether the
    corporate action that caused it can reach the prices it must correct.
    """
    from security_identity import (_pairs, _resolve_pairs,
                                   LINK_MAX_GAP_DAYS, LINK_MAX_OVERLAP_DAYS)
    import corporate_actions as CA

    conn = get_conn()
    t0 = time.time()
    ph = _ph()
    try:
        # The resolver, run exactly as the validation runs it.
        pair_rows = _pairs(conn)
        canonical, components, links, ambiguous = _resolve_pairs(pair_rows)

        # Every (isin, symbol, first, last) grouped by symbol.
        by_symbol = {}
        for isin, sym, first, last, days in pair_rows:
            by_symbol.setdefault(sym, []).append(
                {"isin": isin, "first": str(first)[:10], "last": str(last)[:10],
                 "days": int(days or 0)})

        multi = {s: sorted(v, key=lambda e: e["first"])
                 for s, v in by_symbol.items() if len(v) > 1}

        # Prefer the symbols the audit named, then fill up with others so the
        # sample is not only the ones already looked at.
        wanted = []
        for s in (symbols or []):
            s = s.upper()
            for cand in (s, f"{s}.NS"):
                if cand in multi and cand not in wanted:
                    wanted.append(cand)
        for s in sorted(multi):
            if len(wanted) >= max_symbols:
                break
            if s not in wanted:
                wanted.append(s)
        wanted = wanted[:max_symbols]

        cases = []
        counts = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}

        for sym in wanted:
            entries = multi[sym]
            for prev, nxt in zip(entries, entries[1:]):
                old_isin, new_isin = prev["isin"], nxt["isin"]
                gap = (_d(nxt["first"]) - _d(prev["last"])).days
                merged = canonical.get(old_isin) == canonical.get(new_isin)

                # Actions on EITHER ISIN near the transition.
                #
                # min/max rather than (prev.last, nxt.first) in order: when the
                # two ISINs overlap in time, prev.last falls AFTER nxt.first and
                # the window inverts, silently finding no actions and reporting
                # "no adjustment required" for a case that was never searched.
                _a = _d(prev["last"]).toordinal()
                _b = _d(nxt["first"]).toordinal()
                lo = min(_a, _b) - window_days
                hi = max(_a, _b) + window_days
                from datetime import date as _date
                lo_s = _date.fromordinal(lo).isoformat()
                hi_s = _date.fromordinal(hi).isoformat()
                acts = []
                try:
                    for r in conn.execute(
                        "SELECT isin, ex_date, kind, num, den, amount, parsed "
                        f"FROM corporate_actions WHERE isin IN ({ph}, {ph}) "
                        f"AND ex_date >= {ph} AND ex_date <= {ph} "
                        "ORDER BY ex_date",
                            (old_isin, new_isin, lo_s, hi_s)).fetchall():
                        acts.append({"isin": r[0], "ex_date": str(r[1])[:10],
                                     "kind": r[2], "num": r[3], "den": r[4],
                                     "amount": r[5], "parsed": int(r[6] or 0)})
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    acts = None

                # The prices either side of the transition.
                last_pre = first_post = None
                try:
                    r = conn.execute(
                        "SELECT day, close FROM bhavcopy_eod "
                        f"WHERE symbol = {ph} AND isin = {ph} "
                        "ORDER BY day DESC LIMIT 1",
                        (sym, old_isin)).fetchone()
                    if r:
                        last_pre = {"day": str(r[0])[:10], "close": float(r[1])}
                    r = conn.execute(
                        "SELECT day, close FROM bhavcopy_eod "
                        f"WHERE symbol = {ph} AND isin = {ph} "
                        "ORDER BY day ASC LIMIT 1",
                        (sym, new_isin)).fetchone()
                    if r:
                        first_post = {"day": str(r[0])[:10], "close": float(r[1])}
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass

                raw_ret = None
                if last_pre and first_post and last_pre["close"]:
                    raw_ret = round(100.0 * (first_post["close"] - last_pre["close"])
                                    / last_pre["close"], 2)

                # The multiplier the adjustment layer would compute, and whether
                # the join reaches the pre-transition rows.
                mult = None
                price_affecting = []
                if acts:
                    for a in acts:
                        if a["kind"] not in ("split", "bonus", "dividend"):
                            continue
                        if not a["parsed"]:
                            continue
                        try:
                            m = CA.price_multiplier(
                                {"kind": a["kind"], "num": a["num"],
                                 "den": a["den"], "amount": a["amount"]},
                                prev_close=(last_pre or {}).get("close"))
                        except Exception:
                            m = None
                        if m and abs(m - 1.0) > 1e-9:
                            price_affecting.append(dict(a, multiplier=round(m, 6)))
                    if price_affecting:
                        mult = 1.0
                        for a in price_affecting:
                            mult *= a["multiplier"]

                # adjusted(t) = close(t) * PROD(m for ex_date > t).
                #
                # STRICTLY greater. If the last observation under the old ISIN
                # falls ON or AFTER the ex-date, that price already trades at
                # the post-action level and multiplying it again would invent a
                # discontinuity where none exists. Production gets this right
                # via bisect_left, which applies the factor only to columns
                # before the ex-date; an earlier version of this diagnostic did
                # not, and reported +99.71% for AJANTPHARM on a boundary whose
                # raw return was -0.15% -- that is to say, on a series that was
                # already perfectly continuous.
                # ANCHOR ON THE EX-DATE, NOT ON THE ISIN TRANSITION.
                #
                # They are not the same day and assuming they were produced two
                # wrong numbers here already. AHCL changed ISIN on 2026-04-23
                # while its split and bonus went ex on 2026-04-24, so the
                # ISIN-boundary pair straddles no action at all -- its raw
                # return is -0.42%, and applying the multiplier to it invented
                # +895%. The pair that actually straddles the event is
                # (last close strictly before ex_date, first close on/after it).
                ex_ret = {}
                if price_affecting:
                    ex = min(a["ex_date"] for a in price_affecting)
                    m_ex = 1.0
                    for a in price_affecting:
                        if a["ex_date"] == ex:
                            m_ex *= a["multiplier"]
                    pre = post = None
                    try:
                        r = conn.execute(
                            "SELECT day, close FROM bhavcopy_eod "
                            f"WHERE symbol = {ph} AND day < {ph} AND close > 0 "
                            "ORDER BY day DESC LIMIT 1", (sym, ex)).fetchone()
                        if r:
                            pre = {"day": str(r[0])[:10], "close": float(r[1])}
                        r = conn.execute(
                            "SELECT day, close FROM bhavcopy_eod "
                            f"WHERE symbol = {ph} AND day >= {ph} AND close > 0 "
                            "ORDER BY day ASC LIMIT 1", (sym, ex)).fetchone()
                        if r:
                            post = {"day": str(r[0])[:10], "close": float(r[1])}
                    except Exception:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                    if pre and post and pre["close"]:
                        rr = 100.0 * (post["close"] - pre["close"]) / pre["close"]
                        aa = (100.0 * (post["close"] - pre["close"] * m_ex)
                              / (pre["close"] * m_ex))
                        ex_ret = {
                            "ex_date": ex,
                            "multiplier_at_ex_date": round(m_ex, 6),
                            "last_close_before_ex": pre,
                            "first_close_on_or_after_ex": post,
                            "raw_return_pct": round(rr, 2),
                            "adjusted_return_pct": round(aa, 2),
                        }

                mult_at_boundary = None
                adj_ret = None

                # --- classify -------------------------------------------------
                if acts is None:
                    verdict, why = "E", "corporate_actions unreadable"
                elif not price_affecting:
                    unparsed = [a for a in (acts or []) if not a["parsed"]]
                    if unparsed:
                        verdict = "E"
                        why = (f"{len(unparsed)} action(s) at the transition are "
                               f"stored but unparsed, so whether an adjustment "
                               f"was required cannot be determined")
                    else:
                        verdict = "D"
                        why = ("no price-affecting action at this transition; an "
                               "ISIN can change without the price moving")
                elif merged:
                    verdict = "A"
                    why = ("the resolver merged both ISINs into one identity, so "
                           "the action is mapped onto the same canonical key as "
                           "the pre-transition prices and reaches them")
                else:
                    verdict = "B"
                    why = (f"a price-affecting action exists but the resolver did "
                           f"NOT merge these ISINs (gap {gap}d vs limit "
                           f"{LINK_MAX_GAP_DAYS}d), so the action cannot reach "
                           f"the pre-transition prices")

                # C: the resolver merged identities that overlapped in time,
                # which would mean two live securities were joined.
                if merged and gap < -LINK_MAX_OVERLAP_DAYS:
                    verdict = "C"
                    why = (f"both ISINs traded simultaneously for {-gap} days yet "
                           f"were merged -- the action may be applied to the "
                           f"wrong security")

                counts[verdict] += 1
                cases.append({
                    "symbol": sym,
                    "old_isin": old_isin, "new_isin": new_isin,
                    "old_last_seen": prev["last"], "new_first_seen": nxt["first"],
                    "gap_days": gap,
                    "resolver_merged": merged,
                    "canonical_old": canonical.get(old_isin),
                    "canonical_new": canonical.get(new_isin),
                    "actions_near_transition": acts,
                    "price_affecting_actions": price_affecting,
                    "combined_multiplier": mult,
                    "across_the_ex_date": ex_ret or None,
                    "multiplier_applying_at_this_boundary": mult_at_boundary,
                    "boundary_note": (
                        "returns are measured across the EX-DATE, which is "
                        "not always the day the ISIN changed"
                        if price_affecting else None),
                    "last_pre_action_observation": last_pre,
                    "first_post_action_observation": first_post,
                    "isin_boundary_raw_return_pct": raw_ret,
                    "raw_return_pct": (ex_ret or {}).get("raw_return_pct"),
                    "adjusted_return_pct": (ex_ret or {}).get("adjusted_return_pct"),
                    "verdict": verdict,
                    "why": why,
                })
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"diagnostic": "isin_split_linkage", "status": "UNMEASURED",
                "reason": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()

    total = sum(counts.values())
    return {
        "diagnostic": "isin_split_linkage",
        "question": ("When a corporate action mints a new ISIN, does the "
                     "adjustment layer still reach the prices that need "
                     "correcting?"),
        "read_only": True,
        "seconds": round(time.time() - t0, 1),
        "examined": {
            "symbols_with_multiple_isins_in_archive": len(multi),
            "symbols_examined": len(wanted),
            "isin_transitions_examined": total,
            "resolver_links_total": len(links),
            "resolver_ambiguous_total": len(ambiguous),
            "link_window": f"gap in [-{LINK_MAX_OVERLAP_DAYS}, {LINK_MAX_GAP_DAYS}] days",
        },
        "classification": {
            "A_correctly_linked": counts["A"],
            "B_action_exists_but_unlinked": counts["B"],
            "C_linked_to_wrong_security": counts["C"],
            "D_no_adjustment_required": counts["D"],
            "E_unable_to_determine": counts["E"],
        },
        "symbols_examined": wanted,
        "cases": cases,
        "note": ("A new ISIN does not mean a new company, and an old->new "
                 "transition is not automatically an error. D and E are real "
                 "answers, not failures to look."),
    }


# ------------------------------------------------ the resolver's refusals

def _issuer(isin: str):
    """
    The issuing company, read from the ISIN itself.

    An Indian ISIN is IN | E/F/9 | 4-char company code | security-line digits |
    check digit. Characters 0-6 therefore name the ISSUER and the tail names the
    line: INE927D01010 and INE927D01028 are two securities of one company.

    This is evidence about identity that depends on neither the resolver nor a
    company-name lookup -- which matters here, because the production universe
    table is empty and cannot supply a name at all.
    """
    s = str(isin or "").strip().upper()
    return s[:7] if len(s) >= 12 and s.startswith("IN") else None


def ambiguous_transitions(window_days: int = 120) -> dict:
    """
    Every transition the resolver REFUSED to link, examined one by one.

    This is the population where a B-type failure can hide. Wherever the
    resolver merged, an action filed under either ISIN reaches the prices --
    that was Step 3A's result. Where it declined, an action on one side cannot
    reach prices on the other, by construction. So these cases decide whether
    "0 unlinked" survives contact with the rest of the archive.

    The classification asks whether the two identities are the same economic
    security, on evidence:

        A  same security and correctly linkable
        B  an action exists and is genuinely unlinked
        C  evidence points to a DIFFERENT security; linking would be wrong
        D  no adjustment required either way
        E  genuinely indeterminate

    E is not a failure to look. Forcing a merge to make E disappear would
    manufacture a continuous history across an identity boundary the evidence
    does not support, which is the one thing this project has refused to do
    throughout.
    """
    from security_identity import (_pairs, _resolve_pairs,
                                   LINK_MAX_GAP_DAYS, LINK_MAX_OVERLAP_DAYS)
    import corporate_actions as CA
    from datetime import date as _date

    conn = get_conn()
    t0 = time.time()
    ph = _ph()
    try:
        pair_rows = _pairs(conn)
        canonical, components, links, ambiguous = _resolve_pairs(pair_rows)

        ranges = {}
        for isin, sym, first, last, days in pair_rows:
            ranges[(sym, isin)] = {"first": str(first)[:10],
                                   "last": str(last)[:10],
                                   "days": int(days or 0)}

        out, counts = [], {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
        for amb in ambiguous:
            sym = amb["symbol"]
            a, b = amb["isin_a"], amb["isin_b"]
            ra = ranges.get((sym, a), {})
            rb = ranges.get((sym, b), {})
            same_issuer = (_issuer(a) is not None and _issuer(a) == _issuer(b))

            # Corporate actions on either ISIN, over a wide window -- wider than
            # the linked case, because this boundary is by definition not tight.
            acts = []
            try:
                lo = _d(min(ra.get("last", "9999-12-31"),
                            rb.get("first", "9999-12-31"))).toordinal() - window_days
                hi = _d(max(ra.get("last", "0001-01-01"),
                            rb.get("first", "0001-01-01"))).toordinal() + window_days
                for r in conn.execute(
                    "SELECT isin, ex_date, kind, num, den, amount, parsed "
                    f"FROM corporate_actions WHERE isin IN ({ph}, {ph}) "
                    f"AND ex_date >= {ph} AND ex_date <= {ph} ORDER BY ex_date",
                        (a, b, _date.fromordinal(lo).isoformat(),
                         _date.fromordinal(hi).isoformat())).fetchall():
                    m = None
                    if int(r[6] or 0):
                        try:
                            m = CA.price_multiplier({"kind": r[2], "num": r[3],
                                                     "den": r[4], "amount": r[5]})
                        except Exception:
                            m = None
                    acts.append({"isin": r[0], "ex_date": str(r[1])[:10],
                                 "kind": r[2], "num": r[3], "den": r[4],
                                 "parsed": int(r[6] or 0),
                                 "multiplier": (round(m, 6) if m else None)})
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                acts = None

            # Price continuity across the boundary.
            last_a = first_b = None
            sel = ("SELECT day, close FROM bhavcopy_eod WHERE symbol = {p} "
                   "AND isin = {p} AND close > 0 ORDER BY day ").replace("{p}", ph)
            try:
                r = conn.execute(sel + "DESC LIMIT 1", (sym, a)).fetchone()
                if r:
                    last_a = {"day": str(r[0])[:10], "close": float(r[1])}
                r = conn.execute(sel + "ASC LIMIT 1", (sym, b)).fetchone()
                if r:
                    first_b = {"day": str(r[0])[:10], "close": float(r[1])}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass

            ratio = None
            if last_a and first_b and last_a["close"]:
                ratio = round(first_b["close"] / last_a["close"], 4)

            price_affecting = [x for x in (acts or []) if x.get("multiplier")
                               and abs(x["multiplier"] - 1.0) > 1e-9]
            unparsed = [x for x in (acts or []) if not x["parsed"]]

            # ---- classify on evidence, and leave E as E ---------------------
            if acts is None:
                v = "E"
                why = "corporate_actions unreadable; nothing is claimed"
            elif not same_issuer:
                v = "C"
                why = (f"different issuers: {_issuer(a)} vs {_issuer(b)}. The "
                       f"ISIN itself says these are securities of two different "
                       f"companies sharing a recycled ticker, so linking them "
                       f"would splice two unrelated histories together.")
            elif price_affecting:
                v = "B"
                why = (f"same issuer ({_issuer(a)}) and a price-affecting action "
                       f"is on record, but the resolver declined to link "
                       f"({amb.get('reason')}), so that action cannot reach the "
                       f"prices on the other side of the boundary.")
            elif unparsed:
                v = "E"
                why = (f"same issuer ({_issuer(a)}), and {len(unparsed)} "
                       f"action(s) near the boundary are stored but unparsed, "
                       f"so whether an adjustment is required cannot be "
                       f"determined.")
            else:
                v = "D"
                why = (f"same issuer ({_issuer(a)}) and no price-affecting "
                       f"action on record at the boundary, so there is nothing "
                       f"to adjust across it.")

            counts[v] += 1
            out.append({
                "symbol": sym,
                "company_name": None,
                "company_name_note": ("unavailable: the production universe "
                                      "table (nse_stocks) is empty, which is a "
                                      "separately recorded defect"),
                "isin_a": a, "isin_b": b,
                "issuer_a": _issuer(a), "issuer_b": _issuer(b),
                "same_issuer": same_issuer,
                "isin_a_range": ra, "isin_b_range": rb,
                "gap_days": amb.get("gap_days"),
                "resolver_reason": amb.get("reason"),
                "actions_near_boundary": acts,
                "price_affecting_actions": price_affecting,
                "unparsed_actions": (len(unparsed) if acts is not None else None),
                "last_close_on_isin_a": last_a,
                "first_close_on_isin_b": first_b,
                "price_ratio_b_over_a": ratio,
                "verdict": v,
                "why": why,
            })
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"diagnostic": "resolver_ambiguous", "status": "UNMEASURED",
                "reason": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()

    return {
        "diagnostic": "resolver_ambiguous",
        "question": ("Where the resolver REFUSED to establish identity, is an "
                     "adjustment silently going missing?"),
        "read_only": True,
        "seconds": round(time.time() - t0, 1),
        "examined": {"ambiguous_transitions": len(out),
                     "resolver_links_total": len(links),
                     "link_window": f"gap in [-{LINK_MAX_OVERLAP_DAYS}, "
                                    f"{LINK_MAX_GAP_DAYS}] days"},
        "classification": {"A_same_security_linkable": counts["A"],
                           "B_action_exists_genuinely_unlinked": counts["B"],
                           "C_different_security": counts["C"],
                           "D_no_adjustment_required": counts["D"],
                           "E_indeterminate": counts["E"]},
        "cases": out,
        "note": ("The issuer is read from the ISIN itself (characters 0-6), "
                 "which is evidence independent of the resolver and of any "
                 "table this project maintains. E is left as E; no merge is "
                 "forced to make it disappear."),
    }
