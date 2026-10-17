"""League and run settings. Everything league-specific lives here."""

LEAGUE_ID = "1327317900188487680"
MY_USERNAME = "Racsoturtle"
SITE_URL = "https://racsoturtle.github.io/Dynasty-Advisor/"
GITHUB_REPO = "Racsoturtle/Dynasty-Advisor"
GITHUB_OWNER = "Racsoturtle"  # only this account's issues can mark an offer as denied

# Who can sign in. Each profile gets the whole site built from its own team,
# under SITE_URL/<key>/. The team is the league member whose Sleeper display
# name (or team name) is `username`. Passwords are stored only as
# sha256("dynasty-advisor:<key>:<password>"). This keeps casual visitors out;
# it isn't real security, since the site is public and its files can be
# fetched directly. `store` names the browser storage the pages use.
PROFILES = {
    "oscar": {"name": "Oscar", "username": MY_USERNAME, "store": "dynasty-advisor",
              "password_sha256": "a3421bf081b51292f9f066f3b6650e3c6abaef0cf3afe28c689881d5a3b95531"},
    "jawsh": {"name": "Jawsh", "username": "Jawshwaganda", "store": "dynasty-advisor-jawsh",
              "password_sha256": "5499d174877ae57692bd39a90e635fc67b19f515d1a2723f3862078396a72a17"},
}
DEFAULT_PROFILE = "oscar"

# Value sources are asked for this format where they support it.
NUM_TEAMS = 16
NUM_QBS = 1
PPR = 1

# A source whose data is older than this is left out of the consensus.
STALE_DAYS = 14

# Two sources "disagree" on a player when their spread is this large.
DISAGREE_MIN = 1000
DISAGREE_SHARE = 0.35

# Future rookie-draft seasons to value, counted from the current season.
PICK_YEARS_AHEAD = 3

HTTP_TIMEOUT = 30
USER_AGENT = "dynasty-advisor (personal league dashboard)"

# Contend / hold / retool thresholds on playoff odds.
CONTEND_ODDS = 0.35
RETOOL_ODDS = 0.15
SIMULATIONS = 10_000

# A start/sit decision is a close call inside this many projected points.
CLOSE_CALL_POINTS = 1.5
# A free agent must beat your current option by this much to be flagged.
WAIVER_WEEKLY_GAIN = 2.0
WAIVER_VALUE_GAIN = 150
WAIVER_DYNASTY_MAX = 3

# Injury designations that mean a player won't play.
OUT_STATUSES = {"Out", "IR", "PUP", "Sus", "NA", "COV", "DNR"}

# Trade ideas: Oscar gets this much more consensus value than they give.
TRADE_MIN_EDGE = 0.03
TRADE_MAX_EDGE = 0.10
# In a package, the best piece counts fully and each next piece a bit less,
# so two mid players don't add up to one star.
PACKAGE_WEIGHTS = (1.0, 0.85, 0.75, 0.70)
TRADE_POOL = 14  # most valuable assets per side considered in each search
TRADE_IDEAS = 10
TRADE_BACKUPS = 15  # held back on the page to fill in for offers marked "They said no"
TRADE_IDEAS_PER_PARTNER = 2
TRADE_MIN_ASSET = 300  # assets below this value don't move a trade
HOLD_MAX_POINTS_LOSS = 3.0  # weekly points a Hold trade may cost
HOLD_PICKS_FOR_AGE = 25.5  # on Hold, picks only buy players this young or younger
# Spare picks: offers that turn 2 or 3 of Oscar's 2nd/3rd-round picks into one
# better asset, so fewer rookies compete for roster and taxi spots.
PICK_DEALS = 5
PICK_DEAL_ROUNDS = (2, 3)

# League pick premium: what this league pays for 1st-round picks, measured
# from its own trades and priced with each source's values on the trade date.
HISTORY_SEASONS = 3  # this season and up to two before it
# Few trades make a noisy measurement, so it's pulled toward "no premium"
# as if this many fairly priced trades had also been seen.
PREMIUM_PRIOR_TRADES = 3
PREMIUM_RANGE = (0.8, 1.5)
# With the premium, Oscar's real edge can top TRADE_MAX_EDGE while the deal
# still looks fair at league prices. Never more than this, though.
TRADE_MAX_TRUE_EDGE = 0.25

# Trade log: ideas not recommended for this long drop off the log.
LOG_KEEP_DAYS = 120
