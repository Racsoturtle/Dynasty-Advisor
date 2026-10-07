# Dynasty Advisor

A personal dashboard for Racsoturtle's team in the Skulls Super Dynasty League on Sleeper.
It rebuilds every day by 7 AM Eastern (6:45 AM run, adjusted for daylight saving) and publishes to
GitHub Pages. The Thursday and Sunday builds also post a short summary as a GitHub issue.

Pages: Home (contend, hold or retool call; record and luck; roster values; picks), Lineup (best
lineup by consensus projection, changes, close calls, injuries and byes), Trades (offers to send:
at least 3% in your favor by consensus value but no more than 10% at league prices, better for the
partner's starting lineup, and fitting the call; plus what this league pays for 1sts), Trade checker (grade any offer in the browser and get a counter), Trade log (every suggested offer,
re-valued daily, saved on the `data` branch). "They said no" on an offer hides it in that browser and
a backup offer takes its place; Claude can also mark one for every device by opening a "Denied: ... [id]"
issue from Oscar's account, which the build skips), Waivers (free agents
that clearly beat what you have), League (every team's value, needs and playoff odds).

The Refresh from Sleeper button rebuilds every page in the browser. It loads Python there
([Pyodide](https://pyodide.org), added to the site by `tools/build_engine.py`), pulls fresh rosters,
picks and scores from Sleeper, and reruns the same analysis on the morning's values and projections
(`site/engine/raw.json`, written by `advisor/bundle.py`). Lineup, waivers, playoff odds, the League
page, the trade log and the checker all update. The morning's trade offers are kept, except that an
offer is taken down when the other team's roster changed, and all of them are when Oscar's did; new
offers come with the next morning build. The rebuilt pages are kept in that browser until the next
build. If the engine can't load, the button falls back to listing the day's Sleeper moves.

Player and pick values come only from outside sources, averaged with equal weight:

- [FantasyCalc](https://www.fantasycalc.com) (values from real trades)
- [KeepTradeCut](https://keeptradecut.com) (crowdsourced)
- FantasyPros expert rankings, via [DynastyProcess](https://github.com/dynastyprocess/data).
  DynastyProcess values are a formula on FantasyPros rankings, so the two count as one vote.

Each source is turned into ranks and read off one shared 0 to 10,000 curve, so no source counts
for more because its numbers are bigger. A source with data older than 14 days is left out.

League prices: the league's own trades (this season and the last two) where one team sold 1st-round
picks are priced with each source's values on the trade date. The multiplier that makes both sides
equal is what the league paid for the 1sts; it's averaged over trades and pulled toward 1.0 while
there are few of them. Trade ideas count your 1sts at that price when judging how a deal looks to
the other team.

Weekly projections average Sleeper's projections (scored with the league's own settings) and
FantasyPros weekly expert ranks (turned into points at the same position rank). Playoff odds come
from 10,000 simulations of the remaining schedule.

## Run it

```
pip install -r requirements.txt
python -m advisor.main                 # live data, writes ./site
python -m advisor.main --snapshot DIR  # also saves every raw download
python -m advisor.main --offline DIR   # rebuild from a saved snapshot
python -m pytest                       # tests use tests/sample_league.py
```

League settings live in `advisor/config.py`.
