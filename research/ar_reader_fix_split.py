"""
ar_reader_fix_split.py — the development / held-out split for the 2026-10-17 reader fixes.

Written and run BEFORE any individual failing case is examined (plan:
docs/AR_READER_FIX_PLAN_2026-10-17.md). Two populations, from the gap list:

  FACE  read company-years whose only route to acceptance is blocked by the
        face-value check (cause read_incomplete, "face_check" among the misses)
  OCR   company-years whose file on disk has no statements located (scanned
        pages, extracts or notices)

Split BY COMPANY (a company's layout repeats across years, so splitting by
company-year would leak), seed 20261017: companies are shuffled and alternately
assigned. Development cases may be read and tuned on; held-out cases are not
opened until the fixes are frozen, and are scored once.

    python research/ar_reader_fix_split.py <annual_reports_dir> <gap_list.csv> <out.json>
"""
import csv
import glob
import hashlib
import json
import os
import random
import sys

ROOT, GAP, OUT = sys.argv[1:4]
SEED = 20261017
rows = list(csv.DictReader(open(GAP, encoding="utf-8")))
pop = {
    "FACE": [r for r in rows if r["cause"] == "read_incomplete" and "face_check" in r["detail"]],
    "OCR": [r for r in rows if r["cause"] == "file_unusable" and r["detail"].startswith("no statements located")],
}
out = {"seed": SEED, "rule": "by company, shuffled, alternate assignment", "populations": {}}
for name, rs in pop.items():
    companies = sorted({r["symbol"] for r in rs})
    random.Random(f"{SEED}-{name}").shuffle(companies)
    dev = sorted(companies[0::2])
    hold = sorted(companies[1::2])
    def cases(group):
        return [{"symbol": r["symbol"], "fy": int(r["fy"]),
                 "files": sorted(os.path.relpath(p, ROOT).replace("/", "\\") for p in
                                 glob.glob(os.path.join(ROOT, r["symbol"], f"*FY{r['fy']}*.pdf")))}
                for r in sorted(rs, key=lambda r: (r["symbol"], int(r["fy"]))) if r["symbol"] in group]
    out["populations"][name] = {
        "company_years": len(rs), "companies": len(companies),
        "development": {"companies": dev, "cases": cases(set(dev))},
        "held_out": {"companies": hold, "cases": cases(set(hold))},
    }
blob = json.dumps(out, sort_keys=True).encode()
out["sha256_16"] = hashlib.sha256(blob).hexdigest()[:16]
json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
for name, p in out["populations"].items():
    print(f"{name}: {p['company_years']} company-years, {p['companies']} companies -> "
          f"development {len(p['development']['cases'])} ({len(p['development']['companies'])} co), "
          f"held-out {len(p['held_out']['cases'])} ({len(p['held_out']['companies'])} co)")
print("sha256_16", out["sha256_16"])
