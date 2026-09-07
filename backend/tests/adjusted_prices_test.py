"""
adjusted_prices_test.py — the trust gate for the adjustment layer.

Nothing downstream is worth running until this passes. A momentum backtest on a
badly adjusted series produces a confident number that measures corporate
actions, and a p-value computed on it looks exactly like a p-value computed on
anything else.

So the fixtures are built the other way round from usual: a price path is
CONSTRUCTED with a known split or bonus written into it — the raw series really
does halve overnight on the bonus date — and the test asserts the adjusted
series comes out continuous. The expected factors are worked out by hand in the
comments rather than read back from the code, because a test that recomputes
the implementation's own arithmetic proves only that it is self-consistent.

The events are modelled on real ones: BANKBARODA's 2015 face-value split from
Rs 10 to Rs 2, and a 1:1 bonus of the kind GODREJIND and dozens of others have
declared.
"""

import os
import sqlite3
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "adj_prices_test.db")
if os.path.exists(DB):
    os.remove(DB)
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(DB)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import corporate_actions as CA   # noqa: E402
import adjusted_prices as AP     # noqa: E402

PASS, FAIL = [], []


def ok(cond, label, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}" + (f"   {detail}" if detail else ""))


con = sqlite3.connect(DB)
con.execute("""CREATE TABLE bhavcopy_eod (symbol TEXT, day TEXT, open REAL,
    high REAL, low REAL, close REAL, volume REAL, isin TEXT,
    PRIMARY KEY (symbol, day))""")
con.commit()
con.close()


def days_from(y, m, d0, n):
    """n consecutive weekdays as ISO strings."""
    from datetime import date, timedelta
    out, d = [], date(y, m, d0)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def seed(isin, symbol, days, closes):
    con = sqlite3.connect(DB)
    for d, c in zip(days, closes):
        con.execute("INSERT OR REPLACE INTO bhavcopy_eod (symbol, day, close, isin)"
                    " VALUES (?,?,?,?)", (symbol, d, c, isin))
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# BANKBARODA-style: face value Rs 10 -> Rs 2 on day 20. The true economic price
# drifts +0.5% a day throughout; the PRINTED price divides by 5 on the ex-date.
# Expected multiplier = new_fv / old_fv = 2/10 = 0.2, applied to everything
# BEFORE the ex-date.
# ---------------------------------------------------------------------------
D = days_from(2015, 6, 1, 40)
EX_SPLIT = D[20]
true_path = [100.0 * (1.005 ** i) for i in range(40)]
printed = [p if i < 20 else p / 5.0 for i, p in enumerate(true_path)]
seed("INE028A01013", "BANKBARODA", D, printed)
CA.store([{"isin": "INE028A01013", "symbol": "BANKBARODA",
           "exDate": "22-Jun-2015" if EX_SPLIT == "2015-06-22" else EX_SPLIT,
           "subject": "Face Value Split (Sub-Division) - From Rs 10/- Per Share "
                      "To Rs 2/- Per Share"}])

print("\n1. FACE-VALUE SPLIT Rs 10 -> Rs 2  (BANKBARODA 2015)")
ser = AP.price_series("INE028A01013")
ok(ser["n"] == 40, f"40 closes loaded ({ser['n']})")
ok(len(ser["actions_applied"]) == 1,
   f"one action applied ({len(ser['actions_applied'])})",
   f"unapplied: {ser['unapplied']}")
if ser["actions_applied"]:
    m = ser["actions_applied"][0]["multiplier"]
    ok(abs(m - 0.2) < 1e-9, "multiplier is 2/10 = 0.2, computed by hand", f"{m}")
i = ser["days"].index(EX_SPLIT)
raw_jump = ser["raw_close"][i] / ser["raw_close"][i - 1] - 1
adj_jump = ser["close"][i] / ser["close"][i - 1] - 1
ok(abs(raw_jump + 0.8) < 0.02,
   "the RAW series really does fall ~80% on the ex-date",
   f"{raw_jump*100:.2f}%")
ok(abs(adj_jump - 0.005) < 1e-6,
   "the ADJUSTED series shows the ordinary +0.5% day instead",
   f"{adj_jump*100:.4f}%")
ok(abs(ser["factor"][0] - 0.2) < 1e-9,
   "pre-split days carry factor 0.2", f"{ser['factor'][0]}")
ok(abs(ser["factor"][-1] - 1.0) < 1e-12,
   "the latest close is unadjusted", f"{ser['factor'][-1]}")

print("\n   and the twelve-month return is no longer nonsense")
r_raw = ser["raw_close"][-1] / ser["raw_close"][0] - 1
r_adj = ser["close"][-1] / ser["close"][0] - 1
r_true = true_path[-1] / true_path[0] - 1
ok(abs(r_adj - r_true) < 1e-9,
   "adjusted return matches the true economic return",
   f"adjusted {r_adj*100:+.2f}%  true {r_true*100:+.2f}%")
ok(abs(r_raw - r_true) > 0.5,
   "while the raw return is wrong by more than 50 points",
   f"raw {r_raw*100:+.2f}%")

# ---------------------------------------------------------------------------
print("\n2. BONUS 1:1 — shares double, printed price halves")
D2 = days_from(2018, 3, 1, 30)
EX_BONUS = D2[15]
true2 = [500.0 * (1.002 ** i) for i in range(30)]
printed2 = [p if i < 15 else p / 2.0 for i, p in enumerate(true2)]
seed("INE102D01028", "GODREJIND", D2, printed2)
CA.store([{"isin": "INE102D01028", "symbol": "GODREJIND",
           "exDate": EX_BONUS, "subject": "Bonus 1:1"}])
s2 = AP.price_series("INE102D01028")
m2 = s2["actions_applied"][0]["multiplier"] if s2["actions_applied"] else None
ok(m2 is not None and abs(m2 - 0.5) < 1e-9,
   "multiplier is B/(A+B) = 1/2 = 0.5, computed by hand", f"{m2}")
k = s2["days"].index(EX_BONUS)
ok(abs(s2["raw_close"][k] / s2["raw_close"][k - 1] - 1 + 0.5) < 0.01,
   "raw series halves on the ex-date",
   f"{(s2['raw_close'][k]/s2['raw_close'][k-1]-1)*100:.2f}%")
ok(abs(s2["close"][k] / s2["close"][k - 1] - 1 - 0.002) < 1e-6,
   "adjusted series shows the ordinary +0.2% day",
   f"{(s2['close'][k]/s2['close'][k-1]-1)*100:.4f}%")

# ---------------------------------------------------------------------------
print("\n3. TWO ACTIONS ON ONE SECURITY — factors must COMPOUND")
# Split 10->2 on day 10 (x0.2), then bonus 1:1 on day 20 (x0.5).
# A day before both should carry 0.2 * 0.5 = 0.1.
D3 = days_from(2019, 1, 1, 30)
true3 = [1000.0] * 30
p3 = []
for i, p in enumerate(true3):
    v = p
    if i >= 10:
        v /= 5.0
    if i >= 20:
        v /= 2.0
    p3.append(v)
seed("INE999Z01011", "TWOACT", D3, p3)
CA.store([
    {"isin": "INE999Z01011", "symbol": "TWOACT", "exDate": D3[10],
     "subject": "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share"},
    {"isin": "INE999Z01011", "symbol": "TWOACT", "exDate": D3[20],
     "subject": "Bonus 1:1"},
])
s3 = AP.price_series("INE999Z01011")
ok(len(s3["actions_applied"]) == 2, f"both actions applied ({len(s3['actions_applied'])})")
ok(abs(s3["factor"][0] - 0.1) < 1e-9,
   "a day before BOTH carries 0.2 x 0.5 = 0.1", f"{s3['factor'][0]}")
ok(abs(s3["factor"][15] - 0.5) < 1e-9,
   "a day between them carries only the later 0.5", f"{s3['factor'][15]}")
ok(abs(s3["factor"][-1] - 1.0) < 1e-12, "after both, factor 1.0")
ok(max(s3["close"]) - min(s3["close"]) < 1e-6,
   "a flat true price stays flat once adjusted, across both events",
   f"spread {max(s3['close']) - min(s3['close']):.9f}")

# ---------------------------------------------------------------------------
print("\n4. DIVIDEND — needs the prior close, and says so when it lacks one")
D4 = days_from(2020, 5, 1, 20)
seed("INE888Y01010", "DIVCO", D4, [200.0] * 20)
CA.store([{"isin": "INE888Y01010", "symbol": "DIVCO", "exDate": D4[10],
           "subject": "Annual General Meeting/ Dividend - Rs 10/- Per Share"}])
s4 = AP.price_series("INE888Y01010")
m4 = s4["actions_applied"][0]["multiplier"] if s4["actions_applied"] else None
ok(m4 is not None and abs(m4 - 0.95) < 1e-9,
   "Rs 10 on a Rs 200 close -> (200-10)/200 = 0.95", f"{m4}")
# the same dividend before any stored price cannot be applied
CA.store([{"isin": "INE888Y01010", "symbol": "DIVCO", "exDate": "2019-01-15",
           "subject": "Annual General Meeting/ Dividend - Rs 4/- Per Share"}])
s4b = AP.price_series("INE888Y01010")
ok(len(s4b["actions_applied"]) == 1,
   "a dividend before the first stored price is not applied",
   f"applied {len(s4b['actions_applied'])}, unapplied {len(s4b['unapplied'])}")

print("\n5. RETURNS ARE INVARIANT TO THE REFERENCE POINT")
full = AP.price_series("INE028A01013")
part = AP.price_series("INE028A01013", end=full["days"][30])
a = full["close"][25] / full["close"][5] - 1
b = part["close"][25] / part["close"][5] - 1
ok(abs(a - b) < 1e-9,
   "the same two dates give the same return whichever window is loaded",
   f"{a*100:.6f}% vs {b*100:.6f}%")

print("\n6. RAW MODE IS UNTOUCHED, AND THE ARCHIVE IS NEVER WRITTEN")
raw = AP.price_series("INE028A01013", adjusted=False)
ok(raw["close"] == raw["raw_close"], "adjusted=False returns the printed prices")
ok(all(f == 1.0 for f in raw["factor"]), "with factors of exactly 1.0")
con = sqlite3.connect(DB)
n_before = con.execute("SELECT COUNT(*) FROM bhavcopy_eod").fetchone()[0]
chk = con.execute("SELECT SUM(close) FROM bhavcopy_eod").fetchone()[0]
con.close()
AP.price_series("INE028A01013")
AP.price_series("INE102D01028")
con = sqlite3.connect(DB)
ok(con.execute("SELECT COUNT(*) FROM bhavcopy_eod").fetchone()[0] == n_before
   and abs(con.execute("SELECT SUM(close) FROM bhavcopy_eod").fetchone()[0] - chk) < 1e-9,
   "reading the adjusted series wrote nothing back to bhavcopy_eod")
con.close()
src = open(os.path.join(os.path.dirname(__file__), "..", "modules",
                        "adjusted_prices.py"), encoding="utf-8").read()
for verb in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER"):
    ok(verb not in src, f"the module contains no {verb}")

print("\n7. THE CONTINUITY GATE ITSELF")
g = AP.continuity_check("INE028A01013", EX_SPLIT)
ok(g.get("available") is True, f"the check runs ({g.get('reason','')})")
ok(abs(g["raw_jump_pct"] + 80) < 2,
   f"raw jump {g['raw_jump_pct']}%")
ok(abs(g["adjusted_jump_pct"] - 0.5) < 0.01,
   f"adjusted jump {g['adjusted_jump_pct']}%")
ok(g["improvement"] > 100,
   f"the adjustment removes the discontinuity {g['improvement']}x over")
g2 = AP.continuity_check("INE028A01013", "2001-01-01")
ok(g2.get("available") is False,
   f"an ex-date outside the stored range is reported, not guessed",
   f"{g2.get('reason','')[:60]}")

try:
    os.remove(DB)
except Exception:
    pass

print("\n" + "=" * 72)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
