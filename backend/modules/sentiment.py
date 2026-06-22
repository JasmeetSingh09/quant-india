"""
sentiment.py — FinBERT-based sentiment analysis for Indian stock news.

Uses ProsusAI/finbert to score headlines as positive / negative / neutral
with a confidence percentage.  Sentiment is intentionally kept separate from
news fetching so each module has a single responsibility.

Key functions:
  score_headline(text)          → {label, confidence, scores}
  score_headlines_batch(texts)  → list of score dicts
  summarise_sentiment(articles) → {overall, breakdown, trend, …}
"""

from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# FinBERT pipeline — downloaded on first run (~400 MB), then cached locally.
# Auto-detects an NVIDIA GPU (CUDA) and uses it; falls back to CPU otherwise.
# On an RTX 4070 Super this runs ~25x faster than CPU.
import torch
from transformers import pipeline as hf_pipeline

_DEVICE = 0 if torch.cuda.is_available() else -1   # 0 = first GPU, -1 = CPU
_DEVICE_NAME = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
print(f"Loading FinBERT model on {_DEVICE_NAME} (first run downloads ~400 MB)...")

_finbert = hf_pipeline(
    "text-classification",
    model="ProsusAI/finbert",
    top_k=None,          # return all three sentiment scores
    device=_DEVICE,      # GPU if available, else CPU
)
print(f"FinBERT loaded on {_DEVICE_NAME}.")


# ---------------------------------------------------------------------------
# Core scoring
# ---------------------------------------------------------------------------

def score_headline(text: str) -> dict:
    """
    Run FinBERT on a single piece of text.

    Returns:
      label      — "positive", "negative", or "neutral"
      confidence — float 0-1, how confident the model is
      scores     — dict with all three scores
    """
    try:
        text = text[:512]   # FinBERT max token window
        results = _finbert(text)[0]
        best = max(results, key=lambda x: x["score"])
        return {
            "label": best["label"],
            "confidence": round(best["score"], 4),
            "confidence_pct": round(best["score"] * 100, 1),
            "scores": {r["label"]: round(r["score"], 4) for r in results},
        }
    except Exception as e:
        return {
            "label": "neutral",
            "confidence": 0.0,
            "confidence_pct": 0.0,
            "scores": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            "error": str(e),
        }


def score_headlines_batch(texts: list[str]) -> list[dict]:
    """
    Score a list of headline strings.  Returns a list in the same order.
    Batching through the pipeline is more efficient than calling
    score_headline in a loop for large lists.
    """
    if not texts:
        return []

    truncated = [t[:512] for t in texts]
    try:
        raw = _finbert(truncated)
        results = []
        for item in raw:
            best = max(item, key=lambda x: x["score"])
            results.append({
                "label": best["label"],
                "confidence": round(best["score"], 4),
                "confidence_pct": round(best["score"] * 100, 1),
                "scores": {r["label"]: round(r["score"], 4) for r in item},
            })
        return results
    except Exception as e:
        # Fall back to one-by-one
        return [score_headline(t) for t in texts]


# ---------------------------------------------------------------------------
# Summary & trend
# ---------------------------------------------------------------------------

def summarise_sentiment(articles: list[dict], title_key: str = "title") -> dict:
    """
    Summarise sentiment across a list of article dicts.

    Each article must have the field named by title_key (default "title").
    If articles already carry a "sentiment" key they are used directly;
    otherwise FinBERT is run on the title.

    Returns:
      overall_sentiment    — dominant label
      sentiment_breakdown  — counts per label
      positive/negative/neutral_pct
      average_confidence
      trend                — "improving", "worsening", or "stable"
                             (compares first half vs second half)
      most_positive_headline
      most_negative_headline
      scored_articles      — articles enriched with sentiment fields
    """
    if not articles:
        return {"error": "No articles provided"}

    scored = []
    for art in articles:
        a = dict(art)
        if "sentiment" not in a or "confidence" not in a:
            s = score_headline(a.get(title_key, ""))
            a["sentiment"] = s["label"]
            a["confidence"] = s["confidence"]
            a["sentiment_scores"] = s["scores"]
        scored.append(a)

    pos = [a for a in scored if a["sentiment"] == "positive"]
    neg = [a for a in scored if a["sentiment"] == "negative"]
    neu = [a for a in scored if a["sentiment"] == "neutral"]
    total = len(scored)

    overall = "neutral"
    if len(pos) > len(neg) and len(pos) > len(neu):
        overall = "positive"
    elif len(neg) > len(pos) and len(neg) > len(neu):
        overall = "negative"

    avg_conf = sum(a["confidence"] for a in scored) / total

    # Trend: compare sentiment score in first half vs second half
    def _sentiment_score(label: str) -> int:
        return 1 if label == "positive" else (-1 if label == "negative" else 0)

    mid = total // 2
    first_half_score = sum(_sentiment_score(a["sentiment"]) for a in scored[:mid]) if mid else 0
    second_half_score = sum(_sentiment_score(a["sentiment"]) for a in scored[mid:]) if mid else 0
    if total < 4:
        trend = "stable"
    elif second_half_score > first_half_score:
        trend = "improving"
    elif second_half_score < first_half_score:
        trend = "worsening"
    else:
        trend = "stable"

    most_positive  = max(pos, key=lambda x: x["confidence"]) if pos else None
    most_negative  = max(neg, key=lambda x: x["confidence"]) if neg else None

    return {
        "overall_sentiment": overall,
        "total_articles": total,
        "sentiment_breakdown": {
            "positive": len(pos),
            "negative": len(neg),
            "neutral":  len(neu),
        },
        "positive_pct":      round(len(pos) / total * 100, 1),
        "negative_pct":      round(len(neg) / total * 100, 1),
        "neutral_pct":       round(len(neu) / total * 100, 1),
        "average_confidence": round(avg_conf, 4),
        "trend":             trend,
        "most_positive_headline": most_positive[title_key] if most_positive else None,
        "most_negative_headline": most_negative[title_key] if most_negative else None,
        "scored_articles":   scored,
    }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Testing sentiment.py")
    print("=" * 60)

    test_headlines = [
        "Reliance Industries posts record quarterly profit, beats estimates",
        "Indian markets crash as FIIs sell heavily amid global recession fears",
        "RBI holds interest rates steady in latest MPC meeting",
        "TCS wins $2 billion deal from European banking consortium",
        "HDFC Bank reports higher NPA ratio, misses profit forecast",
    ]

    print("\n1. Scoring individual headlines:")
    for h in test_headlines:
        s = score_headline(h)
        print(f"\n   {h}")
        print(f"   → {s['label'].upper()}  ({s['confidence_pct']}% confident)")
        print(f"      +{s['scores'].get('positive', 0):.3f}  "
              f"-{s['scores'].get('negative', 0):.3f}  "
              f"~{s['scores'].get('neutral', 0):.3f}")

    print("\n2. Batch scoring:")
    batch = score_headlines_batch(test_headlines)
    print(f"   Scored {len(batch)} headlines in batch")
    for h, s in zip(test_headlines, batch):
        print(f"   {s['label']:8s} ({s['confidence_pct']:5.1f}%)  {h[:55]}")

    print("\n3. Summary across articles:")
    articles = [{"title": h} for h in test_headlines]
    summary = summarise_sentiment(articles)
    print(f"   Overall:     {summary['overall_sentiment']}")
    print(f"   Breakdown:   {summary['sentiment_breakdown']}")
    print(f"   Avg conf:    {summary['average_confidence']}")
    print(f"   Trend:       {summary['trend']}")
    print(f"   Most +ve:    {summary['most_positive_headline']}")
    print(f"   Most -ve:    {summary['most_negative_headline']}")

    print("\n" + "=" * 60)
    print("sentiment.py test complete")
    print("=" * 60)
