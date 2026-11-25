"""Backup channel: if email fails, keep one GitHub issue open with the problem
and the waiting deals. GitHub notifies the repo owner (email and the GitHub app)
when it opens, and it closes itself once email works again.

Only runs inside GitHub Actions (needs GITHUB_TOKEN and GITHUB_REPOSITORY).
Never includes anyone's email address, since the repo may be public.
"""
import os

import httpx

TITLE = "Flightwatch can't send email"


def _client():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        return None, None
    c = httpx.Client(
        base_url=f"https://api.github.com/repos/{repo}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=20,
    )
    return c, repo


def _open_issue(c):
    r = c.get("/issues", params={"state": "open", "per_page": 50})
    r.raise_for_status()
    for i in r.json():
        if i.get("title") == TITLE and "pull_request" not in i:
            return i
    return None


def report_failure(error, pending):
    """pending: list of (person_name, deals) that didn't go out."""
    c, _ = _client()
    if not c:
        return
    lines = [
        "Flightwatch checked prices fine, but couldn't send email.",
        "",
        f"**Error:** {error}",
        "",
        "This issue updates on every run and closes itself once email works again. "
        "Deals below are kept and will be emailed on the next run that can send.",
    ]
    for name, deals in pending:
        lines += ["", f"### Waiting for {name}"]
        for d in deals:
            normal = f" (usually about ${d['normal']:,})" if d.get("normal") else ""
            lines.append(f"- **{d['origin']} to {d['destination']}: ${d['price']:,}**{normal}, "
                         f"{d['depart']} to {d['return']} ([Google Flights]({d['link']}))")
    body = "\n".join(lines)
    existing = _open_issue(c)
    if existing:
        c.patch(f"/issues/{existing['number']}", json={"body": body}).raise_for_status()
    else:
        c.post("/issues", json={"title": TITLE, "body": body}).raise_for_status()


def clear_failure():
    c, _ = _client()
    if not c:
        return
    existing = _open_issue(c)
    if existing:
        c.post(f"/issues/{existing['number']}/comments", json={"body": "Email is working again."})
        c.patch(f"/issues/{existing['number']}", json={"state": "closed"})
