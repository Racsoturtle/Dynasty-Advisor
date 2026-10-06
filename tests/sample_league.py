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
        r["starters"] = r["players"][:8]
        r["taxi"] = r["players"][-3:]
        r["reserve"] = r["players"][-4:-3]
        users.append({"user_id": owners[i], "display_name": "Racsoturtle" if owners[i] == ME else f"Manager{i + 1}",
                      "metadata": {"team_name": f"Team {i + 1}"} if i % 3 else {}})

    matchups = {}
    for week in range(1, weeks_played + 1):
        ids = list(range(1, 17))
        rng.shuffle(ids)
        rows = []
        for m in range(8):
            for rid in ids[2 * m: 2 * m + 2]:
                rows.append({"roster_id": rid, "matchup_id": m + 1, "points": round(rng.uniform(85, 150), 2)})
        matchups[week] = rows
    for r in rosters:
        r["settings"] = {"wins": 0, "losses": 0, "ties": 0, "fpts": 0, "fpts_decimal": 0,
                         "fpts_against": 0, "fpts_against_decimal": 0}
    by_id = {r["roster_id"]: r for r in rosters}
    pf = {rid: 0.0 for rid in by_id}
    pa = {rid: 0.0 for rid in by_id}
    for rows in matchups.values():
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
        "settings": {"draft_rounds": 3, "taxi_slots": 5, "reserve_slots": 2, "trade_deadline": 11},
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

    sleeper = {
        "league": league, "rosters": rosters, "users": users, "players": players,
        "traded_picks": traded, "state": {"season": SEASON, "season_type": "regular", "week": weeks_played + 1},
        "matchups": matchups,
    }
    return {"sleeper": sleeper, "fantasycalc": fc, "ktc": ktc, "dp_values": dp_values, "dp_ids": dp_ids}
