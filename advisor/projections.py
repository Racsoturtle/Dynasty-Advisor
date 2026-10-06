"""Weekly and rest-of-season projections, scored with this league's rules.

Two sources this week: Sleeper's projections (raw stat lines, which this
scores with the league's own scoring settings) and FantasyPros weekly expert
rankings. FantasyPros publishes ranks, not points, so each rank is turned into
points by reading Sleeper's projection for the player at that same position
rank. The consensus is the plain average of the two.
"""

import json
import re
from dataclasses import dataclass, field

from . import config, http

SLEEPER = "https://api.sleeper.app/projections/nfl"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
FP_PAGES = {"QB": "qb", "RB": "ppr-rb", "WR": "ppr-wr", "TE": "ppr-te", "K": "k", "DEF": "dst"}
FP_TEAM_ALIASES = {"JAC": "JAX", "WSH": "WAS", "LA": "LAR"}
_ECR = re.compile(r"var\s+ecrData\s*=\s*(\{.*?\});", re.DOTALL)

SLEEPER_NAME = "Sleeper"
FP_NAME = "FantasyPros"


def _pos_params():
    return [("season_type", "regular")] + [("position[]", p) for p in POSITIONS]


def fetch_sleeper_week(season, week):
    return http.get_json(f"{SLEEPER}/{season}/{week}", params=_pos_params())


def fetch_sleeper_season(season):
    return http.get_json(f"{SLEEPER}/{season}", params=_pos_params())


def fetch_fp_week():
    pages = {}
    for pos, page in FP_PAGES.items():
        html = http.get_text(f"https://www.fantasypros.com/nfl/rankings/{page}.php")
        m = _ECR.search(html)
        if not m:
            raise ValueError(f"no ecrData on the FantasyPros {page} page")
        pages[pos] = json.loads(m.group(1))
    return pages


def score(stats, scoring):
    return sum(v * scoring[k] for k, v in (stats or {}).items() if k in scoring and isinstance(v, (int, float)))


@dataclass
class Proj:
    points: float
    by_source: dict
    opponent: str | None = None


@dataclass
class Week:
    week: int | None
    players: dict = field(default_factory=dict)  # sleeper id -> Proj
    teams_playing: set = field(default_factory=set)
    sources: list = field(default_factory=list)  # (name, status) rows for the page
    per_game: dict = field(default_factory=dict)  # sleeper id -> rest-of-season points per game

    def points(self, pid):
        p = self.players.get(pid)
        return p.points if p else 0.0


def build(week, sleeper_rows, sleeper_season_rows, fp_pages, scoring, players_db, names, fp_ids):
    out = Week(week)
    by_source = {}

    if sleeper_rows:
        for r in sleeper_rows:
            pid = r.get("player_id")
            if not pid or not r.get("opponent"):
                continue
            out.teams_playing.add(r.get("team"))
            by_source.setdefault(pid, {})[SLEEPER_NAME] = score(r.get("stats"), scoring)
            out.players.setdefault(pid, Proj(0, {}, r.get("opponent")))
        out.sources.append((SLEEPER_NAME, f"{len(by_source)} players"))
    else:
        out.sources.append((SLEEPER_NAME, "unavailable"))

    if fp_pages:
        curves = _sleeper_curves(by_source, players_db)
        matched = 0
        for pos, page in fp_pages.items():
            if page.get("ranking_type_name") != "weekly" or str(page.get("week")) != str(week):
                out.sources.append((f"{FP_NAME} {pos}", f"skipped: page shows {page.get('ranking_type_name')} week {page.get('week')}"))
                continue
            ranked = sorted(page.get("players", []), key=lambda p: float(p.get("rank_ecr") or 999))
            curve = curves.get(pos, [])
            for i, p in enumerate(ranked):
                pid = _fp_to_sleeper(p, pos, names, fp_ids)
                if not pid:
                    continue
                if i < len(curve):
                    pts = curve[i]
                elif p.get("r2p_pts"):
                    pts = float(p["r2p_pts"])
                else:
                    continue
                by_source.setdefault(pid, {})[FP_NAME] = pts
                matched += 1
                if pid not in out.players:
                    team = p.get("player_team_id")
                    out.players[pid] = Proj(0, {}, p.get("player_opponent_id"))
                    out.teams_playing.add(FP_TEAM_ALIASES.get(team, team))
        out.sources.append((FP_NAME, f"{matched} players ranked"))
    else:
        out.sources.append((FP_NAME, "unavailable"))

    for pid, vals in by_source.items():
        info = players_db.get(pid, {})
        proj = out.players.setdefault(pid, Proj(0, {}))
        proj.by_source = vals
        proj.points = sum(vals.values()) / len(vals)
        if info.get("injury_status") in config.OUT_STATUSES:
            proj.points = 0.0

    for r in sleeper_season_rows or []:
        pid = r.get("player_id")
        stats = r.get("stats") or {}
        gp = stats.get("gp") or 0
        if pid and gp:
            out.per_game[pid] = score(stats, scoring) / gp
    return out


def _sleeper_curves(by_source, players_db):
    curves = {}
    for pid, vals in by_source.items():
        if SLEEPER_NAME in vals:
            pos = players_db.get(pid, {}).get("position")
            curves.setdefault(pos, []).append(vals[SLEEPER_NAME])
    for c in curves.values():
        c.sort(reverse=True)
    return curves


def _fp_to_sleeper(p, pos, names, fp_ids):
    if pos == "DEF":
        team = p.get("player_team_id")
        return FP_TEAM_ALIASES.get(team, team)
    return fp_ids.get(str(p.get("player_id"))) or names.find(p.get("player_name", ""), pos)
