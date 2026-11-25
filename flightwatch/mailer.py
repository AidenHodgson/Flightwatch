"""Send alert emails with Gmail/any SMTP, or Resend. Prints if neither is set."""
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

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
    """From header. Gmail only lets you send as the account you log in with, so
    keep FROM_EMAIL's display name but use the SMTP_USER address when they differ."""
    name, addr = parseaddr(_env("FROM_EMAIL"))
    user = _env("SMTP_USER")
    if _env("SMTP_HOST") and user and addr.lower() != user.lower():
        addr = user
    return formataddr((name or "Flightwatch", addr or user))


class EmailLoginError(Exception):
    """Gmail (or another server) rejected the username or password."""


def _smtp(to, subject, html, text):
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, _sender(), to
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    host, user, pw = _env("SMTP_HOST"), _env("SMTP_USER"), _env("SMTP_PASSWORD")
    if not pw:
        raise EmailLoginError("SMTP_PASSWORD is empty. Add it as a GitHub secret.")
    port = int(_env("SMTP_PORT", "587") or "587")

    last = None
    # Try the configured port first, then the other one. Gmail supports both.
    for p in [port] + [x for x in (587, 465) if x != port]:
        try:
            if p == 465:
                s = smtplib.SMTP_SSL(host, 465, timeout=30)
                s.ehlo()
            else:
                s = smtplib.SMTP(host, p, timeout=30)
                s.ehlo()
                s.starttls()
                s.ehlo()
            with s:
                # One login method on purpose. smtplib.login() tries several, and
                # Gmail hangs up after the first failure, which hides the real error.
                s.user, s.password = user, pw
                try:
                    s.auth("PLAIN", s.auth_plain)
                except smtplib.SMTPAuthenticationError as e:
                    raise EmailLoginError(
                        f"The mail server rejected the login for the SMTP_USER account "
                        f"({e.smtp_code}). For Gmail this means the app password is wrong "
                        "for that account: make a new app password while signed in to that "
                        "exact Gmail account (2-Step Verification must be on), then update "
                        "the SMTP_PASSWORD secret."
                    ) from None
                s.send_message(msg)
                return
        except EmailLoginError:
            raise  # a wrong password won't fix itself on another port
        except (smtplib.SMTPException, OSError) as e:
            last = e
            print(f"SMTP on port {p} failed ({e!r}), trying the other port")
    raise last


def _resend(to, subject, html, text):
    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {_env('RESEND_API_KEY')}"},
        json={"from": _sender(), "to": [to], "subject": subject, "html": html, "text": text},
        timeout=30,
    )
    r.raise_for_status()


CITY = {
    "ATL": "Atlanta", "LHR": "London", "CDG": "Paris", "FCO": "Rome", "AMS": "Amsterdam",
    "BCN": "Barcelona", "MAD": "Madrid", "FRA": "Frankfurt", "DUB": "Dublin", "HND": "Tokyo",
    "NRT": "Tokyo", "ICN": "Seoul", "HKG": "Hong Kong", "SIN": "Singapore", "BKK": "Bangkok",
    "TPE": "Taipei", "LIS": "Lisbon", "ATH": "Athens", "MUC": "Munich", "ZRH": "Zurich",
    "IST": "Istanbul", "KEF": "Reykjavik", "EDI": "Edinburgh", "CPH": "Copenhagen",
    "PRG": "Prague", "VIE": "Vienna", "MXP": "Milan", "VCE": "Venice", "DXB": "Dubai",
    "SYD": "Sydney", "AKL": "Auckland", "CUN": "Cancun", "MEX": "Mexico City", "SJU": "San Juan",
    "HNL": "Honolulu", "OGG": "Maui", "LAX": "Los Angeles", "SFO": "San Francisco",
    "JFK": "New York", "BOS": "Boston", "ORD": "Chicago", "DEN": "Denver", "SEA": "Seattle",
    "MIA": "Miami", "MCO": "Orlando", "LAS": "Las Vegas",
}


def city(code):
    return CITY.get(code, code)


def _nice_date(iso):
    from datetime import date
    d = date.fromisoformat(iso)
    return f"{d.strftime('%a')}, {d.strftime('%b')} {d.day}"


def _money(n):
    return f"${n:,}"


def subject_for(deals):
    if len(deals) == 1:
        d = deals[0]
        off = f" ({d['pct_off']}% off)" if d.get("pct_off") else ""
        return f"Flight sale: {city(d['origin'])} to {city(d['destination'])} {_money(d['price'])}{off}"
    names = ", ".join(city(d["destination"]) for d in deals[:3])
    more = f" and {len(deals) - 3} more" if len(deals) > 3 else ""
    return f"{len(deals)} flight sales: {names}{more}"


def _card(d):
    off = d.get("pct_off")
    usual = d.get("normal")
    rng = (f"Usually {_money(d['range_low'])} to {_money(d['range_high'])} for this trip"
           if d.get("range_low") and d.get("range_high") else "")
    lo, hi = d.get("price_span") or (d["price"], d["price"])
    span_prices = f" ({_money(lo)} to {_money(hi)})" if hi > lo else ""
    share = d.get("window_share") or ""
    other = ("<div style='margin-top:6px;font-size:13px;color:#9a6700'>Your airline doesn't fly this "
             "route on these dates, so this is the best other option.</div>") if d.get("other_airline") else ""
    return f"""
<tr><td style="padding:0 0 16px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e6e3dc;border-radius:14px">
    <tr><td style="padding:18px 20px 6px">
      <div style="font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:#6b7078">{city(d['origin'])} to</div>
      <div style="font-size:24px;font-weight:700;color:#16181d;line-height:1.2">{city(d['destination'])}</div>
    </td>
    <td align="right" style="padding:18px 20px 6px;white-space:nowrap">
      <div style="font-size:28px;font-weight:800;color:#0b6e4f;line-height:1">{_money(d['price'])}</div>
      {f'<div style="font-size:14px;color:#6b7078;text-decoration:line-through">{_money(usual)}</div>' if usual else ''}
    </td></tr>
    <tr><td colspan="2" style="padding:4px 20px 0">
      {f'<span style="display:inline-block;background:#e6f4ee;color:#0b6e4f;font-weight:700;font-size:13px;padding:4px 10px;border-radius:999px">{off}% off usual</span>' if off else ''}
      {f'<span style="display:inline-block;background:#f1efe9;color:#16181d;font-size:13px;padding:4px 10px;border-radius:999px;margin-left:4px">Save {_money(usual - d["price"])}</span>' if usual else ''}
    </td></tr>
    <tr><td colspan="2" style="padding:14px 20px 4px;font-size:15px;color:#16181d;line-height:1.55">
      <b>{d.get('flight') or 'Round trip'}</b>, round trip, {d.get('nights', '')} nights<br>
      Cheapest: {_nice_date(d['depart'])} to {_nice_date(d['return'])}<br>
      <b>On sale:</b> {d.get('window') or 'this date'}<br>
      {f'<span style="color:#6b7078">Sale fares on {share}{span_prices}</span>' if share else ''}
      {f'<br><span style="color:#6b7078">{rng}</span>' if rng else ''}
      {other}
    </td></tr>
    <tr><td colspan="2" style="padding:14px 20px 20px">
      <a href="{d['link']}" style="display:inline-block;background:#16181d;color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;padding:11px 18px;border-radius:10px">See it on Google Flights</a>
    </td></tr>
  </table>
</td></tr>"""


def render(name, deals, manage_url=None):
    """deals: dicts from main.evaluate_watch."""
    deals = sorted(deals, key=lambda d: -(d.get("pct_off") or 0))
    subject = subject_for(deals)

    lines = []
    for d in deals:
        off = f", {d['pct_off']}% off (usually {_money(d['normal'])})" if d.get("pct_off") else ""
        lines.append(
            f"{city(d['origin'])} to {city(d['destination'])}: {_money(d['price'])}{off}\n"
            f"  {d.get('flight') or 'Round trip'}, {d.get('nights', '')} nights\n"
            f"  Cheapest: {_nice_date(d['depart'])} to {_nice_date(d['return'])}\n"
            f"  On sale: {d.get('window') or 'this date'} ({d.get('window_share', '')})\n"
            f"  {d['link']}"
        )
    manage_text = f"\n\nChange your routes or pause alerts: {manage_url}" if manage_url else ""
    text = (f"Hi {name},\n\n" + "\n\n".join(lines)
            + "\n\nSale prices can disappear within hours, so check soon. Book directly with the airline when you can."
            + manage_text)

    intro = ("A fare on one of your routes just dropped well below normal."
             if len(deals) == 1 else f"{len(deals)} of your routes just dropped well below normal.")
    manage = (f'<a href="{manage_url}" style="color:#6b7078">Manage your routes</a> &middot; ' if manage_url else "")
    html = f"""<!doctype html><html><body style="margin:0;background:#f6f5f2">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f5f2">
<tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif">
  <tr><td style="padding:0 4px 18px">
    <div style="font-size:15px;font-weight:700;color:#16181d">&#9992;&#65039; Flightwatch</div>
    <div style="font-size:22px;font-weight:700;color:#16181d;margin-top:14px">Hi {name}, there's a sale.</div>
    <div style="font-size:15px;color:#6b7078;margin-top:4px">{intro}</div>
  </td></tr>
  {''.join(_card(d) for d in deals)}
  <tr><td style="padding:4px 4px 0;font-size:13px;color:#6b7078;line-height:1.5">
    Sale prices can disappear within hours, so check soon. "Usual" is Google's typical price for the same trip.
    Book directly with the airline when you can.<br><br>
    {manage}You only get these for big sales: below the usual range and well under the typical price.
  </td></tr>
</table></td></tr></table></body></html>"""
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
