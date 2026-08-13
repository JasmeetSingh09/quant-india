"""
distress_study.py — does the distress penalty identify real underperformers?

What this is NOT: a point-in-time backtest of the old vs corrected model.
yfinance serves only TODAY's balance sheet, so rescoring history would use
fundamentals that were not knowable at the time. That study needs a
point-in-time fundamentals source and is not attempted here.

What this IS: a cross-sectional test of the distress rule itself. Split the
universe on the flags the corrected model uses (negative equity, D/E > 2x,
losses, negative operating cash flow) and compare realised forward returns.

The look-ahead is stated, not hidden: today's balance sheet is used to classify
a stock, then its PAST return is measured. Survivorship also applies — delisted
names are absent. So this can support "distressed names underperformed" as a
descriptive fact; it cannot prove the live model will profit from the rule.
"""
import sys, warnings, json, math, random
warnings.filterwarnings("ignore")
sys.path.insert(0, r"C:\Users\seeraj\OneDrive\Documents\Desktop\code\ai_stock\backend\modules")
import numpy as np, yfinance as yf
import alpha_model as AM


def _num(v):
    """Yahoo occasionally returns these fields as strings; comparing a str to an
    int raised TypeError and killed the whole run mid-sample."""
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def flags_for(ticker):
    """Recompute the corrected model's distress flags from current fundamentals."""
    i = AM._ticker_info(ticker)
    if not i or not i.get("marketCap"):
        return None
    bv, sh = _num(i.get("bookValue")), _num(i.get("sharesOutstanding"))
    debt, ni = _num(i.get("totalDebt")), _num(i.get("netIncomeToCommon"))
    ocf, pb, pe = _num(i.get("operatingCashflow")), _num(i.get("priceToBook")), _num(i.get("trailingPE"))
    eq = (bv * sh) if (bv and sh) else None
    f = []
    if bv is not None and bv < 0:                                f.append("neg_equity")
    if eq and eq > 0 and debt and debt/eq > 2.0:                  f.append("high_debt")
    if ni is not None and ni < 0:                                 f.append("loss")
    if ocf is not None and ocf < 0:                               f.append("neg_ocf")
    # would the OLD value factor have called it cheap on a broken multiple?
    old_trap = (i.get("priceToBook") is not None and i["priceToBook"] < 0) or \
               (i.get("trailingPE") is not None and i["trailingPE"] < 0)
    return {"flags": f, "old_value_trap": old_trap}


def fwd_returns(tickers):
    """Trailing 6m and 12m returns, batched."""
    out = {}
    try:
        px = yf.download(tickers, period="1y", auto_adjust=True, progress=False,
                         group_by="column", threads=True)
        cl = px["Close"] if "Close" in px else px
    except Exception:
        return out
    for t in tickers:
        try:
            s = cl[t].dropna() if t in cl.columns else None
            if s is None or len(s) < 130:
                continue
            out[t] = {
                "r6":  float(s.iloc[-1] / s.iloc[-126] - 1) * 100,
                "r12": float(s.iloc[-1] / s.iloc[0] - 1) * 100,
            }
        except Exception:
            pass
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 250
    from data_fetcher import NSE_SECTORS
    from stock_universe import get_all_symbols
    raw = get_all_symbols("NSE") or []
    uni = []
    for x in raw:                      # rows may be dicts or plain symbols
        t = (x if isinstance(x, str) else (x.get("symbol") or x.get("ticker") or "")).strip().upper()
        if t:
            uni.append(t if t.endswith(".NS") else t + ".NS")
    uni = sorted(set(uni)) or sorted({t for v in NSE_SECTORS.values() for t in v})
    random.Random(42).shuffle(uni)
    sample = uni[:n]

    print(f"classifying {len(sample)} NSE stocks...", flush=True)
    cls = {}
    for i, t in enumerate(sample, 1):
        try:
            r = flags_for(t)
        except Exception:
            r = None
        if r:
            cls[t] = r
        if i % 50 == 0:
            print(f"  {i}/{len(sample)}", flush=True)

    print(f"classified {len(cls)}; fetching prices...", flush=True)
    rets = {}
    ts = list(cls)
    for i in range(0, len(ts), 60):
        rets.update(fwd_returns(ts[i:i+60]))
        print(f"  prices {min(i+60,len(ts))}/{len(ts)}", flush=True)

    rows = [{"t": t, **cls[t], **rets[t]} for t in cls if t in rets]
    if not rows:
        print("no overlap between classification and price data"); return

    def stat(sub, label):
        if not sub:
            print(f"  {label:34s} n=0"); return
        r6 = [x["r6"] for x in sub]; r12 = [x["r12"] for x in sub]
        print(f"  {label:34s} n={len(sub):4d}  6m median {np.median(r6):+7.1f}%  "
              f"12m median {np.median(r12):+7.1f}%  12m mean {np.mean(r12):+7.1f}%")

    print("\n" + "=" * 92)
    print(f"REALISED RETURNS BY DISTRESS CLASSIFICATION  (n={len(rows)})")
    print("=" * 92)
    clean     = [x for x in rows if not x["flags"]]
    distress  = [x for x in rows if x["flags"]]
    stat(clean,    "no distress flags")
    stat(distress, "one or more distress flags")
    print()
    for fl in ("neg_equity", "high_debt", "loss", "neg_ocf"):
        stat([x for x in rows if fl in x["flags"]], f"flag: {fl}")
    print()
    traps = [x for x in rows if x["old_value_trap"]]
    stat(traps, "old model would call these CHEAP")
    stat([x for x in rows if not x["old_value_trap"]], "valid multiples")

    if clean and distress:
        gap12 = np.median([x["r12"] for x in clean]) - np.median([x["r12"] for x in distress])
        print(f"\n  12m median gap (clean - distressed): {gap12:+.1f} pts")
    json.dump(rows, open("distress_study_rows.json", "w"), indent=1)
    print("\nCaveats: today's balance sheet classifies a PAST return (look-ahead),")
    print("and delisted names are absent (survivorship). Descriptive, not a backtest.")


if __name__ == "__main__":
    main()
