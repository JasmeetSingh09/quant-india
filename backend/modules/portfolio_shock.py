"""
portfolio_shock.py — "what happens to me if X falls 20%?"

The rest of the app answers "what might happen", by simulating thousands of
futures. This answers a narrower and more useful question: given one specific
event, where does the damage land in MY portfolio, and which holdings cause it.

Every shock uses the same transmission model, because a scenario tool that
switches methods between scenarios is measuring the method rather than the
event. One driver is moved by a stated amount; every holding then moves by its
own measured beta to that driver:

    holding move = beta(holding, driver) x driver move

The driver is the Nifty for a market shock, a basket of the holdings in a
sector for a sector shock, and the stock itself for a single-stock shock. Beta
is estimated by ordinary least squares on daily returns over the lookback, and
the stock being shocked is pinned to the shock exactly rather than to its own
beta against itself.

What this deliberately does NOT claim
-------------------------------------
Betas are historical averages measured across ordinary days, and correlations
rise sharply in a real crash — everything falls together in a way that a
normal-period beta understates. So the losses here are, if anything, optimistic
for a genuine crisis. That is stated in the output rather than buried, because
a risk tool that quietly flatters the downside is worse than no risk tool.

It is also linear and instantaneous: no recovery path, no second round of
selling, no liquidity effects.
"""

from datetime import datetime, timedelta

import numpy as np


LOOKBACK_DAYS = 500
NIFTY = "^NSEI"


def _returns(tickers, lookback_days=LOOKBACK_DAYS):
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=int(lookback_days * 1.5))).strftime("%Y-%m-%d")
    from portfolio_optimizer import _get_returns
    return _get_returns(list(dict.fromkeys(tickers)), start, end)


def _beta(series, driver):
    """OLS slope of series on driver. None when it cannot be estimated."""
    try:
        a = np.asarray(series, dtype=float)
        b = np.asarray(driver, dtype=float)
        m = np.isfinite(a) & np.isfinite(b)
        a, b = a[m], b[m]
        if len(a) < 60:
            return None
        var = float(b.var())
        if var <= 0:
            return None
        return float(np.cov(a, b, ddof=0)[0, 1] / var)
    except Exception:
        return None


def _sector_of(t):
    try:
        from portfolio_advisor import _sector_of as f
        return f(t)
    except Exception:
        return None


def shock(holdings: dict, kind: str = "market", magnitude_pct: float = -20.0,
          target: str = None, cash_pct: float = 0.0,
          initial_value: float = 100000, lookback_days: int = LOOKBACK_DAYS) -> dict:
    """
    Apply one event and report where the damage lands.

    kind      "market" | "sector" | "stock"
    magnitude the driver's move in percent, negative for a fall
    target    sector name for "sector", ticker for "stock"
    cash_pct  share of the portfolio held in cash, which does not move
    """
    holdings = {str(t).strip().upper(): float(v) for t, v in (holdings or {}).items()
                if v and float(v) > 0}
    if not holdings:
        return {"error": "No holdings to shock."}
    if kind not in ("market", "sector", "stock"):
        return {"error": f"Unknown scenario '{kind}'."}
    try:
        magnitude_pct = float(magnitude_pct)
    except Exception:
        return {"error": "Shock size must be a number."}
    if not -95 <= magnitude_pct <= 200:
        return {"error": "Shock size must be between -95% and +200%."}
    cash_pct = max(0.0, min(100.0, float(cash_pct or 0.0)))

    total = sum(holdings.values()) or 1.0
    w = {t: v * 100.0 / total for t, v in holdings.items()}
    tickers = list(w)

    if kind == "stock":
        target = (target or "").strip().upper()
        if target not in w:
            return {"error": f"{target or 'That stock'} is not in this portfolio."}
    if kind == "sector":
        sectors = {s for s in (_sector_of(t) for t in tickers) if s}
        if not target or target not in sectors:
            return {"error": (f"Pick a sector you actually hold. "
                              f"Yours: {', '.join(sorted(sectors)) or 'unknown'}.")}

    need = tickers + ([NIFTY] if kind == "market" else [])
    try:
        rets = _returns(need, lookback_days)
    except Exception as e:
        return {"error": f"Could not load returns: {type(e).__name__}"}
    if rets is None or rets.empty:
        return {"error": "No return history for these holdings."}

    cols = [t for t in need if t in rets.columns]
    rets = rets[cols].dropna()
    if len(rets) < 60:
        return {"error": "Not enough overlapping history to estimate betas."}

    # ---- build the driver series ------------------------------------------
    if kind == "market":
        if NIFTY not in rets.columns:
            return {"error": "Could not load the Nifty to drive a market shock."}
        driver = rets[NIFTY].values
        driver_name = "Nifty 50"
        pinned = set()
    elif kind == "stock":
        if target not in rets.columns:
            return {"error": f"No return history for {target}."}
        driver = rets[target].values
        driver_name = target.replace(".NS", "")
        pinned = {target}
    else:
        members = [t for t in tickers if _sector_of(t) == target and t in rets.columns]
        if not members:
            return {"error": f"No return history for your {target} holdings."}
        driver = rets[members].mean(axis=1).values
        driver_name = f"{target} basket"
        pinned = set(members)

    move = magnitude_pct / 100.0
    invested = 1.0 - cash_pct / 100.0

    rows, total_move = [], 0.0
    for t in tickers:
        if t not in rets.columns:
            rows.append({"ticker": t, "weight_pct": round(w[t], 2), "beta": None,
                         "move_pct": None, "impact_inr": None,
                         "note": "no return history, excluded from the total"})
            continue
        # A stock being shocked directly moves by the shock, not by its beta
        # against itself — which is 1 by construction and would silently smuggle
        # in an estimate where an exact number was intended.
        b = 1.0 if t in pinned else _beta(rets[t].values, driver)
        if b is None:
            rows.append({"ticker": t, "weight_pct": round(w[t], 2), "beta": None,
                         "move_pct": None, "impact_inr": None,
                         "note": "beta could not be estimated, excluded"})
            continue
        mv = b * move
        share = w[t] / 100.0 * invested
        contrib = share * mv
        total_move += contrib
        rows.append({
            "ticker": t,
            "weight_pct": round(w[t], 2),
            "beta": round(b, 2),
            "move_pct": round(mv * 100, 2),
            "impact_inr": round(initial_value * contrib, 0),
            "impact_pts": round(contrib * 100, 2),
            "pinned": t in pinned,
        })

    after_value = initial_value * (1 + total_move)
    rows.sort(key=lambda r: (r.get("impact_pts") if r.get("impact_pts") is not None else 0))

    # Where it lands by sector, which is usually the real story.
    by_sector = {}
    for r in rows:
        if r.get("impact_pts") is None:
            continue
        s = _sector_of(r["ticker"]) or "Unclassified"
        by_sector[s] = round(by_sector.get(s, 0.0) + r["impact_pts"], 2)

    hurt = [r for r in rows if r.get("impact_pts") is not None][:3]
    excluded = [r["ticker"] for r in rows if r.get("impact_pts") is None]

    label = {"market": f"The market falls {abs(magnitude_pct):.0f}%"
                       if move < 0 else f"The market rises {magnitude_pct:.0f}%",
             "sector": f"{target} falls {abs(magnitude_pct):.0f}%"
                       if move < 0 else f"{target} rises {magnitude_pct:.0f}%",
             "stock": f"{driver_name} falls {abs(magnitude_pct):.0f}%"
                      if move < 0 else f"{driver_name} rises {magnitude_pct:.0f}%"}[kind]

    return {
        "scenario": label,
        "driver": driver_name,
        "shock_pct": round(magnitude_pct, 2),
        "cash_pct": round(cash_pct, 1),
        "initial_value": round(initial_value, 2),
        "after_value": round(after_value, 2),
        "change_inr": round(after_value - initial_value, 0),
        "change_pct": round(total_move * 100, 2),
        "holdings": rows,
        "by_sector": dict(sorted(by_sector.items(), key=lambda kv: kv[1])),
        "hurt_most": [{"ticker": r["ticker"].replace(".NS", ""),
                       "impact_pts": r["impact_pts"],
                       "impact_inr": r["impact_inr"]} for r in hurt],
        "excluded": excluded,
        "days_used": int(len(rets)),
        "how": (f"Every holding moves by its own beta to {driver_name}, measured by "
                f"least squares on {len(rets)} days of returns. "
                + (f"The {'stock' if kind == 'stock' else 'sector'} being shocked is "
                   f"pinned to the shock exactly rather than to a beta against itself. "
                   if pinned else "")
                + (f"Cash ({cash_pct:.0f}%) does not move." if cash_pct else "")),
        "limits": (
            "Betas are historical averages measured across ordinary days, and "
            "correlations rise sharply in a real crash — things that normally "
            "move apart fall together. So this figure is, if anything, optimistic "
            "for a genuine crisis. It is also linear and instantaneous: no "
            "recovery path, no second round of selling, no liquidity effects, and "
            "no assumption about how likely any of this is. It answers 'where "
            "would the damage land', not 'will this happen'."),
    }


def compare(current: dict, proposed: dict, kind: str = "market",
            magnitude_pct: float = -20.0, target: str = None,
            initial_value: float = 100000) -> dict:
    """
    The same event, applied to what you hold and to what was suggested.

    The coach can say a change lowers your health score's risk component and
    raises your effective positions. Neither of those is money. This answers the
    question a person actually has before they pay brokerage to rebalance: in
    the bad case this is supposed to protect me from, am I better off?

    Both portfolios go through one shock with one set of betas, so the
    difference is the allocation and nothing else.
    """
    a = shock(current, kind=kind, magnitude_pct=magnitude_pct, target=target,
              initial_value=initial_value)
    if "error" in a:
        return {"error": f"Current portfolio: {a['error']}"}
    b = shock(proposed, kind=kind, magnitude_pct=magnitude_pct, target=target,
              initial_value=initial_value)
    if "error" in b:
        return {"error": f"Suggested portfolio: {b['error']}"}

    diff_pts = round(b["change_pct"] - a["change_pct"], 2)
    diff_inr = round(b["after_value"] - a["after_value"], 0)
    better = diff_pts > 0.05

    if better:
        verdict = (f"In this scenario the suggested portfolio loses "
                   f"{abs(diff_pts):.1f} points less — about "
                   f"Rs {abs(diff_inr):,.0f} on Rs {initial_value:,.0f}.")
    elif diff_pts < -0.05:
        # The case worth building this for. A change can raise a health score
        # and still leave you worse off in the fall it was meant to protect
        # against, and nothing else in the app would have caught that.
        verdict = (f"In this scenario the suggested portfolio loses "
                   f"{abs(diff_pts):.1f} points MORE — about "
                   f"Rs {abs(diff_inr):,.0f} worse on Rs {initial_value:,.0f}. "
                   f"Better structure does not automatically mean a smaller "
                   f"fall in every event.")
    else:
        verdict = ("In this scenario the two are within a rounding error of "
                   "each other. Whatever the change is worth, it is not "
                   "visible here.")

    return {
        "scenario": a["scenario"],
        "current": {"change_pct": a["change_pct"], "after_value": a["after_value"],
                    "by_sector": a["by_sector"], "hurt_most": a["hurt_most"]},
        "suggested": {"change_pct": b["change_pct"], "after_value": b["after_value"],
                      "by_sector": b["by_sector"], "hurt_most": b["hurt_most"]},
        "difference_pts": diff_pts,
        "difference_inr": diff_inr,
        "suggested_is_better": better,
        "verdict": verdict,
        "how": a["how"],
        "limits": (a["limits"] + " And one scenario is not a verdict on a "
                   "rebalance: a change that helps in a market fall can hurt in "
                   "a sector one, so try more than the first button."),
    }


PRESETS = [
    {"key": "crash_10", "kind": "market", "magnitude_pct": -10.0, "label": "Market falls 10%"},
    {"key": "crash_20", "kind": "market", "magnitude_pct": -20.0, "label": "Market falls 20%"},
    {"key": "crash_30", "kind": "market", "magnitude_pct": -30.0, "label": "Market falls 30%"},
    {"key": "rally_20", "kind": "market", "magnitude_pct": 20.0, "label": "Market rises 20%"},
]


def presets_for(holdings: dict) -> list:
    """The preset list, plus the sector and single-stock shocks that are
    actually available for THIS portfolio — offering 'IT falls 30%' to someone
    who holds no IT is how a scenario tool loses credibility."""
    out = list(PRESETS)
    holdings = holdings or {}
    secs = sorted({s for s in (_sector_of(t) for t in holdings) if s})
    for s in secs[:6]:
        out.append({"key": f"sector_{s}", "kind": "sector", "target": s,
                    "magnitude_pct": -30.0, "label": f"{s.replace('_', ' ')} falls 30%"})
    biggest = sorted(holdings, key=lambda t: -float(holdings[t]))[:3]
    for t in biggest:
        out.append({"key": f"stock_{t}", "kind": "stock", "target": t,
                    "magnitude_pct": -40.0,
                    "label": f"{t.replace('.NS', '')} falls 40%"})
    return out
