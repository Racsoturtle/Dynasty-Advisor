"""Writes the static dashboard site."""

import json
import shutil
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config
from jinja2 import Environment, PackageLoader, select_autoescape

PAGES = (
    ("index.html", "Home"),
    ("lineup.html", "Lineup"),
    ("trades.html", "Trades"),
    ("checker.html", "Trade checker"),
    ("log.html", "Trade log"),
    ("waivers.html", "Waivers"),
    ("league.html", "League"),
)

SHORT_SOURCE = {
    "FantasyCalc": "FC",
    "KeepTradeCut": "KTC",
    "FantasyPros (via DynastyProcess)": "FP",
}


def ordinal(n):
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def num(x, digits=0):
    if x is None:
        return ""
    return f"{x:,.{digits}f}"


def day(iso):
    return date.fromisoformat(iso).strftime("%b %-d") if iso else ""


def pct(x):
    return "" if x is None else f"{'+' if x >= 0 else ''}{x * 100:.1f}%"


def _env():
    env = Environment(loader=PackageLoader("advisor", "templates"), autoescape=select_autoescape())
    env.filters["ordinal"] = ordinal
    env.filters["num"] = num
    env.filters["day"] = day
    env.filters["pct"] = pct
    env.globals["SHORT_SOURCE"] = SHORT_SOURCE
    env.globals["PAGES"] = PAGES
    return env


def live_data(report):
    """What the Refresh button needs to make sense of a fresh Sleeper pull:
    names, values and weekly points for every player who could be rostered."""
    db, cons = report.get("players_db") or {}, report["consensus"]
    per_game = report["week_proj"].per_game if report.get("week_proj") else {}
    rostered = {p.pid for t in report["teams"] for p in t.players}
    players = {}
    for pid, p in db.items():
        if pid in rostered or (p.get("team") and p.get("position") in ("QB", "RB", "WR", "TE", "K", "DEF")):
            players[pid] = [p.get("full_name") or f"{p.get('team')} {p.get('position')}", p.get("position"),
                            p.get("team") or "FA", round(cons.player(pid)), round(per_game.get(pid, 0.0), 2),
                            p.get("age")]
    return {
        "fetched_at": int(report["fetched_at"].timestamp() * 1000),
        "league_id": report["league"].get("league_id"),
        "me": report["me"].roster_id,
        "players": players,
    }


def write_site(report, out_dir):
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    env = _env()
    local = report["generated"].astimezone(ZoneInfo("America/New_York"))
    db = report.get("players_db") or {}

    def player(pid):
        p = db.get(pid) or {}
        return {"name": p.get("full_name") or pid or "Empty", "pos": p.get("position") or "",
                "team": p.get("team") or "FA", "injury": p.get("injury_status")}

    ctx = dict(report, fetched_ms=int(report["fetched_at"].timestamp() * 1000), pick_years=config.PICK_YEARS_AHEAD, updated=local.strftime("%a %b %-d, %-I:%M %p ET"),
               sources=[s.name for s in report["consensus"].used], player=player, cfg=config,
               log_by_key={r.key: r for r in report.get("log_rows") or []})
    for filename, title in PAGES:
        html = env.get_template(filename).render(ctx, page=filename, title=title)
        (out / filename).write_text(html)
    (out / "checker.json").write_text(json.dumps(report["checker"]))
    (out / "live.json").write_text(json.dumps(live_data(report)))
    # Tomorrow's run reuses these readings instead of re-pricing old trades.
    (out / "trade_prices.json").write_text(json.dumps(report.get("trade_prices") or {}))
    (out / ".nojekyll").write_text("")
