"""Files the in-browser Refresh button needs to rerun the analysis.

The Refresh button loads Python in the browser (Pyodide), unpacks this
package from engine/app.zip, pulls fresh rosters, matchups and picks from
Sleeper, and reruns `main.analyze` on this morning's downloads of everything
else (values, projections, trade history). It keeps this morning's trade
offers rather than searching again. engine/raw.json is that morning data,
trimmed to the fields the analysis reads.
"""

import json
import zipfile
from pathlib import Path

from . import history

PKG = Path(__file__).parent
SKILL_POS = ("QB", "RB", "WR", "TE", "K", "DEF")
PLAYER_FIELDS = ("full_name", "first_name", "last_name", "position", "team", "age", "injury_status")


def write(raw, report, out_dir):
    engine = Path(out_dir) / "engine"
    engine.mkdir(parents=True, exist_ok=True)
    (engine / "raw.json").write_text(json.dumps(slim(raw, report), separators=(",", ":")))
    with zipfile.ZipFile(engine / "app.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(PKG.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                z.write(path, Path("advisor") / path.relative_to(PKG))
    (engine / "refresh.js").write_text((PKG / "static" / "refresh.js").read_text())


def slim(raw, report):
    s = raw["sleeper"]
    scoring = set((s["league"].get("scoring_settings") or {})) | {"gp"}
    keep = {p.pid for t in report["teams"] for p in t.players}
    for t in raw.get("league_trades") or []:
        keep |= set((t.get("adds") or {})) | set((t.get("drops") or {}))
    players = {pid: {k: p[k] for k in PLAYER_FIELDS if p.get(k) is not None}
               for pid, p in s["players"].items()
               if pid in keep or (p.get("team") and p.get("position") in SKILL_POS)}

    def proj_rows(rows):
        return [{"player_id": r.get("player_id"), "team": r.get("team"), "opponent": r.get("opponent"),
                 "stats": {k: v for k, v in (r.get("stats") or {}).items() if k in scoring}}
                for r in rows or [] if r.get("player_id")]

    fp = None
    if raw.get("fp_week"):
        fp = {pos: {"ranking_type_name": page.get("ranking_type_name"), "week": page.get("week"),
                    "players": [{k: p.get(k) for k in ("player_id", "player_name", "player_team_id",
                                                       "player_opponent_id", "rank_ecr", "r2p_pts")}
                                for p in page.get("players") or []]}
              for pos, page in raw["fp_week"].items()}
    out = {
        "sleeper": {**s, "players": players},
        "fetched_at": raw.get("fetched_at"),
        "fantasycalc": [{"player": {k: r["player"].get(k) for k in ("id", "name", "sleeperId", "position")},
                         "value": r.get("value"), "redraftValue": r.get("redraftValue"), "trend30Day": r.get("trend30Day")}
                        for r in raw.get("fantasycalc") or []] if raw.get("fantasycalc") is not None else None,
        "ktc": [{"playerName": r.get("playerName"), "playerID": r.get("playerID"), "position": r.get("position"),
                 "oneQBValues": {"value": (r.get("oneQBValues") or {}).get("value")}}
                for r in raw.get("ktc") or []] if raw.get("ktc") is not None else None,
        "dp_values": raw.get("dp_values"),
        "dp_ids": [{k: r.get(k) for k in ("sleeper_id", "fantasypros_id", "ktc_id")}
                   for r in raw.get("dp_ids") or [] if r.get("sleeper_id") not in (None, "", "NA")]
        if raw.get("dp_ids") is not None else None,
        "sleeper_week_proj": proj_rows(raw.get("sleeper_week_proj")) if raw.get("sleeper_week_proj") is not None else None,
        "sleeper_season_proj": proj_rows(raw.get("sleeper_season_proj")) if raw.get("sleeper_season_proj") is not None else None,
        "fp_week": fp,
        "league_trades": [t for t in raw.get("league_trades") or [] if history.seller(t)],
        "trade_prices": raw.get("trade_prices") or {},
        "trade_log": report.get("trade_log"),
        "denied": raw.get("denied"),
        "errors": raw.get("errors") or {},
        "fixed_offers": [{"partner": i.partner.roster_id, "give": [a.key for a in i.give], "get": [a.key for a in i.get]}
                         for i in report["trade_offers"]],
    }
    return out
