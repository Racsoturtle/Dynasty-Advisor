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


def test_ktc_reads_players_array():
    html = '<script>var playersArray = [{"playerName": "A", "playerID": 1}];\nvar x = 1;</script>'
    assert ktc._ARRAY.search(html).group(1) == '[{"playerName": "A", "playerID": 1}]'


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
