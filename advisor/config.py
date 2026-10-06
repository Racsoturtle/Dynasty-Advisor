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
