"""Turns several value sources into one consensus value per player and pick.

Sources use different scales (KTC tops out near 9,999, FantasyCalc above
11,000) and different curve shapes. To keep any one source from counting for
more, each source is reduced to ranks, and every rank is read off one shared
reference curve: the average of all sources' curves, each scaled to a top
value of 10,000. A player's consensus value is the plain average of their
per-source values.
"""

from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date

from . import config

SCALE = 10_000


@dataclass
class Value:
    consensus: float
    by_source: dict  # source name -> value on the shared curve
    disagree: bool = False


@dataclass
class Consensus:
    players: dict = field(default_factory=dict)  # sleeper id -> Value
    picks: dict = field(default_factory=dict)  # (year, round, tier) -> Value
    used: list = field(default_factory=list)  # SourceResults in the average
    dropped: list = field(default_factory=list)  # (SourceResult or name, reason)

    def player(self, pid):
        v = self.players.get(pid)
        return v.consensus if v else 0.0

    def pick(self, year, rnd, tier="any"):
        v = self.picks.get((year, rnd, tier))
        if v:
            return v.consensus
        # Years beyond what sources publish take the furthest year they do.
        years = sorted({y for y, r, _ in self.picks if r == rnd and y < year})
        return self.picks[(years[-1], rnd, tier)].consensus if years else 0.0


def reference_curve(sources):
    scaled = [[v * SCALE / s.curve[0] for v in s.curve] for s in sources if s.curve]
    length = max(len(c) for c in scaled)
    ref = []
    for i in range(length):
        at = [c[i] for c in scaled if i < len(c)]
        ref.append(sum(at) / len(at))
    return ref


def _read_curve(ref, rank):
    """Value at a 0-based, possibly fractional rank."""
    if rank <= 0:
        return ref[0]
    if rank >= len(ref) - 1:
        return ref[-1]
    lo = int(rank)
    frac = rank - lo
    return ref[lo] * (1 - frac) + ref[lo + 1] * frac


def _rank_of(curve_desc, raw):
    """Fractional 0-based rank a raw value would hold in a high-to-low curve."""
    asc = curve_desc[::-1]
    n = len(asc)
    i = bisect_left(asc, raw)  # values below raw
    if i >= n:
        return 0.0
    if i == 0:
        return float(n - 1)
    lo, hi = asc[i - 1], asc[i]
    frac = (raw - lo) / (hi - lo) if hi != lo else 0.0
    return (n - i) - frac


def _disagree(values):
    if len(values) < 2:
        return False
    spread = max(values) - min(values)
    mean = sum(values) / len(values)
    return spread > max(config.DISAGREE_MIN, config.DISAGREE_SHARE * mean)


def build(results, failures=(), today=None):
    today = today or date.today()
    out = Consensus(dropped=[(name, reason) for name, reason in failures])
    for s in results:
        age = (today - s.as_of).days
        if age > config.STALE_DAYS:
            out.dropped.append((s.name, f"data is {age} days old"))
        elif not s.curve:
            out.dropped.append((s.name, "returned no players"))
        else:
            out.used.append(s)
    if not out.used:
        raise RuntimeError("no usable value sources")

    ref = reference_curve(out.used)

    per_player = {}
    for s in out.used:
        for pid, raw in s.players.items():
            per_player.setdefault(pid, {})[s.name] = _read_curve(ref, _rank_of(s.curve, raw))
    for pid, vals in per_player.items():
        out.players[pid] = _value(vals)

    per_pick = {}
    for s in out.used:
        for key, raw in s.picks.items():
            per_pick.setdefault(key, {})[s.name] = _read_curve(ref, _rank_of(s.curve, raw))
    for key, vals in per_pick.items():
        out.picks[key] = _value(vals)
    return out


def _value(vals):
    nums = list(vals.values())
    return Value(sum(nums) / len(nums), vals, _disagree(nums))

