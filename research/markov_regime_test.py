"""
markov_regime_test.py — the pre-registered test of a 2-state Markov-switching market regime.

Spec: docs/PREREG_MARKOV_SWITCHING_REGIME_2026-10-05.md. Every number below (seed, window,
threshold, lags, levels, markets, dates) comes from it and may not change after the real run.

    python research/markov_regime_test.py plumbing   # simulated data only; allowed before the run
    python research/markov_regime_test.py run        # the one real run

`run` refuses to start unless the pre-registration (final name, not DRAFT) and this file are
committed with no local changes, so the rules provably came before the numbers.
"""
import json
import os
import subprocess
import sys
import time
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "backend", "modules"))

SEED = 2026
SEARCH_REPS = 20
MIN_WEEKS = 260
PROB_CUT = 0.5
HAC_LAGS = 3
LEVEL_PRIMARY = 0.05 / 2
LEVEL_CONFIRM = 0.05 / 4
MIN_SPELL_WEEKS = 4
NIFTY = "^NSEI"
CONFIRM = ["^NSEBANK", "^GSPC", "^FTSE", "^N225"]
DATA_END = "2026-09-30"
FIRST_SIGNAL = "2012-09"          # informational: the prereg's first month-end with 260 weeks of Nifty
PREREG = "docs/PREREG_MARKOV_SWITCHING_REGIME_2026-10-05.md"


# ── model ────────────────────────────────────────────────────────────────────

def weekly_returns(close: pd.Series, asof=None) -> pd.Series:
    """Weekly log returns in percent from Friday (or last trading day of the week) closes.
    Only weeks that END on or before `asof` are kept, so no partial future week is used."""
    c = close if asof is None else close[close.index <= asof]
    w = c.resample("W-FRI").last().dropna()
    if asof is not None:
        w = w[w.index <= pd.Timestamp(asof)] if len(w) and w.index[-1] > pd.Timestamp(asof) else w
    return (100 * np.log(w).diff()).dropna()


def fit_ms(r: pd.Series):
    """2 regimes, switching mean and variance. Returns (high-risk filtered prob series, converged, params)."""
    np.random.seed(SEED)                        # statsmodels' start search draws from np.random
    mod = MarkovRegression(r.values, k_regimes=2, trend="c", switching_variance=True)
    res = mod.fit(search_reps=SEARCH_REPS, disp=0)
    names = list(mod.param_names)
    p = dict(zip(names, np.asarray(res.params)))
    high = int(np.argmax([p["sigma2[0]"], p["sigma2[1]"]]))       # fixed rule: higher variance = High-risk
    filt = pd.Series(np.asarray(res.filtered_marginal_probabilities)[:, high], index=r.index)
    conv = bool(res.mle_retvals.get("converged", True)) if isinstance(res.mle_retvals, dict) else True
    low = 1 - high
    # statsmodels names the free transition probabilities p[0->0] and p[1->0].
    stay = {0: p.get("p[0->0]"), 1: None if p.get("p[1->0]") is None else 1 - p["p[1->0]"]}
    params = {"mean_high": p[f"const[{high}]"], "mean_low": p[f"const[{low}]"],
              "var_high": p[f"sigma2[{high}]"], "var_low": p[f"sigma2[{low}]"],
              "p_stay_high": stay[high], "p_stay_low": stay[low]}
    return filt, conv, params


# ── signals and outcomes ─────────────────────────────────────────────────────

def month_ends(close: pd.Series):
    return close.groupby(close.index.to_period("M")).apply(lambda s: s.index[-1]).tolist()


def outcomes(close: pd.Series, start, end):
    path = close[(close.index >= start) & (close.index <= end)]
    lr = np.log(path).diff().dropna()
    return {"vol": float(lr.std(ddof=1) * np.sqrt(252) * 100),
            "drawdown": float((1 - (path / path.cummax()).min()) * 100),      # depth, positive
            "ret": float((path.iloc[-1] / path.iloc[0] - 1) * 100), "days": int(len(lr))}


def trend_state(close: pd.Series, buffer=0.02) -> pd.Series:
    ma = close.rolling(200).mean()
    out, cur = {}, None
    for d in close.index[199:]:
        x = close[d] / ma[d] - 1
        if cur is None:
            cur = "up" if x >= 0 else "down"
        elif cur == "up" and x < -buffer:
            cur = "down"
        elif cur == "down" and x > buffer:
            cur = "up"
        out[d] = cur
    return pd.Series(out, dtype=object)


def spells(labels) -> list:
    s = pd.Series(list(labels))
    return s.groupby((s != s.shift()).cumsum()).size().tolist()


def hac(y, X):
    X = sm.add_constant(pd.DataFrame(X).astype(float))
    res = sm.OLS(np.asarray(y, dtype=float), X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    return {k: {"coef": round(float(res.params[k]), 4), "p": float(res.pvalues[k])} for k in X.columns if k != "const"} \
        | {"n": int(res.nobs), "mean_when_0": round(float(res.params["const"]), 4)}


def walk_forward(close: pd.Series, data_end, log=None):
    from market_risk import classify
    mr = classify(close)["state"]
    tr = trend_state(close)
    ends = [m for m in month_ends(close) if m <= pd.Timestamp(data_end)]
    rows, dropped = [], []
    for i, m in enumerate(ends[:-1]):
        nxt = ends[i + 1]
        if nxt.to_period("M") != (m.to_period("M") + 1):
            continue
        r = weekly_returns(close, m)
        if len(r) < MIN_WEEKS:
            continue
        try:
            filt, conv, _ = fit_ms(r)
        except Exception as e:
            dropped.append({"month": str(m)[:7], "why": f"{type(e).__name__}"}); continue
        if not conv:
            dropped.append({"month": str(m)[:7], "why": "did not converge"}); continue
        prob = float(filt.iloc[-1])
        o = outcomes(close, m, nxt)
        rows.append({"month": str(m)[:10], "prob_high": round(prob, 4), "high": int(prob > PROB_CUT),
                     "elevated": None if pd.isna(mr.get(m)) or mr.get(m) is None else int(mr.get(m) == "Elevated"),
                     "downtrend": None if m not in tr.index else int(tr[m] == "down"), **o})
        if log and len(rows) % 24 == 0:
            log(f"  {str(m)[:7]}  {len(rows)} months fitted")
    return pd.DataFrame(rows), dropped


def evaluate(close: pd.Series, data_end, primary=True, log=None):
    t0 = time.time()
    df, dropped = walk_forward(close, data_end, log)
    out = {"months": len(df), "first_signal": df["month"].iloc[0][:7] if len(df) else None,
           "dropped": dropped, "share_high": round(float(df["high"].mean()), 3) if len(df) else None}
    if len(df) < 24:
        out["error"] = "fewer than 24 usable months"; return out, df
    out["P1_vol"] = hac(df["vol"], df[["high"]])
    out["P2_drawdown"] = hac(df["drawdown"], df[["high"]])
    m_sp = spells(df["high"])
    final_r = weekly_returns(close, data_end)
    filt, conv, params = fit_ms(final_r)
    w_sp = spells((filt > PROB_CUT).astype(int))
    out["persistence"] = {"monthly_median_spell_weeks": round(float(np.median(m_sp)) * 52 / 12, 1),
                          "weekly_median_spell_weeks": float(np.median(w_sp)), "final_fit_converged": conv,
                          "passes": float(np.median(m_sp)) * 52 / 12 >= MIN_SPELL_WEEKS and float(np.median(w_sp)) >= MIN_SPELL_WEEKS}
    out["final_fit_params"] = {k: (round(float(v), 4) if v is not None else None) for k, v in params.items()}
    if primary:
        both = df.dropna(subset=["elevated"])
        out["S1_adds_to_market_risk"] = hac(both["vol"], both[["high", "elevated"]])
        out["S2_direction"] = hac(df["ret"], df[["high"]])
        cmp = df.dropna(subset=["elevated", "downtrend"])
        out["comparison"] = {
            "market_risk_vol": hac(cmp["vol"], cmp[["elevated"]]),
            "market_risk_drawdown": hac(cmp["drawdown"], cmp[["elevated"]]),
            "trend_vol": hac(cmp["vol"], cmp[["downtrend"]]),
            "trend_drawdown": hac(cmp["drawdown"], cmp[["downtrend"]]),
            "trend_median_spell_months": float(np.median(spells(cmp["downtrend"]))),
        }
    out["seconds"] = round(time.time() - t0)
    return out, df


def passed(test, level):
    return test["high"]["coef"] > 0 and test["high"]["p"] < level


# ── data ─────────────────────────────────────────────────────────────────────

def yahoo_close(ticker, start="1980-01-01", end=DATA_END):
    import yfinance as yf
    end_excl = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")     # yfinance end is exclusive
    d = yf.download(ticker, start=start, end=end_excl, progress=False, auto_adjust=True)
    c = d["Close"]
    c = c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c
    return c.dropna()


# ── plumbing check (simulated data only) ─────────────────────────────────────

def simulated(regimes=True, seed=7, start="2007-09-17", end=DATA_END):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, end)
    state, states = 0, []
    for _ in idx:
        if regimes and rng.random() < 1 / 60:          # mean spell about 60 trading days
            state = 1 - state
        states.append(state)
    states = np.array(states)
    sd = np.where(states == 1, 0.018, 0.007) if regimes else np.full(len(idx), 0.011)
    mu = np.where(states == 1, -0.0004, 0.0004) if regimes else np.full(len(idx), 0.0002)
    r = rng.normal(mu, sd)
    return pd.Series(100 * np.exp(np.cumsum(r)), index=idx), pd.Series(states, index=idx)


def plumbing():
    report = {"written": datetime.now().isoformat(timespec="seconds"), "note": "simulated data only; no market data used"}
    close, truth = simulated(True)
    res, _ = evaluate(close, DATA_END, primary=False, log=print)
    fr = weekly_returns(close, DATA_END)
    filt, _, _ = fit_ms(fr)
    wk_truth = truth.resample("W-FRI").mean().reindex(fr.index).round()
    acc = float(((filt > PROB_CUT).astype(int) == wk_truth).mean())
    report["with_regimes"] = {"P1_vol": res["P1_vol"]["high"], "P2_drawdown": res["P2_drawdown"]["high"],
                              "persistence": res["persistence"], "weekly_state_accuracy": round(acc, 3),
                              "months": res["months"], "dropped": len(res["dropped"])}
    nulls = []
    for s in (11, 12, 13):
        c0, _ = simulated(False, seed=s)
        r0, _ = evaluate(c0, DATA_END, primary=False)
        nulls.append({"seed": s, "P1_p": r0["P1_vol"]["high"]["p"], "P1_coef": r0["P1_vol"]["high"]["coef"]})
    report["no_regimes"] = nulls
    report["checks"] = {
        "finds regimes that exist (P1 passes)": passed(res["P1_vol"], LEVEL_PRIMARY),
        "weekly states match the truth at least 80%": acc >= 0.80,
        "persistence gate passes on persistent regimes": res["persistence"]["passes"],
        "no false signal on data without regimes (all 3 nulls fail P1)": all(not (n["P1_coef"] > 0 and n["P1_p"] < LEVEL_PRIMARY) for n in nulls),
    }
    report["plumbing_ok"] = all(report["checks"].values())
    path = os.path.join(REPO, "docs", "markov_regime_plumbing_2026-10-05.json")
    json.dump(report, open(path, "w"), indent=1, default=str)
    print(json.dumps(report["checks"], indent=1), "\nplumbing_ok:", report["plumbing_ok"], "\nwritten:", path)


# ── the one real run ─────────────────────────────────────────────────────────

def _committed_and_clean(paths):
    for p in paths:
        if not os.path.exists(os.path.join(REPO, p)):
            return f"{p} does not exist"
        if subprocess.run(["git", "ls-files", "--error-unmatch", p], cwd=REPO, capture_output=True).returncode:
            return f"{p} is not committed"
        if subprocess.run(["git", "status", "--porcelain", p], cwd=REPO, capture_output=True, text=True).stdout.strip():
            return f"{p} has uncommitted changes"
    return None


def run():
    why = _committed_and_clean([PREREG, "research/markov_regime_test.py", "docs/markov_regime_plumbing_2026-10-05.json"])
    if why:
        sys.exit(f"Refusing the real run: {why}. The rules and the runner must be committed first.")
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    result = {"prereg": PREREG, "runner_commit": commit, "run_at": datetime.now().isoformat(timespec="seconds"),
              "data": f"Yahoo daily closes to {DATA_END}"}
    print("Nifty 50 ...")
    nifty, df = evaluate(yahoo_close(NIFTY), DATA_END, primary=True, log=print)
    result["nifty"] = nifty
    p1, p2 = passed(nifty["P1_vol"], LEVEL_PRIMARY), passed(nifty["P2_drawdown"], LEVEL_PRIMARY)
    result["verdict"] = {"persistence_gate": nifty["persistence"]["passes"], "P1_passed": p1, "P2_passed": p2}
    if p1:
        conf = {}
        for t in CONFIRM:
            print(f"confirmation: {t} ...")
            r, _ = evaluate(yahoo_close(t), DATA_END, primary=False, log=print)
            conf[t] = {"months": r.get("months"), "P1_vol": r.get("P1_vol", {}).get("high"),
                       "passed": "P1_vol" in r and passed(r["P1_vol"], LEVEL_CONFIRM),
                       "persistence": r.get("persistence"), "first_signal": r.get("first_signal")}
        result["confirmation"] = conf
        result["verdict"]["confirmed_markets"] = sum(v["passed"] for v in conf.values())
    v = result["verdict"]
    v["ship"] = bool(v["persistence_gate"] and v["P1_passed"] and v.get("confirmed_markets", 0) >= 3)
    if v["ship"]:
        s1 = nifty["S1_adds_to_market_risk"]["high"]
        v["wording"] = ("adds information beyond the market-risk reading" if s1["coef"] > 0 and s1["p"] < 0.05
                        else "agrees with the market-risk reading and adds nothing new")
    stamp = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(REPO, "docs", f"markov_regime_result_{stamp}.json")
    json.dump(result, open(path, "w"), indent=1, default=str)
    df.to_csv(os.path.join(REPO, "docs", f"markov_regime_months_{stamp}.csv"), index=False)
    print(json.dumps(result["verdict"], indent=1), "\nwritten:", path)


if __name__ == "__main__":
    {"plumbing": plumbing, "run": run}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
