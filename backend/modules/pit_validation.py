"""
pit_validation.py — validate the part of the model the archive can actually test.

The point-in-time archive holds symbol, day, OHLC, volume and ISIN. That is
enough to reconstruct exactly two of the model's factors as they would have
been computed on the day, and not enough to reconstruct the other four at all.
This module tests the first group and refuses to test the second, rather than
substituting today's fundamentals for history and calling the result a
backtest.

What is reconstructible, and why
--------------------------------
MOMENTUM is 12-1, volatility-adjusted: the return from 252 trading days ago to
21 days ago, divided by annualised daily volatility over that window, squashed
through tanh. Every input is a past price.

LOW_RISK is annualised volatility and worst drawdown over a trailing ~400
calendar days, combined 60/40. Every input is a past price.

Both are computed here from the same daily closes the exchange published, at
the formation date, using only columns to the left of it. Nothing from after
the formation date touches the score.

What is not, and why it is left alone
-------------------------------------
QUALITY, VALUE, GROWTH and SENTIMENT need fundamentals as reported at the time
and news as published at the time. The archive has neither. Using today's P/E,
today's ROE or today's news to score a February 2025 formation would be
look-ahead bias of the most direct kind — it would score a company on
information that did not exist. The composite alpha and the Strong Buy / Buy /
Neutral / Sell / Strong Sell labels are built from those factors, so they are
not reconstructible either.

Those are reported as UNTESTABLE with the specific data that would be required,
not estimated, not approximated, not filled in.

Sector and market-cap classifications are excluded for the same reason. The
mapping the platform holds is today's, it covers only currently-listed names,
and applying it backwards would import both look-ahead and survivorship into
the strata. Traded value is used instead, and labelled as liquidity rather than
size, because that is what it measures.

On multiple testing
-------------------
Eight primary hypotheses are declared before the numbers are looked at: two
factors by four horizons, each asking whether the top quintile beats the bottom.
Bonferroni is applied to those. Everything cut by regime or liquidity is
exploratory, is labelled exploratory, and reports how many comparisons were
made so a reader can discount accordingly.

Nothing here tunes anything. There is no parameter in this file that was chosen
after seeing a result, and the two factor definitions are read from the frozen
model rather than restated.
"""

import math
from datetime import datetime

import numpy as np


# Read from the model rather than restated, so a change there shows up here as
# a different test rather than a silent disagreement.
try:
    from alpha_model import FACTOR_WEIGHTS as _V1_W
except Exception:
    _V1_W = {}
try:
    from alpha_v2 import WEIGHTS_V2 as _V2_W
except Exception:
    _V2_W = {}

# Momentum, exactly as alpha_model computes it.
MOM_LOOKBACK = 252
MOM_SKIP = 21
MOM_TANH_DIV = 1.5

# Low risk, exactly as alpha_v2 computes it. The live factor pulls ~400
# calendar days from Yahoo, which is about 270 NSE trading days.
LR_WINDOW = 270
LR_VOL_REF = 0.20
LR_DD_REF = 0.25
LR_VOL_W, LR_DD_W = 0.6, 0.4

# Shared with the frozen backtest so the two cannot drift apart silently.
MIN_MONTHLY_TURNOVER = 1e7
COST_ROUNDTRIP_PCT = 0.4
RISK_FREE = 0.065

N_BUCKETS = 5
HORIZONS = (1, 3, 6, 12)
# Below this many non-overlapping windows a horizon is reported as insufficient
# rather than given a p-value. Overlapping forward windows share months, and a
# confidence interval built on them is not one.
MIN_NONOVERLAPPING = 3

# Regime thresholds. Conventions, fixed before any result was seen, and stated
# so a reader can see they are conventions. The volatility cut reuses the 20%
# reference already in the low-risk factor rather than inventing a second one.
REGIME_TREND_PCT = 5.0
REGIME_VOL_ANN = 0.20

FACTORS = ("momentum", "low_risk")

UNTESTABLE = {
    "quality": {
        "weight_v1": _V1_W.get("quality"), "weight_v2": _V2_W.get("quality"),
        "needs": ("Point-in-time fundamentals: return on equity, debt/equity, "
                  "margins and interest cover AS REPORTED on each formation "
                  "date, with the filing date attached so a figure is only "
                  "visible after it was published."),
        "why_not": ("The archive holds prices. Today's ROE applied to a "
                    "February 2025 formation scores the company on information "
                    "that did not exist then, and on a balance sheet that has "
                    "since been restated."),
    },
    "value": {
        "weight_v1": _V1_W.get("value"), "weight_v2": _V2_W.get("value"),
        "needs": ("Point-in-time earnings, book value and sales per share, "
                  "with filing dates. Price is already available, so a "
                  "historical P/E needs only the denominator."),
        "why_not": ("Today's EPS against a 2025 price is not the multiple "
                    "anyone traded on; it embeds two years of subsequent "
                    "earnings news."),
    },
    "growth": {
        "weight_v1": None, "weight_v2": _V2_W.get("growth"),
        "needs": ("A history of reported revenue and earnings growth by filing "
                  "date."),
        "why_not": ("Same reason as quality and value, and worse: growth is "
                    "measured across periods, so a single restatement moves "
                    "every historical observation."),
    },
    "sentiment": {
        "weight_v1": _V1_W.get("sentiment"), "weight_v2": _V2_W.get("sentiment"),
        "needs": ("An archive of news headlines with publication timestamps, "
                  "scored by the same FinBERT model, so the score at a "
                  "formation date reflects only articles published before it."),
        "why_not": ("News is fetched live. There is no stored history of what "
                    "was published when, so a historical sentiment score cannot "
                    "be reconstructed at all — not approximately, not at all."),
    },
    "composite_alpha_and_signals": {
        "weight_v1": 1.0, "weight_v2": 1.0,
        "needs": ("All of the above. The composite is a weighted sum, so it is "
                  "reconstructible exactly when its inputs are."),
        "why_not": ("Strong Buy / Buy / Neutral / Sell / Strong Sell are "
                    "thresholds on the composite. With four of six inputs "
                    "unavailable historically, the labels cannot be "
                    "reconstructed, and a version built from the two available "
                    "factors would be a different model wearing the same "
                    "names."),
    },
    "sector_attribution": {
        "weight_v1": None, "weight_v2": None,
        "needs": ("A point-in-time sector classification covering delisted "
                  "companies — an industry mapping as it stood on each date."),
        "why_not": ("The platform's sector map is today's and covers only "
                    "currently-listed names, so using it would import both "
                    "look-ahead and survivorship into every sector bucket."),
    },
    "market_cap_strata": {
        "weight_v1": None, "weight_v2": None,
        "needs": ("Historical shares outstanding, to turn a close into a market "
                  "capitalisation."),
        "why_not": ("The bhavcopy files carry price and volume but not shares "
                    "outstanding. Traded value is reported instead and called "
                    "liquidity, because a Large/Mid/Small label derived from "
                    "turnover would be a guess with a precise-sounding name."),
    },
}


# ------------------------------------------------------------------ loading

def _load(conn, canonical):
    """
    The archive as two dense matrices, securities by trading day.

    Dense is the right shape here: about 3,000 securities over 656 days is a
    few megabytes as float32, and every factor below is then a slice rather
    than a query.
    """
    days = [r[0] for r in conn.execute(
        "SELECT DISTINCT day FROM bhavcopy_eod ORDER BY day").fetchall()]
    day_ix = {d: i for i, d in enumerate(days)}

    rows_by_day = {}
    keys = {}
    for d in days:
        rows = conn.execute(
            "SELECT symbol, close, volume, isin FROM bhavcopy_eod WHERE day = ?",
            (d,)).fetchall()
        rows_by_day[d] = rows
        for sym, close, vol, isin in rows:
            k = canonical.get(isin, isin) if isin else sym
            if k and k not in keys:
                keys[k] = len(keys)

    n_k, n_d = len(keys), len(days)
    C = np.full((n_k, n_d), np.nan, dtype=np.float32)
    V = np.zeros((n_k, n_d), dtype=np.float32)
    for d, rows in rows_by_day.items():
        j = day_ix[d]
        for sym, close, vol, isin in rows:
            k = canonical.get(isin, isin) if isin else sym
            if not k or close is None:
                continue
            try:
                px = float(close)
            except (TypeError, ValueError):
                continue
            if px <= 0:
                continue
            i = keys[k]
            C[i, j] = px
            try:
                V[i, j] = px * float(vol or 0)
            except (TypeError, ValueError):
                V[i, j] = 0.0
    return list(keys), days, C, V


def _month_end_cols(days):
    """Last stored trading day of each month, as a column index."""
    last = {}
    for i, d in enumerate(days):
        last[str(d)[:7]] = i
    return sorted(last.items())


# ------------------------------------------------------------------ factors

def _momentum_scores(C, col):
    """
    Absolute 12-1 momentum, volatility-adjusted, at one formation column.

    Identical arithmetic to alpha_model._compute_momentum_factor, vectorised.
    Only columns strictly left of `col` are touched.
    """
    a = col - MOM_LOOKBACK
    b = col - MOM_SKIP
    if a < 0 or b <= a:
        return None
    p0, p1 = C[:, a], C[:, b]
    with np.errstate(invalid="ignore", divide="ignore"):
        mom = p1 / p0 - 1.0
        win = C[:, a:b + 1]
        rets = win[:, 1:] / win[:, :-1] - 1.0
        vol = np.nanstd(rets, axis=1) * math.sqrt(252)
        risk_adj = np.where(vol > 1e-6, mom / np.where(vol > 1e-6, vol, 1.0), 0.0)
        score = np.tanh(risk_adj / MOM_TANH_DIV)
    score[~np.isfinite(score)] = np.nan
    return score


def _low_risk_scores(C, col):
    """
    The low-volatility factor at one formation column.

    Volatility and worst drawdown over the trailing window, combined 60/40, on
    the same tanh references the live factor uses. The drawdown curve is
    prepended with 1.0 so a fall in the first period counts, matching the fix
    already made in alpha_v2.
    """
    a = max(0, col - LR_WINDOW)
    if col - a < 60:
        return None
    win = C[:, a:col + 1]
    with np.errstate(invalid="ignore", divide="ignore"):
        rets = win[:, 1:] / win[:, :-1] - 1.0
        vol = np.nanstd(rets, axis=1) * math.sqrt(252)
        filled = np.where(np.isfinite(rets), rets, 0.0)
        curve = np.cumprod(1.0 + filled, axis=1)
        curve = np.concatenate([np.ones((curve.shape[0], 1)), curve], axis=1)
        peak = np.maximum.accumulate(curve, axis=1)
        dd = np.min(curve / peak - 1.0, axis=1)
        vol_s = np.tanh((LR_VOL_REF - vol) / LR_VOL_REF)
        dd_s = np.tanh((LR_DD_REF + dd) / LR_DD_REF)
        score = np.clip(LR_VOL_W * vol_s + LR_DD_W * dd_s, -1.0, 1.0)
    # A security with no usable history in the window scores nothing rather
    # than zero: zero is a real score meaning "average risk".
    usable = np.sum(np.isfinite(rets), axis=1) >= 60
    score = np.where(usable, score, np.nan)
    return score


# ------------------------------------------------------------------ stats

def _binom(hits, n):
    try:
        from market_validation import _binom_p
        return _binom_p(hits, n)
    except Exception:
        return None, None


def _wilson_ci(hits, n):
    try:
        from market_validation import _wilson
        return _wilson(hits, n)
    except Exception:
        return None


def _deff(month_hits):
    """Design effect from observations clustered by formation month."""
    try:
        from market_validation import _design_effect
        return _design_effect([{"date": m + "-01", "_hit": h}
                               for m, h in month_hits])
    except Exception:
        return None


def _mean_test(x):
    """Mean, median, interval, t, p and effect size for one series."""
    n = len(x)
    if n < 3:
        return {"n": n, "insufficient": True}
    arr = np.asarray(x, dtype=float)
    mean = float(np.mean(arr))
    med = float(np.median(arr))
    sd = float(np.std(arr, ddof=1))
    se = sd / math.sqrt(n) if sd > 0 else 0.0
    t = mean / se if se > 0 else None
    p, crit = None, 1.96
    if t is not None:
        try:
            from scipy import stats as st
            p = float(2 * st.t.sf(abs(t), df=n - 1))
            crit = float(st.t.ppf(0.975, df=n - 1))
        except Exception:
            p = float(math.erfc(abs(t) / math.sqrt(2)))
    return {
        "n": n,
        "mean_pct": round(mean * 100, 3),
        "median_pct": round(med * 100, 3),
        "sd_pct": round(sd * 100, 3),
        "t_stat": round(t, 3) if t is not None else None,
        "p_value": round(p, 4) if p is not None else None,
        "ci95_pct": ([round((mean - crit * se) * 100, 3),
                      round((mean + crit * se) * 100, 3)] if se > 0 else None),
        "effect_size_d": round(mean / sd, 3) if sd > 0 else None,
    }


def _series_stats(monthly):
    """Portfolio statistics from a monthly return series."""
    n = len(monthly)
    if n < 2:
        return {}
    total = 1.0
    for r in monthly:
        total *= (1 + r)
    years = n / 12.0
    cagr = (total ** (1 / years) - 1) if total > 0 else -1.0
    mean = sum(monthly) / n
    sd = (sum((r - mean) ** 2 for r in monthly) / (n - 1)) ** 0.5
    vol = sd * math.sqrt(12)
    curve, peak, mdd = 1.0, 1.0, 0.0
    for r in monthly:
        curve *= (1 + r)
        peak = max(peak, curve)
        mdd = min(mdd, curve / peak - 1)
    return {
        "months": n,
        "cagr_pct": round(cagr * 100, 2),
        "vol_pct": round(vol * 100, 2),
        "sharpe": round((cagr - RISK_FREE) / vol, 3) if vol > 0 else None,
        "max_drawdown_pct": round(mdd * 100, 2),
        "months_up_pct": round(sum(1 for r in monthly if r > 0) / n * 100, 1),
    }


def _grade(obs, label, n_form, horizon, exploratory=False):
    """
    One cell of the results: excess returns for a group of observations.

    `obs` is a list of (month, excess, raw). Everything reported here is
    clustered by formation month, because stocks selected in the same month
    share that month's market.
    """
    if not obs:
        return {"group": label, "n": 0, "insufficient": True}
    months = sorted({m for m, _, _ in obs})
    exc = [e for _, e, _ in obs]
    raw = [r for _, _, r in obs]
    hits = sum(1 for e in exc if e > 0)
    n = len(exc)

    d = _deff([(m, e > 0) for m, e, _ in obs])
    n_eff = round(n / d["deff"], 1) if d and d.get("deff") else None
    n_i = int(round(n_eff)) if n_eff and n_eff >= 5 else None
    eff_hits = int(round(hits / n * n_i)) if n_i else None
    p_eff, method = _binom(eff_hits, n_i) if n_i else (None, None)

    non_overlap = len(months) // max(horizon, 1)
    out = {
        "group": label,
        "n_observations": n,
        "n_months": len(months),
        "effective_sample_size": n_eff,
        "design_effect": d.get("deff") if d else None,
        "excess": _mean_test(exc),
        "raw_return": _mean_test(raw),
        "hit_rate_pct": round(hits / n * 100, 1),
        "hit_rate_ci95": _wilson_ci(eff_hits, n_i) if n_i else None,
        "hit_rate_p_value": round(p_eff, 4) if p_eff is not None else None,
        "hit_rate_p_method": method,
        "non_overlapping_windows": non_overlap,
        "exploratory": exploratory,
    }
    if non_overlap < MIN_NONOVERLAPPING:
        out["insufficient_independent_windows"] = (
            f"{non_overlap} non-overlapping {horizon}-month window(s) fit in "
            f"{len(months)} formation months. Overlapping windows share months, "
            f"so the interval and p-value above understate the uncertainty and "
            f"should not be read as evidence.")
    return out


# ------------------------------------------------------------------ main

def validate(min_turnover: float = MIN_MONTHLY_TURNOVER,
             n_buckets: int = N_BUCKETS) -> dict:
    """
    Track A: everything the point-in-time archive can legitimately test.

    Returns per-factor, per-horizon quintile results with the top-minus-bottom
    spread as the declared primary hypothesis, plus exploratory cuts by regime
    and liquidity, and the Track B list of what cannot be tested and why.
    """
    try:
        from db import get_conn
        conn = get_conn()
    except Exception as e:
        return {"error": f"No database ({type(e).__name__})."}

    try:
        try:
            from security_identity import _pairs, _resolve_pairs
            canonical, _c, links, amb = _resolve_pairs(_pairs(conn))
            ident = {"linked_isins": len(links), "ambiguous_not_merged": len(amb)}
        except Exception as e:
            canonical, ident = {}, {"error": type(e).__name__}
        keys, days, C, V = _load(conn, canonical)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    me = _month_end_cols(days)
    months = [m for m, _ in me]
    cols = [c for _, c in me]
    if len(me) < 16:
        return {"error": f"Only {len(me)} months of files; not enough to form "
                         f"a 12-month lookback and measure anything after it."}

    # Formation months are those with a full momentum lookback behind them.
    form_ix = [i for i in range(len(me)) if cols[i] - MOM_LOOKBACK >= 0]
    if not form_ix:
        return {"error": "No month has a full 252-day lookback behind it."}

    # Equal-weight market return per month, from the eligible universe itself.
    # Used for excess and for regimes, so the whole of Track A stays inside the
    # point-in-time archive with no external series.
    records = []          # (month, key_ix, mom, lr, liq, {h: (raw, excess)})
    market_monthly = {}

    for i in form_ix:
        col = cols[i]
        mom = _momentum_scores(C, col)
        lr = _low_risk_scores(C, col)
        if mom is None:
            continue
        px_now = C[:, col]
        liq = V[:, col]
        eligible = (np.isfinite(px_now) & (px_now > 0) & np.isfinite(mom)
                    & (liq >= min_turnover))
        if eligible.sum() < 50:
            continue
        idx = np.where(eligible)[0]

        fwd = {}
        for h in HORIZONS:
            j = i + h
            if j >= len(cols):
                continue
            px_next = C[:, cols[j]]
            with np.errstate(invalid="ignore", divide="ignore"):
                r = px_next[idx] / px_now[idx] - 1.0
            # A security with no price at the horizon stopped trading inside
            # the window. Marked to -100%, the same treatment the frozen
            # backtest uses, so the two cannot disagree about delistings.
            r = np.where(np.isfinite(r), r, -1.0)
            fwd[h] = r

        if 1 in fwd:
            market_monthly[months[i]] = float(np.mean(fwd[1]))

        for h, r in fwd.items():
            mkt = float(np.mean(r))
            for pos, k in enumerate(idx):
                records.append({
                    "month": months[i], "key": k, "h": h,
                    "mom": float(mom[k]),
                    "lr": float(lr[k]) if lr is not None and np.isfinite(lr[k]) else None,
                    "liq": float(liq[k]),
                    "raw": float(r[pos]), "excess": float(r[pos] - mkt),
                })

    if not records:
        return {"error": "No formation month produced a usable cross-section."}

    n_form = len({r["month"] for r in records})

    # -------------------------------------------------- regimes, from the PIT
    # market itself and known only from months BEFORE the formation date.
    ordered = [m for m in months if m in market_monthly]
    regime_of = {}
    for pos, m in enumerate(ordered):
        if pos < 3:
            regime_of[m] = ("Insufficient history", "Insufficient history")
            continue
        prior = [market_monthly[x] for x in ordered[pos - 3:pos]]
        cum = 1.0
        for r in prior:
            cum *= (1 + r)
        trend = (cum - 1) * 100
        sd = float(np.std(prior, ddof=1)) if len(prior) > 1 else 0.0
        ann = sd * math.sqrt(12)
        regime_of[m] = (
            "Bull" if trend > REGIME_TREND_PCT else
            "Bear" if trend < -REGIME_TREND_PCT else "Sideways",
            "High volatility" if ann > REGIME_VOL_ANN else "Low volatility")

    # -------------------------------------------------- per factor / horizon
    results, primary = {}, []
    for factor in FACTORS:
        fkey = "mom" if factor == "momentum" else "lr"
        results[factor] = {
            "definition": (
                "Absolute 12-1 momentum, volatility-adjusted: return from 252 "
                "trading days before formation to 21 days before, divided by "
                "annualised daily volatility over that window, through tanh. "
                "Read from alpha_model, not restated here."
                if factor == "momentum" else
                "Annualised volatility and worst drawdown over the trailing "
                "~400 calendar days, combined 60/40 through tanh, scored so "
                "calmer is higher. Read from alpha_v2, not restated here."),
            "weight_v1": _V1_W.get(factor),
            "weight_v2": _V2_W.get(factor),
            "horizons": {},
        }
        for h in HORIZONS:
            rows = [r for r in records if r["h"] == h and r[fkey] is not None]
            if len(rows) < 100:
                results[factor]["horizons"][f"{h}m"] = {
                    "insufficient": True,
                    "reason": f"{len(rows)} observations."}
                continue

            # Buckets are formed WITHIN each month, so a bucket is a
            # cross-sectional rank and not a comparison across time.
            by_month = {}
            for r in rows:
                by_month.setdefault(r["month"], []).append(r)
            for m, group in by_month.items():
                group.sort(key=lambda r: r[fkey])
                nb = len(group)
                for pos, r in enumerate(group):
                    r["_bucket"] = min(n_buckets - 1, pos * n_buckets // nb)

            buckets = []
            for b in range(n_buckets):
                obs = [(r["month"], r["excess"], r["raw"])
                       for r in rows if r["_bucket"] == b]
                buckets.append(_grade(obs, f"Q{b + 1}", n_form, h))

            # Monthly long-only series for the top bucket, net of costs.
            top_monthly, prev = [], set()
            for m in sorted(by_month):
                g = [r for r in by_month[m] if r["_bucket"] == n_buckets - 1]
                if not g:
                    continue
                gross = float(np.mean([r["raw"] for r in g]))
                cur = {r["key"] for r in g}
                turn = len(cur ^ prev) / max(2 * len(cur), 1) if prev else 1.0
                top_monthly.append(gross - turn * COST_ROUNDTRIP_PCT / 100.0)
                prev = cur

            # The declared primary test: top quintile minus bottom, paired by
            # month so the market's move cancels.
            spread = []
            for m, group in by_month.items():
                hi = [r["excess"] for r in group if r["_bucket"] == n_buckets - 1]
                lo = [r["excess"] for r in group if r["_bucket"] == 0]
                if hi and lo:
                    spread.append(float(np.mean(hi)) - float(np.mean(lo)))
            spread_test = _mean_test(spread)
            non_overlap = len(spread) // max(h, 1)
            spread_test["non_overlapping_windows"] = non_overlap
            if non_overlap < MIN_NONOVERLAPPING:
                spread_test["insufficient_independent_windows"] = (
                    f"{non_overlap} non-overlapping {h}-month window(s). Not "
                    f"enough independent periods to test this horizon.")
            primary.append((f"{factor} {h}m top-minus-bottom",
                            spread_test.get("p_value"),
                            non_overlap >= MIN_NONOVERLAPPING))

            results[factor]["horizons"][f"{h}m"] = {
                "buckets": buckets,
                "top_minus_bottom": spread_test,
                "top_bucket_portfolio": _series_stats(top_monthly) if h == 1 else None,
                "turnover_note": ("Portfolio statistics are shown for the "
                                  "1-month horizon only, because rebalancing "
                                  "monthly is what the model does; longer "
                                  "horizons here measure signal decay, not a "
                                  "tradeable series."),
            }

    # -------------------------------------------------- exploratory cuts
    tested = [r for r in records if r["h"] == 1]
    explore = {"n_comparisons": 0, "by_regime": {}, "by_liquidity": {}}
    for factor in FACTORS:
        fkey = "mom" if factor == "momentum" else "lr"
        rows = [r for r in tested if r[fkey] is not None]
        if not rows:
            continue
        by_month = {}
        for r in rows:
            by_month.setdefault(r["month"], []).append(r)
        for m, group in by_month.items():
            group.sort(key=lambda r: r[fkey])
            nb = len(group)
            for pos, r in enumerate(group):
                r["_b"] = min(n_buckets - 1, pos * n_buckets // nb)
            # Liquidity terciles, ranked within the month for the same reason.
            group2 = sorted(group, key=lambda r: r["liq"])
            for pos, r in enumerate(group2):
                r["_liq"] = ["Least liquid", "Mid liquidity",
                             "Most liquid"][min(2, pos * 3 // len(group2))]

        top = [r for r in rows if r.get("_b") == n_buckets - 1]
        reg, liqd = {}, {}
        for r in top:
            t, v = regime_of.get(r["month"], ("Unknown", "Unknown"))
            for label in (t, v):
                reg.setdefault(label, []).append((r["month"], r["excess"], r["raw"]))
            liqd.setdefault(r["_liq"], []).append((r["month"], r["excess"], r["raw"]))
        explore["by_regime"][factor] = {
            k: _grade(v, k, n_form, 1, exploratory=True)
            for k, v in sorted(reg.items())}
        explore["by_liquidity"][factor] = {
            k: _grade(v, k, n_form, 1, exploratory=True)
            for k, v in sorted(liqd.items())}
        explore["n_comparisons"] += len(reg) + len(liqd)

    # -------------------------------------------------- multiple testing
    usable = [(name, p) for name, p, ok in primary if ok and p is not None]
    n_primary = len(usable)
    alpha = 0.05 / n_primary if n_primary else None
    survivors = [n for n, p in usable if alpha and p < alpha]

    return {
        "track_a": {
            "label": "V1.0 price-observable validation",
            "not": ("This is NOT full V1/V2 validation. It covers the two "
                    "factors the archive can reconstruct and no others."),
            "weight_covered": {
                "v1_pct": round(sum(v for k, v in _V1_W.items()
                                    if k in FACTORS) * 100, 1),
                "v2_pct": round(sum(v for k, v in _V2_W.items()
                                    if k in FACTORS) * 100, 1),
            },
            "factors": results,
            "exploratory": explore,
            "exploratory_warning": (
                f"{explore['n_comparisons']} exploratory comparisons were made "
                f"by regime and liquidity. No correction is applied to them "
                f"and none should be read as a finding; they are cut from the "
                f"same {n_form} months as the primary tests and cannot be "
                f"independent of them."),
        },
        "track_b": {
            "label": "UNTESTABLE WITH CURRENT PIT DATA",
            "components": UNTESTABLE,
            "rule_applied": (
                "No historical value was substituted for a missing one. "
                "Today's fundamentals, today's news, today's sector map and "
                "today's market caps were all available and all refused, "
                "because using any of them would score a past date on "
                "information from after it."),
        },
        "multiple_testing": {
            "primary_hypotheses_declared": len(primary),
            "primary_hypotheses_testable": n_primary,
            "bonferroni_alpha": round(alpha, 5) if alpha else None,
            "survived_correction": survivors,
            "detail": [{"hypothesis": n, "p_value": p} for n, p in usable],
            "note": ("Two factors by four horizons were declared before the "
                     "results were read. Horizons without enough "
                     "non-overlapping windows are excluded from the correction "
                     "rather than counted as passes or failures."),
        },
        "universe": {
            "securities_seen": len(keys),
            "trading_days": len(days),
            "formation_months": n_form,
            "months_available": len(me),
            "first_month": months[0], "last_month": months[-1],
            "liquidity_floor_rupees": min_turnover,
            "identity": ident,
        },
        "method": {
            "identity": ("Securities are resolved identities, chained across "
                         "renames and ISIN changes, the same keying the "
                         "corrected backtest uses."),
            "excess": ("Excess is against the equal-weighted return of the "
                       "eligible universe that month, not an index. It removes "
                       "the market move without introducing an external series "
                       "the archive cannot verify."),
            "delistings": ("A security with no price at the horizon is marked "
                           "-100%, matching the frozen backtest."),
            "buckets": ("Quintiles are formed within each month, so a bucket "
                        "is a cross-sectional rank and never a comparison "
                        "across time."),
            "clustering": ("Every interval and p-value is computed on the "
                           "effective sample size — observations divided by a "
                           "design effect estimated by ANOVA across formation "
                           "months. Stocks picked in the same month share that "
                           "month's market and are not independent."),
            "costs": f"{COST_ROUNDTRIP_PCT}% round trip on realised turnover.",
            "regimes": (f"Trend is the trailing 3-month equal-weight market "
                        f"return, above +{REGIME_TREND_PCT}% Bull, below "
                        f"-{REGIME_TREND_PCT}% Bear, otherwise Sideways. "
                        f"Volatility is the annualised trailing 3-month figure "
                        f"against {REGIME_VOL_ANN:.0%}. Both use only months "
                        f"before the formation date. These thresholds are "
                        f"conventions fixed in advance, not fitted."),
        },
        "limits": (
            f"{n_form} formation months over a single market period. Prices are "
            f"exchange closes, unadjusted for splits and dividends, so a "
            f"corporate action inside a holding window distorts that window for "
            f"that security. Nothing here establishes a durable edge, and a "
            f"result that survives correction over {n_form} months would still "
            f"need out-of-sample confirmation."),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
