"""Temporary: where does the KeepTradeCut page load its full player list now? (round 3)"""
import re, sys
sys.path.insert(0, ".")
from advisor import http
from advisor.sources import ktc

base = "https://keeptradecut.com"
html = http.get_text(ktc.URL, params={"page": 0, "filters": "QB|WR|RB|TE|RDP", "format": 1})
i = html.find("var playersArray")
print("== around playersArray\n", html[i - 1500: i + 2500])
srcs = re.findall(r'<script[^>]*src="(/[^"]+)"', html)
print("local scripts:", srcs)
for s in srcs:
    js = http.get_text(base + s)
    print(f"\n######## {s} length {len(js)}")
    print("head:", js[:1500])
    for word in ("playersArray", "fetch(", "$.ajax", "$.get", "/api/", "dataCache", "oneQBValues", "dynasty-rankings"):
        for m in list(re.finditer(re.escape(word), js))[:4]:
            print(f"-- {word} at {m.start()}: {js[max(0, m.start() - 250): m.start() + 450]}")
