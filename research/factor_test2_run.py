"""
factor_test2_run.py — run factor test 2 on the data factor_test2_fetch.py saved.

Rules: docs/PREREG_FACTOR_TEST2_2026-09-13.md, including its amendments, all
committed before this runs on real data. The test mirrors factor test 1
(backend/modules/pit_validation.py): quintiles within each month, the
top-minus-bottom spread tested across months with the same t-test, at least 3
non-overlapping windows per usable horizon, Bonferroni over the usable tests.

    python research/factor_test2_run.py DATA_DIR
"""

import bisect
import calendar
import json
import math
import os
import sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statement_factors as S  # noqa: E402

FACTORS = ("quality", "value", "growth")
HORIZONS = (1, 3, 6)
N_BUCKETS = 5
MIN_ELIGIBLE = 50
MIN_NONOVERLAPPING = 3
MIN_MONTHLY_TURNOVER = 1e7
FIRST_FORMATION = "2023-06"
PRICE_STALE_DAYS = 7
YEAR_GAP_DAYS = (300, 430)


# ------------------------------------------------------------------ statistics

def mean_test(x):
    """pit_validation._mean_test, copied so the two tests use the same arithmetic."""
    n = len(x)
    if n < 3:
        return {"n": n, "insufficient": True}
    arr = np.asarray(x, dtype=float)
    mean = float(np.mean(arr))
    med = float(np.median(arr))
    sd = float(np.std(arr, ddof=1))
    se = sd / math.sqrt(n) if sd > 0 else 0.0
    t = mean / se if se > 0 else None
    p, crit = None, 1.96
    if t is not None:
        try:
            from scipy import stats as st
            p = float(2 * st.t.sf(abs(t), df=n - 1))
            crit = float(st.t.ppf(0.975, df=n - 1))
        except Exception:
            p = float(math.erfc(abs(t) / math.sqrt(2)))
    return {
        "n": n,
        "mean_pct": round(mean * 100, 3),
        "median_pct": round(med * 100, 3),
        "sd_pct": round(sd * 100, 3),
        "t_stat": round(t, 3) if t is not None else None,
        "p_value": round(p, 4) if p is not None else None,
        "ci95_pct": ([round((mean - crit * se) * 100, 3),
                      round((mean + crit * se) * 100, 3)] if se > 0 else None),
        "effect_size_d": round(mean / sd, 3) if sd > 0 else None,
    }


# ------------------------------------------------------------------ data

def load(data_dir):
    stmts, prices = {}, {}
    sdir, pdir = os.path.join(data_dir, "statements"), os.path.join(data_dir, "prices")
    for f in os.listdir(sdir):
        with open(os.path.join(sdir, f), encoding="utf-8") as fh:
            rec = json.load(fh)
        if rec.get("income") or rec.get("balance") or rec.get("cashflow"):
            stmts[f[:-5]] = rec
    for f in os.listdir(pdir):
        with open(os.path.join(pdir, f), encoding="utf-8") as fh:
            rec = json.load(fh)
        if rec.get("close"):
            prices[f[:-5]] = rec
    return stmts, prices


def periods_of(rec):
    found = set()
    for part in ("income", "balance", "cashflow"):
        for values in (rec.get(part) or {}).values():
            found.update(values)
    return sorted(found)


def statement_for(rec, period):
    out = {}
    for part in ("income", "balance", "cashflow"):
        for field, values in (rec.get(part) or {}).items():
            if period in values and field not in out:
                out[field] = values[period]
    return out


def previous_year(periods, period):
    d = date.fromisoformat(period)
    earlier = [p for p in periods
               if YEAR_GAP_DAYS[0] <= (d - date.fromisoformat(p)).days <= YEAR_GAP_DAYS[1]]
    return max(earlier) if earlier else None


def month_end(ym):
    y, m = map(int, ym.split("-"))
    return date(y, m, calendar.monthrange(y, m)[1]).isoformat()


def add_months(ym, k):
    y, m = map(int, ym.split("-"))
    m += k
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def price_at(days, closes, target):
    """Last close on or before `target`, if it is no more than a week old."""
    i = bisect.bisect_right(days, target) - 1
    if i < 0:
        return None
    if (date.fromisoformat(target) - date.fromisoformat(days[i])).days > PRICE_STALE_DAYS:
        return None
    px = closes[days[i]]
    return px if px and px > 0 else None


def turnover(days, rec, ym):
    lo = bisect.bisect_left(days, ym + "-01")
    hi = bisect.bisect_right(days, ym + "-31")
    return sum(rec["close"][d] * rec["volume"].get(d, 0.0) for d in days[lo:hi])


# ------------------------------------------------------------------ panel

def build_panel(stmts, prices):
    tickers = sorted(set(stmts) & set(prices))
    days = {t: sorted(prices[t]["close"]) for t in tickers}
    last_day = max(d[-1] for d in days.values())
    months, ym = [], FIRST_FORMATION
    while month_end(ym) <= last_day:
        months.append(ym)
        ym = add_months(ym, 1)

    panel = {}
    for ym in months:
        me = month_end(ym)
        rows = []
        for t in tickers:
            px = price_at(days[t], prices[t]["close"], me)
            if px is None or turnover(days[t], prices[t], ym) < MIN_MONTHLY_TURNOVER:
                continue
            rec = stmts[t]
            periods = periods_of(rec)
            p = S.usable_period(periods, me)
            if p is None:
                continue
            cur = statement_for(rec, p)
            prev_p = previous_year(periods, p)
            prev = statement_for(rec, prev_p) if prev_p else None
            fwd = {}
            for h in HORIZONS:
                me2 = month_end(add_months(ym, h))
                if me2 > last_day:
                    continue
                px2 = price_at(days[t], prices[t]["close"], me2)
                if px2 is not None:              # amendment: a gap is left out, not -100%
                    fwd[h] = px2 / px - 1.0
            eps, eq = cur.get("Diluted EPS"), cur.get("Stockholders Equity")
            shares = cur.get("Ordinary Shares Number")
            pe = px / eps if eps else None
            pb = px / (eq / shares) if (eq and shares) else None
            rows.append({
                "ticker": t, "turnover": turnover(days[t], prices[t], ym), "fwd": fwd,
                "period": p,
                "scores": {"quality": S.quality_score(cur, prev, px),
                           "value": S.value_score(cur, px),
                           "growth": S.growth_score(cur, prev)},
                "pe": pe if (pe and pe > 0) else None,
                "pb": pb if (pb and pb > 0) else None,
            })
        panel[ym] = rows
    return tickers, last_day, panel


def rank_value(rows):
    """Exploratory: value from each month's cross-sectional ranks of P/E and P/B."""
    def pct_ranks(key):
        vals = sorted((r[key], i) for i, r in enumerate(rows) if r[key] is not None)
        out = {}
        for pos, (_, i) in enumerate(vals):
            out[i] = pos / max(len(vals) - 1, 1)
        return out
    pe_r, pb_r = pct_ranks("pe"), pct_ranks("pb")
    for i, r in enumerate(rows):
        if i not in pe_r and i not in pb_r:
            r["scores"]["value_rank"] = None
        else:
            r["scores"]["value_rank"] = -0.6 * pe_r.get(i, 0.5) - 0.4 * pb_r.get(i, 0.5)


# ------------------------------------------------------------------ test

def test_factor(panel, factor, h):
    spreads, bucket_means = [], [[] for _ in range(N_BUCKETS)]
    liq_top = {"Least liquid": [], "Mid liquidity": [], "Most liquid": []}
    for ym, rows in panel.items():
        elig = [r for r in rows if h in r["fwd"]]
        if len(elig) < MIN_ELIGIBLE:
            continue
        mkt = float(np.mean([r["fwd"][h] for r in elig]))
        scored = [r for r in elig if r["scores"].get(factor) is not None]
        if len(scored) < N_BUCKETS * 2:
            continue
        scored.sort(key=lambda r: r["scores"][factor])       # stable
        nb = len(scored)
        groups = [[] for _ in range(N_BUCKETS)]
        for pos, r in enumerate(scored):
            groups[min(N_BUCKETS - 1, pos * N_BUCKETS // nb)].append(r)
        for b in range(N_BUCKETS):
            bucket_means[b].append(float(np.mean([r["fwd"][h] - mkt for r in groups[b]])))
        spreads.append(float(np.mean([r["fwd"][h] for r in groups[-1]]))
                       - float(np.mean([r["fwd"][h] for r in groups[0]])))
        if h == 1:
            by_turn = sorted(scored, key=lambda r: r["turnover"])
            tercile = {id(r): ("Least liquid", "Mid liquidity", "Most liquid")[min(2, pos * 3 // nb)]
                       for pos, r in enumerate(by_turn)}
            per = {k: [] for k in liq_top}
            for r in groups[-1]:
                per[tercile[id(r)]].append(r["fwd"][h] - mkt)
            for k, v in per.items():
                if v:
                    liq_top[k].append(float(np.mean(v)))
    result = mean_test(spreads)
    result["non_overlapping_windows"] = len(spreads) // h
    result["usable"] = (not result.get("insufficient")
                        and result["non_overlapping_windows"] >= MIN_NONOVERLAPPING)
    result["group_mean_excess_pct"] = [round(float(np.mean(v)) * 100, 3) if v else None
                                       for v in bucket_means]
    out = {"top_minus_bottom": result}
    if h == 1:
        out["exploratory_top_group_by_liquidity"] = {k: mean_test(v) for k, v in liq_top.items()}
    return out


def run(data_dir):
    stmts, prices = load(data_dir)
    tickers, last_day, panel = build_panel(stmts, prices)
    for rows in panel.values():
        rank_value(rows)

    counts = [len(v) for v in panel.values()]
    primary, results = [], {}
    for factor in FACTORS:
        results[factor] = {}
        for h in HORIZONS:
            r = test_factor(panel, factor, h)
            results[factor][f"{h}m"] = r
            t = r["top_minus_bottom"]
            if t["usable"]:
                primary.append((factor, h, t["mean_pct"], t["p_value"]))
    alpha = 0.05 / len(primary) if primary else None
    verdicts = {}
    for factor in FACTORS:
        mine = [(h, m, p) for f, h, m, p in primary if f == factor]
        lead = [h for h, m, p in mine if p is not None and p < alpha and m > 0]
        rev = [h for h, m, p in mine if p is not None and p < alpha and m < 0]
        verdicts[factor] = ("approximate lead" if lead else "reversed" if rev else "no lead",
                            {"lead_horizons": lead, "reversed_horizons": rev})
    exploratory_value_rank = {f"{h}m": test_factor(panel, "value_rank", h)["top_minus_bottom"]
                              for h in HORIZONS}
    return {
        "rules": "docs/PREREG_FACTOR_TEST2_2026-09-13.md (with amendments)",
        "label": "APPROXIMATE: restated statements, about four fiscal years, companies listed today only",
        "data": {
            "stocks_with_statements": len(stmts), "stocks_with_prices": len(prices),
            "stocks_with_both": len(tickers), "last_price_day": last_day,
            "formation_months": list(panel),
            "eligible_per_month": {"min": min(counts) if counts else 0,
                                   "median": float(np.median(counts)) if counts else 0,
                                   "max": max(counts) if counts else 0},
        },
        "bonferroni": {"usable_tests": len(primary), "alpha": alpha},
        "verdicts": {f: v[0] for f, v in verdicts.items()},
        "verdict_detail": {f: v[1] for f, v in verdicts.items()},
        "results": results,
        "exploratory_value_by_rank": exploratory_value_rank,
    }


if __name__ == "__main__":
    out = run(sys.argv[1])
    path = os.path.join(sys.argv[1], "factor_test2_result.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({k: out[k] for k in ("label", "data", "bonferroni", "verdicts")}, indent=1)[:3000])
    for f in FACTORS:
        for h in HORIZONS:
            t = out["results"][f][f"{h}m"]["top_minus_bottom"]
            print(f"{f:<8} {h}m: spread {t.get('mean_pct')}%  p={t.get('p_value')}  "
                  f"windows={t.get('non_overlapping_windows')}  usable={t.get('usable')}  "
                  f"groups={t.get('group_mean_excess_pct')}")
    print("written:", path)
