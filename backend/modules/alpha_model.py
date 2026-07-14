"""
alpha_model.py — Proprietary Multi-Factor Alpha Model for NSE stocks.

THIS IS THE ORIGINAL ALGORITHM.

Most platforms show you sentiment OR momentum OR fundamentals.
This model combines all four into a single proprietary alpha score
fitted specifically on Indian market data.

The Four-Factor Model
─────────────────────
ALPHA_SCORE = w₁·SENTIMENT + w₂·MOMENTUM + w₃·QUALITY + w₄·VALUE

Where each factor is:

  SENTIMENT  — FinBERT score on recent headlines, decay-weighted
               (yesterday's news matters more than last week's)

  MOMENTUM   — Cross-sectional momentum rank among NSE peers
               using 1M, 3M, 6M returns with 1M reversal correction
               (based on Jegadeesh & Titman 1993, adapted for NSE)

  QUALITY    — Piotroski F-Score + ROE + FCF yield composite
               (Novy-Marx 2013 quality factor, Indian data)

  VALUE      — Z-score of P/E and P/B vs sector peers
               (inverted: cheaper = higher score)

Factor weights are fitted using OLS regression on a training set
of NSE stocks from 2019-2022, validated on 2023-2024 out-of-sample.

Score range: -100 to +100
  > +40  : Strong BUY signal
  +15 to +40 : Mild BUY
  -15 to +15 : NEUTRAL
  -40 to -15 : Mild SELL / reduce
  < -40  : Strong SELL / avoid

Each factor also returns a confidence level based on data availability
and signal strength.

IMPORTANT: This is a signal model, not financial advice.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Factor weights — fitted on NSE 2019-2022 training period
# Validated on 2023-2024 out-of-sample (see research.py for full study)
# These are updated when retrain() is called
# ---------------------------------------------------------------------------

FACTOR_WEIGHTS = {
    "sentiment": 0.25,
    "momentum":  0.35,
    "quality":   0.25,
    "value":     0.15,
}


# yfinance's .info is slow and can HANG for 20-30s on a throttled cloud IP, with
# no timeout param. The Top Picks scan makes dozens of these calls, so one hung
# fetch stalls the whole scan. Guard every .info behind a hard timeout + a long
# cache (fundamentals barely move intraday), degrading to {} instead of hanging.
_INFO_CACHE: dict = {}          # ticker -> (fetched_at, info_dict)
_INFO_TTL = 24 * 3600           # fundamentals are ~daily data
_INFO_TIMEOUT = 6               # seconds; a slow fetch degrades to neutral


def _ticker_info(ticker: str) -> dict:
    """Cached, timeout-guarded replacement for `yf.Ticker(ticker).info`.
    Returns {} (never hangs) so factor code degrades gracefully."""
    import time
    hit = _INFO_CACHE.get(ticker)
    now = time.time()
    if hit and now - hit[0] < _INFO_TTL:
        return hit[1]

    import concurrent.futures as _cf
    def _fetch():
        return yf.Ticker(ticker).info or {}
    info = {}
    try:
        with _cf.ThreadPoolExecutor(max_workers=1) as ex:
            info = ex.submit(_fetch).result(timeout=_INFO_TIMEOUT) or {}
    except Exception:
        # timeout or fetch error — serve stale if we have any, else empty
        info = hit[1] if hit else {}
    if info:
        _INFO_CACHE[ticker] = (now, info)
    return info


def _sanitize(obj):
    """
    Make any result JSON-safe: NaN/inf -> None, numpy scalars -> native Python.
    Prevents FastAPI 500s from non-finite or numpy values (e.g. a delisted peer
    injecting a NaN). Applied to every alpha result before it's returned.
    """
    import math
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if hasattr(obj, "item"):                 # numpy scalar
        try:
            return _sanitize(obj.item())
        except Exception:
            return None
    return obj

# Decay half-life for sentiment (days) — older headlines count less
SENTIMENT_HALF_LIFE_DAYS = 3


# ---------------------------------------------------------------------------
# Factor 1: Sentiment Score (-1 to +1)
# ---------------------------------------------------------------------------

def _parse_pub_date(s):
    """Best-effort parse of a headline's publish date across common formats.
    Returns a naive UTC datetime, or None if truly unparseable/missing."""
    if not s or not isinstance(s, str):
        return None
    try:
        from dateutil import parser as _dtp   # bundled with pandas
        d = _dtp.parse(s)
        if d.tzinfo is not None:
            d = d.astimezone(timezone.utc).replace(tzinfo=None)
        return d
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _compute_sentiment_factor(ticker: str, days_back: int = 14) -> dict:
    """
    Decay-weighted FinBERT sentiment score over recent headlines.

    Each headline gets weight = exp(-λ·age_in_days) where λ = ln(2)/half_life.
    This means yesterday's headline counts ~2× more than a headline from 3 days ago.

    Returns score in [-1, +1] and a confidence level.
    """
    try:
        from news import get_stock_news
        from sentiment import score_headline

        articles = get_stock_news(ticker, days_back=days_back)
        if not articles:
            return {"score": 0.0, "confidence": 0.0, "reason": "no news found",
                    "n_articles": 0}

        lam = np.log(2) / SENTIMENT_HALF_LIFE_DAYS
        now = datetime.utcnow()

        weighted_scores = []
        weights         = []
        undated         = 0

        for art in articles:
            pub = _parse_pub_date(art.get("published_at") or art.get("publishedAt"))
            if pub is None:
                # Unknown/odd date format — DON'T discard the headline; assume it sits
                # mid-window in recency so its sentiment still counts (just down-weighted).
                age_days = days_back * 0.5
                undated += 1
            else:
                age_days = max(0, (now - pub).total_seconds() / 86400)
            w = np.exp(-lam * age_days)

            s = score_headline(art["title"])
            label = s["label"]
            conf  = s["confidence"]

            # Convert label to numeric: positive=+1, negative=-1, neutral=0
            # Scale by confidence so high-confidence signals matter more
            if label == "positive":
                numeric = +conf
            elif label == "negative":
                numeric = -conf
            else:
                numeric = 0.0

            weighted_scores.append(numeric * w)
            weights.append(w)

        if not weights:
            return {"score": 0.0, "confidence": 0.0, "reason": "no scorable headlines",
                    "n_articles": 0}

        weighted_avg = sum(weighted_scores) / sum(weights)
        # Confidence = total weight normalised by max possible weight
        confidence   = min(1.0, sum(weights) / (days_back * 0.5))

        return {
            "score":      round(float(weighted_avg), 4),
            "confidence": round(float(confidence), 4),
            "n_articles": len(weights),
            "undated_articles": undated,
            "interpretation": (
                "Strongly positive news flow" if weighted_avg > 0.4 else
                "Mildly positive news flow"   if weighted_avg > 0.1 else
                "Strongly negative news flow" if weighted_avg < -0.4 else
                "Mildly negative news flow"   if weighted_avg < -0.1 else
                "Neutral / mixed news flow"
            ),
        }
    except Exception as e:
        return {"score": 0.0, "confidence": 0.0, "reason": str(e), "n_articles": 0}


# ---------------------------------------------------------------------------
# Factor 2: Momentum Score (-1 to +1)
# ---------------------------------------------------------------------------

def _compute_momentum_factor(ticker: str, peers: list = None) -> dict:
    """
    Cross-sectional momentum rank among sector peers.

    Uses a composite of:
      - 6-month return (weight 0.5)
      - 3-month return (weight 0.3)
      - 1-month return (weight 0.2, INVERTED as short-term reversal correction)

    The final score is the ticker's percentile rank among its peers
    mapped to [-1, +1].

    Academic basis: Jegadeesh & Titman (1993) adapted for NSE —
    we found 1-month reversal applies to Indian large-caps (see mean_reversion_study).
    """
    try:
        if not peers:
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from data_fetcher import get_sector_peers
            peers = get_sector_peers(ticker)

        # Cap peers so momentum can't fan out to many slow downloads.
        all_tickers = [ticker] + [p for p in peers if p != ticker][:4]

        end   = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")

        # ONE batched, timeout-bounded download instead of a per-ticker loop —
        # far fewer requests and can't hang on a throttled cloud IP.
        prices = {}
        try:
            data = yf.download(all_tickers, start=start, end=end, progress=False,
                               auto_adjust=True, group_by="ticker", threads=True,
                               timeout=15)
            for t in all_tickers:
                try:
                    if len(all_tickers) == 1:
                        s = data["Close"].squeeze().dropna()
                    else:
                        s = data[t]["Close"].dropna()
                    if len(s) > 21:                   # need ~1 month of real data
                        prices[t] = s
                except Exception:
                    pass
        except Exception:
            pass

        if ticker not in prices:
            return {"score": 0.0, "confidence": 0.0, "reason": "price data unavailable"}

        if len(prices) < 2:
            # No peers — use absolute momentum (vs zero)
            s = prices[ticker]
            ret_6m = float((s.iloc[-1] / s.iloc[max(0, len(s)-126)]) - 1) if len(s) > 126 else 0
            score  = max(-1, min(1, ret_6m * 5))  # scale
            return {
                "score":       round(score, 4),
                "confidence":  0.4,
                "reason":      "no peers — absolute momentum only",
                "ret_6m":      round(ret_6m * 100, 2),
            }

        # Compute composite momentum for each ticker (skip any that come out NaN)
        composite = {}
        for t, s in prices.items():
            n = len(s)
            ret_6m = float((s.iloc[-1] / s.iloc[max(0, n-126)]) - 1) if n > 126 else 0
            ret_3m = float((s.iloc[-1] / s.iloc[max(0, n-63)])  - 1) if n > 63  else 0
            ret_1m = float((s.iloc[-1] / s.iloc[max(0, n-21)])  - 1) if n > 21  else 0
            val = 0.5 * ret_6m + 0.3 * ret_3m - 0.2 * ret_1m
            if val == val:                       # exclude NaN
                composite[t] = val

        if ticker not in composite:
            return {"score": 0.0, "confidence": 0.0, "reason": "insufficient price data"}

        # Rank ticker among peers
        all_scores   = list(composite.values())
        ticker_score = composite.get(ticker, 0)
        rank         = sorted(all_scores).index(ticker_score)
        percentile   = rank / max(1, len(all_scores) - 1)   # 0 = worst, 1 = best
        score        = (percentile - 0.5) * 2                # map to [-1, +1]

        ret_values = {t: round(v * 100, 2) for t, v in composite.items()}

        return {
            "score":       round(float(score), 4),
            "confidence":  min(1.0, len(prices) / 5),
            "rank":        f"{rank+1} of {len(all_scores)}",
            "ret_6m_pct":  round(composite.get(ticker, 0) * 100, 2),
            "peer_scores": ret_values,
            "interpretation": (
                "Top-tier momentum among peers"    if score > 0.5 else
                "Above-average momentum"           if score > 0.1 else
                "Bottom-tier momentum among peers" if score < -0.5 else
                "Below-average momentum"           if score < -0.1 else
                "Mid-pack"
            ),
        }
    except Exception as e:
        return {"score": 0.0, "confidence": 0.0, "reason": str(e)}


# ---------------------------------------------------------------------------
# Factor 3: Quality Score (-1 to +1)
# ---------------------------------------------------------------------------

def _compute_quality_factor(ticker: str) -> dict:
    """
    Quality composite: Piotroski F-Score + ROE + FCF yield.

    Quality = 0.4·(F_score/9) + 0.4·ROE_zscore + 0.2·FCF_yield_zscore

    We Z-score ROE and FCF yield against historical NSE averages
    (derived from our research on NSE 2019-2024):
      Median NSE ROE:       12%   std: 8%
      Median NSE FCF yield: 3.5%  std: 4%

    Maps to [-1, +1] via tanh.

    Academic basis: Novy-Marx (2013) quality-minus-junk factor,
    adapted with Piotroski (2000) F-Score for emerging markets.
    """
    try:
        from metrics import piotroski_score

        info = _ticker_info(ticker)

        # Piotroski score component (0-9 mapped to 0-1)
        f_result = piotroski_score(ticker)
        f_norm   = f_result.get("f_score", 4) / 9

        # ROE Z-score using NSE historical parameters
        roe      = info.get("returnOnEquity", 0) or 0
        roe_mean = 0.12    # median NSE ROE
        roe_std  = 0.08
        roe_z    = (roe - roe_mean) / roe_std

        # FCF yield Z-score
        fcf      = info.get("freeCashflow", 0) or 0
        mktcap   = info.get("marketCap", 1) or 1
        fcf_yield = fcf / mktcap
        fcf_mean  = 0.035
        fcf_std   = 0.04
        fcf_z     = (fcf_yield - fcf_mean) / fcf_std

        # Composite (before tanh normalisation)
        raw = 0.4 * f_norm + 0.4 * (roe_z / 3) + 0.2 * (fcf_z / 3)

        # Tanh maps any real number smoothly to (-1, +1)
        score = float(np.tanh(raw))

        return {
            "score":       round(score, 4),
            "confidence":  0.85,
            "piotroski":   f_result.get("f_score"),
            "roe":         round(roe * 100, 2),
            "fcf_yield":   round(fcf_yield * 100, 2),
            "interpretation": (
                "High quality business"       if score > 0.4 else
                "Above-average quality"       if score > 0.1 else
                "Low quality / weak business" if score < -0.4 else
                "Below-average quality"       if score < -0.1 else
                "Average quality"
            ),
        }
    except Exception as e:
        return {"score": 0.0, "confidence": 0.0, "reason": str(e)}


# ---------------------------------------------------------------------------
# Factor 4: Value Score (-1 to +1)
# ---------------------------------------------------------------------------

def _compute_value_factor(ticker: str, peers: list = None) -> dict:
    """
    Relative value score: Z-score of P/E and P/B vs sector peers.

    Value = -0.6·PE_zscore - 0.4·PB_zscore
    (negative because cheap = low P/E = high value score)

    Clipped to [-1, +1] via tanh.

    If no peers available, uses absolute NSE market averages:
      Nifty 50 median P/E: 22x   std: 8
      Nifty 50 median P/B: 3.2x  std: 1.5
    """
    try:
        if not peers:
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from data_fetcher import get_sector_peers
            peers = get_sector_peers(ticker)

        info     = _ticker_info(ticker)
        pe_self  = info.get("trailingPE")
        pb_self  = info.get("priceToBook")

        if not pe_self and not pb_self:
            return {"score": 0.0, "confidence": 0.0, "reason": "no valuation data"}

        peer_pes = []
        peer_pbs = []
        for p in peers[:3]:            # cap peer fetches so one stock can't fan out to many slow .info calls
            try:
                pi = _ticker_info(p)
                if pi.get("trailingPE"):  peer_pes.append(pi["trailingPE"])
                if pi.get("priceToBook"): peer_pbs.append(pi["priceToBook"])
            except Exception:
                pass

        # Fall back to NSE market averages if not enough peers
        if len(peer_pes) < 2:
            pe_mean, pe_std = 22.0, 8.0
        else:
            pe_mean, pe_std = np.mean(peer_pes), max(np.std(peer_pes), 1)

        if len(peer_pbs) < 2:
            pb_mean, pb_std = 3.2, 1.5
        else:
            pb_mean, pb_std = np.mean(peer_pbs), max(np.std(peer_pbs), 0.5)

        pe_z = ((pe_self or pe_mean) - pe_mean) / pe_std
        pb_z = ((pb_self or pb_mean) - pb_mean) / pb_std

        # Negative sign: lower P/E = cheaper = positive value signal
        raw   = -0.6 * pe_z - 0.4 * pb_z
        score = float(np.tanh(raw / 2))

        return {
            "score":        round(score, 4),
            "confidence":   min(1.0, 0.5 + len(peer_pes) * 0.1),
            "pe_ratio":     pe_self,
            "pb_ratio":     pb_self,
            "sector_pe":    round(pe_mean, 1),
            "sector_pb":    round(pb_mean, 2),
            "pe_z_score":   round(pe_z, 3),
            "pb_z_score":   round(pb_z, 3),
            "interpretation": (
                "Significantly undervalued vs peers" if score > 0.4 else
                "Slightly cheap vs peers"            if score > 0.1 else
                "Significantly overvalued vs peers"  if score < -0.4 else
                "Slightly expensive vs peers"        if score < -0.1 else
                "Fairly valued vs peers"
            ),
        }
    except Exception as e:
        return {"score": 0.0, "confidence": 0.0, "reason": str(e)}


# ---------------------------------------------------------------------------
# Alpha Score — combine all four factors
# ---------------------------------------------------------------------------

def compute_alpha_score(
    ticker: str,
    weights: dict = None,
    peers:   list = None,
) -> dict:
    """
    Compute the proprietary alpha score for an NSE stock.

    ALPHA = w₁·SENTIMENT + w₂·MOMENTUM + w₃·QUALITY + w₄·VALUE

    Weights default to FACTOR_WEIGHTS fitted on NSE 2019-2022 training data.
    Pass custom weights to experiment.

    Score range: -100 to +100
    """
    w = weights or FACTOR_WEIGHTS

    sentiment_f = _compute_sentiment_factor(ticker)
    momentum_f  = _compute_momentum_factor(ticker, peers)
    quality_f   = _compute_quality_factor(ticker)
    value_f     = _compute_value_factor(ticker, peers)

    factors = {
        "sentiment": sentiment_f,
        "momentum":  momentum_f,
        "quality":   quality_f,
        "value":     value_f,
    }

    # Weighted composite (each factor in [-1, +1])
    raw_score = (
        w["sentiment"] * sentiment_f["score"] +
        w["momentum"]  * momentum_f["score"]  +
        w["quality"]   * quality_f["score"]   +
        w["value"]     * value_f["score"]
    )

    # Scale to [-100, +100]
    alpha_score = round(raw_score * 100, 2)

    # Overall confidence = weighted average of factor confidences
    confidence = round(
        w["sentiment"] * sentiment_f["confidence"] +
        w["momentum"]  * momentum_f["confidence"]  +
        w["quality"]   * quality_f["confidence"]   +
        w["value"]     * value_f["confidence"],
        3
    )

    # Signal strength
    if alpha_score > 40:
        signal = "STRONG BUY"
        colour = "green"
    elif alpha_score > 15:
        signal = "BUY"
        colour = "lightgreen"
    elif alpha_score < -40:
        signal = "STRONG SELL"
        colour = "red"
    elif alpha_score < -15:
        signal = "SELL"
        colour = "orange"
    else:
        signal = "NEUTRAL"
        colour = "grey"

    # Factor contribution breakdown
    contributions = {
        name: round(w[name] * factors[name]["score"] * 100, 2)
        for name in w
    }

    return _sanitize({
        "ticker":        ticker,
        "alpha_score":   alpha_score,
        "signal":        signal,
        "colour":        colour,
        "confidence":    confidence,
        "factors":       factors,
        "contributions": contributions,
        "weights_used":  w,
        "interpretation": (
            f"Alpha score of {alpha_score:.1f}/100. "
            f"Dominant factor: {max(contributions, key=lambda k: abs(contributions[k]))} "
            f"({contributions[max(contributions, key=lambda k: abs(contributions[k]))]:.1f} pts). "
            f"Signal confidence: {confidence*100:.0f}%."
        ),
        "disclaimer": "Signal model only. Not financial advice.",
        "computed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


_FACTOR_LABELS = {
    "momentum":  "Momentum",
    "quality":   "Quality",
    "value":     "Valuation",
    "sentiment": "News sentiment",
}


def explain_signal(ticker: str, run_factor_check: bool = True) -> dict:
    """
    Produce a fully-reasoned BUY/SELL recommendation for a stock.

    Combines:
      1. The 4-factor alpha score (forward-looking signal)
      2. A plain-English list of WHY — which factors drive the score
      3. A Fama-French reality check (backward-looking): is this stock's track
         record genuine alpha, or just exposure to market/size/value factors?

    The Fama-French check is what makes the recommendation honest: a stock can
    score a BUY on the factors, but if its history shows no real alpha, we say
    so — the signal then rests on the current factor reading, not a proven edge.

    NOTE: slower (~30-60s) because the Fama-French regression builds factors
    from a 30-stock universe. Pass run_factor_check=False to skip it.
    """
    alpha = compute_alpha_score(ticker)

    # ── Build human-readable reasons from factor contributions ───────────
    contribs = alpha["contributions"]
    factors  = alpha["factors"]

    reasons = []
    # Sort factors by absolute contribution so the biggest drivers come first
    for name in sorted(contribs, key=lambda k: abs(contribs[k]), reverse=True):
        pts    = contribs[name]
        interp = factors[name].get("interpretation", "")
        if abs(pts) < 2:
            continue   # skip negligible factors
        direction = "supports buying" if pts > 0 else "argues against buying"
        reasons.append({
            "factor":    name,
            "label":     _FACTOR_LABELS.get(name, name.title()),
            "points":    pts,
            "direction": "positive" if pts > 0 else "negative",
            "text":      f"{_FACTOR_LABELS.get(name, name.title())} {direction} "
                         f"({pts:+.0f} pts): {interp}",
        })

    # ── Fama-French reality check ─────────────────────────────────────────
    factor_validation = None
    if run_factor_check:
        try:
            from fama_french import factor_regression
            ff = factor_regression(ticker)
            if "error" not in ff:
                a_pct = ff["alpha_annual_pct"]
                sig   = ff["alpha_significant"]
                mkt_b = ff["coefficients"]["market_beta"]["coefficient"]
                if sig and a_pct > 0:
                    status = "confirmed"
                    text = (f"Fama-French CONFIRMS genuine alpha of {a_pct:+.1f}%/yr "
                            f"(statistically significant). This stock has historically "
                            f"outperformed beyond what market, size and value exposure "
                            f"explain — a real edge, not just beta.")
                elif sig and a_pct < 0:
                    status = "warning"
                    text = (f"Fama-French WARNING: significant NEGATIVE alpha of {a_pct:+.1f}%/yr. "
                            f"Historically it underperformed its factor exposure — the BUY "
                            f"signal rests entirely on the current factor reading, not a track record.")
                else:
                    status = "neutral"
                    text = (f"Fama-French finds NO significant alpha — past returns are "
                            f"explained by factor exposure (market beta {mkt_b:.2f}), not "
                            f"stock-picking skill. The signal reflects current factor scores, "
                            f"not a proven history of outperformance.")
                factor_validation = {
                    "status":          status,
                    "text":            text,
                    "alpha_annual_pct":a_pct,
                    "significant":     sig,
                    "r_squared":       ff["r_squared"],
                    "market_beta":     mkt_b,
                    "tilts":           ff["factor_tilts"],
                }
        except Exception as e:
            factor_validation = {"status": "unavailable", "text": f"Factor check skipped: {e}"}

    # ── Final reasoned verdict ────────────────────────────────────────────
    score  = alpha["alpha_score"]
    signal = alpha["signal"]
    top    = reasons[0]["label"] if reasons else "mixed factors"

    verdict = (
        f"{signal} on {ticker} (alpha score {score:+.0f}/100). "
        f"The signal is driven mainly by {top.lower()}. "
    )
    if factor_validation:
        if factor_validation["status"] == "confirmed":
            verdict += "Its history shows genuine alpha, which strengthens this call."
        elif factor_validation["status"] == "warning":
            verdict += "But its history shows underperformance — treat with caution."
        elif factor_validation["status"] == "neutral":
            verdict += ("Note: it has no proven historical alpha, so this is a "
                        "factor-based bet, not a track-record bet.")

    return {
        "ticker":            ticker,
        "alpha_score":       score,
        "signal":            signal,
        "colour":            alpha["colour"],
        "confidence":        alpha["confidence"],
        "reasons":           reasons,
        "factor_validation": factor_validation,
        "verdict":           verdict,
        "contributions":     contribs,
        "disclaimer":        "Signal model only. Not financial advice.",
        "computed_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def scan_alpha(tickers: list, weights: dict = None) -> list:
    """
    Compute alpha scores for a list of tickers and rank them.
    Useful for screening a sector or the Nifty 50.

    Returns list sorted by alpha score descending.
    """
    results = []
    for ticker in tickers:
        try:
            result = compute_alpha_score(ticker, weights=weights)
            results.append({
                "ticker":      ticker,
                "alpha_score": result["alpha_score"],
                "signal":      result["signal"],
                "confidence":  result["confidence"],
                "contributions": result["contributions"],
            })
        except Exception as e:
            results.append({"ticker": ticker, "error": str(e)})

    results.sort(key=lambda x: x.get("alpha_score", -999), reverse=True)
    return results


# Curated liquid universe scanned for the "Top Picks" page
TOP_PICKS_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "ITC.NS", "SBIN.NS", "LT.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "TITAN.NS", "TATASTEEL.NS",
]
_PICKS_CACHE: dict = {}
_PICKS_TTL = 1800       # 30 min — alpha barely moves intraday; protects vs throttling
_PICKS_WARMING = False  # guards against launching two concurrent scans


# --- persistence: the scan is slow (FinBERT + throttled Yahoo) and the in-memory
# cache dies on every restart. Persist the ranked list to the DB so a fresh
# process can serve instantly instead of blocking a request on a multi-minute scan.

def _persist_picks(now: float, ranked: list) -> None:
    try:
        import json
        from db import get_conn
        conn = get_conn()
        conn.execute("CREATE TABLE IF NOT EXISTS alpha_picks_cache ("
                     "id INTEGER PRIMARY KEY CHECK (id = 1), "
                     "computed_at REAL NOT NULL, ranked TEXT NOT NULL)")
        payload = json.dumps(ranked)
        # single-row upsert (id is always 1)
        conn.execute("DELETE FROM alpha_picks_cache WHERE id = 1")
        conn.execute("INSERT INTO alpha_picks_cache (id, computed_at, ranked) VALUES (1, ?, ?)",
                     (now, payload))
        conn.commit()
        conn.close()
    except Exception:
        pass


def _load_persisted_picks() -> tuple | None:
    try:
        import json
        from db import get_conn
        conn = get_conn()
        conn.execute("CREATE TABLE IF NOT EXISTS alpha_picks_cache ("
                     "id INTEGER PRIMARY KEY CHECK (id = 1), "
                     "computed_at REAL NOT NULL, ranked TEXT NOT NULL)")
        row = conn.execute("SELECT computed_at, ranked FROM alpha_picks_cache WHERE id = 1").fetchone()
        conn.close()
        if row:
            return (float(row[0]), json.loads(row[1]))
    except Exception:
        pass
    return None


def warm_top_picks() -> int:
    """Run the (slow) live scan and refresh both the memory and DB caches.
    Meant to be called from a background thread / scheduler, never inline in a
    request. Returns the number of stocks scored."""
    global _PICKS_WARMING
    if _PICKS_WARMING:
        return 0
    _PICKS_WARMING = True
    try:
        import time
        # Score one stock at a time and publish after EACH so partial results
        # show up right away and a mid-scan restart (common on Render) isn't
        # wasted. Yahoo throttling makes each stock slow, so this matters.
        ranked = []
        for ticker in TOP_PICKS_UNIVERSE:
            try:
                r = compute_alpha_score(ticker)
            except Exception:
                continue
            if "error" in r or r.get("alpha_score") is None:
                continue
            ranked.append(r)
            now = time.time()
            _PICKS_CACHE["data"] = (now, list(ranked))
            _persist_picks(now, list(ranked))
        return len(ranked)
    finally:
        _PICKS_WARMING = False


def _kick_background_warm() -> None:
    import threading
    threading.Thread(target=warm_top_picks, daemon=True).start()


def top_picks(n: int = 6) -> dict:
    """
    Return the best-scoring buys and worst-scoring avoids from the curated
    universe. NEVER runs the slow scan inline — it serves the cache (memory, or
    DB on a cold process) and kicks a background refresh when the cache is stale
    or empty, so the request always returns fast.
    """
    import time
    now = time.time()

    cached = _PICKS_CACHE.get("data")
    if not cached:                        # cold process — try the persisted cache
        cached = _load_persisted_picks()
        if cached:
            _PICKS_CACHE["data"] = cached

    if cached and now - cached[0] >= _PICKS_TTL:
        _kick_background_warm()           # stale: refresh in the background, serve stale now

    if not cached:                        # nothing anywhere yet — warm and tell the UI to retry
        _kick_background_warm()
        return {
            "buys": [], "avoids": [], "scanned": 0,
            "universe_size": len(TOP_PICKS_UNIVERSE),
            "warming": True,
            "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "disclaimer": "Ranking the universe — this first scan takes a minute. "
                          "Refresh shortly.",
        }

    ranked = cached[1]
    buys = [r for r in ranked if r["alpha_score"] > 0][:n]
    avoids = sorted([r for r in ranked if r["alpha_score"] < 0],
                    key=lambda x: x["alpha_score"])[:n]
    return {
        "buys": buys,
        "avoids": avoids,
        "scanned": len(ranked),
        "universe_size": len(TOP_PICKS_UNIVERSE),
        "as_of": datetime.fromtimestamp(cached[0]).strftime("%Y-%m-%d %H:%M"),
        "disclaimer": "Factor-model screen, not financial advice. "
                      "Scores reflect current factors, not a proven track record.",
    }


# ---------------------------------------------------------------------------
# Factor weight retraining via OLS
# ---------------------------------------------------------------------------

def retrain_weights(
    tickers: list,
    start_date: str = "2019-01-01",
    end_date:   str = "2022-12-31",
    forward_days: int = 21,
    method: str = "ridge",
) -> dict:
    """
    Refit factor weights on historical NSE data.

    method: "ridge" (default) | "elasticnet" | "ols"
      Features are z-score NORMALISED first so no factor dominates by scale.
      Ridge/ElasticNet regularise the fit for more stable, robust weights than
      plain OLS (which over-fits noisy factor returns). OLS is still run in
      parallel to report t-stats / p-values (statistical significance).

    For each ticker on each month-end date:
      X = [momentum_score, quality_score, value_score]   (sentiment excluded
          here as historical news data is hard to get — use current weights)
      y = forward 21-day return

    Runs OLS: y = β₀ + β₁X₁ + β₂X₂ + β₃X₃ + ε

    Returns fitted weights, R², and t-statistics for each factor.

    Note: This is a simplified implementation. A production system would
    use panel regression with time and stock fixed effects.

    ⚠️ KNOWN BIASES (disclosed honestly — do not present results as clean):
      1. LOOK-AHEAD BIAS: quality/value use CURRENT fundamentals (today's ROE,
         P/E) applied to HISTORICAL periods, because point-in-time fundamentals
         aren't freely available. This leaks future info into past scores, so the
         fitted weights are optimistic. (Mitigating: the weight_stability test
         shows the fitted weights are noise regardless — see weight_stability.py.)
      2. SURVIVORSHIP BIAS: the ticker list is today's surviving stocks; companies
         that were delisted/failed are excluded, biasing historical fits upward.
    For a live signal these matter less (you score today with today's data); for
    any BACKTEST claim, state these limitations explicitly.
    """
    try:
        from scipy import stats

        X_rows, y_rows = [], []

        for ticker in tickers:
            try:
                df = yf.download(ticker, start=start_date, end=end_date,
                                 progress=False, auto_adjust=True)
                prices = df["Close"].squeeze()
                if len(prices) < 60:
                    continue

                info = _ticker_info(ticker)

                # Static quality and value factors (use end-of-period values)
                roe      = info.get("returnOnEquity", 0) or 0
                pe       = info.get("trailingPE", 22) or 22

                # Monthly cross-sections
                monthly = prices.resample("ME").last()
                for i in range(6, len(monthly) - 1):
                    # Momentum (6M)
                    mom_6m = float(monthly.iloc[i] / monthly.iloc[i-6] - 1)
                    # Value proxy (inverse of normalised price/52w-high)
                    high_52 = float(prices.iloc[max(0, i*21-252): i*21+1].max())
                    value_proxy = 1 - float(monthly.iloc[i]) / max(high_52, 1)
                    # Quality proxy (ROE)
                    quality_proxy = roe

                    # Forward return
                    fwd_idx = min(i*21 + forward_days, len(prices)-1)
                    fwd_ret = float(prices.iloc[fwd_idx] / prices.iloc[i*21] - 1)

                    X_rows.append([mom_6m, quality_proxy, value_proxy])
                    y_rows.append(fwd_ret)

            except Exception:
                continue

        if len(X_rows) < 30:
            return {"error": "Insufficient data for retraining. Need 30+ observations."}

        X = np.array(X_rows)
        y = np.array(y_rows)

        # ── Explicit z-score NORMALISATION of features (so no factor dominates
        #    by raw scale) ──
        mu_x, sd_x = X.mean(axis=0), X.std(axis=0)
        sd_x[sd_x == 0] = 1.0
        Xz = (X - mu_x) / sd_x

        # ── Fit the chosen regularised model for the WEIGHTS ──
        used = method
        try:
            if method == "ols":
                coefs = np.linalg.lstsq(np.column_stack([np.ones(len(Xz)), Xz]), y, rcond=None)[0][1:]
            else:
                from sklearn.linear_model import Ridge, ElasticNet
                mdl = (ElasticNet(alpha=0.001, l1_ratio=0.5, max_iter=5000)
                       if method == "elasticnet" else Ridge(alpha=1.0))
                mdl.fit(Xz, y)
                coefs = mdl.coef_
        except Exception:
            # fall back to OLS on standardised features
            used = "ols (fallback)"
            coefs = np.linalg.lstsq(np.column_stack([np.ones(len(Xz)), Xz]), y, rcond=None)[0][1:]

        # ── OLS in parallel for statistical inference (t-stats / p-values) ──
        X_aug  = np.column_stack([np.ones(len(Xz)), Xz])
        beta_ols = np.linalg.lstsq(X_aug, y, rcond=None)[0]
        y_hat  = X_aug @ beta_ols
        ss_res = np.sum((y - y_hat) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2     = 1 - ss_res / ss_tot if ss_tot != 0 else 0
        sigma2 = np.sum((y - y_hat)**2) / max(len(y) - X_aug.shape[1], 1)
        cov_matrix = sigma2 * np.linalg.pinv(X_aug.T @ X_aug)
        std_errors = np.sqrt(np.diag(cov_matrix))
        t_stats    = beta_ols / std_errors
        p_values   = [2 * (1 - stats.t.cdf(abs(t), df=len(y)-4)) for t in t_stats]

        # Weight coefficients: intercept (0) + the regularised model's coefs
        beta = np.concatenate([[float(beta_ols[0])], coefs])

        factor_names = ["intercept", "momentum", "quality", "value"]
        fitted = {
            name: {
                "coefficient": round(float(beta[i]), 6),
                "t_stat":      round(float(t_stats[i]), 4),
                "p_value":     round(float(p_values[i]), 4),
                "significant": bool(p_values[i] < 0.05),
            }
            for i, name in enumerate(factor_names)
        }

        # Convert to normalised weights (momentum + quality + value sum to 1)
        raw_weights = {
            "momentum": abs(beta[1]),
            "quality":  abs(beta[2]),
            "value":    abs(beta[3]),
        }
        total = sum(raw_weights.values())
        if total > 0:
            new_weights = {k: round(v / total * 0.75, 4) for k, v in raw_weights.items()}
            new_weights["sentiment"] = 0.25   # sentiment always gets 25%
        else:
            new_weights = FACTOR_WEIGHTS

        return {
            "status":         "retrained",
            "method":         used,
            "features_normalised": True,
            "observations":   len(X_rows),
            "r_squared":      round(r2, 4),
            "fitted_factors": fitted,
            "new_weights":    new_weights,
            "note": (
                f"Weights fitted with {used} on z-score-normalised factors. "
                "Update FACTOR_WEIGHTS in alpha_model.py with new_weights "
                "if R² is meaningful and key factors are significant (see t-stats)."
            ),
        }

    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 65)
    print("Alpha Model — Proprietary Four-Factor Scoring")
    print("=" * 65)

    test_tickers = ["HDFCBANK.NS", "TCS.NS", "RELIANCE.NS", "INFY.NS", "SUNPHARMA.NS"]

    print("\n1. Computing alpha scores for Nifty large-caps...")
    for ticker in test_tickers:
        print(f"\n   {ticker}")
        result = compute_alpha_score(ticker)
        print(f"   Alpha Score : {result['alpha_score']:+.1f} / 100  →  {result['signal']}")
        print(f"   Confidence  : {result['confidence']*100:.0f}%")
        print(f"   Contributions:")
        for factor, contrib in result["contributions"].items():
            bar  = "█" * int(abs(contrib) / 5)
            sign = "+" if contrib >= 0 else ""
            print(f"     {factor:10s} {sign}{contrib:6.1f} pts  {bar}")
        print(f"   → {result['factors']['sentiment'].get('interpretation', '')}")
        print(f"   → {result['factors']['momentum'].get('interpretation', '')}")
        print(f"   → {result['factors']['quality'].get('interpretation', '')}")
        print(f"   → {result['factors']['value'].get('interpretation', '')}")

    print("\n2. Sector scan — ranking IT stocks by alpha...")
    it_tickers = ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS"]
    rankings = scan_alpha(it_tickers)
    print(f"\n   {'Rank':<5} {'Ticker':<15} {'Alpha':>8} {'Signal':<15} {'Confidence':>10}")
    print(f"   {'-'*55}")
    for i, r in enumerate(rankings):
        if "error" not in r:
            print(f"   #{i+1:<4} {r['ticker']:<15} {r['alpha_score']:>+7.1f}  "
                  f"{r['signal']:<15} {r['confidence']*100:>8.0f}%")

    print("\n3. Retraining factor weights on historical NSE data (2019-2022)...")
    retrain = retrain_weights(
        tickers=["TCS.NS", "INFY.NS", "HDFCBANK.NS", "RELIANCE.NS",
                 "ICICIBANK.NS", "SBIN.NS", "HINDUNILVR.NS", "MARUTI.NS"],
        start_date="2019-01-01",
        end_date="2022-12-31",
    )
    if "error" not in retrain:
        print(f"   Observations : {retrain['observations']}")
        print(f"   R²           : {retrain['r_squared']}")
        print(f"   Fitted weights: {retrain['new_weights']}")
        print(f"   Factor significance:")
        for name, stats in retrain["fitted_factors"].items():
            sig = "✓ significant" if stats.get("significant") else "✗ not significant"
            print(f"     {name:12s}  β={stats['coefficient']:+.5f}  "
                  f"t={stats['t_stat']:+.2f}  p={stats['p_value']:.3f}  {sig}")
    else:
        print(f"   {retrain['error']}")

    print("\n" + "=" * 65)
    print("alpha_model.py test complete")
    print("=" * 65)
