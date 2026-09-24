"""
ar_company_sites.py: fetch annual reports from each company's OWN website only.

Owner approval 2026-09-25: "yes to 1 AND ONLY FROM THEIR OWN WEBSITES".
Never contacts bseindia.com, nseindia.com, the Internet Archive or any third
party; only the company's official site as Yahoo lists it, and only paths its
robots.txt allows.

For each company in full_sample.json:
  1. its website, from Yahoo (.NS listing);
  2. a short, polite crawl of that site (same domain, at most MAX_PAGES pages,
     DELAY seconds between requests) for pages about investors/annual reports;
  3. PDF links whose link text or address names one of the needed years and
     looks like an annual report (not a notice, BRR, subsidiary accounts...);
  4. download, then keep only if it is a complete PDF whose own text names
     that financial year most often. Everything else is logged, not kept.

Resumable: a manifest line per company; finished companies are skipped.

    python research/ar_company_sites.py <annual_reports_dir> [limit]
"""

import collections
import io
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.robotparser

import requests

logging.disable(logging.CRITICAL)

UA = "Mozilla/5.0 (compatible; QuantIndia-student-research/1.0; annual reports, polite crawl)"
DELAY = 3.0
MAX_PAGES = 25
MAX_BYTES = 90 * 1024 * 1024
BLOCKED_HOSTS = ("bseindia.com", "nseindia.com", "archive.org", "screener.in")
NAV_WORDS = re.compile(r"invest|annual|financ|sharehold|report|disclosure|stakeholder", re.I)
EXCLUDE = re.compile(r"notice|brr|business[\s_-]*responsib|sustainab|esg|subsidiar|form[\s_-]*(aoc|mgt|20-?f)|"
                     r"agm|postal|ballot|transcript|presentation|quarter|q[1-4]|press|result|voting|"
                     r"dividend|policy|scrutinizer|integrated[\s_-]*report[\s_-]*summary|abridged", re.I)
ANNUAL = re.compile(r"annual|\bar\b|ar[-_ ]?\d{2}", re.I)

sess = requests.Session()
sess.headers["User-Agent"] = UA
_robots = {}
_last = [0.0]


def polite_get(url, **kw):
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(b in host for b in BLOCKED_HOSTS):
        raise PermissionError(f"blocked host {host}")
    wait = DELAY - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    return sess.get(url, timeout=40, **kw)


def allowed(url):
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = polite_get(base + "/robots.txt")
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _robots[base] = rp
    return _robots[base].can_fetch(UA, url)


def site_of(symbol):
    import yfinance as yf
    try:
        info = yf.Ticker(symbol + ".NS").info or {}
    except Exception:
        info = {}
    return info.get("website"), info.get("longName") or info.get("shortName")


def same_site(a, b):
    ha = urllib.parse.urlparse(a).netloc.lower().removeprefix("www.")
    hb = urllib.parse.urlparse(b).netloc.lower().removeprefix("www.")
    return ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha)


LINK = re.compile(r"<a\b[^>]*href\s*=\s*['\"]([^'\"#]+)['\"][^>]*>(.*?)</a>", re.I | re.S)


def links(html, base):
    for href, text in LINK.findall(html):
        t = re.sub(r"<[^>]+>", " ", text)
        t = re.sub(r"\s+", " ", t).strip()
        yield urllib.parse.urljoin(base, href.strip()), t


def year_tokens(y):
    a, b = str(y - 1), str(y)
    return [f"{a}-{b[2:]}", f"{a}-{b}", f"{a}–{b[2:]}", f"{a}_{b[2:]}", f"{a}{b[2:]}",
            f"fy{b[2:]}", f"fy {b}", f"fy{b}", f"ar{b[2:]}", f"ar-{b[2:]}", f"ar_{b[2:]}", f"{a}_{b}"]


def match_year(text, years):
    t = text.lower()
    hits = [y for y in years if any(tok in t for tok in year_tokens(y))]
    return hits[0] if len(hits) == 1 else None


def _norm(t):
    return re.sub(r"[^a-z0-9 ]+", " ", (t or "").lower()).split()


def identity_ok(text, long_name):
    """Is this the company's own English annual report?

    Found on coalindia.in in the first trial (2026-09-25): the same site hosts
    Hindi editions and every subsidiary's report, and a year check alone kept
    8 wrong files out of 10. So the report must be in English and must name
    the company itself, repeatedly, and must not present itself as another
    company's subsidiary.
    """
    words = _norm(text)
    if words.count("the") < 40:                      # Hindi or scanned
        return False, "not English text"
    name = [w for w in _norm(long_name) if w not in ("limited", "ltd", "the", "of", "and")]
    if not name:
        return False, "no company name"
    joined = " ".join(words)
    hits = joined.count(" ".join(name))
    if hits < 3:
        return False, f"company name found {hits} times"
    if re.search(r"(a\s+)?(wholly\s+owned\s+)?subsidiary\s+of", text[:6000], re.I) and hits < 8:
        return False, "presents itself as a subsidiary"
    return True, ""


def pdf_year(blob):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        n = len(pdf.pages)
        text = " ".join((pdf.pages[i].extract_text() or "") for i in range(min(n, 15)))
    pdf_year.last_text = text
    c = collections.Counter()
    for a, b in re.findall(r"\b(20\d\d)\s*[-–]\s*(?:20)?(\d\d)\b", text):
        if int(b) == (int(a) + 1) % 100:
            c[int(a) + 1] += 1
    for y in re.findall(r"31(?:st)?\s+march,?\s+(20\d\d)|march\s+31,?\s+(20\d\d)", text, re.I):
        c[int(y[0] or y[1])] += 1
    return (c.most_common(1)[0][0] if c else None), n


def crawl(company, root_dir):
    sym, years = company["name"], company["years"]
    rec = {"symbol": sym, "needed": years, "got": {}, "log": []}
    site, longname = site_of(sym)
    rec["website"], rec["long_name"] = site, longname
    if not site:
        rec["log"].append("no website on Yahoo")
        return rec
    queue, seen, cands = [site], set(), {}
    while queue and len(seen) < MAX_PAGES:
        url = queue.pop(0)
        if url in seen or not allowed(url):
            continue
        seen.add(url)
        try:
            r = polite_get(url)
        except Exception as e:
            rec["log"].append(f"{url[:80]}: {type(e).__name__}")
            continue
        if "html" not in r.headers.get("content-type", ""):
            continue
        for href, text in links(r.text, r.url):
            if not same_site(href, site) or not href.startswith("http"):
                continue
            blob = f"{text} {urllib.parse.unquote(href)}"
            if ".pdf" in href.lower():
                if EXCLUDE.search(blob) or not ANNUAL.search(blob):
                    continue
                y = match_year(blob, years)
                if y and y not in rec["got"]:
                    cands.setdefault(y, []).append(href)
            elif NAV_WORDS.search(blob) and href not in seen and len(queue) < 200:
                queue.append(href)
    os.makedirs(os.path.join(root_dir, sym), exist_ok=True)
    for y in sorted(cands):
        for href in cands[y][:6]:
            if not allowed(href):
                continue
            try:
                r = polite_get(href, stream=True)
                blob = r.raw.read(MAX_BYTES + 1, decode_content=True)
            except Exception as e:
                rec["log"].append(f"FY{y} {type(e).__name__}")
                continue
            if len(blob) > MAX_BYTES or not blob.startswith(b"%PDF") or b"%%EOF" not in blob[-4096:]:
                rec["log"].append(f"FY{y} not a complete PDF ({len(blob)} bytes)")
                continue
            try:
                found, pages = pdf_year(blob)
            except Exception as e:
                rec["log"].append(f"FY{y} unreadable {type(e).__name__}")
                continue
            if found != y or pages < 80:
                rec["log"].append(f"FY{y} rejected: text says {found}, {pages} pages ({href[-60:]})")
                continue
            ok, why = identity_ok(pdf_year.last_text, longname or sym)
            if not ok:
                rec["log"].append(f"FY{y} rejected: {why} ({href[-60:]})")
                continue
            path = os.path.join(root_dir, sym, f"{sym}_FY{y}_companysite.pdf")
            open(path, "wb").write(blob)
            rec["got"][y] = {"url": href, "bytes": len(blob), "pages": pages}
            break
    return rec


def main():
    root = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    sample = json.load(open(os.path.join(root, "full_sample.json")))
    man_path = os.path.join(root, "company_site_manifest.jsonl")
    done = set()
    if os.path.exists(man_path):
        done = {json.loads(l)["symbol"] for l in open(man_path) if l.strip()}
    todo = [c for c in sample if c["name"] not in done][:limit]
    for c in todo:
        t0 = time.time()
        try:
            rec = crawl(c, root)
        except Exception as e:
            rec = {"symbol": c["name"], "needed": c["years"], "got": {}, "log": [f"crashed {type(e).__name__}: {e}"]}
        rec["seconds"] = round(time.time() - t0)
        with open(man_path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"{c['name']:14} got {len(rec['got'])}/{len(c['years'])} "
              f"site {rec.get('website')} {rec['seconds']}s", flush=True)


if __name__ == "__main__":
    main()
