"""Which roster still holds the most of what it took in the league's startup draft."""
import json, urllib.request

API = "https://api.sleeper.app/v1"
def get(p):
    with urllib.request.urlopen(API + p, timeout=30) as r:
        return json.load(r)

lid = "1327317900188487680"
chain = []
while lid and lid != "0":
    lg = get(f"/league/{lid}")
    chain.append(lg)
    lid = lg.get("previous_league_id")
print("Seasons:", [(l["season"], l["league_id"]) for l in chain])
first = chain[-1]
drafts = []
for lg in chain:
    for d in get(f"/league/{lg['league_id']}/drafts"):
        drafts.append((lg["season"], d))
for s, d in drafts:
    print("draft", s, d["draft_id"], d.get("type"), d.get("status"), "rounds", (d.get("settings") or {}).get("rounds"),
          "name", (d.get("metadata") or {}).get("name"))
season0 = first["season"]
startup = max((d for s, d in drafts if s == season0), key=lambda d: (d.get("settings") or {}).get("rounds") or 0)
print("Using startup draft", startup["draft_id"], "season", season0)
picks = get(f"/draft/{startup['draft_id']}/picks")
cur = chain[0]["league_id"]
rosters = get(f"/league/{cur}/rosters")
users = {u["user_id"]: u for u in get(f"/league/{cur}/users")}
users0 = {u["user_id"]: u for u in get(f"/league/{first['league_id']}/users")}
rost0 = {r["roster_id"]: r for r in get(f"/league/{first['league_id']}/rosters")}
def name(u):
    return ((u.get("metadata") or {}).get("team_name") or u.get("display_name")) if u else "?"
drafted = {}
for p in picks:
    drafted.setdefault(p["roster_id"], []).append(p)
rows = []
for r in rosters:
    rid = r["roster_id"]
    now = set(r.get("players") or []) | set(r.get("taxi") or []) | set(r.get("reserve") or [])
    mine = [p for p in drafted.get(rid, []) if p.get("player_id")]
    kept = [p for p in mine if p["player_id"] in now]
    u, u0 = users.get(r.get("owner_id")), users0.get((rost0.get(rid) or {}).get("owner_id"))
    rows.append((len(kept), len(mine), len(now), rid, name(u), (u or {}).get("display_name"), name(u0),
                 [f"{p['metadata'].get('first_name','')} {p['metadata'].get('last_name','')} (R{p['round']})" for p in kept]))
rows.sort(key=lambda x: (-x[0] / max(x[1], 1), -x[0]))
print()
print("kept/drafted | share of current roster | roster | team now (user) | team at draft")
for k, m, n, rid, t, dn, t0, names in rows:
    print(f"{k}/{m} = {k/max(m,1):.0%} | {k/max(n,1):.0%} of {n} | {rid} | {t} ({dn}) | {t0}")
    print("    kept:", ", ".join(names))
