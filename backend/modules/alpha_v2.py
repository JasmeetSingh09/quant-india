"""
alpha_v2.py — the six-factor model, built to be compared rather than believed.

V1 uses four factors: momentum, sentiment, quality, value. V2 adds growth and
low-risk, and reweights the rest. It does NOT replace V1 — both are computed for
every stock, so the question "does the sixth factor help?" becomes something the
track record can answer instead of something a weighting asserts.

That matters because the honest state of the evidence is that V1 has not been
shown to work: 7 of 13 correct on independent windows, an interval spanning 29%
to 77%. Replacing an untested model with a bigger untested model would swap one
unknown for a larger one. Running both means that in a few weeks the log can say
which, if either, separated winners from losers.

Two design choices worth stating.

Weights are not equal, and they are configurable. Equal weighting is a claim
that every factor carries the same information, which nobody believes and no
evidence supports. These are a starting point to be tested, not a finding.

Liquidity is NOT a factor and never touches the score. Being liquid is not
attractiveness — nobody buys a stock because it trades often. It is an execution
constraint, reported beside the score, which keeps the architecture clean:

  Alpha          how attractive is this stock
  Risk           what can go wrong
  Portfolio fit  does it belong in THIS portfolio
  Execution      can you actually trade it

The scoring layer is only the first of those four.
"""

import numpy as np

# Starting weights, deliberately transparent and deliberately not equal. Equal
# weighting is a claim that every factor carries the same information, which
# nobody believes and no evidence supports.
#
# These are a STARTING point, not a finding. They are configurable so the app can
# eventually answer "why these weights?" with a comparison instead of a shrug.
WEIGHTS_V2 = {
    "momentum":  0.18,
    "quality":   0.22,
    "growth":    0.15,
    "value":     0.17,
    "sentiment": 0.10,
    "low_risk":  0.18,
}

# These changed once, on evidence rather than preference.
#
# Momentum fell from 25% to 18% because it is the ONLY factor that has been
# tested on this universe, and it failed: 12 walk-forward configurations across
# three horizons and two universe sizes produced no result surviving correction
# for multiple testing, sign flips between adjacent settings, and a gross spread
# smaller than trading costs in 7 of 12 cases. Giving the largest weight to the
# one factor measured and found wanting could not be defended.
#
# It is reduced rather than removed. A null on 42 windows of one market is not
# proof that momentum never works — it is a failure to demonstrate that it works
# here. Removing it would overclaim in the opposite direction.
#
# Sentiment fell from 15% to 10%: weakest published evidence at this horizon, and
# untested here.
#
# Low-risk rose to 18% because the low-volatility anomaly has the broadest
# replication record of anything in this model, though it too is untested here.
# Quality and value rose slightly for the same reason.
#
# None of this makes the model validated. It makes the weights consistent with
# what is known, which is a lower bar and the only one currently reachable.
WEIGHT_NOTES = {
    "momentum": "Strongest published record, and the only factor computed purely "
                "from prices — it never waits for a company to report.",
    "quality":  "Profitability and balance-sheet health. Also carries the distress "
                "veto that stops a nearly-insolvent company scoring as cheap.",
    "growth":   "Revenue and earnings growth. Weighted moderately because fast "
                "growth is rarely a secret — it tends to be in the price already.",
    "value":    "Cheapness against sector peers. Slow-acting, and can stay cheap "
                "for years.",
    "sentiment": "FinBERT on recent headlines. The weakest evidence base here at "
                 "this horizon; a candidate for reduction once the log can judge it.",
    "low_risk": "The low-volatility anomaly: calmer stocks have historically earned "
                "better risk-adjusted returns than their beta predicts.",
}

MODEL_VERSION_V2 = "alpha-v2-six-factor"


def _growth_factor(ticker: str) -> dict:
    """
    Revenue and earnings growth, scored against a plausible range.

    Growth is included with a caveat that applies to it more than to the others:
    it is the factor most prone to being already in the price. A company growing
    30% is rarely a secret. It earns a moderate weight for that reason.
    """
    try:
        from data_fetcher import get_info
        info = get_info(ticker) or {}
        rev_g = info.get("revenueGrowth")
        earn_g = info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")

        parts, wsum = [], 0.0
        if rev_g is not None:
            # +/-30% revenue growth spans most of the real distribution.
            parts.append((0.5, float(np.tanh(float(rev_g) / 0.30))))
            wsum += 0.5
        if earn_g is not None:
            parts.append((0.5, float(np.tanh(float(earn_g) / 0.50))))
            wsum += 0.5
        if not parts:
            return {"score": 0.0, "confidence": 0.0, "reason": "no growth data"}

        raw = sum(w * v for w, v in parts) / wsum
        return {
            "score": round(max(-1.0, min(1.0, raw)), 4),
            "confidence": round(0.85 * wsum, 3),
            "revenue_growth": rev_g,
            "earnings_growth": earn_g,
            "reason": ("Revenue and earnings growth against a normal range. Fast "
                       "growth is rarely a secret, so this is weighted moderately."),
        }
    except Exception as e:
        return {"score": 0.0, "confidence": 0.0, "reason": str(e)}


def _low_risk_factor(ticker: str) -> dict:
    """
    The low-volatility anomaly: calmer stocks have historically earned better
    risk-adjusted returns than their beta would predict.

    Scored so that LOW volatility is POSITIVE. This is the factor most likely to
    disagree with momentum, which is exactly why it is worth having — a model
    whose factors always agree is one factor wearing several hats.
    """
    try:
        from datetime import datetime, timedelta
        import yfinance as yf
        end = datetime.now()
        start = end - timedelta(days=400)
        df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                         end=end.strftime("%Y-%m-%d"), progress=False,
                         auto_adjust=True)
        if df is None or len(df) < 60:
            return {"score": 0.0, "confidence": 0.0, "reason": "insufficient history"}
        close = df["Close"]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        rets = close.pct_change().dropna()
        if len(rets) < 60:
            return {"score": 0.0, "confidence": 0.0, "reason": "insufficient returns"}

        ann_vol = float(rets.std() * np.sqrt(252))
        # Worst peak-to-trough over the window.
        curve = (1 + rets).cumprod()
        drawdown = float((curve / curve.cummax() - 1).min())

        # 20% annualised volatility is unremarkable for an Indian equity; 60% is
        # extreme. Below 20 scores positive, above scores negative.
        vol_score = float(np.tanh((0.20 - ann_vol) / 0.20))
        dd_score = float(np.tanh((0.25 + drawdown) / 0.25))   # drawdown is negative

        raw = 0.6 * vol_score + 0.4 * dd_score
        return {
            "score": round(max(-1.0, min(1.0, raw)), 4),
            "confidence": round(min(1.0, 0.5 + len(rets) / 500), 3),
            "annual_volatility_pct": round(ann_vol * 100, 1),
            "max_drawdown_pct": round(drawdown * 100, 1),
            "reason": (f"Annualised volatility {ann_vol*100:.0f}%, worst drawdown "
                       f"{drawdown*100:.0f}%. Calmer stocks score higher — the "
                       f"low-volatility anomaly is among the best-documented "
                       f"effects in equities."),
        }
    except Exception as e:
        return {"score": 0.0, "confidence": 0.0, "reason": str(e)}


def compute_v2(ticker: str, v1_result: dict = None) -> dict:
    """
    Six-factor score. Reuses V1's momentum, quality, value and sentiment rather
    than recomputing them, so the two models differ ONLY by the added factors and
    the reweighting — which is what makes a comparison between them meaningful.
    """
    from alpha_model import compute_alpha_score

    v1 = v1_result or compute_alpha_score(ticker)
    if not v1 or "error" in v1:
        return {"error": (v1 or {}).get("error", "V1 unavailable"), "ticker": ticker}

    f = v1.get("factors") or {}
    growth = _growth_factor(ticker)
    low_risk = _low_risk_factor(ticker)

    factors = {
        "momentum":  f.get("momentum", {}),
        "quality":   f.get("quality", {}),
        "value":     f.get("value", {}),
        "growth":    growth,
        "low_risk":  low_risk,
        "sentiment": f.get("sentiment", {}),
    }

    # Weight only what actually has data, then rescale — otherwise a missing
    # factor silently drags the score toward zero and looks like a bearish view.
    contributions, used_w = {}, 0.0
    raw = 0.0
    for name, weight in WEIGHTS_V2.items():
        fac = factors.get(name) or {}
        sc = fac.get("score")
        conf = fac.get("confidence", 0) or 0
        if sc is None or conf <= 0:
            contributions[name] = None
            continue
        raw += weight * float(sc)
        used_w += weight
        contributions[name] = round(weight * float(sc) * 100, 2)

    if used_w <= 0:
        return {"error": "No factor had usable data.", "ticker": ticker}

    alpha = round(raw / used_w * 100, 2)

    # Liquidity stays OUTSIDE the alpha score. It is an execution constraint, not
    # attractiveness — nobody buys a stock because it trades often. Folding it in
    # would blur the architecture the rest of the app depends on:
    #   Alpha = how attractive        Risk = what can go wrong
    #   Portfolio fit = does it belong    Execution = can you actually trade it
    liq = None
    try:
        from liquidity import assess, label
        a = assess(ticker) or {}
        liq = {"tier": a.get("tier"), "daily_value_label": label(a.get("daily_value")),
               "tradeable": a.get("tradeable"), "note": a.get("note")}
    except Exception:
        liq = None

    if alpha > 40:      signal = "STRONG BUY"
    elif alpha > 15:    signal = "BUY"
    elif alpha < -40:   signal = "STRONG SELL"
    elif alpha < -15:   signal = "SELL"
    else:               signal = "NEUTRAL"

    coverage = round(used_w / sum(WEIGHTS_V2.values()), 3)

    return {
        "ticker": ticker,
        "model_version": MODEL_VERSION_V2,
        "alpha_score": alpha,
        "signal": signal,
        "factors": factors,
        "contributions": contributions,
        "weights_used": WEIGHTS_V2,
        "factor_coverage": coverage,
        "liquidity": liq,
        "horizon_days": 21,
        "evidence_status": "experimental",
        "evidence_note": (
            "This model has NOT been shown to predict returns. Its largest tested "
            "factor, momentum, did not demonstrate a statistically significant "
            "edge across 12 walk-forward configurations after correcting for "
            "multiple testing. That is a result about this implementation on "
            "this universe, not a claim that momentum never works. Treat every "
            "score as a research output, not a recommendation."),
        "score_scale": {"range": [-100, 100],
                        "means": "Model preference, not a predicted return."},
        # The comparison is the point of running both.
        "v1_score": v1.get("alpha_score"),
        "v1_signal": v1.get("signal"),
        "disagreement": (round(alpha - (v1.get("alpha_score") or 0), 2)),
        "note": ("Six factors against V1's four, with growth and low-risk added "
                 "and sentiment reduced from 25% to 8%. Both models run on every "
                 "stock so the track record can eventually say which is better — "
                 "neither has been shown to work yet."),
    }


# How each factor reads in words, and what would break it. The score is the
# finding; this is what makes the finding usable by someone who does not already
# know what a factor model is.
FACTOR_PLAIN = {
    "momentum":  ("Recent price trend",
                  "Momentum can reverse quickly, especially after a sharp run-up."),
    "quality":   ("Profitability and financial health",
                  "Reported figures lag reality by a quarter."),
    "growth":    ("Revenue and earnings growth",
                  "Fast growth is often already in the price."),
    "value":     ("Cheapness against peers",
                  "Cheap can stay cheap for years, and sometimes it is cheap for a reason."),
    "sentiment": ("Tone of recent news",
                  "Headlines move faster than businesses; this is the noisiest input here."),
    "low_risk":  ("Volatility and drawdown",
                  "A calm history is not a promise of a calm future."),
}


def explain(v2: dict) -> dict:
    """
    What the model agrees on, what holds the stock back, and one sentence.

    Six bars ask the reader to do the synthesis themselves. Most will not, and
    those who try will weight them by eye. The sentence is the part that actually
    gets read, so it is generated from the same numbers rather than written to
    sound reassuring — it cannot drift more positive than the score supports.
    """
    if not v2 or "error" in v2:
        return {}
    contrib = {k: v for k, v in (v2.get("contributions") or {}).items() if v is not None}
    if not contrib:
        return {}

    weights = v2.get("weights_used") or WEIGHTS_V2
    rows = []
    for k, v in contrib.items():
        cap = weights.get(k, 0) * 100
        rows.append({
            "factor": k,
            "label": FACTOR_PLAIN.get(k, (k, ""))[0],
            "points": v,
            "max_points": round(cap, 1),
            # Share of what this factor COULD have contributed, so factors that
            # do not share a scale can still be compared by eye.
            "fill_pct": (round(max(0.0, min(1.0, (v + cap) / (2 * cap))) * 100, 0)
                         if cap else 50.0),
            "positive": v > 0,
            "risk_note": FACTOR_PLAIN.get(k, ("", ""))[1],
        })
    rows.sort(key=lambda r: -r["points"])

    pos = [r for r in rows if r["points"] > 0]
    neg = [r for r in rows if r["points"] < 0]
    name = v2["ticker"].replace(".NS", "")

    if pos and neg:
        lead = ", ".join(r["label"].lower() for r in pos[:2])
        verb = "are" if len(pos[:2]) > 1 else "is"
        # neg inherits the descending sort, so neg[0] is the MILDEST negative.
        # Naming that as "the main thing holding it back" understated the real
        # problem and disagreed with biggest_concern two lines below.
        worst_neg = neg[-1]
        sentence = (f"{name} scores as it does because {lead} {verb} favourable. "
                    f"{worst_neg['label']} is the main thing holding it back.")
    elif pos:
        sentence = (f"{name} scores positively on every factor with data, led by "
                    f"{pos[0]['label'].lower()}.")
    elif neg:
        sentence = (f"{name} scores poorly on every factor with data, worst on "
                    f"{neg[0]['label'].lower()}.")
    else:
        sentence = f"{name} is neutral on every measured factor."

    # The teaching cases: cheap-but-weak, and good-but-expensive.
    lesson = None
    cv, qv, gv = contrib.get("value"), contrib.get("quality"), contrib.get("growth")
    if cv is not None and cv > 0 and (qv or 0) < 0 and (gv or 0) < 0:
        lesson = ("Cheap does not mean good. This looks inexpensive, but weak "
                  "quality and growth are why — the discount may be deserved.")
    elif cv is not None and cv < 0 and (qv or 0) > 0 and (gv or 0) > 0:
        lesson = ("Good does not mean cheap. The business scores well on quality "
                  "and growth, and the market has noticed — you are paying for it.")

    weakest = rows[-1] if rows else None
    return {
        "rows": rows,
        "n_positive": len(pos),
        "n_total": len(rows),
        "strongest": rows[0]["label"] if rows else None,
        "biggest_concern": (weakest["label"]
                            if weakest and weakest["points"] < 0 else None),
        "sentence": sentence,
        "lesson": lesson,
        "what_could_change_it": (weakest["risk_note"]
                                 if weakest and weakest["risk_note"] else None),
        "caveat": ("This explains why the model scored the stock as it did. It is "
                   "not evidence the score predicts anything — the track record "
                   "is the only thing that can say that."),
    }
