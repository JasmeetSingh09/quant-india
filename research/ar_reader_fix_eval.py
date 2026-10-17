"""Evaluate the reader fixes on a split part (development or held-out) plus the no-regression set.

    python research/ar_reader_fix_eval.py development <work_dir>   (held_out only after the fixes are committed)
Writes accepted_<part>.json here; never touches review_v11/accepted.json.
"""
import json, os, sys, collections
PART = sys.argv[1]
RES = r"C:\Users\seeraj\OneDrive\Documents\Desktop\code\ai_stock\research"
ROOT = r"C:\Users\seeraj\quant_data\annual_reports"
HERE = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__))  # holds the baseline and outputs
sys.path.insert(0, RES)
import ar_review as AR  # noqa: E402

split = json.load(open(os.path.join(ROOT, "manifest", "reader_fix_split_2026-10-17.json"), encoding="utf-8"))
cases = split["populations"]["FACE"][PART]["cases"]
other = "held_out" if PART == "development" else "development"
forbidden = {f for c in split["populations"]["FACE"][other]["cases"] for f in c["files"]} if PART == "development" else set()
base = json.load(open(os.path.join(HERE, "baseline_complete_2026-10-17.json"), encoding="utf-8"))
base_files = {f for v in base.values() for f in v}
target = {f for c in cases for f in c["files"]}
only = (target | base_files) - forbidden
extract = AR.load_extract(os.path.join(ROOT, "extract_v10_full3.json"))
out = os.path.join(HERE, f"accepted_{PART}.json")
cwd = os.getcwd()
os.chdir(ROOT)
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    AR.check(ROOT, extract, os.path.join(ROOT, "review_v11"), r"C:\Users\seeraj\quant_data\ar_cache",
             out_path=out, only=only)
os.chdir(cwd)
new = json.load(open(out, encoding="utf-8"))

# Same completeness rule as the coverage count (ar_gap_list.py), applied to the new readings.
src = open(os.path.join(RES, "ar_gap_list.py"), encoding="utf-8").read().split("rows, tot, complete = [], 0, 0")[0]
ns = {}
sys.argv = ["x", ROOT]
exec(src, ns)
score = ns["score"]
# 1. no regression on the 474
reg = []
for key, files in base.items():
    for f, figs in files.items():
        rec = new.get(f)
        if not rec:
            reg.append((key, f, "missing"))
            continue
        v, q, _ = score(rec)
        if not (v and q):
            reg.append((key, f, "no longer complete"))
            continue
        for k, (cur, prev) in figs.items():
            fig = rec["figures"].get(k) or {}
            if not fig.get("accepted") or fig.get("current") != cur or fig.get("previous") != prev:
                reg.append((key, f, f"{k} changed: {cur}->{fig.get('current')}"))
print(f"no-regression: {len(base)} complete company-years, {len(reg)} problems")
for r in reg[:20]:
    print("   ", r)
# 2. gain on the part
gain, still = [], collections.Counter()
for c in cases:
    recs = [new[f] for f in c["files"] if f in new]
    sc = [score(r) for r in recs]
    if any(v and q for v, q, _ in sc):
        gain.append((c["symbol"], c["fy"]))
    else:
        best = min(sc, key=lambda x: len(x[2])) if sc else (0, 0, ["not read"])
        for m in best[2]:
            still[m] += 1
print(f"{PART}: {len(gain)} of {len(cases)} company-years now complete")
print("   newly complete:", gain)
print("   still missing (inputs, among the rest):", still.most_common())
subs = [(f, r["figures"]["share_capital"].get("page")) for f, r in new.items()
        if f in target and (r["figures"].get("share_capital") or {}).get("source")]
print("   equity-line substitutions:", len(subs))
