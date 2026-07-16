"""
black_scholes.py — European option pricing (Black-Scholes-Merton) with Greeks,
risk-neutral probability of finishing in-the-money, an implied-volatility solver,
and a payoff/sensitivity generator for the Options Lab.

Pure math (only the standard library) so it is fast and dependency-light:
the normal CDF/PDF are built from math.erf.

Conventions reported to the UI (trader-friendly):
  vega  — price change per +1 percentage-point of volatility  (raw vega / 100)
  theta — price change per calendar day of time decay          (raw theta / 365)
  rho   — price change per +1 percentage-point of rate         (raw rho  / 100)
delta and gamma are in their natural per-1.0 units.
"""

import math

SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI


def _intrinsic(spot: float, strike: float, option_type: str) -> float:
    return max(0.0, spot - strike) if option_type == "call" else max(0.0, strike - spot)


def black_scholes(
    spot: float,
    strike: float,
    t_years: float,
    rate_pct: float,
    vol_pct: float,
    option_type: str = "call",
) -> dict:
    """
    Price a European option and its Greeks.

    spot, strike — in the same currency (₹)
    t_years      — time to expiry in YEARS (e.g. 30 days ≈ 0.0822)
    rate_pct     — annual risk-free rate, in PERCENT (e.g. 6.5)
    vol_pct      — annual volatility, in PERCENT (e.g. 22.0)
    option_type  — "call" or "put"
    """
    option_type = (option_type or "call").lower()
    if option_type not in ("call", "put"):
        return {"error": "option_type must be 'call' or 'put'"}
    try:
        S = float(spot); K = float(strike); T = float(t_years)
        r = float(rate_pct) / 100.0; sig = float(vol_pct) / 100.0
    except (TypeError, ValueError):
        return {"error": "all inputs must be numbers"}
    if S <= 0 or K <= 0:
        return {"error": "spot and strike must be greater than 0"}

    # Degenerate cases: no time left, or no volatility → price is the discounted
    # intrinsic value and Greeks are (almost all) zero. Handle explicitly so we
    # never divide by zero.
    if T <= 0 or sig <= 0:
        intrinsic = _intrinsic(S, K, option_type)
        return _result(option_type, S, K, T, r, sig,
                       price=intrinsic, delta=(1.0 if (option_type == "call" and S > K)
                                               else -1.0 if (option_type == "put" and S < K) else 0.0),
                       gamma=0.0, vega=0.0, theta=0.0, rho=0.0,
                       prob_itm=(1.0 if intrinsic > 0 else 0.0), d1=None, d2=None,
                       note="No time value (T=0 or vol=0): price = intrinsic value.")

    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * sqrtT)
    d2 = d1 - sig * sqrtT
    Nd1, Nd2 = _norm_cdf(d1), _norm_cdf(d2)
    nd1 = _norm_pdf(d1)
    disc = math.exp(-r * T)

    if option_type == "call":
        price = S * Nd1 - K * disc * Nd2
        delta = Nd1
        theta = (-(S * nd1 * sig) / (2 * sqrtT) - r * K * disc * Nd2)
        rho   = K * T * disc * Nd2
        prob_itm = Nd2                        # risk-neutral P(S_T > K)
    else:
        price = K * disc * _norm_cdf(-d2) - S * _norm_cdf(-d1)
        delta = Nd1 - 1.0
        theta = (-(S * nd1 * sig) / (2 * sqrtT) + r * K * disc * _norm_cdf(-d2))
        rho   = -K * T * disc * _norm_cdf(-d2)
        prob_itm = _norm_cdf(-d2)             # risk-neutral P(S_T < K)

    gamma = nd1 / (S * sig * sqrtT)
    vega  = S * nd1 * sqrtT

    return _result(option_type, S, K, T, r, sig,
                   price=price, delta=delta, gamma=gamma,
                   vega=vega / 100.0,        # per +1% vol
                   theta=theta / 365.0,      # per calendar day
                   rho=rho / 100.0,          # per +1% rate
                   prob_itm=prob_itm, d1=d1, d2=d2)


def _result(option_type, S, K, T, r, sig, *, price, delta, gamma, vega, theta,
            rho, prob_itm, d1, d2, note=None) -> dict:
    moneyness = ("ATM" if abs(S - K) / K < 0.005 else
                 ("ITM" if _intrinsic(S, K, option_type) > 0 else "OTM"))
    out = {
        "option_type":   option_type,
        "spot":          round(S, 4),
        "strike":        round(K, 4),
        "t_years":       round(T, 6),
        "rate_pct":      round(r * 100, 4),
        "vol_pct":       round(sig * 100, 4),
        "price":         round(price, 4),
        "intrinsic":     round(_intrinsic(S, K, option_type), 4),
        "time_value":    round(price - _intrinsic(S, K, option_type), 4),
        "moneyness":     moneyness,
        "greeks": {
            "delta": round(delta, 4),
            "gamma": round(gamma, 6),
            "vega":  round(vega, 4),   # per +1% vol
            "theta": round(theta, 4),  # per day
            "rho":   round(rho, 4),    # per +1% rate
        },
        "prob_itm_pct":  round(prob_itm * 100, 2),
        "d1": round(d1, 4) if d1 is not None else None,
        "d2": round(d2, 4) if d2 is not None else None,
    }
    if note:
        out["note"] = note
    return out


def implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    t_years: float,
    rate_pct: float,
    option_type: str = "call",
) -> dict:
    """
    Back out the volatility that reproduces an observed option price, using
    Newton-Raphson (with vega) and a bisection fallback for robustness.
    """
    try:
        target = float(market_price); S = float(spot); K = float(strike)
        T = float(t_years); r = float(rate_pct) / 100.0
    except (TypeError, ValueError):
        return {"error": "all inputs must be numbers"}
    if target <= 0 or S <= 0 or K <= 0 or T <= 0:
        return {"error": "market_price, spot, strike and time must be > 0"}

    intrinsic = _intrinsic(S, K, option_type)
    if target < intrinsic - 1e-6:
        return {"error": "price is below intrinsic value — no implied vol exists"}

    # Newton-Raphson
    sig = 0.25
    for _ in range(100):
        r_res = black_scholes(S, K, T, r * 100, sig * 100, option_type)
        diff = r_res["price"] - target
        vega_raw = r_res["greeks"]["vega"] * 100.0   # undo the /100 scaling
        if vega_raw < 1e-8:
            break
        step = diff / vega_raw
        sig -= step
        if sig <= 1e-6:
            sig = 1e-4
        if abs(step) < 1e-6:
            break

    # Bisection fallback if Newton wandered out of a sane range
    # Bisection fallback if Newton left the sane range OR converged to a value
    # whose price doesn't actually match the target (Newton can stall on
    # low-vol / low-price options where vega is tiny). Bisection is slower but
    # globally convergent on the monotonic price-vs-vol curve.
    def _price_at(s):
        return black_scholes(S, K, T, r * 100, s * 100, option_type)["price"]

    newton_ok = (1e-4 < sig < 5.0) and abs(_price_at(sig) - target) < max(1e-3, 1e-3 * target)
    if not newton_ok:
        lo, hi = 1e-6, 5.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if _price_at(mid) > target:
                hi = mid
            else:
                lo = mid
        sig = 0.5 * (lo + hi)

    return {"implied_vol_pct": round(sig * 100, 2)}


def payoff_curve(strike: float, premium: float, option_type: str,
                 spot: float, points: int = 41) -> list:
    """
    Profit/loss at expiry for a long option across a range of underlying prices
    (roughly ±40% around spot). For plotting the payoff diagram.
    """
    option_type = (option_type or "call").lower()
    lo, hi = spot * 0.6, spot * 1.4
    curve = []
    for i in range(points):
        s = lo + (hi - lo) * i / (points - 1)
        intrinsic = max(0.0, s - strike) if option_type == "call" else max(0.0, strike - s)
        curve.append({"spot": round(s, 2), "pnl": round(intrinsic - premium, 2)})
    return curve


if __name__ == "__main__":
    print("=" * 60)
    print("Testing black_scholes.py")
    print("=" * 60)
    r = black_scholes(spot=100, strike=100, t_years=1.0, rate_pct=5, vol_pct=20, option_type="call")
    print("ATM 1y call (S=K=100, r=5%, vol=20%):")
    print(f"  price = {r['price']}  (textbook ≈ 10.45)")
    print(f"  delta={r['greeks']['delta']} gamma={r['greeks']['gamma']} "
          f"vega={r['greeks']['vega']} theta={r['greeks']['theta']} rho={r['greeks']['rho']}")
    print(f"  P(ITM) = {r['prob_itm_pct']}%")
    iv = implied_volatility(r["price"], 100, 100, 1.0, 5, "call")
    print(f"  implied vol from that price = {iv['implied_vol_pct']}% (should recover ~20%)")
    p = black_scholes(100, 100, 1.0, 5, 20, "put")
    print(f"put price = {p['price']}  (put-call parity check: C - P ≈ S - K·e^-rT)")
