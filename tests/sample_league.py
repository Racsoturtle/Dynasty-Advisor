"""Builds a realistic offline snapshot for tests.

DynastyProcess files are real downloads (tests/fixtures/*_real.csv). The
Sleeper league, FantasyCalc and KeepTradeCut payloads are generated from them
in each service's documented shape, with seeded noise so the sources disagree
the way real ones do.
"""

import csv
import random
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"
SEASON = "2026"
ME = "1133612972255117312"


def _csv(name):
    with open(FIX / name, newline="") as f:
        return list(csv.DictReader(f))


def _starters(pids, players):
    """A plausible Sleeper lineup in slot order: QB, RB, RB, WR, WR, TE, FLEX, FLEX."""
    pos = lambda p: players[p]["position"]  # noqa: E731
    out, used = [], set()
    for slot in ("QB", "RB", "RB", "WR", "WR", "TE"):
        p = next((p for p in pids if p not in used and pos(p) == slot), "0")
        used.add(p)
        out.append(p)
    for _ in range(2):
        p = next((p for p in pids if p not in used and pos(p) in ("RB", "WR", "TE")), "0")
        used.add(p)
        out.append(p)
    return out


def build(weeks_played=4, seed=7):
    rng = random.Random(seed)
    dp_values = _csv("dp_values_real.csv")
    dp_ids = _csv("dp_ids_real.csv")
    fp_to_row = {r["fantasypros_id"]: r for r in dp_ids}

    players = {}
    ranked = []
    for v in dp_values:
        if v["pos"] == "PICK" or v["fp_id"] not in fp_to_row:
            continue
        idr = fp_to_row[v["fp_id"]]
        sid = idr["sleeper_id"]
        first, _, last = v["player"].partition(" ")
        players[sid] = {
            "player_id": sid, "full_name": v["player"], "first_name": first, "last_name": last,
            "position": v["pos"], "team": v["team"] if v["team"] != "NA" else None,
            "age": int(float(v["age"])) if v["age"] != "NA" else None,
            "injury_status": rng.choice([None] * 12 + ["Questionable", "Out"]),
        }
        ranked.append((float(v["value_1qb"]), sid, v, idr))
    ranked.sort(reverse=True)

    nfl = sorted({v["team"] for v in dp_values if v["team"] not in ("NA", "FA", "")})[:32]
    for team in nfl:
        players[team] = {"player_id": team, "full_name": f"{team} Defense", "position": "DEF", "team": team}
        kid = f"K{team}"
        players[kid] = {"player_id": kid, "full_name": f"{team} Kicker", "position": "K", "team": team}

    # Snake-draft the top 16 * 22 players onto 16 rosters.
    rosters = [{"roster_id": i + 1, "players": [], "starters": [], "taxi": [], "reserve": []} for i in range(16)]
    pool = [sid for _, sid, _, _ in ranked[: 16 * 22]]
    for rnd in range(22):
        order = range(16) if rnd % 2 == 0 else range(15, -1, -1)
        for i in order:
            rosters[i]["players"].append(pool.pop(rng.randrange(min(len(pool), 6))))
    owners = [ME if i == 6 else str(1000 + i) for i in range(16)]
    users = []
    for i, r in enumerate(rosters):
        r["owner_id"] = owners[i]
        r["taxi"] = r["players"][-3:]
        r["reserve"] = r["players"][-4:-3]
        r["players"] += [nfl[i], f"K{nfl[i]}"]
        r["starters"] = _starters(r["players"], players) + [f"K{nfl[i]}", nfl[i]]
        users.append({"user_id": owners[i], "display_name": "Racsoturtle" if owners[i] == ME else f"Manager{i + 1}",
                      "metadata": {"team_name": f"Team {i + 1}"} if i % 3 else {}})

    matchups = {}
    for week in range(1, 15):
        ids = list(range(1, 17))
        rng.shuffle(ids)
        rows = []
        for m in range(8):
            for rid in ids[2 * m: 2 * m + 2]:
                pts = round(rng.uniform(85, 150), 2) if week <= weeks_played else 0.0
                rows.append({"roster_id": rid, "matchup_id": m + 1, "points": pts})
        matchups[week] = rows
    for r in rosters:
        r["settings"] = {"wins": 0, "losses": 0, "ties": 0, "fpts": 0, "fpts_decimal": 0,
                         "fpts_against": 0, "fpts_against_decimal": 0}
    by_id = {r["roster_id"]: r for r in rosters}
    pf = {rid: 0.0 for rid in by_id}
    pa = {rid: 0.0 for rid in by_id}
    for week, rows in matchups.items():
        if week > weeks_played:
            continue
        rows = sorted(rows, key=lambda r: r["matchup_id"])
        for a, b in zip(rows[::2], rows[1::2]):
            pf[a["roster_id"]] += a["points"]; pa[a["roster_id"]] += b["points"]
            pf[b["roster_id"]] += b["points"]; pa[b["roster_id"]] += a["points"]
            win, lose = (a, b) if a["points"] > b["points"] else (b, a)
            by_id[win["roster_id"]]["settings"]["wins"] += 1
            by_id[lose["roster_id"]]["settings"]["losses"] += 1
    for rid, r in by_id.items():
        r["settings"]["fpts"], r["settings"]["fpts_decimal"] = int(pf[rid]), round(pf[rid] % 1 * 100)
        r["settings"]["fpts_against"], r["settings"]["fpts_against_decimal"] = int(pa[rid]), round(pa[rid] % 1 * 100)

    league = {
        "league_id": "1327317900188487680", "name": "Skulls Super Dynasty League", "season": SEASON,
        "status": "in_season", "total_rosters": 16,
        "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF"] + ["BN"] * 8,
        "settings": {"draft_rounds": 3, "taxi_slots": 5, "reserve_slots": 2, "trade_deadline": 11,
                     "playoff_week_start": 15, "playoff_teams": 6},
        "scoring_settings": {"pass_yd": 0.04, "pass_td": 4.0, "pass_int": -1.0, "rush_yd": 0.1, "rush_td": 6.0,
                             "rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0, "fum_lost": -2.0, "xpm": 1.0, "fgm": 3.0,
                             "sack": 1.0, "int": 2.0, "fum_rec": 2.0, "pts_allow_14_20": 1.0},
    }
    traded = [
        {"season": "2027", "round": 1, "roster_id": 3, "previous_owner_id": 3, "owner_id": 7},
        {"season": "2027", "round": 2, "roster_id": 7, "previous_owner_id": 7, "owner_id": 12},
    ]

    fc = []
    for value, sid, v, idr in ranked:
        noisy = round(value * 1.1 * rng.uniform(0.8, 1.2))
        fc.append({"player": {"id": int(sid) if sid.isdigit() else 0, "name": v["player"], "sleeperId": sid,
                              "position": v["pos"], "maybeTeam": v["team"]},
                   "value": noisy, "redraftValue": round(noisy * rng.uniform(0.5, 1.2)), "trend30Day": 0})
    for name, value in (("2027 1st (Early)", 5200), ("2027 1st (Mid)", 4100), ("2027 1st (Late)", 3300),
                        ("2027 2nd (Mid)", 1500), ("2028 1st", 3900), ("2028 2nd", 1400)):
        fc.append({"player": {"id": 0, "name": name, "position": "PICK"}, "value": value})
    fc.sort(key=lambda r: -r["value"])

    ktc = []
    for value, sid, v, idr in ranked[:500]:
        if idr["ktc_id"] in ("", "NA"):
            continue
        ktc.append({"playerName": v["player"], "playerID": int(idr["ktc_id"]), "position": v["pos"],
                    "oneQBValues": {"value": min(9999, round(value * rng.uniform(0.85, 1.15)))}})
    # One player KTC lists under a different id and a name with a suffix.
    ktc.append({"playerName": "Made Up Rookie Jr.", "playerID": 999999, "position": "WR",
                "oneQBValues": {"value": 2500}})
    for name, value in (("2027 Early 1st", 6000), ("2027 Mid 1st", 4800), ("2027 Late 1st", 3900),
                        ("2027 Mid 2nd", 2100), ("2028 Mid 1st", 4500)):
        ktc.append({"playerName": name, "playerID": 0, "position": "RDP", "oneQBValues": {"value": value}})

    week = weeks_played + 1
    bye = set(nfl[:2])
    week_rows, season_rows = [], []
    fp_pages = {pos: {"ranking_type_name": "weekly", "week": str(week), "players": []}
                for pos in ("QB", "RB", "WR", "TE", "K", "DEF")}
    for value, sid, v, idr in ranked[:400]:
        team = players[sid]["team"]
        base = 4 + value / 600
        rec = base / 3 * rng.uniform(0.7, 1.3)
        stats = {"rec": rec, "rec_yd": base * 4, "rush_yd": base * 2, "gp": 1.0} if v["pos"] != "QB" else \
                {"pass_yd": 180 + value / 40, "pass_td": 1.5, "pass_int": 0.6, "rush_yd": 15, "gp": 1.0}
        if team not in bye:
            week_rows.append({"player_id": sid, "team": team, "opponent": "OPP", "stats": stats})
            fp_pages[v["pos"]]["players"].append(
                {"player_id": int(idr["fantasypros_id"]), "player_name": v["player"], "player_team_id": team,
                 "rank_ecr": value * rng.uniform(0.8, 1.2)})
        season_rows.append({"player_id": sid, "stats": {k: x * 17 if k != "gp" else 17.0 for k, x in stats.items()}})
    for i, team in enumerate(nfl):
        if team in bye:
            continue
        week_rows.append({"player_id": team, "team": team, "opponent": "OPP", "stats": {"sack": 2 + i % 4, "int": 1.0}})
        week_rows.append({"player_id": f"K{team}", "team": team, "opponent": "OPP", "stats": {"fgm": 1.5 + (i % 5) / 4, "xpm": 2.5}})
        fp_pages["DEF"]["players"].append({"player_id": 9000 + i, "player_name": f"{team} D", "player_team_id": team, "rank_ecr": 50 - i})
    for page in fp_pages.values():
        page["players"].sort(key=lambda p: -p["rank_ecr"])
        for i, p in enumerate(page["players"]):
            p["rank_ecr"] = i + 1

    # Past league trades, and each source's readings on the trade dates. In two
    # of them the 1st seller got about 30% more than the 1st was worth.
    p = [r["players"][0] for r in rosters]
    names = {str(i + 1): f"Team {i + 1}" for i in range(16)}

    def trade(tid, ms, rosters_in, adds, picks):
        drops = {pid: next(r for r in rosters_in if r != rid) for pid, rid in adds.items()}
        return {"transaction_id": tid, "type": "trade", "status": "complete", "status_updated": ms,
                "roster_ids": rosters_in, "adds": adds, "drops": drops, "draft_picks": picks,
                "season": SEASON, "teams": names}

    def pick(season, rnd, orig, frm, to):
        return {"season": season, "round": rnd, "roster_id": orig, "previous_owner_id": frm, "owner_id": to}

    league_trades = [
        # Team 2 sells its 2027 1st for team 9's player.
        trade("t1", 1788000000000, [2, 9], {p[8]: 2}, [pick("2027", 1, 2, 2, 9)]),
        # Team 4 sells a 1st and a player for two of team 11's players.
        trade("t2", 1789000000000, [4, 11], {p[10]: 4, p[3]: 11, p[11]: 4}, [pick("2027", 1, 4, 4, 11)]),
        # No 1st: doesn't measure anything.
        trade("t3", 1789500000000, [5, 6], {p[4]: 6, p[5]: 5}, []),
        # 1sts both ways: can't tell who overpaid for which.
        trade("t4", 1789600000000, [1, 8], {}, [pick("2027", 1, 1, 1, 8), pick("2028", 1, 8, 8, 1)]),
    ]
    prices = {
        "t1": {"FantasyCalc": {"pick:2027:1:2": 4000, p[8]: 5200},
               "KeepTradeCut": {"pick:2027:1:2": 5000, p[8]: 6500},
               "FantasyPros (via DynastyProcess)": {"pick:2027:1:2": 2000, p[8]: 2600}},
        "t2": {"FantasyCalc": {"pick:2027:1:4": 4000, p[3]: 3000, p[10]: 6000, p[11]: 2000},
               # KTC has no reading for one of the players then, so it sits this one out.
               "KeepTradeCut": {"pick:2027:1:4": 5000, p[3]: 3500, p[10]: None, p[11]: 2500}},
    }

    sleeper = {
        "league": league, "rosters": rosters, "users": users, "players": players,
        "traded_picks": traded, "state": {"season": SEASON, "season_type": "regular", "week": weeks_played + 1},
        "matchups": matchups,
    }
    return {"sleeper": sleeper, "fantasycalc": fc, "ktc": ktc, "dp_values": dp_values, "dp_ids": dp_ids,
            "sleeper_week_proj": week_rows, "sleeper_season_proj": season_rows, "fp_week": fp_pages,
            "league_trades": league_trades, "trade_prices": prices}
