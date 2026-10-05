"""
security_names_test.py — company names in the shared database (2026-10-05).

Production's stock_universe list is a local SQLite file that is empty while NSE
collection is paused, so name search failed there ("20 microns" found nothing).
This checks the shared-database names table and stock_universe's fallback to it.
Offline: a SQLite file this test creates.
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

import security_names as SN  # noqa: E402
from pathlib import Path  # noqa: E402

REAL_SEED = SN.SEED_FILE
SN.SEED_FILE = Path(TMP) / "no_seed_here.json"      # start empty; the shipped file is tested at the end

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


ROWS = [
    {"yf_ticker": "20MICRONS.NS", "symbol": "20MICRONS", "company_name": "20 Microns Limited", "isin": "INE144J01027", "series": "EQ"},
    {"yf_ticker": "RELIANCE.NS", "symbol": "RELIANCE", "company_name": "Reliance Industries Limited", "isin": "INE002A01018", "series": "EQ"},
    {"yf_ticker": "RPOWER.NS", "symbol": "RPOWER", "company_name": "Reliance Power Limited", "isin": "INE614G01033", "series": "EQ"},
    {"yf_ticker": "RELINFRA.NS", "symbol": "RELINFRA", "company_name": "Reliance Infrastructure Limited", "isin": "INE036A01016", "series": "EQ"},
    {"yf_ticker": "SBIN.NS", "symbol": "SBIN", "company_name": "State Bank of India", "isin": "INE062A01020", "series": "EQ"},
    {"yf_ticker": "OBRIEN.NS", "symbol": "OBRIEN", "company_name": "O'Brien & Sons Limited", "isin": "INE000000001", "series": "EQ"},
]

print("\n1. Load and look up")
r = SN.load(ROWS, source="test list")
ok(r["loaded"] == 6 and SN.count() == 6, "six names loaded")
ok(SN.lookup("SBIN")["company_name"] == "State Bank of India" and SN.lookup("SBIN.NS")["isin"] == "INE062A01020",
   "lookup works by symbol or ticker")
ok(SN.lookup("NOPE") is None, "an unknown symbol is None, not a guess")
SN.load([dict(ROWS[0], company_name="20 Microns Ltd")], source="refresh")
ok(SN.count() == 6 and SN.lookup("20MICRONS")["company_name"] == "20 Microns Ltd", "reloading updates, never duplicates")
ok(SN.lookup("OBRIEN")["company_name"] == "O'Brien & Sons Limited", "an apostrophe in a name is stored intact")

print("\n2. Search by name, not only by symbol")
ok([x["symbol"] for x in SN.search("20 microns")] == ["20MICRONS"], "'20 microns' finds 20 Microns")
rel = [x["symbol"] for x in SN.search("reliance")]
ok(rel[0] == "RELIANCE" and set(rel) == {"RELIANCE", "RPOWER", "RELINFRA"},
   f"'reliance' finds all three, exact symbol first ({rel})")
ok([x["symbol"] for x in SN.search("state bank")] == ["SBIN"], "'state bank' finds SBI by name")
ok(SN.search("") == [], "an empty query returns nothing")

print("\n3. stock_universe falls back to these names when its own list is empty")
import stock_universe as SU  # noqa: E402
ok([x["symbol"] for x in SU.search_stocks("20 microns")] == ["20MICRONS"], "search_stocks finds a company by name")
ok((SU.get_stock_by_symbol("SBIN") or {}).get("company_name") == "State Bank of India",
   "get_stock_by_symbol returns the stored name")

print("\n4. The shipped list seeds production's empty table")
ok(REAL_SEED.exists() and REAL_SEED.parent.name != "data",
   "the shipped file exists and is not under backend/data, which production's disk mount hides")
r = SN.seed_from_file(REAL_SEED)
ok(r["loaded"] >= 2500, f"{r['loaded']} names loaded from {REAL_SEED.name}")
ok(SN.lookup("20MICRONS")["company_name"].lower().startswith("20 microns"), "20 Microns has its real name")
ok(SN.lookup("TCS")["company_name"].lower().startswith("tata consultancy"), "TCS is Tata Consultancy Services")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
