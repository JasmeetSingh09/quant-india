"""
factor_correlation.py — are six factors actually six signals?

The model states six weights summing to 100%. That presentation only means what
it appears to mean if the six are measuring different things. If two of them
correlate at 0.9 across the universe, the pair is one signal carrying their
combined weight, and a reader looking at the weight table is being told
something false about how the score is built.

Computed across the whole scored universe, because a correlation on a handful
of stocks is noise. Pairs are formed on complete cases only: dropping an entire
row because one factor is missing would silently shrink the sample for every
other pair too.

This reports. It does not adjust weights — a weight changed because two factors
correlate is a weight fitted to the data, which is the thing this project
spends most of its effort not doing.
"""

from datetime import datetime

FACTORS_V2 = ("momentum", "quality", "growth", "value", "sentiment", "low_risk")
FACTORS_V1 = ("momentum", "quality", "value", "sentiment")

# Above this, two factors are close enough to being one that the weight table
# is misleading. Chosen before looking at the data.
HIGH_CORR = 0.7
MIN_PAIRS = 30


def _corr(xa, xb):
    n = len(xa)
    if n < MIN_PAIRS:
        return None
    ma = sum(xa) / n
    mb = sum(xb) / n
    va = sum((x - ma) ** 2 for x in xa)
    vb = sum((x - mb) ** 2 for x in xb)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((xa[i] - ma) * (xb[i] - mb) for i in range(n))
    return cov / ((va ** 0.5) * (vb ** 0.5))


def matrix() -> dict:
    try:
        from db import get_conn
        conn = get_conn()
    except Exception as e:
        return {"available": False,
                "reason": f"No database connection ({type(e).__name__})."}

    cols, source, rows = None, None, []
    try:
        try:
            r = conn.execute(
                "SELECT momentum, quality, growth, value, sentiment, low_risk "
                "FROM factor_history WHERE model = 'v2'").fetchall()
        except Exception:
            r = []
        if len(r) >= 50:
            cols, source, rows = FACTORS_V2, "factor_history (six-factor model)", r
        else:
            r = conn.execute(
                "SELECT momentum, quality, value, sentiment FROM alpha_scan2 "
                "WHERE alpha_score IS NOT NULL AND error IS NULL").fetchall()
            cols, source, rows = FACTORS_V1, "universe scan (four-factor model)", r
    except Exception as e:
        conn.close()
        return {"available": False,
                "reason": f"Could not read factor scores ({type(e).__name__})."}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if len(rows) < MIN_PAIRS:
        return {"available": False, "rows": len(rows), "source": source,
                "reason": (f"Only {len(rows)} scored rows. A correlation on "
                           f"fewer than {MIN_PAIRS} stocks is noise, so none is "
                           f"reported rather than reporting a misleading one.")}

    series = {name: [] for name in cols}
    for row in rows:
        for i, name in enumerate(cols):
            series[name].append(row[i])

    out, high = {}, []
    for a in cols:
        out[a] = {}
        for b in cols:
            xa, xb = [], []
            for va, vb in zip(series[a], series[b]):
                if va is None or vb is None:
                    continue
                try:
                    xa.append(float(va))
                    xb.append(float(vb))
                except (TypeError, ValueError):
                    continue
            c = _corr(xa, xb)
            out[a][b] = None if c is None else round(c, 4)
            if c is not None and a < b and abs(c) >= HIGH_CORR:
                high.append({"a": a, "b": b, "corr": round(c, 4), "n": len(xa)})

    weights = {}
    try:
        from alpha_v2 import WEIGHTS_V2
        weights = dict(WEIGHTS_V2)
    except Exception:
        pass

    for h in high:
        h["combined_weight_pct"] = round(
            (weights.get(h["a"], 0) + weights.get(h["b"], 0)) * 100, 1)

    return {
        "available": True,
        "source": source,
        "rows": len(rows),
        "factors": list(cols),
        "matrix": out,
        "threshold": HIGH_CORR,
        "redundant_pairs": high,
        "verdict": (
            f"{len(high)} factor pair(s) correlate at or above {HIGH_CORR}. "
            f"Each such pair is effectively one signal carrying their combined "
            f"weight, so the weight table overstates how many independent "
            f"things the score is built from."
            if high else
            f"No factor pair reaches {HIGH_CORR}. On this universe the six are "
            f"measuring materially different things, so the stated weights mean "
            f"what they appear to mean."),
        "does_not_adjust": (
            "This reports only. Re-weighting because two factors correlate "
            "would be fitting weights to the data, which is exactly what the "
            "rest of this project avoids."),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
