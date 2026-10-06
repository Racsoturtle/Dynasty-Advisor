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
    for week in range(1, completed_weeks(league, state) + 1):
        data.matchups[week] = http.get_json(f"{BASE}/league/{league_id}/matchups/{week}")
    return data


def completed_weeks(league, state):
    """Weeks of this league's season that are fully played."""
    if str(state.get("season")) != str(league.get("season")):
        return 0
    if state.get("season_type") != "regular":
        return 0
    return max(0, int(state.get("week") or 0) - 1)
