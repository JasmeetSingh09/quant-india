"""
ar_review.py: a second (and third) reader for annual reports the rules could not verify.

The rule-based reader (ar_extract.py) is one reader. An AI (Codex, Claude,
another model) or a person can be another: each fills the same form from the
statement pages. Nothing a reader says is trusted on its own. A figure is
accepted only if

  1. grounded   the quoted line is on the cited page and contains the number,
                so a figure cannot be invented; and
  2. confirmed  the report-level checks pass with it (balance sheet totals
                equal; profit / EPS gives a real face value), or two readers
                read the same number independently.

    python research/ar_review.py export <reports_dir> <extract.json> <review_dir> [--cache DIR] [--all]
    python research/ar_review.py check  <reports_dir> <extract.json> <review_dir> [--cache DIR]

export writes, per report, <id>.pages.txt (the statement pages) and
<id>.form.json (blank). A reader saves its answers as <id>.<reader>.json,
for example <id>.codex.json. check writes accepted.json and prints a summary.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ar_extract as A  # noqa: E402

FIELDS = ("revenue", "profit_for_year", "eps_basic", "share_capital", "total_equity",
          "total_assets", "total_equity_and_liabilities", "borrowings", "operating_cash_flow")

INSTRUCTIONS = """# Reading an annual report: instructions for any reader (AI or person)

Fill `<id>.form.json` from `<id>.pages.txt` and save it as `<id>.<your name>.json`
(for example `<id>.codex.json`). Do not edit the form itself.

Rules
- STANDALONE statements only, never consolidated.
- Copy every number exactly as printed in the statement's own unit. Do not convert,
  round or add anything up. Losses and negatives are negative numbers.
- `quote` is the whole printed line the number comes from, copied character for
  character; `page` is the number in its "===== page N" marker. The checker rejects a
  figure whose quote is not on that page or does not contain the number.
- A figure the statements do not print is `null`. Never estimate one. Say why in `notes`.
- `unit`: crore, lakh, million, thousand or rupees, as the statements state it.
- `fy`: the year the accounts end, e.g. 2012 for the year ending 31 March 2012.

Fields (current year and previous year)
- revenue: revenue from operations (net of excise duty if both are shown).
- profit_for_year: profit (loss) for the year after tax, including discontinued
  operations. Not "before exceptional items", not total comprehensive income.
- eps_basic: basic earnings per share for the year, after exceptional items.
- share_capital: equity share capital.
- total_equity: shareholders' funds / total equity.
- total_assets: total assets. In the old "Sources of funds / Application of funds"
  layout the printed TOTAL is capital employed, NOT total assets: give total_assets as
  null there unless the report prints total assets, and put the printed TOTAL in
  total_equity_and_liabilities.
- total_equity_and_liabilities: the total of the equity-and-liabilities side.
- borrowings: all borrowings (long-term, short-term, debt securities, subordinated
  debt), as separate lines are not added: give the largest single borrowings line and
  list the others in notes.
- operating_cash_flow: net cash from (used in) operating activities.
"""


def safe_id(path):
    return re.sub(r"[^A-Za-z0-9]+", "_", path[:-4]).strip("_")


def load_extract(path):
    return {r["file"]: r for r in json.load(open(path))}


def export(root, extract, out_dir, cache, everything):
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, "INSTRUCTIONS.md"), "w", encoding="utf-8").write(INSTRUCTIONS)
    n = 0
    for name, r in sorted(extract.items()):
        if not r.get("figures") or (r.get("verified") and not everything):
            continue
        pages = A.load_pages(name, cache)
        pages = [A.LIGATURE.sub(r"\1", p) for p in pages]
        want = set()
        for p in (r.get("statement_pages") or {}).values():
            want.update({p - 1, p, p + 1})          # 1-based page and its neighbours
        text = "".join(f"\n===== page {p}\n{pages[p - 1]}\n" for p in sorted(want) if 1 <= p <= len(pages))
        sid = safe_id(name)
        open(os.path.join(out_dir, sid + ".pages.txt"), "w", encoding="utf-8").write(
            f"Report: {name}\nStandalone statement pages found by the rule reader: "
            f"{r.get('statement_pages')}\n{text}")
        form = {"report": name, "fy": None, "unit": None,
                "figures": {k: {"current": None, "previous": None, "page": None, "quote": None} for k in FIELDS},
                "notes": ""}
        json.dump(form, open(os.path.join(out_dir, sid + ".form.json"), "w"), indent=1)
        n += 1
    print(f"exported {n} reports to {out_dir}")


def _norm(s):
    return re.sub(r"\s+", " ", A.LIGATURE.sub(r"\1", s or "")).strip()


def grounded(pages, fig, value):
    """The quote is on the cited page and the value is one of its numbers."""
    if value is None:
        return True
    q, p = _norm(fig.get("quote")), fig.get("page")
    if not q or not isinstance(p, int) or not 1 <= p <= len(pages):
        return False
    if q not in _norm(pages[p - 1]):
        return False
    if value == 0 and re.search(r"(^|\s)[–-](\s|$)", q):
        return True                                  # "LOAN FUNDS – –": printed as a dash
    nums = [A.num(t) for t in A.NUM.findall(q.replace("`", " "))]
    return any(x is not None and abs(abs(x) - abs(value)) < 1e-6 for x in nums)


def rule_reading(r):
    f = r["figures"]
    out = {k: ({"current": v["current"], "previous": v["previous"]} if v else None) for k, v in f.items()}
    ta = f.get("total_assets")
    out["total_equity_and_liabilities"] = None
    if ta and ta.get("balanced") and not ta.get("net_of_current_liabilities"):
        out["total_equity_and_liabilities"] = {"current": ta["current"], "previous": ta["previous"]}
    return {"unit": r.get("unit"), "figures": out}


def report_checks(fig, unit):
    k_cr = A.TO_CRORE.get(unit)
    g = lambda k, c="current": (fig.get(k) or {}).get(c)
    ok = {}
    if g("total_assets") is not None and g("total_equity_and_liabilities") is not None:
        ok["balance"] = abs(g("total_assets") - g("total_equity_and_liabilities")) <= 0.001 * abs(g("total_assets")) + 1
    implied, face = A.face_check(g("profit_for_year"), g("eps_basic"),
                                 [g("share_capital"), g("share_capital", "previous")], k_cr)
    if implied is not None:
        ok["face_value"] = face
    return ok


def check(root, extract, review_dir, cache):
    accepted, summary = {}, []
    for name, r in sorted(extract.items()):
        sid = safe_id(name)
        readers = {f.split(".")[-2]: os.path.join(review_dir, f) for f in os.listdir(review_dir)
                   if f.startswith(sid + ".") and f.endswith(".json") and not f.endswith(".form.json")}
        if not readers:
            continue
        pages = [A.LIGATURE.sub(r"\1", p) for p in A.load_pages(name, cache)]
        reads = {"rules": rule_reading(r)} if r.get("figures") else {}
        problems = []
        for who, path in readers.items():
            try:
                d = json.load(open(path, encoding="utf-8"))
            except (ValueError, OSError) as e:
                problems.append(f"{who}: unreadable file ({type(e).__name__})")
                continue
            clean = {}
            for k in FIELDS:
                fig = (d.get("figures") or {}).get(k) or {}
                cur, prev = fig.get("current"), fig.get("previous")
                if cur is None and prev is None:
                    clean[k] = None
                elif grounded(pages, fig, cur) and grounded(pages, fig, prev):
                    clean[k] = {"current": cur, "previous": prev}
                else:
                    clean[k] = None
                    problems.append(f"{who}: {k} not found on page {fig.get('page')} as quoted")
            reads[who] = {"unit": d.get("unit"), "figures": clean, "notes": d.get("notes", "")}
        final = {}
        for k in FIELDS:
            votes = {}
            for who, rd in reads.items():
                v = rd["figures"].get(k)
                if v and v.get("current") is not None:
                    votes.setdefault((rd["unit"], v["current"], v["previous"]), []).append(who)
            if not votes:
                continue
            (unit, cur, prev), who = max(votes.items(), key=lambda kv: len(kv[1]))
            final[k] = {"current": cur, "previous": prev, "unit": unit, "readers": who,
                        "agreed": len(who) >= 2, "disputed": len(votes) > 1}
        units = {v["unit"] for v in final.values()}
        unit = units.pop() if len(units) == 1 else None
        chk = report_checks(final, unit) if unit else {}
        for k, v in final.items():
            by_check = (k in ("total_assets", "total_equity_and_liabilities") and chk.get("balance")) or \
                       (k in ("profit_for_year", "eps_basic", "share_capital") and chk.get("face_value"))
            v["accepted"] = bool(v["agreed"] and not v["disputed"]) or bool(by_check and not v["disputed"])
        accepted[name] = {"unit": unit, "checks": chk, "figures": final, "problems": problems,
                          "readers": sorted(reads)}
        n_acc = sum(1 for v in final.values() if v["accepted"])
        summary.append(f"{name[:48]:48} readers {'+'.join(sorted(reads)):20} accepted {n_acc}/{len(final)} "
                       f"checks {chk} {'; '.join(problems)[:120]}")
    json.dump(accepted, open(os.path.join(review_dir, "accepted.json"), "w"), indent=1)
    print("\n".join(summary) or "no reader files found")


def main():
    cmd, root, extract_path, review_dir = sys.argv[1:5]
    cache = sys.argv[sys.argv.index("--cache") + 1] if "--cache" in sys.argv else None
    extract = load_extract(extract_path)
    # Page-cache keys are paths relative to the reports folder, as ar_extract uses them.
    review_dir, cache = os.path.abspath(review_dir), cache and os.path.abspath(cache)
    os.chdir(root)
    if cmd == "export":
        export(root, extract, review_dir, cache, "--all" in sys.argv)
    elif cmd == "check":
        check(root, extract, review_dir, cache)


if __name__ == "__main__":
    main()
