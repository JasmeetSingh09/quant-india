"""
regime_detector.py — Gaussian HMM-based Market Regime Detector for NSE/Nifty 50.

ALGORITHM: Hidden Markov Model with Gaussian Emissions

The core idea: markets cycle through distinct "regimes" that are not
directly observable — they are hidden states. We observe only daily
returns and volatility. The HMM learns to infer which hidden state
(regime) we are in from these observations.

MODEL SPEC:
  Hidden states  : 3  (Bull, Bear, Sideways/Volatile)
  Observed data  : [daily_return, abs(daily_return)]  — return + volatility
  Emissions      : Gaussian  N(μ_k, σ_k) per state k
  Transitions    : Learned Markov chain A[i,j] = P(state_j | state_i)

ESTIMATION: Baum-Welch (EM algorithm)
  E-step: Forward-Backward algorithm to compute state posteriors
  M-step: Update μ, σ, A using weighted sufficient statistics
  Repeat until convergence (log-likelihood change < 1e-4)

WHY THIS MATTERS FOR INVESTING:
  The same signal (e.g. negative sentiment) means different things
  in different regimes:
    - Bull regime: negative sentiment → mild pullback, buy the dip
    - Bear regime: negative sentiment → extended sell-off, reduce exposure
    - Sideways:    negative sentiment → range-bound, smaller position size

  The alpha model uses current regime to SCALE factor weights:
    Bull:     momentum weight ↑, value weight ↓
    Bear:     quality weight ↑, sentiment weight ↑
    Sideways: equal weights

OUTPUT:
  - Current regime with probability
  - Regime history (for charting)
  - Transition matrix (how likely is regime change?)
  - Regime-conditioned signal multipliers
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

NIFTY_TICKER = "^NSEI"


# ---------------------------------------------------------------------------
# Gaussian HMM — implemented from scratch (no hmmlearn dependency)
# ---------------------------------------------------------------------------

class GaussianHMM:
    """
    Three-state Gaussian HMM fitted via Baum-Welch EM algorithm.

    All math implemented from scratch so the algorithm is fully
    transparent and auditable — important for quant firm interviews.
    """

    def __init__(self, n_states: int = 3, n_iter: int = 100, tol: float = 1e-4):
        self.n_states = n_states
        self.n_iter   = n_iter
        self.tol      = tol
        self.fitted   = False

    def _init_params(self, X: np.ndarray):
        """Initialise parameters using k-means-style percentile split."""
        n, d = X.shape
        K    = self.n_states

        # Initial transition matrix (slightly sticky — regimes persist)
        self.A = np.full((K, K), 0.1 / (K - 1))
        np.fill_diagonal(self.A, 0.8)

        # Initial state distribution
        self.pi_0 = np.ones(K) / K

        # Initialise means by splitting observations into K groups
        sorted_idx = np.argsort(X[:, 0])   # sort by return
        chunk      = n // K
        self.mu    = np.array([X[sorted_idx[i*chunk:(i+1)*chunk], :].mean(axis=0)
                                for i in range(K)])
        self.sigma = np.array([np.cov(X[sorted_idx[i*chunk:(i+1)*chunk], :].T) + 1e-6 * np.eye(d)
                                for i in range(K)])

    def _gaussian_pdf(self, x: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> float:
        """Multivariate Gaussian PDF evaluated at x."""
        d    = len(mu)
        diff = x - mu
        try:
            cov_inv = np.linalg.inv(sigma)
            det     = np.linalg.det(sigma)
            if det <= 0:
                det = 1e-10
            exponent = -0.5 * diff @ cov_inv @ diff
            norm     = 1 / (((2 * np.pi) ** (d / 2)) * (det ** 0.5))
            return float(norm * np.exp(np.clip(exponent, -500, 0)))
        except Exception:
            return 1e-300

    def _emission_matrix(self, X: np.ndarray) -> np.ndarray:
        """Compute B[t, k] = P(x_t | state=k) for all t, k."""
        n = len(X)
        B = np.zeros((n, self.n_states))
        for k in range(self.n_states):
            for t in range(n):
                B[t, k] = self._gaussian_pdf(X[t], self.mu[k], self.sigma[k])
        B = np.clip(B, 1e-300, None)
        return B

    def _forward(self, B: np.ndarray):
        """Forward algorithm: α[t,k] = P(x_1...x_t, state_t=k)."""
        n, K = B.shape
        alpha = np.zeros((n, K))
        scale = np.zeros(n)

        alpha[0] = self.pi_0 * B[0]
        scale[0] = alpha[0].sum()
        alpha[0] /= max(scale[0], 1e-300)

        for t in range(1, n):
            alpha[t] = (alpha[t-1] @ self.A) * B[t]
            scale[t] = alpha[t].sum()
            alpha[t] /= max(scale[t], 1e-300)

        return alpha, scale

    def _backward(self, B: np.ndarray, scale: np.ndarray):
        """Backward algorithm: β[t,k] = P(x_{t+1}...x_T | state_t=k)."""
        n, K = B.shape
        beta = np.zeros((n, K))
        beta[-1] = 1.0

        for t in range(n - 2, -1, -1):
            beta[t] = self.A @ (B[t+1] * beta[t+1])
            beta[t] /= max(scale[t+1], 1e-300)

        return beta

    def fit(self, X: np.ndarray):
        """
        Fit HMM parameters via Baum-Welch (EM).
        X shape: (T, n_features)
        """
        self._init_params(X)
        prev_ll = -np.inf

        for iteration in range(self.n_iter):
            B     = self._emission_matrix(X)
            alpha, scale = self._forward(B)
            beta  = self._backward(B, scale)

            log_ll = np.sum(np.log(np.clip(scale, 1e-300, None)))

            # E-step: state posteriors
            gamma = alpha * beta
            gamma /= gamma.sum(axis=1, keepdims=True)

            n, K   = X.shape[0], self.n_states
            xi_sum = np.zeros((K, K))
            for t in range(n - 1):
                xi_t = (alpha[t][:, None] * self.A *
                        B[t+1][None, :] * beta[t+1][None, :])
                denom = xi_t.sum()
                xi_sum += xi_t / max(denom, 1e-300)

            # M-step: update parameters
            self.pi_0 = gamma[0] / max(gamma[0].sum(), 1e-300)
            # Transition matrix
            row_sums = xi_sum.sum(axis=1, keepdims=True)
            self.A   = xi_sum / np.clip(row_sums, 1e-300, None)

            # Emission parameters
            d = X.shape[1]
            for k in range(K):
                w_k = gamma[:, k]
                w_sum = max(w_k.sum(), 1e-300)
                self.mu[k] = (w_k[:, None] * X).sum(axis=0) / w_sum
                diff         = X - self.mu[k]
                self.sigma[k] = (w_k[:, None, None] * (diff[:, :, None] * diff[:, None, :])).sum(axis=0) / w_sum
                self.sigma[k] += 1e-6 * np.eye(d)

            # Convergence check
            if abs(log_ll - prev_ll) < self.tol:
                break
            prev_ll = log_ll

        self.fitted    = True
        self.log_ll    = log_ll
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Return most likely state sequence (Viterbi)."""
        if not self.fitted:
            raise RuntimeError("Model not fitted")
        B = self._emission_matrix(X)
        # Simplified: use highest posterior probability at each step
        B_f  = self._forward(B)
        alpha = B_f[0]
        scale = B_f[1]
        beta  = self._backward(B, scale)
        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True)
        return np.argmax(gamma, axis=1), gamma

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return posterior state probabilities for each observation."""
        _, gamma = self.predict(X)
        return gamma


# ---------------------------------------------------------------------------
# Regime detector (high-level API)
# ---------------------------------------------------------------------------

_REGIME_LABELS = {0: "Bear", 1: "Sideways", 2: "Bull"}
_REGIME_COLORS = {"Bull": "#16a34a", "Bear": "#dc2626", "Sideways": "#f59e0b"}

# Factor weight multipliers per regime
# Bull: ride momentum. Bear: hide in quality. Sideways: balanced.
REGIME_WEIGHT_MULTIPLIERS = {
    "Bull":     {"sentiment": 1.0, "momentum": 1.4, "quality": 0.8, "value": 0.8},
    "Bear":     {"sentiment": 1.3, "momentum": 0.6, "quality": 1.5, "value": 1.0},
    "Sideways": {"sentiment": 1.0, "momentum": 1.0, "quality": 1.0, "value": 1.0},
}


def detect_regime(
    ticker: str = NIFTY_TICKER,
    lookback_days: int = 252,
    n_states: int = 3,
) -> dict:
    """
    Detect current market regime using a 3-state Gaussian HMM.

    Features used: [daily_return, abs(daily_return)] — captures both
    direction and volatility, which together identify regime better
    than either alone.

    Returns:
      current_regime  — Bull | Bear | Sideways
      current_proba   — probability of each regime right now
      history         — regime label for each trading day (for chart)
      transition_matrix — how likely is a regime shift?
      regime_stats    — mean return and volatility per regime
    """
    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=lookback_days + 30)).strftime("%Y-%m-%d")

    try:
        df = yf.download(ticker, start=start, end=end,
                         progress=False, auto_adjust=True)
        prices = df["Close"].squeeze().dropna()
    except Exception as e:
        return {"error": f"Could not download {ticker}: {e}"}

    if len(prices) < 60:
        return {"error": "Insufficient price data for regime detection"}

    daily_ret  = prices.pct_change().dropna()
    abs_ret    = daily_ret.abs()

    # Feature matrix: (T, 2)
    X = np.column_stack([daily_ret.values, abs_ret.values])

    # Fit HMM
    hmm = GaussianHMM(n_states=n_states, n_iter=150, tol=1e-5)
    hmm.fit(X)
    states, proba = hmm.predict(X)

    # Label states: sort by mean return — lowest = Bear, highest = Bull
    state_means = [X[states == k, 0].mean() if (states == k).sum() > 0 else 0
                   for k in range(n_states)]
    sorted_states = np.argsort(state_means)   # [bear_id, sideways_id, bull_id]
    label_map = {sorted_states[0]: "Bear",
                 sorted_states[1]: "Sideways",
                 sorted_states[2]: "Bull"}

    # Current regime
    current_state = int(states[-1])
    current_label = label_map[current_state]
    current_proba = {label_map[k]: round(float(proba[-1, k]), 4) for k in range(n_states)}

    # Regime history for charting
    dates   = daily_ret.index
    history = [
        {
            "date":   str(dates[i].date()),
            "regime": label_map[int(states[i])],
            "return_pct": round(float(X[i, 0]) * 100, 3),
        }
        for i in range(len(states))
    ]

    # Regime statistics
    regime_stats = {}
    for k in range(n_states):
        mask = states == k
        if mask.sum() > 0:
            label = label_map[k]
            rets  = X[mask, 0]
            regime_stats[label] = {
                "n_days":          int(mask.sum()),
                "pct_of_time":     round(mask.sum() / len(states) * 100, 1),
                "avg_daily_ret":   round(float(rets.mean()) * 100, 3),
                "avg_daily_vol":   round(float(X[mask, 1].mean()) * 100, 3),
                "annualised_ret":  round(float(rets.mean()) * 252 * 100, 2),
                "annualised_vol":  round(float(X[mask, 1].mean()) * np.sqrt(252) * 100, 2),
            }

    # Transition matrix with labels
    transition = {}
    for i in range(n_states):
        from_label = label_map[i]
        transition[from_label] = {}
        for j in range(n_states):
            transition[from_label][label_map[j]] = round(float(hmm.A[i, j]), 4)

    # Regime-conditioned factor weight multipliers
    weight_adjustments = REGIME_WEIGHT_MULTIPLIERS[current_label]

    return {
        "ticker":          ticker,
        "lookback_days":   lookback_days,
        "current_regime":  current_label,
        "current_proba":   current_proba,
        "regime_colour":   _REGIME_COLORS[current_label],
        "regime_stats":    regime_stats,
        "transition_matrix": transition,
        "factor_weight_adjustments": weight_adjustments,
        "history":         history[-90:],   # last 90 days for chart
        "model_log_ll":    round(float(hmm.log_ll), 2),
        "interpretation": (
            f"Current regime: {current_label} "
            f"({current_proba[current_label]*100:.0f}% probability). "
            + (
                "In bull regimes, momentum signals are more reliable. "
                "Increase position sizes gradually."
                if current_label == "Bull" else
                "In bear regimes, prioritise capital preservation. "
                "Weight quality and sentiment signals more heavily."
                if current_label == "Bear" else
                "Sideways/volatile regime. No strong directional bias. "
                "Range-trading and mean-reversion strategies work better."
            )
        ),
        "computed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def regime_conditioned_alpha(ticker: str) -> dict:
    """
    Compute alpha score adjusted for current market regime.

    Pipeline:
      1. Detect current Nifty regime via HMM
      2. Adjust alpha model factor weights based on regime
      3. Recompute alpha score with regime-conditioned weights
      4. Return both raw and regime-adjusted scores

    This is the full original algorithm combining HMM + multi-factor model.
    """
    from alpha_model import compute_alpha_score, FACTOR_WEIGHTS

    # Detect regime
    print(f"  Detecting market regime...")
    regime = detect_regime(NIFTY_TICKER)
    if "error" in regime:
        # Fall back to standard alpha
        return compute_alpha_score(ticker)

    current_regime = regime["current_regime"]
    multipliers    = regime["factor_weight_adjustments"]

    # Adjust weights
    base_weights = FACTOR_WEIGHTS.copy()
    adjusted = {k: v * multipliers[k] for k, v in base_weights.items()}
    # Renormalise to sum to 1
    total    = sum(adjusted.values())
    adjusted = {k: round(v / total, 4) for k, v in adjusted.items()}

    print(f"  Regime: {current_regime}. Adjusted weights: {adjusted}")

    # Compute alpha with adjusted weights
    raw_alpha      = compute_alpha_score(ticker, weights=base_weights)
    adjusted_alpha = compute_alpha_score(ticker, weights=adjusted)

    return {
        "ticker":         ticker,
        "regime":         current_regime,
        "regime_proba":   regime["current_proba"],
        "base_weights":   base_weights,
        "regime_weights": adjusted,
        "raw_alpha_score":      raw_alpha["alpha_score"],
        "adjusted_alpha_score": adjusted_alpha["alpha_score"],
        "signal":         adjusted_alpha["signal"],
        "factors":        adjusted_alpha["factors"],
        "contributions":  adjusted_alpha["contributions"],
        "regime_interpretation": regime["interpretation"],
        "computed_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 65)
    print("Regime Detector — Gaussian HMM on Nifty 50")
    print("=" * 65)

    print("\n1. Fitting 3-state HMM on Nifty 50 (last 2 years)...")
    regime = detect_regime(NIFTY_TICKER, lookback_days=504)

    if "error" in regime:
        print(f"   Error: {regime['error']}")
    else:
        print(f"\n   Current regime : {regime['current_regime']}")
        print(f"   Probabilities  : {regime['current_proba']}")
        print(f"   {regime['interpretation']}")

        print(f"\n   Regime statistics:")
        for label, stats in regime["regime_stats"].items():
            print(f"\n   [{label}]")
            print(f"     Days in regime    : {stats['n_days']} ({stats['pct_of_time']}% of time)")
            print(f"     Avg daily return  : {stats['avg_daily_ret']:+.3f}%")
            print(f"     Annualised return : {stats['annualised_ret']:+.1f}%")
            print(f"     Annualised vol    : {stats['annualised_vol']:.1f}%")

        print(f"\n   Transition matrix (row=from, col=to):")
        labels = ["Bull", "Bear", "Sideways"]
        print(f"   {'':12s}" + "".join(f"{l:>12s}" for l in labels))
        for from_l in labels:
            if from_l in regime["transition_matrix"]:
                row = regime["transition_matrix"][from_l]
                print(f"   {from_l:12s}" +
                      "".join(f"{row.get(to_l, 0):12.4f}" for to_l in labels))

        print(f"\n   Factor weight adjustments in {regime['current_regime']} regime:")
        for factor, mult in regime["factor_weight_adjustments"].items():
            print(f"     {factor:12s}  ×{mult}")

    print("\n2. Regime-conditioned alpha for HDFCBANK.NS...")
    print("   (combines HMM regime + four-factor alpha)")
    result = regime_conditioned_alpha("HDFCBANK.NS")
    if "adjusted_alpha_score" in result:
        print(f"   Regime          : {result['regime']}")
        print(f"   Raw alpha       : {result['raw_alpha_score']:+.1f}")
        print(f"   Adjusted alpha  : {result['adjusted_alpha_score']:+.1f}  → {result['signal']}")
        print(f"   Regime weights  : {result['regime_weights']}")

    print("\n" + "=" * 65)
    print("regime_detector.py test complete")
    print("=" * 65)
