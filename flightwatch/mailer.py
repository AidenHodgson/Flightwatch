"""Send alert emails with Gmail/any SMTP, or Resend. Prints if neither is set."""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx


def send(to, subject, html, text):
    if os.environ.get("SMTP_HOST"):
        return _smtp(to, subject, html, text)
    if os.environ.get("RESEND_API_KEY"):
        return _resend(to, subject, html, text)
    print(f"--- email to {to}: {subject}\n{text}\n")


def _sender():
    return os.environ.get("FROM_EMAIL") or os.environ.get("SMTP_USER")


def _smtp(to, subject, html, text):
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, _sender(), to
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(os.environ["SMTP_HOST"], port) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)


def _resend(to, subject, html, text):
    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json={"from": _sender(), "to": [to], "subject": subject, "html": html, "text": text},
        timeout=30,
    )
    r.raise_for_status()


def render(name, deals, manage_url=None):
    """deals: list of dicts with route, dates, price, normal, link."""
    lines, rows = [], []
    for d in deals:
        normal = f" (usually about ${d['normal']:,})" if d.get("normal") else ""
        lines.append(
            f"{d['origin']} to {d['destination']}: ${d['price']:,}{normal}\n"
            f"  {d['depart']} to {d['return']}  {d['link']}"
        )
        rows.append(
            f"<tr><td style='padding:8px 0'><b>{d['origin']} &rarr; {d['destination']}</b>"
            f" &nbsp; <b style='color:#0a7d32'>${d['price']:,}</b>{normal}<br>"
            f"{d['depart']} to {d['return']} &middot; <a href='{d['link']}'>See it on Google Flights</a></td></tr>"
        )
    count = len(deals)
    subject = f"Flightwatch: {count} flight deal{'s' if count != 1 else ''} for you"
    manage_text = f"\n\nChange your routes or pause alerts: {manage_url}" if manage_url else ""
    manage_html = (
        f"<p><a href='{manage_url}' style='display:inline-block;padding:10px 16px;background:#111;"
        f"color:#fff;border-radius:8px;text-decoration:none'>Manage your routes</a></p>"
        if manage_url else ""
    )
    text = f"Hi {name},\n\nNew deals on routes you're watching:\n\n" + "\n\n".join(lines) + (
        "\n\nPrices change fast, so check before booking. Book directly with the airline if you can."
    ) + manage_text
    html = (
        f"<p>Hi {name},</p><p>New deals on routes you're watching:</p>"
        f"<table>{''.join(rows)}</table>"
        "<p style='color:#666'>Prices change fast, so check before booking. "
        "Book directly with the airline if you can.</p>"
        + manage_html
    )
    return subject, html, text
