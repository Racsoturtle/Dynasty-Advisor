"""Temporary: read KTC's player-pool loader and try its URL. (round 4)"""
import json, re, sys
sys.path.insert(0, ".")
from advisor import http
from advisor.sources import ktc

base = "https://keeptradecut.com"
html = http.get_text(ktc.URL, params={"page": 0, "filters": "QB|WR|RB|TE|RDP", "format": 1})
ver = re.search(r"var playersVersion = '([^']+)'", html).group(1)
print("playersVersion", ver)
src = re.search(r'<script[^>]*src="(/early/dataCache\.js[^"]*)"', html).group(1)
js = http.get_text(base + src)
print("######## dataCache.js\n", js)
for path in ("/dynasty-rankings/players", "/dynasty-rankings/pool", "/dynasty-rankings/player-pool", "/players/pool"):
    for q in ({"v": ver}, {"version": ver}, {}):
        try:
            r = http.get(base + path, params=q, retries=1)
            print("TRY", path, q, r.status_code, r.headers.get("content-type"), len(r.text), r.text[:600])
        except Exception as e:
            print("TRY", path, q, "->", repr(e)[:200])
