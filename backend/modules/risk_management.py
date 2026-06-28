"""
risk_management.py — Position sizing the way professionals do it.

A signal says WHAT to buy; risk management says HOW MUCH — which matters more
for survival. Bet too big and one bad streak ruins you even with a real edge.

  - Kelly Criterion: the mathematically optimal fraction for long-term growth.
    Pros use HALF-Kelly because full Kelly is brutally volatile.
  - Volatility targeting: scale the position so the portfolio hits a target
    volatility (what managed-vol / risk-parity funds do).

All inputs are annualised (return %, vol %). Risk-free defaults to RBI repo.
"""

RISK_FREE = 0.065   # RBI repo rate proxy


def kelly_fraction(annual_return_pct: float, annual_vol_pct: float,
                   risk_free_pct: float = RISK_FREE * 100) -> dict:
    """
    Continuous Kelly fraction: f* = (return - risk_free) / variance.
    Returns full Kelly and the safer half-Kelly.
    """
    try:
        mu = float(annual_return_pct) / 100
        sig = float(annual_vol_pct) / 100
        rf = float(risk_free_pct) / 100
    except (TypeError, ValueError):
        return {"error": "inputs must be numbers"}
    if sig <= 0:
        return {"error": "volatility must be greater than 0"}

    full = (mu - rf) / (sig ** 2)
    half = full / 2
    return {
        "full_kelly": round(full, 4),
        "half_kelly": round(half, 4),
        "full_kelly_pct": round(full * 100, 1),
        "half_kelly_pct": round(half * 100, 1),
        "note": (
            "Full Kelly is the growth-optimal fraction but very volatile; "
            "half-Kelly keeps ~75% of the growth with far smaller drawdowns. "
            + ("Negative Kelly = the edge doesn't beat the risk-free rate; don't bet."
               if full <= 0 else "")
        ),
    }


def vol_target_weight(asset_vol_pct: float, target_vol_pct: float = 15.0,
                      allow_leverage: bool = False) -> dict:
    """
    Weight needed so the position runs at target volatility.
    weight = target_vol / asset_vol (capped at 1 unless leverage allowed).
    """
    try:
        av = float(asset_vol_pct); tv = float(target_vol_pct)
    except (TypeError, ValueError):
        return {"error": "inputs must be numbers"}
    if av <= 0:
        return {"error": "asset volatility must be greater than 0"}

    raw = tv / av
    weight = raw if allow_leverage else min(1.0, raw)
    return {
        "target_vol_pct": tv,
        "asset_vol_pct": av,
        "weight": round(weight, 4),
        "weight_pct": round(weight * 100, 1),
        "cash_pct": round(max(0.0, 1 - weight) * 100, 1),
        "uses_leverage": weight > 1.0,
        "note": (
            f"To run at {tv:g}% volatility with a {av:g}%-vol asset, hold "
            f"{round(weight*100,1)}%"
            + (f" and keep {round((1-weight)*100,1)}% in cash."
               if weight < 1 else " (leveraged)." )
        ),
    }


def recommend_position(annual_return_pct: float, annual_vol_pct: float,
                       target_vol_pct: float = 15.0,
                       max_position_pct: float = 100.0) -> dict:
    """
    Combine half-Kelly and vol-targeting into one conservative recommendation:
    take the SMALLER of the two (the more cautious), capped at max_position.
    """
    k = kelly_fraction(annual_return_pct, annual_vol_pct)
    v = vol_target_weight(annual_vol_pct, target_vol_pct)
    if "error" in k:
        return k
    if "error" in v:
        return v

    half_kelly_w = max(0.0, k["half_kelly"])          # never negative
    vol_w        = v["weight"]
    cap          = max_position_pct / 100
    recommended  = min(half_kelly_w, vol_w, cap)

    driver = ("edge too weak (Kelly ≈ 0)" if half_kelly_w <= 0
              else "Kelly (risk/reward)" if half_kelly_w <= vol_w else "volatility target")

    return {
        "inputs": {"annual_return_pct": annual_return_pct,
                   "annual_vol_pct": annual_vol_pct,
                   "target_vol_pct": target_vol_pct},
        "half_kelly_weight_pct": round(half_kelly_w * 100, 1),
        "vol_target_weight_pct": round(vol_w * 100, 1),
        "recommended_weight_pct": round(recommended * 100, 1),
        "cash_pct": round(max(0.0, 1 - recommended) * 100, 1),
        "binding_constraint": driver,
        "verdict": (
            f"Allocate about {round(recommended*100,1)}% of capital to this position "
            f"(the rest in cash). Driven by the {driver}. This sizing protects you "
            f"from ruin while capturing most of the growth."
            if recommended > 0 else
            "Don't take this position — the expected edge doesn't justify the risk."
        ),
    }


if __name__ == "__main__":
    print("=" * 60)
    print("Testing risk_management.py")
    print("=" * 60)

    print("\n1. Strong edge (18% return, 20% vol):")
    print("  ", recommend_position(18, 20)["verdict"])

    print("\n2. Weak edge (7% return ~ risk-free, 25% vol):")
    print("  ", recommend_position(7, 25)["verdict"])

    print("\n3. High-vol asset (15% return, 45% vol), target 15%:")
    v = vol_target_weight(45, 15)
    print("  ", v["note"])

    print("\n4. Kelly detail (20% return, 18% vol):")
    k = kelly_fraction(20, 18)
    print(f"   full {k['full_kelly_pct']}% | half {k['half_kelly_pct']}%")

    print("\n5. Edge cases:")
    print("   zero vol:", kelly_fraction(10, 0).get("error"))
    print("   bad input:", vol_target_weight("x", 15).get("error"))
    print("\nDone.")
