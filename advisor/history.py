"""What this league actually pays for 1st-round picks.

Oscar's read is that leaguemates overpay for 1sts. This checks it against the
league's own trades: for every two-team trade where one side sold 1st-round
picks, each value source prices both sides on the trade date, and we solve for
the multiplier on the 1sts that makes the two sides equal. Each source is one
vote, as in the consensus. The multipliers are averaged across trades and
pulled toward 1.0 (no premium) because a few trades make a noisy measurement.
"""

import math
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from . import config, http
from .sources import dynastyprocess, fantasycalc, ktc
from .sources.common import NameIndex, parse_pick

FC, KTC, FP = "FantasyCalc", "KeepTradeCut", "FantasyPros (via DynastyProcess)"
SOURCES = (FC, KTC, FP)


def trade_date(t):
    ms = t.get("status_updated") or t.get("created") or 0
    return datetime.fromtimestamp(ms / 1000, timezone.utc).date()


def sides(t):
    """roster id -> {"gives": [asset keys], "gets": [asset keys]}. Players are
    Sleeper ids; picks are "pick:<season>:<round>:<original roster id>"."""
    out = {str(r): {"gives": [], "gets": []} for r in t.get("roster_ids") or []}
    for pid, rid in (t.get("drops") or {}).items():
        out.setdefault(str(rid), {"gives": [], "gets": []})["gives"].append(pid)
    for pid, rid in (t.get("adds") or {}).items():
        out.setdefault(str(rid), {"gives": [], "gets": []})["gets"].append(pid)
    for p in t.get("draft_picks") or []:
        key = f"pick:{p['season']}:{p['round']}:{p['roster_id']}"
        out.setdefault(str(p["previous_owner_id"]), {"gives": [], "gets": []})["gives"].append(key)
        out.setdefault(str(p["owner_id"]), {"gives": [], "gets": []})["gets"].append(key)
    return out


def is_first(key):
    return key.startswith("pick:") and key.split(":")[2] == "1"


def seller(t):
    """The roster that sold 1sts, when this trade can measure the premium:
    two teams, and only one of them gave up 1st-round picks."""
    s = sides(t)
    if len(s) != 2:
        return None
    selling = [rid for rid, side in s.items() if any(is_first(k) for k in side["gives"])]
    return selling[0] if len(selling) == 1 and s[selling[0]]["gets"] else None


def measurable(trades):
    return [t for t in trades if seller(t)]


def _pick_parts(key):
    _, year, rnd, _ = key.split(":")
    return int(year), int(rnd)


def _on(history, day):
    """A source's value on a day: its latest reading on or before it."""
    days = [d for d in history if d <= day]
    return history[max(days)] if days else None


class Pricer:
    """Prices assets on a past date with each source's own history.
    A value of None means the source has no reading for that asset then."""

    def __init__(self, players_db, fc_rows, ktc_rows, dp_ids):
        self.db = players_db
        self.names = NameIndex(players_db)
        self.fp_ids, ktc_to_sleeper = dynastyprocess.id_maps(dp_ids or [])
        self.sleeper_to_ktc = {s: k for k, s in ktc_to_sleeper.items()}
        self.fc_players, self.fc_picks = fantasycalc.history_ids(fc_rows or [])
        self.ktc_slugs, self.ktc_picks = {}, {}
        for r in ktc_rows or []:
            if not r.get("slug"):
                continue
            if r.get("position") in ("RDP", "PICK"):
                key = parse_pick(r["playerName"])
                if key:
                    self.ktc_picks[key] = r["slug"]
            else:
                self.ktc_slugs[str(r.get("playerID"))] = r["slug"]
        self._hist = {}
        self._dp_versions = None
        self._dp_at = {}

    def _history(self, source, ident, fetch):
        """Cached per run. None when the page doesn't exist."""
        if (source, ident) not in self._hist:
            try:
                self._hist[(source, ident)] = fetch(ident)
            except (http.NotFound, ValueError):  # no such page, or no history on it
                self._hist[(source, ident)] = None
        return self._hist[(source, ident)]

    def fc(self, key, day):
        if key.startswith("pick:"):
            year, rnd = _pick_parts(key)
            fc_id = self.fc_picks.get((year, rnd, "mid")) or self.fc_picks.get((year, rnd, "any"))
            if not fc_id:
                return None
        else:
            fc_id = self.fc_players.get(key)
            if not fc_id:
                return 0.0  # not on FantasyCalc's list at all
        hist = self._history(FC, fc_id, fantasycalc.fetch_history)
        return _on(hist, day) if hist else None

    def ktc(self, key, day):
        if key.startswith("pick:"):
            slug = self.ktc_picks.get(_pick_parts(key) + ("mid",))
            if not slug:
                return None
        else:
            ktc_id = self.sleeper_to_ktc.get(key)
            if not ktc_id:
                return 0.0  # KTC doesn't list this player
            name = (self.db.get(key) or {}).get("full_name") or ""
            slug = self.ktc_slugs.get(ktc_id) or ktc.slug_for(name, ktc_id)
        hist = self._history(KTC, slug, ktc.fetch_history)
        return _on(hist, day) if hist else None

    def fp(self, key, day):
        result = self._dp_on(day)
        if result is None:
            return None
        if key.startswith("pick:"):
            year, rnd = _pick_parts(key)
            return result.picks.get((year, rnd, "mid"))
        return result.players.get(key, 0.0)

    def _dp_on(self, day):
        if self._dp_versions is None:
            self._dp_versions = dynastyprocess.fetch_versions(since=day - timedelta(days=60))
        older = [(d, sha) for d, sha in self._dp_versions if d <= day]
        if not older:
            return None
        sha = max(older)[1]
        if sha not in self._dp_at:
            rows = dynastyprocess.fetch_values_at(sha)
            self._dp_at[sha] = dynastyprocess.parse(rows, self.names, self.fp_ids)
        return self._dp_at[sha]

    def prime_dp(self, earliest):
        """Fetch the version list once, reaching back to the oldest trade."""
        self._dp_versions = dynastyprocess.fetch_versions(since=earliest - timedelta(days=60))


def price(trades, players_db, fc_rows, ktc_rows, dp_ids, cache=None):
    """{transaction id: {source: {asset key: value or None}}} for every trade
    that can measure the premium. Past trades never change, so readings in
    `cache` (yesterday's output) are reused. A source that fails on the
    network is left out today and tried again tomorrow."""
    cache = cache or {}
    todo = measurable(trades)
    pricer = Pricer(players_db, fc_rows, ktc_rows, dp_ids)
    out = {}
    need_dp = [t for t in todo if FP not in (cache.get(t["transaction_id"]) or {})]
    if need_dp:
        try:
            pricer.prime_dp(min(trade_date(t) for t in need_dp))
        except Exception:
            traceback.print_exc()
    lookups = {FC: pricer.fc, KTC: pricer.ktc, FP: pricer.fp}
    for t in todo:
        tid, day = t["transaction_id"], trade_date(t)
        keys = [k for side in sides(t).values() for k in side["gives"]]
        out[tid] = dict(cache.get(tid) or {})
        for source in SOURCES:
            if source in out[tid]:
                continue
            if source == FP and pricer._dp_versions is None:
                continue
            try:
                out[tid][source] = {k: lookups[source](k, day) for k in keys}
            except Exception:
                traceback.print_exc()
    return out


def previous_prices():
    """Yesterday's readings from the live site, so old trades aren't re-priced."""
    try:
        return http.get_json(config.SITE_URL + "trade_prices.json")
    except Exception:
        return {}


@dataclass
class TradeRead:
    when: date
    seller: str
    buyer: str
    gave: list
    got: list
    by_source: dict  # source -> implied multiplier on the 1sts
    multiplier: float | None


@dataclass
class Premium:
    multiplier: float = 1.0
    raw: float | None = None  # before pulling toward 1.0
    trades: list = field(default_factory=list)
    weight: float = 0.0  # trades counted, each weighted by its share of sources

    @property
    def counted(self):
        return [t for t in self.trades if t.multiplier is not None]


def _package(values):
    w = config.PACKAGE_WEIGHTS
    return sum(v * w[min(i, len(w) - 1)] for i, v in enumerate(sorted(values, reverse=True)))


def implied(gave, got):
    """gave: [(value, is_first)] from the seller; got: [values]. The multiplier
    m on the seller's 1sts that makes package(gave) == package(got)."""
    target = _package(got)
    if not any(v > 0 and f for v, f in gave) or target <= 0:
        return None
    f = lambda m: _package([v * m if first else v for v, first in gave]) - target  # noqa: E731
    lo, hi = 0.2, 5.0
    if f(lo) >= 0:
        return lo
    if f(hi) <= 0:
        return hi
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    return (lo + hi) / 2


def _label(key, db):
    if key.startswith("pick:"):
        year, rnd = _pick_parts(key)
        return f"{year} {'1st' if rnd == 1 else '2nd' if rnd == 2 else '3rd' if rnd == 3 else f'{rnd}th'}"
    return (db.get(key) or {}).get("full_name") or key


def measure(trades, prices, players_db):
    out = Premium()
    logs, weights = [], []
    for t in measurable(trades):
        sell = seller(t)
        s = sides(t)
        buy = next(r for r in s if r != sell)
        readings = (prices or {}).get(t["transaction_id"]) or {}
        by_source = {}
        for source in SOURCES:
            vals = readings.get(source)
            if not vals:
                continue
            keys_gave, keys_got = s[sell]["gives"], s[sell]["gets"]
            if any(vals.get(k) is None for k in keys_gave + keys_got):
                continue
            m = implied([(vals[k], is_first(k)) for k in keys_gave], [vals[k] for k in keys_got])
            if m is not None:
                by_source[source] = m
        mult = math.exp(sum(math.log(m) for m in by_source.values()) / len(by_source)) if by_source else None
        teams = t.get("teams") or {}
        out.trades.append(TradeRead(trade_date(t), teams.get(sell, f"Team {sell}"), teams.get(buy, f"Team {buy}"),
                                    [_label(k, players_db) for k in s[sell]["gives"]],
                                    [_label(k, players_db) for k in s[sell]["gets"]], by_source, mult))
        if mult is not None:
            # One wild trade shouldn't swing the price: cap each at 3x either way.
            logs.append(max(-math.log(3), min(math.log(3), math.log(mult))))
            weights.append(len(by_source) / len(SOURCES))
    out.trades.sort(key=lambda r: r.when, reverse=True)
    if weights:
        w = sum(weights)
        mean = sum(l * x for l, x in zip(logs, weights)) / w
        out.raw = math.exp(mean)
        out.weight = w
        lo, hi = config.PREMIUM_RANGE
        out.multiplier = min(hi, max(lo, math.exp(mean * w / (w + config.PREMIUM_PRIOR_TRADES))))
    return out
