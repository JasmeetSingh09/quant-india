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


def _panel(conn, month_days: list, canonical: dict = None):
    """
    Month-end close and traded value for every security, per month.

    A security missing from a month-end file is missing on purpose: it was not
    trading. That absence is what makes the universe point-in-time, so it is
    never filled in.
    """
    canonical = canonical or {}
    closes, values = {}, {}
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
        c, v = {}, {}
        for sym, close, vol, isin in rows:
            key = canonical.get(isin, isin) if isin else sym
            if not key or close is None:
                continue
            sym = key
            try:
                px = float(close)
            except (TypeError, ValueError):
                continue
            if px <= 0:
                continue
            c[sym] = px
            try:
                v[sym] = px * float(vol or 0)
            except (TypeError, ValueError):
                v[sym] = 0.0
        closes[ym] = c
        values[ym] = v
    return closes, values


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
        survivor_only: bool = False) -> dict:
    """
    Run frozen v1.0 momentum on the point-in-time universe.

    survivor_only=True restricts every month to the symbols trading in the
    FINAL month, which reproduces the survivorship bias deliberately so the
    two runs can be compared on identical code.
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
        # Resolve identity BEFORE building the panel, so a company that changed
        # ISIN mid-window is one column rather than two.
        try:
            from security_identity import _pairs, _resolve_pairs
            canonical, _components, _links, _amb = _resolve_pairs(_pairs(conn))
            resolved = {"linked_isins": len(_links),
                        "ambiguous_not_merged": len(_amb)}
        except Exception as e:
            canonical, resolved = {}, {"error": type(e).__name__}
        closes, values = _panel(conn, month_days, canonical)
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
        rets = []
        for sym in basket:
            p_now = now_px.get(sym)
            p_next = next_px.get(sym)
            if p_now is None or p_now <= 0:
                continue
            if p_next is None:
                rets.append(-1.0)
                delisted_held.append({"month": hold_m, "security": sym})
                continue
            rets.append(p_next / p_now - 1.0)
        if not rets:
            continue

        gross = sum(rets) / len(rets)
        turn = len(set(basket) ^ prev_basket) / max(2 * len(basket), 1)
        strat_rets.append(gross - turn * cost)
        prev_basket = set(basket)
        eq_months.append(hold_m)

        b0, b1 = bench.get(form_m), bench.get(hold_m)
        bench_rets.append((b1 / b0 - 1.0) if (b0 and b1) else 0.0)

    if len(strat_rets) < 3:
        return {"error": f"Only {len(strat_rets)} rebalances survived the "
                         f"eligibility rules."}

    return {
        "stats": _stats(strat_rets),
        "benchmark_stats": _stats(bench_rets) if any(bench_rets) else None,
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
            "keyed_on": ("resolved identity — ISINs chained through shared "
                         "tickers; symbol only where no ISIN exists"),
            "coverage": identity,
            "resolution": resolved,
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

    rf = 0.065
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
