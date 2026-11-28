"""Temporary: dump standings, divisions and the remaining schedule from Sleeper."""
import json, sys
sys.path.insert(0, ".")
from advisor import config, http, sleeper

B = sleeper.BASE
lid = config.LEAGUE_ID
league = http.get_json(f"{B}/league/{lid}")
state = http.get_json(f"{B}/state/nfl")
rosters = http.get_json(f"{B}/league/{lid}/rosters")
users = http.get_json(f"{B}/league/{lid}/users")
last = sleeper.last_regular_week(league)
matchups = {w: [{"roster_id": m["roster_id"], "matchup_id": m.get("matchup_id"), "points": m.get("points")}
                for m in http.get_json(f"{B}/league/{lid}/matchups/{w}")] for w in range(1, last + 1)}
names = {u["user_id"]: u.get("display_name") for u in users}
out = {
    "state": {k: state.get(k) for k in ("season", "season_type", "week", "display_week", "leg")},
    "settings": league.get("settings"),
    "metadata": league.get("metadata"),
    "rosters": [{"roster_id": r["roster_id"], "owner": names.get(r.get("owner_id")),
                 "settings": r.get("settings")} for r in rosters],
    "matchups": matchups,
}
print(json.dumps(out))
