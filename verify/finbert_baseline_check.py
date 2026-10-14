"""
finbert_baseline_check.py — inside the verification image: the pinned FinBERT reproduces the
recorded baseline (verify/finbert_baseline_2026-10-14.json, recorded 2026-10-14 under
transformers 5.12.1 / torch 2.12.1).

The same comparison was run locally under production's torch / transformers / tokenizers (identical
outputs); this runs it on Python 3.12, Linux and numpy 1.26.4, the combination not run locally. Exits 1 on any difference
in label or 4-decimal confidence, or a different failure path.
"""
import json
import sys

from transformers import pipeline
import torch

REV = "4556d13015211d73dccd3fdd39d39232506f3e43"
base = json.load(open(sys.argv[1], encoding="utf-8"))
torch.set_num_threads(1)
pipe = pipeline("text-classification", model="ProsusAI/finbert", revision=REV, top_k=None, device=-1)
cases = {
    "valid_positive": "Reliance Industries posts record quarterly profit, beats estimates",
    "valid_negative": "Vodafone Idea shares slump after losses widen and debt concerns mount",
    "valid_neutral": "Infosys to announce second-quarter results on October 16",
    "valid_mixed": "Tata Steel revenue rises but margins fall on higher coking coal costs",
    "unicode_hindi": "रिलायंस का मुनाफा बढ़ा",
    "long_over_512_chars": ("Markets " * 120).strip(),
    "empty_string": "",
}
bad, maxd = 0, 0.0
for k, t in cases.items():
    r = {x["label"]: x["score"] for x in pipe(t[:512])[0]}
    lab = max(r, key=r.get)
    b = base["cases"][k]
    d = max(abs(r[l] - b["scores"][l]) for l in b["scores"])
    maxd = max(maxd, d)
    same = lab == b["label"] and round(r[lab], 4) == b["confidence"]
    bad += not same
    print(f"{'ok  ' if same else 'DIFF'} {k}: {lab} {round(r[lab], 4)} (baseline {b['label']} {b['confidence']}), max |dp| {d:.2e}")
for k, t in {"non_string_none": None, "non_string_int": 12345}.items():
    try:
        pipe(t)
        print(f"DIFF {k}: did not raise"); bad += 1
    except Exception as e:
        print(f"ok   {k}: raises {type(e).__name__}")
print(f"max raw probability difference {maxd:.2e}; {bad} difference(s)")
sys.exit(1 if bad else 0)
