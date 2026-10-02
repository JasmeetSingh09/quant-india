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

print("\n6. v1.4.2: one ordinary word from a longer name is never enough")
# docs/PROPOSAL_NEWS_MATCHER_FIX_2026-10-01.md. Each headline is a real kind of
# false match measured on general news before the fix.
OIL = ("Oil India Limited", "OIL.NS")
GREEN = ("Adani Green Energy Limited", "ADANIGREEN.NS")
IDFC = ("IDFC First Bank Limited", "IDFCFIRSTB.NS")
BHEL = ("Bharat Heavy Electricals Limited", "BHEL.NS")
JUST = ("Just Dial Limited", "JUSTDIAL.NS")
LIC = ("Life Insurance Corporation of India", "LICI.NS")
IRFC = ("Indian Railway Finance Corporation Limited", "IRFC.NS")
BOB = ("Bank of Baroda", "BANKBARODA.NS")
TPOWER = ("The Tata Power Company Limited", "TATAPOWER.NS")
INFY = ("Infosys Limited", "INFY.NS")
for name, tk, head in [
    (*OIL, "COVID-19: India sets new record of cases"),
    (*GREEN, "Sensex closes in green, Nifty above 11,900"),
    (*IDFC, "First batch of Covid-19 vaccines en route from India"),
    (*BHEL, "IMD issues orange alert: heavy rains expected"),
    (*JUST, "Apple just delayed these iPhone features"),
    (*LIC, "HDFC Life Insurance raises Rs 1,000 crore"),
    (*IRFC, "Indian Railways cancels 277 trains due to fog"),
    (*BOB, "Bank of Ceylon takes the lead in economic revival"),
    (*SBIN, "State Bank of Mauritius opens Mumbai branch"),
]:
    ok(not matches(name, tk, head), f"{tk.replace('.NS',''):<11} rejects: {head[:58]}")
for name, tk, head in [
    (*OIL, "Oil India Q2 profit jumps 40%"),
    (*GREEN, "Adani Green Energy Q4 net profit declines"),
    (*IDFC, "IDFC First Bank board approves fund raising"),
    (*BHEL, "BHEL bags 2,400 MW order from NLC India"),
    (*JUST, "Just Dial shares hit upper circuit"),
    (*BOB, "Bank of Baroda Q2 profit doubles"),
    (*TPOWER, "Tata Power signs agreement with SJVNL"),
    (*INFY, "Infosys wins $1.5 billion deal"),
    (*ADANI, "Adani Ports Q1 results: cargo volumes up 11% year on year"),
    (*TATAMOT, "Tata Motors sales jump 15% in August"),
]:
    ok(matches(name, tk, head), f"{tk.replace('.NS',''):<11} accepts: {head[:58]}")
w_oil, _ = _identity_terms(*OIL)
ok("india" not in w_oil, f"'india' alone never identifies Oil India ({sorted(w_oil)})")
w_infy, _ = _identity_terms(*INFY)
ok("infosys" in w_infy, "a one-word name still identifies itself")
_, p_tp = _identity_terms(*TPOWER)
ok(all(not x.pattern.startswith(r"\bthe") for x in p_tp), "a leading 'the' is dropped from the name")

print("\n7. v1.4.3: Google results are checked, with hand-checked short names")
# docs/PROPOSAL_STEP1_NEWS_FILTER_2026-10-02.md. Headlines are from the live
# app's news on 2026-10-01.
from rss_news import _keep_search_item, _keep_market_item, _short_name_patterns, _is_list_headline


def kept_search(name, tk, title):
    w, p = _identity_terms(name, tk)
    return _keep_search_item({"title": title, "description": ""}, w, p, _short_name_patterns(tk))


HUL = ("Hindustan Unilever Limited", "HINDUNILVR.NS")
HCL = ("HCL Technologies Limited", "HCLTECH.NS")
for name, tk, head in [
    (*SBIN, "SBI, MS Strategic, BoB and insurers may cut stake sale in NSE IPO"),
    (*HUL, "HUL Q1 results: Net profit falls 4% to Rs 2,631 crore, shares decline 7%"),
    (*HCL, "HCL Tech stock crashes over 10% after Q4 miss"),
    (*OIL, "Oil India is beating ONGC. Can its production edge last?"),
    (*INFY, "Infosys Shares Fall 2.02% in Midday Trade"),
]:
    ok(kept_search(name, tk, head), f"{tk.replace('.NS',''):<11} keeps: {head[:58]}")
for name, tk, head in [
    (*OIL, "Indian shares post worst day in 10 weeks on oil spike, proposed insurance curbs"),
    (*OIL, "India stocks log fifth weekly loss as oil fears grip markets"),
    (*SBIN, "Top 12 Bank Stocks To Buy In India October 2026"),
    (*INFY, "Indian Stock Market Weekly Round-Up: Bears Take Charge as Nifty Slides 2%"),
]:
    ok(not kept_search(name, tk, head), f"{tk.replace('.NS',''):<11} drops: {head[:58]}")

print("\n8. v1.4.3: list headlines are dropped, real news headed like a list is not")
ok(_is_list_headline("Stocks to Watch Today: Astra Microwave, Navin Fluorine, Tata Steel"), "'Stocks to watch' is a list")
ok(_is_list_headline("Stocks in news: UltraTech Cement, Tata Motors PV, Axis Bank"), "'Stocks in news' is a list")
ok(not _is_list_headline("Canara Bank shares in focus as its board approves plan to raise capital"),
   "'in focus as the board approves...' is real news, not a list")
ok(not _is_list_headline("Buzzing Stocks: EMS shares surge 9%; Hero MotoCorp slips 2% as exports decline"),
   "a 'buzzing stocks' round-up with a reason is kept")
w_ts, p_ts = _identity_terms("Tata Steel Limited", "TATASTEEL.NS")
ok(not _keep_market_item({"title": "Stocks to Watch Today: Astra Microwave, Tata Steel, Swiggy", "description": ""}, w_ts, p_ts),
   "a market-feed list is dropped in step 2 too")
ok(_keep_market_item({"title": "Tata Steel Q1 net profit rises 40%", "description": ""}, w_ts, p_ts),
   "real market-feed news is still kept")
ok(not any(p.search("sbi") for p in _short_name_patterns("TCS.NS")) and _short_name_patterns("UNKNOWN.NS") == [],
   "short names belong only to their own company; unknown tickers have none")

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
