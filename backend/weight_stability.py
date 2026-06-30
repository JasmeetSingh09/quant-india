"""
Are the alpha-model factor weights STABLE across time, or just noise?

The critique: "you fitted weights on only 2019-2022 — why not more data?"
The honest test: refit the factor weights (momentum / quality / value) on several
DIFFERENT historical windows and see whether they agree. If they jump around or
flip sign period-to-period, the exact weights are noise and shouldn't be trusted
to 2 decimals — which is itself an honest, valuable finding.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "modules"))
import numpy as np
from alpha_model import retrain_weights

TICKERS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
           "ITC.NS", "SBIN.NS", "LT.NS", "SUNPHARMA.NS", "HINDUNILVR.NS"]

WINDOWS = [
    ("2012-01-01", "2015-12-31"),
    ("2015-01-01", "2018-12-31"),
    ("2018-01-01", "2021-12-31"),
    ("2021-01-01", "2024-12-31"),
    ("2012-01-01", "2024-12-31"),   # full history
]


def run():
    print("Refitting factor weights on different time windows...\n")
    rows = []
    print(f"{'Window':24s} {'momentum':>10s} {'quality':>10s} {'value':>10s} {'R^2':>7s}  significant")
    for start, end in WINDOWS:
        r = retrain_weights(TICKERS, start_date=start, end_date=end)
        if "error" in r:
            print(f"{start[:7]}..{end[:7]:8s}  {r['error']}")
            continue
        f = r["fitted_factors"]
        mom, qual, val = f["momentum"], f["quality"], f["value"]
        sig = [k for k in ("momentum", "quality", "value") if f[k]["significant"]]
        label = f"{start[:7]}..{end[:7]}" + ("  (FULL)" if start == "2012-01-01" and end == "2024-12-31" else "")
        print(f"{label:24s} {mom['coefficient']:+10.3f} {qual['coefficient']:+10.3f} "
              f"{val['coefficient']:+10.3f} {r['r_squared']:7.3f}  {','.join(sig) or 'none'}")
        rows.append((mom["coefficient"], qual["coefficient"], val["coefficient"], r["r_squared"]))

    if len(rows) >= 3:
        sub = np.array(rows[:-1])     # exclude full-history row from the spread
        print("\n=== STABILITY ACROSS THE 4 SUB-PERIODS ===")
        for j, name in enumerate(["momentum", "quality", "value"]):
            col = sub[:, j]
            flips = "YES" if (col.min() < 0 < col.max()) else "no"
            print(f"  {name:9s}: range [{col.min():+.3f}, {col.max():+.3f}], "
                  f"std {col.std():.3f}, sign flips across periods: {flips}")
        avg_r2 = sub[:, 3].mean()
        print(f"\n  average R^2 across periods: {avg_r2:.3f}")
        print("\nVERDICT:")
        if avg_r2 < 0.03:
            print("  R^2 is near zero -> the factors barely explain forward returns AT ALL.")
        flips_any = any((sub[:, j].min() < 0 < sub[:, j].max()) for j in range(3))
        if flips_any:
            print("  Coefficients FLIP SIGN across periods -> the precise weights are NOT")
            print("  stable; they are essentially noise. Honest conclusion: trust the FOUR")
            print("  FACTORS as sensible, but do NOT over-trust the exact 0.35/0.25 weights.")
        else:
            print("  Coefficients keep their sign -> reasonably stable; weights are meaningful.")


if __name__ == "__main__":
    run()
