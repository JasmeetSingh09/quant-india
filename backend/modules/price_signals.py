"""
price_signals.py — factor test 4: do two price signals add anything beyond momentum?

Rules: docs/PREREG_FACTOR_TEST4_PRICE_SIGNALS_2026-10-06.md (owner approval 2026-10-06,
committed in be7da02 before this file existed). This module implements that document and
nothing else. Everything mechanical is borrowed from pit_validation (factor test 1) so the
two tests cannot disagree about prices, identity, eligibility, forward returns, excess or
statistics:

  load_adjusted        closes corrected for splits, bonuses and dividends; ISIN identity joins
  _month_end_cols      formation dates
  _momentum_scores     the frozen 12-1 volatility-adjusted momentum, through tanh
  _mean_test           the mean of monthly spreads, tested across months
  -100%                for a security with no price at the end of the holding period

The two signals, computed at formation column `col` from columns at or before `col`:

  reversal   -(C[col] / C[col-21] - 1)              higher = bigger recent fall
  high52     C[col] / max(C[col-251 .. col])        higher = nearer the 52-week high,
                                                    needs at least 200 valid closes

The primary sort is momentum-neutral: within each month the eligible stocks are split
into 5 momentum groups, each momentum group into 5 signal groups, and signal group k is
the union of sub-group k across the momentum groups. The primary statistic is the mean,
across formation months, of group 5's excess return minus group 1's.
"""

import math

import numpy as np

import pit_validation as P

SIGNALS = ("reversal", "high52")
HORIZONS = P.HORIZONS                       # 1, 3, 6, 12 months
N_GROUPS = 5
MIN_ELIGIBLE = 100                          # at least 4 stocks per cell
REVERSAL_DAYS = 21
HIGH52_DAYS = 252
HIGH52_MIN_CLOSES = 200
N_PRIMARY = len(SIGNALS) * len(HORIZONS)    # 8
LEVEL = 0.05 / N_PRIMARY                    # 0.00625 with all 8 usable; the run uses 0.05 / (usable tests)


# ------------------------------------------------------------------ the signals

def reversal_scores(C, col):
    """Minus the last 21 trading days' return. NaN where either close is missing."""
    if col - REVERSAL_DAYS < 0:
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        r = C[:, col] / C[:, col - REVERSAL_DAYS] - 1.0
    s = -r.astype(np.float64)
    s[~np.isfinite(s)] = np.nan
    return s


def high52_scores(C, col):
    """Close over the highest close of the last 252 trading days (inclusive). NaN with
    fewer than 200 valid closes in the window."""
    a = col - (HIGH52_DAYS - 1)
    if a < 0:
        return None
    win = C[:, a:col + 1].astype(np.float64)
    valid = np.sum(np.isfinite(win), axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        hi = np.nanmax(np.where(np.isfinite(win), win, -np.inf), axis=1)
        s = C[:, col].astype(np.float64) / hi
    s[(valid < HIGH52_MIN_CLOSES) | ~np.isfinite(s) | (hi <= 0)] = np.nan
    return s


SIGNAL_FN = {"reversal": reversal_scores, "high52": high52_scores}

# Measured on synthetic prices before any real run (2026-10-06): when returns depend on
# momentum ONLY, with an effect as strong as the real one, the 52-week-high signal held
# momentum-neutral still showed t of about 1.0-2.5 (vs about 4.1-4.5 standalone), because
# five momentum groups control momentum coarsely. That is below the pass line (t about 2.9
# at p 0.00625), so momentum alone cannot pass the test, but a borderline high52 pass should
# be read with this in mind. The method is fixed by the prereg; this is reported, not changed.
KNOWN_LIMIT = ("Five momentum groups control momentum only coarsely. On synthetic prices where "
               "returns depend on momentum alone (as strongly as on real data), the 52-week-high "
               "signal held momentum-neutral still reached t of about 1.0-2.5 over 15 years, below "
               "the pass line of about 2.9. A pass well above that line is not explained by "
               "momentum leaking through; a borderline one for high52 should be read with caution.")


# ------------------------------------------------------------------ grouping

def _groups(values, n=N_GROUPS):
    """Group 0..n-1 by rank within the given values (stable), as pit_validation does."""
    order = np.argsort(values, kind="stable")
    lab = np.empty(len(values), dtype=np.int64)
    lab[order] = np.minimum(n - 1, np.arange(len(values)) * n // len(values))
    return lab


def neutral_groups(mom, sig, n=N_GROUPS):
    """Momentum-neutral signal groups: signal group k within each momentum group."""
    mg = _groups(mom, n)
    out = np.empty(len(sig), dtype=np.int64)
    for g in range(n):
        idx = np.where(mg == g)[0]
        if len(idx):
            out[idx] = _groups(sig[idx], n)
    return out


def _spearman(a, b):
    ra = np.argsort(np.argsort(a, kind="stable"), kind="stable").astype(float)
    rb = np.argsort(np.argsort(b, kind="stable"), kind="stable").astype(float)
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


# ------------------------------------------------------------------ the run on a matrix

def run_on_matrix(keys, days, C, V, min_turnover=P.MIN_MONTHLY_TURNOVER):
    """Everything after loading, so offline tests can run it on synthetic matrices."""
    me = P._month_end_cols(days)
    months = [m for m, _ in me]
    cols = [c for _, c in me]
    form_ix = P._formation_indices(cols, months)

    # per signal: monthly records {month: {"h": {...}}}
    rec = {s: {} for s in SIGNALS}
    corr = {s: [] for s in SIGNALS}
    market_1m = {}
    for i in form_ix:
        col = cols[i]
        mom = P._momentum_scores(C, col)
        if mom is None:
            continue
        px_now, liq = C[:, col], V[:, col]
        base = np.isfinite(px_now) & (px_now > 0) & np.isfinite(mom) & (liq >= min_turnover)
        fwd = {}
        for h in HORIZONS:
            j = i + h
            if j >= len(cols):
                continue
            with np.errstate(invalid="ignore", divide="ignore"):
                r = C[:, cols[j]] / px_now - 1.0
            fwd[h] = np.where(np.isfinite(r), r, -1.0)
        if 1 in fwd and base.sum():
            market_1m[months[i]] = float(np.mean(fwd[1][base]))
        for s in SIGNALS:
            sig = SIGNAL_FN[s](C, col)
            if sig is None:
                continue
            elig = base & np.isfinite(sig)
            idx = np.where(elig)[0]
            if len(idx) < MIN_ELIGIBLE:
                continue
            ng = neutral_groups(mom[idx], sig[idx])
            sg = _groups(sig[idx])
            c = _spearman(sig[idx], mom[idx])
            if c is not None:
                corr[s].append(c)
            liq_t = _groups(liq[idx].astype(float), 3)
            row = {"keys": idx, "ng": ng, "sg": sg, "liq_t": liq_t, "fwd": {}}
            for h, r in fwd.items():
                rr = r[idx]
                row["fwd"][h] = rr - rr.mean()           # excess vs the eligible universe that month
            rec[s][months[i]] = row

    # regimes from months BEFORE formation, as factor test 1
    ordered = [m for m in months if m in market_1m]
    regime_of = {}
    for pos, m in enumerate(ordered):
        if pos < 3:
            continue
        prior = [market_1m[x] for x in ordered[pos - 3:pos]]
        trend = (np.prod([1 + r for r in prior]) - 1) * 100
        ann = float(np.std(prior, ddof=1)) * math.sqrt(12)
        regime_of[m] = ("Bull" if trend > P.REGIME_TREND_PCT else "Bear" if trend < -P.REGIME_TREND_PCT else "Sideways",
                        "High volatility" if ann > P.REGIME_VOL_ANN else "Low volatility")

    results, primary = {}, []
    for s in SIGNALS:
        res = {"horizons": {}, "rank_correlation_with_momentum": {
            "months": len(corr[s]), "mean": round(float(np.mean(corr[s])), 3) if corr[s] else None}}
        ms = sorted(rec[s])
        half = ms[len(ms) // 2] if ms else None
        for h in HORIZONS:
            neutral, standalone, top_net, spread_net = [], [], [], []
            prev_top = prev_bot = None
            for k, m in enumerate(ms):
                row = rec[s][m]
                if h not in row["fwd"]:
                    continue
                e = row["fwd"][h]
                top, bot = row["ng"] == N_GROUPS - 1, row["ng"] == 0
                neutral.append((m, float(e[top].mean() - e[bot].mean())))
                stop, sbot = row["sg"] == N_GROUPS - 1, row["sg"] == 0
                standalone.append((m, float(e[stop].mean() - e[sbot].mean())))
            # costs: rebalancing every h months, from the first formation month
            for m in ms[::h]:
                row = rec[s][m]
                if h not in row["fwd"]:
                    continue
                e = row["fwd"][h]
                top_keys = set(row["keys"][row["ng"] == N_GROUPS - 1].tolist())
                bot_keys = set(row["keys"][row["ng"] == 0].tolist())
                t_top = len(top_keys ^ prev_top) / max(2 * len(top_keys), 1) if prev_top is not None else 1.0
                t_bot = len(bot_keys ^ prev_bot) / max(2 * len(bot_keys), 1) if prev_bot is not None else 1.0
                cost = P.COST_ROUNDTRIP_PCT / 100.0
                gross = float(e[row["ng"] == N_GROUPS - 1].mean() - e[row["ng"] == 0].mean())
                spread_net.append(gross - cost * (t_top + t_bot))
                top_net.append(float(e[row["ng"] == N_GROUPS - 1].mean()) - cost * t_top)
                prev_top, prev_bot = top_keys, bot_keys
            vals = [v for _, v in neutral]
            test = P._mean_test(vals)
            non_overlap = len(vals) // h
            usable = non_overlap >= P.MIN_NONOVERLAPPING and test.get("p_value") is not None
            primary.append((s, h, test.get("p_value"), test.get("mean_pct"), usable))
            first = [v for m, v in neutral if half and m < half]
            second = [v for m, v in neutral if half and m >= half]
            res["horizons"][f"{h}m"] = {
                "momentum_neutral_spread": test,
                "non_overlapping_windows": non_overlap,
                "usable": usable,
                "standalone_spread_described": P._mean_test([v for _, v in standalone]),
                "halves_described": {
                    "split_month": half,
                    "first_half_mean_pct": round(float(np.mean(first)) * 100, 3) if first else None,
                    "second_half_mean_pct": round(float(np.mean(second)) * 100, 3) if second else None},
                "after_costs_described": {
                    "rebalances": len(spread_net),
                    "neutral_spread_net_mean_pct": round(float(np.mean(spread_net)) * 100, 3) if spread_net else None,
                    "neutral_group5_net_mean_pct": round(float(np.mean(top_net)) * 100, 3) if top_net else None,
                    "cost_rule": f"{P.COST_ROUNDTRIP_PCT}% round trip on the turnover realised when rebalancing every {h} month(s)"},
            }
        # exploratory, 1 month only: neutral spread by regime and by liquidity tercile
        by_reg, by_liq = {}, {}
        for m in ms:
            row = rec[s][m]
            if 1 not in row["fwd"]:
                continue
            e = row["fwd"][1]
            sp = float(e[row["ng"] == N_GROUPS - 1].mean() - e[row["ng"] == 0].mean())
            for lab in regime_of.get(m, ()):
                by_reg.setdefault(lab, []).append(sp)
            for t, name in enumerate(("Least liquid", "Mid liquidity", "Most liquid")):
                sel = row["liq_t"] == t
                hi, lo = sel & (row["ng"] == N_GROUPS - 1), sel & (row["ng"] == 0)
                if hi.any() and lo.any():
                    by_liq.setdefault(name, []).append(float(e[hi].mean() - e[lo].mean()))
        res["exploratory"] = {"by_regime": {k: P._mean_test(v) for k, v in sorted(by_reg.items())},
                              "by_liquidity": {k: P._mean_test(v) for k, v in sorted(by_liq.items())},
                              "warning": "Uncorrected cuts of the same months. Never a finding."}
        results[s] = res

    # decision rule
    usable = [(s, h, p, m) for s, h, p, m, u in primary if u]
    level = 0.05 / len(usable) if usable else None   # prereg: 0.05 / number of usable primary tests
    verdicts = {}
    for s in SIGNALS:
        cells = [(h, p, m) for ss, h, p, m in usable if ss == s]
        if level and any(p < level and m > 0 for h, p, m in cells):
            v = "adds beyond momentum"
        elif level and any(p < level and m < 0 for h, p, m in cells):
            v = "reversed"
        else:
            v = "no demonstrated added edge"
        passing = [h for h, p, m in cells if level and p < level and m > 0]
        proposal = []
        for h in passing:
            hz = results[s]["horizons"][f"{h}m"]
            halves = hz["halves_described"]
            net = hz["after_costs_described"]["neutral_spread_net_mean_pct"]
            if (halves["first_half_mean_pct"] or 0) > 0 and (halves["second_half_mean_pct"] or 0) > 0 and (net or 0) > 0:
                proposal.append(f"{h}m")
        verdicts[s] = {"verdict": v, "passing_horizons": [f"{h}m" for h in passing],
                       "meets_all_conditions_for_a_proposal": proposal}

    return {
        "prereg": "docs/PREREG_FACTOR_TEST4_PRICE_SIGNALS_2026-10-06.md",
        "known_limit": KNOWN_LIMIT,
        "verdicts": verdicts,
        "signals": results,
        "multiple_testing": {"primary_declared": N_PRIMARY, "primary_usable": len(usable),
                             "level": level, "detail": [{"signal": s, "horizon": f"{h}m", "p": p, "mean_pct": m}
                                                        for s, h, p, m in usable]},
        "universe": {"formation_months": len(form_ix), "first_month": months[0] if months else None,
                     "last_month": months[-1] if months else None, "liquidity_floor_rupees": min_turnover,
                     "min_eligible": MIN_ELIGIBLE},
    }


# ------------------------------------------------------------------ production entry point

def validate_signals(min_turnover=P.MIN_MONTHLY_TURNOVER):
    try:
        from db import get_conn
        conn = get_conn()
    except Exception as e:
        return {"error": f"No database ({type(e).__name__})."}
    try:
        try:
            from security_identity import _pairs, _resolve_pairs
            pair_rows = _pairs(conn)
            canonical, _c, links, amb = _resolve_pairs(pair_rows)
            ident = {"linked_isins": len(links), "ambiguous_not_merged": len(amb)}
            del _c, links, amb
        except Exception as e:
            canonical, pair_rows, ident = {}, [], {"error": type(e).__name__}
        # Precondition recorded, not assumed: the hand-verified split rows still present.
        try:
            hv = conn.execute("SELECT symbol FROM corporate_actions WHERE subject LIKE ?",
                              ("Hand-verified%",)).fetchall()
            hand_verified = sorted({str(r[0]) for r in hv})
        except Exception:
            hand_verified = None
        keys, days, C, V, adjustment = P.load_adjusted(conn, canonical, pair_rows)
        del pair_rows
    finally:
        try:
            conn.close()
        except Exception:
            pass
    out = run_on_matrix(keys, days, C, V, min_turnover=min_turnover)
    out["price_series"] = {"source": "bhavcopy_eod (NSE end-of-day, as printed)", "adjustment": adjustment,
                           "data_range": [days[0], days[-1]] if days else None, "identity_resolution": ident}
    out["preconditions"] = {"hand_verified_split_rows_present": hand_verified,
                            "expected": ["ALANKIT", "DAAWAT"],
                            "duplicates_withdrawn": hand_verified == ["ALANKIT", "DAAWAT"]}
    return out
