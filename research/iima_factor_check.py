"""
iima_factor_check.py: the pre-registered check in
docs/IIMA_FACTOR_CHECK_PREREG_2026-09-17.md.

Did the momentum (WML) and value (HML) premiums exist in Indian equities, on
IIMA's independently built factor library? Nothing here touches our own code
or scores.

Data: Agarwalla, S. K., Jacob, J. and Varma, J. R. (2013), Four factor model in
Indian equities market, W.P. No. 2013-09-05, IIM Ahmedabad.
https://faculty.iima.ac.in/iffm/Indian-Fama-French-Momentum/

Raw files are not committed. They are downloaded into DATA_DIR (first
argument) and their SHA-256 is recorded in the output.

    python research/iima_factor_check.py <data_dir> [out.json]
"""

import csv
import hashlib
import json
import math
import os
import sys
import urllib.request

BASE = "https://faculty.iima.ac.in/iffm/Indian-Fama-French-Momentum/DATA/"
ADJUSTED = "2025-12_FourFactors_and_Market_Returns_Monthly_SurvivorshipBiasAdjusted.csv"
UNADJUSTED = "2025-12_FourFactors_and_Market_Returns_Monthly.csv"
NW_LAGS = 6
ALPHA_EACH = 0.05 / 2           # two primary tests, Bonferroni
SPLIT = "2012-12"               # last month of the first subperiod


def fetch(data_dir, name):
    path = os.path.join(data_dir, name)
    if not os.path.exists(path):
        urllib.request.urlretrieve(BASE + name, path)
    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    return path, sha


def load(path):
    rows = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows[r["Date"]] = {k: (None if v in ("NA", "") else float(v))
                               for k, v in r.items() if k != "Date"}
    return rows


def series(rows, col, start=None, end=None):
    return [(d, v[col]) for d, v in sorted(rows.items())
            if v[col] is not None and (start is None or d >= start)
            and (end is None or d <= end)]


def newey_west_mean(xs, lags=NW_LAGS):
    """Mean, Newey-West standard error of the mean (Bartlett weights), t, p."""
    n = len(xs)
    m = sum(xs) / n
    dev = [x - m for x in xs]
    lrv = sum(d * d for d in dev) / n
    for lag in range(1, min(lags, n - 1) + 1):
        g = sum(dev[t] * dev[t - lag] for t in range(lag, n)) / n
        lrv += 2 * (1 - lag / (lags + 1)) * g
    se = math.sqrt(lrv / n) if lrv > 0 else None
    t = m / se if se else None
    p = math.erfc(abs(t) / math.sqrt(2)) if t is not None else None
    return {"n": n, "mean_pct_per_month": round(m, 4),
            "nw_se": round(se, 4) if se else None, "nw_lags": lags,
            "t_stat": round(t, 3) if t is not None else None,
            "p_two_sided": round(p, 6) if p is not None else None}


def describe(pairs):
    xs = [v for _, v in pairs]
    level, peak, worst = 1.0, 1.0, 0.0
    years = {}
    for d, v in pairs:
        level *= 1 + v / 100
        peak = max(peak, level)
        worst = min(worst, level / peak - 1)
        years[d[:4]] = years.get(d[:4], 1.0) * (1 + v / 100)
    full_years = {y: g for y, g in years.items()
                  if sum(1 for d, _ in pairs if d[:4] == y) == 12}
    months = len(xs)
    return {
        "first_month": pairs[0][0], "last_month": pairs[-1][0],
        "arithmetic_mean_annualised_pct": round(sum(xs) / months * 12, 2),
        "compound_annual_pct": round((level ** (12 / months) - 1) * 100, 2),
        "full_calendar_years": len(full_years),
        "positive_years": sum(1 for g in full_years.values() if g > 1),
        "worst_drawdown_pct": round(worst * 100, 1),
    }


def main():
    data_dir = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None
    os.makedirs(data_dir, exist_ok=True)
    adj_path, adj_sha = fetch(data_dir, ADJUSTED)
    raw_path, raw_sha = fetch(data_dir, UNADJUSTED)
    adj, raw = load(adj_path), load(raw_path)

    primary = {}
    for label, col in (("P1_momentum_WML", "WML"), ("P2_value_HML", "HML")):
        res = newey_west_mean([v for _, v in series(adj, col)])
        res["passes"] = (res["mean_pct_per_month"] > 0
                         and res["p_two_sided"] is not None
                         and res["p_two_sided"] < ALPHA_EACH)
        primary[label] = res

    secondary = {"subperiods": {}, "descriptive": {}, "published_only": {},
                 "adjusted_minus_unadjusted_mean_pct": {}}
    for col in ("WML", "HML"):
        secondary["subperiods"][col] = {
            "1993-10_to_2012-12": newey_west_mean(
                [v for _, v in series(adj, col, end=SPLIT)]),
            "2013-01_to_2025-12": newey_west_mean(
                [v for _, v in series(adj, col, start="2013-01")]),
        }
        secondary["descriptive"][col] = describe(series(adj, col))
        a = [v for _, v in series(adj, col)]
        r = [v for _, v in series(raw, col)]
        secondary["adjusted_minus_unadjusted_mean_pct"][col] = round(
            sum(a) / len(a) - sum(r) / len(r), 4)
    for col in ("SMB", "MF"):
        secondary["published_only"][col] = {
            **newey_west_mean([v for _, v in series(adj, col)]),
            **describe(series(adj, col))}

    out = {
        "preregistration": "docs/IIMA_FACTOR_CHECK_PREREG_2026-09-17.md",
        "source": ("Agarwalla, S. K., Jacob, J. and Varma, J. R. (2013), Four factor "
                   "model in Indian equities market, W.P. No. 2013-09-05, IIM Ahmedabad"),
        "files": {ADJUSTED: adj_sha, UNADJUSTED: raw_sha},
        "alpha_each": ALPHA_EACH,
        "primary": primary,
        "secondary": secondary,
        "limits": [
            "IIMA recomputes the library from each Prowess release; past accounts "
            "are today's view, not as first published.",
            "Value-weighted, total returns with dividends, no trading costs: a "
            "different construction from every Quant India backtest.",
            "Tests the ideas behind momentum and value, not Quant India's scoring.",
        ],
    }
    text = json.dumps(out, indent=2)
    if out_path:
        with open(out_path, "w") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
