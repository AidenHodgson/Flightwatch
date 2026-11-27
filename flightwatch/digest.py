"""Check-in email: proof Flightwatch is running, even when there are no sales.

Sent Sunday and Wednesday at 10 AM New York time to people with digest turned on.
GitHub sometimes skips scheduled runs, so the workflow tries several times that
morning; this script sends once per person per day and ignores the extra tries.

  python -m flightwatch.digest           # send if it's Sun/Wed after 10 AM and not sent yet
  python -m flightwatch.digest --force   # send now, any day (for testing)
"""
import argparse
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import mailer
from .db import D1
from .mailer import city

log = logging.getLogger("flightwatch.digest")
NY = ZoneInfo("America/New_York")
DAYS = {6: "Sunday", 2: "Wednesday"}  # Python weekday numbers
SEND_HOUR = 10


def _utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def gather(db, user, since):
    runs = db.query(
        "SELECT COUNT(DISTINCT strftime('%Y-%m-%d %H', checked_at)) AS runs, COUNT(*) AS prices, "
        "MAX(checked_at) AS last FROM prices WHERE checked_at >= ?", [since])[0]
    sales = db.query(
        """SELECT w.origin, w.destination, a.price, a.depart_date FROM alerts a
           JOIN watches w ON w.id = a.watch_id
           WHERE w.user_id = ? AND a.sent_at >= ? ORDER BY a.sent_at""", [user["id"], since])
    closest = []
    for w in db.query(
        "SELECT DISTINCT origin, destination, cabin FROM watches WHERE user_id = ? AND active = 1", [user["id"]]
    ):
        rows = db.query(
            """SELECT price, typical, depart_date FROM prices
               WHERE origin=? AND destination=? AND cabin=? AND checked_at >= ? AND typical > 0
               ORDER BY (typical - price) * 1.0 / typical DESC LIMIT 1""",
            [w["origin"], w["destination"], w["cabin"], since])
        if rows:
            r = rows[0]
            closest.append({**w, **r, "pct": round(100 * (r["typical"] - r["price"]) / r["typical"])})
    closest.sort(key=lambda x: -x["pct"])
    return runs, sales, closest


def _when(utc_text):
    if not utc_text:
        return "never"
    dt = datetime.strptime(utc_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(NY)
    return f"{dt.strftime('%a')} {dt.strftime('%b')} {dt.day} at {dt.strftime('%I:%M %p').lstrip('0')}"


def render(user, runs, sales, closest, since_label, manage_url):
    n_runs = runs["runs"] or 0
    if n_runs == 0:
        subject = "Flightwatch hasn't checked prices lately"
        headline = "Heads up: no price checks ran."
        status = (f"No checks have run since {since_label}. Open the Actions tab in the "
                  "Flightwatch repo on GitHub to see what's wrong.")
    else:
        subject = (f"Flightwatch check-in: {len(sales)} sale{'s' if len(sales) != 1 else ''} sent"
                   if sales else "Flightwatch check-in: running, no sales yet")
        headline = "All good, Flightwatch is running." if not sales else "All good, and you got sales."
        status = (f"{n_runs} price checks since {since_label}, {runs['prices']:,} fares looked at. "
                  f"Last check: {_when(runs['last'])}.")

    sale_lines = [f"{city(s['destination'])}: ${s['price']:,} (leaving {mailer._nice_date(s['depart_date'])})" for s in sales]
    near = closest[:3]

    def near_text(c):
        if c["pct"] > 0:
            return f"{city(c['destination'])}: ${c['price']:,}, {c['pct']}% under its usual ${c['typical']:,}"
        return f"{city(c['destination'])}: ${c['price']:,}, about the usual ${c['typical']:,}"

    text = (f"Hi {user['name']},\n\n{headline}\n{status}\n\n"
            + ("Sales sent:\n" + "\n".join("- " + x for x in sale_lines) + "\n\n" if sale_lines else "No sales were big enough to email.\n\n")
            + ("Closest to a sale (any airline):\n" + "\n".join("- " + near_text(c) for c in near) + "\n\n" if near else "")
            + "A sale email goes out when a fare is below its usual range and at least 30% under typical."
            + (f"\n\nManage your routes: {manage_url}" if manage_url else ""))

    li = lambda items: "".join(f"<li style='margin:4px 0'>{x}</li>" for x in items)
    near_html = "".join(
        f"<tr><td style='padding:8px 0;border-top:1px solid #eee'><b>{city(c['destination'])}</b></td>"
        f"<td align='right' style='padding:8px 0;border-top:1px solid #eee'>${c['price']:,} "
        f"<span style='color:#6b7078'>vs ${c['typical']:,}</span></td>"
        f"<td align='right' style='padding:8px 0 8px 10px;border-top:1px solid #eee;color:{'#0b6e4f' if c['pct'] > 0 else '#6b7078'};font-weight:700'>"
        f"{str(c['pct']) + '% off' if c['pct'] > 0 else 'usual'}</td></tr>" for c in near)
    dot = "#0b6e4f" if n_runs else "#b42318"
    html = f"""<!doctype html><html><body style="margin:0;background:#f6f5f2">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#16181d">
<tr><td style="padding:0 4px 16px"><div style="font-size:15px;font-weight:700">&#9992;&#65039; Flightwatch check-in</div></td></tr>
<tr><td style="background:#fff;border:1px solid #e6e3dc;border-radius:14px;padding:18px 20px">
  <div style="font-size:20px;font-weight:700"><span style="color:{dot}">&#9679;</span> {headline}</div>
  <div style="font-size:15px;color:#6b7078;margin-top:6px;line-height:1.5">{status}</div>
</td></tr>
<tr><td style="height:14px"></td></tr>
<tr><td style="background:#fff;border:1px solid #e6e3dc;border-radius:14px;padding:18px 20px;font-size:15px;line-height:1.5">
  <div style="font-weight:700;margin-bottom:6px">Sales sent</div>
  {f"<ul style='margin:0;padding-left:18px'>{li(sale_lines)}</ul>" if sale_lines else "<div style='color:#6b7078'>None were big enough to email.</div>"}
  {f"<div style='font-weight:700;margin:16px 0 2px'>Closest to a sale <span style='font-weight:400;color:#6b7078'>(any airline)</span></div><table width='100%' cellpadding='0' cellspacing='0' style='font-size:15px'>{near_html}</table>" if near else ""}
</td></tr>
<tr><td style="padding:14px 4px 0;font-size:13px;color:#6b7078;line-height:1.5">
  A sale email goes out when a fare is below its usual range and at least 30% under typical. You get this check-in Sunday and Wednesday mornings.
  {f'<br><a href="{manage_url}" style="color:#6b7078">Manage your routes</a>' if manage_url else ''}
</td></tr></table></td></tr></table></body></html>"""
    return subject, html, text


def run(force=False):
    now = datetime.now(NY)
    if not force and (now.weekday() not in DAYS or now.hour < SEND_HOUR):
        log.info("Not a check-in time (%s). Nothing to do.", now.strftime("%a %H:%M"))
        return
    db = D1()
    today = now.date().isoformat()
    site = os.environ.get("SITE_URL", "").strip().rstrip("/")
    users = db.query("SELECT * FROM users WHERE active = 1 AND digest = 1")
    failed = []
    for u in users:
        if not force and db.query("SELECT 1 FROM digests WHERE user_id=? AND day=?", [u["id"], today]):
            log.info("already sent %s today", u["name"])
            continue
        last = db.query("SELECT MAX(sent_at) AS t FROM digests WHERE user_id=?", [u["id"]])[0]["t"]
        floor = _utc(now - timedelta(days=7))
        since = max(last, floor) if last else _utc(now - timedelta(days=4))
        runs, sales, closest = gather(db, u, since)
        manage = f"{site}/u/{u['token']}" if site and u.get("token") else None
        subject, html, text = render(u, runs, sales, closest, _when(since), manage)
        try:
            mailer.send(u["email"], subject, html, text)
            db.execute("INSERT OR REPLACE INTO digests (user_id, day) VALUES (?, ?)", [u["id"], today])
            log.info("sent check-in to %s", u["name"])
        except Exception as e:
            failed.append(str(e))
            log.error("check-in failed for %s: %s", u["name"], e)
    if failed:
        raise SystemExit(f"Check-in email failed: {failed[0]}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="send now, any day")
    run(force=p.parse_args().force)
