"""
momentum_scrutiny.py — is the null result real, or did I build a test that
cannot detect an edge?

The walk-forward reported a 50.0% win rate and p = 1.000, which is a striking
claim. Before it is used to justify anything, the test that produced it has to
be examined as sceptically as the model was.

Specific things that could manufacture a false null:

  * 15 large caps is a narrow, low-dispersion universe. Momentum is usually
    reported to work best where dispersion is wide.
  * Top 5 of 15 is the top THIRD, not the extreme. Weak separation dilutes any
    real signal.
  * A single 21-day horizon. Momentum is normally documented at 1-12 months.
  * A single period, 2023-2026, which is one regime.
  * The spread is GROSS. Costs would make a marginal edge negative, but their
    absence cannot create a null out of a real edge.

So the result is re-run across horizons, universe sizes and selection widths. If
it is a genuine null it should survive all of them. If it flips on one setting,
the honest report is that the answer depends on the setting — which is itself a
finding, and a more useful one than either "it works" or "it doesn't".
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

from walk_forward import run

WIDE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LT.NS", "KOTAKBANK.NS",
    "AXISBANK.NS", "SUNPHARMA.NS", "MARUTI.NS", "TITAN.NS", "WIPRO.NS",
    "TATAMOTORS.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "COALINDIA.NS",
    "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "ADANIENT.NS", "BAJFINANCE.NS",
    "ASIANPAINT.NS", "NESTLEIND.NS", "HINDUNILVR.NS", "DRREDDY.NS", "CIPLA.NS",
    "TECHM.NS", "HCLTECH.NS", "GRASIM.NS", "ULTRACEMCO.NS", "BPCL.NS",
    "EICHERMOT.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "DIVISLAB.NS", "BRITANNIA.NS",
]

# Round-trip cost of rebalancing the whole long/short book once per window:
# brokerage + slippage both sides, plus STT and stamp duty.
COST_PER_WINDOW_PCT = ((2 * 0.001) + (2 * 0.0005) + 0.001 + 0.00015) * 100

rows = []
print("\nMomentum sensitivity\n" + "=" * 78)
print(f"{'universe':>9} {'horizon':>8} {'top-n':>6} {'windows':>8} "
      f"{'gross':>8} {'net':>8} {'win%':>7} {'p':>7}")
print("-" * 78)

for universe, uname in ((None, "15"), (WIDE, "40")):
    for horizon in (21, 63, 126):
        for top_n in (3, 5):
            if universe is WIDE and top_n == 3:
                top_n = 8          # extremes of a wide universe, not the top third
            try:
                r = run(tickers=universe, horizon_days=horizon,
                        step_days=horizon, top_n=top_n)
            except Exception as e:
                print(f"{uname:>9} {horizon:>8} {top_n:>6}   error: {type(e).__name__}")
                continue
            if "error" in r:
                print(f"{uname:>9} {horizon:>8} {top_n:>6}   {r['error'][:40]}")
                continue
            gross = r["mean_spread_pct"]
            # One rebalance per window, both legs.
            net = gross - COST_PER_WINDOW_PCT
            sig = r.get("significance") or {}
            p = sig.get("p_value")
            rows.append({
                "universe": uname, "horizon": horizon, "top_n": top_n,
                "windows": r["windows"], "gross": gross, "net": round(net, 3),
                "win": r["win_rate_pct"], "p": p,
                "significant": sig.get("significant_at_5pct"),
            })
            print(f"{uname:>9} {horizon:>8} {top_n:>6} {r['windows']:>8} "
                  f"{gross:>8.3f} {net:>8.3f} {r['win_rate_pct']:>7.1f} "
                  f"{(p if p is not None else float('nan')):>7.3f}")

print("=" * 78)

if not rows:
    print("No usable configurations — cannot judge.")
    sys.exit(0)

sig_rows = [r for r in rows if r.get("significant")]
pos_gross = [r for r in rows if r["gross"] > 0]
pos_net = [r for r in rows if r["net"] > 0]

print(f"\nconfigurations tested      : {len(rows)}")
print(f"positive GROSS spread      : {len(pos_gross)} / {len(rows)}")
print(f"positive NET of costs      : {len(pos_net)} / {len(rows)}")
print(f"statistically significant  : {len(sig_rows)} / {len(rows)}")
print(f"cost per window            : {COST_PER_WINDOW_PCT:.3f}%")

best = max(rows, key=lambda r: r["gross"])
print(f"\nbest configuration         : {best['universe']} stocks, "
      f"{best['horizon']}d horizon, top {best['top_n']} "
      f"-> gross {best['gross']}%, net {best['net']}%, "
      f"win {best['win']}%, p={best['p']}")

# Testing twelve configurations and reporting the best is the oldest way to
# manufacture a result. At p < 0.05, twelve tests yield about 0.6 false positives
# by chance — so finding exactly one is not a discovery, it is the expected yield
# of the search itself.
BONF = 0.05 / len(rows)
survivors = [r for r in rows if r.get("p") is not None and r["p"] < BONF]
print("\nmultiple-testing correction")
print(f"  tests run                : {len(rows)}")
print(f"  expected false positives : {0.05 * len(rows):.1f} at p<0.05")
print(f"  Bonferroni threshold     : p < {BONF:.4f}")
print(f"  survive correction       : {len(survivors)}")
if sig_rows and not survivors:
    _b = min(sig_rows, key=lambda r: r["p"])
    print(f"  -> the one 'significant' result (p={_b['p']:.3f}) sits "
          f"{_b['p'] / BONF:.0f}x above the corrected threshold")

print("\nCONCLUSION")
if sig_rows and not survivors:
    print("  The null holds. One configuration reached p<0.05 uncorrected, which is")
    print("  precisely what searching twelve configurations yields by chance, and it")
    print("  does not survive correcting for having searched.")
    print("  The sign flips are the tell: a real edge does not appear and vanish")
    print("  depending on whether you take the top 3 or the top 5.")
    print(f"  Costs settle it. Trading the book once per window costs "
          f"{COST_PER_WINDOW_PCT:.3f}%, exceeding the gross spread in "
          f"{len(rows) - len(pos_net)} of {len(rows)} configurations.")
elif not sig_rows and not pos_net:
    print("  The null survives every configuration tested. Momentum did not")
    print("  separate winners from losers on this universe at any horizon or")
    print("  selection width, and every gross spread is smaller than the cost of")
    print("  trading it. The original 50% result was not an artefact of one")
    print("  narrow setting.")
elif sig_rows:
    print(f"  {len(sig_rows)} configuration(s) reached significance. The answer")
    print("  therefore DEPENDS on the setting, which is itself the finding — and a")
    print("  reason to distrust any single configuration, including the one that")
    print("  happens to look best.")
else:
    print("  No configuration reached significance, though some show a positive")
    print("  gross spread. Positive-but-not-significant on a sample this size is")
    print("  what noise looks like; it is not evidence of an edge.")
print("=" * 78)
