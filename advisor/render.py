"""Writes the static dashboard site."""

import shutil
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config
from jinja2 import Environment, PackageLoader, select_autoescape

PAGES = (
    ("index.html", "Home"),
    ("lineup.html", "Lineup"),
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


def _env():
    env = Environment(loader=PackageLoader("advisor", "templates"), autoescape=select_autoescape())
    env.filters["ordinal"] = ordinal
    env.filters["num"] = num
    env.globals["SHORT_SOURCE"] = SHORT_SOURCE
    env.globals["PAGES"] = PAGES
    return env


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

    ctx = dict(report, pick_years=config.PICK_YEARS_AHEAD, updated=local.strftime("%a %b %-d, %-I:%M %p ET"),
               sources=[s.name for s in report["consensus"].used], player=player, cfg=config)
    for filename, title in PAGES:
        html = env.get_template(filename).render(ctx, page=filename, title=title)
        (out / filename).write_text(html)
    (out / ".nojekyll").write_text("")
