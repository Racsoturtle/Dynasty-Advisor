"""Playoff odds by simulating the rest of the regular season.

Each team's expected weekly score comes from projections: this week's best
lineup by consensus weekly projection, and later weeks' best lineup by
Sleeper's rest-of-season points per game. Projections are rescaled so the
league average matches what teams have actually scored, then blended with
each team's own scoring so far. Weekly scores vary around that mean by the
spread seen in this league's real weekly scores.
"""

import random
import statistics
from dataclasses import dataclass, field

from . import config, lineup

PROJ_WEIGHT = 0.75  # the rest comes from the team's actual average


@dataclass
class Odds:
    playoff: dict = field(default_factory=dict)  # roster id -> probability
    wins: dict = field(default_factory=dict)  # roster id -> average final wins
    weekly_mean: dict = field(default_factory=dict)  # roster id -> expected points, later weeks
    this_week: dict = field(default_factory=dict)  # roster id -> expected points this week
    sd: float = 0.0
    weeks_left: int = 0


def call(prob, week, trade_deadline):
    if week is None:
        return "Offseason", "The regular season is over, so the call is about next year."
    if trade_deadline and week > trade_deadline:
        return "Past deadline", "The trade deadline has passed. Set the best lineup each week and plan for the offseason."
    if prob >= config.CONTEND_ODDS:
        return "Contend", "Trade picks and young bench players for starters who help this year."
    if prob >= config.RETOOL_ODDS:
        return "Hold", "Only make trades that win on value. Don't spend future assets on this season."
    return "Retool", "Sell older starters for picks and young players while they still have value."


def simulate(data, league_teams, week_proj, current_week, seed=0):
    league = data.league
    roster_positions = league.get("roster_positions", [])
    players_db = data.players
    last = int((league.get("settings") or {}).get("playoff_week_start") or 15) - 1
    playoff_teams = int((league.get("settings") or {}).get("playoff_teams") or 6)
    out = Odds()
    if current_week is None:
        return out

    from .sleeper import schedule
    weeks = list(range(current_week, last + 1))
    sched = schedule(data, weeks)
    out.weeks_left = len(weeks)

    by_id = {t.roster_id: t for t in league_teams}
    rosters = {r["roster_id"]: r for r in data.rosters}

    def lineup_points(roster, points):
        active = [p for p in roster.get("players") or [] if p not in set(roster.get("taxi") or [])]
        healthy = [p for p in active if players_db.get(p, {}).get("injury_status") not in config.OUT_STATUSES]
        positions = {p: players_db.get(p, {}).get("position") for p in healthy}
        return sum(s.points for s in lineup.best_lineup(healthy, roster_positions, positions, points))

    raw_now = {rid: lineup_points(r, week_proj.points) for rid, r in rosters.items()}
    raw_later = {rid: lineup_points(r, lambda p: week_proj.per_game.get(p, 0.0)) for rid, r in rosters.items()}
    if not any(raw_later.values()):
        raw_later = dict(raw_now)

    actual = {rid: t.weekly_points for rid, t in by_id.items()}
    all_scores = [p for pts in actual.values() for p in pts]
    league_avg = statistics.mean(all_scores) if all_scores else None

    def calibrate(raw):
        avg = statistics.mean(raw.values()) or 1.0
        scale = league_avg / avg if league_avg else 1.0
        out_ = {}
        for rid, v in raw.items():
            proj = v * scale
            mine = actual.get(rid) or []
            out_[rid] = PROJ_WEIGHT * proj + (1 - PROJ_WEIGHT) * statistics.mean(mine) if len(mine) >= 2 else proj
        return out_

    out.this_week = calibrate(raw_now)
    out.weekly_mean = calibrate(raw_later)
    residuals = [p - statistics.mean(pts) for pts in actual.values() if len(pts) >= 2 for p in pts]
    out.sd = max(15.0, statistics.pstdev(residuals) if len(residuals) > 4 else 25.0)

    rng = random.Random(seed)
    made = {rid: 0 for rid in by_id}
    total_wins = {rid: 0.0 for rid in by_id}
    for _ in range(config.SIMULATIONS):
        wins = {rid: t.wins + 0.5 * t.ties for rid, t in by_id.items()}
        pf = {rid: t.points_for for rid, t in by_id.items()}
        for week in weeks:
            means = out.this_week if week == current_week else out.weekly_mean
            for a, b in sched.get(week, []):
                sa = rng.gauss(means[a], out.sd)
                sb = rng.gauss(means[b], out.sd)
                pf[a] += sa
                pf[b] += sb
                if sa > sb:
                    wins[a] += 1
                else:
                    wins[b] += 1
        ranked = sorted(by_id, key=lambda rid: (wins[rid], pf[rid]), reverse=True)
        for rid in ranked[:playoff_teams]:
            made[rid] += 1
        for rid in by_id:
            total_wins[rid] += wins[rid]
    out.playoff = {rid: made[rid] / config.SIMULATIONS for rid in by_id}
    out.wins = {rid: total_wins[rid] / config.SIMULATIONS for rid in by_id}
    return out
