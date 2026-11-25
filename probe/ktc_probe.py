"""Temporary: what does the KeepTradeCut rankings page return now? (round 2)"""
import json, re, sys
sys.path.insert(0, ".")
from advisor import http
from advisor.sources import ktc

html = http.get_text(ktc.URL, params={"page": 0, "filters": "QB|WR|RB|TE|RDP", "format": 1})
for m in re.finditer(r"var\s+(\w+)\s*=\s*(\[|\{|true|false|\d)", html):
    print("var", m.group(1), "starts", m.group(2), "at", m.start())
m = ktc._ARRAY.search(html)
print("playersArray match:", m.group(0)[:200] if m else None)
dec = json.JSONDecoder()
i = html.find("var oneQBPlayers")
rows, _ = dec.raw_decode(html, html.index("[", i))
print("oneQBPlayers rows", len(rows))
r0 = rows[0]
print("row0 keys:", list(r0))
q = r0["oneQBValues"]
print("oneQBValues keys:", {k: (v if not isinstance(v, (dict, list)) else type(v).__name__) for k, v in q.items()})
for k, v in q.items():
    if isinstance(v, dict):
        print(f"oneQBValues.{k}:", {kk: vv for kk, vv in v.items() if not isinstance(vv, list)})
pos = {}
for r in rows:
    pos[r.get("position")] = pos.get(r.get("position"), 0) + 1
print("positions:", pos)
picks = [r for r in rows if r.get("position") not in ("QB", "RB", "WR", "TE")]
for r in picks[:40]:
    q = r["oneQBValues"]
    print("pick:", r["playerName"], "|", r["position"], "| value", q.get("value"), "| blend", q.get("blendValue"), "| vft", q.get("vftValue"))
for r in rows[:8]:
    q = r["oneQBValues"]
    print("player:", r["playerName"], r["position"], "value", q.get("value"), "blend", q.get("blendValue"), "vft", q.get("vftValue"))
top = sorted(rows, key=lambda r: -(r["oneQBValues"].get("value") or 0))[:5]
print("top by value:", [(r["playerName"], r["oneQBValues"].get("value")) for r in top])
