"""Send alert emails with Gmail/any SMTP, or Resend. Prints if neither is set."""
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx


def _env(name, default=""):
    v = (os.environ.get(name) or default).strip()
    if name == "SMTP_PASSWORD":
        # Gmail app passwords are 16 letters shown in groups. Pasting on a phone can
        # add normal or invisible spaces, and anything that isn't plain ASCII makes
        # Gmail hang up mid-login, so keep only letters and digits.
        v = re.sub(r"[^A-Za-z0-9]", "", v)
    return v


def send(to, subject, html, text):
    if _env("SMTP_HOST"):
        return _smtp(to, subject, html, text)
    if _env("RESEND_API_KEY"):
        return _resend(to, subject, html, text)
    print(f"--- email to {to}: {subject}\n{text}\n")


def _sender():
    return _env("FROM_EMAIL") or _env("SMTP_USER")


def _smtp(to, subject, html, text):
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, _sender(), to
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    host, user, pw = _env("SMTP_HOST"), _env("SMTP_USER"), _env("SMTP_PASSWORD")
    raw = os.environ.get("SMTP_PASSWORD") or ""
    # Safe to log: lengths only, never the password
    print(f"SMTP login as {user}: password {len(pw)} chars after cleanup "
          f"({len(raw)} raw, {sum(1 for c in raw if ord(c) > 127)} non-ASCII)")
    port = int(_env("SMTP_PORT", "587") or "587")
    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(user, pw)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise
    except (smtplib.SMTPServerDisconnected, OSError) as e:
        # Gmail sometimes drops port 587 from cloud servers; try SSL on 465
        print(f"SMTP on {port} failed ({e}), trying SSL on 465")
        with smtplib.SMTP_SSL(host, 465, timeout=30) as s:
            s.login(user, pw)
            s.send_message(msg)


def _resend(to, subject, html, text):
    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {_env('RESEND_API_KEY')}"},
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


def render_setup(name, routes, manage_url=None):
    """The test email: confirms alerts work, lists no fares."""
    subject = "Flightwatch is set up"
    manage_text = f"\n\nChange your routes or pause alerts: {manage_url}" if manage_url else ""
    text = (
        f"Hi {name},\n\nYou're watching {routes} route{'s' if routes != 1 else ''}. "
        "Flightwatch checks them every few hours and only emails you when a fare is on sale, "
        "meaning well below what that route normally costs. It needs a few days of prices "
        "to learn what normal is, so the first alerts can take a few days."
        + manage_text
    )
    button = (
        f"<p><a href='{manage_url}' style='display:inline-block;padding:10px 16px;background:#111;"
        f"color:#fff;border-radius:8px;text-decoration:none'>Manage your routes</a></p>"
        if manage_url else ""
    )
    html = (
        f"<p>Hi {name},</p><p>You're watching {routes} route{'s' if routes != 1 else ''}. "
        "Flightwatch checks them every few hours and only emails you when a fare is on sale, "
        "meaning well below what that route normally costs.</p>"
        "<p style='color:#666'>It needs a few days of prices to learn what normal is, "
        "so the first alerts can take a few days.</p>" + button
    )
    return subject, html, text
