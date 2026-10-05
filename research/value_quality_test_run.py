"""
value_quality_test_run.py — the runner for the value and quality test on as-published accounts.

Rules: docs/PREREG_VALUE_QUALITY_REPORTS_DRAFT_2026-09-26.md. This file implements them and
nothing else. Until that document is approved and committed, the only run allowed is the
placebo (plumbing) check, which this file can do on its own:

    python research/value_quality_test_run.py placebo INPUT_DIR      # allowed before commit
    python research/value_quality_test_run.py run INPUT_DIR          # only after the prereg is committed

INPUT_DIR holds four files. Each is produced elsewhere and is described here so the
runner does not depend on how it was made.

  accounts.json   {"SYMBOL|FY": {"profit": x, "total_equity": x, "total_assets": x,
                    "share_capital": x, "face_value": x, "cfo": x, "revenue": x,
                    "revenue_prev": x, "year_end": "YYYY-MM-DD", "accepted": true|false}}
                  Money in Rs crore. "accepted" is true only when every input the formulas
                  use was accepted under the prereg's data rules (verified by the report's
                  own checks, or accepted by research/ar_review.py). A field not accepted
                  is absent. Nothing is ever filled in.
  universe.json   {"FY": ["SYMBOL", ...]} — the top 100 by traded value in financial year
                  FY from the point-in-time archive, funds and financial companies removed
                  (the classification list is committed before the run).
  prices.json     {"SYMBOL": {"YYYY-MM": {"close": printed month-end close,
                    "share_factor": shares now per share at the year end (splits and
                    bonuses between the year end and this month-end, from the stored
                    corporate actions), "fwd": {"1": r, "3": r, "6": r, "12": r}}}}
                  fwd are forward returns from this month-end, from the same machinery as
                  factor test 1 (backend/modules/pit_validation.py: adjusted for splits,
                  bonuses and dividends; ISIN identity joins; a security with no price at
                  the end of the holding period counts as -100%).
  meta.json       {"archive_first_day": ..., "archive_last_day": ..., "source": ...}

One detail the prereg leaves implicit is fixed here, before any run: "net of the market
that month" means net of the equal-weighted mean return of all stocks scored that month
for that factor, the same convention as factor test 1. It must be confirmed when the
prereg is committed.
"""

import json
import math
import os
import random
import sys

import numpy as np

HORIZONS = (1, 3, 6, 12)
N_GROUPS = 5
MIN_SCORED = 50
LEVEL = 0.05 / 8                      # eight primary tests, Bonferroni
COVERAGE_GATE = 0.80
PLACEBO_DRAWS = 200
FIRST_FORMATION = "2013-01"
LAG_MONTHS = 9                        # accounts usable from the first month-end >= 9 months after the year end

# Value constants, as the app's fallbacks (no sector peers can be rebuilt for a past date).
PE_MID, PE_SPREAD, PB_MID, PB_SPREAD = 22.0, 8.0, 3.2, 1.5


# ------------------------------------------------------------------ the formulas

def value_score(a, close, share_factor):
    """Value score for one company-year at one month-end, or None if an input is missing."""
    need = ("profit", "total_equity", "share_capital", "face_value")
    if any(a.get(k) is None for k in need) or not close or not a["face_value"]:
        return None
    shares_crore = a["share_capital"] / a["face_value"] * (share_factor or 1.0)
    mcap = close * shares_crore                                  # Rs crore
    pe = mcap / a["profit"] if a["profit"] else None
    pb = mcap / a["total_equity"] if a["total_equity"] else None
    pe = pe if (pe is not None and pe > 0) else None
    pb = pb if (pb is not None and pb > 0) else None
    if pe is None and pb is None:
        return -0.5
    pe_v = PE_MID if pe is None else pe                          # a dropped leg sits at its constant
    pb_v = PB_MID if pb is None else pb
    raw = -0.6 * (pe_v - PE_MID) / PE_SPREAD - 0.4 * (pb_v - PB_MID) / PB_SPREAD
    return math.tanh(raw / 2)


def quality_score(a):
    """Quality score for one company-year, or None if an input is missing."""
    need = ("profit", "total_assets", "total_equity", "cfo", "revenue", "revenue_prev")
    if any(a.get(k) is None for k in need) or not a["total_assets"]:
        return None
    roa = a["profit"] / a["total_assets"]
    roe = a["profit"] / a["total_equity"] if a["total_equity"] > 0 else None
    f = (int(roa > 0) + int(a["cfo"] > 0) + int(roa > 0.05) + int(a["cfo"] / a["total_assets"] > roa)
         + 1 + int(a["revenue"] > a["revenue_prev"]))          # points 5, 6, 8 are 0 (prereg)
    raw = (0.4 * f / 9 + 0.4 * ((roe - 0.12) / 0.08) / 3) / 0.8 if roe is not None else f / 9
    pen = (0.5 if a["total_equity"] < 0 else 0) + (0.25 if a["profit"] < 0 else 0) + (0.25 if a["cfo"] < 0 else 0)
    if pen:
        raw = min(raw, 0.0) - pen
    return math.tanh(raw)


# ------------------------------------------------------------------ timing

def add_months(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) + k
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def formation_months(year_end):
    """The twelve month-ends at which one year's accounts are used: from the first month-end
    at least nine months after the year end. For a March year end Y that is January Y+1 to
    December Y+1, as the prereg states."""
    ym = year_end[:7]
    if ym[5:7] == "03":
        first = add_months(ym, LAG_MONTHS + 1)                 # March 2012 -> January 2013, as the prereg states
    else:
        first = add_months(ym, LAG_MONTHS)                     # December 2014 -> September 2015 (nine months)
    return [add_months(first, i) for i in range(12)]


# ------------------------------------------------------------------ statistics

def newey_west_t(x, lag):
    """Mean, Newey-West standard error with `lag` lags (Bartlett), t and two-sided p."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 3:
        return None
    mu = float(x.mean())
    e = x - mu
    var = float(e @ e) / n
    for L in range(1, min(lag, n - 1) + 1):
        w = 1 - L / (lag + 1)
        var += 2 * w * float(e[L:] @ e[:-L]) / n
    se = math.sqrt(max(var, 0.0) / n)
    if se == 0:
        return {"n": n, "mean": mu, "se": 0.0, "t": None, "p": None}
    t = mu / se
    try:
        from scipy import stats
        p = float(2 * stats.t.sf(abs(t), df=n - 1))
    except Exception:
        p = math.erfc(abs(t) / math.sqrt(2))
    return {"n": n, "mean": mu, "se": se, "t": t, "p": p}


def min_detectable(se, level=LEVEL, power=0.80):
    """Smallest spread the test would detect with 80% power at the primary level."""
    from statistics import NormalDist
    z = NormalDist()
    return (z.inv_cdf(1 - level / 2) + z.inv_cdf(power)) * se


# ------------------------------------------------------------------ the panel

def build_scores(accounts, universe, prices):
    """{factor: {month: [(symbol, score, {h: excess-to-be})...]}}, plus coverage counts."""
    out = {"value": {}, "quality": {}}
    eligible = accepted = 0
    for fy, syms in universe.items():
        for sym in syms:
            a = accounts.get(f"{sym}|{fy}")
            eligible += 1
            if not a or not a.get("accepted"):
                continue
            accepted += 1
            months = formation_months(a.get("year_end") or f"{fy}-03-31")
            q = quality_score(a)
            for ym in months:
                if ym < FIRST_FORMATION:
                    continue
                p = (prices.get(sym) or {}).get(ym)
                if not p or not p.get("fwd"):
                    continue
                v = value_score(a, p.get("close"), p.get("share_factor"))
                for factor, sc in (("value", v), ("quality", q)):
                    if sc is not None:
                        out[factor].setdefault(ym, []).append((sym, sc, p["fwd"]))
    return out, {"eligible_company_years": eligible, "accepted_company_years": accepted,
                 "coverage": (accepted / eligible) if eligible else 0.0}


def monthly_spreads(by_month, h, rng=None):
    """Top-minus-bottom group excess return per month for horizon h. With rng, scores are
    shuffled within each month first (the placebo)."""
    spreads = []
    for ym in sorted(by_month):
        rows = [(s, sc, fwd.get(str(h))) for s, sc, fwd in by_month[ym] if fwd.get(str(h)) is not None]
        if len(rows) < MIN_SCORED:
            continue
        scores = [r[1] for r in rows]
        if rng is not None:
            rng.shuffle(scores)
        rets = np.array([r[2] for r in rows], dtype=float)
        excess = rets - rets.mean()
        order = np.argsort(np.array(scores), kind="mergesort")
        groups = np.array_split(order, N_GROUPS)
        spreads.append((ym, float(excess[groups[-1]].mean() - excess[groups[0]].mean())))
    return spreads


def test(scores, horizons=HORIZONS):
    res = {}
    for factor in ("value", "quality"):
        for h in horizons:
            sp = monthly_spreads(scores[factor], h)
            nonoverlap = len(sp) // h
            r = newey_west_t([s for _, s in sp], lag=h - 1) if nonoverlap >= 3 else None
            key = f"{factor}_{h}m"
            if r is None:
                res[key] = {"usable": False, "months": len(sp)}
                continue
            verdict = ("demonstrated edge" if r["p"] is not None and r["p"] < LEVEL and r["mean"] > 0 else
                       "reversed" if r["p"] is not None and r["p"] < LEVEL and r["mean"] < 0 else
                       "no demonstrated edge")
            res[key] = {"usable": True, "months": len(sp), "mean_spread_pct": round(r["mean"] * 100, 3),
                        "nw_t": r["t"] and round(r["t"], 3), "p": r["p"] and round(r["p"], 5),
                        "min_detectable_pct": round(min_detectable(r["se"]) * 100, 3), "verdict": verdict}
    return res


def placebo(scores, draws=PLACEBO_DRAWS, seed=20260926):
    """Scores shuffled within each month, `draws` times: the machinery must give about zero."""
    rng = random.Random(seed)
    out = {}
    for factor in ("value", "quality"):
        for h in HORIZONS:
            means = []
            for _ in range(draws):
                sp = monthly_spreads(scores[factor], h, rng=rng)
                if sp:
                    means.append(float(np.mean([s for _, s in sp])))
            if means:
                out[f"{factor}_{h}m"] = {"draws": len(means), "mean_of_means_pct": round(float(np.mean(means)) * 100, 4),
                                         "sd_of_means_pct": round(float(np.std(means)) * 100, 4)}
    return out


# ------------------------------------------------------------------ entry point

def load(input_dir):
    j = lambda f: json.load(open(os.path.join(input_dir, f), encoding="utf-8"))
    return j("accounts.json"), j("universe.json"), j("prices.json"), j("meta.json")


def main():
    mode, input_dir = sys.argv[1], sys.argv[2]
    accounts, universe, prices, meta = load(input_dir)
    scores, cov = build_scores(accounts, universe, prices)
    report = {"mode": mode, "meta": meta, "coverage": cov}
    if mode == "placebo":
        report["placebo"] = placebo(scores)
    elif mode == "run":
        if cov["coverage"] < COVERAGE_GATE:
            report["result"] = "insufficient data: coverage below the prereg's 80% gate; tests not run"
        else:
            report["tests"] = test(scores)
            report["placebo"] = placebo(scores)
    else:
        raise SystemExit("mode must be placebo or run")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
