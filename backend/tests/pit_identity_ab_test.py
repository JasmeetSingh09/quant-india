"""
pit_identity_ab_test.py — prove the identity fix on data whose answer is known.

The production archive can show that the three keyings disagree. It cannot show
which one is RIGHT, because nobody wrote down the true answer in advance. So
this builds a small exchange archive by hand containing exactly one rename and
exactly one ISIN change, both engineered to be held by the strategy, and checks
that each keying makes the specific mistake it is supposed to make:

    symbol-keyed    writes off the renamed company
    ISIN-keyed      writes off the restructured company
    resolved        writes off neither

If the resolved run ever books an invalid -100%, the fix is broken, and that is
a single assertion rather than an opinion about a table of numbers.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import pit_backtest as pit  # noqa: E402
from security_identity import _pairs, _resolve_pairs  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


# ---------------------------------------------------------------- fixture
# 24 month-ends. Enough for a 12-1 lookback plus a skip month plus a run.
MONTHS = [f"{y}-{m:02d}" for y in (2024, 2025) for m in range(1, 13)]
LAST_DAY = {ym: f"{ym}-28" for ym in MONTHS}

# Two securities that change identity, and enough ordinary ones to fill a
# basket. The changers are given the strongest momentum so they are certain to
# be selected, which is what makes the assertions below meaningful.
RENAMED_ISIN = "INE100A01011"      # keeps ISIN, changes ticker at 2025-07
CHANGED_SYMBOL = "RESTRUCT.NS"     # keeps ticker, changes ISIN at 2025-07
CHANGED_OLD_ISIN = "INE200B01011"
CHANGED_NEW_ISIN = "INE200B01029"

FILLERS = [(f"INE{300 + i:03d}C01011", f"FILL{i}.NS") for i in range(40)]


def build_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE bhavcopy_eod (day TEXT, symbol TEXT, "
                 "close REAL, volume REAL, isin TEXT)")
    rows = []
    for i, ym in enumerate(MONTHS):
        day = LAST_DAY[ym]
        # The two changers climb fastest, so they top the momentum ranking.
        px_fast = 100.0 * (1.30 ** i)
        # Renamed: one ISIN, ticker changes from month 18 onward.
        sym = "OLDNAME.NS" if i < 18 else "NEWNAME.NS"
        rows.append((day, sym, px_fast, 1e9, RENAMED_ISIN))
        # Restructured: one ticker, ISIN replaced from month 18 onward.
        isin = CHANGED_OLD_ISIN if i < 18 else CHANGED_NEW_ISIN
        rows.append((day, CHANGED_SYMBOL, px_fast * 0.99, 1e9, isin))
        for j, (fisin, fsym) in enumerate(FILLERS):
            rows.append((day, fsym, 50.0 * (1.01 ** i) + j, 1e9, fisin))
    conn.executemany("INSERT INTO bhavcopy_eod VALUES (?,?,?,?,?)", rows)
    conn.commit()
    return conn


print("\nBuilding a 24-month archive with one rename and one ISIN change")
conn = build_db()
month_days = pit._month_end_days(conn)
ok(len(month_days) == 24, f"24 month-ends recorded (got {len(month_days)})")

canonical, components, links, ambiguous = _resolve_pairs(_pairs(conn))
ok(canonical.get(CHANGED_OLD_ISIN) == canonical.get(CHANGED_NEW_ISIN),
   "the two ISINs of the restructured company resolve to one identity")
ok(len(ambiguous) == 0, "nothing in this fixture is ambiguous")

print("\nRunning the same strategy under all three keyings")
# The benchmark is a network call and irrelevant to identity; stub it so the
# test is deterministic and offline.
pit._benchmark = lambda months: {}
panels = pit._panels_all(conn, month_days, canonical)

results = {}
for mode in ("symbol", "isin", "resolved"):
    c, v, r = panels[mode]
    results[mode] = pit.run(top_fraction=0.2, key_mode=mode,
                            _prebuilt=(month_days, c, v, r, {}))
    if "error" in results[mode]:
        print(f"    {mode}: ERROR {results[mode]['error']}")


def invalid(mode):
    return (results[mode].get("identity", {})
            .get("invalid_writeoffs", {}).get("count"))


def booked(mode):
    return results[mode].get("delistings_held", {}).get("count")


print()
for mode in ("symbol", "isin", "resolved"):
    if "error" not in results[mode]:
        print(f"    {mode:9s} delistings booked={booked(mode)} "
              f"invalid={invalid(mode)} "
              f"months={results[mode].get('months_tested')}")

print()
ok(all("error" not in results[m] for m in results),
   "all three keyings produced a result")

if all("error" not in results[m] for m in results):
    # The point of the whole exercise.
    ok(invalid("resolved") == 0,
       "resolved keying books ZERO invalid write-offs")
    ok(invalid("symbol") > 0,
       f"symbol keying wrongly writes off the renamed company "
       f"({invalid('symbol')} position-months)")
    ok(invalid("isin") > 0,
       f"ISIN keying wrongly writes off the restructured company "
       f"({invalid('isin')} position-months)")
    ok(booked("resolved") == 0,
       "no security in this fixture actually delisted, and resolved agrees")

    # A -100% booking has to hurt, or the test above proves nothing.
    r_sym = results["symbol"]["stats"]["cagr_pct"]
    r_res = results["resolved"]["stats"]["cagr_pct"]
    print(f"\n    CAGR symbol-keyed {r_sym}%  vs resolved {r_res}%")
    ok(r_res > r_sym,
       "removing the phantom losses improves the result, as it must")

    # Every run must have seen the same months and the same book size, or the
    # comparison is measuring something other than identity.
    ok(len({results[m]["months_tested"] for m in results}) == 1,
       "all three runs tested the same number of months")
    ok(len({results[m]["universe"]["avg_holdings"] for m in results}) == 1,
       "all three runs held the same number of positions per month")

print("\n" + "=" * 62)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
