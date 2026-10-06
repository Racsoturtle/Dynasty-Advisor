"""League and run settings. Everything league-specific lives here."""

LEAGUE_ID = "1327317900188487680"
MY_USERNAME = "Racsoturtle"

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
TRADE_IDEAS_PER_PARTNER = 2
TRADE_MIN_ASSET = 300  # assets below this value don't move a trade
HOLD_MAX_POINTS_LOSS = 3.0  # weekly points a Hold trade may cost
HOLD_PICKS_FOR_AGE = 25.5  # on Hold, picks only buy players this young or younger
