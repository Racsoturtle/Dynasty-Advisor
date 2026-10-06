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
