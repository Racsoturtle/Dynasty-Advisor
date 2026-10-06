"""Every trade idea the dashboard has suggested, re-valued each day.

The log lives on the repo's `data` branch (the daily workflow loads and saves
it). An idea keeps its id across days, so one that is still a good deal is
simply recommended again. Ideas Oscar marked as denied are kept here but no
longer recommended.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from . import config, github, trades


@dataclass
class Row:
    key: str
    entry: dict
    status: str  # "recommended", "denied", "gone", "dropped"
    note: str
    edge: float | None  # today, None when the offer can't be made any more
    league_edge: float | None
    gain: float | None  # consensus value Oscar would gain today
    deny_url: str


def update(log, today, ideas, league_teams, me_team, roster_positions, per_game, premium, denied):
    """Adds today's ideas to the log and re-values every logged idea.
    `denied` is {idea key: issue url} from GitHub, or None when GitHub
    couldn't be asked (then the marks already in the log stand).
    Returns (log, rows) with rows in display order."""
    log = {"version": 1, "ideas": dict((log or {}).get("ideas") or {})}
    day = today.isoformat()

    for i in ideas:
        e = log["ideas"].get(i.key)
        if not e:
            e = log["ideas"][i.key] = {
                "partner_id": i.partner.roster_id, "partner": i.partner.team_name,
                "give": [[a.key, a.label] for a in i.give], "get": [[a.key, a.label] for a in i.get],
                "first_seen": day, "first_edge": round(i.edge, 6), "first_league_edge": round(i.league_edge, 6),
                "days_recommended": 0, "last_recommended": None, "denied": False, "checks": [],
            }
        if e["last_recommended"] != day:
            e["days_recommended"] += 1
        e["last_recommended"] = day
        # Names and pick tiers can change; the ids in the key don't.
        e["partner"] = i.partner.team_name
        e["give"], e["get"] = [[a.key, a.label] for a in i.give], [[a.key, a.label] for a in i.get]

    if denied is not None:
        for key, e in log["ideas"].items():
            was = e.get("denied")
            e["denied"] = key in denied
            e["issue"] = denied.get(key)
            if e["denied"] and not was:
                e["denied_on"] = day

    cutoff = (today - timedelta(days=config.LOG_KEEP_DAYS)).isoformat()
    log["ideas"] = {k: e for k, e in log["ideas"].items() if (e["last_recommended"] or e["first_seen"]) >= cutoff}

    roster_size = sum(1 for s in roster_positions if s not in ("IR", "TAXI"))
    teams = {t.roster_id: t for t in league_teams}
    me = trades.TeamState(me_team, roster_positions, roster_size, per_game)
    mine = {a.key: a for a in trades.assets_for(me_team, 0)}
    today_keys = [i.key for i in ideas]
    rows = []
    for key, e in log["ideas"].items():
        partner = teams.get(e["partner_id"])
        theirs = {a.key: a for a in trades.assets_for(partner, 0)} if partner else {}
        give = [mine.get(k) for k, _ in e["give"]]
        get = [theirs.get(k) for k, _ in e["get"]]
        moved = [label for (k, label), a in zip(e["give"] + e["get"], give + get) if a is None]
        edge = league_edge = gain = None
        if moved:
            status, note = "gone", f"{', '.join(moved)} {'has' if len(moved) == 1 else 'have'} moved since."
        else:
            them = trades.TeamState(partner, roster_positions, roster_size, per_game)
            nums = trades.evaluate(me, them, give, get, premium)
            edge, league_edge = nums["edge"], nums["league_edge"]
            gain = nums["get_value"] - nums["give_value"]
            e["checks"] = [c for c in e["checks"] if c[0] != day][-59:] + [[day, round(edge, 6), round(league_edge, 6)]]
            status, note = ("recommended", "") if key in today_keys else ("dropped", _why_not(nums))
        if e.get("denied"):
            status, note = "denied", f"Marked denied{' on ' + _short(e['denied_on']) if e.get('denied_on') else ''}."
        url = github.deny_url(key, e["partner"], [g[1] for g in e["give"]], [g[1] for g in e["get"]])
        rows.append(Row(key, e, status, note, edge, league_edge, gain, url))

    order = {"recommended": 0, "dropped": 1, "gone": 2, "denied": 3}
    rows.sort(key=lambda r: (order[r.status],
                             today_keys.index(r.key) if r.key in today_keys else 0,
                             _neg_date(r.entry["last_recommended"] or r.entry["first_seen"])))
    return log, rows


def _why_not(nums):
    if nums["edge"] < config.TRADE_MIN_EDGE:
        return "Values moved, so it no longer wins enough for you."
    if nums["edge"] > config.TRADE_MAX_TRUE_EDGE or nums["league_edge"] > config.TRADE_MAX_EDGE:
        return "Values moved, so it now looks too lopsided for them to accept."
    if nums["their_lineup_change"] <= 0:
        return "It no longer improves their starting lineup."
    return "Still a fair deal, but other ideas ranked higher today or it no longer fits the call."


def _short(iso):
    return date.fromisoformat(iso).strftime("%b %-d")


def _neg_date(iso):
    return -date.fromisoformat(iso).toordinal()
