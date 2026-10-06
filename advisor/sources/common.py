import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

TIERS = ("early", "mid", "late")


@dataclass
class SourceResult:
    """One value source, read and matched to Sleeper ids.

    `curve` holds every player value the source publishes, matched or not,
    sorted high to low. Ranks are taken against it, so a player the tool
    couldn't match still pushes the players below them down a spot.
    """

    name: str
    as_of: date
    players: dict = field(default_factory=dict)  # sleeper id -> raw value
    picks: dict = field(default_factory=dict)  # (year, round, tier) -> raw value
    curve: list = field(default_factory=list)
    unmatched: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)  # sleeper id -> source-specific fields

    def finish(self):
        self.curve.sort(reverse=True)
        fill_pick_tiers(self.picks)
        return self


_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def norm_name(name):
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^a-z ]", "", name.lower().replace("-", " "))
    name = _SUFFIX.sub("", name)
    return " ".join(name.split())


class NameIndex:
    """Finds a Sleeper player id from a name and position."""

    def __init__(self, sleeper_players):
        self._by_key = {}
        for pid, p in sleeper_players.items():
            name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}"
            pos = p.get("position")
            if not name.strip() or not pos:
                continue
            key = (norm_name(name), pos)
            # Prefer a player currently on a team when two share a name.
            if key not in self._by_key or (p.get("team") and not sleeper_players[self._by_key[key]].get("team")):
                self._by_key[key] = pid

    def find(self, name, pos):
        return self._by_key.get((norm_name(name), pos))


_PICK = re.compile(
    r"(?P<year>20\d\d)\s+"
    r"(?:(?P<tier>early|mid|late)\s+)?"
    r"(?:round\s*(?P<round_a>\d)|(?P<round_b>\d)(?:st|nd|rd|th)|pick\s+(?P<round_c>\d)\.(?P<slot>\d+))"
    r"(?:\s*\((?P<tier_after>early|mid|late)\))?",
    re.IGNORECASE,
)


def parse_pick(name, teams_in_source=12):
    """'2027 Mid 1st' and '2027 1st (Mid)' -> (2027, 1, 'mid'); '2027 1st' -> (2027, 1, 'any');
    '2027 Pick 1.05' -> (2027, 1, 'mid'). None when it isn't a pick."""
    m = _PICK.search(name)
    if not m:
        return None
    rnd = int(m["round_a"] or m["round_b"] or m["round_c"])
    if m["slot"]:
        third = (int(m["slot"]) - 1) * 3 // teams_in_source
        tier = TIERS[min(third, 2)]
    else:
        tier = (m["tier"] or m["tier_after"] or "any").lower()
    return int(m["year"]), rnd, tier


def add_pick(picks, key, value):
    """Exact slots ('1.05') collapse into tiers, so average them."""
    picks.setdefault(key, []).append(value)


def fill_pick_tiers(picks):
    """Average collected values, then make sure every (year, round) has all
    four tiers: a missing generic value is the tier average, and missing
    tiers fall back to the generic value."""
    for key, vals in list(picks.items()):
        if isinstance(vals, list):
            picks[key] = sum(vals) / len(vals)
    for year, rnd in {(y, r) for y, r, _ in picks}:
        tiers = [picks[(year, rnd, t)] for t in TIERS if (year, rnd, t) in picks]
        if (year, rnd, "any") not in picks:
            picks[(year, rnd, "any")] = sum(tiers) / len(tiers)
        for t in TIERS:
            picks.setdefault((year, rnd, t), picks[(year, rnd, "any")])
