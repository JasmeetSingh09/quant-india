"""
factor_history.py — what each factor scored, and when.

The app could tell you a stock's factor scores today and could tell you its
overall alpha last week, but it could not tell you what any individual factor
did in between: the scan table keeps one row per cycle with four of the six
factors, and nothing kept the other two at all. So "growth improved 17 points
while the price went nowhere" was unanswerable, not because the data was hard
to compute but because nobody wrote it down.

This writes it down. Nothing here predicts anything or scores anything. It
records what was measured and when, so a later question about change has a
factual answer instead of a reconstruction.

Two models feed it and they measure different things:

  v1  the nightly universe scan — momentum, quality, value, sentiment
  v2  the six-factor model, run on demand — adds growth and low_risk

Rows say which model produced them. Comparing a v1 momentum score against a v2
momentum score would be comparing two different definitions and calling the
difference a change, so reads are filtered to one model at a time.

Price is stored alongside, because every interesting question here is about a
factor moving differently from the price, and joining to a separate price
series after the fact invites the two to drift out of alignment.
"""

from datetime import datetime, timedelta

try:
    from db import get_conn, IS_POSTGRES
except Exception:                                   # pragma: no cover
    from .db import get_conn, IS_POSTGRES


FACTORS = ("momentum", "quality", "growth", "value", "sentiment", "low_risk")
V1_FACTORS = ("momentum", "quality", "value", "sentiment")

_READY = False


def _init():
    global _READY
    if _READY:
        return
    conn = get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS factor_history (
                ticker      TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                model       TEXT NOT NULL,
                alpha_score REAL,
                momentum    REAL,
                quality     REAL,
                growth      REAL,
                value       REAL,
                sentiment   REAL,
                low_risk    REAL,
                price       REAL,
                PRIMARY KEY (ticker, captured_at, model)
            )
        """)
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

    # Index on its own connection. A failed statement aborts the whole
    # transaction on Postgres, so batching migrations means one harmless
    # already-exists error takes the rest of them down with it.
    conn = get_conn()
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fh_ticker "
                     "ON factor_history (ticker, captured_at)")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
    _READY = True


def record(ticker: str, model: str, alpha_score=None, factors: dict = None,
           price=None, captured_at: str = None) -> bool:
    """
    Store one observation. Never raises: a failed write must not take down the
    scan or the page that triggered it, and a missing row is a gap in history
    rather than a broken product.
    """
    try:
        _init()
        ticker = (ticker or "").strip().upper()
        if not ticker or model not in ("v1", "v2"):
            return False
        f = factors or {}

        def _score(name):
            v = f.get(name)
            if isinstance(v, dict):
                v = v.get("score")
            try:
                return None if v is None else float(v)
            except Exception:
                return None

        # Neither alpha model returns a price, so without this every row landed
        # with price NULL — and divergence, which is entirely about a factor
        # moving differently from the price, had nothing to compare against.
        # get_current_price is cached, and during a scan the price for this
        # ticker was just used to compute momentum, so this is almost always a
        # memory hit. A failure here loses the price, never the observation.
        if price is None:
            try:
                from data_fetcher import get_current_price
                price = (get_current_price(ticker) or {}).get("price")
            except Exception:
                price = None

        # One row per ticker per DAY per model. A user refreshing a stock page
        # ten times should not create ten observations and make a day look
        # busier than it was.
        stamp = captured_at or datetime.now().strftime("%Y-%m-%d")
        vals = (ticker, stamp, model,
                None if alpha_score is None else float(alpha_score),
                _score("momentum"), _score("quality"), _score("growth"),
                _score("value"), _score("sentiment"), _score("low_risk"),
                None if price is None else float(price))

        conn = get_conn()
        try:
            if IS_POSTGRES:
                conn.execute(
                    "INSERT INTO factor_history (ticker, captured_at, model,"
                    " alpha_score, momentum, quality, growth, value, sentiment,"
                    " low_risk, price) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                    # COALESCE, not plain assignment. A caller supplying only
                    # some factors used to blank the rest for that day, so a
                    # partial refresh silently destroyed the fuller record
                    # written earlier — and the loss was invisible until a
                    # change query came back empty.
                    " ON CONFLICT (ticker, captured_at, model) DO UPDATE SET"
                    " alpha_score=COALESCE(EXCLUDED.alpha_score, factor_history.alpha_score),"
                    " momentum=COALESCE(EXCLUDED.momentum, factor_history.momentum),"
                    " quality=COALESCE(EXCLUDED.quality, factor_history.quality),"
                    " growth=COALESCE(EXCLUDED.growth, factor_history.growth),"
                    " value=COALESCE(EXCLUDED.value, factor_history.value),"
                    " sentiment=COALESCE(EXCLUDED.sentiment, factor_history.sentiment),"
                    " low_risk=COALESCE(EXCLUDED.low_risk, factor_history.low_risk),"
                    " price=COALESCE(EXCLUDED.price, factor_history.price)", vals)
            else:
                # INSERT OR REPLACE deletes the old row and writes a new one, so
                # unsupplied columns come back NULL. Merge with what is already
                # stored before writing, or a partial update destroys the rest.
                prev = conn.execute(
                    "SELECT alpha_score, momentum, quality, growth, value,"
                    " sentiment, low_risk, price FROM factor_history"
                    " WHERE ticker = ? AND captured_at = ? AND model = ?",
                    (ticker, stamp, model)).fetchone()
                if prev:
                    merged = list(vals)
                    for i, old_v in enumerate(prev):
                        if merged[3 + i] is None and old_v is not None:
                            merged[3 + i] = old_v
                    vals = tuple(merged)
                conn.execute(
                    "INSERT OR REPLACE INTO factor_history (ticker, captured_at,"
                    " model, alpha_score, momentum, quality, growth, value,"
                    " sentiment, low_risk, price) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    vals)
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def history(ticker: str, model: str = None, limit: int = 90) -> list:
    """Observations for one stock, oldest first."""
    try:
        _init()
        ticker = (ticker or "").strip().upper()
        conn = get_conn()
        try:
            sql = ("SELECT captured_at, model, alpha_score, momentum, quality,"
                   " growth, value, sentiment, low_risk, price"
                   " FROM factor_history WHERE ticker = ?")
            args = [ticker]
            if model:
                sql += " AND model = ?"
                args.append(model)
            sql += " ORDER BY captured_at DESC"
            rows = conn.execute(sql, tuple(args)).fetchall()[:limit]
        finally:
            conn.close()
        out = [{"captured_at": r[0], "model": r[1], "alpha_score": r[2],
                "momentum": r[3], "quality": r[4], "growth": r[5],
                "value": r[6], "sentiment": r[7], "low_risk": r[8],
                "price": r[9]} for r in rows]
        out.reverse()
        return out
    except Exception:
        return []


def change(ticker: str, days: int = 30, model: str = None) -> dict:
    """
    What moved over the window, and what did not.

    Returns a status rather than numbers when there is not enough history,
    because a change feature built on one observation shows zero for everything
    and reads as "nothing is happening" when it means "we have not been
    watching long enough". Those are opposite claims.
    """
    try:
        _init()
        rows = history(ticker, model=model, limit=400)
        if not rows:
            return {"ticker": (ticker or "").upper(), "status": "no_history",
                    "note": ("Nothing recorded for this stock yet. Factor history "
                            "starts accumulating from the first scan after this "
                            "feature shipped — it cannot be backfilled, because "
                            "the scores were never stored.")}

        # Compare like with like: one model, or the one with the most rows.
        if not model:
            counts = {}
            for r in rows:
                counts[r["model"]] = counts.get(r["model"], 0) + 1
            model = max(counts, key=counts.get)
            rows = [r for r in rows if r["model"] == model]

        if len(rows) < 2:
            first = rows[0]["captured_at"]
            return {"ticker": (ticker or "").upper(), "status": "too_short",
                    "model": model, "observations": len(rows),
                    "first_seen": first,
                    "note": (f"Only one observation so far ({first}). A change "
                             f"needs at least two, so there is nothing to report "
                             f"yet — which is not the same as nothing changing.")}

        cutoff = (datetime.now() - timedelta(days=int(days))).strftime("%Y-%m-%d")
        older = [r for r in rows if r["captured_at"] <= cutoff]
        start = older[-1] if older else rows[0]
        end = rows[-1]
        if start["captured_at"] == end["captured_at"]:
            return {"ticker": (ticker or "").upper(), "status": "too_short",
                    "model": model, "observations": len(rows),
                    "note": "All observations are from the same day."}

        names = FACTORS if model == "v2" else V1_FACTORS
        deltas = {}
        for f in names:
            a, b = start.get(f), end.get(f)
            if a is None or b is None:
                continue
            deltas[f] = {"from": round(a, 2), "to": round(b, 2),
                         "change": round(b - a, 2)}

        alpha_change = None
        if start.get("alpha_score") is not None and end.get("alpha_score") is not None:
            alpha_change = {"from": round(start["alpha_score"], 2),
                            "to": round(end["alpha_score"], 2),
                            "change": round(end["alpha_score"] - start["alpha_score"], 2)}

        price_change_pct = None
        if start.get("price") and end.get("price") and start["price"] > 0:
            price_change_pct = round((end["price"] / start["price"] - 1) * 100, 2)

        span = _days_between(start["captured_at"], end["captured_at"])
        return {
            "ticker": (ticker or "").upper(),
            "status": "ok",
            "model": model,
            "from_date": start["captured_at"],
            "to_date": end["captured_at"],
            "days_covered": span,
            "requested_days": int(days),
            "observations": len(rows),
            "factors": deltas,
            "alpha": alpha_change,
            "price_change_pct": price_change_pct,
            # The window actually covered is rarely the window asked for, and
            # quietly relabelling 9 days as "30 days" would make every number
            # here mean something other than what it says.
            "window_note": (f"Comparing {start['captured_at']} to "
                            f"{end['captured_at']} — {span} days, not the "
                            f"{int(days)} requested, because that is how far "
                            f"the recorded history goes."
                            if span < int(days) * 0.9 else None),
            "means": ("This describes what changed. It is not a forecast and "
                      "carries no claim that a change predicts anything."),
        }
    except Exception as e:
        return {"ticker": (ticker or "").upper(), "status": "error",
                "note": f"{type(e).__name__}"}


# Momentum IS price, and value is price divided by fundamentals — both move
# mechanically when the price moves. Counting them as evidence that "the
# fundamentals improved while the price did not react" would be counting the
# price as evidence about itself, which is how a divergence claim becomes
# circular without anyone noticing.
PRICE_LINKED = ("momentum", "value")
INDEPENDENT = ("growth", "quality", "low_risk", "sentiment")

# Thresholds, stated rather than tuned. A factor move under 8 points is inside
# the range these scores wander in normally, and a price move under 3% over a
# month is not a reaction to anything.
MEANINGFUL_FACTOR_MOVE = 8.0
FLAT_PRICE_MOVE = 3.0


def divergences(ticker: str, days: int = 30, model: str = None) -> dict:
    """
    Places where different parts of the story disagree.

    These are OBSERVATIONS. Nothing here has been shown to predict a return,
    and the app has already learned once what happens when a plausible-looking
    pattern meets a walk-forward test. The output says so in every response
    rather than in a footnote, because the label is the only thing standing
    between "interesting" and "buy this".
    """
    c = change(ticker, days=days, model=model)
    if c.get("status") != "ok":
        return {**c, "divergences": []}

    f = c["factors"]
    price = c.get("price_change_pct")
    found = []

    def moved(name):
        d = f.get(name)
        return d["change"] if d else None

    if price is not None:
        indep_up = [n for n in INDEPENDENT
                    if (moved(n) or 0) >= MEANINGFUL_FACTOR_MOVE]
        indep_down = [n for n in INDEPENDENT
                      if (moved(n) or 0) <= -MEANINGFUL_FACTOR_MOVE]

        if len(indep_up) >= 2 and abs(price) < FLAT_PRICE_MOVE:
            found.append({
                "kind": "fundamentals_up_price_flat",
                "label": "Fundamentals improved, price did not react",
                "detail": (f"{', '.join(indep_up)} rose "
                           f"{', '.join(f'{moved(n):+.0f}' for n in indep_up)} points "
                           f"over {c['days_covered']} days while the price moved "
                           f"{price:+.1f}%."),
                "factors": indep_up,
                "price_change_pct": price,
            })

        if len(indep_down) >= 2 and abs(price) < FLAT_PRICE_MOVE:
            found.append({
                "kind": "fundamentals_down_price_flat",
                "label": "Fundamentals weakened, price has not reflected it",
                "detail": (f"{', '.join(indep_down)} fell over "
                           f"{c['days_covered']} days while the price moved "
                           f"{price:+.1f}%."),
                "factors": indep_down,
                "price_change_pct": price,
            })

        sent = moved("sentiment")
        if sent is not None and sent >= MEANINGFUL_FACTOR_MOVE and price <= -FLAT_PRICE_MOVE:
            found.append({
                "kind": "sentiment_up_price_down",
                "label": "News tone improved while the price fell",
                "detail": (f"Sentiment rose {sent:+.0f} points but the price is "
                           f"down {price:.1f}% over {c['days_covered']} days."),
                "factors": ["sentiment"], "price_change_pct": price,
            })
        if sent is not None and sent <= -MEANINGFUL_FACTOR_MOVE and price >= FLAT_PRICE_MOVE:
            found.append({
                "kind": "sentiment_down_price_up",
                "label": "News tone worsened while the price rose",
                "detail": (f"Sentiment fell {sent:+.0f} points but the price is "
                           f"up {price:+.1f}% over {c['days_covered']} days."),
                "factors": ["sentiment"], "price_change_pct": price,
            })

    return {
        **c,
        "divergences": found,
        "price_linked_excluded": list(PRICE_LINKED),
        "why_excluded": ("Momentum and value are not counted as independent "
                         "evidence here. Momentum IS the price, and value is "
                         "price against fundamentals, so both move mechanically "
                         "when the price moves — treating them as confirmation "
                         "would be using the price as evidence about itself."),
        "thresholds": {"factor_points": MEANINGFUL_FACTOR_MOVE,
                       "flat_price_pct": FLAT_PRICE_MOVE},
        "status_label": ("observation" if found else "nothing_unusual"),
        "not_a_signal": (
            "These are observations about what moved, not opportunities. No "
            "divergence here has been tested against future returns, so none of "
            "them is known to predict anything. The one factor this app HAS "
            "tested end to end — momentum — did not survive that test, which is "
            "the reason these stay labelled as observations until the same "
            "walk-forward machinery says otherwise."),
    }


def _days_between(a: str, b: str) -> int:
    try:
        fa = datetime.fromisoformat(a[:10])
        fb = datetime.fromisoformat(b[:10])
        return abs((fb - fa).days)
    except Exception:
        return 0


def coverage() -> dict:
    """How much history exists — the honest answer to 'why is this empty'."""
    try:
        _init()
        conn = get_conn()
        try:
            n = conn.execute("SELECT COUNT(*) FROM factor_history").fetchone()[0]
            t = conn.execute("SELECT COUNT(DISTINCT ticker) FROM factor_history").fetchone()[0]
            d = conn.execute("SELECT MIN(captured_at), MAX(captured_at) "
                             "FROM factor_history").fetchone()
        finally:
            conn.close()
        return {"observations": n, "tickers": t,
                "first": d[0] if d else None, "last": d[1] if d else None,
                "note": ("History accumulates from the first scan after this "
                         "shipped. It cannot be backfilled: the per-factor "
                         "scores were never stored before, so there is nothing "
                         "to recover.")}
    except Exception:
        return {"observations": 0, "tickers": 0}
