"""
finbert_failure_injection.py — the sentiment failure policy against the REAL pinned FinBERT.

Local only: it loads the model (CI is offline). Spec:
docs/SPEC_SENTIMENT_FAILURE_POLICY_2026-10-14.md. Checks:
  1. every valid baseline headline scores exactly as recorded in
     docs/audit/finbert_baseline_2026-10-14.json (pinned revision unchanged);
  2. with one headline forced to raise INSIDE the real pipeline, the sentiment
     factor equals the run without that headline (skipped, counted, no dilution,
     no inflated coverage);
  3. with every headline forced to raise, sentiment is refused with
     "sentiment inference failed".
News is stubbed with the baseline headlines; nothing touches the network or a database.

    cd backend && python ../research/finbert_failure_injection.py
"""
import json
import os
import sys
import types
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "backend")
sys.path.insert(0, os.path.join(BACKEND, "modules"))
os.environ.pop("DATABASE_URL", None)

BASE = json.load(open(os.path.join(HERE, "..", "docs", "audit", "finbert_baseline_2026-10-14.json"),
                      encoding="utf-8"))
HEADLINES = {
    "valid_positive": "Reliance Industries posts record quarterly profit, beats estimates",
    "valid_negative": "Vodafone Idea shares slump after losses widen and debt concerns mount",
    "valid_neutral": "Infosys to announce second-quarter results on October 16",
    "valid_mixed": "Tata Steel revenue rises but margins fall on higher coking coal costs",
}
POISON = "THIS HEADLINE IS FORCED TO FAIL INSIDE THE PIPELINE"

import sentiment as S  # noqa: E402  (loads the pinned model)

PASS, FAIL = [], []


def ok(cond, label, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))


print("\n1. PINNED MODEL REPRODUCES THE BASELINE")
for k, t in HEADLINES.items():
    r = S.score_headline(t)
    b = BASE["cases"][k]
    ok(r["label"] == b["label"] and abs(r["confidence"] - b["confidence"]) < 1e-9, k,
       f"{r['label']} {r['confidence']} vs {b['label']} {b['confidence']}")

real_pipe = S._finbert


def poisoned(text, *a, **k):
    if (text if isinstance(text, str) else "") .startswith(POISON[:20]):
        raise RuntimeError("injected inference failure")
    return real_pipe(text, *a, **k)


S._finbert = poisoned
news = types.ModuleType("news")
sys.modules["news"] = news
import alpha_model as A  # noqa: E402


def run(titles):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    news.get_stock_news = lambda ticker, days_back=14: [
        {"title": t, "published_at": (now - timedelta(hours=6 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        for i, t in enumerate(titles)]
    return A._compute_sentiment_factor("X.NS")


print("\n2. ONE HEADLINE FAILS INSIDE THE REAL PIPELINE")
valid = list(HEADLINES.values())
clean = run(valid)
mixed = run(valid + [POISON])
ok(S.score_headline(POISON).get("error") is not None, "the injected headline really fails (error reported)")
ok(mixed.get("inference_failures") == 1, "it is counted", mixed.get("inference_failures"))
ok(abs(mixed["score"] - clean["score"]) < 2e-4 and abs(mixed["confidence"] - clean["confidence"]) < 2e-3,
   "score and coverage equal the run without it (no dilution, no inflated coverage)",
   f"{mixed['score']}/{mixed['confidence']} vs {clean['score']}/{clean['confidence']}")
ok(mixed["n_articles"] == clean["n_articles"] == len(valid), "only the real headlines are used")

print("\n3. EVERY HEADLINE FAILS")
allfail = run([POISON] * 3)
ok(allfail["confidence"] == 0.0 and allfail.get("reason") == "sentiment inference failed"
   and allfail.get("inference_failures") == 3, "sentiment is unavailable, with the reason", allfail.get("reason"))

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
