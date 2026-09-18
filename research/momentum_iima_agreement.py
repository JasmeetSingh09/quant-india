"""
momentum_iima_agreement.py: H3 of docs/PREREG_MOMENTUM_ROBUSTNESS_2026-09-17.md.

Does our monthly 12-1 momentum spread (top fifth minus bottom fifth, from
GET /validation/pit at the default floor) move with IIMA's independently built
WML factor?

Alignment: our spread is keyed by the FORMATION month m and measures the
return over the next month; IIMA's WML for month t is the return earned during
month t. So our month m is paired with IIMA month m + 1: the month in which
both returns were earned.

    python research/momentum_iima_agreement.py <validation_pit.json> <iima_monthly_adjusted.csv> [out.json]
"""

import csv
import json
import math
import sys

import numpy as np
from scipy import stats

NW_LAGS = 6
ALPHA_EACH = 0.05 / 3        # three primary tests in the pre-registration


def next_month(m):
    y, mo = int(m[:4]), int(m[5:7])
    return f"{y + (mo == 12)}-{1 if mo == 12 else mo + 1:02d}"


def load_ours(path):
    d = json.load(open(path))
    rows = d["track_a"]["factors"]["momentum"]["horizons"]["1m"]["top_minus_bottom"]["monthly"]
    return {next_month(r["month"]): r["spread_pct"] for r in rows}


def load_wml(path):
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["WML"] not in ("NA", ""):
                out[r["Date"]] = float(r["WML"])
    return out


def ols_nw(y, x, lags=NW_LAGS):
    """y = a + b x; Newey-West (Bartlett) standard errors for a and b."""
    n = len(y)
    X = np.column_stack([np.ones(n), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    u = y - X @ beta
    xu = X * u[:, None]
    S = xu.T @ xu / n
    for lag in range(1, lags + 1):
        w = 1 - lag / (lags + 1)
        g = xu[lag:].T @ xu[:-lag] / n
        S += w * (g + g.T)
    XtX_inv = np.linalg.inv(X.T @ X / n)
    cov = XtX_inv @ S @ XtX_inv / n
    se = np.sqrt(np.diag(cov))
    t = beta / se
    p = [math.erfc(abs(v) / math.sqrt(2)) for v in t]
    return {"intercept_pct_per_month": round(float(beta[0]), 4), "intercept_t": round(float(t[0]), 3),
            "intercept_p": round(p[0], 6), "slope": round(float(beta[1]), 4),
            "slope_t": round(float(t[1]), 3), "slope_p": round(p[1], 6), "nw_lags": lags}


def main():
    ours, wml = load_ours(sys.argv[1]), load_wml(sys.argv[2])
    common = sorted(set(ours) & set(wml))
    a = np.array([ours[m] for m in common])
    b = np.array([wml[m] for m in common])
    r, _ = stats.pearsonr(a, b)
    n = len(common)
    t = r * math.sqrt((n - 2) / (1 - r * r))
    p = float(2 * stats.t.sf(abs(t), df=n - 2))
    out = {
        "preregistration": "docs/PREREG_MOMENTUM_ROBUSTNESS_2026-09-17.md (H3)",
        "alignment": "our formation month m paired with IIMA month m+1 (the month both returns were earned)",
        "months": n, "first_return_month": common[0], "last_return_month": common[-1],
        "H3": {"pearson_r": round(float(r), 4), "t": round(t, 3), "p_two_sided": round(p, 6),
               "alpha": round(ALPHA_EACH, 5), "passes": bool(r > 0 and p < ALPHA_EACH)},
        "secondary_regression_ours_on_wml": ols_nw(a, b),
        "means_pct_per_month": {"ours": round(float(a.mean()), 4), "iima_wml": round(float(b.mean()), 4)},
    }
    text = json.dumps(out, indent=2)
    if len(sys.argv) > 3:
        open(sys.argv[3], "w").write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
