"""
sentiment_test3_run.py — factor test 3: does the app's FinBERT labelling agree
with people on Indian financial headlines it was not trained on?

Rules: docs/PREREG_FACTOR_TEST3_SENTIMENT_2026-09-13.md, committed before this
runs on the real data.

    python research/sentiment_test3_run.py SEntFiN.csv OUT.json

`run(csv_path, classify=...)` takes any function from a list of headlines to a
list of labels, so the scoring and the verdict can be checked on made-up
headlines without loading the model.
"""

import ast
import csv
import json
import random
import sys

LABELS = ("positive", "negative", "neutral")
BOOTSTRAP_RESAMPLES = 2000
SEED = 20260913
WORKS_F1, FAILS_F1, BASELINE_MARGIN = 0.60, 0.40, 0.10


def load(csv_path):
    """Single-entity headlines and their human label."""
    rows, skipped_multi, skipped_bad = [], 0, 0
    with open(csv_path, encoding="utf-8", newline="") as fh:
        for rec in csv.DictReader(fh):
            try:
                decisions = ast.literal_eval(rec["Decisions"])
            except Exception:
                skipped_bad += 1
                continue
            if not isinstance(decisions, dict) or len(decisions) != 1:
                skipped_multi += 1
                continue
            label = str(next(iter(decisions.values()))).strip().lower()
            if label not in LABELS:
                skipped_bad += 1
                continue
            rows.append((rec["Title"], label))
    return rows, {"multi_entity_excluded": skipped_multi, "unreadable_excluded": skipped_bad}


def finbert_classifier(batch_size=32):
    """The app's labelling: FinBERT, all scores, text cut to 512 characters, highest score wins."""
    from transformers import pipeline
    pipe = pipeline("text-classification", model="ProsusAI/finbert", top_k=None, device=-1)

    def classify(texts):
        out = []
        for i in range(0, len(texts), batch_size):
            for item in pipe([t[:512] for t in texts[i:i + batch_size]]):
                out.append(max(item, key=lambda x: x["score"])["label"].lower())
        return out
    return classify


def scores(true, pred):
    n = len(true)
    confusion = {t: {p: 0 for p in LABELS} for t in LABELS}
    for t, p in zip(true, pred):
        confusion[t][p if p in LABELS else "neutral"] += 1
    per = {}
    for lab in LABELS:
        tp = confusion[lab][lab]
        fp = sum(confusion[t][lab] for t in LABELS if t != lab)
        fn = sum(confusion[lab][p] for p in LABELS if p != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[lab] = {"precision": prec, "recall": rec, "f1": f1, "support": tp + fn}
    accuracy = sum(confusion[l][l] for l in LABELS) / n if n else 0.0
    macro_f1 = sum(per[l]["f1"] for l in LABELS) / len(LABELS)
    expected = sum((sum(confusion[l].values()) / n) * (sum(confusion[t][l] for t in LABELS) / n)
                   for l in LABELS) if n else 0.0
    kappa = (accuracy - expected) / (1 - expected) if expected < 1 else 0.0
    polar = [(t, p) for t, p in zip(true, pred) if t in ("positive", "negative")]
    flips = sum(1 for t, p in polar if (t, p) in (("positive", "negative"), ("negative", "positive")))
    return {"n": n, "accuracy": accuracy, "macro_f1": macro_f1, "kappa": kappa,
            "per_label": per, "confusion": confusion,
            "polarity_flips": flips, "polar_headlines": len(polar),
            "polarity_flip_rate": flips / len(polar) if polar else None}


def bootstrap(true, pred, resamples=BOOTSTRAP_RESAMPLES, seed=SEED):
    rng = random.Random(seed)
    n = len(true)
    f1s, accs = [], []
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        s = scores([true[i] for i in idx], [pred[i] for i in idx])
        f1s.append(s["macro_f1"])
        accs.append(s["accuracy"])
    f1s.sort()
    accs.sort()
    lo, hi = int(0.025 * resamples), int(0.975 * resamples) - 1
    return {"macro_f1": [f1s[lo], f1s[hi]], "accuracy": [accs[lo], accs[hi]]}


def verdict(ci, baseline_accuracy):
    f1_lo, acc_lo = ci["macro_f1"][0], ci["accuracy"][0]
    if f1_lo >= WORKS_F1 and acc_lo >= baseline_accuracy + BASELINE_MARGIN:
        return "works"
    if f1_lo < FAILS_F1 or acc_lo <= baseline_accuracy:
        return "fails"
    return "weak"


def run(csv_path, classify=None, resamples=BOOTSTRAP_RESAMPLES):
    rows, excluded = load(csv_path)
    texts = [t for t, _ in rows]
    true = [l for _, l in rows]
    classify = classify or finbert_classifier()
    pred = classify(texts)
    s = scores(true, pred)
    ci = bootstrap(true, pred, resamples=resamples)
    counts = {l: true.count(l) for l in LABELS}
    majority = max(counts, key=counts.get)
    base = scores(true, [majority] * len(true))
    return {
        "rules": "docs/PREREG_FACTOR_TEST3_SENTIMENT_2026-09-13.md",
        "data": {"headlines_used": len(rows), **excluded, "human_label_counts": counts},
        "model": s,
        "ci95": ci,
        "baseline": {"always": majority, "accuracy": base["accuracy"], "macro_f1": base["macro_f1"]},
        "verdict": verdict(ci, base["accuracy"]),
        "thresholds": {"works_macro_f1_lower_bound": WORKS_F1, "fails_below": FAILS_F1,
                       "accuracy_margin_over_baseline": BASELINE_MARGIN},
    }


if __name__ == "__main__":
    result = run(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    m = result["model"]
    print(json.dumps({"data": result["data"], "verdict": result["verdict"],
                      "macro_f1": round(m["macro_f1"], 4), "accuracy": round(m["accuracy"], 4),
                      "kappa": round(m["kappa"], 4), "ci95": result["ci95"],
                      "baseline": result["baseline"],
                      "polarity_flip_rate": m["polarity_flip_rate"]}, indent=1))
    print("written:", sys.argv[2])
