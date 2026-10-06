"""FantasyCalc: values built from real trades (https://www.fantasycalc.com)."""

from datetime import date

from .. import config, http
from .common import SourceResult, add_pick, parse_pick

URL = "https://api.fantasycalc.com/values/current"


def fetch():
    return http.get_json(URL, params={
        "isDynasty": "true",
        "numQbs": config.NUM_QBS,
        "numTeams": config.NUM_TEAMS,
        "ppr": config.PPR,
    })


def parse(rows, names, today=None):
    out = SourceResult("FantasyCalc", today or date.today())
    for row in rows:
        p = row["player"]
        value = row["value"]
        if p.get("position") == "PICK":
            key = parse_pick(p["name"], config.NUM_TEAMS)
            if key:
                add_pick(out.picks, key, value)
            continue
        out.curve.append(value)
        pid = str(p.get("sleeperId") or "") or names.find(p["name"], p.get("position"))
        if not pid:
            out.unmatched.append(p["name"])
            continue
        out.players[pid] = value
        out.extra[pid] = {"redraft": row.get("redraftValue"), "trend30": row.get("trend30Day")}
    return out.finish()


HISTORY_URL = "https://api.fantasycalc.com/trades/implied/{fc_id}"


def fetch_history(fc_id):
    """Daily values for one FantasyCalc player or pick id, as {date: value}.
    FantasyCalc keeps about the current calendar year."""
    data = http.get_json(HISTORY_URL.format(fc_id=fc_id), params={
        "isDynasty": "true", "numQbs": config.NUM_QBS, "numTeams": config.NUM_TEAMS, "ppr": config.PPR})
    out = {}
    for row in data.get("historicalValues") or []:
        m, d, y = row["date"].split("/")
        out[date(int(y), int(m), int(d))] = row["value"]
    return out


def history_ids(rows):
    """Sleeper id -> FantasyCalc id, and (year, round, tier) -> FantasyCalc id."""
    players, picks = {}, {}
    for row in rows:
        p = row["player"]
        if p.get("position") == "PICK":
            key = parse_pick(p["name"], config.NUM_TEAMS)
            if key:
                picks[key] = p["id"]
        elif p.get("sleeperId"):
            players[str(p["sleeperId"])] = p["id"]
    return players, picks
