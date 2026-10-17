"""
ar_equity_capital.py — the EQUITY share capital line from the share-capital note.

Reader fix B (docs/AR_READER_FIX_PLAN_2026-10-17.md). Diagnosed on development
cases only (TCS FY2012/13, JSW Steel, Aban): the balance sheet's "Share capital"
line can include preference capital, so profit / EPS / share capital implies a
face value no company has (TCS 1.51 for a Re 1 share), the face check fails, and
the share count used later for P/B would be overstated. The reading instructions
already define share_capital as EQUITY share capital; readers took the combined
balance-sheet line.

The note prints the equity line itself, for example
    (i) 195,72,20,996 equity shares of ` 1 each 195.72 195.72
This module reads that line. It is used only if the line is internally
consistent: share count x face value = the printed amount (within 0.5%), the
count read either as shares or in the statement's unit. Nothing is computed by
subtraction. Whether the reading is used at all is decided in ar_review: only
when the unchanged face check then passes.
"""
import re

TO_RUPEES = {"crore": 1e7, "lakh": 1e5, "million": 1e6, "billion": 1e9, "thousand": 1e3, "rupees": 1.0}

ISSUED = re.compile(r"issued(?:,|\s+and)?\s*subscribed|subscribed\s+and\s+(?:fully\s+)?paid|"
                    r"issued\s+and\s+(?:fully\s+)?paid|paid[\s-]*up\s+(?:share\s+)?capital", re.I)
# The issued block's HEADING: it starts the line, optionally after "b", "(ii)", "2." and the like.
# A sentence such as "The authorised, issued, subscribed ... comprises" is not a heading
# (TCS FY2012 development case: matching it took the authorised line).
ISSUED_HEAD = re.compile(r"^\s*(?:\(?[a-z0-9]{1,4}[).]?\s+)?(?:issued|subscribed)\b", re.I)
# The par value where the issued line itself does not print it (JSW Steel development case:
# "24,17,22,044 ... Equity Shares fully paid up 241.72 223.12", par value given once above).
PAR_VALUE = re.compile(r"equity\s+shares?\s+of\s+(?:the\s+par\s+value\s+of\s+)?\s*(?:rs\.?|re\.?|inr|`|₹)\s*"
                       r"(\d+(?:\.\d+)?)\s*/?-?\s*each", re.I)
CAPITAL_NOTE = re.compile(r"share\s+capital", re.I)
NUM = r"\d[\d,]*(?:\.\d+)?"
EQUITY_LINE = re.compile(
    r"(?P<count>" + NUM + r")\s*(?:million|lakh|crore)?\s*(?:\([^)]*\)\s*)?"
    r"(?:fully\s+paid[\s-]*up\s+)?equity\s+shares?"
    r"(?:\s+of\s+(?:the\s+par\s+value\s+of\s+)?(?:rs\.?|re\.?|inr|`|₹)\s*(?P<fv>\d+(?:\.\d+)?)\s*/?-?\s*(?:each)?)?"
    r"(?P<rest>.*)$", re.I)
AMOUNTS = re.compile(r"(?<![\w.])(" + NUM + r")(?![\w.])")
# Ind AS layout (JSW Steel FY2017+ development cases): the issued block lists a
# reconciliation whose last line carries the share counts, then the amounts:
#   (iii) Outstanding at the end of the year, fully paid up 2,40,17,11,464 2,40,62,31,580 240 241
CLOSING_LINE = re.compile(r"outstanding\s+at\s+the\s+end\s+of\s+the\s+year(?P<rest>.*)$", re.I)


def _num(s):
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _consistent(count, fv, amount, unit):
    """count x face value = amount, with count as shares or in the statement's unit."""
    k = TO_RUPEES.get(unit)
    if not (count and fv and amount and k):
        return False
    target = amount * k
    # No Indian company's equity capital approaches Rs 5 lakh crore (the largest is
    # about Rs 7,000 crore): a bigger "amount" is a share count read as money
    # (JSW Steel FY2017, Adani Enterprises FY2018 development cases).
    if target > 5e12:
        return False
    readings = [count]
    # The count may be printed in the statement's unit ("36.88 million shares"), but
    # only a small number can be such a count; two share counts side by side would
    # otherwise match each other trivially.
    if count < 1e7:
        readings.append(count * k)
    return any(abs(shares * fv - target) <= 0.005 * target for shares in readings)


def read_equity_capital(pages, unit, start_page=0):
    """
    {current, previous, face_value, page, quote} for the standalone equity line, or None.

    pages: the report's page texts; start_page: 0-based index of the standalone balance
    sheet, so the first share-capital note after it (the standalone one) is used.
    """
    for i in range(max(0, start_page), len(pages)):
        text = pages[i]
        if not (CAPITAL_NOTE.search(text) and ISSUED.search(text)):
            continue
        lines = text.split("\n")
        start = next((j for j, l in enumerate(lines) if ISSUED_HEAD.search(l)), None)
        if start is None:
            continue
        par = PAR_VALUE.search(text)
        for line in lines[start + 1:start + 25]:
            m = EQUITY_LINE.search(line)
            if not m:
                continue
            amounts = [_num(a) for a in AMOUNTS.findall(m.group("rest"))]
            amounts = [a for a in amounts if a is not None]
            count = _num(m.group("count"))
            fv = _num(m.group("fv")) if m.group("fv") else (_num(par.group(1)) if par else None)
            if not amounts or not _consistent(count, fv, amounts[0], unit):
                continue
            prev = amounts[1] if len(amounts) > 1 else None
            return {"current": amounts[0], "previous": prev, "face_value": fv,
                    "page": i + 1, "quote": line.strip()}
        # Second pattern: the closing line of the issued block's reconciliation, read as
        # counts then amounts. Only with a par value printed on the page, and only if the
        # same count x face value = amount check holds.
        fv = _num(par.group(1)) if par else None
        for line in lines[start + 1:start + 25]:
            m = CLOSING_LINE.search(line)
            if not (m and fv):
                continue
            nums = [x for x in (_num(a) for a in AMOUNTS.findall(m.group("rest"))) if x is not None]
            if len(nums) < 3 or not _consistent(nums[0], fv, nums[2], unit):
                continue
            return {"current": nums[2], "previous": nums[3] if len(nums) > 3 else None,
                    "face_value": fv, "page": i + 1, "quote": line.strip()}
        # The first share-capital note after the balance sheet is the standalone one;
        # if its equity line is not readable, do not fall through to the consolidated note.
        return None
    return None
