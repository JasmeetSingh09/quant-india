"""
alerts.py — Gmail alert sender for the Indian stock platform.

Sends multi-signal alerts combining:
  - Price movement (from watchlist thresholds)
  - Sentiment shift (FinBERT score from sentiment.py)
  - Valuation context (P/E, 52-week range from data_fetcher)

Uses SMTP_SSL on port 465. Credentials from .env:
  GMAIL_ADDRESS      — sender address
  GMAIL_APP_PASSWORD — Gmail app password (not account password)
  GMAIL_RECEIVER     — destination email (defaults to GMAIL_ADDRESS if unset)
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

GMAIL_SENDER   = os.getenv("GMAIL_ADDRESS")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
GMAIL_RECEIVER = os.getenv("GMAIL_RECEIVER", GMAIL_SENDER)


# ---------------------------------------------------------------------------
# Core send
# ---------------------------------------------------------------------------

def send_email(subject: str, body_html: str) -> dict:
    """
    Send an HTML email via Gmail SMTP_SSL (port 465).

    Returns {"status": "sent"} or {"error": "..."}.
    """
    if not GMAIL_SENDER or not GMAIL_PASSWORD:
        return {"error": "GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set in .env"}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = GMAIL_RECEIVER

    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, GMAIL_RECEIVER, msg.as_string())
        return {"status": "sent", "to": GMAIL_RECEIVER, "subject": subject}
    except smtplib.SMTPAuthenticationError:
        return {"error": "Gmail authentication failed. Check GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env."}
    except Exception as e:
        return {"error": str(e)}


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
) -> dict:
    """Send a price movement alert email."""
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
    return send_email(subject, body)


def send_sentiment_alert(
    ticker: str,
    company_name: str,
    sentiment_label: str,
    confidence_pct: float,
    headline: str,
    current_price: float,
) -> dict:
    """Send a sentiment shift alert email."""
    subject = (
        f"Sentiment Alert: {ticker} — {sentiment_label.upper()} "
        f"({confidence_pct:.0f}% confident)"
    )
    body = _build_sentiment_alert_html(
        ticker, company_name, sentiment_label,
        confidence_pct, headline, current_price
    )
    return send_email(subject, body)


def send_multi_signal_alert(
    ticker: str,
    company_name: str,
    price_change_pct: float,
    current_price: float,
    sentiment_label: str,
    confidence_pct: float,
    headline: str,
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
    return send_email(subject, body)


def check_and_send_watchlist_alerts(watchlist_entries: list) -> list:
    """
    Given a list of watchlist entries (from watchlist.get_watchlist),
    check each one and send price alerts where thresholds are breached.

    Returns list of alert results.
    """
    results = []
    for entry in watchlist_entries:
        if not entry.get("alert_triggered"):
            continue

        result = send_price_alert(
            ticker=entry["ticker"],
            company_name=entry.get("company_name", entry["ticker"]),
            added_price=entry.get("added_price", 0),
            current_price=entry.get("current_price", 0),
            change_pct=entry.get("change_from_add_pct", 0),
            threshold_pct=entry.get("price_alert_pct", 5.0),
        )
        results.append({"ticker": entry["ticker"], "alert_type": "price", **result})

    return results


def send_test_alert() -> dict:
    """Send a test email to verify Gmail credentials are working."""
    subject = "Test Alert — Indian Stock Platform"
    body = f"""
    <html><body style="font-family:Arial,sans-serif;">
      <h2 style="color:#16a34a">&#10003; Alert System Working</h2>
      <p>Your Gmail alert configuration is correct.</p>
      <p>Sender  : {GMAIL_SENDER}</p>
      <p>Receiver: {GMAIL_RECEIVER}</p>
      <p>Sent at : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </body></html>
    """
    return send_email(subject, body)


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Testing alerts.py")
    print("=" * 60)

    print(f"\nGmail sender  : {GMAIL_SENDER}")
    print(f"Gmail receiver: {GMAIL_RECEIVER}")
    print(f"Password set  : {'YES' if GMAIL_PASSWORD else 'NO — set GMAIL_APP_PASSWORD in .env'}")

    if not GMAIL_SENDER or not GMAIL_PASSWORD:
        print("\nSkipping live send — configure .env first.")
        print("Expected .env keys: GMAIL_ADDRESS, GMAIL_APP_PASSWORD, GMAIL_RECEIVER")
    else:
        print("\n1. Sending test email...")
        result = send_test_alert()
        print(f"   {result}")

        print("\n2. Sending mock price alert...")
        result = send_price_alert(
            ticker="RELIANCE.NS",
            company_name="Reliance Industries Limited",
            added_price=2800.00,
            current_price=2954.50,
            change_pct=5.52,
            threshold_pct=5.0,
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
        )
        print(f"   {result}")

    print("\n" + "=" * 60)
    print("alerts.py test complete")
    print("=" * 60)
