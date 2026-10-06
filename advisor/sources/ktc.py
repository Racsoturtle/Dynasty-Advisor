"""KeepTradeCut: crowdsourced keep/trade/cut votes (https://keeptradecut.com).

KTC has no public API. Its rankings page embeds the top 500 players and
picks as JSON in a `<script id="ktc-players">` tag, which is what this reads.
Older versions of the page used a `playersArray` JavaScript variable.
"""

import json
import re
from datetime import date

from .. import http
from .common import SourceResult, add_pick, parse_pick

URL = "https://keeptradecut.com/dynasty-rankings"
_JSON_TAG = re.compile(r'<script[^>]*id="ktc-players"[^>]*>(.*?)</script>', re.DOTALL)
_ARRAY = re.compile(r"var\s+playersArray\s*=\s*(\[.*?\]);", re.DOTALL)


def fetch():
    html = http.get_text(URL, params={"page": 0, "filters": "QB|WR|RB|TE|RDP", "format": 1})
    return extract(html)


def extract(html):
    m = _JSON_TAG.search(html) or _ARRAY.search(html)
    if not m:
        raise ValueError("couldn't find player data on the KeepTradeCut page; its layout changed")
    return json.loads(m.group(1))


def parse(rows, names, ktc_to_sleeper, today=None):
    out = SourceResult("KeepTradeCut", today or date.today())
    for row in rows:
        value = (row.get("oneQBValues") or {}).get("value")
        if not value:
            continue
        name, pos = row["playerName"], row.get("position")
        if pos in ("RDP", "PICK"):
            key = parse_pick(name)
            if key:
                add_pick(out.picks, key, value)
            continue
        out.curve.append(value)
        pid = ktc_to_sleeper.get(str(row.get("playerID"))) or names.find(name, pos)
        if not pid:
            out.unmatched.append(name)
            continue
        out.players[pid] = value
    return out.finish()


PLAYER_URL = "https://keeptradecut.com/dynasty-rankings/players/{slug}"
_PLAYER_TAG = re.compile(r'<script[^>]*id="pd-oneqb"[^>]*>(.*?)</script>', re.DOTALL)


def fetch_history(slug):
    """Daily 1QB values for one KTC player or pick page, as {date: value}."""
    m = _PLAYER_TAG.search(http.get_text(PLAYER_URL.format(slug=slug)))
    if not m:
        raise ValueError(f"no value history on the KeepTradeCut page for {slug}")
    out = {}
    for row in json.loads(m.group(1)).get("overallValue") or []:
        d = row["d"]  # YYMMDD
        out[date(2000 + int(d[:2]), int(d[2:4]), int(d[4:]))] = row["v"]
    return out


def slug_for(name, ktc_id):
    """KTC page slugs are the name's letters and digits in lowercase runs
    joined by hyphens, then the KTC id: "De'Von Achane" -> de-von-achane-1398."""
    words = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{words}-{ktc_id}"
