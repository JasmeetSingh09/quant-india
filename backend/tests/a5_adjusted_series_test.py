"""
a5_adjusted_series_test.py — A5 must see corrected prices, and must not see the future.

The validation ran on the closes the exchange printed. A 1:4 bonus prints an 80%
overnight fall in which nothing happened to the company, and any 12-1 momentum
window spanning one scored that company as the worst momentum on the exchange.
A4 built the adjustment layer and proved it against four real events; this
proves the validation actually reads through it.

Two claims are load-bearing and they pull in opposite directions:

    an action INSIDE the formation window must change the score
        -- otherwise the adjustment is not reaching the factor at all;

    an action AFTER the formation date must NOT change it
        -- otherwise the correction has smuggled the future into the past,
           which is a worse defect than the discontinuity it set out to fix.

The second is the one that matters. The adjustment convention scales history to
meet the present, so the LEVEL at any past date depends on actions after it. The
reason that is safe is that every frozen factor reads ratios, never levels, and
in a ratio the factor cancels except for actions inside the window. That is an
argument, and arguments are what tests are for: the look-ahead invariance below
adds an action after the formation date and asserts the score does not move by
so much as a float.

The rest guard the things a correction must never quietly do -- invent an
observation, drop one, move a date, change who is eligible, or stitch a series
across an identity boundary the resolver refused to merge.
"""

import os
import sqlite3
import sys
import types
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "a5_adjusted_test.db")
if os.path.exists(DB):
    os.remove(DB)
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import numpy as np  # noqa: E402
import pit_validation as PV  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


# ---------------------------------------------------------------- fixtures

def trading_days(n, start=date(2015, 1, 1)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


DAYS = trading_days(420)


def build(price_rows, actions, pairs):
    """Rebuild the archive. price_rows: {(isin, symbol): {day: close}}."""
    if os.path.exists(DB):
        os.remove(DB)
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE bhavcopy_eod (symbol TEXT, day TEXT, open REAL,"
                 " high REAL, low REAL, close REAL, volume REAL, isin TEXT,"
                 " PRIMARY KEY (symbol, day))")
    conn.execute("CREATE TABLE corporate_actions (isin TEXT, symbol TEXT,"
                 " ex_date TEXT, kind TEXT, num REAL, den REAL, amount REAL,"
                 " subject TEXT, parsed INTEGER, sig TEXT, fetched_at TEXT,"
                 " PRIMARY KEY (isin, ex_date, sig))")
    for (isin, sym), by_day in price_rows.items():
        for d, px in by_day.items():
            conn.execute("INSERT INTO bhavcopy_eod (symbol, day, close, volume,"
                         " isin) VALUES (?,?,?,?,?)", (sym, d, px, 100000.0, isin))
    for a in actions:
        conn.execute("INSERT INTO corporate_actions (isin, ex_date, kind, num,"
                     " den, amount, parsed, sig) VALUES (?,?,?,?,?,?,1,?)",
                     (a["isin"], a["ex_date"], a["kind"], a.get("num"),
                      a.get("den"), a.get("amount"), a.get("sig", a["ex_date"])))
    conn.commit()
    conn.close()
    return pairs


def load(canonical=None, pairs=None):
    conn = sqlite3.connect(DB)
    keys, days, C, V = PV._load(conn, canonical or {}, pairs or [])
    F, info = PV._apply_adjustment(conn, keys, days, C.copy(), canonical or {})
    conn.close()
    return keys, days, C, V, F, info


# A 1:4 bonus: multiplier 4/(1+4) ... the production parser reads "Bonus 4:1"
# as four new shares for one held, so the price multiplier is 1/(4+1) = 0.2 --
# the same 0.2 that appeared in all four real A4 events.
BONUS_COL = 300
BONUS_DAY = DAYS[BONUS_COL]
FLAT, AFTER = 1000.0, 200.0


def one_stock_with_bonus():
    px = {}
    for i, d in enumerate(DAYS):
        px[d] = FLAT if i < BONUS_COL else AFTER
    return {("INE000A01001", "AAA"): px}


print("=" * 74)
print("THE DISCONTINUITY THE ARCHIVE PRINTS")
print("=" * 74)

build(one_stock_with_bonus(),
      [{"isin": "INE000A01001", "ex_date": BONUS_DAY, "kind": "bonus",
        "num": 4, "den": 1}],
      [("INE000A01001", "AAA")])
keys, days, C, V, F, info = load(pairs=[("INE000A01001", "AAA")])

raw_jump = C[0, BONUS_COL] / C[0, BONUS_COL - 1] - 1.0
adj = C[0] * F[0]
adj_jump = adj[BONUS_COL] / adj[BONUS_COL - 1] - 1.0
print(f"  raw   {C[0, BONUS_COL-1]:.2f} -> {C[0, BONUS_COL]:.2f}   {raw_jump*100:+.2f}%")
print(f"  adj   {adj[BONUS_COL-1]:.2f} -> {adj[BONUS_COL]:.2f}   {adj_jump*100:+.2f}%")

check("the archive really does print an ~80% fall",
      abs(raw_jump + 0.80) < 0.001, f"{raw_jump*100:+.2f}%")
check("the adjusted series is continuous across it",
      abs(adj_jump) < 1e-5, f"{adj_jump*100:+.4f}%")
check("the multiplier matches the four real A4 events (0.2)",
      abs(float(F[0, BONUS_COL - 1]) - 0.2) < 1e-6, f"{float(F[0, BONUS_COL-1]):.6f}")
check("prices on and after the ex-date are untouched",
      abs(float(F[0, BONUS_COL]) - 1.0) < 1e-9,
      "history is scaled to meet the present, not the other way round")
check("the action is reported as applied", info["actions_applied"] == 1, f"{info}")

print()
print("=" * 74)
print("AN ACTION INSIDE THE WINDOW MUST CHANGE THE SCORE")
print("=" * 74)

col = 400                                   # formation date, bonus is behind it
raw_score = PV._momentum_scores(C, col)[0]
adj_score = PV._momentum_scores(C * F, col)[0]
print(f"  momentum on raw closes   {raw_score:+.4f}")
print(f"  momentum on adjusted     {adj_score:+.4f}")
check("raw closes score the bonus as a collapse",
      raw_score < -0.5, f"{raw_score:+.4f}")
check("the adjusted series scores it as the non-event it was",
      abs(adj_score) < 0.05, f"{adj_score:+.4f}")
check("the correction is worth more than a rounding difference",
      abs(raw_score - adj_score) > 0.5,
      f"{abs(raw_score - adj_score):.3f} of the tanh range")

print()
print("=" * 74)
print("AN ACTION AFTER THE FORMATION DATE MUST NOT CHANGE IT")
print("=" * 74)

# Same prices, no split. One run with nothing after the formation date, one with
# a large action after it. The score at that date must be bit-identical.
flat = {("INE000B01001", "BBB"):
        {d: 100.0 + i * 0.5 for i, d in enumerate(DAYS)}}
pairs_b = [("INE000B01001", "BBB")]

build(flat, [], pairs_b)
_, _, C0, _, F0, _ = load(pairs=pairs_b)
score_without = PV._momentum_scores(C0 * F0, 300)[0]

build(flat, [{"isin": "INE000B01001", "ex_date": DAYS[380], "kind": "bonus",
              "num": 4, "den": 1}], pairs_b)
_, _, C1, _, F1, info_after = load(pairs=pairs_b)
score_with = PV._momentum_scores(C1 * F1, 300)[0]

print(f"  formation at column 300, action at column 380 (80 days later)")
print(f"  score with no future action   {score_without:.10f}")
print(f"  score with a 5x bonus later   {score_with:.10f}")
check("the future action was actually applied to the series",
      info_after["actions_applied"] == 1 and float(F1[0, 0]) < 0.5,
      f"factor at t0 = {float(F1[0,0]):.4f}")
check("LOOK-AHEAD: the score at formation is unchanged to 1e-9",
      abs(float(score_without) - float(score_with)) < 1e-9,
      f"delta = {abs(float(score_without)-float(score_with)):.3e}")

lr_without = PV._low_risk_scores(C0 * F0, 300)[0]
build(flat, [{"isin": "INE000B01001", "ex_date": DAYS[380], "kind": "bonus",
              "num": 4, "den": 1}], pairs_b)
_, _, C2, _, F2, _ = load(pairs=pairs_b)
lr_with = PV._low_risk_scores(C2 * F2, 300)[0]
lr_delta = abs(float(lr_without) - float(lr_with))

# low_risk does far more arithmetic than momentum -- a cumulative product and a
# running maximum across 271 columns -- so it leaves a residual where momentum
# leaves none. A residual "small enough to ignore" is not an argument, so the
# cause is identified rather than tolerated.
#
# An action after the formation window multiplies EVERY column in that window by
# the same m, and every number the factors read is a ratio, so m cancels
# exactly. In floating point it cancels only as well as m can be represented:
# (a*m)/(b*m) is not bitwise (a/b) when m is not a binary fraction.
#
# That gives a decisive test. 0.5 IS exactly representable and 0.2 is not, so if
# the residual is representation it must vanish for one and not the other -- and
# must shrink with the width of the type. Information leaking from the future
# would not care about either.
n = len(DAYS)
row32 = np.array([[100.0 + i * 0.5 for i in range(n)]], dtype=np.float32)
probe = {}
for tname, row, dt in (("float32", row32, np.float32),
                       ("float64", row32.astype(np.float64), np.float64)):
    for m in (0.2, 0.5):
        base = PV._low_risk_scores(row * np.full(row.shape, dt(1.0), dtype=dt), 300)[0]
        scaled = PV._low_risk_scores(row * np.full(row.shape, dt(m), dtype=dt), 300)[0]
        probe[(tname, m)] = abs(float(base) - float(scaled))
        mb = PV._momentum_scores(row * np.full(row.shape, dt(1.0), dtype=dt), 300)[0]
        ms = PV._momentum_scores(row * np.full(row.shape, dt(m), dtype=dt), 300)[0]
        probe[("mom", tname, m)] = abs(float(mb) - float(ms))

print(f"  low_risk delta, float32, m=0.2   {probe[('float32', 0.2)]:.3e}"
      f"   (float32 eps {np.finfo(np.float32).eps:.2e})")
print(f"  low_risk delta, float32, m=0.5   {probe[('float32', 0.5)]:.3e}"
      f"   <- 0.5 is exact in binary")
print(f"  low_risk delta, float64, m=0.2   {probe[('float64', 0.2)]:.3e}"
      f"   (float64 eps {np.finfo(np.float64).eps:.2e})")

check("LOOK-AHEAD: momentum is exactly invariant to a future action",
      lr_delta >= 0 and probe[("mom", "float32", 0.2)] == 0.0
      and probe[("mom", "float64", 0.2)] == 0.0,
      "zero, not merely small")
check("low_risk residual stays under float32 epsilon",
      lr_delta < float(np.finfo(np.float32).eps), f"{lr_delta:.3e}")
check("an EXACTLY representable factor gives exact invariance",
      probe[("float32", 0.5)] == 0.0 and probe[("float64", 0.5)] == 0.0,
      "m=0.5 -> delta is 0.0 in both widths")
check("the residual shrinks with the width of the type",
      probe[("float64", 0.2)] < probe[("float32", 0.2)] / 1000.0,
      f"{probe[('float64', 0.2)]:.3e} vs {probe[('float32', 0.2)]:.3e}")
check("so the residual is the binary representation of the multiplier",
      probe[("float64", 0.2)] <= 10 * float(np.finfo(np.float64).eps),
      "future information would not depend on how 0.2 is stored")

print()
print("=" * 74)
print("WHAT THE CORRECTION MUST NEVER DO")
print("=" * 74)

px = one_stock_with_bonus()
px[("INE000C01001", "CCC")] = {d: (250.0 if i % 7 else None)
                               for i, d in enumerate(DAYS)}
px[("INE000C01001", "CCC")] = {d: v for d, v in
                               px[("INE000C01001", "CCC")].items() if v}
build(px, [{"isin": "INE000A01001", "ex_date": BONUS_DAY, "kind": "bonus",
            "num": 4, "den": 1}],
      [("INE000A01001", "AAA"), ("INE000C01001", "CCC")])
keys, days, C, V, F, info = load(pairs=[("INE000A01001", "AAA"),
                                        ("INE000C01001", "CCC")])
adj = C * F

check("no date is added, removed or moved", days == DAYS, f"{len(days)} days")
check("no security is added or removed", len(keys) == 2, f"{keys}")
check("ELIGIBILITY: the missing-price mask is identical",
      np.array_equal(np.isnan(C), np.isnan(adj)),
      "a correction must not create or destroy an observation")
check("a missing cell stays missing",
      int(np.isnan(C).sum()) == int(np.isnan(adj).sum()) > 0,
      f"{int(np.isnan(C).sum())} gaps preserved")
check("a security with no actions is left exactly alone",
      np.array_equal(F[keys.index("INE000C01001")],
                     np.ones(len(days), dtype=np.float32)))
check("TRADED VALUE is left raw", info["traded_value_left_raw"] is True,
      "turnover is a level; an adjusted level carries future actions")
check("V really is unadjusted",
      abs(float(V[0, 0]) - 1000.0 * 100000.0) < 1.0,
      f"V[0,0]={float(V[0,0]):.0f} = raw close x volume")
check("every adjustment factor is strictly positive",
      bool(np.all(F > 0)), "a zero or negative factor would erase a price")

print()
print("=" * 74)
print("IDENTITY BOUNDARIES ARE RESPECTED (THE AEGISLOG CASE)")
print("=" * 74)

# AEGISLOG's face-value split changed its ISIN. A4 showed production correctly
# REFUSED to compute continuity across that boundary rather than inventing it.
old_isin, new_isin = "INE208C01017", "INE208C01025"
split_col = 200
two_eras = {
    (old_isin, "AEGISLOG"): {d: 1000.0 for d in DAYS[:split_col]},
    (new_isin, "AEGISLOG"): {d: 100.0 for d in DAYS[split_col:]},
}
acts = [{"isin": new_isin, "ex_date": DAYS[split_col], "kind": "split",
         "num": 10, "den": 1}]
pairs_two = [(old_isin, "AEGISLOG"), (new_isin, "AEGISLOG")]

# Unresolved: the resolver did not merge them, so they are two rows.
build(two_eras, acts, pairs_two)
keys, days, C, V, F, info = load(canonical={}, pairs=pairs_two)
check("an unmerged ISIN pair stays two separate securities",
      len(keys) == 2, f"{keys}")
i_old, i_new = keys.index(old_isin), keys.index(new_isin)
check("the pre-split era holds only its own prices",
      np.isfinite(C[i_old, :split_col]).all()
      and np.isnan(C[i_old, split_col:]).all(),
      "no stitching across the identity boundary")
check("the split touches only the ISIN it belongs to",
      float(F[i_old, 0]) == 1.0,
      "the action is filed under the new ISIN; the old row must not receive it")

# Resolved: the resolver DID merge them, so one row spans both eras and gets
# the action. That is continuity the identity system established, not invented.
merged = {old_isin: old_isin, new_isin: old_isin}
build(two_eras, acts, pairs_two)
keys_m, days_m, C_m, V_m, F_m, info_m = load(canonical=merged, pairs=pairs_two)
check("a merged pair becomes one security", len(keys_m) == 1, f"{keys_m}")
check("the merged row receives the action filed under either ISIN",
      float(F_m[0, 0]) < 1.0, f"factor={float(F_m[0,0]):.4f}")
check("continuity comes from the resolver, never from the adjuster",
      info_m["actions_applied"] == 1)

print()
print("=" * 74)
print("REFUSALS ARE COUNTED, NOT GUESSED")
print("=" * 74)

# A dividend on the very first stored day has no prior close to divide by.
build({("INE000D01001", "DDD"): {d: 500.0 for d in DAYS}},
      [{"isin": "INE000D01001", "ex_date": DAYS[0], "kind": "dividend",
        "amount": 5.0}],
      [("INE000D01001", "DDD")])
keys, days, C, V, F, info = load(pairs=[("INE000D01001", "DDD")])
check("a dividend with no close before it is not applied",
      info["actions_applied"] == 0 and info["actions_unapplied"] == 1, f"{info}")
check("the reason is recorded",
      bool(info["unapplied_by_reason"]), f"{info['unapplied_by_reason']}")
check("and the price is left exactly as printed",
      float(F[0, 0]) == 1.0, "never approximated")

build({("INE000D01001", "DDD"): {d: 500.0 for d in DAYS}},
      [{"isin": "INE999Z01999", "ex_date": DAYS[100], "kind": "bonus",
        "num": 1, "den": 1}],
      [("INE000D01001", "DDD")])
_, _, _, _, F2, info2 = load(pairs=[("INE000D01001", "DDD")])
check("an action for a security not in the matrix is skipped, not misapplied",
      info2["actions_applied"] == 0 and bool(np.all(F2 == 1.0)), f"{info2}")

print()
print("=" * 74)
print("THE FROZEN SPECIFICATION IS UNTOUCHED")
print("=" * 74)

check("lookback still 252", PV.MOM_LOOKBACK == 252)
check("skip still 21", PV.MOM_SKIP == 21)
check("tanh divisor still 1.5", PV.MOM_TANH_DIV == 1.5)
check("horizons still 1/3/6/12", tuple(PV.HORIZONS) == (1, 3, 6, 12))
check("buckets still 5", PV.N_BUCKETS == 5)
check("cost assumption still 0.4%", PV.COST_ROUNDTRIP_PCT == 0.4)

import inspect  # noqa: E402

msrc = inspect.getsource(PV._momentum_scores)
check("the momentum function itself was not edited",
      "MOM_LOOKBACK" in msrc and "MOM_SKIP" in msrc
      and "np.tanh(risk_adj / MOM_TANH_DIV)" in msrc,
      "adjustment happens to the prices, never to the factor")

try:
    os.remove(DB)
except Exception:
    pass

print()
print("=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
