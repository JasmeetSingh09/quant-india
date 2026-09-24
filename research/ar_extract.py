"""
ar_extract.py (v2): pull standalone headline figures from Indian annual reports,
and check them against each other so a wrong figure is caught, not trusted.

Figures, current and previous year, converted to Rs crore:
  revenue, profit_for_year, eps_basic (Rs per share), share_capital,
  total_equity, total_assets, borrowings, operating_cash_flow

Checks (all recorded per report):
  balance     the balance sheet's closing total appears twice: total assets
              and total equity and liabilities are the same number
  face_value  profit / EPS gives the share count; share capital / share count
              must be a real face value (Rs 1, 2, 5 or 10). One test that
              confirms profit, EPS, share capital AND the unit together.
  equity_lt_assets, assets_positive

v1 (2026-09-25) found 5-8 of 9 figures in most reports but read some wrong
lines (Tata Steel FY2016 "total assets" was a micro-enterprise dues line).
A figure is never filled in: not found is None.

    python research/ar_extract.py <reports_dir> <out.json> [--cache DIR]
"""

import glob
import json
import logging
import os
import pickle
import re
import sys

logging.disable(logging.CRITICAL)

NUM = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?")
FACES = (1, 2, 5, 10)
TO_CRORE = {"crore": 1.0, "lakh": 0.01, "million": 0.1, "billion": 100.0, "thousand": 1e-4}

TITLE = {
    "bs": re.compile(r"\bbalance\s*sheet\b", re.I),
    "pl": re.compile(r"(statement\s+of\s+profit\s+(and|&)\s+loss|profit\s+(and|&)\s+loss\s+(account|statement))", re.I),
    "cf": re.compile(r"(cash\s*flow\s+statement|statement\s+of\s+cash\s*flows?)", re.I),
}
NEED = {
    "bs": re.compile(r"assets", re.I),
    "pl": re.compile(r"(earnings?\s+per|\beps\b|per\s+equity\s+share)", re.I),
    "cf": re.compile(r"operating\s+activities", re.I),
}
SKIP_HEAD = re.compile(r"consolidated|auditor|report\s+on|notes?\s+(to|forming)|significant\s+accounting|"
                       r"we\s+have\s+audited|directors|annexure|highlights|ten\s*year|financial\s+summary|"
                       r"key\s+(figures|indicators)|at\s+a\s+glance", re.I)


def num(tok):
    t = tok.replace(",", "")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


ENUM = re.compile(r"^\s*[\(\[]?(?:[0-9]{1,2}|[ivxIVX]{1,4}|[a-hA-H])[\)\]\.]\s+")


def values(line):
    """Numbers on a line, after removing a leading list number like (1) or (ii)."""
    line = ENUM.sub("", line)
    vals = [num(t) for t in NUM.findall(line)]
    vals = [v for v in vals if v is not None]
    return vals


def clean(line):
    s = line.replace("`", " ").replace("₹", " ").replace("Rs.", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def unit_of(text):
    t = text.lower()
    for u, pat in (("crore", r"crore|\bcr\b"), ("lakh", r"lakh|lacs|\blac\b"),
                   ("million", r"million|\bmn\b"), ("billion", r"billion"), ("thousand", r"thousand|'000")):
        if re.search(pat, t):
            return u
    return None


def find_statements(pages):
    """First balance sheet followed within a few pages by the P&L and cash flow.

    Highlights and summary pages carry the same titles; the real statements
    come as a block (DHFL FY2016's summary page 46, HUL FY2018's page 9).
    """
    cand = {"bs": [], "pl": [], "cf": []}
    for i, text in enumerate(pages):
        head = "\n".join(text.splitlines()[:12])
        if SKIP_HEAD.search(head) or len(re.findall(r"\d[\d,]{3,}", text)) < 15:
            continue
        for key in cand:
            if TITLE[key].search(head) and NEED[key].search(text):
                cand[key].append(i)
    for need_cf in (True, False):
        for b in cand["bs"]:
            pl = [p for p in cand["pl"] if abs(p - b) <= 4]
            cf = [c for c in cand["cf"] if 0 <= c - b <= 8]
            if pl and (cf or not need_cf):
                out = {"bs": b, "pl": pl[0]}
                if cf:
                    out["cf"] = cf[0]
                return out
    return {k: v[0] for k, v in cand.items() if v}


NCOLS = [2]


def columns_of(text):
    """2 value columns normally; 3 in a transition year that also shows an opening date."""
    head = " ".join(text.splitlines()[:25])
    dates = set(re.findall(r"(?:31(?:st)?\s+march|march\s+31|1(?:st)?\s+april|april\s+1)[,\s]+(20\d\d)", head, re.I))
    return 3 if len(dates) >= 3 else 2


def line_value(lines, idx):
    """(current, previous) from a matching line, or the next line if it holds only numbers."""
    n = NCOLS[0]
    v = values(lines[idx])
    if len(v) < 2 and idx + 1 < len(lines) and not re.search(r"[A-Za-z]{3,}", lines[idx + 1]):
        v = v + values(lines[idx + 1])
    if len(v) >= n:
        return v[-n], v[-n + 1]
    if len(v) >= 2:
        return v[-2], v[-1]
    if len(v) == 1:
        return v[-1], None
    return None, None


def first_match(page_texts, patterns, exclude=None, prefer=None):
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for pno, text in page_texts:
            lines = [clean(l) for l in text.splitlines()]
            for i, l in enumerate(lines):
                head = re.sub(r"^[\(\)\[\]ivxIVX\d\.\s\-–•]{0,8}(?=[A-Za-z])", "", l)
                if not rx.search(head) or (exclude and re.search(exclude, head, re.I)):
                    continue
                cur, prev = line_value(lines, i)
                if cur is None:
                    continue
                return {"current": cur, "previous": prev, "page": pno + 1, "line": l[:150]}
    return None


def balancing_total(text):
    """The balance sheet total: a 'total' line whose value appears twice."""
    rows = []
    for l in (clean(x) for x in text.splitlines()):
        if re.match(r"^(total|t o t a l)\b", l, re.I) and not re.search(r"current|non.current|other|"
                                                                       r"borrow|financial|provision", l, re.I):
            v = values(l)
            n = NCOLS[0]
            if len(v) >= n:
                rows.append((v[-n], v[-n + 1], l))
    counts = {}
    for c, p, l in rows:
        counts.setdefault((round(c, 2), round(p, 2)), []).append(l)
    twice = [k for k, ls in counts.items() if len(ls) >= 2 and k[0] > 0]
    if not twice:
        return None
    c, p = max(twice)
    return {"current": c, "previous": p, "line": counts[(c, p)][0][:150], "balanced": True}


def extract_pages(pages, name):
    out = {"file": name, "pages": len(pages)}
    st = find_statements(pages)
    out["statement_pages"] = {k: v + 1 for k, v in st.items()}
    if not st:
        out["error"] = "no standalone statements found"
        return out
    span = lambda k, n=2: [(i, pages[i]) for i in range(st[k], min(st[k] + n, len(pages)))] if k in st else []
    unit = unit_of("\n".join(pages[i][:1500] for i in st.values()))
    out["unit"] = unit
    f = {}
    bs, pl, cf = span("bs"), span("pl"), span("cf", 3)
    if bs:
        NCOLS[0] = columns_of(bs[0][1])
        tb = balancing_total(bs[0][1]) or (balancing_total(bs[1][1]) if len(bs) > 1 else None)
        f["total_assets"] = tb or first_match(bs, [r"^total\s+assets\b"])
        f["share_capital"] = first_match(bs, [r"^equity\s+share\s+capital", r"^share\s+capital"])
        f["total_equity"] = first_match(bs, [r"^total\s+equity(?!\s+and)", r"^total\s+shareholders.?\s*funds",
                                             r"^shareholders.?\s*funds"])
        res = first_match(bs, [r"^other\s+equity", r"^reserves\s+(and|&)\s+surplus"])
        if not f["total_equity"] and f["share_capital"] and res:
            sc = f["share_capital"]
            f["total_equity"] = {"current": sc["current"] + res["current"],
                                 "previous": (sc["previous"] + res["previous"]) if (sc["previous"] is not None and res["previous"] is not None) else None,
                                 "page": res["page"], "line": "share capital + " + res["line"][:80],
                                 "derived": True}
        # Borrowings: every borrowings line on the face (non-current and current).
        tot_c = tot_p = 0.0
        hits = []
        for pno, text in bs:
            lines = [clean(l) for l in text.splitlines()]
            for i, l in enumerate(lines):
                head = re.sub(r"^[\(\)\[\]ivxIVX\d\.\s\-–•]{0,8}(?=[A-Za-z])", "", l)
                if re.match(r"^(long.term\s+|short.term\s+|non.current\s+|current\s+)?borrowings\b", head, re.I):
                    c, p = line_value(lines, i)
                    if c is not None and l[:60] not in hits:
                        tot_c += c
                        tot_p += p or 0.0
                        hits.append(l[:60])
        f["borrowings"] = {"current": tot_c, "previous": tot_p, "line": " + ".join(hits)} if hits else None
    if pl:
        NCOLS[0] = columns_of(pl[0][1])
        f["revenue"] = first_match(pl, [r"^revenue\s+from\s+operations", r"^income\s+from\s+operations",
                                        r"^net\s+sales", r"^total\s+revenue", r"^total\s+income", r"^interest\s+earned"],
                                   exclude=r"other\s+income")
        f["profit_for_year"] = first_match(pl, [
            r"^(net\s+)?(\(loss\)\s*/\s*)?profit\s*(/\s*\(loss\))?\s+for\s+the\s+(year|period)(?!.*before)",
            r"^(net\s+)?(profit|loss)\s+for\s+the\s+(year|period)(?!.*before)",
            r"^(net\s+)?[\(\)/\s]*(profit|loss)[\(\)/\sa-z]{0,20}for\s+the\s+(year|period)",
            r"^(net\s+)?profit\s*(/\s*\(loss\))?\s+after\s+tax", r"^net\s+profit\b(?!.*before)"],
            exclude=r"before|comprehensive|attributable|discontinued")
        f["eps_basic"] = first_match(pl, [r"^basic\b", r"basic\s*(and|&|/)\s*diluted", r"^\W*\(?[a-z]\)?\s*basic"])
    if cf:
        NCOLS[0] = columns_of(cf[0][1])
        f["operating_cash_flow"] = first_match(cf, [
            r"^net\s+cash\s+(flow\s+)?(generated\s+|from\s+|\(used\s+in\)\s*/?\s*|used\s+in\s*/?\s*)*"
            r"(from|in|by)?\s*(/\s*\(used\s+in\)\s*)?operating\s+activities",
            r"net\s+cash.{0,40}operating\s+activities"])
    for k in ("total_assets", "share_capital", "total_equity", "borrowings", "revenue",
              "profit_for_year", "eps_basic", "operating_cash_flow"):
        f.setdefault(k, None)
    # Convert to crore (EPS stays in rupees per share).
    k_cr = TO_CRORE.get(unit)
    for k, v in f.items():
        if v and k != "eps_basic":
            v["current_crore"] = None if k_cr is None else round(v["current"] * k_cr, 4)
            v["previous_crore"] = None if (k_cr is None or v["previous"] is None) else round(v["previous"] * k_cr, 4)
    out["figures"] = f

    chk = {}
    ta, te = f["total_assets"], f["total_equity"]
    chk["balance"] = bool(ta and ta.get("balanced"))
    chk["assets_positive"] = bool(ta and ta["current"] > 0)
    if ta and te:
        chk["equity_lt_assets"] = te["current"] < ta["current"]
    pr, eps, sc = f["profit_for_year"], f["eps_basic"], f["share_capital"]
    if pr and eps and sc and k_cr and eps["current"] and pr["current"] and sc["current"]:
        # EPS uses the weighted average share count, so when shares were issued
        # during the year the average of opening and closing capital is fairer.
        shares = pr["current"] * k_cr * 1e7 / eps["current"]
        caps = [sc["current"]]
        if sc["previous"]:
            caps.append((sc["current"] + sc["previous"]) / 2)
        faces = [c * k_cr * 1e7 / shares for c in caps] if shares else []
        tol = 0.04 + 0.005 / abs(eps["current"])        # EPS is printed to 2 decimals
        out["implied_face_value"] = round(faces[0], 3) if faces else None
        chk["face_value"] = any(abs(fc - fv) / fv < tol for fc in faces for fv in FACES)
    out["checks"] = chk
    out["found"] = sum(1 for v in f.values() if v)
    out["verified"] = chk.get("balance", False) and chk.get("face_value", False)
    return out


def load_pages(path, cache):
    if cache:
        key = os.path.relpath(path).replace("\\", "_").replace("/", "_").replace(" ", "_")[:-4]
        pk = os.path.join(cache, key + ".pkl")
        if os.path.exists(pk):
            return pickle.load(open(pk, "rb"))["pages"]
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return [(p.extract_text() or "") for p in pdf.pages]


def main():
    root, out_path = sys.argv[1], sys.argv[2]
    cache = sys.argv[sys.argv.index("--cache") + 1] if "--cache" in sys.argv else None
    os.chdir(root)
    results = []
    for path in sorted(glob.glob(os.path.join("*", "*.pdf"))):
        try:
            r = extract_pages(load_pages(path, cache), path)
        except Exception as e:
            r = {"file": path, "error": f"{type(e).__name__}: {e}"}
        results.append(r)
        c = r.get("checks", {})
        print(f"{path[:55]:55} found {r.get('found', 0)}/8 unit {str(r.get('unit')):7} "
              f"balance {'Y' if c.get('balance') else '-'} face {'Y' if c.get('face_value') else '-'} "
              f"{r.get('implied_face_value', '')} {r.get('error', '')}", flush=True)
    json.dump(results, open(out_path, "w"), indent=1)
    ok = [r for r in results if r.get("figures")]
    print(f"\n{len(ok)} reports with statements; verified (balance AND face value): "
          f"{sum(1 for r in ok if r.get('verified'))}")


if __name__ == "__main__":
    main()
