"""
sentiment_zero_weight_test.py — years-old headlines are "no recent news", never NaN (v1.6.2).

For some symbols the news source returns 2017 chart pages despite the 14-day
window. Each weighs exp(-ln2/3 * age) = 0.0, the weighted average was 0/0 = NaN,
and the NaN emptied the composite into a NULL score labelled NEUTRAL (36 rows,
13 stocks by 2026-11-16). docs/PROPOSAL_SENTIMENT_ZERO_WEIGHT_2026-11-17.md
(owner-approved). This checks:

  1. all-ancient headlines give score 0, confidence 0, reason "no recent headlines";
  2. one recent headline among them is still scored as before;
  3. a composite that is not a number is an error, never NEUTRAL;
  4. the spec records both rules, so the change is visible to the drift check.

Offline: news, FinBERT and the price/fundamental factors are stubbed.

    cd backend && python tests/sentiment_zero_weight_test.py
"""
import math
import os
import sys
import types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("QUANT_DATA_DIR", os.environ.get("TEMP", "/tmp"))
os.environ.pop("DATABASE_URL", None)

_news = types.ModuleType("news")
_news.get_stock_news = lambda ticker, days_back=14: []
sys.modules["news"] = _news
_sent = types.ModuleType("sentiment")
_sent.score_headline = lambda title: {"label": "positive", "confidence": 0.9}
sys.modules["sentiment"] = _sent

import alpha_model as AM                                      # noqa: E402
import strategy_version as SV                                 # noqa: E402

PASS = FAIL = 0


def ok(cond, label, detail=""):
    global PASS, FAIL
    PASS += bool(cond)
    FAIL += not cond
    print(f"  {'PASS' if cond else 'FAIL'}  {label}  {'' if cond else detail}")


OLD = [{"title": "NCLIND Stock Price and Chart — NSE:NCLIND", "published_at": "2017-07-22T07:15:21"},
       {"title": "NCL Industries (NSEI:NCLIND) - Stock Analysis", "published_at": "2017-12-01T14:33:45"}]

print("\n1. ONLY YEARS-OLD HEADLINES")
_news.get_stock_news = lambda ticker, days_back=14: OLD
r = AM._compute_sentiment_factor("NCLIND.NS")
ok(r["score"] == 0.0 and r["confidence"] == 0.0, "score 0 and confidence 0, not NaN", str(r))
ok(r.get("reason") == "no recent headlines", "reason says no recent headlines", str(r.get("reason")))
ok(r.get("stale_articles") == 2 and len(r.get("articles_used", [])) == 2,
   "the stale headlines are still recorded", str(r))

print("\n2. A RECENT HEADLINE STILL COUNTS")
recent = (datetime.utcnow() - timedelta(days=1)).isoformat()
_news.get_stock_news = lambda ticker, days_back=14: OLD + [{"title": "NCL wins order", "published_at": recent}]
r = AM._compute_sentiment_factor("NCLIND.NS")
ok(math.isfinite(r["score"]) and r["score"] > 0 and r.get("n_articles") == 3,
   "scored as before, positive, from all three", str({k: r.get(k) for k in ("score", "n_articles", "reason")}))

print("\n3. A NON-NUMBER COMPOSITE IS AN ERROR")
real = {n: getattr(AM, n) for n in ("_compute_sentiment_factor", "_compute_momentum_factor",
                                    "_compute_quality_factor", "_compute_value_factor", "_ticker_info")}
try:
    AM._compute_sentiment_factor = lambda t: {"score": float("nan"), "confidence": 0.0}
    AM._compute_momentum_factor = lambda t, p=None: {"score": 0.1, "confidence": 1.0}
    AM._compute_quality_factor = lambda t: {"score": 0.2, "confidence": 1.0}
    AM._compute_value_factor = lambda t, p=None: {"score": 0.3, "confidence": 1.0}
    AM._ticker_info = lambda t: {"marketCap": 1e9}
    r = AM.compute_alpha_score("NCLIND.NS")
    ok("error" in r and "not a number" in r["error"] and "sentiment" in r["error"],
       "an error naming the factor, not a NEUTRAL row", str(r)[:200])
    ok(r.get("signal") is None and r.get("alpha_score") is None, "no signal or score is emitted", str(r)[:200])
finally:
    for n, f in real.items():
        setattr(AM, n, f)

print("\n4. THE SPEC RECORDS IT")
spec = SV.current_spec()
sm = spec.get("sentiment_model") or {}
ok("zero_weight_policy" in sm and "non_finite_policy" in sm, "both rules are in the spec", str(list(sm)))
ok(AM.MODEL_VERSION.startswith("v1.6.2"), "the model stamp is v1.6.2", AM.MODEL_VERSION)

print(f"\nTOTAL: {PASS + FAIL}  FAILURES: {FAIL}")
sys.exit(1 if FAIL else 0)
