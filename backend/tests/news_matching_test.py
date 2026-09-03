"""
news_matching_test.py — an article about RBL Bank is not news about SBIN.

Every headline below was really attributed to that stock by production on
2026-09-03, and really scored by FinBERT into that stock's sentiment factor.
The old filter kept any name token longer than two characters and admitted an
article on any single hit, so:

  - "and" was a keyword for Adani Ports and ONGC, whose legal names contain it
  - "bank" made every banking story a State Bank of India story
  - "coal" made every Bharat Coking Coal story a Coal India story
  - matching was substring, so ITC's ticker matched the word "switch"

Measured over the 18 Top Picks: 206 of 360 articles mentioned the company, and
the median stock drew only 14.9% of its sentiment weight from articles about
itself. The intruders were general market stories published that morning, so
their decay weight was near 1.0 while genuine company news sat older and
lighter — SBIN and ONGC reported sentiment confidence 1.00 on zero relevant
articles while NESTLEIND, at 100% relevant, reported 0.0001.

Precision matters more than recall here and the tests are written that way. A
missed article costs a little evidence, and less evidence means a score shrunk
toward neutral — the honest direction. An article about another company invents
an opinion out of nothing.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from rss_news import _identity_terms, _mentions, _GENERIC_TOKENS, _STOPWORDS

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


def matches(long_name, ticker, headline):
    w, p = _identity_terms(long_name, ticker)
    return _mentions(headline, w, p)


SBIN = ("State Bank of India", "SBIN.NS")
ONGC = ("Oil and Natural Gas Corporation Limited", "ONGC.NS")
ADANI = ("Adani Ports and Special Economic Zone Limited", "ADANIPORTS.NS")
COAL = ("Coal India Limited", "COALINDIA.NS")
SUN = ("Sun Pharmaceutical Industries Limited", "SUNPHARMA.NS")
TCS = ("Tata Consultancy Services Limited", "TCS.NS")
TATAMOT = ("Tata Motors Limited", "TATAMOTORS.NS")
REL = ("Reliance Industries Limited", "RELIANCE.NS")
RELPOWER = ("Reliance Power Limited", "RPOWER.NS")
NESTLE = ("Nestle India Limited", "NESTLEIND.NS")
ITC = ("ITC Limited", "ITC.NS")
HDFCB = ("HDFC Bank Limited", "HDFCBANK.NS")

print("\n1. The exact articles production mis-filed are now rejected")
for name, tk, head in [
    (*SBIN, "RBL Bank surges as board to mull overseas debt fundraising plan"),
    (*SBIN, "Indices trade with sideways; private bank shares advance"),
    (*SBIN, "Plastic pipes makers poised to bounce back in Q2 as PVC prices recover"),
    (*ONGC, "Dollar index pulls back notably as oil halts recent rally; sharp yen rally weighs"),
    (*ONGC, "India bonds gain as RBI FX inflows lift liquidity, spur short-term debt buying"),
    (*ADANI, "Defence re-rating buzz | Raymond share price hits 52-week high"),
    (*ADANI, "Bonus issue alert! Multibagger Titan Biotech announces its maiden 1:4 bonus issue"),
    (*ADANI, "Wakefit shares jump over 4% as Nomura initiates coverage. Check target price"),
    (*COAL, "Bharat Coking Coal share price crashes 7% after Q1FY27 results"),
    (*COAL, "BSE rules out coal exchange entry while MCX, NSE receive SEBI nod"),
    (*TCS, "Tata Consumer Share Price Live Updates: Tata Consumer News"),
]:
    ok(not matches(name, tk, head), f"{tk.replace('.NS',''):<11} rejects: {head[:58]}")

print("\n2. The company's own news is still found")
for name, tk, head in [
    (*SBIN, "State Bank of India Q1 profit rises 12% to Rs 18,300 crore"),
    (*SBIN, "SBIN shares hit 52-week high after strong quarterly results"),
    (*ONGC, "ONGC to invest Rs 1 lakh crore in exploration over five years"),
    (*ONGC, "Oil and Natural Gas Corporation announces dividend"),
    (*ADANI, "Adani Ports Q1 results: cargo volumes up 11% year on year"),
    (*COAL, "Coal India subsidiary Mahanadi Coalfields files draft papers for IPO"),
    (*SUN, "Sun Pharma Share Price Live Updates: Sun Pharma's Market Update"),
    (*SUN, "Sun Pharmaceutical schedules analyst meetings in Mumbai"),
    (*TCS, "Tata Consultancy Services wins $1 billion deal"),
    (*TCS, "TCS shares fall 2% after Q1 margin miss"),
    (*NESTLE, "Nestle India shares jump 6% to hit 52-week high on strong Q4 results"),
    (*REL, "Reliance shares rise 3% on Jio tariff hike buzz"),
]:
    ok(matches(name, tk, head), f"{tk.replace('.NS',''):<11} accepts: {head[:58]}")

print("\n3. Sibling companies are not confused with each other")
ok(not matches(*TCS[:2], "Tata Motors sales jump 15% in August"),
   "TCS does not claim Tata Motors news")
ok(matches(*TATAMOT[:2], "Tata Motors sales jump 15% in August"),
   "Tata Motors does claim it")
ok(not matches(*RELPOWER[:2], "Reliance Industries announces Jio results"),
   "Reliance Power does not claim Reliance Industries news")
ok(matches(*RELPOWER[:2], "Reliance Power shares hit upper circuit"),
   "Reliance Power does claim its own")
ok(not matches(*COAL[:2], "Bharat Coking Coal IPO listing date announced"),
   "Coal India does not claim Bharat Coking Coal")

print("\n4. The specific defects that caused this")
w_adani, _ = _identity_terms(*ADANI)
w_ongc, _ = _identity_terms(*ONGC)
ok("and" not in w_adani and "and" not in w_ongc,
   "'and' is never an identifying word")
ok(all(s in _GENERIC_TOKENS for s in _STOPWORDS),
   "every stopword is blocked from identifying a company")
ok(not matches(*ITC[:2], "Engineers switch to new grid protocol"),
   "substring matching is gone — ITC no longer matches 'switch'")
ok(matches(*ITC[:2], "ITC, Britannia shares fall after FSSAI proposal"),
   "but ITC as a whole word still matches")
w_sbin, _ = _identity_terms(*SBIN)
ok("bank" not in w_sbin, "'bank' alone never identifies SBIN")
w_coal, _ = _identity_terms(*COAL)
ok("coal" not in w_coal, "'coal' alone never identifies Coal India")
w_rel, _ = _identity_terms(*REL)
ok(len(w_rel) > 0,
   f"a company whose whole name is a group name still has terms ({sorted(w_rel)})")

print("\n5. Degenerate inputs do not crash or match everything")
for nm, tk, label in [("", "", "empty name and ticker"),
                      ("", "XYZ.NS", "empty name"),
                      ("A", "A.NS", "one-letter name"),
                      ("Limited", "LTD.NS", "name that is only a legal suffix")]:
    try:
        w, p = _identity_terms(nm, tk)
        hit = _mentions("Some unrelated market headline about banks and oil", w, p)
        ok(not hit, f"{label}: matches nothing")
    except Exception as e:
        ok(False, f"{label}: raised {type(e).__name__}")

print("\n" + "=" * 68)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
