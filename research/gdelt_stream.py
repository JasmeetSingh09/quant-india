"""
gdelt_stream.py: collect India-related GDELT GKG rows, one day at a time.

Stage 1 of the sentiment test (research/, never deployed). For every
15-minute GKG 2.1 file it downloads the zip into memory, keeps only the rows
defined below, and discards the rest. Raw files are never written to disk.

A row is kept if ANY of these holds (fixed before looking at any result):
  - its source domain is in INDIAN_OUTLETS, or ends in ".in";
  - its V1 locations name India (FIPS country code "IN").

Kept per row: GDELT DATE (the 15-minute batch the article was processed in,
so the headline was public by then), source, URL, PAGE_TITLE from Extras,
V2Organizations, V2Tone. One gzipped TSV per day, plus a JSON manifest with
counts, missing files and titles seen, so coverage is measured, not assumed.

Resumable: a day whose manifest exists is skipped. Missing or unreadable
files are recorded in that day's manifest, never silently dropped.

    python research/gdelt_stream.py OUT_DIR 2019-09-01 2026-09-16 [workers]

Data: The GDELT Project, https://www.gdeltproject.org (free for any use,
citation required).
"""

import datetime as dt
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

BASE = "http://data.gdeltproject.org/gdeltv2/{ts}.gkg.csv.zip"

INDIAN_OUTLETS = {
    "livemint.com", "business-standard.com", "economictimes.indiatimes.com",
    "moneycontrol.com", "thehindubusinessline.com", "financialexpress.com",
    "businesstoday.in", "cnbctv18.com", "zeebiz.com", "ndtvprofit.com",
    "fortuneindia.com", "outlookbusiness.com", "timesofindia.indiatimes.com",
    "hindustantimes.com", "thehindu.com", "indianexpress.com", "news18.com",
    "deccanherald.com", "tribuneindia.com", "thestatesman.com",
    "telegraphindia.com", "firstpost.com", "indiatoday.in", "ndtv.com",
    "moneylife.in", "newindianexpress.com", "dnaindia.com",
    "freepressjournal.in", "thehansindia.com", "outlookindia.com", "scroll.in",
    "theprint.in", "business-standard.in", "economictimes.com",
    "devdiscourse.com", "bizzbuzz.news", "siliconindia.com",
}

_TITLE = re.compile(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", re.S)
_CLEAN = str.maketrans({"\t": " ", "\n": " ", "\r": " "})


def _keep(src, locations):
    if src in INDIAN_OUTLETS or src.endswith(".in"):
        return True
    for loc in locations.split(";"):
        parts = loc.split("#")
        if len(parts) > 2 and parts[2] == "IN":
            return True
    return False


def fetch(ts, tries=4):
    """(ts, bytes | None, error | None). 404 is final; other errors retry."""
    url = BASE.format(ts=ts)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return ts, r.read(), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ts, None, "404"
            err = f"HTTP {e.code}"
        except Exception as e:  # network blips
            err = type(e).__name__
        time.sleep(5 * (attempt + 1))
    return ts, None, err


def parse(blob):
    """Kept rows, total rows, kept rows with a title."""
    kept, total, titled = [], 0, 0
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        with z.open(z.namelist()[0]) as f:
            for line in io.TextIOWrapper(f, encoding="utf-8", errors="replace"):
                p = line.rstrip("\n").split("\t")
                if len(p) < 27:
                    continue
                total += 1
                if not _keep(p[3], p[9]):
                    continue
                m = _TITLE.search(p[26])
                title = m.group(1).translate(_CLEAN).strip() if m else ""
                titled += bool(title)
                kept.append("\t".join((p[1], p[3], p[4].translate(_CLEAN), title,
                                       p[14].translate(_CLEAN), p[15])))
    return kept, total, titled


def run_day(out_dir, day, workers):
    stem = os.path.join(out_dir, day.strftime("%Y%m%d"))
    if os.path.exists(stem + ".json"):
        return None
    stamps = [(day + dt.timedelta(minutes=15 * k)).strftime("%Y%m%d%H%M%S")
              for k in range(96)]
    rows, man = [], {"day": day.strftime("%Y-%m-%d"), "files_expected": 96,
                     "files_read": 0, "missing": {}, "rows_total": 0,
                     "rows_kept": 0, "rows_kept_with_title": 0}
    with ThreadPoolExecutor(workers) as ex:
        for ts, blob, err in ex.map(fetch, stamps):
            if blob is None:
                man["missing"][ts] = err
                continue
            try:
                kept, total, titled = parse(blob)
            except Exception as e:  # corrupt zip, CRC failure
                man["missing"][ts] = f"unreadable: {type(e).__name__}"
                continue
            man["files_read"] += 1
            man["rows_total"] += total
            man["rows_kept"] += len(kept)
            man["rows_kept_with_title"] += titled
            rows.extend(kept)
    with gzip.open(stem + ".tsv.gz.part", "wt", encoding="utf-8") as g:
        g.write("date\tsource\turl\ttitle\torganizations\ttone\n")
        g.writelines(r + "\n" for r in rows)
    os.replace(stem + ".tsv.gz.part", stem + ".tsv.gz")
    with open(stem + ".json", "w") as f:       # written last: marks the day done
        json.dump(man, f)
    return man


def main():
    out_dir, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    os.makedirs(out_dir, exist_ok=True)
    day = dt.datetime.strptime(start, "%Y-%m-%d")
    last = dt.datetime.strptime(end, "%Y-%m-%d")
    while day <= last:
        t0 = time.time()
        man = run_day(out_dir, day, workers)
        if man:
            print(f"{man['day']} files {man['files_read']}/96 kept {man['rows_kept']} "
                  f"titled {man['rows_kept_with_title']} of {man['rows_total']} "
                  f"missing {len(man['missing'])} in {time.time() - t0:.0f}s", flush=True)
        day += dt.timedelta(days=1)


if __name__ == "__main__":
    main()
