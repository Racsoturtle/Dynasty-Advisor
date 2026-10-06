# Dynasty Advisor

A personal dashboard for Racsoturtle's team in the Skulls Super Dynasty League on Sleeper.
It rebuilds every morning on GitHub and publishes to GitHub Pages.

Player and pick values come only from outside sources, averaged with equal weight:

- [FantasyCalc](https://www.fantasycalc.com) (values from real trades)
- [KeepTradeCut](https://keeptradecut.com) (crowdsourced)
- FantasyPros expert rankings, via [DynastyProcess](https://github.com/dynastyprocess/data).
  DynastyProcess values are a formula on FantasyPros rankings, so the two count as one vote.

Each source is turned into ranks and read off one shared 0 to 10,000 curve, so no source counts
for more because its numbers are bigger. A source with data older than 14 days is left out.

## Run it

```
pip install -r requirements.txt
python -m advisor.main                 # live data, writes ./site
python -m advisor.main --snapshot DIR  # also saves every raw download
python -m advisor.main --offline DIR   # rebuild from a saved snapshot
python -m pytest                       # tests use tests/sample_league.py
```

League settings live in `advisor/config.py`.
