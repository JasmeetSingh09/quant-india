"""
gdelt_strict.py: a strict research matcher for the GDELT sentiment test.

Owner decision 2026-09-28 ("A"): the app's matcher is right on about 10% of
general-news headlines (research/gdelt_match.py), so the historical test uses a
stricter matcher, and runs only if a fresh hand-labelled sample shows it is
right often enough. The app is not changed (v1.4.1 is frozen).

A headline is assigned to a company only if it names the company: its full
name, a hand-listed short name (SBI, L&T, Zomato...) or a distinctive ticker.
A single ordinary word never counts; tickers that are ordinary words or mean
other things (OIL, IDEA, IOC, NCC...) are dropped, and a few acronyms (SAIL,
BEL, HAL...) count only in capitals. When one company's term sits inside
another's at the same place ("HDFC" in "HDFC Bank"), only the longer counts.
A term claimed by two companies is dropped for both.

Attempt 0, withdrawn before any labelling (2026-09-28): the first version also
required GDELT's organisation list to contain the company. On the development
days (1st/11th/21st, already examined) that list proved unreliable: often
empty, missing companies the article is about (Hindustan Unilever), and
mangling names ("Larsen Toubro Ltd", "Reddy Laboratories", "Why Is Yes Bank").
35 of 204 companies were never matched on the check days, a recall defect that
would bias the test by company. The requirement was removed. Only match counts
from the check days had been seen; no check-day headline had been labelled.

Labelling guide, fixed before labelling. "Y" if the headline is about the
listed company or a business it runs directly (its brands, plants, divisions,
results, shares, management acting for it). "N" if it is about a separately
listed or separately incorporated relative (ICICI Securities for ICICI Bank,
SBI Mutual Fund for SBI, Kotak Life for Kotak Bank), a different company with
a similar name, or the company only as a passing word in a list of 3 or more
companies with no news about it ("Sensex: HDFC Bank, ITC, TCS among gainers"
is Y for each named mover, because a price move is news about the stock).

Acceptance rule, fixed before any labelling (this file is committed first):
  a fresh random 300 matches from days never looked at (the 6th, 16th and 26th
  of each month; seed 20260928), labelled by hand. The matcher is accepted if
  precision is at least 90% AND its 95% Wilson lower bound is at least 85%.
  If it fails, the rules may be changed, but the next check uses new days
  (the 3rd, 13th and 23rd) and every attempt is reported.

    python research/gdelt_strict.py sample <gdelt_dir> <names.json> <out_dir> <days> <seed>
      e.g. ... 6,16,26 20260928
"""

import csv
import html
import glob
import gzip
import json
import os
import random
import re
import sys

LEGAL = {"limited", "ltd", "pvt", "private", "inc", "incorporated", "plc", "corp", "corporation",
         "company", "co", "the"}

# Short names the press uses, written 2026-09-28 before any labelling. Old names
# are included where a company was renamed during 2019-2026.
ALIASES = {
    "ABB": ["abb india"], "ACC": ["acc cement", "acc cements", "acc ltd", "acc limited"],
    "ADANIENSOL": ["adani energy solutions", "adani transmission"], "ADANIGREEN": ["adani green"],
    "ADANIPORTS": ["adani ports"], "AMBER": ["amber enterprises"], "AMBUJACEM": ["ambuja cement", "ambuja cements"],
    "ANGELONE": ["angel one", "angel broking"], "APOLLO": ["apollo micro systems", "apollo micro"],
    "APOLLOHOSP": ["apollo hospitals"], "AUBANK": ["au small finance bank", "au bank", "au sfb"],
    "AUROPHARMA": ["aurobindo pharma", "aurobindo"], "AWL": ["adani wilmar", "awl agri"],
    "BAJAJ-AUTO": ["bajaj auto"], "BAJAJFINSV": ["bajaj finserv"], "BATAINDIA": ["bata india"],
    "BDL": ["bharat dynamics"], "BEL": ["bharat electronics"], "BHARTIARTL": ["bharti airtel", "airtel"],
    "BHEL": ["bharat heavy electricals"], "BPCL": ["bharat petroleum"], "BRITANNIA": ["britannia"],
    "BSE": ["bse ltd", "bse limited"], "CGPOWER": ["cg power"], "CHOLAFIN": ["cholamandalam investment", "chola finance"],
    "COFORGE": ["coforge", "niit technologies"], "CUPID": ["cupid ltd", "cupid limited"], "DABUR": ["dabur"],
    "DATAPATTNS": ["data patterns"], "DHFL": ["dewan housing"], "DIVISLAB": ["divi's laboratories", "divi's labs", "divis labs"],
    "DIXON": ["dixon technologies", "dixon tech"], "DMART": ["d-mart", "avenue supermarts"],
    "DRREDDY": ["dr reddy's", "dr. reddy's", "dr reddys"], "EICHERMOT": ["eicher motors", "royal enfield"],
    "EMBDL": ["embassy developments", "indiabulls real estate", "equinox india"], "ESCORTS": ["escorts kubota", "escorts ltd"],
    "ETERNAL": ["zomato", "eternal ltd", "eternal limited"], "FEDERALBNK": ["federal bank"],
    "GLENMARK": ["glenmark"], "GMDCLTD": ["gmdc"], "GODFRYPHLP": ["godfrey phillips"],
    "GRSE": ["garden reach shipbuilders"], "GVT&D": ["ge vernova t&d", "ge t&d india"],
    "HAL": ["hindustan aeronautics"], "HAVELLS": ["havells"], "HCLTECH": ["hcl technologies", "hcl tech", "hcltech"],
    "HDFC": ["hdfc ltd", "hdfc limited", "housing development finance"], "HDFCAMC": ["hdfc amc", "hdfc asset management"],
    "HDFCLIFE": ["hdfc life"], "HINDALCO": ["hindalco"], "HINDPETRO": ["hindustan petroleum", "hpcl"],
    "HINDUNILVR": ["hindustan unilever", "hul"], "HSCL": ["himadri speciality", "himadri"],
    "ICICIGI": ["icici lombard"], "ICICIPRULI": ["icici prudential life", "icici pru life"],
    "IDEA": ["vodafone idea"], "IEX": ["indian energy exchange"], "INDHOTEL": ["indian hotels", "ihcl"],
    "INDIGO": ["interglobe aviation", "indigo"], "IOC": ["indian oil", "iocl"], "JINDALSTEL": ["jindal steel", "jspl"],
    "JIOFIN": ["jio financial"], "JUBLFOOD": ["jubilant foodworks"], "KALYANKJIL": ["kalyan jewellers"],
    "KAYNES": ["kaynes technology", "kaynes"], "KOTAKBANK": ["kotak mahindra bank", "kotak bank"],
    "LAURUSLABS": ["laurus labs"], "LENSKART": ["lenskart"], "LICHSGFIN": ["lic housing finance"],
    "LICI": ["lic", "life insurance corporation"], "LT": ["l&t", "larsen & toubro", "larsen and toubro"],
    "LTF": ["l&t finance"], "LTM": ["ltimindtree", "lti mindtree", "ltim"], "M&M": ["mahindra & mahindra", "mahindra and mahindra", "m&m"],
    "M&MFIN": ["mahindra finance", "mahindra & mahindra financial"], "MARUTI": ["maruti suzuki", "maruti"],
    "MAXHEALTH": ["max healthcare"], "MAZDOCK": ["mazagon dock"], "MCX": ["multi commodity exchange"],
    "MOTHERSON": ["samvardhana motherson", "motherson sumi", "motherson"], "MTARTECH": ["mtar technologies", "mtar"],
    "MUTHOOTFIN": ["muthoot finance"], "NATIONALUM": ["nalco", "national aluminium"], "NAUKRI": ["info edge", "naukri"],
    "NESTLEIND": ["nestle india"], "NETWEB": ["netweb technologies", "netweb"], "NYKAA": ["nykaa", "fsn e-commerce"],
    "OFSS": ["oracle financial services"], "OLAELEC": ["ola electric"], "ONGC": ["oil and natural gas"],
    "PATANJALI": ["patanjali foods", "ruchi soya"], "PAYTM": ["paytm", "one97", "one 97"], "PCJEWELLER": ["pc jeweller"],
    "PEL": ["piramal enterprises"], "PERSISTENT": ["persistent systems"], "PFC": ["power finance corporation"],
    "PNB": ["punjab national bank"], "POLICYBZR": ["policybazaar", "pb fintech"], "POLYCAB": ["polycab"],
    "POWERGRID": ["power grid corporation", "powergrid"], "POWERINDIA": ["hitachi energy india"], "PVRINOX": ["pvr inox", "pvr"],
    "RECLTD": ["rec ltd", "rec limited", "rural electrification corporation"], "RELIANCE": ["reliance industries", "ril"],
    "RVNL": ["rail vikas nigam"], "SAIL": ["steel authority of india"], "SAMMAANCAP": ["sammaan capital", "indiabulls housing finance"],
    "SBICARD": ["sbi card", "sbi cards"], "SBILIFE": ["sbi life"], "SBIN": ["sbi", "state bank of india"],
    "SHRIRAMFIN": ["shriram finance", "shriram transport finance"], "SIEMENS": ["siemens ltd", "siemens limited", "siemens india"],
    "SUNPHARMA": ["sun pharma", "sun pharmaceutical"], "SUNTV": ["sun tv"], "TATACONSUM": ["tata consumer"],
    "TATAPOWER": ["tata power"], "TCS": ["tata consultancy services", "tcs"], "TECHM": ["tech mahindra"],
    "TEJASNET": ["tejas networks"], "TITAN": ["titan company", "titan ltd"], "TMCV": ["tata motors commercial vehicles", "tmcv"],
    "TMPV": ["tata motors"], "TORNTPHARM": ["torrent pharma", "torrent pharmaceuticals"], "TRENT": ["trent ltd", "trent limited"],
    "TVSMOTOR": ["tvs motor"], "ULTRACEMCO": ["ultratech cement", "ultratech"], "UNIONBANK": ["union bank of india"],
    "UNITDSPR": ["united spirits"], "VBL": ["varun beverages"], "VMM": ["vishal mega mart"], "WAAREEENER": ["waaree energies"],
    "WOCKPHARMA": ["wockhardt"], "YESBANK": ["yes bank"], "ZEEL": ["zee entertainment", "zeel"],
    "ZYDUSLIFE": ["zydus lifesciences", "zydus", "cadila healthcare"],
}
# Replaces the Yahoo name where Yahoo's is today's name for a different company.
NAME_OVERRIDE = {"TMCV": None, "TMPV": "Tata Motors"}
# Tickers that are ordinary words or mean something else in the news.
DROP_TICKER = {"oil", "idea", "ioc", "titan", "trent", "sail", "ncc", "bse", "mcx", "iex", "ltm", "acc", "cupid",
               "amber", "apollo", "escorts", "eternal", "siemens", "abb", "dixon", "persistent", "patanjali",
               "bel", "hal", "pel", "upl"}
# Acronyms that count only when printed in capitals (not in an all-capitals headline).
UPPER_ONLY = {"SAIL": "SAIL", "BEL": "BEL", "HAL": "HAL", "IEX": "IEX", "MCX": "MCX", "UPL": "UPL", "IOC": "IOCL"}


def norm(s):
    s = (s or "").lower().replace("’", "'")
    s = re.sub(r"\([^)]*\)", " ", s)                  # "(India)"
    s = re.sub(r"[^a-z0-9&' ]+", " ", s)
    return " ".join(s.split())


def core(name):
    toks = [t for t in norm(name).split() if t not in LEGAL]
    return " ".join(toks)


def build(names_path):
    table = json.load(open(names_path))
    terms, confirm = {}, {}
    for sym, v in table.items():
        full = NAME_OVERRIDE.get(sym, v["name"])
        t = set(norm(a) for a in ALIASES.get(sym, []))
        c = core(full) if full else ""
        if c and (len(c.split()) >= 2 or sym in ALIASES and c in t or c == sym.lower()):
            t.add(c)
        if c.endswith(" india") and len(c.split()) >= 3:
            t.add(c[:-6])                                # "maruti suzuki india" -> "maruti suzuki"
        tick = re.sub(r"[^a-z0-9]", "", sym.lower())
        if len(tick) >= 3 and tick not in DROP_TICKER:
            t.add(tick)
        if len(c.split()) == 1 and c and c not in DROP_TICKER:
            t.add(c)                                     # single-word names: infosys, wipro, cipla
        terms[sym] = t
        confirm[sym] = {core(x) for x in t if core(x)} | ({c} if c else set())
    # A term claimed by two companies identifies neither.
    owners = {}
    for sym, t in terms.items():
        for x in t:
            owners.setdefault(x, set()).add(sym)
    clash = {x for x, o in owners.items() if len(o) > 1}
    for sym in terms:
        terms[sym] -= clash
    rx = {sym: [(x, re.compile(r"(?<![a-z0-9&])" + re.escape(x) + r"(?![a-z0-9&])")) for x in sorted(t, key=len, reverse=True)]
          for sym, t in terms.items()}
    return rx, confirm, sorted(clash)


def match(title, orgs, rx, confirm, require_org=False):
    title = html.unescape(title or "")
    t = norm(title)
    spans = []
    for sym, pats in rx.items():
        for x, p in pats:
            for m in p.finditer(t):
                spans.append((m.start(), m.end(), sym))
    shouting = sum(ch.isupper() for ch in title) > 0.6 * max(1, sum(ch.isalpha() for ch in title))
    if not shouting:
        for sym, word in UPPER_ONLY.items():
            if sym in rx and re.search(r"(?<![A-Za-z])" + word + r"(?![A-Za-z])", title):
                spans.append((-1, -1, sym))
    # longest term wins where two companies' terms overlap
    keep = set()
    for s, e, sym in spans:
        if s >= 0 and any(s2 <= s and e <= e2 and (e2 - s2) > (e - s) and sym2 != sym for s2, e2, sym2 in spans if s2 >= 0):
            continue
        keep.add(sym)
    if not keep or not require_org:
        return sorted(keep)
    org_names = {core(o.rsplit(",", 1)[0]) for o in (orgs or "").split(";") if o}
    return sorted(sym for sym in keep if org_names & confirm[sym])


def sample(gdelt_dir, names_path, out_dir, days, seed):
    rx, confirm, clash = build(names_path)
    os.makedirs(out_dir, exist_ok=True)
    days = {int(d) for d in days.split(",")}
    files = sorted(f for f in glob.glob(os.path.join(gdelt_dir, "*.tsv.gz")) if int(os.path.basename(f)[6:8]) in days)
    seen, hits, per = set(), [], {}
    n_titles = 0
    for f in files:
        with gzip.open(f, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                p = line.rstrip("\n").split("\t")
                if len(p) < 5 or not p[3] or p[3] in seen:
                    continue
                seen.add(p[3])
                n_titles += 1
                for sym in match(p[3], p[4], rx, confirm):
                    hits.append((p[0][:8], p[1], sym, p[3]))
                    per[sym] = per.get(sym, 0) + 1
    pick = random.Random(seed).sample(hits, min(300, len(hits)))
    table = json.load(open(names_path))
    tag = f"days{'-'.join(str(d) for d in sorted(days))}_seed{seed}"
    with open(os.path.join(out_dir, f"strict_label_300_{tag}.tsv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["n", "day", "source", "symbol", "company", "title", "about_company (Y/N)"])
        for i, (d, src, s, t) in enumerate(pick, 1):
            w.writerow([i, d, src, s, table[s]["name"], t, ""])
    stats = {"days": len(files), "unique_titles": n_titles, "matches": len(hits),
             "matched_share": round(len(hits) / max(n_titles, 1), 5), "companies_matched": len(per),
             "companies_never_matched": sorted(set(table) - set(per)), "dropped_clashing_terms": clash,
             "top": sorted(per.items(), key=lambda kv: -kv[1])[:30]}
    json.dump(stats, open(os.path.join(out_dir, f"strict_stats_{tag}.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in stats.items() if k != "companies_never_matched"}, indent=1))
    print("never matched:", len(stats["companies_never_matched"]), stats["companies_never_matched"])


if __name__ == "__main__":
    if sys.argv[1] == "sample":
        sample(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], int(sys.argv[6]))
