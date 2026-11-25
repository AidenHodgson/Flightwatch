"""Add and list people and routes without touching SQL.

  python -m flightwatch.manage add-user "Dad" dad@example.com
  python -m flightwatch.manage link dad@example.com
  python -m flightwatch.manage add-watch dad@example.com ATL FCO --nights 5-10 --months 6
  python -m flightwatch.manage list
  python -m flightwatch.manage pause-watch 3
"""
import argparse
import os
import secrets

from fli.models import Airport

from .db import D1


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    u = sub.add_parser("add-user")
    u.add_argument("name")
    u.add_argument("email")
    u.add_argument("--basecamp", action="store_true", help="ping Basecamp instead of email")

    lk = sub.add_parser("link", help="print someone's settings page link")
    lk.add_argument("email")

    w = sub.add_parser("add-watch")
    w.add_argument("email")
    w.add_argument("origin")
    w.add_argument("destinations", nargs="+", help="one or more airport codes")
    w.add_argument("--cabin", default="ECONOMY", choices=["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"])
    w.add_argument("--nights", default="5-10", help="trip length range, e.g. 5-10")
    w.add_argument("--months", type=int, default=6, help="how far ahead to look")
    w.add_argument("--drop", type=int, default=30, help="alert when this %% below normal")
    w.add_argument("--max-price", type=int, help="always alert under this price")

    sub.add_parser("list")
    pw = sub.add_parser("pause-watch")
    pw.add_argument("watch_id", type=int)

    a = p.parse_args()
    db = D1()

    if a.cmd == "add-user":
        token = secrets.token_urlsafe(18)
        db.execute(
            "INSERT INTO users (name, email, token, basecamp) VALUES (?, ?, ?, ?)",
            [a.name, a.email.lower(), token, 1 if a.basecamp else 0],
        )
        print(f"Added {a.name}. Settings link: {_link(token)}")
    elif a.cmd == "link":
        rows = db.query("SELECT token FROM users WHERE email=?", [a.email.lower()])
        if not rows:
            raise SystemExit(f"No user with email {a.email}")
        token = rows[0]["token"]
        if not token:
            token = secrets.token_urlsafe(18)
            db.execute("UPDATE users SET token=? WHERE email=?", [token, a.email.lower()])
        print(_link(token))
    elif a.cmd == "add-watch":
        rows = db.query("SELECT id FROM users WHERE email=?", [a.email.lower()])
        if not rows:
            raise SystemExit(f"No user with email {a.email}. Run add-user first.")
        lo, hi = (int(x) for x in a.nights.split("-"))
        for code in [a.origin, *a.destinations]:
            if code.upper() not in Airport.__members__:
                raise SystemExit(f"Unknown airport code: {code}")
        for dest in a.destinations:
            db.execute(
                """INSERT INTO watches (user_id, origin, destination, cabin, min_nights, max_nights,
                   months_ahead, drop_pct, max_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [rows[0]["id"], a.origin.upper(), dest.upper(), a.cabin, lo, hi, a.months, a.drop, a.max_price],
            )
            print(f"Watching {a.origin.upper()} to {dest.upper()}")
    elif a.cmd == "list":
        for r in db.query(
            """SELECT w.id, u.name, w.origin, w.destination, w.cabin, w.min_nights, w.max_nights,
                      w.months_ahead, w.drop_pct, w.max_price, w.active
               FROM watches w JOIN users u ON u.id = w.user_id ORDER BY u.name, w.id"""
        ):
            state = "" if r["active"] else " (paused)"
            print(f"#{r['id']} {r['name']}: {r['origin']}-{r['destination']} {r['cabin']} "
                  f"{r['min_nights']}-{r['max_nights']} nights, {r['months_ahead']} mo, "
                  f"-{r['drop_pct']}%{state}")
    elif a.cmd == "pause-watch":
        db.execute("UPDATE watches SET active=0 WHERE id=?", [a.watch_id])
        print(f"Paused #{a.watch_id}")


def _link(token):
    site = os.environ.get("SITE_URL", "").rstrip("/")
    return f"{site}/u/{token}" if site else f"/u/{token} (set SITE_URL for the full link)"


if __name__ == "__main__":
    main()
