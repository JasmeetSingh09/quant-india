import os
"""
alerts.py — Gmail alert sender for the Indian stock platform.

Sends multi-signal alerts combining:
  - Price movement (from watchlist thresholds)
  - Sentiment shift (FinBERT score from sentiment.py)
  - Valuation context (P/E, 52-week range from data_fetcher)

Uses SMTP_SSL on port 465. Credentials from .env:
  GMAIL_ADDRESS      — sender address
  GMAIL_APP_PASSWORD — Gmail app password (not account password)

Every mail goes to an explicit recipient. There is no default inbox any more
(V4-04 / R4, decided 19 Nov 2026): GMAIL_RECEIVER is no longer read, so no
anonymous or public request can make the server mail the owner.
"""

import os
import html as _html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

GMAIL_SENDER   = os.getenv("GMAIL_ADDRESS")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# Shown in every alert and summary e-mail (decided 19 Nov 2026).
NOT_ADVICE = "Educational research tool, not investment advice; not SEBI-registered."
NOT_ADVICE_HTML = (
    '<p style="color:#6b7280;font-size:12px;margin-top:12px">' + NOT_ADVICE + '</p>'
)


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------

def _esc(value) -> str:
    """Text for an HTML email body. Ticker, company name and headline can come
    from a request (/alerts/send) or a news feed; unescaped they could carry the
    sender's own markup and links in mail from this account (V4-03, 18 Nov 2026)."""
    return _html.escape("" if value is None else str(value), quote=True)


def _one_line(value) -> str:
    """Text for a mail header: no line breaks, so nothing can add a header."""
    return " ".join(("" if value is None else str(value)).split())


# ---------------------------------------------------------------------------
# Core send
# ---------------------------------------------------------------------------

def send_email(subject: str, body_html: str, to_email: str = None) -> dict:
    """
    Send an HTML email via Gmail SMTP_SSL (port 465).

    to_email — the recipient: a user's own confirmed, opted-in address.
    Required. There is no fallback inbox (V4-04 / R4, 19 Nov 2026): a call
    without a recipient sends nothing.

    Returns {"status": "sent"} or {"error": "..."}.
    """
    recipient = (to_email or "").strip() if isinstance(to_email, str) else ""
    if not recipient or "@" not in recipient:
        return {"error": "No recipient."}

    if not GMAIL_SENDER or not GMAIL_PASSWORD:
        return {"error": "GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set in .env"}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = _one_line(subject)
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = recipient

    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, recipient, msg.as_string())
        return {"status": "sent", "to": recipient, "subject": subject}
    except smtplib.SMTPAuthenticationError:
        return {"error": "Gmail authentication failed. Check GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env."}
    except smtplib.SMTPRecipientsRefused:
        return {"error": "The mail server refused the recipient."}
    except Exception as e:
        # Never the exception text: SMTP errors quote addresses (Codex review
        # R6, 18 Nov 2026). The type is enough to diagnose from the logs.
        print(f"[mail] send failed: {type(e).__name__}")
        return {"error": f"Sending failed ({type(e).__name__})."}


# ---------------------------------------------------------------------------
# Alert builders
# ---------------------------------------------------------------------------

def _build_price_alert_html(
    ticker: str,
    company_name: str,
    added_price: float,
    current_price: float,
    change_pct: float,
    threshold_pct: float,
    valuation: dict,
) -> str:
    ticker, company_name = _esc(ticker), _esc(company_name)
    valuation = {k: _esc(v) for k, v in (valuation or {}).items()}
    direction = "risen" if change_pct > 0 else "fallen"
    color     = "#16a34a" if change_pct > 0 else "#dc2626"
    pe_str    = f"{valuation.get('pe_ratio', 'N/A')}"
    high52    = valuation.get("week_52_high", "N/A")
    low52     = valuation.get("week_52_low", "N/A")

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;">
      <h2 style="color:{color}">&#9888; Price Alert: {ticker}</h2>
      <p><strong>{company_name}</strong> has {direction}
         <strong style="color:{color}">{abs(change_pct):.2f}%</strong>
         (your threshold: {threshold_pct}%).</p>
      <table style="border-collapse:collapse;width:100%">
        <tr><td style="padding:8px;border:1px solid #ddd">Added price</td>
            <td style="padding:8px;border:1px solid #ddd">&#8377;{added_price:.2f}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd">Current price</td>
            <td style="padding:8px;border:1px solid #ddd;color:{color}">&#8377;{current_price:.2f}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd">Change</td>
            <td style="padding:8px;border:1px solid #ddd;color:{color}">{change_pct:+.2f}%</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd">P/E Ratio</td>
            <td style="padding:8px;border:1px solid #ddd">{pe_str}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd">52-week range</td>
            <td style="padding:8px;border:1px solid #ddd">&#8377;{low52} &#8211; &#8377;{high52}</td></tr>
      </table>
      <p style="color:#6b7280;font-size:12px">
        Sent at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} IST by Indian Stock Platform
      </p>
      {NOT_ADVICE_HTML}
    </body></html>
    """


def _build_sentiment_alert_html(
    ticker: str,
    company_name: str,
    sentiment_label: str,
    confidence_pct: float,
    headline: str,
    current_price: float,
) -> str:
    ticker, company_name, headline = _esc(ticker), _esc(company_name), _esc(headline)
    sentiment_label = _esc(sentiment_label)
    color = "#dc2626" if sentiment_label == "negative" else "#16a34a"
    icon  = "&#128308;" if sentiment_label == "negative" else "&#128994;"
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;">
      <h2 style="color:{color}">{icon} Sentiment Alert: {ticker}</h2>
      <p>A strong <strong style="color:{color}">{sentiment_label}</strong> signal
         ({confidence_pct:.1f}% confidence) was detected for
         <strong>{company_name}</strong>.</p>
      <blockquote style="border-left:4px solid {color};margin:16px 0;padding:8px 16px;
                         background:#f9fafb;color:#374151;">
        <em>"{headline}"</em>
      </blockquote>
      <table style="border-collapse:collapse;width:100%">
        <tr><td style="padding:8px;border:1px solid #ddd">Sentiment</td>
            <td style="padding:8px;border:1px solid #ddd;color:{color}">{sentiment_label.upper()}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd">Confidence</td>
            <td style="padding:8px;border:1px solid #ddd">{confidence_pct:.1f}%</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd">Current price</td>
            <td style="padding:8px;border:1px solid #ddd">&#8377;{current_price:.2f}</td></tr>
      </table>
      <p style="color:#6b7280;font-size:12px">
        Sent at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} IST by Indian Stock Platform
      </p>
      {NOT_ADVICE_HTML}
    </body></html>
    """


def _build_multi_signal_alert_html(
    ticker: str,
    company_name: str,
    price_change_pct: float,
    current_price: float,
    sentiment_label: str,
    confidence_pct: float,
    headline: str,
    valuation: dict,
) -> str:
    ticker, company_name, headline = _esc(ticker), _esc(company_name), _esc(headline)
    sentiment_label = _esc(sentiment_label)
    valuation = {k: _esc(v) for k, v in (valuation or {}).items()}
    price_color = "#16a34a" if price_change_pct > 0 else "#dc2626"
    sent_color  = "#dc2626" if sentiment_label == "negative" else "#16a34a"

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;">
      <h2>&#9889; Multi-Signal Alert: {ticker}</h2>
      <p><strong>{company_name}</strong> is showing multiple signals simultaneously.
         Review before making any decision.</p>

      <h3 style="color:{price_color}">Price Signal</h3>
      <p>Price has moved <strong style="color:{price_color}">{price_change_pct:+.2f}%</strong>
         to &#8377;{current_price:.2f}</p>

      <h3 style="color:{sent_color}">Sentiment Signal</h3>
      <p>FinBERT classified the latest news as
         <strong style="color:{sent_color}">{sentiment_label.upper()}</strong>
         ({confidence_pct:.1f}% confident).</p>
      <blockquote style="border-left:4px solid {sent_color};margin:12px 0;padding:8px 16px;
                         background:#f9fafb;color:#374151;">
        <em>"{headline}"</em>
      </blockquote>

      <h3>Valuation Context</h3>
      <table style="border-collapse:collapse;width:100%">
        <tr><td style="padding:8px;border:1px solid #ddd">P/E Ratio</td>
            <td style="padding:8px;border:1px solid #ddd">{valuation.get("pe_ratio","N/A")}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd">52-week high</td>
            <td style="padding:8px;border:1px solid #ddd">&#8377;{valuation.get("week_52_high","N/A")}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd">52-week low</td>
            <td style="padding:8px;border:1px solid #ddd">&#8377;{valuation.get("week_52_low","N/A")}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd">ROE</td>
            <td style="padding:8px;border:1px solid #ddd">{valuation.get("roe","N/A")}</td></tr>
      </table>
      <p style="color:#6b7280;font-size:12px">
        Sent at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} IST by Indian Stock Platform
      </p>
      {NOT_ADVICE_HTML}
    </body></html>
    """


# ---------------------------------------------------------------------------
# High-level alert triggers
# ---------------------------------------------------------------------------

def send_price_alert(
    ticker: str,
    company_name: str,
    added_price: float,
    current_price: float,
    change_pct: float,
    threshold_pct: float,
    to_email: str = None,
) -> dict:
    """Send a price movement alert email to `to_email` (required)."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from data_fetcher import get_financial_metrics
        valuation = get_financial_metrics(ticker)
    except Exception:
        valuation = {}

    subject = f"Price Alert: {ticker} moved {change_pct:+.1f}%"
    body    = _build_price_alert_html(
        ticker, company_name, added_price, current_price,
        change_pct, threshold_pct, valuation
    )
    return send_email(subject, body, to_email=to_email)


def send_sentiment_alert(
    ticker: str,
    company_name: str,
    sentiment_label: str,
    confidence_pct: float,
    headline: str,
    current_price: float,
    to_email: str = None,
) -> dict:
    """Send a sentiment shift alert email to `to_email` (required)."""
    subject = (
        f"Sentiment Alert: {ticker} — {sentiment_label.upper()} "
        f"({confidence_pct:.0f}% confident)"
    )
    body = _build_sentiment_alert_html(
        ticker, company_name, sentiment_label,
        confidence_pct, headline, current_price
    )
    return send_email(subject, body, to_email=to_email)


def send_multi_signal_alert(
    ticker: str,
    company_name: str,
    price_change_pct: float,
    current_price: float,
    sentiment_label: str,
    confidence_pct: float,
    headline: str,
    to_email: str = None,
) -> dict:
    """Send a combined price + sentiment + valuation alert email."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from data_fetcher import get_financial_metrics
        valuation = get_financial_metrics(ticker)
    except Exception:
        valuation = {}

    subject = (
        f"Multi-Signal Alert: {ticker} — "
        f"Price {price_change_pct:+.1f}% + {sentiment_label.upper()} sentiment"
    )
    body = _build_multi_signal_alert_html(
        ticker, company_name, price_change_pct, current_price,
        sentiment_label, confidence_pct, headline, valuation
    )
    return send_email(subject, body, to_email=to_email)


def check_and_send_watchlist_alerts(watchlist_entries: list, to_email: str = None) -> list:
    """
    Given ONE user's watchlist entries (from watchlist.get_watchlist) and that
    user's own opted-in address, send price alerts where thresholds are
    breached. Without an address nothing is sent.

    Returns list of alert results.
    """
    results = []
    if not to_email:
        return results
    for entry in watchlist_entries:
        if not threshold_ok(entry.get("price_alert_pct")):
            continue
        if not entry.get("alert_triggered"):
            continue

        result = send_price_alert(
            ticker=entry["ticker"],
            company_name=entry.get("company_name", entry["ticker"]),
            added_price=entry.get("added_price", 0),
            current_price=entry.get("current_price", 0),
            change_pct=entry.get("change_from_add_pct", 0),
            threshold_pct=entry.get("price_alert_pct", 5.0),
            to_email=to_email,
        )
        results.append({"ticker": entry["ticker"], "alert_type": "price", **result})

    return results


# ---------------------------------------------------------------------------
# Automatic alert scheduler — checks watchlists and emails on threshold breach
# ---------------------------------------------------------------------------

import math
import sqlite3
import sqlite_local
from apscheduler.schedulers.background import BackgroundScheduler

_DB_PATH = Path(os.environ.get("QUANT_DATA_DIR", str(Path(__file__).parent.parent))) / "quant_platform.db"
_alert_scheduler = None
_alert_scheduler_started = False


# ---------------------------------------------------------------------------
# Who may receive an automatic alert (V4-04 / R4, decided 19 Nov 2026)
# ---------------------------------------------------------------------------
# Before: the job read the shared "public" watchlist (anyone can write to it
# without signing in, with a threshold of 0) and sent with no recipient, so
# mail fell back to the owner's inbox; signed-in users never got their own.
# Now: only users who opted in to alerts from a verified token with a
# confirmed address (user_prefs.alert_opt_in, behind require_mail_identity),
# each about THEIR OWN watchlist, each to THEIR OWN address. The anonymous
# "public" list and unverified ids never trigger mail.

def eligible_user_id(user_id) -> bool:
    """A real, verified account id: not the shared anonymous bucket and not
    an id from a token that failed verification."""
    return (isinstance(user_id, str) and bool(user_id.strip())
            and user_id != "public" and not user_id.startswith("unverified:"))


def threshold_ok(pct) -> bool:
    """A usable alert threshold: a finite number above zero. A threshold of 0
    would fire on every check, so it never sends (validated at the API too)."""
    try:
        v = float(pct)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v > 0


# Once per crossing (review fix, 19 Nov 2026). The threshold is measured from
# the price when the stock was added, which never moves, so a stock that stays
# past it used to be mailed again every 6 hours, around the clock. Now a row in
# alert_log_user means "this user was told about this stock's current move":
# no more mail while it stays past the threshold, and the row is cleared
# (re-armed) only when a live price shows the move back INSIDE the threshold.
# A check without a live price changes nothing.

def _init_alert_log():
    conn = sqlite_local.connect(_DB_PATH)
    # Per user and stock. The old alert_log (one row per ticker for the single
    # owner inbox) is left in place, unused.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_log_user (
            user_id       TEXT NOT NULL,
            ticker        TEXT NOT NULL,
            last_sent_at  TEXT NOT NULL,
            PRIMARY KEY (user_id, ticker)
        )
    """)
    conn.commit()
    conn.close()


def _already_alerted(user_id: str, ticker: str) -> bool:
    """True if this user was already told about this stock's current move."""
    conn = sqlite_local.connect(_DB_PATH)
    row = conn.execute("SELECT 1 FROM alert_log_user WHERE user_id = ? AND ticker = ?",
                       (user_id, ticker)).fetchone()
    conn.close()
    return bool(row)


def _rearm(user_id: str, ticker: str):
    """The move is back inside the threshold: the next crossing alerts again."""
    conn = sqlite_local.connect(_DB_PATH)
    conn.execute("DELETE FROM alert_log_user WHERE user_id = ? AND ticker = ?", (user_id, ticker))
    conn.commit()
    conn.close()


def _mark_alerted(user_id: str, ticker: str):
    conn = sqlite_local.connect(_DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO alert_log_user (user_id, ticker, last_sent_at) VALUES (?, ?, ?)",
        (user_id, ticker, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def forget_user(user_id: str) -> int:
    """Delete this user's alert history (account deletion, 19 Nov 2026). The
    table lives in the server's local SQLite file, not the main database, so
    account_deletion calls this after its own transaction. Returns rows deleted."""
    if not eligible_user_id(user_id):
        return 0
    _init_alert_log()
    conn = sqlite_local.connect(_DB_PATH)
    try:
        cur = conn.execute("DELETE FROM alert_log_user WHERE user_id = ?", (user_id,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def _load_recipients() -> list:
    """[(user_id, email)] for everyone who opted in to alerts. Separate so
    tests can see exactly who the job would consider."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from user_prefs import alert_recipients
    return alert_recipients()


def _load_watchlist(user_id: str) -> list:
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from watchlist import get_watchlist
    return get_watchlist(refresh_prices=True, user_id=user_id)


def _sentiment_for(ticker: str) -> tuple:
    """(label, confidence %, headline) for the alert; neutral when unavailable."""
    try:
        from news import get_stock_news
        from sentiment import summarise_sentiment
        articles = get_stock_news(ticker, days_back=7)
        if articles:
            summ = summarise_sentiment(articles[:10])
            return (summ.get("overall_sentiment", "neutral"),
                    round(summ.get("average_confidence", 0) * 100, 1),
                    articles[0]["title"])
    except Exception:
        pass
    return ("neutral", 0.0, "")


def run_watchlist_alert_check() -> list:
    """
    The automatic job: for each user who opted in to alerts, read THEIR
    watchlist with live prices and, for any stock that has CROSSED its
    threshold since they were last told, send a multi-signal email
    (price + current sentiment + valuation) to THEIR address. Once per
    crossing: re-armed only when a live price is back inside the threshold.

    Returns a list of what was sent or skipped (used by the scheduler log and
    the owner-only /alerts/run-check endpoint). It never contains an address;
    users appear as an 8-character id prefix.
    """
    _init_alert_log()
    sent = []

    try:
        recipients = _load_recipients()
    except Exception as e:
        return [{"error": f"could not load alert recipients ({type(e).__name__})"}]

    sentiment_cache = {}
    for user_id, address in recipients:
        if not eligible_user_id(user_id):
            continue
        if not (isinstance(address, str) and "@" in address):
            continue
        who = user_id[:8]
        try:
            entries = _load_watchlist(user_id)
        except Exception as e:
            sent.append({"user": who, "status": "error",
                         "detail": f"could not load watchlist ({type(e).__name__})"})
            continue

        for entry in entries:
            ticker = entry.get("ticker")
            if not ticker or not threshold_ok(entry.get("price_alert_pct")):
                continue
            if not entry.get("alert_triggered"):
                # Back inside the threshold on a LIVE price: re-arm. With no
                # live price (change_from_add_pct None) nothing is known, so
                # nothing changes.
                if entry.get("change_from_add_pct") is not None and _already_alerted(user_id, ticker):
                    _rearm(user_id, ticker)
                continue
            if _already_alerted(user_id, ticker):
                sent.append({"user": who, "ticker": ticker, "status": "skipped (already alerted for this move)"})
                continue

            if ticker not in sentiment_cache:
                sentiment_cache[ticker] = _sentiment_for(ticker)
            sentiment_label, confidence_pct, headline = sentiment_cache[ticker]

            result = send_multi_signal_alert(
                ticker=ticker,
                company_name=entry.get("company_name", ticker),
                price_change_pct=entry.get("change_from_add_pct", 0),
                current_price=entry.get("current_price", 0),
                sentiment_label=sentiment_label,
                confidence_pct=confidence_pct,
                headline=headline or "Price threshold breached",
                to_email=address,
            )
            if result.get("status") == "sent":
                _mark_alerted(user_id, ticker)
            sent.append({"user": who, "ticker": ticker,
                         "status": result.get("status", "error"),
                         "detail": result.get("error", "")})

    return sent

def _alert_job():
    """Background wrapper with logging."""
    try:
        results = run_watchlist_alert_check()
        fired = [r for r in results if r.get("status") == "sent"]
        if fired:
            print(f"[Alerts] {datetime.now().strftime('%H:%M')} — sent {len(fired)} alert(s): "
                  f"{[r['ticker'] for r in fired]}")
    except Exception as e:
        print(f"[Alerts] check error: {e}")


def start_alert_scheduler(interval_minutes: int = 30):
    """
    Start the background job that auto-checks watchlists and sends alerts.
    Safe to call multiple times — only starts once.
    """
    global _alert_scheduler, _alert_scheduler_started
    if _alert_scheduler_started:
        return
    if not GMAIL_SENDER or not GMAIL_PASSWORD:
        print("[Alerts] Gmail not configured — auto-alerts disabled "
              "(set GMAIL_ADDRESS and GMAIL_APP_PASSWORD).")
        return
    _init_alert_log()
    _alert_scheduler = BackgroundScheduler()
    _alert_scheduler.add_job(_alert_job, "interval", minutes=interval_minutes, id="watchlist_alerts")
    _alert_scheduler.start()
    _alert_scheduler_started = True
    print(f"[Alerts] Auto-alert scheduler started ({interval_minutes}-min checks, "
          f"one alert per threshold crossing).")


def send_test_alert(to_email: str = None) -> dict:
    """Send a test email to `to_email` (required) to verify Gmail credentials."""
    subject = "Test Alert — Indian Stock Platform"
    body = f"""
    <html><body style="font-family:Arial,sans-serif;">
      <h2 style="color:#16a34a">&#10003; Alert System Working</h2>
      <p>Your Gmail alert configuration is correct.</p>
      <p>Sent at : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
      {NOT_ADVICE_HTML}
    </body></html>
    """
    return send_email(subject, body, to_email=to_email)


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Testing alerts.py")
    print("=" * 60)

    # Usage: python alerts.py you@example.com  (mail goes only to that address)
    import sys as _sys
    to = _sys.argv[1] if len(_sys.argv) > 1 else None
    print(f"Password set  : {'YES' if GMAIL_PASSWORD else 'NO — set GMAIL_APP_PASSWORD in .env'}")

    if not GMAIL_SENDER or not GMAIL_PASSWORD or not to:
        print("\nSkipping live send — configure .env and pass a recipient address.")
        print("Expected .env keys: GMAIL_ADDRESS, GMAIL_APP_PASSWORD")
    else:
        print("\n1. Sending test email...")
        result = send_test_alert(to_email=to)
        print(f"   {result}")

        print("\n2. Sending mock price alert...")
        result = send_price_alert(
            ticker="RELIANCE.NS",
            company_name="Reliance Industries Limited",
            added_price=2800.00,
            current_price=2954.50,
            change_pct=5.52,
            threshold_pct=5.0,
            to_email=to,
        )
        print(f"   {result}")

        print("\n3. Sending mock sentiment alert...")
        result = send_sentiment_alert(
            ticker="TCS.NS",
            company_name="Tata Consultancy Services",
            sentiment_label="negative",
            confidence_pct=87.3,
            headline="TCS misses Q4 revenue estimates amid weak demand from US banking clients",
            current_price=3450.25,
            to_email=to,
        )
        print(f"   {result}")

    print("\n" + "=" * 60)
    print("alerts.py test complete")
    print("=" * 60)
