"""DynastyProcess open data (https://github.com/dynastyprocess/data).

DynastyProcess values are a fixed formula applied to FantasyPros expert
consensus rankings (ECR), so the two always rank players in the same order.
They count as ONE vote here, labelled "FantasyPros (via DynastyProcess)".
"""

import csv
import io
import os
from datetime import date

from .. import http
from .common import SourceResult, add_pick, parse_pick

BASE = "https://raw.githubusercontent.com/dynastyprocess/data/master/files"


def fetch_values():
    return list(csv.DictReader(io.StringIO(http.get_text(f"{BASE}/values.csv"))))


def fetch_ids():
    return list(csv.DictReader(io.StringIO(http.get_text(f"{BASE}/db_playerids.csv"))))


def id_maps(id_rows):
    """fantasypros id -> sleeper id, and ktc id -> sleeper id."""
    fp, ktc = {}, {}
    for r in id_rows:
        sid = r.get("sleeper_id")
        if not sid or sid == "NA":
            continue
        if r.get("fantasypros_id") not in (None, "", "NA"):
            fp[r["fantasypros_id"]] = sid
        if r.get("ktc_id") not in (None, "", "NA"):
            ktc[r["ktc_id"]] = sid
    return fp, ktc


def parse(rows, names, fp_to_sleeper):
    dates = [r["scrape_date"] for r in rows if r.get("scrape_date") not in (None, "", "NA")]
    as_of = date.fromisoformat(max(dates)) if dates else date.min
    out = SourceResult("FantasyPros (via DynastyProcess)", as_of)
    for r in rows:
        if r.get("value_1qb") in (None, "", "NA"):
            continue
        value = float(r["value_1qb"])
        if r["pos"] == "PICK":
            key = parse_pick(r["player"])
            if key:
                add_pick(out.picks, key, value)
            continue
        out.curve.append(value)
        pid = fp_to_sleeper.get(r.get("fp_id")) or names.find(r["player"], r["pos"])
        if not pid:
            out.unmatched.append(r["player"])
            continue
        out.players[pid] = value
    return out.finish()


COMMITS_URL = "https://api.github.com/repos/dynastyprocess/data/commits"
RAW_AT = "https://raw.githubusercontent.com/dynastyprocess/data/{sha}/files/values.csv"


def fetch_versions(since):
    """Past versions of values.csv since a date, newest first, as
    (date, commit sha). DynastyProcess updates the file every week or so."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    out, page = [], 1
    while True:
        rows = http.get(COMMITS_URL, params={"path": "files/values.csv", "since": f"{since}T00:00:00Z",
                                             "per_page": 100, "page": page}, headers=headers).json()
        out += [(date.fromisoformat(r["commit"]["committer"]["date"][:10]), r["sha"]) for r in rows]
        if len(rows) < 100:
            return out
        page += 1


def fetch_values_at(sha):
    return list(csv.DictReader(io.StringIO(http.get_text(RAW_AT.format(sha=sha)))))
