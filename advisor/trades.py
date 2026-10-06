"""Trade ideas to propose, and the shared math the trade checker uses.

Every number here is consensus value. A deal is a candidate when:
  - Oscar comes out ahead by TRADE_MIN_EDGE to TRADE_MAX_EDGE after package
    and roster-spot adjustments (slightly in Oscar's favor, per the plan),
  - the partner's starting lineup gets better, so the offer fixes a real need,
  - it fits the contend / hold / retool call.
"""

from dataclasses import dataclass, field
from itertools import combinations

from . import config, teams as teams_mod


@dataclass(frozen=True)
class Asset:
    key: str  # sleeper player id, or "pick:2027:1:3"
    label: str
    value: float
    pos: str | None = None  # None for picks
    age: float | None = None
    roster_spot: bool = True  # picks don't take a roster spot


@dataclass
class Idea:
    partner: object
    give: tuple
    get: tuple
    give_value: float
    get_value: float
    edge: float
    my_lineup_change: float
    my_points_change: float
    their_lineup_change: float
    reason: str
    score: float = 0.0
    tags: list = field(default_factory=list)


def package_value(assets):
    vals = sorted((a.value for a in assets), reverse=True)
    weights = config.PACKAGE_WEIGHTS
    return sum(v * weights[min(i, len(weights) - 1)] for i, v in enumerate(vals))


def assets_for(team, min_value=config.TRADE_MIN_ASSET):
    out = [Asset(p.pid, p.name, p.value, p.pos, p.age) for p in team.players
           if p.pos in teams_mod.POSITIONS and p.value >= min_value]
    for pk in team.picks:
        if pk.value >= min_value:
            nth = {1: "1st", 2: "2nd", 3: "3rd"}.get(pk.round, f"{pk.round}th")
            tier = "" if pk.tier == "any" else f" ({pk.tier})"
            out.append(Asset(f"pick:{pk.year}:{pk.round}:{pk.original_roster_id}",
                             f"{pk.original_owner}'s {pk.year} {nth}{tier}", pk.value, None, None, False))
    out.sort(key=lambda a: -a.value)
    return out


class TeamState:
    """A team's roster for what-if math: value lineup, drops, ages."""

    def __init__(self, team, roster_positions, roster_size, per_game=None):
        self.team = team
        self.roster_positions = roster_positions
        self.roster_size = roster_size
        self.per_game = per_game or {}
        self.active = [p for p in team.players if p.status not in ("taxi", "ir")]
        self.base_lineup = self.lineup_value(self.active)
        self.base_points = self.lineup_points(self.active)

    def lineup_value(self, players):
        return sum(p.value for p in teams_mod.value_lineup(players, self.roster_positions))

    def lineup_points(self, players):
        if not self.per_game:
            return 0.0
        scored = [_Pts(p, self.per_game.get(p.pid, 0.0)) for p in players]
        return sum(p.value for p in teams_mod.value_lineup(scored, self.roster_positions))

    def after(self, out_keys, incoming):
        """Active roster after a trade, cutting the least valuable bench
        players when the roster would be over its limit."""
        kept = [p for p in self.active if p.pid not in out_keys]
        added = [teams_mod.RosterPlayer(a.key, a.label, a.pos, "", a.age, "bench", a.value, {}, False)
                 for a in incoming if a.roster_spot]
        players = kept + added
        # A roster already over the limit (IR returns, Sleeper quirks) only
        # cuts for the extra spots this trade adds.
        over = len(players) - max(self.roster_size, len(self.active))
        cut = []
        if over > 0:
            lineup = {p.pid for p in teams_mod.value_lineup(players, self.roster_positions)}
            # Kickers and defenses fill their own slots and are never the cut.
            bench = sorted((p for p in players if p.pid not in lineup and p.pos in teams_mod.POSITIONS),
                           key=lambda p: p.value)
            cut = bench[:over]
            players = [p for p in players if p not in cut]
        return players, cut


class _Pts:
    """A player stand-in whose 'value' is rest-of-season points per game."""

    def __init__(self, p, pts):
        self.pid, self.pos, self.status, self.value = p.pid, p.pos, p.status, pts


def evaluate(me, them, give, get):
    """Oscar gives `give` to `them` and gets `get`. Returns the numbers the
    finder and the checker both use."""
    give_keys = {a.key for a in give}
    get_keys = {a.key for a in get}
    my_after, my_cut = me.after(give_keys, get)
    their_after, their_cut = them.after(get_keys, give)
    give_value = package_value(give) + sum(p.value for p in my_cut)
    get_value = package_value(get) + sum(p.value for p in their_cut)
    return {
        "give_value": give_value,
        "get_value": get_value,
        "edge": (get_value - give_value) / give_value if give_value else 0.0,
        "my_lineup_change": me.lineup_value(my_after) - me.base_lineup,
        "my_points_change": me.lineup_points(my_after) - me.base_points,
        "their_lineup_change": them.lineup_value(their_after) - them.base_lineup,
        "my_cut": my_cut,
        "their_cut": their_cut,
    }


def _avg_age(assets):
    aged = [a for a in assets if a.age]
    w = sum(a.value for a in aged)
    return sum(a.age * a.value for a in aged) / w if w else None


def fits_direction(call, give, get, numbers):
    """Contend: weekly points can't drop. Retool: get younger or get picks.
    Hold: don't give up more than HOLD_MAX_POINTS_LOSS a week, and only
    spend picks on young players."""
    if call == "Contend":
        return numbers["my_points_change"] >= 0
    if call == "Retool":
        get_picks = sum(a.value for a in get if a.pos is None)
        younger = (_avg_age(get) or 99) < (_avg_age(give) or 0)
        return younger or get_picks >= 0.25 * sum(a.value for a in get)
    if call == "Hold":
        if numbers["my_points_change"] < -config.HOLD_MAX_POINTS_LOSS:
            return False
        if any(a.pos is None for a in give):
            return (_avg_age(get) or 99) <= config.HOLD_PICKS_FOR_AGE
    return True


def find(league_teams, me_team, call, roster_positions, per_game=None):
    roster_size = sum(1 for s in roster_positions if s not in ("IR", "TAXI"))
    me = TeamState(me_team, roster_positions, roster_size, per_game)
    mine = assets_for(me_team)[: config.TRADE_POOL]
    ideas = []
    for partner in league_teams:
        if partner.roster_id == me_team.roster_id:
            continue
        them = TeamState(partner, roster_positions, roster_size, per_game)
        theirs = assets_for(partner)[: config.TRADE_POOL]
        found = []
        for n_give, n_get in ((1, 1), (2, 1), (1, 2), (2, 2)):
            for give in combinations(mine, n_give):
                gv = package_value(give)
                for get in combinations(theirs, n_get):
                    # Cheap pre-check before the roster math.
                    raw_edge = (package_value(get) - gv) / gv
                    if not -0.05 <= raw_edge <= config.TRADE_MAX_EDGE + 0.05:
                        continue
                    nums = evaluate(me, them, give, get)
                    if not config.TRADE_MIN_EDGE <= nums["edge"] <= config.TRADE_MAX_EDGE:
                        continue
                    if nums["their_lineup_change"] <= 0:
                        continue
                    if not fits_direction(call, give, get, nums):
                        continue
                    found.append(_idea(partner, give, get, nums, call))
        found.sort(key=lambda i: -i.score)
        ideas += _distinct(found)[: config.TRADE_IDEAS_PER_PARTNER]
    ideas.sort(key=lambda i: -i.score)
    return _spread(ideas)[: config.TRADE_IDEAS]


def _spread(ideas):
    """Across partners: the same package of Oscar's once, and each of
    Oscar's assets in at most two ideas, so the list offers real choices."""
    used_packages, uses, out = set(), {}, []
    for i in ideas:
        package = frozenset(a.key for a in i.give)
        if package in used_packages or any(uses.get(a.key, 0) >= 2 for a in i.give):
            continue
        used_packages.add(package)
        for a in i.give:
            uses[a.key] = uses.get(a.key, 0) + 1
        out.append(i)
    return out


def _idea(partner, give, get, nums, call):
    idea = Idea(partner, give, get, nums["give_value"], nums["get_value"], nums["edge"],
                nums["my_lineup_change"], nums["my_points_change"], nums["their_lineup_change"], "")
    gained = sorted({a.pos for a in give if a.pos and a.pos in partner.needs})
    if gained:
        idea.reason = f"Fills their {' and '.join(gained)} need; their starting lineup value rises {nums['their_lineup_change']:,.0f}."
    else:
        idea.reason = f"Their starting lineup value rises {nums['their_lineup_change']:,.0f}."
    if any(a.pos is None for a in give):
        idea.tags.append("uses your picks")
    if nums["my_cut"]:
        idea.tags.append("you cut " + ", ".join(p.name for p in nums["my_cut"]))
    gain = nums["get_value"] - nums["give_value"]
    weight = 1.0 if call == "Contend" else 0.5
    # Favor deals that help the partner (likelier to be accepted) and that
    # keep or raise Oscar's weekly points. 100 value ~ 1 point a week.
    idea.score = gain + 0.25 * nums["their_lineup_change"] + weight * 100 * nums["my_points_change"]
    return idea


def _distinct(ideas):
    """Don't show the same player going to one partner twice."""
    seen, out = set(), []
    for i in ideas:
        keys = {a.key for a in i.give} | {a.key for a in i.get}
        if keys & seen:
            continue
        seen |= keys
        out.append(i)
    return out


def checker_data(league_teams, me_team, call, roster_positions, per_game):
    """Everything the in-browser trade checker needs, as plain JSON."""
    roster_size = sum(1 for s in roster_positions if s not in ("IR", "TAXI"))
    out_teams = []
    for t in league_teams:
        players = [{"id": p.pid, "name": p.name, "pos": p.pos, "age": p.age, "value": round(p.value),
                    "status": p.status, "ppg": round(per_game.get(p.pid, 0.0), 2)} for p in t.players]
        picks = [{"id": a.key, "name": a.label, "value": round(a.value)} for a in assets_for(t, 0) if a.pos is None]
        out_teams.append({"id": t.roster_id, "name": t.team_name, "owner": t.owner, "needs": t.needs,
                          "players": players, "picks": picks})
    return {
        "me": me_team.roster_id,
        "call": call,
        "teams": out_teams,
        "roster_positions": roster_positions,
        "roster_size": roster_size,
        "flex": teams_mod.FLEX_ELIGIBLE,
        "positions": list(teams_mod.POSITIONS),
        "package_weights": list(config.PACKAGE_WEIGHTS),
        "min_edge": config.TRADE_MIN_EDGE,
        "max_edge": config.TRADE_MAX_EDGE,
        "hold_max_points_loss": config.HOLD_MAX_POINTS_LOSS,
        "hold_picks_for_age": config.HOLD_PICKS_FOR_AGE,
    }
