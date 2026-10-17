"""
ar_gap_list.py — what stands between the annual-report collection and the 80% gate.

Reproduces the coverage count of docs/VALUE_QUALITY_RESULT_2026-10-13.md (same
eligibility, same financial-company list, same acceptance rule as the 2026-10-06
coverage script), then gives every incomplete company-year ONE cause and ONE
recovery route:

  read_incomplete   a right-year report was read but an input was not accepted
                    -> reader/validation work on a file we already have (no download)
  file_unusable     a file is on disk for that year but it is not a usable
                    right-year report (wrong year, wrong company, no statements
                    located, or not yet read)
  no_file           nothing on disk -> a download is needed

Download routes (no_file and file_unusable):
  company_site      the company's own site is known and has served scripts before
  hand_only_site    the site blocks scripts, shows a CAPTCHA or needs clicks;
                    the owner clicks (never automated, never a CAPTCHA solved)
  bse_by_hand       no usable company copy known; BSE's annual-report archive,
                    downloaded BY HAND only (BSE's terms forbid automation)

Priority: P1 companies that stopped trading (they carry the survivorship test),
P2 FY2012-2015 (the thinnest years), P3 the rest.

Read-only: it reads the local collection and writes the gap list. Nothing is
downloaded or fetched.

    python research/ar_gap_list.py <annual_reports_dir> <out.csv>
"""
import collections
import csv
import glob
import json
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\seeraj\quant_data\annual_reports"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "manifest", "gap_list.csv")

# The financial-company list the 2026-10-13 coverage used (banks, lenders, housing
# finance, insurers, exchanges/depositories), unchanged.
FIN = set("""ALBK ANGELONE AUBANK AXISBANK BAJAJFINSV BAJFINANCE BANDHANBNK BANKBARODA BANKINDIA BHARATFIN BSE CANBK
CDSL CHOLAFIN DHFL FEDERALBNK GROWW HDFC HDFCAMC HDFCBANK HDFCLIFE HUDCO ICICIBANK ICICIGI ICICIPRULI IDBI IDFC
IDFCFIRSTB IFCI INDIABULLS INDUSINDBK IREDA IRFC JIOFIN KOTAKBANK KTKBANK LICHSGFIN LICI LTF M&MFIN MCX MUTHOOTFIN
ORIENTBANK PEL PFC PNB RBLBANK RECLTD RELCAPITAL SAMMAANCAP SBICARD SBILIFE SBIN SHRIRAMFIN UCOBANK UJJIVAN
UNIONBANK YESBANK POLICYBZR""".split())

# Sites recorded in the pilot notes as refusing scripts, CAPTCHA-protected, or
# needing clicks (2026-10-02..06). The owner downloads these by hand.
HAND_ONLY = {
    "INFY": "returns 403 to scripts", "HINDUNILVR": "returns 403 to scripts",
    "NTPC": "Radware CAPTCHA (never solved by a script)", "M&M": "filter posts through /antibot",
    "MARUTI": "listing redirects; URL pattern failed", "ASIANPAINT": "custom widget",
    "JINDALSTEL": "needs clicks", "LUPIN": "needs clicks", "DRREDDY": "site 404s",
    "BAJAJ-AUTO": "files served were not valid PDFs",
}

fs = json.load(open(os.path.join(ROOT, "full_sample.json"), encoding="utf-8"))
acc = json.load(open(os.path.join(ROOT, "review_v11", "accepted.json"), encoding="utf-8"))
ex = {r["file"]: r for r in json.load(open(os.path.join(ROOT, "extract_v10_full3.json"), encoding="utf-8"))}
YC = json.load(open(os.path.join(ROOT, "manifest", "year_confirm_2026-10-06.json"), encoding="utf-8"))
wrong = set(json.load(open(os.path.join(ROOT, "manifest", "wrong_company_2026-10-06.json"), encoding="utf-8")))
missing_meta = json.load(open(os.path.join(ROOT, "manifest", "missing_2026-10-06.json"), encoding="utf-8"))

NEED_V = ("profit_for_year", "total_equity", "share_capital")
NEED_Q = ("profit_for_year", "total_equity", "total_assets", "operating_cash_flow", "revenue")


def ok(f, k, prev=False):
    v = f.get(k)
    return bool(v and v.get("accepted") and v.get("current") is not None
                and (not prev or v.get("previous") is not None))


def score(rec):
    f, chk = rec["figures"], rec.get("checks", {})
    face = chk.get("face_value") is True
    v = all(ok(f, k) for k in NEED_V) and face
    q = all(ok(f, k) for k in NEED_Q) and ok(f, "revenue", prev=True)
    miss = [k for k in NEED_Q + ("share_capital", "eps_basic") if not ok(f, k)]
    if not face:
        miss.append("face_check")
    if not ok(f, "revenue", prev=True) and "revenue" not in miss:
        miss.append("revenue_prev")
    return v, q, miss


def fy_of(name):
    m = re.search(r"FY(\d{4})", os.path.basename(name))
    return int(m.group(1)) if m else None


def right_year(name):
    y = fy_of(name)
    yc = YC.get(name) or {}
    return y is not None and ((ex.get(name) or {}).get("fy") == y or yc.get("found") == y)


# Accepted readings of right-year, right-company files (identical to the 2026-10-06 rule).
by = collections.defaultdict(list)
for name, rec in acc.items():
    if name in wrong or fy_of(name) is None or not right_year(name):
        continue
    by[(os.path.split(name)[0], fy_of(name))].append(score(rec))

# Every PDF on disk, by company and the year in its name (rejected folder excluded).
on_disk = collections.defaultdict(list)
for p in glob.glob(os.path.join(ROOT, "*", "*.pdf")):
    d = os.path.basename(os.path.dirname(p))
    if d.startswith("_"):
        continue
    rel = d + "\\" + os.path.basename(p)
    y = fy_of(rel)
    if y:
        on_disk[(d, y)].append(rel)


def unusable_reason(files):
    """Why none of the files on disk for this company-year counts."""
    reasons = []
    for f in files:
        if f in wrong:
            reasons.append("another company's report")
            continue
        e, yc = ex.get(f), YC.get(f) or {}
        if right_year(f):
            reasons.append("right year, not yet reviewed" if f not in acc else "right year, reading failed")
        elif yc.get("why"):
            reasons.append(yc["why"])
        elif e and e.get("fy") and e.get("fy") != fy_of(f):
            reasons.append(f"statements inside are FY{e['fy']}")
        elif e and not e.get("statement_pages"):
            reasons.append("no statements located (scanned, extract or notice)")
        elif not e:
            reasons.append("not yet read")
        else:
            reasons.append("year not confirmed")
    return "; ".join(sorted(set(reasons)))


rows, tot, complete = [], 0, 0
for c in fs:
    sym = c["name"]
    if sym in FIN:
        continue
    stopped = (c.get("status") or "").startswith("stopped")
    for y in c["years"]:
        tot += 1
        rs = by.get((sym, y), [])
        if any(r[0] and r[1] for r in rs):
            complete += 1
            continue
        if rs:
            best = min(rs, key=lambda r: len(r[2]))
            cause, detail, route = "read_incomplete", "missing: " + ", ".join(best[2]), "reader_or_validation"
        else:
            files = on_disk.get((sym, y), [])
            cause = "file_unusable" if files else "no_file"
            detail = unusable_reason(files) if files else ""
            if sym in HAND_ONLY:
                route = "hand_only_site"
                detail = (detail + "; " if detail else "") + HAND_ONLY[sym]
            elif not stopped and (missing_meta.get(sym) or {}).get("known_site"):
                route = "company_site"
            else:
                route = "bse_by_hand"
        prio = "P1" if stopped else ("P2" if y <= 2015 else "P3")
        rows.append({"priority": prio, "symbol": sym, "fy": y, "cause": cause, "route": route,
                     "status": c.get("status"), "isins": " ".join(c.get("isins") or []),
                     "known_site": (missing_meta.get(sym) or {}).get("known_site") or "",
                     "detail": detail})

rows.sort(key=lambda r: (r["priority"], r["cause"] != "read_incomplete", r["symbol"], r["fy"]))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

need = -(-int(round(0.80 * tot * 1000)) // 1000)   # ceiling of 80%
print(f"eligible {tot}; complete {complete} ({complete/tot:.1%}); gate needs {need}; short by {need-complete}")
cc = collections.Counter(r["cause"] for r in rows)
print("by cause:", dict(cc))
print("by route:", dict(collections.Counter((r["cause"], r["route"]) for r in rows)))
print("by priority:", dict(collections.Counter(r["priority"] for r in rows)))
print("no_file by priority:", dict(collections.Counter(r["priority"] for r in rows if r["cause"] == "no_file")))
print("unusable reasons:", collections.Counter(r["detail"].split(";")[0] for r in rows
                                                 if r["cause"] == "file_unusable").most_common(8))
top = collections.Counter(r["symbol"] for r in rows if r["cause"] != "read_incomplete").most_common(15)
print("companies with most years to download:", top)
print("wrote", OUT, len(rows), "rows")
