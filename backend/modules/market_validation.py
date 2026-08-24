"""
market_validation.py — does the model work across the market, or only where
we happened to look?

The track record already refuses to count 780 overlapping observations as 780
pieces of evidence: it selects a non-overlapping subset per stock and judges on
that. This module takes the next two steps, both of which the existing code
names as open problems without solving.

First, cross-stock clustering. Observations of thirty different stocks on the
same day are not thirty independent draws — they mostly measure whether the
market went up that day. The existing comment says exactly this and then treats
different stocks as independent anyway, because quantifying it is harder than
flagging it. Here it is quantified with a design effect estimated from the data.

Second, stratification. An aggregate hit rate can be positive because the model
works everywhere, or because it works in large-cap IT and is carried by the
weight of those observations. Those are different findings and the aggregate
cannot tell them apart, so results are reported per market-cap bucket, per
sector, and per signal bucket.

What this can and cannot validate
---------------------------------
It validates FORWARD predictions: a score logged on a date, graded against what
actually happened afterwards. That has no look-ahead problem, which is what
makes it the only honest route to evidence about quality, growth, value and
sentiment — those read current fundamentals and therefore cannot be backtested
historically at all.

The cost is time. Evidence accumulates at the speed of the market, and cannot
be manufactured by resampling what is already there. Today the answer will
almost certainly be INSUFFICIENT EVIDENCE, and reporting that clearly is the
purpose rather than a failure of it.
"""

import math
from collections import defaultdict
from datetime import datetime


# Signal buckets, ordered worst to best. Monotonicity is checked against this
# order: if Strong Buy does not beat Buy, the score is not carrying information
# even when the aggregate looks positive.
BUCKET_ORDER = ["Strong Sell", "Sell", "Neutral", "Buy", "Strong Buy"]

# Coverage a result must clear before it may be called anything better than
# preliminary. These are stated here rather than tuned to whatever the data
# happens to contain.
MIN_INDEPENDENT_PER_STRATUM = 30
MIN_SECTORS = 5
MIN_CAP_BUCKETS = 3
MIN_INDEPENDENT_TOTAL = 200
MIN_DISTINCT_DATES = 20


def _bucket_for_score(score):
    """Five buckets from the alpha score. Thresholds match the signal labels
    the app already shows, so a user sees the same words in both places."""
    if score is None:
        return None
    if score <= -30:
        return "Strong Sell"
    if score <= -10:
        return "Sell"
    if score < 10:
        return "Neutral"
    if score < 30:
        return "Buy"
    return "Strong Buy"


def _cap_bucket(market_cap):
    """
    Large / Mid / Small by rupee market capitalisation.

    SEBI defines these by RANK (top 100, next 150, rest), which is the correct
    definition and needs a full ranked universe on the day. Where only a cap
    figure is available these thresholds approximate it, and the difference is
    disclosed rather than hidden: a stock near a boundary may land in the wrong
    bucket.
    """
    if market_cap is None or market_cap <= 0:
        return None
    cr = market_cap / 1e7          # rupees -> crore
    if cr >= 50000:
        return "Large"
    if cr >= 15000:
        return "Mid"
    return "Small"


def _wilson(hits, n, z=1.96):
    """Wilson interval — behaves at small n and near 0 or 1, unlike the normal
    approximation, and small n is the case this module exists to report."""
    if not n:
        return None
    p = hits / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round((centre - half) * 100, 1), round((centre + half) * 100, 1)]


def _binom_p(hits, n, p0=0.5):
    """Two-sided binomial test. Falls back to a normal approximation only if
    scipy is unavailable, and says which was used."""
    if not n:
        return None, None
    try:
        from scipy import stats
        return float(stats.binomtest(hits, n, p0).pvalue), "exact binomial"
    except Exception:
        se = math.sqrt(p0 * (1 - p0) / n)
        if se == 0:
            return None, None
        z = (hits / n - p0) / se
        try:
            from math import erfc
            return float(erfc(abs(z) / math.sqrt(2))), "normal approximation"
        except Exception:
            return None, None


def _non_overlapping(records, horizon_days):
    """Per stock, keep observations separated by at least one full horizon."""
    by_t = defaultdict(list)
    for r in records:
        by_t[r["ticker"]].append(r)
    keep = []
    for t, rows in by_t.items():
        rows = sorted(rows, key=lambda r: r["date"])
        last = None
        for r in rows:
            try:
                d = datetime.strptime(r["date"][:10], "%Y-%m-%d")
            except Exception:
                continue
            if last is None or (d - last).days >= horizon_days:
                keep.append(r)
                last = d
    return keep


def _design_effect(records):
    """
    How much the same-day clustering costs in effective sample size.

    Observations sharing a date share the market's move that day, so they are
    not independent draws. The standard correction is

        DEFF = 1 + (m - 1) * rho
        N_eff = N / DEFF

    where m is the average cluster size and rho the intra-cluster correlation
    of the outcome. rho is ESTIMATED FROM THE DATA here, by a one-way ANOVA
    decomposition of the hit indicator across date clusters, rather than
    assumed. When it cannot be estimated the function says so and applies no
    correction, because inventing a rho would be worse than leaving the
    inflation visible.
    """
    by_date = defaultdict(list)
    for r in records:
        hit = r.get("_hit")
        if hit is None:
            continue
        by_date[r["date"][:10]].append(1.0 if hit else 0.0)

    clusters = [v for v in by_date.values() if v]
    n = sum(len(v) for v in clusters)
    k = len(clusters)
    if k < 2 or n < 10:
        return {"deff": 1.0, "rho": None, "mean_cluster_size": (n / k) if k else 0,
                "n_clusters": k, "estimable": False,
                "note": ("Too few dates to estimate clustering, so no correction "
                         "is applied. The independent count is therefore an "
                         "upper bound on real independence.")}

    grand = sum(sum(v) for v in clusters) / n
    # Between-cluster and within-cluster mean squares.
    ss_between = sum(len(v) * (sum(v) / len(v) - grand) ** 2 for v in clusters)
    ss_within = sum(sum((x - sum(v) / len(v)) ** 2 for x in v) for v in clusters)
    df_b, df_w = k - 1, n - k
    if df_b <= 0 or df_w <= 0:
        return {"deff": 1.0, "rho": None, "mean_cluster_size": n / k,
                "n_clusters": k, "estimable": False,
                "note": "Degrees of freedom too small to estimate clustering."}
    ms_b, ms_w = ss_between / df_b, ss_within / df_w
    m0 = (n - sum(len(v) ** 2 for v in clusters) / n) / (k - 1)
    if m0 <= 0 or (ms_b + (m0 - 1) * ms_w) == 0:
        rho = 0.0
    else:
        rho = (ms_b - ms_w) / (ms_b + (m0 - 1) * ms_w)
    # A negative estimate means less within-date similarity than chance, which
    # is not evidence of negative clustering at these sample sizes.
    rho = max(0.0, min(1.0, rho))
    m = n / k
    deff = 1 + (m - 1) * rho
    return {"deff": round(deff, 3), "rho": round(rho, 4),
            "mean_cluster_size": round(m, 2), "n_clusters": k, "estimable": True,
            "note": ("Observations sharing a date share that day's market move. "
                     "rho is the intra-date correlation of the hit indicator, "
                     "estimated from these observations by ANOVA, not assumed.")}


def _stats_for(rows, label):
    """Hit rate, returns and interval for one group. `_hit` is set by caller."""
    graded = [r for r in rows if r.get("_hit") is not None]
    n = len(graded)
    if not n:
        return {"group": label, "n_independent": 0, "insufficient": True}
    hits = sum(1 for r in graded if r["_hit"])
    exc = [r["excess_pct"] for r in graded if r.get("excess_pct") is not None]
    fwd = [r["forward_return_pct"] for r in graded
           if r.get("forward_return_pct") is not None]
    p, method = _binom_p(hits, n)
    exc_sorted = sorted(exc)
    return {
        "group": label,
        "n_independent": n,
        "hit_rate_pct": round(hits / n * 100, 1),
        "hit_ci_95": _wilson(hits, n),
        "avg_excess_pct": round(sum(exc) / len(exc), 3) if exc else None,
        "median_excess_pct": (round(exc_sorted[len(exc_sorted) // 2], 3)
                              if exc_sorted else None),
        "avg_forward_pct": round(sum(fwd) / len(fwd), 3) if fwd else None,
        "p_value": round(p, 4) if p is not None else None,
        "p_method": method,
        "significant_at_5pct": (p is not None and p < 0.05),
        # A stratum below the floor is reported, never suppressed, but it is
        # marked so nobody reads a 71% hit rate off eleven observations.
        "insufficient": n < MIN_INDEPENDENT_PER_STRATUM,
    }


def validate(min_days: int = 21, records: list = None) -> dict:
    """
    Stratified market-wide validation of the live forward track record.

    Pass `records` to validate a supplied set; otherwise the graded predictions
    are read from the tracker.
    """
    if records is None:
        try:
            from prediction_tracker import evaluate
            ev = evaluate(min_days=min_days) or {}
            # The tracker returns these under "predictions". Reading "records"
            # returned an empty list and reported "no graded predictions yet",
            # which is indistinguishable from a genuine empty record — the same
            # silent key mismatch that dropped Black-Litterman from the strategy
            # comparison. Both names are accepted so neither side can break it
            # again, and an unrecognised shape says so instead of reporting
            # emptiness.
            records = ev.get("predictions")
            if records is None:
                records = ev.get("records")
            if records is None:
                return {"available": False,
                        "reason": ("The track record returned a shape this "
                                   "validator does not recognise "
                                   f"(keys: {sorted(ev.keys())}). Reporting that "
                                   "rather than an empty sample, because the two "
                                   "look identical and mean opposite things.")}
        except Exception as e:
            return {"available": False,
                    "reason": f"Could not load the track record ({type(e).__name__})."}

    if not records:
        return {"available": False,
                "reason": ("No graded predictions yet. Evidence accumulates at "
                           "the speed of the market: a score logged today can "
                           "only be graded once its horizon has actually "
                           "passed, and nothing about that can be hurried."),
                "raw_observations": 0}

    # --- attach the outcome, the cap bucket and the sector -----------------
    caps, sectors = _lookup_caps_and_sectors({r["ticker"] for r in records})

    for r in records:
        # A "hit" is direction agreement against the benchmark, not a positive
        # return: a BUY that rises 1% while the index rises 3% got it wrong.
        exc = r.get("excess_pct")
        sig = (r.get("signal") or "").upper()
        if exc is None or sig not in ("BUY", "SELL"):
            r["_hit"] = None
        else:
            r["_hit"] = (exc > 0) if sig == "BUY" else (exc < 0)
        r["_cap"] = _cap_bucket(caps.get(r["ticker"]))
        r["_sector"] = sectors.get(r["ticker"])
        r["_bucket"] = _bucket_for_score(r.get("alpha_score"))

    raw_n = len(records)
    indep = _non_overlapping(records, min_days)
    deff = _design_effect(indep)
    n_graded = len([r for r in indep if r.get("_hit") is not None])
    n_eff = int(n_graded / deff["deff"]) if deff["deff"] > 0 else n_graded

    overall = _stats_for(indep, "All stocks")

    by_cap = [_stats_for([r for r in indep if r["_cap"] == c], c)
              for c in ("Large", "Mid", "Small")]
    sector_names = sorted({r["_sector"] for r in indep if r["_sector"]})
    by_sector = [_stats_for([r for r in indep if r["_sector"] == s], s)
                 for s in sector_names]
    by_bucket = [_stats_for([r for r in indep if r["_bucket"] == b], b)
                 for b in BUCKET_ORDER]

    mono = _monotonicity(by_bucket)
    coverage = _coverage(indep, by_cap, by_sector, n_graded)
    checklist, verdict = _checklist(overall, coverage, mono, deff, n_graded)

    return {
        "available": True,
        "horizon_days": min_days,
        "sample": {
            "raw_observations": raw_n,
            "independent_windows": len(indep),
            "graded_independent": n_graded,
            "effective_sample_size": n_eff,
            "unique_stocks": len({r["ticker"] for r in records}),
            "distinct_dates": len({r["date"][:10] for r in records}),
            "sectors_covered": len(sector_names),
            "design_effect": deff,
            "why_these_differ": (
                f"{raw_n} raw observations become {len(indep)} once windows that "
                f"share days for the same stock are removed, and about {n_eff} "
                f"once same-day clustering across stocks is accounted for. Only "
                f"the last number is evidence; the first is a row count."),
        },
        "overall": overall,
        "by_market_cap": by_cap,
        "by_sector": by_sector,
        "by_signal_bucket": by_bucket,
        "monotonicity": mono,
        "coverage": coverage,
        "checklist": checklist,
        "verdict": verdict,
        "limits": (
            "Forward-graded predictions only, so there is no look-ahead here — "
            "but also no history before the day logging started, and it cannot "
            "be backfilled. Market-cap buckets use rupee thresholds rather than "
            "the SEBI rank definition, so stocks near a boundary may sit in the "
            "wrong one. Different stocks on the same day are corrected for by "
            "design effect, not eliminated."),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _lookup_caps_and_sectors(tickers):
    caps, sectors = {}, {}
    try:
        from db import get_conn
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT ticker, market_cap FROM alpha_scan2 "
                "WHERE market_cap IS NOT NULL").fetchall()
            for t, mc in rows:
                if t in tickers:
                    caps[t] = mc
        finally:
            conn.close()
    except Exception:
        pass
    # Sector comes from the STATIC map only, never a per-ticker lookup.
    # portfolio_advisor._sector_of falls back to get_company_info, which fetches
    # over the network for anything uncached — fine for one portfolio, fatal
    # here: validating across 2,500 stocks would make 2,500 requests, and the
    # first run of this test suite fired several hundred 404s against synthetic
    # tickers before anything was measured.
    #
    # A ticker absent from the map has no sector, so it contributes to the
    # overall figures and to its cap bucket but not to any sector row. That is
    # the honest handling: unknown, not guessed.
    try:
        from data_fetcher import NSE_SECTORS
        flat = {}
        for sector, members in NSE_SECTORS.items():
            for m in members:
                flat[str(m).strip().upper()] = sector
        for t in tickers:
            sectors[t] = flat.get(str(t).strip().upper())
    except Exception:
        pass
    return caps, sectors


def _monotonicity(by_bucket):
    """
    Does a stronger score actually mean a better outcome?

    This is the question the aggregate hit rate cannot answer. A model can be
    right more often than not while its Strong Buy calls do worse than its Buy
    calls, which means the score is not carrying the information the app
    presents it as carrying.
    """
    usable = [b for b in by_bucket
              if b.get("n_independent", 0) >= MIN_INDEPENDENT_PER_STRATUM
              and b.get("avg_excess_pct") is not None]
    if len(usable) < 3:
        return {"testable": False,
                "reason": (f"Fewer than three signal buckets have "
                           f"{MIN_INDEPENDENT_PER_STRATUM}+ independent "
                           f"observations, so ordering cannot be tested yet."),
                "buckets_with_enough": len(usable)}
    order = {b: i for i, b in enumerate(BUCKET_ORDER)}
    usable.sort(key=lambda b: order[b["group"]])
    vals = [b["avg_excess_pct"] for b in usable]
    increasing = all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))
    return {
        "testable": True,
        "monotonic": increasing,
        "sequence": [{"bucket": b["group"], "avg_excess_pct": b["avg_excess_pct"],
                      "n": b["n_independent"]} for b in usable],
        "verdict": ("Excess return rises with the score across the buckets that "
                    "have enough observations."
                    if increasing else
                    "Excess return does NOT rise consistently with the score. "
                    "A higher score did not mean a better outcome, which is a "
                    "problem with the score rather than with this test."),
    }


def _coverage(indep, by_cap, by_sector, n_graded):
    caps_ok = [c for c in by_cap
               if c.get("n_independent", 0) >= MIN_INDEPENDENT_PER_STRATUM]
    secs_ok = [s for s in by_sector
               if s.get("n_independent", 0) >= MIN_INDEPENDENT_PER_STRATUM]
    dates = len({r["date"][:10] for r in indep})
    return {
        "cap_buckets_with_enough": len(caps_ok),
        "cap_buckets_needed": MIN_CAP_BUCKETS,
        "sectors_with_enough": len(secs_ok),
        "sectors_needed": MIN_SECTORS,
        "distinct_dates": dates,
        "dates_needed": MIN_DISTINCT_DATES,
        "graded_independent": n_graded,
        "independent_needed": MIN_INDEPENDENT_TOTAL,
        "per_stratum_floor": MIN_INDEPENDENT_PER_STRATUM,
    }


def _checklist(overall, coverage, mono, deff, n_graded):
    """
    A transparent list of what passed, not a score.

    A single number like "robustness 94/100" would hide exactly the trade-offs
    that matter and invite tuning until it looks good. Every line here is
    checkable against the tables above it.
    """
    items = [
        ("Independent sample", n_graded >= MIN_INDEPENDENT_TOTAL,
         f"{n_graded} graded independent windows, need {MIN_INDEPENDENT_TOTAL}"),
        ("Market-cap coverage",
         coverage["cap_buckets_with_enough"] >= MIN_CAP_BUCKETS,
         f"{coverage['cap_buckets_with_enough']} of {MIN_CAP_BUCKETS} buckets "
         f"have {MIN_INDEPENDENT_PER_STRATUM}+ observations"),
        ("Sector coverage", coverage["sectors_with_enough"] >= MIN_SECTORS,
         f"{coverage['sectors_with_enough']} of {MIN_SECTORS} sectors qualify"),
        ("Time coverage", coverage["distinct_dates"] >= MIN_DISTINCT_DATES,
         f"{coverage['distinct_dates']} distinct dates, need {MIN_DISTINCT_DATES}"),
        ("Clustering accounted for", deff.get("estimable", False),
         deff.get("note", "")[:80]),
        ("No look-ahead", True,
         "Forward-graded only: every score was logged before its outcome existed"),
        ("Statistical evidence", bool(overall.get("significant_at_5pct")),
         f"p = {overall.get('p_value')} on the independent sample"),
        ("Score monotonicity", bool(mono.get("monotonic")),
         mono.get("verdict", mono.get("reason", ""))[:80]),
    ]
    checklist = [{"criterion": c, "passed": bool(p), "detail": d}
                 for c, p, d in items]
    passed = sum(1 for c in checklist if c["passed"])

    required = ("Independent sample", "Market-cap coverage", "Sector coverage",
                "Time coverage", "Statistical evidence", "Score monotonicity")
    all_required = all(c["passed"] for c in checklist
                       if c["criterion"] in required)

    if n_graded < MIN_INDEPENDENT_TOTAL:
        verdict = "INSUFFICIENT EVIDENCE"
    elif all_required:
        verdict = "ROBUST OUT-OF-SAMPLE EVIDENCE"
    elif passed >= 6:
        verdict = "PROMISING"
    else:
        verdict = "PRELIMINARY"

    return checklist, {
        "label": verdict,
        "passed": passed,
        "total": len(checklist),
        "means": {
            "INSUFFICIENT EVIDENCE": (
                "Not enough independent observations to say anything. This is "
                "the expected answer early on and it is not a failure of the "
                "model — it is the absence of a test."),
            "PRELIMINARY": (
                "Some evidence exists but coverage or significance is missing. "
                "Nothing here should be described as validated."),
            "PROMISING": (
                "Most criteria pass. Still not a validated edge: the remaining "
                "failures are the ones that would matter most."),
            "ROBUST OUT-OF-SAMPLE EVIDENCE": (
                "Every required criterion passed on forward-graded, "
                "non-overlapping observations across caps, sectors and dates."),
        }[verdict],
    }
