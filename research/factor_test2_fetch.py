"""
factor_test2_fetch.py — download the data for factor test 2, once, and keep it.

For every EQ-series stock in the app's NSE equity list: Yahoo's annual income
statement, balance sheet and cash flow, and daily prices (adjusted closes and
volume) from 2022. Everything is saved to disk so the test runs on exactly the
data it downloaded, and can be rerun without asking Yahoo again.

Resumable: a stock whose file already exists is skipped, so an interrupted run
continues where it stopped. Paced, because Yahoo throttles bursts, and an
answer that comes back empty is retried after a pause rather than saved as
"no data".

The data stays on this machine. It is Yahoo's, and it does not go in the repo.

    python research/factor_test2_fetch.py OUT_DIR
"""

import json
import os
import sqlite3
import sys
import time
import warnings

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_DB = os.path.join(HERE, "..", "backend", "quant_platform.db")
PRICE_START = "2022-01-01"
PAUSE = 0.8
RETRY_WAITS = (5.0, 20.0)
PRICE_BATCH = 40


def universe():
    conn = sqlite3.connect(f"file:{UNIVERSE_DB}?mode=ro", uri=True)
    try:
        return sorted(r[0] for r in conn.execute(
            "SELECT yf_ticker FROM nse_stocks WHERE series = 'EQ' AND yf_ticker IS NOT NULL"))
    finally:
        conn.close()


def frame_to_dict(df):
    """{field: {period_end: value}}, dropping missing values."""
    if df is None or df.empty:
        return {}
    out = {}
    for field in df.index:
        row = {}
        for col in df.columns:
            v = df.at[field, col]
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv == fv:                      # not NaN
                row[str(col.date())] = fv
        if row:
            out[str(field)] = row
    return out


def fetch_statements(ticker):
    import yfinance as yf
    last = None
    for wait in (0.0,) + RETRY_WAITS:
        if wait:
            time.sleep(wait)
        try:
            t = yf.Ticker(ticker)
            got = {"income": frame_to_dict(t.financials),
                   "balance": frame_to_dict(t.balance_sheet),
                   "cashflow": frame_to_dict(t.cashflow)}
            if any(got.values()):
                return got
            last = "empty"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    return {"income": {}, "balance": {}, "cashflow": {}, "error": last}


def fetch_prices(tickers, out_dir):
    import yfinance as yf
    path = os.path.join(out_dir, "prices")
    os.makedirs(path, exist_ok=True)
    todo = [t for t in tickers if not os.path.exists(os.path.join(path, f"{t}.json"))]
    for i in range(0, len(todo), PRICE_BATCH):
        batch = todo[i:i + PRICE_BATCH]
        for wait in (0.0,) + RETRY_WAITS:
            if wait:
                time.sleep(wait)
            try:
                df = yf.download(batch, start=PRICE_START, auto_adjust=True,
                                 progress=False, group_by="ticker", threads=False)
                break
            except Exception:
                df = None
        for t in batch:
            rec = {"close": {}, "volume": {}}
            try:
                sub = df[t] if (df is not None and len(batch) > 1) else df
                for day, c, v in zip(sub.index, sub["Close"], sub["Volume"]):
                    if c == c:
                        rec["close"][str(day.date())] = float(c)
                        rec["volume"][str(day.date())] = float(v) if v == v else 0.0
            except Exception as e:
                rec["error"] = f"{type(e).__name__}"
            with open(os.path.join(path, f"{t}.json"), "w", encoding="utf-8") as fh:
                json.dump(rec, fh)
        print(f"  prices {min(i + PRICE_BATCH, len(todo))}/{len(todo)}", flush=True)
        time.sleep(PAUSE * 3)


def main(out_dir):
    tickers = universe()
    stmt_dir = os.path.join(out_dir, "statements")
    os.makedirs(stmt_dir, exist_ok=True)
    print(f"{len(tickers)} EQ stocks; saving to {out_dir}", flush=True)
    t0 = time.time()
    for i, t in enumerate(tickers, 1):
        path = os.path.join(stmt_dir, f"{t}.json")
        if os.path.exists(path):
            continue
        rec = fetch_statements(t)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        if i % 50 == 0:
            print(f"  statements {i}/{len(tickers)}  {time.time() - t0:.0f}s", flush=True)
        time.sleep(PAUSE)
    print("statements done", flush=True)
    fetch_prices(tickers, out_dir)
    manifest = {"tickers": len(tickers), "price_start": PRICE_START,
                "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "universe_source": "backend/quant_platform.db nse_stocks, series EQ"}
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    print("done", manifest, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
