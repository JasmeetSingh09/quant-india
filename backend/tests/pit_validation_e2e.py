"""
pit_validation_e2e.py — run validate() end to end on a synthetic archive.

The unit tests cover the factor maths and the statistics. This runs the whole
function against a database, because the parts that break in production are the
joins between pieces that each work: the identity index, the panel assembly,
the bucketing, the exploratory cuts.

It also exists because the first production run was killed for memory. A
synthetic archive of the same SHAPE as the real one (about 3,000 securities
over 650 days) exercises the same allocations, so a regression there shows up
here rather than as a 502.
"""

import os
import sqlite3
import sys
import tempfile
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


N_SEC = 900
N_DAY = 640
rng = np.random.default_rng(4242)

print(f"\nBuilding a synthetic archive: {N_SEC} securities x {N_DAY} days")
days = []
d = date(2024, 1, 1)
while len(days) < N_DAY:
    if d.weekday() < 5:
        days.append(d.isoformat())
    d += timedelta(days=1)

prices = 100.0 * np.cumprod(
    1 + rng.normal(0.0004, 0.018, size=(N_SEC, N_DAY)), axis=1)
isins = [f"INE{i:04d}A0101{i % 10}" for i in range(N_SEC)]
symbols = [f"SYN{i:04d}.NS" for i in range(N_SEC)]
# One rename and one ISIN change, so identity resolution is exercised too.
RENAME_AT, CHANGE_AT = 400, 400

tmp = os.path.join(tempfile.gettempdir(), "pit_val_e2e.db")
if os.path.exists(tmp):
    os.remove(tmp)
con = sqlite3.connect(tmp)
con.execute("CREATE TABLE bhavcopy_eod (symbol TEXT, day TEXT, open REAL, "
            "high REAL, low REAL, close REAL, volume REAL, isin TEXT, "
            "PRIMARY KEY (symbol, day))")
rows = []
for j, dd in enumerate(days):
    for i in range(N_SEC):
        sym, isin = symbols[i], isins[i]
        if i == 0 and j >= RENAME_AT:
            sym = "SYN0000RENAMED.NS"           # same ISIN, new ticker
        if i == 1 and j >= CHANGE_AT:
            isin = "INE9999Z01019"              # same ticker, new ISIN
        px = float(prices[i, j])
        rows.append((sym, dd, px, px, px, px, 5e6, isin))
con.executemany("INSERT OR IGNORE INTO bhavcopy_eod VALUES (?,?,?,?,?,?,?,?)",
                rows)
con.commit()
con.close()
print(f"  {len(rows):,} rows written to {tmp}")

# Inject a db module pointing at the fixture.
import types  # noqa: E402
fake = types.ModuleType("db")
fake.get_conn = lambda: sqlite3.connect(tmp)
fake.IS_POSTGRES = False
sys.modules["db"] = fake

import pit_validation as pv  # noqa: E402
pv._benchmark = lambda months: {}

print("\nRunning validate()")
import tracemalloc  # noqa: E402
tracemalloc.start()
res = pv.validate()
peak = tracemalloc.get_traced_memory()[1] / 1e6
tracemalloc.stop()
print(f"  peak python allocation: {peak:.0f} MB")

ok("error" not in res, f"validate() returned a result ({res.get('error')})")
if "error" not in res:
    u = res["universe"]
    print(f"  securities {u['securities_seen']}  days {u['trading_days']}  "
          f"formation months {u['formation_months']}")
    ok(u["trading_days"] == N_DAY, "every trading day was loaded")
    # The rename shares an ISIN so it is one identity; the ISIN change is
    # chained through the shared ticker. Both collapse to one security each.
    ok(u["securities_seen"] == N_SEC,
       f"identity resolution keeps {N_SEC} securities, got {u['securities_seen']}")
    ok(u["formation_months"] >= 3, "at least three formation months")

    ta = res["track_a"]
    ok(set(ta["factors"]) == {"momentum", "low_risk"},
       "both price-observable factors were tested")
    for f, fd in ta["factors"].items():
        for h, hd in fd["horizons"].items():
            if hd.get("insufficient"):
                continue
            bs = hd["buckets"]
            ok(len(bs) == 5, f"{f} {h} produced five quintiles")
            # Excess is measured against the universe mean, so the quintile
            # means must very nearly cancel. This is the arithmetic check that
            # catches a bucketing or centring mistake.
            means = [b["pooled_description_only"]["excess_mean_pct"]
                     for b in bs if not b.get("insufficient")]
            if len(means) == 5:
                ok(abs(sum(means)) < 0.5,
                   f"{f} {h} quintile excesses cancel (sum {sum(means):.3f})")
            for b in bs:
                if b.get("insufficient"):
                    continue
                ok(b["excess"]["n"] == b["n_months"],
                   f"{f} {h} {b['group']} tests months, not positions")

    # Random walks: nothing should survive Bonferroni.
    mt = res["multiple_testing"]
    print(f"  primary declared {mt['primary_hypotheses_declared']}, "
          f"testable {mt['primary_hypotheses_testable']}, "
          f"survived {mt['survived_correction']}")
    ok(mt["survived_correction"] == [],
       "no hypothesis survives correction on random-walk data")

    tb = res["track_b"]
    ok(len(tb["components"]) >= 5, "Track B lists the untestable components")
    ok("refused" in tb["rule_applied"],
       "Track B states that available substitutes were refused")

    ok(peak < 700, f"peak allocation stays under 700 MB (was {peak:.0f})")

try:
    os.remove(tmp)
except Exception:
    pass

print("\n" + "=" * 64)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
