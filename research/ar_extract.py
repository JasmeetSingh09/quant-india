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

Pilot results (27 readable reports, 10 companies, FY2011-FY2019):
  v1 12 verified, v4 16, v8 26. The one failure is Infosys FY2012, an
  abridged report with an uncaptioned profit line (enter by hand).
  These rules were tuned on the same 27 reports, so 26/27 is in-sample;
  the first batch of new reports must be scored before any tuning on it.
  borrowings is NOT covered by either check and reads low for lenders and
  for old layouts ("Long Term Liabilities", current maturities of debt in
  "Other current liabilities"); leverage should use total assets minus
  total equity, which the balance check does cover.

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
    # "Statements of Profit and Loss" (TCS FY2018) is plural.
    "pl": re.compile(r"(statements?\s+of\s+profit\s+(and|&)\s+loss|profit\s+(and|&)\s+loss\s+(account|statement))", re.I),
    "cf": re.compile(r"(cash\s*flow\s+statement|statement\s+of\s+cash\s*flows?)", re.I),
}
NEED = {
    "bs": re.compile(r"assets", re.I),
    "pl": re.compile(r"(earnings?[\s/()a-z]{0,15}\s+per\s+(equity\s+)?share|\beps\b|per\s+equity\s+share)", re.I),
    "cf": re.compile(r"operating\s+activities", re.I),
}
SKIP_HEAD = re.compile(r"consolidated|auditor|report\s+on|notes?\s+(to|forming)|significant\s+accounting|"
                       r"we\s+have\s+audited|directors|annexure|highlights|ten\s*year|financial\s+summary|"
                       r"key\s+(figures|indicators)|at\s+a\s+glance", re.I)
# A running navigation banner names every section of the report on every page:
# "Company Overview ... Standalone Accounts Consolidated Accounts" (M&M FY2017).
# Such a line is not a heading, so it must not make a standalone page look consolidated.
NAV_BANNER = re.compile(r"standalone.{0,40}consolidated|consolidated.{0,40}standalone|"
                        r"(overview|report|analysis|governance|accounts)(\s+\S+){0,3}\s+"
                        r"(overview|report|analysis|governance|accounts)\s+(overview|report|analysis|governance|accounts)",
                        re.I)


def head_of(text, n=12):
    """The first n lines without navigation-banner lines."""
    return "\n".join(l for l in text.splitlines()[:n] if not NAV_BANNER.search(l))


# Font-encoded text. pdfplumber returns "(cid:N)" for glyphs whose font has no
# Unicode map. Two shapes occur:
#   ligatures only: "Pro(cid:191) t", "bene(cid:191) ts" (DLF FY2013) -- one code
#     stands for "fi" or "fl";
#   the whole page: every character is (cid:N), N = ord(c) + k for one shift k
#     per font (GAIL FY2012 k = 0, GAIL FY2021 k = 29).
CID = re.compile(r"\(cid:(\d+)\)")
CHECK_WORDS = ("profit", "benefit", "financial", "fixed", "flow", "assets", "total", "share",
               "capital", "loss", "statement", "balance", "sheet", "revenue", "year", "income")


def decode_cids(text):
    """Decode (cid:N) codes when a single, checkable rule explains them; else leave them."""
    if "(cid:" not in text:
        return text
    codes = CID.findall(text)
    if len(codes) > 0.3 * max(1, len(re.sub(r"\(cid:\d+\)", "", text))):
        # Whole-page encoding: pick the shift that turns the page into English.
        best, best_hits = None, 0
        for k in range(-40, 60):
            try:
                dec = CID.sub(lambda m: chr(int(m.group(1)) + k) if 9 < int(m.group(1)) + k < 0x2000 else " ", text)
            except ValueError:
                continue
            hits = sum(dec.lower().count(w) for w in CHECK_WORDS)
            if hits > best_hits:
                best, best_hits = dec, hits
        return best if best_hits >= 5 else text
    # Ligature codes between letters: "Pro(cid:191) t" -> "Profit". Each code is
    # mapped to whichever of fi/fl/ff makes more of the check words appear.
    out = text
    for code in set(codes):
        pat = re.compile(r"\(cid:" + code + r"\)\s?")
        best, best_hits = None, 0
        for lig in ("fi", "fl", "ff", "ffi"):
            dec = pat.sub(lig, out)
            hits = sum(dec.lower().count(w) for w in CHECK_WORDS)
            if hits > best_hits:
                best, best_hits = dec, hits
        base = sum(out.lower().count(w) for w in CHECK_WORDS)
        if best is not None and best_hits > base:
            out = best
    return out


def num(tok):
    t = tok.replace(",", "")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


ENUM = re.compile(r"^\s*(?:[\(\[]?(?:[0-9]{1,2}|[ivxIVX]{1,4}|[a-hA-H])[\)\]\.]|[0-9]{1,2}(?=\s+[A-Za-z])|"
                  r"[IVX]{1,4}(?=\s+[A-Z]))\s+")
FORMULA = re.compile(r"\((?:\s*[IVXivx\d]+\s*[-+–/]\s*)+[IVXivx\d]+\s*\)")
# "of face value of Rs 5 each", "par value 5/- each", "Nominal value of share Rs 2/-":
# the 5 or 2 is not a figure (RCOM FY2019, Suzlon FY2012).
FACE_TEXT = re.compile(r"(face|par|nominal)\s+value\s*(of\s+(each\s+)?(equity\s+)?shares?)?\s*(of)?\s*(rs\.?|₹|`)?\s*"
                       r"\d+(\.\d+)?\s*(/-)?\s*(each)?", re.I)
# Some PDFs split the fi and fl ligatures off the word: "Profi t", "Cash fl ow" (L&T FY2011).
LIGATURE = re.compile(r"(fi|fl) (?=[a-z])")
# Note and page references before a caption: "2 148 (a) Share Capital" (Tata Steel FY2012).
NOTE_REF = re.compile(r"^\s*(?:\d{1,3}\s+){1,2}(?=[\(\[]?[A-Za-z])")


def strip_label(line):
    """The caption without its note references and list number, for matching patterns."""
    return ENUM.sub("", NOTE_REF.sub("", line)).strip()


def values(line):
    """Numbers on a line, without list numbers like (1) and formulas like (VII-VIII)."""
    line = FORMULA.sub(" ", ENUM.sub("", line))
    line = FACE_TEXT.sub(" ", line)
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
    titled_pl = []
    for i, text in enumerate(pages):
        head = head_of(text)
        if SKIP_HEAD.search(head) or len(re.findall(r"\d[\d,]{3,}", text)) < 15:
            continue
        # A statement can run onto the next page (HUL FY2018 prints its EPS on
        # the P&L's second page), so the required caption may be on either.
        both = text + "\n" + (pages[i + 1] if i + 1 < len(pages) else "")
        for key in cand:
            if TITLE[key].search(head) and NEED[key].search(both):
                cand[key].append(i)
        if TITLE["pl"].search(head):
            titled_pl.append(i)
    # An abridged P&L prints no EPS (Infosys FY2012): a titled P&L right next
    # to a balance sheet is accepted when no P&L with EPS is near one.
    for b in cand["bs"]:
        if not any(abs(p - b) <= 4 for p in cand["pl"]):
            cand["pl"] += [p for p in titled_pl if 0 < p - b <= 2]
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


REF_TOKEN = re.compile(r"^\d{1,3}(\.\d{1,2})?$")


def row_values(line):
    """values(), plus: a lone dash is a zero, and note/page references are dropped.

    "(i) Borrowings 2.18 - 9,359" is 0 this year, 9,359 last year (RCOM FY2019);
    without the dash the note number 2.18 was read as this year's figure.
    """
    line = re.sub(r"(?<=\s)[-–](?=\s|$)", " 0 ", line)
    toks = [t for t in NUM.findall(FACE_TEXT.sub(" ", FORMULA.sub(" ", ENUM.sub("", line))))]
    vals = [(t, num(t)) for t in toks if num(t) is not None]
    while len(vals) > NCOLS[0] and REF_TOKEN.match(vals[0][0]):
        vals = vals[1:]
    return [v for _, v in vals]


def item_subtotal(v):
    """RCOM prints an item and its subtotal side by side for each year:
    "Other Equity 11,003 12,386 7,933 9,316" is 11,003 now, 7,933 last year
    (12,386 and 9,316 are total equity). Recognised only when both years'
    subtotal-minus-item gaps agree, as they do when share capital is unchanged."""
    if len(v) != 4 or min(abs(x) for x in v) < 100:
        return None
    g1, g2 = v[1] - v[0], v[3] - v[2]
    if g1 and g2 and 0.5 <= g1 / g2 <= 2:
        return v[0], v[2]
    return None


def line_value(lines, idx):
    """(current, previous) from a matching line, or the next line if it holds only numbers."""
    n = NCOLS[0]
    v = row_values(lines[idx])
    if len(v) < 2 and idx + 1 < len(lines) and not re.search(r"[A-Za-z]{3,}", lines[idx + 1]):
        v = v + row_values(lines[idx + 1])
    if n == 2 and item_subtotal(v):
        return item_subtotal(v)
    if len(v) >= n:
        return v[-n], v[-n + 1]
    if len(v) >= 2:
        return v[-2], v[-1]
    if len(v) == 1:
        return v[-1], None
    return None, None


def first_match(page_texts, patterns, exclude=None, last=False, max_abs=None):
    """The first (or, with last=True, the final) line matching a pattern, in pattern order.

    max_abs drops implausible values: an EPS line reading 2,29,69,44,664 is a
    share count (Infosys prints "Basic" for both).
    """
    for pat in patterns:
        rx = re.compile(pat, re.I)
        hits = []
        for pno, text in page_texts:
            lines = [clean(l) for l in text.splitlines()]
            for i, l in enumerate(lines):
                head = strip_label(re.sub(r"^[\-–•\s]+", "", l))
                if not rx.search(head) or (exclude and re.search(exclude, head, re.I)):
                    continue
                cur, prev = line_value(lines, i)
                if cur is None or (max_abs and abs(cur) > max_abs):
                    continue
                hits.append({"current": cur, "previous": prev, "page": pno + 1, "line": l[:150]})
                if not last:
                    return hits[0]
        if hits:
            return hits[-1]
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
    if twice:
        c, p = max(twice)
        return {"current": c, "previous": p, "line": counts[(c, p)][0][:150], "balanced": True}
    # Infosys and Tata Steel FY2016 print their totals as bare figure rows with
    # no "Total" caption. Accept a bare row only if it appears twice AND is the
    # largest figure on the page, as the grand total must be.
    bare = {}
    for l in (clean(x) for x in text.splitlines()):
        if re.search(r"[A-Za-z]", l):
            continue
        v = values(l)
        if len(v) == NCOLS[0]:
            bare.setdefault((round(v[0], 2), round(v[1], 2)), []).append(l)
    twice = [k for k, ls in bare.items() if len(ls) >= 2 and k[0] > 0]
    if not twice:
        return None
    c, p = max(twice)
    if c < max(k[0] for k in bare):
        return None
    return {"current": c, "previous": p, "line": bare[(c, p)][0][:150] + " (bare row)", "balanced": True}


def old_layout_gross(text):
    """Total assets from an old "Sources / Application of funds" balance sheet.

    Before FY2012 the balance sheet total is capital employed: current
    liabilities and provisions are subtracted from current assets ("Less:
    Current Liabilities and Provisions ... Net Current Assets"). Total assets
    = that total + current liabilities and provisions. Accepted only when
    current assets - (liabilities + provisions) = the printed net current
    assets, in both years.
    """
    lines = [clean(l) for l in text.splitlines()]
    less = next((i for i, l in enumerate(lines)
                 if re.match(r"^less\s*:?\s*current\s+liabilities", strip_label(l), re.I)), None)
    if less is None:
        return None
    nca = next((i for i in range(less + 1, min(less + 12, len(lines)))
                if re.match(r"^net\s+current\s+assets", strip_label(lines[i]), re.I)), None)
    if nca is None:
        return None
    items = [line_value(lines, i) for i in range(less + 1, nca) if re.search(r"[A-Za-z]{3,}", lines[i])]
    items = [v for v in items if v[0] is not None and v[1] is not None]
    net = line_value(lines, nca)
    # current assets: the bare subtotal row just above the "Less:" line
    ca = next((row_values(lines[i]) for i in range(less - 1, max(less - 3, -1), -1)
               if not re.search(r"[A-Za-z]", lines[i]) and len(row_values(lines[i])) == 2), None)
    if not items or net[0] is None or net[1] is None or not ca:
        return None
    cl = (sum(v[0] for v in items), sum(v[1] for v in items))
    ok = all(abs(ca[j] - cl[j] - net[j]) <= 0.001 * abs(ca[j]) + 1 for j in (0, 1))
    return {"cl_current": cl[0], "cl_previous": cl[1], "checked": ok}


def face_check(profit, eps, caps, k_cr, exact_any=False):
    """(implied face value, passes) from profit / EPS = share count, capital / count = face.

    EPS uses the weighted average share count, so when shares were issued
    during the year the face value may lie between what opening and closing
    capital imply. A bonus issue doubles capital but restates the share count,
    so the closing capital alone may also match (Infosys FY2016, FY2019).
    """
    caps = [c for c in caps if c]
    if not (profit and eps and caps and k_cr):
        return None, False
    shares = profit * k_cr * 1e7 / eps
    faces = [c * k_cr * 1e7 / shares for c in caps]
    tol = 0.04 + 0.005 / abs(eps)               # EPS is printed to 2 decimals
    exact = any(abs(fc - fv) / fv < tol for fc in (faces if exact_any else faces[:1]) for fv in FACES)
    lo, hi = min(faces), max(faces)
    between = 0 < lo and hi / lo < 1.6 and any(lo * (1 - tol) <= fv <= hi * (1 + tol) for fv in FACES)
    return faces[0], exact or between


def extract_pages(pages, name):
    out = {"file": name, "pages": len(pages)}
    pages = [LIGATURE.sub(r"\1", decode_cids(p)) for p in pages]
    st = find_statements(pages)
    out["statement_pages"] = {k: v + 1 for k, v in st.items()}
    if not st:
        out["error"] = "no standalone statements found"
        return out
    span = lambda k, n=2: [(i, pages[i]) for i in range(st[k], min(st[k] + n, len(pages)))] if k in st else []
    unit = unit_of("\n".join(pages[i][:1500] for i in st.values()))
    years = re.findall(r"(?:31(?:st)?\s+march|march\s+31|31\.03\.)[,\s]*(20\d\d)", pages[st["bs"]][:1500], re.I) \
        if "bs" in st else []
    out["fy"] = max(int(y) for y in years) if years else None
    out["unit"] = unit
    f = {}
    bs, pl, cf = span("bs"), span("pl"), span("cf", 3)
    if bs:
        NCOLS[0] = columns_of(bs[0][1])
        tb = balancing_total(bs[0][1]) or (balancing_total(bs[1][1]) if len(bs) > 1 else None)
        if not tb:
            # Ind AS layout: "Total assets" and "Total equity and liabilities"
            # are separate captions, often on separate pages.
            ta = first_match(bs, [r"^total\s+assets\b"])
            tel = first_match(bs, [r"^total\s+equity\s+(and|&)\s+liabilities", r"^total\s+liabilities\s+(and|&)\s+equity"])
            if ta:
                ta["balanced"] = bool(tel and abs(tel["current"] - ta["current"]) <= 0.01 * abs(ta["current"]) + 1)
            tb = ta
        old = re.search(r"sources\s+of\s+funds", bs[0][1], re.I) and re.search(r"application\s+of\s+funds", bs[0][1], re.I)
        out["layout"] = "sources_and_application" if old else "equity_and_liabilities"
        if tb and old:
            # The printed total is capital employed, not total assets.
            tb["net_of_current_liabilities"] = True
            g = old_layout_gross(bs[0][1])
            if g and g["checked"]:
                tb["capital_employed"] = (tb["current"], tb["previous"])
                tb["current"] += g["cl_current"]
                tb["previous"] += g["cl_previous"]
                tb["line"] = "capital employed + current liabilities and provisions: " + tb["line"][:80]
            else:
                tb["balanced"] = False      # no checked total assets: do not pass
        f["total_assets"] = tb
        f["share_capital"] = first_match(bs, [r"^equity\s+share\s+capital", r"^share\s+capital",
                                               r"^equity\s+([a-z]\s+)?[\d(]"])   # DHFL FY2019: "Equity 24 31,382"
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
                                        r"^net\s+sales", r"^sales.{0,25}\(net\)", r"^operating\s+revenue", r"^total\s+revenue", r"^total\s+income", r"^interest\s+earned"],
                                   exclude=r"other\s+income")
        f["profit_for_year"] = first_match(pl, [
            r"^(net\s+)?(\(loss\)\s*/\s*)?profit\s*(/\s*\(loss\))?\s+for\s+the\s+(year|period)(?!.*before)",
            r"^(net\s+)?(profit|loss)\s+for\s+the\s+(year|period)(?!.*before)",
            r"^(net\s+)?[\(\)/\s]*(profit|loss)[\(\)/\sa-z]{0,20}for\s+the\s+(year|period)",
            r"^(net\s+)?profit\s*(/\s*\(loss\))?\s+after\s+tax", r"^(net\s+)?[\(\)/\s]*(profit|loss)[\(\)/\sa-z]{0,20}after\s+tax",
            r"^net\s+profit\b(?!.*before)"],
            exclude=r"before|comprehensive|attributable|discontinued|account|statement|ended")
        # With discontinued operations and no "profit for the year" line, the
        # year's profit is continuing plus discontinued (RCOM FY2019: 5,099 - 2,252).
        disc = first_match(pl, [r"(profit|loss).{0,20}after\s+tax.{0,10}from\s+discontinued"], exclude=r"before")
        pr0 = f["profit_for_year"]
        if disc and pr0 and not re.search(r"for\s+the\s+(year|period)", pr0["line"], re.I):
            f["profit_for_year"] = {
                "current": pr0["current"] + disc["current"],
                "previous": (pr0["previous"] + disc["previous"]) if (pr0["previous"] is not None and disc["previous"] is not None) else None,
                "page": pr0["page"], "line": pr0["line"][:70] + " + " + disc["line"][:70], "derived": True}
        # The last "Basic" line: Infosys FY2016 prints EPS before and after an
        # exceptional item, and the second (68.73) is the year's EPS.
        f["eps_basic"] = first_match(pl, [r"^continuing\s+(operations\s+)?(and|&)\s+discontinued",
                                          r"^basic\b", r"basic\s*(and|&|/)\s*diluted",
                                          r"basic\s+earnings\s+per", r"earnings\s+per\s+share.*basic"],
                                     exclude=r"before\s+exceptional|weighted|number\s+of", last=True,
                                     max_abs=20000)
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
    if pr and eps and sc and k_cr:
        implied, ok = face_check(pr["current"], eps["current"], [sc["current"], sc["previous"]], k_cr)
        if implied is not None:
            out["implied_face_value"] = round(implied, 3)
            chk["face_value"] = ok
        # The previous-year column, for information only: it needs capital at
        # the START of last year, which this report does not print. On the
        # pilot all 7 misses were shares issued last year or restated EPS
        # (Jet, Suzlon, Tata Steel, DHFL, RCOM), none a misread.
        implied, ok = face_check(pr["previous"], eps["previous"], [sc["previous"], sc["current"]], k_cr,
                                 exact_any=True)
        if implied is not None:
            out["info_face_value_prev"] = ok
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


CONTINUITY_FIELDS = ("revenue", "profit_for_year", "share_capital", "total_equity", "total_assets", "eps_basic")


def continuity(results):
    """Last year's column in one report against the current column of the report before.

    The two reports are separate documents, so this is an independent read of
    the same number. A figure taken from the wrong column (RCOM equity before
    v8) fails it. Genuine restatements (Ind AS transition, mergers) fail it
    too, so a mismatch is flagged for review, never corrected automatically.
    """
    by_co = {}
    for r in results:
        if r.get("figures") and r.get("fy"):
            by_co.setdefault(os.path.dirname(r["file"]), {})[r["fy"]] = r
    for reps in by_co.values():
        for fy, r in reps.items():
            prior = reps.get(fy - 1)
            if not prior:
                continue
            res = {}
            for k in CONTINUITY_FIELDS:
                a, b = r["figures"].get(k), prior["figures"].get(k)
                if not (a and b) or a.get("previous") is None:
                    continue
                ka = 1 if k == "eps_basic" else TO_CRORE.get(r.get("unit"), 0)
                kb = 1 if k == "eps_basic" else TO_CRORE.get(prior.get("unit"), 0)
                va, vb = a["previous"] * ka, b["current"] * kb
                res[k] = abs(va - vb) <= 0.02 * abs(vb) + (0.011 if k == "eps_basic" else 0.5)
            r["continuity"] = res


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
    continuity(results)
    json.dump(results, open(out_path, "w"), indent=1)
    ok = [r for r in results if r.get("figures")]
    print(f"\n{len(ok)} reports with statements; verified (balance AND face value): "
          f"{sum(1 for r in ok if r.get('verified'))}")
    pairs = [(r["file"], k, v) for r in ok for k, v in r.get("continuity", {}).items()]
    print(f"continuity, last year's column vs the prior report: {sum(1 for p in pairs if p[2])} of "
          f"{len(pairs)} figures agree")
    for name, k, v in pairs:
        if not v:
            print(f"   differs: {name} {k}")


if __name__ == "__main__":
    main()
