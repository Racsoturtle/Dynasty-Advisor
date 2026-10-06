"""KeepTradeCut: crowdsourced keep/trade/cut votes (https://keeptradecut.com).

KTC has no public API. Its rankings page embeds every player as a
`playersArray` JavaScript variable, which is what this reads.
"""

import json
import re
from datetime import date

from .. import http
from .common import SourceResult, add_pick, parse_pick

URL = "https://keeptradecut.com/dynasty-rankings"
_ARRAY = re.compile(r"var\s+playersArray\s*=\s*(\[.*?\]);", re.DOTALL)


def fetch():
    html = http.get_text(URL, params={"page": 0, "filters": "QB|WR|RB|TE|RDP", "format": 1})
    m = _ARRAY.search(html)
    if not m:
        raise ValueError("KeepTradeCut page no longer has playersArray; the page layout changed")
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
