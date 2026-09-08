"""
metric_applicability_test.py — a dash must not mean two different things.

SBIN's page showed a dash against EV/EBITDA, Gross Margin, D/E, Current Ratio
and Quick Ratio, which reads as a data failure. Measured across fourteen
securities, every gap was financial-sector and all eleven non-financials were
complete. The figures are absent from the data because they are absent from the
concept: a bank has no cost of goods sold and its current liabilities are
customer deposits.

So the rule under test is narrow and it cuts both ways:

    say "not applicable" only about the CONCEPT, never to excuse a data gap;
    and never let it hide a value that is actually present.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from metric_applicability import applicability, annotate, _kind  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


print("=" * 72)
print("CLASSIFICATION — FROM THE REAL INDUSTRY STRINGS")
print("=" * 72)

# Exactly the strings production returned for these tickers.
REAL = [
    ("SBIN", "Financial Services", "Banks - Regional", "bank"),
    ("HDFCBANK", "Financial Services", "Banks - Regional", "bank"),
    ("ICICIBANK", "Financial Services", "Banks - Regional", "bank"),
    ("BAJFINANCE", "Financial Services", "Credit Services", "financial"),
    ("RELIANCE", "Energy", "Oil & Gas Refining & Marketing", "other"),
    ("TCS", "Technology", "Information Technology Services", "other"),
    ("ITC", "Consumer Defensive", "Tobacco", "other"),
    ("MARUTI", "Consumer Cyclical", "Auto Manufacturers", "other"),
    ("NTPC", "Utilities", "Utilities - Regulated Electric", "other"),
    ("DMART", "Consumer Defensive", "Discount Stores", "other"),
]
for tkr, sec, ind, want in REAL:
    got = _kind(sec, ind)
    check(f"{tkr:<11} {ind[:30]:<32} -> {want}", got == want, f"got {got}")

print()
print("=" * 72)
print("WHAT IS NOT APPLICABLE TO A BANK")
print("=" * 72)

bank = applicability("Financial Services", "Banks - Regional")
for m in ("ev_ebitda", "ebitda", "gross_margin", "current_ratio",
          "quick_ratio", "debt_to_equity"):
    check(f"{m} is not applicable to a bank", m in bank)
    if m in bank:
        check(f"  ...and it says why", len(bank[m]) > 40, bank[m][:56] + "...")

for m in ("pe_ratio", "price_to_book", "roe", "roa", "profit_margin",
          "operating_margin"):
    check(f"{m} REMAINS applicable to a bank", m not in bank,
          "banks have earnings, book value and margins")

print()
print("=" * 72)
print("AN NBFC IS NOT A BANK")
print("=" * 72)

nbfc = applicability("Financial Services", "Credit Services")
check("D/E IS applicable to an NBFC", "debt_to_equity" not in nbfc,
      "production returns a real D/E for BAJFINANCE")
check("but EV/EBITDA is still not", "ev_ebitda" in nbfc)
check("and the current ratio is still not", "current_ratio" in nbfc)

print()
print("=" * 72)
print("NON-FINANCIALS ARE UNTOUCHED")
print("=" * 72)

for sec, ind in (("Energy", "Oil & Gas Refining & Marketing"),
                 ("Technology", "Information Technology Services"),
                 ("Consumer Cyclical", "Auto Manufacturers"),
                 ("Basic Materials", "Steel")):
    check(f"{ind[:34]:<36} nothing excluded",
          applicability(sec, ind) == {})

check("an unknown industry excludes nothing",
      applicability("Whatever", "Something New") == {},
      "the default must be to show the metric, not to excuse it")
check("sector alone does not trigger it",
      applicability("Financial Services", None) == {},
      "'Financial Services' also covers exchanges and fintech")

print()
print("=" * 72)
print("IT MUST NOT HIDE A VALUE THAT IS PRESENT")
print("=" * 72)

a = annotate({"sector": "Financial Services", "industry": "Banks - Regional",
              "current_ratio": 1.4, "gross_margin": 0.0, "pe_ratio": 10.8,
              "roe": 0.15, "roa": None})
check("applicability is about the concept, not the value",
      "current_ratio" in a["not_applicable"],
      "the caller still receives the 1.4 and decides")
check("a genuinely absent APPLICABLE metric is listed as unavailable",
      "roa" in a["unavailable"], f"{a['unavailable']}")
check("a not-applicable metric is NOT listed as unavailable",
      "current_ratio" not in a["unavailable"]
      and "gross_margin" not in a["unavailable"],
      "that conflation is the whole bug")
check("a present metric is in neither list",
      "pe_ratio" not in a["unavailable"]
      and "pe_ratio" not in a["not_applicable"])
check("the two are explained in the payload", "conflated" in a["note"])

sbin_shaped = annotate({
    "sector": "Financial Services", "industry": "Banks - Regional",
    "pe_ratio": 10.77, "forward_pe": 9.61, "peg_ratio": 0.53,
    "ev_ebitda": None, "price_to_book": 1.496, "roe": 0.15177, "roa": 0.01132,
    "gross_margin": 0.0, "operating_margin": 0.35717, "profit_margin": 0.22376,
    "debt_to_equity": None, "current_ratio": None, "quick_ratio": None,
    "ebitda": None})
check("on the real SBIN payload, nothing is reported as unavailable",
      sbin_shaped["unavailable"] == [],
      f"every gap explained as inapplicable: {sbin_shaped['unavailable']}")
check("and five metrics are explained rather than dashed",
      len(sbin_shaped["not_applicable"]) == 6,
      f"{sorted(sbin_shaped['not_applicable'])}")

print()
print("=" * 72)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
