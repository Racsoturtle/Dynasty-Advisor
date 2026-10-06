"""The short pre-game summary posted Thursday and Sunday mornings."""

from . import config

SITE = config.SITE_URL


def build(r):
    me, db = r["me"], r["players_db"]
    week = r["week"]
    name = lambda pid: db.get(pid, {}).get("full_name") or pid  # noqa: E731
    lines = []
    if week is None:
        return f"No games this week. [Dashboard]({SITE})"
    odds = r["odds"].playoff.get(me.roster_id)
    label, _ = r["call"]
    if odds is not None:
        lines.append(f"**Week {week}: {label}.** Playoff odds {odds:.0%}, projected {r['odds'].wins[me.roster_id]:.1f} wins.")

    advice = r["advice"]
    if advice.changes:
        moves = "; ".join(
            f"start {name(s)} over {name(o)} (+{g:.1f})" if o else f"start {name(s)} in an empty slot"
            for s, o, g in advice.changes)
        lines.append(f"**Lineup:** {moves}.")
    else:
        lines.append(f"**Lineup:** set. Projected {advice.projected:.1f} points.")
    if advice.warnings:
        lines.append("**Watch:** " + "; ".join(f"{name(p)} ({why})" for p, why in advice.warnings) + ".")
    if advice.close_calls:
        s, b, gap, _ = advice.close_calls[0]
        lines.append(f"**Closest call:** {name(s)} over {name(b)} by {gap:.1f}.")
    weekly = [f for f in r["waivers"] if f.kind == "this week"]
    if weekly:
        f = weekly[0]
        drop = f" (drop {name(f.drop)})" if f.drop else ""
        lines.append(f"**Waivers:** add {name(f.pid)}{drop}, who {f.reason}.")
    ideas = r.get("trade_ideas") or []
    if ideas:
        i = ideas[0]
        give = " + ".join(a.label for a in i.give)
        get = " + ".join(a.label for a in i.get)
        lines.append(f"**Best trade idea:** to {i.partner.team_name}, {give} for {get} (+{i.edge:.0%} value).")
    lines.append(f"[Open the dashboard]({SITE})")
    return "\n\n".join(lines)
