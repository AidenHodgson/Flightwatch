"""Daily run: check every watched route once, save prices, email deals.

Usage:
  python -m flightwatch.main            # normal run
  python -m flightwatch.main --report   # also email everyone their cheapest
                                        # fares even if they aren't deals
                                        # (handy for testing a new setup)
"""
import argparse
import logging
import os
from datetime import timedelta

from . import deals, mailer, notify
from .db import D1
from .search import PriceChecker, booking_link, sample_departures

log = logging.getLogger("flightwatch")
HISTORY_DAYS = 60


def load_watches(db):
    return db.query(
        """SELECT w.*, u.name AS user_name, u.email AS user_email,
                  u.token AS user_token, u.basecamp AS user_basecamp
           FROM watches w JOIN users u ON u.id = w.user_id
           WHERE w.active = 1 AND u.active = 1"""
    )


def route_key(w):
    nights = round((w["min_nights"] + w["max_nights"]) / 2)
    return (w["origin"], w["destination"], w["cabin"], nights)


def route_history(db, origin, destination, cabin):
    rows = db.query(
        """SELECT price FROM prices
           WHERE origin=? AND destination=? AND cabin=?
             AND checked_at >= datetime('now', ?)""",
        [origin, destination, cabin, f"-{HISTORY_DAYS} days"],
    )
    return [r["price"] for r in rows]


def run(report=False):
    db = D1()
    checker = PriceChecker()
    every = int(os.environ.get("SAMPLE_EVERY_DAYS", "10"))
    watches = load_watches(db)
    if not watches:
        log.info("No active watches. Add some with: python -m flightwatch.manage")
        return

    # Group watches so each unique route is only searched once
    groups = {}
    for w in watches:
        groups.setdefault(route_key(w), []).append(w)

    per_user = {}  # email -> {"name":..., "deals": [...]}
    for (origin, dest, cabin, nights), ws in groups.items():
        months = max(w["months_ahead"] for w in ws)
        normal = deals.baseline(route_history(db, origin, dest, cabin))
        found = []
        for depart in sample_departures(months, every_days=every):
            price = checker.cheapest_round_trip(origin, dest, cabin, depart, nights)
            if price is None:
                continue
            ret = depart + timedelta(days=nights)
            found.append((price, depart.isoformat(), ret.isoformat()))
            db.execute(
                """INSERT INTO prices (origin, destination, cabin, depart_date, return_date, price)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [origin, dest, cabin, depart.isoformat(), ret.isoformat(), price],
            )
        log.info("%s-%s %s %sn: %d prices, normal=%s", origin, dest, cabin, nights, len(found), normal)
        if not found:
            continue

        found.sort()
        for w in ws:
            recent = [
                r["price"]
                for r in db.query(
                    "SELECT price FROM alerts WHERE watch_id=? AND sent_at >= datetime('now', ?)",
                    [w["id"], f"-{deals.REALERT_DAYS} days"],
                )
            ]
            pick = None
            for price, dep, ret in found:  # cheapest first
                if deals.is_deal(price, normal, w["drop_pct"], w["max_price"]) and deals.should_alert(price, recent):
                    pick = (price, dep, ret)
                    break
            is_real_deal = pick is not None
            if pick is None and report:
                pick = found[0]
            if pick is None:
                continue
            price, dep, ret = pick
            entry = per_user.setdefault(w["user_email"], {
                "name": w["user_name"], "deals": [],
                "token": w.get("user_token"), "basecamp": w.get("user_basecamp"),
            })
            entry["deals"].append({
                "origin": origin, "destination": dest, "price": price,
                "normal": int(normal) if normal else None,
                "depart": dep, "return": ret, "link": booking_link(origin, dest, dep, ret),
            })
            if is_real_deal:
                db.execute(
                    "INSERT INTO alerts (watch_id, depart_date, return_date, price) VALUES (?, ?, ?, ?)",
                    [w["id"], dep, ret, price],
                )

    site = os.environ.get("SITE_URL", "").rstrip("/")
    for email, info in per_user.items():
        manage_url = f"{site}/u/{info['token']}" if site and info.get("token") else None
        if info.get("basecamp") and notify.enabled():
            try:
                notify.post_basecamp(info["deals"], manage_url)
                log.info("posted %d to Basecamp for %s", len(info["deals"]), info["name"])
                continue
            except Exception as e:  # fall back to email
                log.warning("Basecamp post failed, emailing instead: %s", e)
        subject, html, text = mailer.render(info["name"], info["deals"], manage_url)
        if report:
            subject = subject.replace("deals", "fares").replace("deal ", "fare ") + " (test report)"
        mailer.send(email, subject, html, text)
        log.info("emailed %s (%d)", email, len(info["deals"]))

    # Keep the database small: old prices aren't used for "normal" anymore
    db.execute("DELETE FROM prices WHERE checked_at < datetime('now', '-120 days')")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--report", action="store_true", help="email cheapest fares even if not deals")
    run(report=p.parse_args().report)
