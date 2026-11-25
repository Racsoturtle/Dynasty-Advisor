"""Temporary: what does the KeepTradeCut rankings page return now?"""
import json, re, sys
sys.path.insert(0, ".")
from advisor import http
from advisor.sources import ktc

html = http.get_text(ktc.URL, params={"page": 0, "filters": "QB|WR|RB|TE|RDP", "format": 1})
print("length", len(html))
for tag in re.findall(r"<script[^>]*>", html)[:40]:
    print("script tag:", tag[:200])
m1 = ktc._JSON_TAG.search(html)
m2 = ktc._ARRAY.search(html)
print("ktc-players tag:", bool(m1), "playersArray:", bool(m2))
m = m1 or m2
if m:
    rows = json.loads(m.group(1))
    print("rows", len(rows), type(rows).__name__)
    if rows:
        r0 = rows[0]
        print("row0 keys:", list(r0.keys()) if isinstance(r0, dict) else r0)
        print("row0:", json.dumps(r0)[:3000])
        pos = {}
        for r in rows:
            pos[r.get("position")] = pos.get(r.get("position"), 0) + 1
        print("positions:", pos)
        for r in rows:
            if r.get("position") not in ("QB", "RB", "WR", "TE"):
                print("pick row:", json.dumps(r)[:600]); break
for word in ("oneQB", "superflex", "Value", "playerName", "__NEXT_DATA__", "application/json"):
    i = html.find(word)
    print(f"== {word} first at {i}")
    if i >= 0:
        print(html[max(0, i - 300): i + 500].replace("\n", " "))
print("== head\n", html[:3000])
