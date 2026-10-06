"""Daily run: pull the league and the value sources, build the site.

    python -m advisor.main                 # live data, writes ./site
    python -m advisor.main --snapshot DIR  # also save every raw download to DIR
    python -m advisor.main --offline DIR   # build from a saved snapshot
"""

import argparse
import csv
import json
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

from . import config, consensus, lineup, odds, projections, render, sleeper, summary, teams, waivers
from .sources import dynastyprocess, fantasycalc, ktc
from .sources.common import NameIndex


def collect_live():
    league = sleeper.fetch(config.LEAGUE_ID)
    raw = {"sleeper": league.__dict__}
    season = league.league["season"]
    week = sleeper.current_week(league.league, league.state)
    fetchers = [
        ("fantasycalc", fantasycalc.fetch),
        ("ktc", ktc.fetch),
        ("dp_values", dynastyprocess.fetch_values),
        ("dp_ids", dynastyprocess.fetch_ids),
    ]
    if week:
        fetchers += [
            ("sleeper_week_proj", lambda: projections.fetch_sleeper_week(season, week)),
            ("sleeper_season_proj", lambda: projections.fetch_sleeper_season(season)),
            ("fp_week", projections.fetch_fp_week),
        ]
    for name, fn in fetchers:
        try:
            raw[name] = fn()
        except Exception as exc:  # one broken source must not stop the run
            traceback.print_exc()
            raw[name] = None
            raw.setdefault("errors", {})[name] = f"{type(exc).__name__}: {exc}"
    return raw


def save_snapshot(raw, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, payload in raw.items():
        if name in ("dp_values", "dp_ids") and payload:
            with open(folder / f"{name}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(payload[0].keys()))
                w.writeheader()
                w.writerows(payload)
        else:
            (folder / f"{name}.json").write_text(json.dumps(payload))


def load_snapshot(folder):
    folder = Path(folder)
    raw = {}
    for path in folder.iterdir():
        if path.suffix == ".csv":
            with open(path, newline="") as f:
                raw[path.stem] = list(csv.DictReader(f))
        elif path.suffix == ".json":
            raw[path.stem] = json.loads(path.read_text())
    return raw


def analyze(raw, today=None):
    today = today or date.today()
    data = sleeper.League(**raw["sleeper"])
    data.matchups = {int(k): v for k, v in (data.matchups or {}).items()}
    names = NameIndex(data.players)
    errors = dict(raw.get("errors") or {})

    fp_ids, ktc_ids = ({}, {})
    if raw.get("dp_ids"):
        fp_ids, ktc_ids = dynastyprocess.id_maps(raw["dp_ids"])

    results, failures = [], []
    parsers = (
        ("FantasyCalc", "fantasycalc", lambda p: fantasycalc.parse(p, names, today)),
        ("KeepTradeCut", "ktc", lambda p: ktc.parse(p, names, ktc_ids, today)),
        ("FantasyPros (via DynastyProcess)", "dp_values", lambda p: dynastyprocess.parse(p, names, fp_ids)),
    )
    for label, key, parse in parsers:
        if raw.get(key) is None:
            failures.append((label, errors.get(key, "download failed")))
            continue
        try:
            results.append(parse(raw[key]))
        except Exception as exc:
            traceback.print_exc()
            failures.append((label, f"couldn't read it: {exc}"))

    cons = consensus.build(results, failures, today)
    league_teams = teams.build(data, cons)
    me = _find_me(data, league_teams)

    week = sleeper.current_week(data.league, data.state)
    week_proj = projections.build(
        week, raw.get("sleeper_week_proj"), raw.get("sleeper_season_proj"), raw.get("fp_week"),
        data.league.get("scoring_settings") or {}, data.players, names, fp_ids)
    for key, label in (("sleeper_week_proj", "Sleeper"), ("fp_week", "FantasyPros")):
        if key in errors:
            week_proj.sources = [(n, st) if n != label else (n, f"unavailable: {errors[key]}") for n, st in week_proj.sources]
    my_roster = next(r for r in data.rosters if r["roster_id"] == me.roster_id)
    advice = lineup.advise(my_roster, data.players, week_proj, data.league.get("roster_positions", []))
    league_odds = odds.simulate(data, league_teams, week_proj, week, seed=int(today.strftime("%Y%m%d")))
    deadline = int((data.league.get("settings") or {}).get("trade_deadline") or 0)
    my_odds = league_odds.playoff.get(me.roster_id, 0.0)
    report = {
        "league": data.league,
        "state": data.state,
        "teams": league_teams,
        "me": me,
        "consensus": cons,
        "completed_weeks": sleeper.completed_weeks(data.league, data.state),
        "generated": datetime.now(timezone.utc),
        "week": week,
        "week_proj": week_proj,
        "players_db": data.players,
        "advice": advice,
        "odds": league_odds,
        "call": odds.call(my_odds, week, deadline),
        "waivers": waivers.find(data, my_roster, me, advice, week_proj, cons),
    }
    report["summary"] = summary.build(report)
    return report


def _find_me(data, league_teams):
    user = next((u for u in data.users if (u.get("display_name") or "").lower() == config.MY_USERNAME.lower()), None)
    if not user:
        raise RuntimeError(f"{config.MY_USERNAME} isn't in this league")
    return next(t for t in league_teams if t.owner_id == user["user_id"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    ap.add_argument("--offline")
    ap.add_argument("--snapshot")
    args = ap.parse_args()

    raw = load_snapshot(args.offline) if args.offline else collect_live()
    if args.snapshot:
        save_snapshot(raw, args.snapshot)
    report = analyze(raw)
    render.write_site(report, args.out)
    Path(args.out, "summary.md").write_text(report["summary"])
    used = ", ".join(s.name for s in report["consensus"].used)
    print(f"Built {args.out} for {report['me'].team_name}; sources used: {used}")
    for name, reason in report["consensus"].dropped:
        print(f"  left out {name}: {reason}")


if __name__ == "__main__":
    main()
