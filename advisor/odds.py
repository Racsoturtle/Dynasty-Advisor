"""Playoff odds by simulating the rest of the regular season.

Each team's expected weekly score comes from projections: this week's best
lineup by consensus weekly projection, and later weeks' best lineup by
Sleeper's rest-of-season points per game. Projections are rescaled so the
league average matches what teams have actually scored, then blended with
each team's own scoring so far. Weekly scores vary around that mean by the
spread seen in this league's real weekly scores.

Points already scored in the week being played count as banked: only the
starters who haven't scored yet are projected, and that week's spread shrinks
with the share of the projection still to come.

Playoff spots follow the league's divisions when it has them: each division
sends its best records (wins, then points for) in equal shares. Otherwise the
best records league-wide get in.
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
    banked: dict = field(default_factory=dict)  # roster id -> points already scored this week
    divisions: dict = field(default_factory=dict)  # roster id -> division number, when the league has them


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

    # The week being played: bank what's scored, project only who's left.
    week_sd = {rid: out.sd for rid in by_id}
    live = in_progress(data.matchups.get(current_week, []), week_proj.points)
    if live:
        for rid, (scored, left, total) in live.items():
            if rid not in out.this_week:
                continue
            share = left / total if total else 1.0
            out.this_week[rid] = scored + out.this_week[rid] * share
            week_sd[rid] = out.sd * share ** 0.5
        out.banked = {rid: v[0] for rid, v in live.items()}

    divisions = division_of(data.rosters, league)

    rng = random.Random(seed)
    made = {rid: 0 for rid in by_id}
    total_wins = {rid: 0.0 for rid in by_id}
    for _ in range(config.SIMULATIONS):
        wins = {rid: t.wins + 0.5 * t.ties for rid, t in by_id.items()}
        pf = {rid: t.points_for for rid, t in by_id.items()}
        for week in weeks:
            now = week == current_week
            means = out.this_week if now else out.weekly_mean
            for a, b in sched.get(week, []):
                sa = rng.gauss(means[a], week_sd[a] if now else out.sd)
                sb = rng.gauss(means[b], week_sd[b] if now else out.sd)
                pf[a] += sa
                pf[b] += sb
                if sa > sb:
                    wins[a] += 1
                else:
                    wins[b] += 1
        for rid in qualifiers(by_id, wins, pf, playoff_teams, divisions):
            made[rid] += 1
        for rid in by_id:
            total_wins[rid] += wins[rid]
    out.divisions = divisions
    out.playoff = {rid: made[rid] / config.SIMULATIONS for rid in by_id}
    out.wins = {rid: total_wins[rid] / config.SIMULATIONS for rid in by_id}
    return out


def division_of(rosters, league):
    """roster id -> division, or {} when the league doesn't split into divisions."""
    count = int((league.get("settings") or {}).get("divisions") or 0)
    if count < 2:
        return {}
    out = {r["roster_id"]: (r.get("settings") or {}).get("division") for r in rosters}
    return out if all(out.values()) and len(set(out.values())) > 1 else {}


def qualifiers(teams, wins, pf, playoff_teams, divisions):
    """The roster ids that make the playoffs: the best records (wins, then
    points for) in each division in equal shares, or league-wide without
    divisions."""
    def best(ids, n):
        return sorted(ids, key=lambda rid: (wins[rid], pf[rid]), reverse=True)[:n]

    if not divisions:
        return best(teams, playoff_teams)
    groups = {}
    for rid in teams:
        groups.setdefault(divisions[rid], []).append(rid)
    share, extra = divmod(playoff_teams, len(groups))
    out = [rid for ids in groups.values() for rid in best(ids, share)]
    # Spots that don't split evenly go to the best remaining records.
    return out + best([rid for rid in teams if rid not in out], extra)


def in_progress(rows, projected):
    """For a week underway: roster id -> (points scored, projected points still
    to come, projected points in all) for its set starters. A starter who
    hasn't scored yet is taken as not having played. None until anyone scores."""
    if not any((m.get("points") or 0) > 0 for m in rows):
        return None
    out = {}
    for m in rows:
        pts = m.get("players_points") or {}
        starters = [p for p in m.get("starters") or [] if p and p != "0"]
        waiting = [p for p in starters if not pts.get(p)]
        total = sum(projected(p) for p in starters)
        left = sum(projected(p) for p in waiting)
        if not total:  # no projections: go by how many starters are still to play
            total, left = len(starters) or 1, len(waiting) if starters else 1
        out[m["roster_id"]] = (m.get("points") or 0.0, left, total)
    return out
