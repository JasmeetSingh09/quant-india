"""
gdelt_match.py: which GDELT headlines does the app's matcher assign to which company?

Stage 2 of the sentiment test (research only). Uses the app's own matcher,
rss_news._identity_terms / _mentions, unchanged (the model is frozen), so the
test measures the matching the app really does, weaknesses included.

Names come from Yahoo (the app's existing source) for companies still quoted,
and are written by hand for the few that are not. The NSE list is off-limits
under the NSE commitment (AGENTS.md rule 1).

    python research/gdelt_match.py names  <annual_reports_dir> <names.json>
    python research/gdelt_match.py sample <gdelt_dir> <names.json> <out_dir> [days_per_month]

sample reads a fixed spread of days (the 1st, 11th and 21st of each month by
default: chosen by date, not by content) and writes every match plus a random
300 for labelling by hand, so the matcher's precision is measured before any
sentiment result exists.
"""

import csv
import glob
import gzip
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "modules"))
import rss_news  # noqa: E402

# Companies in the news-period universe that Yahoo may no longer quote.
# Names as the companies called themselves; written by hand, 2026-09-26.
HAND_NAMES = {
    "DHFL": "Dewan Housing Finance Corporation Limited",
    "HDFC": "Housing Development Finance Corporation Limited",
    "RELCAPITAL": "Reliance Capital Limited",
    "MINDTREE": "Mindtree Limited",
    "PCJEWELLER": "PC Jeweller Limited",
    "PEL": "Piramal Enterprises Limited",
    "DRREDDY": "Dr. Reddy's Laboratories Limited",
    "NAUKRI": "Info Edge (India) Limited",
    "ANGELONE": "Angel One Limited",
}
FIRST_NEWS_FY = 2020     # GDELT titles start 2019-09-22


def names(reports_dir, out_path):
    import yfinance as yf
    sample = json.load(open(os.path.join(reports_dir, "full_sample.json")))
    todo = [c for c in sample if any(y >= FIRST_NEWS_FY for y in c["ranked"])]
    out = {}
    for c in todo:
        sym = c["name"]
        name, source = None, None
        if sym in HAND_NAMES:
            name, source = HAND_NAMES[sym], "hand"
        else:
            try:
                info = yf.Ticker(sym + ".NS").info or {}
                name = info.get("longName") or info.get("shortName")
                source = "yahoo" if name else None
            except Exception:
                pass
            time.sleep(0.4)
        out[sym] = {"name": name, "source": source, "isins": c["isins"], "ranked": c["ranked"],
                    "status": c["status"]}
        print(f"{sym:14} {source or 'MISSING':6} {name}", flush=True)
    json.dump(out, open(out_path, "w"), indent=1)
    print(f"\n{sum(1 for v in out.values() if v['name'])} of {len(out)} named")


def build_matchers(names_path):
    table = json.load(open(names_path))
    ms = []
    for sym, v in table.items():
        if v["name"]:
            words, pats = rss_news._identity_terms(v["name"], sym)
            ms.append((sym, words, pats))
    # Cheap prefilter: a title can match only if it contains one of these words.
    keys = set()
    for _, words, pats in ms:
        keys |= set(words)
        for p in pats:
            first = re.findall(r"[a-z0-9&]+", p.pattern.replace("\\b", " ").replace("\\s+", " ").replace("\\w*", ""))
            if first:
                keys.add(first[0])
    return ms, keys


def sample(gdelt_dir, names_path, out_dir, per_month=3):
    ms, keys = build_matchers(names_path)
    os.makedirs(out_dir, exist_ok=True)
    days = {1: [1], 2: [1, 16], 3: [1, 11, 21]}.get(per_month, [1, 11, 21])
    files = sorted(f for f in glob.glob(os.path.join(gdelt_dir, "*.tsv.gz"))
                   if int(os.path.basename(f)[6:8]) in days)
    stats = {"days": 0, "rows": 0, "titled": 0, "titles_unique": 0, "matched_titles": 0,
             "matches": 0, "multi_company_titles": 0}
    per_co = {}
    seen = set()
    all_hits = []
    for f in files:
        stats["days"] += 1
        with gzip.open(f, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                p = line.rstrip("\n").split("\t")
                stats["rows"] += 1
                if len(p) < 4 or not p[3]:
                    continue
                stats["titled"] += 1
                title = p[3]
                if title in seen:
                    continue
                seen.add(title)
                stats["titles_unique"] += 1
                toks = set(re.sub(r"[^a-z0-9& ]+", " ", title.lower()).split())
                if not toks & keys:
                    continue
                hit = [sym for sym, w, pt in ms if rss_news._mentions(title, w, pt)]
                if hit:
                    stats["matched_titles"] += 1
                    stats["matches"] += len(hit)
                    stats["multi_company_titles"] += len(hit) > 1
                    for s in hit:
                        per_co[s] = per_co.get(s, 0) + 1
                        all_hits.append((p[0][:8], p[1], s, title, "+".join(hit)))
        print(f"{os.path.basename(f)} titles {stats['titles_unique']:,} matched {stats['matched_titles']:,}", flush=True)
    with open(os.path.join(out_dir, "matches_sample_days.tsv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["day", "source", "symbol", "title", "all_symbols_matched"])
        w.writerows(all_hits)
    rng = random.Random(20260926)
    pick = rng.sample(all_hits, min(300, len(all_hits)))
    with open(os.path.join(out_dir, "label_300.tsv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["n", "day", "source", "symbol", "company", "title", "about_company (Y/N)"])
        table = json.load(open(names_path))
        for i, (d, src, s, t, _) in enumerate(pick, 1):
            w.writerow([i, d, src, s, table[s]["name"], t, ""])
    stats["companies_with_matches"] = len(per_co)
    stats["top_companies"] = sorted(per_co.items(), key=lambda kv: -kv[1])[:25]
    stats["companies_never_matched"] = sorted(set(json.load(open(names_path))) - set(per_co))
    json.dump(stats, open(os.path.join(out_dir, "match_stats.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in stats.items() if k != "companies_never_matched"}, indent=1))
    print("never matched:", len(stats["companies_never_matched"]))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "names":
        names(sys.argv[2], sys.argv[3])
    elif cmd == "sample":
        sample(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]) if len(sys.argv) > 5 else 3)
