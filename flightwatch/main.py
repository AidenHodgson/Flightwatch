"""Daily run: check every watched route once, save prices, email deals.

Usage:
  python -m flightwatch.main            # normal run
  python -m flightwatch.main --test     # also email everyone a short "you're
                                        # set up" note to check email works
"""
import argparse
import logging
import os
from datetime import date, timedelta

from . import airlines, deals, github_alert, mailer, notify, window
from .db import D1
from .search import PriceChecker, booking_link, sample_departures

log = logging.getLogger("flightwatch")
HISTORY_DAYS = 60


def load_watches(db):
    return db.query(
        """SELECT w.*, u.name AS user_name, u.email AS user_email,
                  u.token AS user_token, u.basecamp AS user_basecamp,
                  u.airlines AS user_airlines, u.airline_mode AS user_airline_mode
           FROM watches w JOIN users u ON u.id = w.user_id
           WHERE w.active = 1 AND u.active = 1"""
    )


def route_key(w):
    nights = round((w["min_nights"] + w["max_nights"]) / 2)
    return (w["origin"], w["destination"], w["cabin"], nights)


def route_history(db, origin, destination, cabin):
    rows = db.query(
        """SELECT price, date(checked_at) AS day FROM prices
           WHERE origin=? AND destination=? AND cabin=?
             AND checked_at >= datetime('now', ?)""",
        [origin, destination, cabin, f"-{HISTORY_DAYS} days"],
    )
    return [r["price"] for r in rows], len({r["day"] for r in rows})


def pick_options(w, results):
    """Each date's itineraries, narrowed to the person's airlines.

    'only' mode: just those airlines. 'prefer' mode (the default): those airlines
    if they fly this route on any date we checked, otherwise any airline."""
    wanted = airlines.parse(w.get("user_airlines"))
    per_date = [(dep, ret, r, r.get("options") or [{"price": r["price"], "airlines": [], "stops": None}])
                for dep, ret, r in results]
    if not wanted:
        return per_date, False
    narrowed = [(dep, ret, r, [o for o in opts if airlines.matches(o, wanted)]) for dep, ret, r, opts in per_date]
    if (w.get("user_airline_mode") or "prefer") == "only" or any(opts for *_, opts in narrowed):
        return narrowed, False
    return per_date, True  # nothing on their airlines here, so fall back to any


def evaluate_watch(w, results, normal):
    """Find this person's sale on this route, or None. Looks at every date so the
    email can say when the sale runs (one week, a month, a whole season)."""
    last_day = date.today() + timedelta(days=30 * w["months_ahead"])
    dated, fell_back = pick_options(w, [x for x in results if x[0] <= last_day])
    checked, sales = 0, []
    for dep, ret, r, opts in dated:
        if not opts:
            continue
        checked += 1
        best = opts[0]
        price, typical, range_low = best["price"], r.get("typical"), r.get("range_low")
        if typical and range_low:
            sale = deals.is_sale(price, typical, range_low, w["drop_pct"])  # Google's numbers
            usual = typical
        else:
            sale = deals.is_deal(price, normal, w["drop_pct"])  # our own history
            usual = normal
        cheap_enough = w["max_price"] is not None and price <= w["max_price"]
        if sale or cheap_enough:
            sales.append({"dep": dep, "ret": ret, "price": price, "usual": usual, "option": best,
                          "range": (r.get("range_low"), r.get("range_high"))})
    if not sales:
        return None
    top = min(sales, key=lambda x: x["price"])
    usual = int(top["usual"]) if top["usual"] else None
    return {
        "origin": w["origin"], "destination": w["destination"],
        "price": top["price"], "normal": usual,
        "pct_off": round(100 * (1 - top["price"] / usual)) if usual else None,
        "range_low": top["range"][0], "range_high": top["range"][1],
        "depart": top["dep"].isoformat(), "return": top["ret"].isoformat(),
        "nights": (top["ret"] - top["dep"]).days,
        "flight": airlines.describe(top["option"]),
        "other_airline": fell_back,
        "window": window.describe([x["dep"] for x in sales]),
        "window_share": window.share(len(sales), checked),
        "sale_dates": len(sales),
        "price_span": (min(x["price"] for x in sales), max(x["price"] for x in sales)),
        "link": booking_link(w["origin"], w["destination"], top["dep"].isoformat(), top["ret"].isoformat()),
    }


def run(test=False):
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

    per_user = {}  # email -> {"name", "deals", "token", "basecamp", "sent"}
    for (origin, dest, cabin, nights), ws in groups.items():
        months = max(w["months_ahead"] for w in ws)
        history, days_seen = route_history(db, origin, dest, cabin)
        normal = deals.baseline(history, days_seen)

        # One search per departure date, shared by everyone watching this route
        results = []
        for depart in sample_departures(months, every_days=every):
            r = checker.check(origin, dest, cabin, depart, nights)
            if r is None:
                continue
            ret = depart + timedelta(days=nights)
            results.append((depart, ret, r))
            db.execute(
                """INSERT INTO prices (origin, destination, cabin, depart_date, return_date, price,
                                       typical, range_low, range_high)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [origin, dest, cabin, depart.isoformat(), ret.isoformat(), r["price"],
                 r.get("typical"), r.get("range_low"), r.get("range_high")],
            )
        log.info("%s-%s %s %sn: %d prices, own normal=%s", origin, dest, cabin, nights, len(results), normal)
        if not results:
            continue

        for w in ws:
            deal = evaluate_watch(w, results, normal)
            if deal is None:
                continue
            recent = [r["price"] for r in db.query(
                "SELECT price FROM alerts WHERE watch_id=? AND sent_at >= datetime('now', ?)",
                [w["id"], f"-{deals.REALERT_DAYS} days"],
            )]
            if not deals.should_alert(deal["price"], recent):
                continue
            entry = per_user.setdefault(w["user_email"], {
                "name": w["user_name"], "deals": [],
                "token": w.get("user_token"), "basecamp": w.get("user_basecamp"), "sent": [],
            })
            entry["deals"].append(deal)
            entry["sent"].append((w["id"], deal["depart"], deal["return"], deal["price"]))

    site = os.environ.get("SITE_URL", "").strip().rstrip("/")
    failed, pending, errors = [], [], []

    def record(info):
        # Only remember a deal as sent once it actually went out,
        # so a failed email gets retried on the next run
        for watch_id, dep, ret, price in info["sent"]:
            db.execute(
                "INSERT INTO alerts (watch_id, depart_date, return_date, price) VALUES (?, ?, ?, ?)",
                [watch_id, dep, ret, price],
            )

    login_broken = False
    for email, info in per_user.items():
        if login_broken:
            failed.append(email)
            pending.append((info["name"], info["deals"]))
            continue
        manage_url = f"{site}/u/{info['token']}" if site and info.get("token") else None
        if info.get("basecamp") and notify.enabled():
            try:
                notify.post_basecamp(info["deals"], manage_url)
                record(info)
                log.info("posted %d to Basecamp for %s", len(info["deals"]), info["name"])
                continue
            except Exception as e:  # fall back to email
                log.warning("Basecamp post failed, emailing instead: %s", e)
        subject, html, text = mailer.render(info["name"], info["deals"], manage_url)
        try:
            mailer.send(email, subject, html, text)
            record(info)
            log.info("emailed %s (%d)", email, len(info["deals"]))
        except Exception as e:  # one bad email shouldn't stop the others
            failed.append(email)
            pending.append((info["name"], info["deals"]))
            errors.append(str(e))
            log.error("could not email %s: %s", email, e)
            if isinstance(e, mailer.EmailLoginError):
                # Same login for everyone: stop trying, keep the rest of the deals waiting
                login_broken = True

    if test and not login_broken:
        f2, e2 = send_setup_emails(watches, site)
        failed += f2
        errors += e2

    # Backup channel: a GitHub issue that says what broke and holds the waiting deals
    try:
        if errors:
            github_alert.report_failure(errors[0], pending)
        elif per_user or test:
            github_alert.clear_failure()
    except Exception as e:
        log.warning("could not update the GitHub issue: %s", e)

    # Keep the database small: old prices aren't used for "normal" anymore
    db.execute("DELETE FROM prices WHERE checked_at < datetime('now', '-120 days')")
    if failed:
        # Prices are saved and unsent deals retry next run. Exit non-zero so the
        # run shows red in GitHub, with the reason as the last line of the log.
        raise SystemExit(f"Prices saved. Email failed for {len(failed)} person(s): {errors[0]}")


def send_setup_emails(watches, site):
    """One short note per person so you can confirm email works. No fares."""
    people = {}
    for w in watches:
        people.setdefault(w["user_email"], {"name": w["user_name"], "token": w.get("user_token"), "n": 0})["n"] += 1
    failed, errors = [], []
    for email, p in people.items():
        manage_url = f"{site}/u/{p['token']}" if site and p.get("token") else None
        subject, html, text = mailer.render_setup(p["name"], p["n"], manage_url)
        try:
            mailer.send(email, subject, html, text)
            log.info("sent setup email to %s", email)
        except Exception as e:
            failed.append(email)
            errors.append(str(e))
            log.error("could not email %s: %s", email, e)
            if isinstance(e, mailer.EmailLoginError):
                break
    return failed, errors


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--test", "--report", dest="test", action="store_true",
                   help="also send everyone a short setup email (no fares)")
    run(test=p.parse_args().test)
