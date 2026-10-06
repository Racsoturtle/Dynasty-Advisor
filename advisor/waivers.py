"""Free agents worth adding. Waivers in this league are thin, so a player is
only flagged when they clearly beat what Oscar already has."""

from dataclasses import dataclass

from . import config, lineup

SKILL = ("QB", "RB", "WR", "TE")


@dataclass
class Flag:
    pid: str
    kind: str  # "this week" or "dynasty"
    reason: str
    gain: float
    drop: str | None  # suggested player to drop


def free_agents(data):
    rostered = {p for r in data.rosters for p in (r.get("players") or [])}
    return [pid for pid, p in data.players.items()
            if pid not in rostered and p.get("team") and p.get("position") in lineup.FIXED
            and p.get("injury_status") not in config.OUT_STATUSES]


def find(data, my_roster, my_team, advice, week_proj, cons):
    db = data.players
    fas = free_agents(data)
    drop = _drop_candidate(my_team, advice)
    flags = []

    # This week: a free agent who would start over someone in the best lineup.
    for s in advice.slots:
        best = None
        for pid in fas:
            pos = db[pid].get("position")
            if not lineup.eligible(s.slot, pos):
                continue
            gain = week_proj.points(pid) - s.points
            if gain >= config.WAIVER_WEEKLY_GAIN and (not best or gain > best[1]):
                best = (pid, gain)
        if best and best[0] not in {f.pid for f in flags}:
            pid, gain = best
            who = db.get(s.pid, {}).get("full_name", "your current option") if s.pid else "an empty slot"
            # Kickers and defenses are swapped for each other, not for a bench player.
            same_slot_drop = s.pid if s.slot in ("K", "DEF") else drop
            flags.append(Flag(pid, "this week", f"projects {gain:.1f} more points than {who} at {s.slot}",
                              gain, same_slot_drop))

    # Dynasty: a free agent the consensus values above your least valuable
    # bench player. Only the best few, since each claim costs the same spot.
    if drop:
        floor = cons.player(drop)
        dynasty = []
        for pid in fas:
            if db[pid].get("position") not in SKILL or pid in {f.pid for f in flags}:
                continue
            gain = cons.player(pid) - floor
            if gain >= config.WAIVER_VALUE_GAIN:
                dynasty.append(Flag(pid, "dynasty", f"consensus value {cons.player(pid):,.0f} against {floor:,.0f}", gain, drop))
        flags += sorted(dynasty, key=lambda f: -f.gain)[:config.WAIVER_DYNASTY_MAX]
    return flags


def _drop_candidate(my_team, advice):
    """Least valuable bench player who isn't in this week's best lineup."""
    starting = {s.pid for s in advice.slots}
    bench = [p for p in my_team.players
             if p.status == "bench" and p.pid not in starting and p.pos in SKILL]
    return min(bench, key=lambda p: p.value).pid if bench else None
