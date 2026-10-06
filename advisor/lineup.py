"""Best weekly lineup by consensus projection, close calls and warnings."""

from dataclasses import dataclass, field

from . import config
from .teams import FLEX_ELIGIBLE

FIXED = ("QB", "RB", "WR", "TE", "K", "DEF")


@dataclass
class Slot:
    slot: str
    pid: str | None
    points: float


@dataclass
class Advice:
    slots: list = field(default_factory=list)  # best lineup, in league slot order
    bench: list = field(default_factory=list)  # (pid, points) not in the best lineup
    changes: list = field(default_factory=list)  # (start pid, sit pid, gain)
    close_calls: list = field(default_factory=list)  # (starter pid, bench pid, gap, sources_disagree)
    warnings: list = field(default_factory=list)  # (pid, reason) for current Sleeper starters
    projected: float = 0.0
    current_projected: float = 0.0


def eligible(slot, pos):
    return pos == slot or pos in FLEX_ELIGIBLE.get(slot, ())


def best_lineup(pids, roster_positions, positions, points):
    """Fill fixed slots with the top players at each position, then flex
    slots with the best of what's left. Optimal for these slot types."""
    slots = [s for s in roster_positions if s in FIXED or s in FLEX_ELIGIBLE]
    pool = sorted(pids, key=lambda p: -points(p))
    used, filled = set(), {}
    order = [i for i, s in enumerate(slots) if s in FIXED] + [i for i, s in enumerate(slots) if s not in FIXED]
    for i in order:
        pick = next((p for p in pool if p not in used and eligible(slots[i], positions.get(p))), None)
        if pick:
            used.add(pick)
        filled[i] = Slot(slots[i], pick, points(pick) if pick else 0.0)
    return [filled[i] for i in range(len(slots))]


def advise(roster, players_db, week_proj, roster_positions):
    active = [p for p in roster.get("players") or [] if p not in set(roster.get("taxi") or []) | set(roster.get("reserve") or [])]
    positions = {p: players_db.get(p, {}).get("position") for p in active}
    pts = week_proj.points
    out = Advice()
    out.slots = best_lineup(active, roster_positions, positions, pts)
    starting = {s.pid for s in out.slots if s.pid}
    out.bench = sorted(((p, pts(p)) for p in active if p not in starting), key=lambda x: -x[1])
    out.projected = sum(s.points for s in out.slots)

    slot_names = [s.slot for s in out.slots]
    current_slots = [(slot, p) for slot, p in zip(_starter_slots(roster_positions), roster.get("starters") or [])
                     if slot in slot_names]
    current = [p for _, p in current_slots if p and p != "0"]
    out.current_projected = sum(pts(p) for p in current)
    out.changes = _pair_changes(out.slots, current_slots, positions, pts)

    for s in out.slots:
        if not s.pid:
            continue
        for b, b_pts in out.bench:
            if not eligible(s.slot, positions.get(b)):
                continue
            gap = s.points - b_pts
            disagree = _order_flips(week_proj, s.pid, b)
            if gap <= config.CLOSE_CALL_POINTS or disagree:
                out.close_calls.append((s.pid, b, gap, disagree))
    out.close_calls.sort(key=lambda c: c[2])
    out.close_calls = _dedupe(out.close_calls)[:6]

    for p in current:
        info = players_db.get(p, {})
        status = info.get("injury_status")
        if info.get("team") and info.get("team") not in week_proj.teams_playing and week_proj.teams_playing:
            out.warnings.append((p, "on bye"))
        elif status in config.OUT_STATUSES:
            out.warnings.append((p, status))
        elif status in ("Doubtful", "Questionable"):
            out.warnings.append((p, status))
    return out


def _order_flips(week_proj, a, b):
    pa, pb = week_proj.players.get(a), week_proj.players.get(b)
    if not pa or not pb:
        return False
    common = [s for s in pa.by_source if s in pb.by_source]
    if len(common) < 2:
        return False
    signs = {pa.by_source[s] > pb.by_source[s] for s in common}
    return len(signs) > 1


def _dedupe(calls):
    """Each bench player once, and at most two alternatives per starter."""
    seen, per_starter, out = set(), {}, []
    for c in calls:
        if c[1] in seen or per_starter.get(c[0], 0) >= 2:
            continue
        seen.add(c[1])
        per_starter[c[0]] = per_starter.get(c[0], 0) + 1
        out.append(c)
    return out


def _starter_slots(roster_positions):
    """Sleeper lists a roster's starters in the order of its starting slots."""
    return [s for s in roster_positions if s not in ("BN", "IR", "TAXI")]


def _pair_changes(best_slots, current_slots, positions, pts):
    """Moves from the current Sleeper lineup to the best one, each as
    (start, sit, gain). A player to start replaces someone whose current slot
    the player can fill, preferring the same position."""
    best = {s.pid for s in best_slots if s.pid}
    current = {p for _, p in current_slots}
    to_start = sorted((p for p in best if p not in current), key=lambda p: -pts(p))
    open_slots = [(slot, p) for slot, p in current_slots if p == "0" or not p or p not in best]
    changes = []
    for p in to_start:
        pos = positions.get(p)
        fits = [o for o in open_slots if eligible(o[0], pos)]
        if not fits:
            continue
        same = [o for o in fits if o[1] and o[1] != "0" and positions.get(o[1]) == pos]
        slot, sit = (same or fits)[0]
        open_slots.remove((slot, sit))
        sit = sit if sit and sit != "0" else None
        changes.append((p, sit, pts(p) - (pts(sit) if sit else 0.0)))
    return changes
