from datetime import date

import pytest

from advisor import consensus, main, render
from advisor.consensus import _rank_of
from advisor.sources import ktc
from advisor.sources.common import SourceResult, parse_pick
from tests.sample_league import build

TODAY = date(2026, 10, 6)


@pytest.mark.parametrize("name, expected", [
    ("2027 1st (Early)", (2027, 1, "early")),
    ("2027 Mid 1st", (2027, 1, "mid")),
    ("2028 2nd", (2028, 2, "any")),
    ("2027 Round 3", (2027, 3, "any")),
    ("2026 Pick 1.11", (2026, 1, "late")),
    ("George Pickens", None),
])
def test_parse_pick(name, expected):
    assert parse_pick(name) == expected


def test_rank_of():
    curve = [100, 80, 60, 40]
    assert _rank_of(curve, 100) == 0
    assert _rank_of(curve, 120) == 0
    assert _rank_of(curve, 40) == 3
    assert _rank_of(curve, 70) == pytest.approx(1.5)


def _source(name, values, as_of=TODAY):
    s = SourceResult(name, as_of)
    for i, v in enumerate(values):
        s.players[str(i)] = v
        s.curve.append(v)
    return s.finish()


def test_scale_of_a_source_does_not_matter():
    a = _source("A", [100, 50, 20, 10])
    b = _source("B", [9000, 4000, 3000, 100])
    b_big = _source("B", [v * 7 for v in [9000, 4000, 3000, 100]])
    one = consensus.build([a, b], today=TODAY)
    two = consensus.build([a, b_big], today=TODAY)
    for pid in one.players:
        assert one.player(pid) == pytest.approx(two.player(pid))


def test_sources_count_equally():
    a = _source("A", [100, 50, 20, 10])
    b = _source("B", [100, 50, 20, 10])
    b.players["0"], b.players["3"] = b.players["3"], b.players["0"]  # B flips best and worst
    c = consensus.build([a, b], today=TODAY)
    assert c.player("0") == pytest.approx(c.player("3"))


def test_stale_source_is_left_out():
    fresh = _source("Fresh", [100, 50])
    stale = _source("Stale", [100, 50], as_of=date(2026, 9, 1))
    c = consensus.build([fresh, stale], today=TODAY)
    assert [s.name for s in c.used] == ["Fresh"]
    assert c.dropped[0][0] == "Stale"


def test_ktc_reads_json_tag():
    html = ('<script type="application/json" id="ktc-players">[{"playerName": "A", "playerID": 1}]</script>'
            "<script>var playersArray = JSON.parse(document.getElementById('ktc-players').textContent);</script>")
    assert ktc.extract(html) == [{"playerName": "A", "playerID": 1}]


def test_ktc_reads_old_players_array():
    html = '<script>var playersArray = [{"playerName": "A", "playerID": 1}];\nvar x = 1;</script>'
    assert ktc.extract(html) == [{"playerName": "A", "playerID": 1}]


@pytest.fixture(scope="module")
def report():
    return main.analyze(build(), today=TODAY)


def test_all_three_sources_used(report):
    assert len(report["consensus"].used) == 3
    assert not report["consensus"].dropped


def test_finds_my_team(report):
    assert report["me"].owner == "Racsoturtle"


def test_traded_picks_move(report):
    me = report["me"]
    mine = {(p.year, p.round, p.original_roster_id) for p in me.picks}
    assert (2027, 1, 3) in mine  # got team 3's first
    assert (2027, 2, 7) not in mine  # traded own second away
    assert sum(len(t.picks) for t in report["teams"]) == 16 * 3 * 3


def test_allplay_adds_up(report):
    weeks = report["completed_weeks"]
    for t in report["teams"]:
        assert t.allplay_wins + t.allplay_losses <= 15 * weeks
    assert sum(t.allplay_wins for t in report["teams"]) == sum(t.allplay_losses for t in report["teams"])


def test_value_lineup_fills_skill_slots(report):
    for t in report["teams"]:
        assert sum(p.in_value_lineup for p in t.players) <= 8


def test_first_pick_is_worth_more_than_second(report):
    c = report["consensus"]
    assert c.pick(2027, 1, "early") > c.pick(2027, 1, "late") > c.pick(2027, 2, "mid")
    assert c.pick(2029, 1) == c.pick(2028, 1)  # no source prices 2029 yet


def test_site_builds(report, tmp_path):
    render.write_site(report, tmp_path)
    home = (tmp_path / "index.html").read_text()
    assert "Roster by consensus value" in home
    assert (tmp_path / "league.html").exists()


def test_snapshot_round_trip(tmp_path):
    raw = build()
    main.save_snapshot(raw, tmp_path)
    again = main.analyze(main.load_snapshot(tmp_path), today=TODAY)
    first = main.analyze(raw, today=TODAY)
    assert again["me"].total_value == pytest.approx(first["me"].total_value)
    assert again["completed_weeks"] == 4


def test_missing_source_still_builds():
    raw = build()
    raw["ktc"] = None
    raw["errors"] = {"ktc": "HTTPError: 403"}
    rep = main.analyze(raw, today=TODAY)
    assert [n for n, _ in rep["consensus"].dropped] == ["KeepTradeCut"]
    assert len(rep["consensus"].used) == 2


def test_lineup_fills_every_slot_and_skips_out_players(report):
    a = report["advice"]
    assert [s.slot for s in a.slots] == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF"]
    db = report["players_db"]
    assert all(s.pid for s in a.slots)
    assert not any(db[s.pid].get("injury_status") == "Out" for s in a.slots)


def test_lineup_changes_swap_within_eligible_slots(report):
    db = report["players_db"]
    for start, sit, gain in report["advice"].changes:
        assert gain >= 0
        if sit:
            assert db[sit]["position"] in ("RB", "WR", "TE") or db[sit]["position"] == db[start]["position"]


def test_odds_are_probabilities(report):
    o = report["odds"]
    assert sum(o.playoff.values()) == pytest.approx(6)
    assert all(0 <= p <= 1 for p in o.playoff.values())
    assert report["call"][0] in ("Contend", "Hold", "Retool")


def test_stronger_team_has_better_odds(report):
    o = report["odds"]
    best = max(o.weekly_mean, key=o.weekly_mean.get)
    worst = min(o.weekly_mean, key=o.weekly_mean.get)
    assert o.playoff[best] >= o.playoff[worst]


def test_projection_scoring_uses_league_rules():
    from advisor.projections import score
    assert score({"pass_yd": 250, "pass_td": 2, "pass_int": 1, "gp": 1}, {"pass_yd": 0.04, "pass_td": 4, "pass_int": -1}) == pytest.approx(17)


def test_waiver_flags_need_real_gain(report):
    from advisor import config
    for f in report["waivers"]:
        if f.kind == "this week":
            assert f.gain >= config.WAIVER_WEEKLY_GAIN
        else:
            assert f.gain >= config.WAIVER_VALUE_GAIN


def test_summary_mentions_call_and_link(report):
    assert "Playoff odds" in report["summary"]
    assert "racsoturtle.github.io" in report["summary"]


def test_offseason_skips_weekly_parts():
    raw = build()
    raw["sleeper"]["state"]["season_type"] = "off"
    rep = main.analyze(raw, today=TODAY)
    assert rep["week"] is None
    assert not rep["odds"].playoff


def test_trade_ideas_follow_the_rules(report):
    from advisor import config
    ideas = report["trade_ideas"]
    assert ideas
    for i in ideas:
        assert config.TRADE_MIN_EDGE <= i.edge <= config.TRADE_MAX_EDGE
        assert i.their_lineup_change > 0
        assert i.partner.roster_id != report["me"].roster_id
        if report["call"][0] == "Hold":
            assert i.my_points_change >= -config.HOLD_MAX_POINTS_LOSS


def test_package_value_discounts_depth():
    from advisor.trades import Asset, package_value
    star = [Asset("a", "Star", 6000)]
    two = [Asset("b", "Mid", 3000), Asset("c", "Mid", 3000)]
    assert package_value(two) < 6000 == package_value(star)


def test_trade_ideas_by_call_differ(report):
    from advisor import trades
    args = (report["teams"], report["me"])
    rp = report["league"]["roster_positions"]
    pg = report["week_proj"].per_game
    for i in trades.find(*args, "Contend", rp, pg):
        assert i.my_points_change >= 0


def test_checker_data_is_complete(report):
    d = report["checker"]
    assert d["me"] == report["me"].roster_id
    assert len(d["teams"]) == 16
    assert all(t["players"] for t in d["teams"])
    assert sum(len(t["picks"]) for t in d["teams"]) == 16 * 3 * 3


def test_implied_premium_balances_the_trade():
    from advisor.history import implied
    assert implied([(1000, True)], [1300]) == pytest.approx(1.3)
    # A player thrown in with the 1st counts at full value, the 1st carries the rest.
    from advisor import config
    w = config.PACKAGE_WEIGHTS
    m = implied([(3000, False), (2000, True)], [3000 + 0.85 * 2000 * 1.2])
    assert m == pytest.approx(1.2, abs=1e-6) and w[1] == 0.85


def test_only_clean_first_round_sales_measure_the_premium(report):
    from advisor import history
    trades = build()["league_trades"]
    assert [t["transaction_id"] for t in history.measurable(trades)] == ["t1", "t2"]
    three_way = dict(trades[0], roster_ids=[1, 2, 3])
    three_way["adds"] = {"a": 1, "b": 2, "c": 3}
    assert history.seller(three_way) is None


def test_premium_uses_each_source_as_a_vote_and_shrinks(report):
    from advisor import config
    pp = report["pick_premium"]
    t1 = next(t for t in pp.trades if t.seller == "Team 2")
    t2 = next(t for t in pp.trades if t.seller == "Team 4")
    assert len(t1.by_source) == 3
    assert list(t2.by_source) == ["FantasyCalc"]  # KTC was missing a reading
    assert pp.raw == pytest.approx(1.3, abs=0.01)
    # Two trades worth 1 + 1/3 votes, pulled toward 1.0 by the prior.
    assert pp.weight == pytest.approx(4 / 3)
    assert 1.0 < pp.multiplier < pp.raw
    assert config.PREMIUM_RANGE[0] <= pp.multiplier <= config.PREMIUM_RANGE[1]


def test_no_history_means_no_premium():
    raw = build()
    raw["league_trades"] = []
    rep = main.analyze(raw, today=TODAY)
    assert rep["pick_premium"].multiplier == 1.0
    assert all(i.league_edge == pytest.approx(i.edge) for i in rep["trade_ideas"])


def test_trade_ideas_look_fair_at_league_prices(report):
    from advisor import config
    for i in report["trade_ideas"]:
        assert i.edge >= config.TRADE_MIN_EDGE
        assert i.edge <= config.TRADE_MAX_TRUE_EDGE
        assert i.league_edge <= config.TRADE_MAX_EDGE + 1e-9


def test_premium_lets_oscar_ask_more_for_a_first(report):
    from advisor import trades
    me = report["me"]
    rp = report["league"]["roster_positions"]
    pg = report["week_proj"].per_game
    ideas = trades.find(report["teams"], me, "Retool", rp, pg, premium=1.4)
    selling = [i for i in ideas if any(a.first for a in i.give) and not any(a.first for a in i.get)]
    for i in selling:
        assert i.league_edge < i.edge


def test_price_reuses_cache_and_retries_failures(monkeypatch):
    from advisor import history
    raw = build()
    calls = []

    def fc(self, key, day):
        calls.append(("fc", key))
        return 100.0

    def ktc(self, key, day):
        raise ConnectionError("network")

    monkeypatch.setattr(history.Pricer, "fc", fc)
    monkeypatch.setattr(history.Pricer, "ktc", ktc)
    monkeypatch.setattr(history.Pricer, "prime_dp", lambda self, earliest: None)
    cache = {"t1": raw["trade_prices"]["t1"]}
    out = history.price(raw["league_trades"], raw["sleeper"]["players"], raw["fantasycalc"], raw["ktc"],
                        raw["dp_ids"], cache)
    assert out["t1"] == cache["t1"]  # nothing fetched again
    assert "FantasyCalc" in out["t2"]
    assert "KeepTradeCut" not in out["t2"]  # network error: try again tomorrow
    assert all(k in raw["trade_prices"]["t2"]["FantasyCalc"] for _, k in calls)


def test_ktc_slug():
    from advisor.sources.ktc import slug_for
    assert slug_for("De'Von Achane", 1398) == "de-von-achane-1398"
    assert slug_for("Marvin Harrison Jr.", 1585) == "marvin-harrison-jr-1585"


def _day(raw, d, denied=None, log=None):
    raw = dict(raw, denied=denied, trade_log=log)
    return main.analyze(raw, today=d)


def test_trade_log_counts_days_and_revalues():
    from datetime import timedelta
    raw = build()
    one = _day(raw, TODAY)
    ideas = one["trade_ideas"]
    log = one["trade_log"]
    assert set(log["ideas"]) == {i.key for i in ideas}
    assert all(e["days_recommended"] == 1 for e in log["ideas"].values())
    again = _day(raw, TODAY, log=log)  # a second build the same day
    assert all(e["days_recommended"] == 1 for e in again["trade_log"]["ideas"].values())
    nxt = _day(raw, TODAY + timedelta(days=1), log=again["trade_log"])
    e = nxt["trade_log"]["ideas"][ideas[0].key]
    assert e["days_recommended"] == 2 and e["first_seen"] == TODAY.isoformat()
    assert [c[0] for c in e["checks"]] == [TODAY.isoformat(), (TODAY + timedelta(days=1)).isoformat()]
    top = next(r for r in nxt["log_rows"] if r.key == ideas[0].key)
    assert top.status == "recommended" and top.edge == pytest.approx(ideas[0].edge)


def test_denied_offer_is_kept_but_not_suggested():
    raw = build()
    one = _day(raw, TODAY)
    key = one["trade_ideas"][0].key
    two = _day(raw, TODAY, denied={key: "https://github.com/x/issues/5"}, log=one["trade_log"])
    assert key not in {i.key for i in two["trade_ideas"]}
    row = next(r for r in two["log_rows"] if r.key == key)
    assert row.status == "denied" and row.entry["issue"].endswith("/5")
    # GitHub unreachable: the mark in the log still holds.
    three = _day(raw, TODAY, denied=None, log=two["trade_log"])
    assert key not in {i.key for i in three["trade_ideas"]}
    # Issue closed: the offer can come back.
    four = _day(raw, TODAY, denied={}, log=three["trade_log"])
    assert key in {i.key for i in four["trade_ideas"]}


def test_offer_with_a_moved_player_is_marked_gone():
    raw = build()
    one = _day(raw, TODAY)
    log = one["trade_log"]
    old = dict(next(iter(log["ideas"].values())), get=[["nobody", "Long Gone"]])
    log["ideas"]["0000000000"] = old
    two = _day(raw, TODAY, log=log)
    row = next(r for r in two["log_rows"] if r.key == "0000000000")
    assert row.status == "gone" and "Long Gone" in row.note and row.edge is None


def test_deny_link_round_trips_through_issue_title(monkeypatch):
    from urllib.parse import parse_qs, urlparse
    from advisor import github
    url = github.deny_url("abc123def0", "Team 2", ["Puka Nacua"], ["James Cook", "2029 1st"])
    title = parse_qs(urlparse(url).query)["title"][0]
    assert github._KEY.match(title).group(1) == "abc123def0"

    class Resp:
        def json(self):
            return [{"title": title, "user": {"login": "Racsoturtle"}, "html_url": "u1"},
                    {"title": title.replace("abc123def0", "fff123def0"), "user": {"login": "someone"}, "html_url": "u2"},
                    {"title": "Thursday summary", "user": {"login": "Racsoturtle"}, "html_url": "u3"}]

    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr(github.http, "get", lambda *a, **k: Resp())
    assert github.denied_issues() == {"abc123def0": "u1"}


def test_backup_offers_follow_the_top_ideas(report, tmp_path):
    from advisor import config
    offers, ideas = report["trade_offers"], report["trade_ideas"]
    assert offers[:len(ideas)] == ideas and len(ideas) <= config.TRADE_IDEAS
    assert len(offers) <= config.TRADE_IDEAS + config.TRADE_BACKUPS
    render.write_site(report, tmp_path)
    page = (tmp_path / "trades.html").read_text()
    assert page.count('class="btn deny"') == len(offers)
