"""
pit_backtest.py — the strategy run on the market as it actually was.

Every other backtest in this project starts from a list of companies that
exist today and walks it backwards. This one starts from the exchange's own
daily files and asks, at each rebalance, which companies were trading THAT
month. Firms that later delisted are eligible while they lived and disappear
when they died. Firms that had not listed yet are absent until they had.

Prices come from bhavcopy for the same reason. Yahoo cannot serve AARVEEDEN or
ACLGATI — they are gone, and a data source built around currently-listed
companies has no row for a company that stopped existing. That absence IS
survivorship bias, and using the exchange files is the only way around it with
free data.

What is deliberately unchanged
------------------------------
The 12-1 momentum definition, monthly rebalancing, the top-fraction rule, the
minimum-holdings guard and the cost model are identical to the frozen v1.0
backtest. This is a different UNIVERSE, not a different strategy. If the result
is worse, that is the finding.

Known limits, stated before any number is produced
--------------------------------------------------
The archive starts in January 2024, and a 12-month lookback plus a skip month
consumes the first thirteen. So roughly eighteen months of rebalances remain.
That is a clean test of the implementation over that window and nothing more —
eighteen monthly observations cannot establish a durable edge, and this module
says so in its own output rather than leaving it to a footnote.
"""

from model_config import RISK_FREE_RATE as _RF

from datetime import datetime

# Same cost assumption as the rest of the project: Indian delivery rates for a
# round trip. Repeated here rather than imported so a change to one cannot
# silently alter the other without showing up as a difference.
COST_ROUNDTRIP_PCT = 0.4

LOOKBACK_MONTHS = 12
SKIP_MONTHS = 1
MIN_HOLDINGS = 5
# Below this many rupees of monthly traded value a name is not investable at
# any size that matters, and including it measures a price nobody could have
# transacted at. 1 crore/day is already generous for a retail book.
MIN_MONTHLY_TURNOVER = 1e7


def _month_end_days(conn) -> list:
    """The last trading day the exchange actually recorded in each month."""
    rows = conn.execute(
        "SELECT substr(day,1,7) AS ym, MAX(day) FROM bhavcopy_eod "
        "GROUP BY substr(day,1,7) ORDER BY ym").fetchall()
    return [(r[0], r[1]) for r in rows if r and r[1]]


def _panel(conn, month_days: list, canonical: dict = None,
           key_mode: str = "resolved"):
    """
    Month-end close and traded value for every security, per month.

    A security missing from a month-end file is missing on purpose: it was not
    trading. That absence is what makes the universe point-in-time, so it is
    never filled in.
    """
    canonical = canonical or {}
    closes, values, to_resolved = {}, {}, {}
    for ym, day in month_days:
        # Keyed on resolved identity, not on either raw identifier. Keying on
        # the symbol made ZOMATO look like a company that ceased to exist when
        # it was trading normally as ETERNAL the same day. Keying on the ISIN
        # fixes that and breaks the mirror case: a company that keeps its
        # ticker through a corporate action gets a new ISIN, and the old one
        # vanishing reads as a delisting. In this window that mirror case is
        # the LARGER of the two. security_identity chains both together.
        #
        # Rows without an ISIN fall back to the symbol so a partially
        # backfilled table still runs — degraded, and the caller is told.
        rows = conn.execute(
            "SELECT symbol, close, volume, isin FROM bhavcopy_eod WHERE day = ?",
            (day,)).fetchall()
        c, v, r = {}, {}, {}
        for sym, close, vol, isin in rows:
            # The resolved identity is computed for every row whatever the key
            # mode, because it is what tells a naive run that a security it
            # just wrote off to -100% was in fact still trading.
            rid = canonical.get(isin, isin) if isin else sym
            if key_mode == "symbol":
                key = sym
            elif key_mode == "isin":
                key = isin or sym
            else:
                key = rid
            if not key or close is None:
                continue
            try:
                px = float(close)
            except (TypeError, ValueError):
                continue
            if px <= 0:
                continue
            c[key] = px
            r[key] = rid
            try:
                v[key] = px * float(vol or 0)
            except (TypeError, ValueError):
                v[key] = 0.0
        closes[ym] = c
        values[ym] = v
        to_resolved[ym] = r
    return closes, values, to_resolved


def _panels_all(conn, month_days: list, canonical: dict = None):
    """
    All three keyings built from a single pass over the files.

    Reading the archive once and keying it three ways is faster than three
    passes, and it also removes a question the comparison would otherwise
    invite: the runs cannot differ because of what they read, because they read
    the same rows.
    """
    canonical = canonical or {}
    modes = ("symbol", "isin", "resolved")
    out = {m: ({}, {}, {}) for m in modes}
    for ym, day in month_days:
        rows = conn.execute(
            "SELECT symbol, close, volume, isin FROM bhavcopy_eod WHERE day = ?",
            (day,)).fetchall()
        buckets = {m: ({}, {}, {}) for m in modes}
        for sym, close, vol, isin in rows:
            if close is None:
                continue
            try:
                px = float(close)
            except (TypeError, ValueError):
                continue
            if px <= 0:
                continue
            try:
                val = px * float(vol or 0)
            except (TypeError, ValueError):
                val = 0.0
            rid = canonical.get(isin, isin) if isin else sym
            for m, key in (("symbol", sym), ("isin", isin or sym),
                           ("resolved", rid)):
                if not key:
                    continue
                c, v, r = buckets[m]
                c[key] = px
                v[key] = val
                r[key] = rid
        for m in modes:
            c, v, r = buckets[m]
            out[m][0][ym] = c
            out[m][1][ym] = v
            out[m][2][ym] = r
    return out


def _benchmark(months: list) -> dict:
    """Nifty month-end closes. An index does not delist, so Yahoo is fine."""
    try:
        import yfinance as yf
        start = f"{months[0]}-01"
        df = yf.download("^NSEI", start=start, progress=False,
                         auto_adjust=True, threads=False)
        if df is None or df.empty:
            return {}
        s = df["Close"]
        if hasattr(s, "columns"):
            s = s.iloc[:, 0]
        m = s.resample("ME").last().dropna()
        return {d.strftime("%Y-%m"): float(v) for d, v in m.items()}
    except Exception:
        return {}


def run(top_fraction: float = 0.2, min_turnover: float = MIN_MONTHLY_TURNOVER,
        survivor_only: bool = False, key_mode: str = "resolved",
        _prebuilt: tuple = None) -> dict:
    """
    Run frozen v1.0 momentum on the point-in-time universe.

    survivor_only=True restricts every month to the securities trading in the
    FINAL month, which reproduces the survivorship bias deliberately so the
    two runs can be compared on identical code.

    key_mode selects how a security is identified across months, and changes
    NOTHING else — not a weight, not a threshold, not the cost model:

        symbol    the ticker, which is what the first version used
        isin      the ISIN, which fixed renames and broke restructurings
        resolved  ISINs chained through shared tickers (the correction)

    Running the same strategy under each is the only way to attribute a
    difference in result to identity rather than to anything else.
    """
    if _prebuilt is not None:
        month_days, closes, values, to_resolved, resolved = _prebuilt
    else:
        try:
            from db import get_conn
            conn = get_conn()
        except Exception as e:
            return {"error": f"No database ({type(e).__name__})."}

        try:
            month_days = _month_end_days(conn)
            if len(month_days) < LOOKBACK_MONTHS + SKIP_MONTHS + 2:
                return {"error": (f"Only {len(month_days)} months of exchange "
                                  f"files. A 12-1 momentum test needs at least "
                                  f"{LOOKBACK_MONTHS + SKIP_MONTHS + 2}.")}
            # Resolve identity BEFORE building the panel, so a company that
            # changed ISIN mid-window is one column rather than two.
            try:
                from security_identity import _pairs, _resolve_pairs
                canonical, _components, _links, _amb = _resolve_pairs(_pairs(conn))
                resolved = {"linked_isins": len(_links),
                            "ambiguous_not_merged": len(_amb)}
            except Exception as e:
                canonical, resolved = {}, {"error": type(e).__name__}
            closes, values, to_resolved = _panel(conn, month_days, canonical,
                                                 key_mode)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # How much of this run is genuinely identity-keyed. A run over rows without
    # ISIN is the old symbol-keyed behaviour wearing the new name.
    try:
        from security_identity import coverage as _idcov
        identity = _idcov()
    except Exception:
        identity = {"available": False}

    months = [ym for ym, _ in month_days]
    final_universe = set(closes[months[-1]]) if months else set()

    bench = _benchmark(months)

    L, K = LOOKBACK_MONTHS, SKIP_MONTHS
    strat_rets, bench_rets, eq_months = [], [], []
    prev_basket, eligible_log, holdings_log = set(), [], []
    delisted_held = []
    # Every -100% booking is checked against resolved identity. If the security
    # was still trading that month under another label, the write-off was an
    # artefact of the key, not a delisting — this is the count that says how
    # much of the old result was manufactured by the identity bug.
    invalid_writeoffs = []
    all_holding_rets, unique_held, turnover_log = [], set(), []
    cost = COST_ROUNDTRIP_PCT / 100.0

    for i in range(L, len(months) - 1):
        form_m = months[i]          # formation month (signal computed here)
        hold_m = months[i + 1]      # the month actually held

        past_m = months[i - L]
        recent_m = months[i - K]
        past, recent = closes.get(past_m, {}), closes.get(recent_m, {})
        now_px, next_px = closes.get(form_m, {}), closes.get(hold_m, {})

        # Eligible = trading at formation, with a full lookback, and liquid
        # enough to have been bought. Survivorship enters ONLY through which
        # symbols are present in these dictionaries.
        pool = []
        for sym, p0 in past.items():
            p1 = recent.get(sym)
            p_now = now_px.get(sym)
            if p1 is None or p_now is None or p0 <= 0:
                continue
            if survivor_only and sym not in final_universe:
                continue
            if values.get(form_m, {}).get(sym, 0) < min_turnover:
                continue
            pool.append((sym, p1 / p0 - 1.0))

        eligible_log.append(len(pool))
        if len(pool) < MIN_HOLDINGS / max(top_fraction, 1e-9):
            continue

        pool.sort(key=lambda x: -x[1])
        n_hold = max(MIN_HOLDINGS, int(round(len(pool) * top_fraction)))
        basket = [s for s, _ in pool[:n_hold]]
        holdings_log.append(len(basket))

        # Hold for one month. A name that stops trading before the next
        # month-end has no closing price: that is a delisting mid-hold, and
        # pretending otherwise is precisely the bias being removed. It is
        # marked to -100% of that position, which is the harshest defensible
        # assumption and is disclosed as such.
        alive_next = set(to_resolved.get(hold_m, {}).values())
        rets = []
        for sym in basket:
            p_now = now_px.get(sym)
            p_next = next_px.get(sym)
            if p_now is None or p_now <= 0:
                continue
            if p_next is None:
                rets.append(-1.0)
                rid = to_resolved.get(form_m, {}).get(sym)
                still_trading = rid in alive_next if rid else False
                delisted_held.append({"month": hold_m, "security": sym,
                                      "still_trading_as": rid if still_trading
                                                          else None})
                if still_trading:
                    invalid_writeoffs.append({"month": hold_m, "booked": sym,
                                              "actually_trading_as": rid})
                continue
            rets.append(p_next / p_now - 1.0)
        if not rets:
            continue

        # Kept with their month, because holdings in the same month share that
        # month's market move and are not independent observations.
        all_holding_rets.extend((hold_m, r) for r in rets)
        unique_held.update(basket)
        gross = sum(rets) / len(rets)
        turn = len(set(basket) ^ prev_basket) / max(2 * len(basket), 1)
        turnover_log.append(turn)
        strat_rets.append(gross - turn * cost)
        prev_basket = set(basket)
        eq_months.append(hold_m)

        b0, b1 = bench.get(form_m), bench.get(hold_m)
        bench_rets.append((b1 / b0 - 1.0) if (b0 and b1) else 0.0)

    if len(strat_rets) < 3:
        return {"error": f"Only {len(strat_rets)} rebalances survived the "
                         f"eligibility rules."}

    excess = [s - b for s, b in zip(strat_rets, bench_rets)]

    return {
        "stats": _stats(strat_rets),
        "benchmark_stats": _stats(bench_rets) if any(bench_rets) else None,
        "excess_stats": _evidence(excess),
        "monthly_evidence": _evidence(strat_rets),
        "holdings_stats": _holding_stats(all_holding_rets),
        "unique_securities_held": len(unique_held),
        "turnover": {
            "avg_monthly_pct": round(sum(turnover_log) / len(turnover_log) * 100, 1)
                               if turnover_log else None,
            "note": ("Fraction of the book replaced each month, from the "
                     "symmetric difference between consecutive baskets."),
        },
        "months_tested": len(strat_rets),
        "period": f"{eq_months[0]} to {eq_months[-1]}",
        "universe": {
            "mode": "survivor-only (bias reproduced)" if survivor_only
                    else "point-in-time",
            "avg_eligible_per_rebalance": round(sum(eligible_log) / len(eligible_log), 1)
                                          if eligible_log else 0,
            "min_eligible": min(eligible_log) if eligible_log else 0,
            "max_eligible": max(eligible_log) if eligible_log else 0,
            "avg_holdings": round(sum(holdings_log) / len(holdings_log), 1)
                            if holdings_log else 0,
            "months_available": len(months),
            "first_month": months[0],
            "last_month": months[-1],
        },
        "identity": {
            "key_mode": key_mode,
            "keyed_on": {
                "symbol": "the ticker alone — a rename reads as a delisting",
                "isin": "the ISIN alone — a new ISIN under a kept ticker reads "
                        "as a delisting",
                "resolved": "ISINs chained through shared tickers; symbol only "
                            "where no ISIN exists",
            }.get(key_mode, key_mode),
            "coverage": identity,
            "resolution": resolved,
            "invalid_writeoffs": {
                "count": len(invalid_writeoffs),
                "examples": invalid_writeoffs[:8],
                "meaning": ("Positions booked at -100% that resolved identity "
                            "shows were still trading that month. Under "
                            "key_mode='resolved' this is zero by construction; "
                            "under the other two it is the damage the identity "
                            "bug did to the result."),
            },
            "why": ("Neither identifier survives every corporate event. Keyed "
                    "on symbols, a rename looks like a delisting and gets "
                    "booked as a total loss. Keyed on ISINs, a company that "
                    "keeps its ticker through a restructuring looks like one "
                    "too — and in this window that second case is the larger "
                    "of the two. Chaining both is what makes a delisting here "
                    "mean the security actually stopped trading."),
        },
        "delistings_held": {
            "count": len(delisted_held),
            "examples": delisted_held[:8],
            "treatment": ("A holding with no month-end price is marked to -100%. "
                          "That is the harshest defensible assumption; a real "
                          "investor might have exited earlier or recovered "
                          "something. It is stated rather than softened because "
                          "the alternative — dropping the position — is exactly "
                          "the survivorship this module exists to remove."),
        },
        "costs": {"round_trip_pct": COST_ROUNDTRIP_PCT,
                  "note": ("Charged on realised turnover each month: the "
                           "symmetric difference between consecutive baskets, "
                           "halved, times the round-trip rate.")},
        "limits": (
            f"{len(strat_rets)} monthly observations. That is a clean test of "
            f"the implementation over this window and nothing more — eighteen "
            f"or so months cannot establish a durable edge, whatever the "
            f"number says. Prices are exchange closes, unadjusted for splits "
            f"and dividends, so a corporate action inside the hold month "
            f"distorts that month's return for that name."),
    }


def _evidence(series: list) -> dict:
    """
    Whether a mean is distinguishable from zero, on this many observations.

    Reported alongside every return figure because a mean without an interval
    invites a reader to treat noise as a finding, and at eighteen monthly
    observations noise is the default explanation.
    """
    import math
    n = len(series)
    if n < 3:
        return {"n": n, "insufficient": True,
                "note": "Too few observations to say anything about the mean."}
    mean = sum(series) / n
    var = sum((x - mean) ** 2 for x in series) / (n - 1)
    sd = var ** 0.5
    se = sd / math.sqrt(n) if sd > 0 else 0.0
    t = (mean / se) if se > 0 else None

    p, method = None, None
    if t is not None:
        try:
            from scipy import stats as _st
            p = float(2 * _st.t.sf(abs(t), df=n - 1))
            method = "two-sided t-test"
        except Exception:
            from math import erfc
            p = float(erfc(abs(t) / math.sqrt(2)))
            method = "normal approximation (scipy unavailable)"

    crit = 1.96
    try:
        from scipy import stats as _st
        crit = float(_st.t.ppf(0.975, df=n - 1))
    except Exception:
        pass

    srt = sorted(series)
    mid = n // 2
    median = srt[mid] if n % 2 else (srt[mid - 1] + srt[mid]) / 2

    return {
        "n": n,
        "mean_pct": round(mean * 100, 3),
        "median_pct": round(median * 100, 3),
        "sd_pct": round(sd * 100, 3),
        "t_stat": round(t, 3) if t is not None else None,
        "p_value": round(p, 4) if p is not None else None,
        "p_method": method,
        "ci95_mean_pct": [round((mean - crit * se) * 100, 3),
                          round((mean + crit * se) * 100, 3)]
                         if se > 0 else None,
        # Cohen's d for a one-sample mean against zero.
        "effect_size_d": round(mean / sd, 3) if sd > 0 else None,
        "significant_at_5pct": bool(p is not None and p < 0.05),
    }


def _holding_stats(month_rets: list) -> dict:
    """
    Statistics across individual positions, with the clustering priced in.

    Every holding in a month shares that month's market move, so counting them
    as independent draws overstates the evidence by whatever the intra-month
    correlation happens to be. That correlation is estimated from these
    observations rather than assumed, and the effective sample size is reported
    next to the raw one so the gap is visible.
    """
    if not month_rets:
        return {"n": 0, "insufficient": True}
    rets = [r for _, r in month_rets]
    base = _evidence(rets)
    hits = sum(1 for r in rets if r > 0)
    n = len(rets)

    wilson, binom_p, binom_method, deff = None, None, None, None
    try:
        from market_validation import _wilson, _binom_p, _design_effect
        wilson = _wilson(hits, n)
        binom_p, binom_method = _binom_p(hits, n)
        deff = _design_effect([{"date": m + "-01", "_hit": r > 0}
                               for m, r in month_rets])
    except Exception:
        pass

    n_eff = None
    if deff and deff.get("deff"):
        n_eff = round(n / deff["deff"], 1)

    # The unadjusted interval and p-value are computed as if every position
    # were an independent draw. They are not — positions held in the same month
    # share that month's market move — so on this data the unadjusted p-value
    # is roughly fifty times too confident. Both are reported, but the adjusted
    # pair is the one that means anything, and the unadjusted pair is labelled
    # rather than quietly shown next to it.
    eff_wilson, eff_p, eff_method, eff_hits = None, None, None, None
    if n_eff and n_eff >= 5:
        try:
            from market_validation import _wilson, _binom_p
            n_i = int(round(n_eff))
            eff_hits = int(round(hits / n * n_i))
            eff_wilson = _wilson(eff_hits, n_i)
            eff_p, eff_method = _binom_p(eff_hits, n_i)
        except Exception:
            pass

    out = dict(base)
    out.update({
        "positions": n,
        "hit_rate_pct": round(hits / n * 100, 1),
        "effective_sample_size": n_eff,
        "hit_rate_ci95": eff_wilson,
        "hit_rate_p_value": round(eff_p, 4) if eff_p is not None else None,
        "hit_rate_p_method": (f"{eff_method}, on the effective sample "
                              f"({eff_hits} of {int(round(n_eff))})"
                              if eff_method else None),
        "hit_rate_significant_at_5pct": bool(eff_p is not None and eff_p < 0.05),
        "unadjusted_if_positions_were_independent": {
            "ci95": wilson,
            "p_value": round(binom_p, 4) if binom_p is not None else None,
            "method": binom_method,
            "warning": ("These treat all "
                        + str(n) +
                        " position-months as independent draws. They are not. "
                        "This pair is shown only so the size of the correction "
                        "is visible; it is not evidence of anything."),
        },
        "clustering": deff,
        "note": ("Position-level figures. The headline interval and p-value are "
                 "computed on the EFFECTIVE sample size — the raw count divided "
                 "by a design effect estimated from these observations by "
                 "ANOVA. Positions held in the same month are not independent "
                 "observations, and at a design effect above 50 the difference "
                 "decides whether a result looks significant."),
    })
    return out


def _stats(monthly: list) -> dict:
    """Annualised statistics from monthly returns, written out longhand."""
    import math
    n = len(monthly)
    if n < 2:
        return {}
    total = 1.0
    for r in monthly:
        total *= (1 + r)
    years = n / 12.0
    cagr = (total ** (1 / years) - 1) if total > 0 else -1.0
    mean = sum(monthly) / n
    var = sum((r - mean) ** 2 for r in monthly) / (n - 1)
    vol = (var ** 0.5) * math.sqrt(12)
    down = [r for r in monthly if r < 0]
    dvol = ((sum((r - 0) ** 2 for r in down) / len(down)) ** 0.5 * math.sqrt(12)
            if len(down) > 1 else None)

    curve, peak, max_dd = 1.0, 1.0, 0.0
    for r in monthly:
        curve *= (1 + r)
        peak = max(peak, curve)
        max_dd = min(max_dd, curve / peak - 1)

    rf = _RF
    return {
        "cagr_pct": round(cagr * 100, 2),
        "total_return_pct": round((total - 1) * 100, 2),
        "vol_pct": round(vol * 100, 2),
        "sharpe": round((cagr - rf) / vol, 3) if vol > 0 else None,
        "sortino": round((cagr - rf) / dvol, 3) if dvol else None,
        "max_drawdown_pct": round(max_dd * 100, 2),
        "hit_rate_pct": round(sum(1 for r in monthly if r > 0) / n * 100, 1),
        "n_months": n,
    }


def identity_ab(top_fraction: float = 0.2) -> dict:
    """
    The same strategy run three ways, differing only in what counts as one
    security.

    This is the experiment that says how much of the earlier result was the
    strategy and how much was the identity bug. Nothing else varies between the
    runs — same weights, same lookback, same costs, same eligibility rules,
    same frozen v1.0 — so any difference is attributable to identity and to
    nothing else.
    """
    try:
        from db import get_conn
        conn = get_conn()
    except Exception as e:
        return {"error": f"No database ({type(e).__name__})."}
    try:
        month_days = _month_end_days(conn)
        if len(month_days) < LOOKBACK_MONTHS + SKIP_MONTHS + 2:
            return {"error": (f"Only {len(month_days)} months of exchange files. "
                              f"A 12-1 momentum test needs at least "
                              f"{LOOKBACK_MONTHS + SKIP_MONTHS + 2}.")}
        try:
            from security_identity import _pairs, _resolve_pairs
            canonical, _components, _links, _amb = _resolve_pairs(_pairs(conn))
            resolved = {"linked_isins": len(_links),
                        "ambiguous_not_merged": len(_amb)}
        except Exception as e:
            canonical, resolved = {}, {"error": type(e).__name__}
        panels = _panels_all(conn, month_days, canonical)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    runs = {}
    for mode in ("symbol", "isin", "resolved"):
        c, v, r2 = panels[mode]
        runs[mode] = run(top_fraction=top_fraction, survivor_only=False,
                         key_mode=mode,
                         _prebuilt=(month_days, c, v, r2, resolved))
        if "error" in runs[mode]:
            return {"error": f"{mode} run: {runs[mode]['error']}"}

    def _row(label, fn):
        return {"metric": label,
                "old_symbol": fn(runs["symbol"]),
                "old_isin": fn(runs["isin"]),
                "corrected": fn(runs["resolved"])}

    def _g(d, *path, default=None):
        for k in path:
            if not isinstance(d, dict):
                return default
            d = d.get(k)
        return d if d is not None else default

    table = [
        _row("Months tested", lambda r: r.get("months_tested")),
        _row("Avg eligible per rebalance",
             lambda r: _g(r, "universe", "avg_eligible_per_rebalance")),
        _row("Avg holdings", lambda r: _g(r, "universe", "avg_holdings")),
        _row("Unique securities held",
             lambda r: r.get("unique_securities_held")),
        _row("Position-months", lambda r: _g(r, "holdings_stats", "positions")),
        _row("Delistings booked",
             lambda r: _g(r, "delistings_held", "count")),
        _row("Invalid -100% bookings",
             lambda r: _g(r, "identity", "invalid_writeoffs", "count")),
        _row("Hit rate, monthly (%)",
             lambda r: _g(r, "stats", "hit_rate_pct")),
        _row("Hit rate, positions (%)",
             lambda r: _g(r, "holdings_stats", "hit_rate_pct")),
        _row("Mean monthly return (%)",
             lambda r: _g(r, "monthly_evidence", "mean_pct")),
        _row("Median monthly return (%)",
             lambda r: _g(r, "monthly_evidence", "median_pct")),
        _row("Mean position return (%)",
             lambda r: _g(r, "holdings_stats", "mean_pct")),
        _row("Median position return (%)",
             lambda r: _g(r, "holdings_stats", "median_pct")),
        _row("Mean monthly excess vs Nifty (%)",
             lambda r: _g(r, "excess_stats", "mean_pct")),
        _row("CAGR (%)", lambda r: _g(r, "stats", "cagr_pct")),
        _row("Volatility (%)", lambda r: _g(r, "stats", "vol_pct")),
        _row("Sharpe", lambda r: _g(r, "stats", "sharpe")),
        _row("Max drawdown (%)", lambda r: _g(r, "stats", "max_drawdown_pct")),
        _row("Avg monthly turnover (%)",
             lambda r: _g(r, "turnover", "avg_monthly_pct")),
        _row("t-stat, monthly mean",
             lambda r: _g(r, "monthly_evidence", "t_stat")),
        _row("p-value, monthly mean",
             lambda r: _g(r, "monthly_evidence", "p_value")),
        _row("Effect size (d), monthly",
             lambda r: _g(r, "monthly_evidence", "effect_size_d")),
        _row("Effective sample size, positions",
             lambda r: _g(r, "holdings_stats", "effective_sample_size")),
    ]

    inv_sym = _g(runs["symbol"], "identity", "invalid_writeoffs", "count", default=0)
    inv_isin = _g(runs["isin"], "identity", "invalid_writeoffs", "count", default=0)
    inv_res = _g(runs["resolved"], "identity", "invalid_writeoffs", "count", default=0)

    return {
        "table": table,
        "runs": runs,
        "held_constant": (
            "Factor definition, weights, lookback, skip month, top fraction, "
            "minimum holdings, liquidity floor, cost model, rebalance frequency "
            "and benchmark are identical across the three runs. The only "
            "difference is what counts as one security across months."),
        "invalid_writeoffs": {
            "symbol_keyed": inv_sym,
            "isin_keyed": inv_isin,
            "resolved": inv_res,
            "reading": (
                f"Keyed on tickers, {inv_sym} position(s) were written off to "
                f"-100% while the company was still trading. Keyed on ISINs, "
                f"{inv_isin}. Resolved, {inv_res} — zero by construction, which "
                f"is what makes the corrected run's losses real losses."),
        },
        "caution": (
            "A difference between these columns is a measure of the bug, not "
            "evidence about the strategy. The corrected column is the only one "
            "worth interpreting as a result, and it is still eighteen-odd "
            "monthly observations over a single market regime."),
    }


def compare(top_fraction: float = 0.2) -> dict:
    """
    The experiment: identical code, identical strategy, two universes.

    One run sees only the companies that survived to the final month. The other
    sees what was actually trading. The difference is survivorship and nothing
    else, because every other line is shared.
    """
    pit = run(top_fraction=top_fraction, survivor_only=False)
    sur = run(top_fraction=top_fraction, survivor_only=True)
    if "error" in pit:
        return {"error": f"point-in-time run: {pit['error']}"}
    if "error" in sur:
        return {"error": f"survivor-only run: {sur['error']}"}

    a, b = sur["stats"], pit["stats"]
    diff = {k: (round(b[k] - a[k], 3)
                if isinstance(a.get(k), (int, float))
                and isinstance(b.get(k), (int, float)) else None)
            for k in a}

    return {
        "survivor_only": sur,
        "point_in_time": pit,
        "difference": diff,
        "survivorship_cost_cagr_pct": diff.get("cagr_pct"),
        "verdict": (
            f"Holding the strategy and the code fixed, moving from a "
            f"survivor-only universe to the universe that actually existed "
            f"changes annual return by {diff.get('cagr_pct')} points. "
            + ("The survivor-only run looks better, which is what survivorship "
               "bias does."
               if (diff.get("cagr_pct") or 0) < 0 else
               "The point-in-time run looks better, which is worth "
               "investigating rather than celebrating: survivorship normally "
               "flatters, so a reversal suggests the delisted names were not "
               "being selected anyway.")),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
