"""Read-only access to the Sleeper API (https://docs.sleeper.com)."""

from dataclasses import dataclass, field

from . import http

BASE = "https://api.sleeper.app/v1"


@dataclass
class League:
    league: dict
    rosters: list
    users: list
    players: dict  # sleeper player id -> player record
    traded_picks: list
    state: dict
    matchups: dict = field(default_factory=dict)  # week -> list of matchup rows


def fetch(league_id):
    league = http.get_json(f"{BASE}/league/{league_id}")
    state = http.get_json(f"{BASE}/state/nfl")
    data = League(
        league=league,
        rosters=http.get_json(f"{BASE}/league/{league_id}/rosters"),
        users=http.get_json(f"{BASE}/league/{league_id}/users"),
        players=http.get_json(f"{BASE}/players/nfl"),
        traded_picks=http.get_json(f"{BASE}/league/{league_id}/traded_picks"),
        state=state,
    )
    # Future weeks come back with a matchup_id and zero points, which gives
    # the rest of the regular-season schedule.
    for week in range(1, last_regular_week(league) + 1):
        data.matchups[week] = http.get_json(f"{BASE}/league/{league_id}/matchups/{week}")
    return data


def last_regular_week(league):
    return int((league.get("settings") or {}).get("playoff_week_start") or 15) - 1


def current_week(league, state):
    """The week being played now, or None outside this league's regular season."""
    if str(state.get("season")) != str(league.get("season")) or state.get("season_type") != "regular":
        return None
    week = int(state.get("week") or 0)
    return week if 1 <= week <= last_regular_week(league) else None


def schedule(data, weeks):
    """week -> list of (roster_id, roster_id) pairings."""
    out = {}
    for week in weeks:
        groups = {}
        for m in data.matchups.get(week, []):
            if m.get("matchup_id") is not None:
                groups.setdefault(m["matchup_id"], []).append(m["roster_id"])
        out[week] = [tuple(g) for g in groups.values() if len(g) == 2]
    return out


def completed_weeks(league, state):
    """Weeks of this league's season that are fully played."""
    if str(state.get("season")) != str(league.get("season")):
        return 0
    if state.get("season_type") != "regular":
        return 0
    return min(last_regular_week(league), max(0, int(state.get("week") or 0) - 1))


def fetch_trades(league_id, seasons):
    """Completed trades in this league and up to `seasons - 1` seasons before
    it, following Sleeper's previous_league_id chain. Each trade gets
    `season` and `teams` (roster id -> that season's team name) added."""
    out = []
    for _ in range(seasons):
        if not league_id or league_id == "0":
            break
        league = http.get_json(f"{BASE}/league/{league_id}")
        rosters = http.get_json(f"{BASE}/league/{league_id}/rosters")
        users = {u["user_id"]: u for u in http.get_json(f"{BASE}/league/{league_id}/users")}
        teams = {}
        for r in rosters:
            u = users.get(r.get("owner_id")) or {}
            teams[str(r["roster_id"])] = (u.get("metadata") or {}).get("team_name") or u.get("display_name") or f"Team {r['roster_id']}"
        # Transactions are listed per week ("leg"); offseason moves sit in the first legs.
        for leg in range(0, last_regular_week(league) + 5):
            for t in http.get_json(f"{BASE}/league/{league_id}/transactions/{leg}") or []:
                if t.get("type") == "trade" and t.get("status") == "complete":
                    out.append({**t, "season": league.get("season"), "teams": teams})
        league_id = league.get("previous_league_id")
    seen, unique = set(), []
    for t in sorted(out, key=lambda t: t.get("status_updated") or t.get("created") or 0):
        if t["transaction_id"] not in seen:
            seen.add(t["transaction_id"])
            unique.append(t)
    return unique
