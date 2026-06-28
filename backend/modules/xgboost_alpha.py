"""
xgboost_alpha.py — Gradient-boosted (XGBoost) return predictor for NSE stocks.

Upgrades the linear 4-factor alpha model with a tree-based model that can learn
NONLINEAR interactions between factors. Trained with strict WALK-FORWARD
validation (train on the past, test on the unseen future) so the results are
honest — no look-ahead leakage.

It ALSO trains a Logistic Regression on the same features as a baseline, so we
can answer the real question: does the fancy model actually beat the simple one?

run_comparison() returns out-of-sample AUC + accuracy for both models so we can
decide empirically whether XGBoost is worth keeping.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# A reasonable NSE universe (large + mid caps) to build the training panel
UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS", "LT.NS",
    "HINDUNILVR.NS", "BAJFINANCE.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
    "WIPRO.NS", "TATAMOTORS.NS", "TATASTEEL.NS", "AXISBANK.NS", "NESTLEIND.NS",
    "HCLTECH.NS", "ASIANPAINT.NS", "ULTRACEMCO.NS", "POWERGRID.NS", "NTPC.NS",
]


def _features_for(prices: pd.Series) -> pd.DataFrame:
    """Build a monthly feature panel for one stock from its daily prices."""
    monthly_idx = prices.resample("ME").last().index
    rows = []
    for dt in monthly_idx:
        hist = prices.loc[:dt]
        n = len(hist)
        if n < 252:           # need ~1yr of history
            continue
        p = float(hist.iloc[-1])
        def ret(days):
            return p / float(hist.iloc[-days]) - 1 if n > days else np.nan
        daily = hist.pct_change().dropna()
        feat = {
            "date":       dt,
            "ret_1m":     ret(21),
            "ret_3m":     ret(63),
            "ret_6m":     ret(126),
            "ret_12m":    ret(252),
            "vol_1m":     float(daily.iloc[-21:].std() * np.sqrt(252)),
            "vol_3m":     float(daily.iloc[-63:].std() * np.sqrt(252)),
            "dist_52w_hi":p / float(hist.iloc[-252:].max()) - 1,
            "above_200d": p / float(hist.iloc[-200:].mean()) - 1,
        }
        rows.append(feat)
    df = pd.DataFrame(rows).set_index("date")
    # target: did the stock rise over the NEXT month?
    fwd = prices.resample("ME").last().pct_change().shift(-1)
    df["target"] = (fwd.reindex(df.index) > 0).astype(int)
    return df.dropna()


def build_panel(universe: list = None, start_year: int = 2018) -> pd.DataFrame:
    """Build a stacked panel of features+target across the whole universe."""
    universe = universe or UNIVERSE
    start = f"{start_year}-01-01"
    end   = datetime.now().strftime("%Y-%m-%d")
    frames = []
    for t in universe:
        try:
            px = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)["Close"].squeeze()
            if len(px) > 300:
                f = _features_for(px)
                f["ticker"] = t
                frames.append(f)
        except Exception:
            pass
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index()


def run_comparison(start_year: int = 2018, split: float = 0.7) -> dict:
    """
    Train XGBoost vs Logistic Regression on the same features with a strict
    time-ordered (walk-forward) split. Returns out-of-sample metrics for both.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, accuracy_score
    import xgboost as xgb

    panel = build_panel(start_year=start_year)
    if panel.empty or len(panel) < 200:
        return {"error": "Could not build enough data for comparison"}

    feat_cols = ["ret_1m", "ret_3m", "ret_6m", "ret_12m",
                 "vol_1m", "vol_3m", "dist_52w_hi", "above_200d"]

    # Time-ordered split — train on the past, test on the unseen future
    panel = panel.sort_index()
    cut   = panel.index[int(len(panel) * split)]
    train = panel[panel.index <= cut]
    test  = panel[panel.index > cut]

    Xtr, ytr = train[feat_cols].values, train["target"].values
    Xte, yte = test[feat_cols].values,  test["target"].values

    # Baseline: Logistic Regression
    scaler = StandardScaler()
    Xtr_s, Xte_s = scaler.fit_transform(Xtr), scaler.transform(Xte)
    lr = LogisticRegression(max_iter=1000).fit(Xtr_s, ytr)
    lr_proba = lr.predict_proba(Xte_s)[:, 1]

    # XGBoost
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, eval_metric="logloss",
    )
    model.fit(Xtr, ytr)
    xgb_proba = model.predict_proba(Xte)[:, 1]

    def metrics(proba):
        return {
            "auc": round(float(roc_auc_score(yte, proba)), 4),
            "accuracy": round(float(accuracy_score(yte, (proba > 0.5).astype(int))), 4),
        }

    lr_m  = metrics(lr_proba)
    xgb_m = metrics(xgb_proba)
    base_rate = round(float(yte.mean()), 4)   # naive "always up" accuracy

    # Feature importance from XGBoost
    importance = dict(zip(feat_cols, [round(float(v), 4) for v in model.feature_importances_]))
    importance = dict(sorted(importance.items(), key=lambda x: -x[1]))

    winner = "XGBoost" if xgb_m["auc"] > lr_m["auc"] else "Logistic"
    useful = xgb_m["auc"] > 0.53   # > ~0.53 AUC = some real edge over coin-flip

    return {
        "train_samples": len(train), "test_samples": len(test),
        "test_period": f"{str(test.index[0].date())} to {str(test.index[-1].date())}",
        "logistic":  lr_m,
        "xgboost":   xgb_m,
        "naive_base_rate": base_rate,
        "xgb_feature_importance": importance,
        "winner": winner,
        "xgboost_has_edge": useful,
        "verdict": (
            f"XGBoost AUC {xgb_m['auc']} vs Logistic {lr_m['auc']} (out-of-sample). "
            + ("XGBoost shows a real edge — worth keeping." if useful and winner == "XGBoost"
               else "No meaningful edge over the simple model / coin-flip — honest result, "
                    "consistent with near-efficient markets.")
        ),
    }


if __name__ == "__main__":
    print("=" * 60)
    print("XGBoost vs Logistic — walk-forward NSE return prediction")
    print("=" * 60)
    print("\nBuilding panel + training (this takes a minute)...")
    r = run_comparison(start_year=2018)
    if "error" in r:
        print("Error:", r["error"])
    else:
        print(f"\nTrain: {r['train_samples']} samples | Test: {r['test_samples']} ({r['test_period']})")
        print(f"\nLogistic Regression : AUC {r['logistic']['auc']}  acc {r['logistic']['accuracy']}")
        print(f"XGBoost             : AUC {r['xgboost']['auc']}  acc {r['xgboost']['accuracy']}")
        print(f"Naive base rate     : {r['naive_base_rate']}")
        print(f"\nTop features (XGBoost): {list(r['xgb_feature_importance'].items())[:4]}")
        print(f"\nVERDICT: {r['verdict']}")
