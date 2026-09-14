"""
adjusted_backtest_test.py — a bonus issue is not a crash.

The point-in-time backtest and the momentum variants study read closes as the
exchange printed them, so a 1:1 bonus inside a holding month booked a loss on a
company to which nothing had happened (docs/PHASE2_FINDINGS_2026-09-14.md,
section 3). Both now use pit_validation's corporate-action correction.

This builds a small archive with one bonus issue, held by the strategy, where
the right answer is known: the company rose 30% that month.

Offline: the database is a temporary SQLite file and the benchmark is stubbed.
"""
import os
import sqlite3
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""),
          flush=True)


# ---------------------------------------------------------------- fixture
MONTHS = [f"{y}-{m:02d}" for y in (2024, 2025) for m in range(1, 13)]
BONUS_ISIN, BONUS_SYM = "INE500D01011", "BONUSCO.NS"
FILLERS = [(f"INE{600 + i:03d}E01011", f"FILL{i}.NS") for i in range(60)]
BONUS_MONTH = 17                     # 2025-06, formed at the end of 2025-05
EX_DATE = f"{MONTHS[BONUS_MONTH]}-15"

PATH = os.path.join(tempfile.gettempdir(), f"adjusted_backtest_test_{os.getpid()}.db")
if os.path.exists(PATH):
    os.remove(PATH)
con = sqlite3.connect(PATH)
con.execute("CREATE TABLE bhavcopy_eod (day TEXT, symbol TEXT, close REAL, "
            "volume REAL, isin TEXT)")
con.execute("CREATE TABLE corporate_actions (isin TEXT, ex_date TEXT, kind TEXT, "
            "num REAL, den REAL, amount REAL, parsed INTEGER)")
rows = []
for i, ym in enumerate(MONTHS):
    for dd in ("15", "28"):
        day = f"{ym}-{dd}"
        # BONUSCO climbs 30% a month, so momentum always holds it. From the
        # ex-date the exchange prints half the price for twice the shares.
        true_px = 100.0 * (1.30 ** i)
        rows.append((day, BONUS_SYM, true_px / 2 if day >= EX_DATE else true_px,
                     1e9, BONUS_ISIN))
        for j, (fisin, fsym) in enumerate(FILLERS):
            rows.append((day, fsym, 50.0 * (1.01 ** i) + j, 1e9, fisin))
con.executemany("INSERT INTO bhavcopy_eod VALUES (?,?,?,?,?)", rows)
con.execute("INSERT INTO corporate_actions VALUES (?,?,?,?,?,?,?)",
            (BONUS_ISIN, EX_DATE, "bonus", 1, 1, None, 1))
con.commit()
con.close()

fake_db = types.ModuleType("db")
fake_db.get_conn = lambda: sqlite3.connect(PATH)
fake_db.IS_POSTGRES = False
sys.modules["db"] = fake_db

import pit_backtest as PB  # noqa: E402
import pit_validation as PV  # noqa: E402
from security_identity import _pairs, _resolve_pairs  # noqa: E402

PB._benchmark = lambda months: {}
FORM_M, HOLD_M = MONTHS[BONUS_MONTH - 1], MONTHS[BONUS_MONTH]

print("=" * 74 + "\n1. THE CORRECTION ITSELF\n" + "=" * 74)
check("pit_validation offers one adjusted loader for every study",
      hasattr(PV, "load_adjusted"))
conn = sqlite3.connect(PATH)
canonical = _resolve_pairs(_pairs(conn))[0]
KEY = canonical.get(BONUS_ISIN, BONUS_ISIN)
raw_closes = PB._panel(conn, PB._month_end_days(conn), canonical, "resolved")[0]
raw_ratio = raw_closes[HOLD_M][KEY] / raw_closes[FORM_M][KEY]
check("printed closes show the bonus month as a 35% fall (the fixture is right)",
      abs(raw_ratio - 0.65) < 1e-6, f"{raw_ratio:.4f}")
built = PB._adjusted_prebuilt(conn) if hasattr(PB, "_adjusted_prebuilt") else None
conn.close()
check("the backtest can build its month-end panel from adjusted closes", built is not None)
if built:
    adj_closes, adj_values, prices = built[1], built[2], built[5]
    adj_ratio = adj_closes[HOLD_M][KEY] / adj_closes[FORM_M][KEY]
    check("  ...in which the bonus month is the 30% rise that happened",
          abs(adj_ratio - 1.30) < 1e-4, f"{adj_ratio:.4f}")
    check("  ...and it records one corporate action applied",
          prices.get("adjusted_for_corporate_actions") is True
          and (prices.get("adjustment") or {}).get("actions_applied") == 1,
          str(prices)[:160])
    printed_value = raw_closes[HOLD_M][KEY] * 1e9
    check("  ...while traded value stays as printed",
          abs(adj_values[HOLD_M][KEY] / printed_value - 1) < 1e-6)

print("\n" + "=" * 74 + "\n2. THE BACKTEST\n" + "=" * 74)
adj = PB.run(top_fraction=0.2)
PB.ADJUST_PRICES = False
raw = PB.run(top_fraction=0.2)
PB.ADJUST_PRICES = True
check("the adjusted run produces a result", "error" not in adj, str(adj.get("error")))
check("with adjustment switched off the run still works, on printed closes",
      "error" not in raw, str(raw.get("error")))
if "error" not in adj and "error" not in raw:
    check("the adjusted run says its closes were adjusted",
          (adj.get("prices") or {}).get("adjusted_for_corporate_actions") is True,
          str(adj.get("prices"))[:120])
    check("  ...and the printed-close run says they were not",
          (raw.get("prices") or {}).get("adjusted_for_corporate_actions") is False)
    a_mean = adj["monthly_evidence"]["mean_pct"]
    r_mean = raw["monthly_evidence"]["mean_pct"]
    check("the bonus no longer drags the result down",
          a_mean > r_mean, f"adjusted {a_mean}%, printed {r_mean}%")
    check("the limits text says the closes are adjusted",
          "adjusted for splits, bonuses and dividends" in adj.get("limits", ""),
          adj.get("limits", "")[:160])

print("\n" + "=" * 74 + "\n3. THE SURVIVORSHIP AND IDENTITY COMPARISONS\n" + "=" * 74)
cmp_ = PB.compare(top_fraction=0.2)
check("the survivorship comparison runs both sides on adjusted closes",
      "error" not in cmp_
      and ((cmp_.get("point_in_time") or {}).get("prices") or {}).get("adjusted_for_corporate_actions") is True
      and ((cmp_.get("survivor_only") or {}).get("prices") or {}).get("adjusted_for_corporate_actions") is True,
      str(cmp_.get("error")))
ab = PB.identity_ab(top_fraction=0.2)
check("the identity comparison stays on printed closes, and says so",
      "error" not in ab
      and all(((ab.get("runs") or {}).get(m, {}).get("prices") or {})
              .get("adjusted_for_corporate_actions") is False
              for m in ("symbol", "isin", "resolved"))
      and "printed" in ab.get("caution", ""),
      str(ab.get("error") or ab.get("caution"))[:160])

print("\n" + "=" * 74 + "\n4. THE MOMENTUM VARIANTS STUDY\n" + "=" * 74)
import momentum_variants as MV  # noqa: E402

mv = MV.run()
mvp = mv.get("prices") or {}
check("the momentum variants study reads adjusted closes too",
      mv.get("available") is True and mvp.get("adjusted_for_corporate_actions") is True,
      str(mv.get("reason") or mvp)[:160])
check("  ...and its limits text no longer calls them unadjusted",
      "unadjusted" not in (mv.get("limits") or ""), (mv.get("limits") or "")[:160])

print("\n" + "=" * 74 + "\n5. THE BENCHMARK: EVERY ELIGIBLE STOCK, SAME CLOSES\n" + "=" * 74)
bm = adj.get("benchmark") or {}
check("the backtest's benchmark is the equal-weighted eligible universe",
      bm.get("primary") == "eligible_universe_equal_weight", str(bm)[:120])
if built and "error" not in adj:
    # Every stock in this fixture is liquid with a full lookback from month 12,
    # so the eligible universe is all 61 stocks in every tested month.
    ms = [m for m, _ in built[0]]
    univ = []
    for i in range(12, len(ms) - 1):
        now, nxt = built[1][ms[i]], built[1][ms[i + 1]]
        r = [nxt[k] / now[k] - 1 for k in now]
        univ.append(sum(r) / len(r))
    want = adj["monthly_evidence"]["mean_pct"] - 100 * sum(univ) / len(univ)
    got = (adj.get("excess_stats") or {}).get("mean_pct")
    check("excess = strategy minus the eligible universe, worked out independently",
          got is not None and abs(got - want) < 0.01, f"got {got}, want {want:.3f}")
nref = adj.get("nifty_price_reference") or {}
check("with no Nifty data the reference says so instead of counting 0% months",
      nref.get("available") is False and nref.get("months") == 0, str(nref)[:120])
check("  ...and the excess is not simply the strategy's own return",
      (adj.get("excess_stats") or {}).get("mean_pct")
      != (adj.get("monthly_evidence") or {}).get("mean_pct"))
PB._benchmark = lambda months: {m: 1000.0 * (1.01 ** k) for k, m in enumerate(months)}
with_nifty = PB.run(top_fraction=0.2)
PB._benchmark = lambda months: {}
wref = with_nifty.get("nifty_price_reference") or {}
check("with Nifty data it is a labelled secondary reference: price-only, not alpha",
      wref.get("available") is True and wref.get("months") == with_nifty.get("months_tested")
      and "dividends excluded" in wref.get("note", "")
      and "not a measure of alpha" in wref.get("note", ""), str(wref)[:160])
rows = [t for t in (ab.get("table") or []) if "excess" in str(t.get("metric", "")).lower()]
check("the identity comparison labels its excess as against the eligible universe",
      bool(rows) and all("eligible universe" in t["metric"] for t in rows),
      str([t.get("metric") for t in rows]))

try:
    os.remove(PATH)
except Exception:
    pass

print("\n" + "=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
