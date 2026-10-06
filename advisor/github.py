"""Offers Oscar marked as denied, read from GitHub issues.

The dashboard is a static site, so the "Mark as denied" button opens a new
GitHub issue with the offer's id in the title. Each build reads Oscar's open
issues; closing the issue undoes the mark. Issues opened by anyone else are
ignored, since the repo is public.
"""

import os
import re
from urllib.parse import quote

from . import config, http

API = "https://api.github.com"
_KEY = re.compile(r"^Denied:.*\[([0-9a-f]{10})\]\s*$")


def denied_issues():
    """{idea key: issue url} for Oscar's open "Denied" issues, or None when
    there's no token to ask GitHub with (local runs)."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"}
    out, page = {}, 1
    while True:
        rows = http.get(f"{API}/repos/{config.GITHUB_REPO}/issues", headers=headers, params={
            "state": "open", "creator": config.GITHUB_OWNER, "per_page": 100, "page": page}).json()
        for issue in rows:
            m = _KEY.match(issue.get("title") or "")
            if m and (issue.get("user") or {}).get("login", "").lower() == config.GITHUB_OWNER.lower():
                out[m.group(1)] = issue["html_url"]
        if len(rows) < 100:
            return out
        page += 1


def deny_url(key, partner, give, get):
    """A link that opens a prefilled "Denied" issue for one offer."""
    title = f"Denied: {' + '.join(give)} to {partner} for {' + '.join(get)} [{key}]"
    body = (f"I offered this to {partner} and they said no, so the dashboard should stop suggesting it.\n\n"
            f"- I give: {', '.join(give)}\n- I get: {', '.join(get)}\n\n"
            "Submit this issue to mark it. Close it later if you want the dashboard to suggest this offer again.")
    return (f"https://github.com/{config.GITHUB_REPO}/issues/new?labels=denied"
            f"&title={quote(title)}&body={quote(body)}")
