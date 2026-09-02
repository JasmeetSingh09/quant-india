"""
factor_provenance.py — what the model saw, when, from where.

The factor history records that Growth was 73. It does not record why, and it
cannot be made to later: the inputs were fetched, used, and dropped. Two cycles
of that have already gone by, and a score with no inputs behind it is a number
in a table rather than an observation anyone can check.

This stores the inputs alongside the score, for observations made from here on.

What this is NOT
----------------
It is not a point-in-time fundamentals layer, and calling it one would repeat
the mistake this project has spent weeks removing. Yahoo's `.info` carries no
filing date. Capturing returnOnEquity today records what Yahoo REPORTED on this
date, not what the company had FILED as of it. A restatement changes the former
without touching our observation date, silently. Every such field is therefore
categorised `observation_yahoo` and never `pit_market`, and the catalogue below
says so field by field so a future reader cannot mistake one for the other.

What is reproducible, and what only explains
--------------------------------------------
A score is reproducible when the stored values determine it arithmetically:

    momentum  score = tanh(risk_adj / 1.5)          risk_adj stored -> yes
    value     z-scores from the stock's multiples and the sector aggregate,
              both stored                            -> yes
    quality   composite of piotroski, roe, fcf_yield, all stored -> yes
    sentiment decay-weighted mean over an article set -> yes, if the set is
              stored, which is why articles get their own table

The underlying PRICE SERIES is a different matter. Momentum pulls it from
Yahoo with auto_adjust=True, so it is split- and dividend-adjusted; bhavcopy is
unadjusted. They are not the same series and bhavcopy cannot stand in for it.
The window bounds are recorded as provenance; the series itself is gone, and
this module says gone rather than implying otherwise.

Failure policy
--------------
Nothing here may break a scan. A lost provenance row is a gap in the record; a
raised exception would cost the whole stock, and then the score too.
"""

import hashlib
from datetime import datetime

try:
    from db import get_conn, IS_POSTGRES
except Exception:                                   # pragma: no cover
    from .db import get_conn, IS_POSTGRES

_READY = False

# The five kinds of thing a stored value can be. Kept apart because conflating
# the first two is precisely the error that makes a dataset look
# point-in-time when it is not.
PIT_MARKET = "pit_market"                 # exchange data, true as of its date
OBSERVATION_YAHOO = "observation_yahoo"   # what Yahoo said today; NOT filed-as-of
DERIVED = "derived"                       # computed from inputs
MODEL_SCORE = "model_score"               # the factor's output
ASSUMPTION = "assumption"                 # a fallback constant, not measured

CATEGORIES = {
    PIT_MARKET: "Exchange data, correct as of the date it carries.",
    OBSERVATION_YAHOO: ("Fetched from Yahoo on the observation date. Carries no "
                        "filing date, so it is NOT point-in-time: a later "
                        "restatement changes what Yahoo reports without "
                        "changing this row."),
    DERIVED: "Computed from other stored values by the factor itself.",
    MODEL_SCORE: "The factor's output for this observation.",
    ASSUMPTION: "A constant used when data was unavailable. Not a measurement.",
}

# Every field, documented where it is defined rather than in a wiki that drifts.
#   kind         raw | derived | metadata | score
#   category     one of the five above
#   pit          is this true as of the observation date, or merely observed then
#   reproduces   does storing it help recompute the score
#   immutable    can the underlying truth change after we recorded it
FIELD_CATALOG = {
    # ---- momentum -------------------------------------------------------
    "momentum.mom_12_1_pct": {
        "meaning": "Return from 252 trading days before formation to 21 before.",
        "source": "yfinance daily closes, auto_adjust=True",
        "kind": "derived", "category": DERIVED, "pit": False,
        "reproduces": True, "immutable": False,
        "note": ("Not immutable: the adjusted series is restated by later "
                 "splits and dividends, so recomputing this tomorrow from the "
                 "same window can give a different number."),
    },
    "momentum.ann_vol_pct": {
        "meaning": "Annualised volatility of daily returns over the window.",
        "source": "yfinance daily closes", "kind": "derived",
        "category": DERIVED, "pit": False, "reproduces": True,
        "immutable": False,
    },
    "momentum.risk_adj": {
        "meaning": "mom_12_1 / annualised volatility. Determines the score.",
        "source": "derived", "kind": "derived", "category": DERIVED,
        "pit": False, "reproduces": True, "immutable": False,
        "note": "score = tanh(risk_adj / MOMENTUM_TANH_DIVISOR), so this alone "
                "reproduces the score exactly.",
    },
    "momentum.window_lookback_days": {
        "meaning": "Trading days back to the window start.",
        "source": "alpha_model.MOMENTUM_LOOKBACK_DAYS", "kind": "metadata",
        "category": ASSUMPTION, "pit": False, "reproduces": False,
        "immutable": True,
    },
    "momentum.window_skip_days": {
        "meaning": "Trading days skipped at the recent end.",
        "source": "alpha_model.MOMENTUM_SKIP_DAYS", "kind": "metadata",
        "category": ASSUMPTION, "pit": False, "reproduces": False,
        "immutable": True,
    },
    "momentum.price_source": {
        "meaning": "Where the price series came from.",
        "source": "constant", "kind": "metadata", "category": DERIVED,
        "pit": False, "reproduces": False, "immutable": True,
        "note": ("yfinance adjusted closes. bhavcopy is UNADJUSTED and cannot "
                 "substitute; the series itself is not recoverable."),
    },
    # ---- quality --------------------------------------------------------
    "quality.piotroski": {
        "meaning": "Piotroski F-score, 0-9.",
        "source": "metrics.piotroski_score over Yahoo .info",
        "kind": "derived", "category": OBSERVATION_YAHOO, "pit": False,
        "reproduces": True, "immutable": False,
    },
    "quality.roe": {
        "meaning": "Return on equity as reported by Yahoo.",
        "source": "Yahoo .info returnOnEquity", "kind": "raw",
        "category": OBSERVATION_YAHOO, "pit": False, "reproduces": True,
        "immutable": False,
    },
    "quality.fcf_yield": {
        "meaning": "Free cash flow / market cap.",
        "source": "Yahoo .info freeCashflow, marketCap", "kind": "derived",
        "category": OBSERVATION_YAHOO, "pit": False, "reproduces": True,
        "immutable": False,
    },
    "quality.inputs_used": {
        "meaning": "How many of the three legs had data.",
        "source": "alpha_model", "kind": "metadata", "category": DERIVED,
        "pit": False, "reproduces": True, "immutable": True,
    },
    "quality.distress_flags": {
        "meaning": "Distress conditions that vetoed or capped the score.",
        "source": "alpha_model", "kind": "metadata", "category": DERIVED,
        "pit": False, "reproduces": True, "immutable": True,
    },
    # ---- value ----------------------------------------------------------
    "value.pe_ratio": {
        "meaning": "The stock's trailing P/E.",
        "source": "Yahoo .info trailingPE", "kind": "raw",
        "category": OBSERVATION_YAHOO, "pit": False, "reproduces": True,
        "immutable": False,
    },
    "value.pb_ratio": {
        "meaning": "The stock's price/book.",
        "source": "Yahoo .info priceToBook", "kind": "raw",
        "category": OBSERVATION_YAHOO, "pit": False, "reproduces": True,
        "immutable": False,
    },
    "value.sector_pe": {
        "meaning": "Peer/market P/E the stock was z-scored against.",
        "source": "peer .info, or an NSE market constant if too few peers",
        "kind": "derived", "category": OBSERVATION_YAHOO, "pit": False,
        "reproduces": True, "immutable": False,
        "note": "With pe_ratio this reproduces pe_z_score, and the peer table "
                "records which peers produced it.",
    },
    "value.sector_pb": {
        "meaning": "Peer/market P/B the stock was z-scored against.",
        "source": "peer .info, or an NSE market constant", "kind": "derived",
        "category": OBSERVATION_YAHOO, "pit": False, "reproduces": True,
        "immutable": False,
    },
    "value.pe_z_score": {
        "meaning": "Z-score of the stock's P/E against the sector figure.",
        "source": "derived", "kind": "derived", "category": DERIVED,
        "pit": False, "reproduces": True, "immutable": True,
    },
    "value.pb_z_score": {
        "meaning": "Z-score of the stock's P/B against the sector figure.",
        "source": "derived", "kind": "derived", "category": DERIVED,
        "pit": False, "reproduces": True, "immutable": True,
    },
    "value.legs_used": {
        "meaning": "How many of P/E and P/B survived the distress checks.",
        "source": "alpha_model", "kind": "metadata", "category": DERIVED,
        "pit": False, "reproduces": True, "immutable": True,
    },
    "value.valued_on": {
        "meaning": "Which multiples the score was actually built from.",
        "source": "alpha_model", "kind": "metadata", "category": DERIVED,
        "pit": False, "reproduces": True, "immutable": True,
    },
    "value.peer_count": {
        "meaning": "Peers whose multiples entered the sector figure.",
        "source": "alpha_model", "kind": "metadata", "category": DERIVED,
        "pit": False, "reproduces": False, "immutable": True,
    },
    # ---- sentiment ------------------------------------------------------
    "sentiment.n_articles": {
        "meaning": "Headlines that carried a usable date and were scored.",
        "source": "news + FinBERT", "kind": "metadata", "category": DERIVED,
        "pit": False, "reproduces": True, "immutable": True,
    },
    "sentiment.undated_articles": {
        "meaning": "Headlines dropped for having no parseable date.",
        "source": "news", "kind": "metadata", "category": DERIVED,
        "pit": False, "reproduces": True, "immutable": True,
    },
    "sentiment.days_back": {
        "meaning": "News window in days; confidence divides by it.",
        "source": "alpha_model._compute_sentiment_factor", "kind": "metadata",
        "category": ASSUMPTION, "pit": False, "reproduces": True,
        "immutable": True,
        "note": ("Required for reproduction. The score is the decay-weighted "
                 "mean SHRUNK by confidence, and confidence is "
                 "sum(weights)/(days_back*0.5) — so the article set alone does "
                 "not determine the score."),
    },
    "sentiment.half_life_days": {
        "meaning": "Decay half-life applied to headline age.",
        "source": "alpha_model.SENTIMENT_HALF_LIFE_DAYS", "kind": "metadata",
        "category": ASSUMPTION, "pit": False, "reproduces": True,
        "immutable": True,
    },
}

# Which returned keys to persist per factor, and under what catalogue name.
# Read from the factor's own result dict — nothing here re-fetches, so storing
# provenance cannot change what was scored.
CAPTURE_MAP = {
    "momentum": ["mom_12_1_pct", "ann_vol_pct", "risk_adj"],
    "quality": ["piotroski", "roe", "fcf_yield", "inputs_used",
                "distress_flags"],
    "value": ["pe_ratio", "pb_ratio", "sector_pe", "sector_pb", "pe_z_score",
              "pb_z_score", "legs_used", "valued_on", "peer_count"],
    "sentiment": ["n_articles", "undated_articles", "days_back"],
}


def _init():
    global _READY
    if _READY:
        return
    for ddl in (
        """CREATE TABLE IF NOT EXISTS factor_inputs (
               ticker      TEXT NOT NULL,
               isin        TEXT,
               cycle_id    TEXT NOT NULL,
               observed_at TEXT NOT NULL,
               factor      TEXT NOT NULL,
               input_name  TEXT NOT NULL,
               value_num   REAL,
               value_text  TEXT,
               category    TEXT,
               source      TEXT,
               missing     INTEGER DEFAULT 0,
               PRIMARY KEY (ticker, cycle_id, factor, input_name)
           )""",
        """CREATE TABLE IF NOT EXISTS factor_input_peers (
               ticker      TEXT NOT NULL,
               cycle_id    TEXT NOT NULL,
               peer_ticker TEXT NOT NULL,
               peer_pe     REAL,
               peer_pb     REAL,
               source      TEXT,
               observed_at TEXT,
               PRIMARY KEY (ticker, cycle_id, peer_ticker)
           )""",
        """CREATE TABLE IF NOT EXISTS factor_input_articles (
               ticker       TEXT NOT NULL,
               cycle_id     TEXT NOT NULL,
               title_hash   TEXT NOT NULL,
               title        TEXT,
               published_at TEXT,
               finbert_label TEXT,
               finbert_confidence REAL,
               weight       REAL,
               observed_at  TEXT,
               PRIMARY KEY (ticker, cycle_id, title_hash)
           )""",
    ):
        conn = get_conn()
        try:
            conn.execute(ddl)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            conn.close()
    _READY = True


def _num(v):
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    except (TypeError, ValueError):
        return None


def capture(ticker: str, cycle_id: str, factors: dict, isin: str = None,
            observed_at: str = None) -> dict:
    """
    Persist the inputs behind one observation's factor scores.

    Reads only what the factor functions already returned. It re-fetches
    nothing, so it cannot change a score, and it raises nothing, so it cannot
    cost one.

    Returns a summary including `complete`, which is what
    factor_history.raw_inputs_available is set from: true only when every
    factor that produced a score also produced its inputs.
    """
    out = {"stored": 0, "missing": 0, "peers": 0, "articles": 0,
           "complete": False, "factors": {}}
    try:
        _init()
        ticker = (ticker or "").strip().upper()
        if not ticker or not cycle_id or not isinstance(factors, dict):
            return out
        now = observed_at or datetime.now().isoformat()

        rows, per_factor = [], {}
        for factor, keys in CAPTURE_MAP.items():
            fd = factors.get(factor)
            if not isinstance(fd, dict):
                continue
            # A factor that produced no score has no inputs worth claiming.
            scored = _num(fd.get("score")) is not None
            got = 0
            for key in keys:
                name = f"{factor}.{key}"
                meta = FIELD_CATALOG.get(name, {})
                raw = fd.get(key)
                num = _num(raw)
                text = None
                if num is None and raw is not None:
                    text = str(raw)[:200]
                missing = 1 if (raw is None) else 0
                if not missing:
                    got += 1
                rows.append((ticker, isin, cycle_id, now, factor, key, num,
                             text, meta.get("category"), meta.get("source"),
                             missing))
            # Constants that shaped the calculation but are not in the result.
            # They are stored, and they do NOT count toward completeness: they
            # are always present, so counting them let a factor that had lost
            # every real input still report a full set. The completeness test
            # caught exactly that.
            for name, val in _constants_for(factor):
                rows.append((ticker, isin, cycle_id, now, factor, name,
                             _num(val), None if _num(val) is not None else str(val),
                             ASSUMPTION, "module constant", 0))
            per_factor[factor] = {"scored": scored, "inputs_captured": got,
                                  "inputs_expected": len(keys)}

        stored, missing_n = _write(rows)
        out["stored"], out["missing"] = stored, missing_n
        out["factors"] = per_factor
        out["peers"] = _write_peers(ticker, cycle_id, factors, now)
        out["articles"] = _write_articles(ticker, cycle_id, factors, now)

        # Complete means: every factor that scored also has all of its declared
        # inputs present. A factor that could not score is not held against the
        # observation — it recorded honestly that it had nothing.
        out["complete"] = bool(per_factor) and all(
            (not v["scored"]) or v["inputs_captured"] >= v["inputs_expected"]
            for v in per_factor.values())
    except Exception as e:                                  # never raise
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _constants_for(factor):
    """Module constants that shaped the calculation, recorded with it."""
    try:
        if factor == "momentum":
            import alpha_model as am
            return [("window_lookback_days", am.MOMENTUM_LOOKBACK_DAYS),
                    ("window_skip_days", am.MOMENTUM_SKIP_DAYS),
                    ("price_source", "yfinance adjusted closes")]
        if factor == "sentiment":
            import alpha_model as am
            return [("half_life_days", am.SENTIMENT_HALF_LIFE_DAYS)]
    except Exception:
        pass
    return []


def _write(rows):
    if not rows:
        return 0, 0
    stmt = ("INSERT INTO factor_inputs (ticker, isin, cycle_id, observed_at, "
            "factor, input_name, value_num, value_text, category, source, "
            "missing) VALUES (?,?,?,?,?,?,?,?,?,?,?)")
    if IS_POSTGRES:
        stmt += (" ON CONFLICT (ticker, cycle_id, factor, input_name) "
                 "DO NOTHING")
    else:
        stmt = stmt.replace("INSERT INTO", "INSERT OR IGNORE INTO")
    conn = get_conn()
    try:
        conn.executemany(stmt, rows)
        conn.commit()
        return len(rows), sum(1 for r in rows if r[10])
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        ok = 0
        for r in rows:
            try:
                conn.execute(stmt, r)
                ok += 1
            except Exception:
                pass
        conn.commit()
        return ok, sum(1 for r in rows if r[10])
    finally:
        conn.close()


def _write_peers(ticker, cycle_id, factors, now):
    peers = ((factors.get("value") or {}).get("peers_used") or [])
    if not isinstance(peers, list) or not peers:
        return 0
    stmt = ("INSERT INTO factor_input_peers (ticker, cycle_id, peer_ticker, "
            "peer_pe, peer_pb, source, observed_at) VALUES (?,?,?,?,?,?,?)")
    stmt = (stmt + " ON CONFLICT (ticker, cycle_id, peer_ticker) DO NOTHING"
            if IS_POSTGRES else stmt.replace("INSERT INTO", "INSERT OR IGNORE INTO"))
    rows = []
    for p in peers[:10]:
        if isinstance(p, dict):
            rows.append((ticker, cycle_id, str(p.get("ticker"))[:32],
                         _num(p.get("pe")), _num(p.get("pb")),
                         "Yahoo .info", now))
        else:
            rows.append((ticker, cycle_id, str(p)[:32], None, None,
                         "Yahoo .info", now))
    conn = get_conn()
    try:
        conn.executemany(stmt, rows)
        conn.commit()
        return len(rows)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        conn.close()


def _write_articles(ticker, cycle_id, factors, now):
    arts = ((factors.get("sentiment") or {}).get("articles_used") or [])
    if not isinstance(arts, list) or not arts:
        return 0
    stmt = ("INSERT INTO factor_input_articles (ticker, cycle_id, title_hash, "
            "title, published_at, finbert_label, finbert_confidence, weight, "
            "observed_at) VALUES (?,?,?,?,?,?,?,?,?)")
    stmt = (stmt + " ON CONFLICT (ticker, cycle_id, title_hash) DO NOTHING"
            if IS_POSTGRES else stmt.replace("INSERT INTO", "INSERT OR IGNORE INTO"))
    rows = []
    for a in arts[:40]:
        if not isinstance(a, dict):
            continue
        title = str(a.get("title") or "")[:400]
        h = hashlib.sha256(title.encode("utf-8", "ignore")).hexdigest()[:32]
        rows.append((ticker, cycle_id, h, title, str(a.get("published_at") or "")[:32],
                     str(a.get("label") or "")[:16], _num(a.get("confidence")),
                     _num(a.get("weight")), now))
    if not rows:
        return 0
    conn = get_conn()
    try:
        conn.executemany(stmt, rows)
        conn.commit()
        return len(rows)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        conn.close()


# ------------------------------------------------------------------ reads

def inputs_for(ticker: str, cycle_id: str = None) -> dict:
    """Everything stored behind one observation."""
    try:
        _init()
        conn = get_conn()
        try:
            if not cycle_id:
                row = conn.execute("SELECT MAX(cycle_id) FROM factor_inputs "
                                   "WHERE ticker = ?", (ticker,)).fetchone()
                cycle_id = row[0] if row else None
            if not cycle_id:
                return {"available": False, "reason": "no observation stored"}
            rows = conn.execute(
                "SELECT factor, input_name, value_num, value_text, category, "
                "source, missing, observed_at, isin FROM factor_inputs "
                "WHERE ticker = ? AND cycle_id = ? ORDER BY factor, input_name",
                (ticker, cycle_id)).fetchall()
            peers = conn.execute(
                "SELECT peer_ticker, peer_pe, peer_pb FROM factor_input_peers "
                "WHERE ticker = ? AND cycle_id = ?", (ticker, cycle_id)).fetchall()
            arts = conn.execute(
                "SELECT title, published_at, finbert_label, finbert_confidence, "
                "weight FROM factor_input_articles WHERE ticker = ? AND "
                "cycle_id = ?", (ticker, cycle_id)).fetchall()
        finally:
            conn.close()
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}

    by_factor = {}
    for f, name, num, text, cat, src, miss, obs, isin in rows:
        d = by_factor.setdefault(f, {})
        d[name] = {"value": num if num is not None else text,
                   "category": cat, "source": src, "missing": bool(miss)}
    return {
        "available": bool(rows), "ticker": ticker, "cycle_id": cycle_id,
        "observed_at": rows[0][7] if rows else None,
        "isin": rows[0][8] if rows else None,
        "factors": by_factor,
        "peers": [{"ticker": p[0], "pe": p[1], "pb": p[2]} for p in peers],
        "articles": [{"title": a[0], "published_at": a[1], "label": a[2],
                      "confidence": a[3], "weight": a[4]} for a in arts],
        "provenance_note": (
            "Fields categorised observation_yahoo record what Yahoo reported on "
            "the observation date. They carry no filing date and are NOT "
            "point-in-time: a restatement changes the underlying figure without "
            "changing this row."),
        "categories": CATEGORIES,
    }


def coverage() -> dict:
    """How much of the record has its inputs."""
    try:
        _init()
        conn = get_conn()
        try:
            obs = conn.execute(
                "SELECT COUNT(DISTINCT ticker || '|' || cycle_id) "
                "FROM factor_inputs").fetchone()[0]
            rows = conn.execute("SELECT COUNT(*) FROM factor_inputs").fetchone()[0]
            miss = conn.execute("SELECT COUNT(*) FROM factor_inputs "
                                "WHERE missing = 1").fetchone()[0]
            cyc = conn.execute("SELECT MIN(cycle_id), MAX(cycle_id) "
                               "FROM factor_inputs").fetchone()
            peers = conn.execute("SELECT COUNT(*) FROM factor_input_peers").fetchone()[0]
            arts = conn.execute("SELECT COUNT(*) FROM factor_input_articles").fetchone()[0]
        finally:
            conn.close()
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}
    return {
        "available": True, "observations_with_inputs": obs,
        "input_rows": rows, "missing_inputs": miss,
        "peer_rows": peers, "article_rows": arts,
        "first_cycle": cyc[0] if cyc else None,
        "last_cycle": cyc[1] if cyc else None,
        "note": ("Observations recorded before this shipped have no inputs and "
                 "are flagged raw_inputs_available = false. They are not "
                 "reconstructed: today's Yahoo values are not what those scores "
                 "were computed from, and writing them in would fabricate a "
                 "provenance that never existed."),
    }
