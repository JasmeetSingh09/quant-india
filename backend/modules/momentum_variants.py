"""
momentum_variants.py — does the skipped month earn its place?

PRE-REGISTRATION. The hypotheses, the family, the decision rule and the
statistics below were written and committed BEFORE the experiment was run. The
git history is the evidence: this file's first commit contains the declaration
and no results.

Why that matters here more than usual
-------------------------------------
This experiment exists because a STRONG BUY on SBIN lost money and the skipped
month was the suspected cause. That is a post-outcome hypothesis search, and
the honest way to run one is to say so, declare the whole family in advance,
correct for it, and refuse to promote whichever variant happens to win.

Momentum's measured edge on this archive already ranged from +0.01 to +23.23
depending only on methodology choice, and twelve walk-forward configurations
produced nothing surviving correction. The prior is that these four variants
are four draws from a noisy cloud, not four candidates one of which is right.

THE FAMILY (declared, complete, and closed)
-------------------------------------------
    A  252 / 21   the frozen V1.4 specification
    B  252 /  0   the proposed change: momentum sees the most recent month
    C  126 / 21   robustness on lookback, skip held
    D  126 /  0   robustness on both

Everything else is held identical by construction: one panel is loaded once and
all four variants read the same prices, the same formation dates, the same
eligible universe, the same liquidity floor, the same benchmark, the same cost
assumption, the same bucketing, the same horizons and the same missing-data
rule. The variants differ in two integers and nothing else.

THE DECISION RULE (declared before results)
--------------------------------------------
V1.4 is NOT changed unless a variant:

  1. beats A on the pre-declared primary statistic, AND
  2. survives Bonferroni correction across this family of four, AND
  3. holds its sign across regimes and across both horizons, AND
  4. does so on non-overlapping windows, not merely on overlapping ones.

A variant winning on point 1 alone is evidence worth investigating and nothing
more. A variant losing is also a result: it would be the first evidence that
the skip is doing something rather than merely being conventional.

WHAT THIS MODULE DOES NOT DO
-----------------------------
It does not modify V1.4, alpha_model, the frozen spec, or any constant the
scanner reads. It is read-only research. MOM_LOOKBACK and MOM_SKIP are imported
to define variant A so the baseline cannot drift from the shipped model.
"""

import math
from datetime import datetime

import numpy as np

# Variant A is read from the model rather than restated, so the baseline is the
# shipped specification by construction and cannot quietly disagree with it.
try:
    from pit_validation import MOM_LOOKBACK as _A_LOOKBACK, MOM_SKIP as _A_SKIP
except Exception:                                   # pragma: no cover
    _A_LOOKBACK, _A_SKIP = 252, 21

# (label, lookback_trading_days, skip_trading_days, description)
VARIANTS = [
    ("A_252_21", _A_LOOKBACK, _A_SKIP,
     "Frozen V1.4: 12-1, the most recent month excluded"),
    ("B_252_00", _A_LOOKBACK, 0,
     "Proposed: 12-0, momentum sees the most recent month"),
    ("C_126_21", 126, _A_SKIP,
     "Robustness: 6-month lookback, skip retained"),
    ("D_126_00", 126, 0,
     "Robustness: 6-month lookback, no skip"),
]

BASELINE = "A_252_21"
FAMILY_SIZE = len(VARIANTS)
ALPHA = 0.05
BONFERRONI_ALPHA = ALPHA / FAMILY_SIZE      # 0.0125

# The primary statistic, declared: mean monthly top-minus-bottom quintile spread
# in excess of the equal-weighted eligible universe, at a 1-month horizon.
# 3-month is reported as a secondary horizon for sign stability. Longer horizons
# are excluded because this archive cannot supply enough non-overlapping windows
# to test them, which was established before this experiment.
PRIMARY_HORIZON = 1
SECONDARY_HORIZON = 3
MIN_NONOVERLAPPING = 3

PRE_REGISTERED_AT = "declared before the experiment was run; see git history"


def _momentum(C, col, lookback, skip):
    """
    12-1 style momentum at one formation column, vectorised.

    Identical arithmetic to the shipped factor — return over the window divided
    by annualised volatility over the same window, through tanh — with only the
    window boundaries varying. skip=0 means the window runs to the formation
    day itself.
    """
    a = col - lookback
    b = col - skip
    if a < 0 or b <= a:
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        mom = C[:, b] / C[:, a] - 1.0
        win = C[:, a:b + 1]
        rets = win[:, 1:] / win[:, :-1] - 1.0
        vol = np.nanstd(rets, axis=1) * math.sqrt(252)
        risk_adj = np.where(vol > 1e-6, mom / np.where(vol > 1e-6, vol, 1.0), 0.0)
        score = np.tanh(risk_adj / 1.5)
    score[~np.isfinite(score)] = np.nan
    return score


def run(min_turnover: float = 1e7, n_buckets: int = 5) -> dict:
    """
    All four variants on one panel. Read-only.

    The panel is loaded once and shared, so the variants cannot differ by what
    they read — only by the two integers that define them.
    """
    try:
        from db import get_conn
        from pit_validation import (_load, _month_end_cols, _grade, _mean_test,
                                    COST_ROUNDTRIP_PCT)
        from security_identity import _pairs, _resolve_pairs
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}

    try:
        conn = get_conn()
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}"}
    try:
        pair_rows = _pairs(conn)
        canonical, _c, _l, _amb = _resolve_pairs(pair_rows)
        keys, days, C, V = _load(conn, canonical, pair_rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    me = _month_end_cols(days)
    months = [m for m, _ in me]
    cols = [c for _, c in me]
    if len(me) < 16:
        return {"available": False,
                "reason": f"Only {len(me)} months of files."}

    results, market_monthly = {}, {}

    for label, lookback, skip, desc in VARIANTS:
        form_ix = [i for i in range(len(me)) if cols[i] - lookback >= 0]
        per_h = {}
        for horizon in (PRIMARY_HORIZON, SECONDARY_HORIZON):
            spreads, months_used, bucket_rows = [], [], {b: [] for b in range(n_buckets)}
            for i in form_ix:
                j = i + horizon
                if j >= len(cols):
                    continue
                col = cols[i]
                mom = _momentum(C, col, lookback, skip)
                if mom is None:
                    continue
                px_now, px_next = C[:, col], C[:, cols[j]]
                liq = V[:, col]
                elig = (np.isfinite(px_now) & (px_now > 0) & np.isfinite(mom)
                        & (liq >= min_turnover))
                idx = np.where(elig)[0]
                if len(idx) < n_buckets * 10:
                    continue
                with np.errstate(invalid="ignore", divide="ignore"):
                    fwd = px_next[idx] / px_now[idx] - 1.0
                fwd = np.where(np.isfinite(fwd), fwd, -1.0)
                mkt = float(np.mean(fwd))
                exc = fwd - mkt

                order = np.argsort(mom[idx], kind="stable")
                nb = len(order)
                lab = np.minimum(n_buckets - 1, np.arange(nb) * n_buckets // nb)
                hi = exc[order[lab == n_buckets - 1]]
                lo = exc[order[lab == 0]]
                if len(hi) and len(lo):
                    spreads.append(float(np.mean(hi)) - float(np.mean(lo)))
                    months_used.append(months[i])
                for b in range(n_buckets):
                    sel = order[lab == b]
                    bucket_rows[b].extend(
                        (months[i], float(exc[k]), float(fwd[k])) for k in sel)
                if horizon == PRIMARY_HORIZON:
                    market_monthly.setdefault(months[i], mkt)

            test = _mean_test(spreads) if spreads else {"insufficient": True}
            non_overlap = len(spreads) // max(horizon, 1)
            test["non_overlapping_windows"] = non_overlap
            test["sufficient_independent_windows"] = non_overlap >= MIN_NONOVERLAPPING
            test["months_used"] = months_used
            per_h[f"{horizon}m"] = {
                "top_minus_bottom": test,
                "buckets": [_grade(bucket_rows[b], f"Q{b+1}", len(months_used),
                                   horizon) for b in range(n_buckets)],
                "monthly_spreads": [round(s * 100, 4) for s in spreads],
            }

        results[label] = {"lookback_days": lookback, "skip_days": skip,
                          "description": desc, "horizons": per_h}

    # ---------------- regime split on the primary horizon, from the PIT market
    ordered = sorted(market_monthly)
    regime_of = {}
    for pos, m in enumerate(ordered):
        if pos < 3:
            regime_of[m] = "Insufficient history"
            continue
        prior = [market_monthly[x] for x in ordered[pos - 3:pos]]
        cum = 1.0
        for r in prior:
            cum *= (1 + r)
        trend = (cum - 1) * 100
        regime_of[m] = ("Bull" if trend > 5 else "Bear" if trend < -5 else "Sideways")

    for label in results:
        prim = results[label]["horizons"].get(f"{PRIMARY_HORIZON}m", {})
        t = prim.get("top_minus_bottom", {})
        ms, sp = t.get("months_used") or [], prim.get("monthly_spreads") or []
        by_regime = {}
        for m, s in zip(ms, sp):
            by_regime.setdefault(regime_of.get(m, "Unknown"), []).append(s)
        results[label]["by_regime"] = {
            k: {"months": len(v), "mean_spread_pct": round(float(np.mean(v)), 3),
                "positive_months": sum(1 for x in v if x > 0)}
            for k, v in sorted(by_regime.items())}
        # Sign stability: does the spread point the same way everywhere it is
        # measured? A variant that wins on average by flipping sign between
        # regimes has not found an effect, it has found two effects cancelling.
        signs = [np.sign(v["mean_spread_pct"])
                 for k, v in results[label]["by_regime"].items()
                 if k != "Insufficient history" and v["months"] >= 2]
        h1 = t.get("mean_pct")
        h3 = (results[label]["horizons"].get(f"{SECONDARY_HORIZON}m", {})
              .get("top_minus_bottom", {}).get("mean_pct"))
        results[label]["sign_stability"] = {
            "regime_signs_agree": bool(signs) and len(set(signs)) == 1,
            "horizons_agree": (h1 is not None and h3 is not None
                               and np.sign(h1) == np.sign(h3)),
            "primary_mean_pct": h1, "secondary_mean_pct": h3,
        }

    # ---------------- the declared decision rule, applied
    base = results.get(BASELINE, {})
    base_mean = (base.get("horizons", {}).get(f"{PRIMARY_HORIZON}m", {})
                 .get("top_minus_bottom", {}).get("mean_pct"))
    verdicts = {}
    for label, r in results.items():
        t = (r["horizons"].get(f"{PRIMARY_HORIZON}m", {})
             .get("top_minus_bottom", {}))
        p = t.get("p_value")
        mean = t.get("mean_pct")
        beats = (label != BASELINE and mean is not None and base_mean is not None
                 and mean > base_mean)
        survives = p is not None and p < BONFERRONI_ALPHA
        stable = (r["sign_stability"]["regime_signs_agree"]
                  and r["sign_stability"]["horizons_agree"])
        independent = t.get("sufficient_independent_windows", False)
        verdicts[label] = {
            "beats_baseline": beats if label != BASELINE else None,
            "survives_bonferroni": survives,
            "sign_stable": stable,
            "enough_independent_windows": independent,
            "meets_decision_rule": bool(beats and survives and stable and independent),
        }

    promotable = [k for k, v in verdicts.items() if v["meets_decision_rule"]]

    return {
        "available": True,
        "pre_registration": {
            "family": [{"label": l, "lookback": lb, "skip": sk, "description": d}
                       for l, lb, sk, d in VARIANTS],
            "family_size": FAMILY_SIZE,
            "baseline": BASELINE,
            "primary_statistic": ("mean monthly top-minus-bottom quintile spread, "
                                  "excess of the equal-weighted eligible universe, "
                                  f"{PRIMARY_HORIZON}-month horizon"),
            "alpha": ALPHA,
            "bonferroni_alpha": BONFERRONI_ALPHA,
            "declared": PRE_REGISTERED_AT,
            "motivation_disclosed": (
                "This family was declared after a STRONG BUY on SBIN lost money "
                "and the skipped month was the suspected cause. That makes it a "
                "post-outcome hypothesis search, which is why the whole family "
                "is declared, corrected for, and closed — and why a winner is "
                "evidence to investigate rather than a model to ship."),
        },
        "variants": results,
        "verdicts": verdicts,
        "promotable_under_decision_rule": promotable,
        "conclusion": (
            f"No variant meets the pre-declared rule. V1.4 stands unchanged."
            if not promotable else
            f"{', '.join(promotable)} meets the pre-declared rule. That is "
            f"evidence worth investigating out-of-sample, NOT a validated "
            f"model: the family was chosen after an adverse outcome, and one "
            f"corrected pass over a single market period does not establish an "
            f"edge."),
        "universe": {"securities": len(keys), "trading_days": len(days),
                     "months_available": len(me), "liquidity_floor": min_turnover,
                     "cost_roundtrip_pct": COST_ROUNDTRIP_PCT},
        "limits": (
            "One market period, monthly rebalances, prices unadjusted for splits "
            "and dividends. The archive cannot supply enough non-overlapping "
            "windows beyond three months, so longer horizons are excluded rather "
            "than reported weakly. Nothing here establishes a durable edge for "
            "any variant, including the baseline."),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
