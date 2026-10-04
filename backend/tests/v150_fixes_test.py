"""
v150_fixes_test.py — the three data fixes in model version v1.5.0 (owner approval 2026-10-05).

1. Piotroski F2, F4 and F5 read operating cash flow, total assets, equity and long-term
   debt from the statements when Yahoo's .info lacks them (it never has the last three
   for NSE stocks, so every stock lost those points). Unknown never becomes a free point.
2. Funds and ETFs (ISIN prefix INF) are left out of the scored universe.
3. A distressed value score (-0.5) records the negative multiples it came from.

Offline: Yahoo and statement data are replaced with fixed values; the universe test
runs against a SQLite file this test creates.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp()
open(os.path.join(TMP, "quant_platform.db"), "wb").close()
os.environ["QUANT_DATA_DIR"] = TMP
os.environ.pop("DATABASE_URL", None)

import data_fetcher  # noqa: E402
import metrics  # noqa: E402
import alpha_model  # noqa: E402

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


print("\n1. Piotroski reads the statements when .info lacks them")
INFO = {"returnOnAssets": None, "operatingCashflow": None, "grossMargins": 0.3, "revenueGrowth": 0.1}
DER = {}
metrics.get_info = lambda t: dict(INFO)
data_fetcher._derived_fundamentals = lambda t, info: dict(DER)


def f(**der):
    DER.clear(); DER.update(der)
    return metrics.piotroski_score("TEST.NS")


r = f(roa=0.08, operating_cashflow=900.0, total_assets=10000.0, total_equity=6000.0, long_term_debt=1200.0)
s = r["signals"]
ok(s["cfo_positive"] == 1, "F2: operating cash flow taken from the cash-flow statement")
ok(s["cfo_beats_roa"] == 1, "F4: cash flow / assets (9%) beats ROA (8%) with assets from the balance sheet")
ok(s["low_leverage"] == 1, "F5: long-term debt / equity 0.2 earns the low-leverage point")
ok(set(r["inputs_from_statements"]) == {"total_assets", "total_equity", "long_term_debt"},
   "the record says which inputs came from the statements")
r = f(roa=0.08, operating_cashflow=900.0, total_assets=10000.0, total_equity=6000.0)
ok(r["signals"]["low_leverage"] == 0, "no debt figure at all: the point is not given (unknown is not zero debt)")
r = f(roa=0.08, operating_cashflow=900.0, total_assets=10000.0, total_equity=-500.0, long_term_debt=100.0)
ok(r["signals"]["low_leverage"] == 0, "negative equity: no leverage point")
r = f(roa=0.08, total_assets=10000.0, total_equity=6000.0, long_term_debt=4000.0)
ok(r["signals"]["low_leverage"] == 0 and r["signals"]["cfo_positive"] == 0,
   "high debt fails F5; no cash-flow figure fails F2")
INFO.update(totalAssets=20000.0, operatingCashflow=50.0)
r = f(roa=0.08, operating_cashflow=900.0, total_assets=10000.0, total_equity=6000.0, long_term_debt=1200.0)
ok(r["signals"]["cfo_beats_roa"] == 0, ".info still wins when Yahoo does supply the figure (50/20000 < 8%)")
INFO.pop("totalAssets"); INFO.pop("operatingCashflow")

print("\n2. Statement fallbacks: long-term debt, else total debt")
import pandas as pd  # noqa: E402
import importlib  # noqa: E402
df = importlib.reload(data_fetcher)
bs = pd.DataFrame({pd.Timestamp("2026-03-31"): [10000.0, 6000.0, 3000.0, 2500.0, 1000.0]},
                  index=["Total Assets", "Stockholders Equity", "Total Debt", "Current Assets", "Current Liabilities"])
cf = pd.DataFrame({pd.Timestamp("2026-03-31"): [900.0, -300.0]}, index=["Operating Cash Flow", "Capital Expenditure"])


class FakeTicker:
    def __init__(self, t):
        self.balance_sheet, self.cashflow = bs, cf


df.yf.Ticker = FakeTicker
d = df._derived_fundamentals("NOLTD.NS", {"netIncomeToCommon": 800.0})
ok(d["total_assets"] == 10000.0 and d["total_equity"] == 6000.0 and d["operating_cashflow"] == 900.0,
   "assets, equity and operating cash flow come from the statements")
ok(d["long_term_debt"] == 3000.0 and "total debt" in d["long_term_debt_source"],
   "no long-term debt row: total debt is used, and labelled")

print("\n3. Funds and ETFs are left out of the scan universe")
import universe_scan  # noqa: E402
from db import get_conn  # noqa: E402
c = get_conn()
c.execute("CREATE TABLE IF NOT EXISTS bhavcopy_eod (symbol TEXT, day TEXT, open REAL, high REAL, low REAL, "
          "close REAL, volume REAL, isin TEXT)")
c.executemany("INSERT INTO bhavcopy_eod (symbol, day, isin) VALUES (?, ?, ?)",
              [("TCS.NS", "2026-09-07", "INE467B01029"), ("LIQUID1.NS", "2026-09-07", "INF732E01037"),
               ("NIFTYBEES.NS", "2026-09-07", "INF204KB14I2"), ("JISLDVREQS.NS", "2026-09-07", "IN9175A01010"),
               ("NOISIN.NS", "2026-09-07", None), ("OLD.NS", "2026-09-06", "INE000000000")])
c.commit(); c.close()
syms = set(universe_scan._bhavcopy_symbols())
ok(syms == {"TCS.NS", "JISLDVREQS.NS", "NOISIN.NS"}, f"companies kept, funds and ETFs left out ({sorted(syms)})")
src = open(universe_scan.__file__, encoding="utf-8").read()
q = src[src.index("SELECT DISTINCT symbol FROM bhavcopy_eod"):src.index(".fetchall()", src.index("SELECT DISTINCT symbol FROM bhavcopy_eod"))]
ok("%'" not in q and "NOT LIKE ?" in q, "the pattern is a parameter, so Postgres does not read % as a placeholder")

print("\n4. A distress value score records what it came from")
alpha_model._ticker_info = lambda t: {"trailingPE": -12.5, "priceToBook": -3.3}
v = alpha_model._compute_value_factor("DISTRESS.NS", peers=["X.NS"])
ok(v["score"] == -0.5, "the score is unchanged: -0.5")
ok(v["pe_ratio"] == -12.5 and v["pb_ratio"] == -3.3 and v["legs_used"] == 0 and "distress" in v["valued_on"],
   "the negative multiples behind it are recorded")
from factor_provenance import CAPTURE_MAP  # noqa: E402
ok(not all(v.get(k) is None for k in CAPTURE_MAP["value"]), "provenance no longer sees a score from nothing")

print("\n5. The specification records v1.5.0's rules")
import strategy_version  # noqa: E402
spec = strategy_version.current_spec()
uni = spec.get("universe_rules", {})
ok(list(uni.get("excluded_isin_prefixes") or []) == ["INF"], "excluded ISIN prefixes are part of the spec")
ok(uni.get("piotroski_statement_fallbacks"), "Piotroski's statement fallbacks are part of the spec")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
