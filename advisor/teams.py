"""Builds a picture of every team: roster, picks, values, needs and luck."""

from dataclasses import dataclass, field

from . import config
from .sleeper import completed_weeks

POSITIONS = ("QB", "RB", "WR", "TE")
FLEX_ELIGIBLE = {
    "FLEX": ("RB", "WR", "TE"),
    "WRRB_FLEX": ("RB", "WR"),
    "REC_FLEX": ("WR", "TE"),
    "SUPER_FLEX": ("QB", "RB", "WR", "TE"),
}


@dataclass
class RosterPlayer:
    pid: str
    name: str
    pos: str
    team: str
    age: float | None
    status: str  # starter, bench, taxi, ir
    value: float
    by_source: dict
    disagree: bool
    in_value_lineup: bool = False
    injury: str | None = None


@dataclass
class Pick:
    year: int
    round: int
    original_roster_id: int
    original_owner: str
    tier: str
    value: float


@dataclass
class Team:
    roster_id: int
    owner_id: str
    owner: str
    team_name: str
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    players: list = field(default_factory=list)
    picks: list = field(default_factory=list)
    player_value: float = 0.0
    pick_value: float = 0.0
    lineup_value: float = 0.0
    position_value: dict = field(default_factory=dict)
    position_rank: dict = field(default_factory=dict)
    avg_age: float | None = None
    allplay_wins: int = 0
    allplay_losses: int = 0
    weekly_points: list = field(default_factory=list)
    ranks: dict = field(default_factory=dict)
    league_size: int = 16

    @property
    def total_value(self):
        return self.player_value + self.pick_value

    @property
    def games(self):
        return self.wins + self.losses + self.ties

    @property
    def expected_wins(self):
        n = self.allplay_wins + self.allplay_losses
        return self.games * self.allplay_wins / n if n else 0.0

    @property
    def needs(self):
        """Positions where this team ranks in the bottom half, worst first."""
        return sorted((p for p, r in self.position_rank.items() if r > self.league_size / 2),
                      key=lambda p: -self.position_rank[p])

    @property
    def strengths(self):
        return sorted((p for p, r in self.position_rank.items() if r <= 4),
                      key=lambda p: self.position_rank[p])


def value_lineup(players, roster_positions):
    """Best lineup by consensus value. K and DEF aren't valued by any source,
    so only offensive skill slots count. Filling fixed slots first and flex
    slots from what's left is optimal for these slot types."""
    slots = [s for s in roster_positions if s in POSITIONS or s in FLEX_ELIGIBLE]
    pool = sorted((p for p in players if p.status != "taxi" and p.pos in POSITIONS),
                  key=lambda p: -p.value)
    used = set()
    chosen = []
    for slot in [s for s in slots if s in POSITIONS]:
        best = next((p for p in pool if p.pid not in used and p.pos == slot), None)
        if best:
            used.add(best.pid)
            chosen.append(best)
    for slot in [s for s in slots if s in FLEX_ELIGIBLE]:
        best = next((p for p in pool if p.pid not in used and p.pos in FLEX_ELIGIBLE[slot]), None)
        if best:
            used.add(best.pid)
            chosen.append(best)
    return chosen


def build(data, cons):
    league = data.league
    users = {u["user_id"]: u for u in data.users}
    roster_positions = league.get("roster_positions", [])
    teams = []
    for r in data.rosters:
        s = r.get("settings") or {}
        user = users.get(r.get("owner_id")) or {}
        t = Team(
            roster_id=r["roster_id"],
            owner_id=r.get("owner_id") or "",
            owner=user.get("display_name") or f"Team {r['roster_id']}",
            team_name=(user.get("metadata") or {}).get("team_name") or user.get("display_name") or f"Team {r['roster_id']}",
            wins=s.get("wins", 0),
            losses=s.get("losses", 0),
            ties=s.get("ties", 0),
            points_for=s.get("fpts", 0) + s.get("fpts_decimal", 0) / 100,
            points_against=s.get("fpts_against", 0) + s.get("fpts_against_decimal", 0) / 100,
        )
        t.league_size = len(data.rosters)
        t.players = _roster_players(r, data.players, cons)
        teams.append(t)

    for t in teams:
        lineup = value_lineup(t.players, roster_positions)
        for p in lineup:
            p.in_value_lineup = True
        t.lineup_value = sum(p.value for p in lineup)
        t.position_value = {pos: sum(p.value for p in lineup if p.pos == pos) for pos in POSITIONS}
        t.player_value = sum(p.value for p in t.players)
        aged = [p for p in t.players if p.age and p.value > 0]
        weight = sum(p.value for p in aged)
        t.avg_age = sum(p.age * p.value for p in aged) / weight if weight else None

    _add_allplay(teams, data)
    _rank(teams)
    _add_picks(teams, data, cons)
    for t in teams:
        t.pick_value = sum(p.value for p in t.picks)
    _rank(teams)  # total value now includes picks
    return teams


def _roster_players(roster, players_db, cons):
    taxi = set(roster.get("taxi") or [])
    ir = set(roster.get("reserve") or [])
    starters = set(roster.get("starters") or [])
    out = []
    for pid in roster.get("players") or []:
        info = players_db.get(pid, {})
        v = cons.players.get(pid)
        status = "taxi" if pid in taxi else "ir" if pid in ir else "starter" if pid in starters else "bench"
        name = info.get("full_name") or f"{info.get('first_name', '')} {info.get('last_name', '')}".strip() or pid
        out.append(RosterPlayer(
            pid=pid,
            name=name,
            pos=info.get("position") or "?",
            team=info.get("team") or "FA",
            age=info.get("age"),
            status=status,
            value=v.consensus if v else 0.0,
            by_source=v.by_source if v else {},
            disagree=v.disagree if v else False,
            injury=info.get("injury_status"),
        ))
    out.sort(key=lambda p: -p.value)
    return out


def _add_allplay(teams, data):
    by_id = {t.roster_id: t for t in teams}
    for week in range(1, completed_weeks(data.league, data.state) + 1):
        rows = [m for m in data.matchups.get(week, []) if m.get("points") is not None]
        for m in rows:
            t = by_id.get(m["roster_id"])
            if not t:
                continue
            t.weekly_points.append(m["points"])
            for other in rows:
                if other is m:
                    continue
                if m["points"] > other["points"]:
                    t.allplay_wins += 1
                elif m["points"] < other["points"]:
                    t.allplay_losses += 1


def _rank(teams):
    def rank_by(key):
        ordered = sorted(teams, key=key, reverse=True)
        return {t.roster_id: i + 1 for i, t in enumerate(ordered)}

    ranks = {
        "total_value": rank_by(lambda t: t.total_value),
        "lineup_value": rank_by(lambda t: t.lineup_value),
        "points_for": rank_by(lambda t: t.points_for),
        "points_against": rank_by(lambda t: t.points_against),
        "standings": rank_by(lambda t: (t.wins + 0.5 * t.ties, t.points_for)),
    }
    for pos in POSITIONS:
        ranks[pos] = rank_by(lambda t, pos=pos: t.position_value.get(pos, 0))
    for t in teams:
        t.ranks = {k: v[t.roster_id] for k, v in ranks.items()}
        t.position_rank = {pos: t.ranks[pos] for pos in POSITIONS}


def _add_picks(teams, data, cons):
    """Every team owns its own picks unless Sleeper lists a trade.

    Next year's picks are priced early, mid or late by how strong the
    original team looks now: the average of its standings rank and its
    starting-lineup value rank. Later years are priced as an average pick.
    """
    league = data.league
    season = int(league["season"])
    rounds = int((league.get("settings") or {}).get("draft_rounds") or 3)
    years = [season + i for i in range(1, config.PICK_YEARS_AHEAD + 1)]
    by_id = {t.roster_id: t for t in teams}

    owner = {(y, rnd, rid): rid for y in years for rnd in range(1, rounds + 1) for rid in by_id}
    for tp in data.traded_picks:
        key = (int(tp["season"]), int(tp["round"]), int(tp["roster_id"]))
        if key in owner:
            owner[key] = int(tp["owner_id"])

    n = len(teams)
    strength = sorted(teams, key=lambda t: (t.ranks["standings"] + t.ranks["lineup_value"]) / 2)
    # strength[0] is the strongest team, whose pick comes last.
    tier_of = {}
    for i, t in enumerate(strength):
        third = i * 3 // n
        tier_of[t.roster_id] = ("late", "mid", "early")[third]

    for (year, rnd, orig), holder in owner.items():
        tier = tier_of[orig] if year == years[0] else "any"
        by_id[holder].picks.append(Pick(
            year=year,
            round=rnd,
            original_roster_id=orig,
            original_owner=by_id[orig].owner,
            tier=tier,
            value=cons.pick(year, rnd, tier),
        ))
    for t in teams:
        t.picks.sort(key=lambda p: (p.year, p.round, -p.value))
