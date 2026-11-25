"""Optional push to a Basecamp app (Aiden's personal message board).

Set BASECAMP_URL and BASECAMP_POST_TOKEN, and mark a user with basecamp=1.
Anyone self-hosting can ignore this; email still works on its own.
"""
import os

import httpx


def enabled():
    return bool(os.environ.get("BASECAMP_URL", "").strip() and os.environ.get("BASECAMP_POST_TOKEN", "").strip())


def post_basecamp(deal_list, manage_url=None):
    lines = []
    for d in deal_list:
        normal = f" (usually about ${d['normal']:,})" if d.get("normal") else ""
        lines.append(
            f"- **{d['origin']} to {d['destination']}: ${d['price']:,}**{normal}, "
            f"{d['depart']} to {d['return']} [[url:{d['link']}|Google Flights]]"
        )
    if manage_url:
        lines.append(f"\n[[url:{manage_url}|Change your routes]]")
    n = len(deal_list)
    r = httpx.post(
        os.environ["BASECAMP_URL"].strip().rstrip("/") + "/messages",
        headers={"Authorization": f"Bearer {os.environ['BASECAMP_POST_TOKEN'].strip()}"},
        json={
            "kind": "alert",
            "author": "flightwatch",
            "title": f"{n} flight deal{'s' if n != 1 else ''}",
            "body": "\n".join(lines),
        },
        timeout=30,
    )
    r.raise_for_status()
