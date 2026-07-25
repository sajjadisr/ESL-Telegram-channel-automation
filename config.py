import os

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# Optional. Your own Telegram numeric chat ID (message @userinfobot to get it).
# Used to hand you image-generation prompts to paste into an image tool
# yourself (this project never calls an image generator), AND for low-topic-
# supply / broken-poll admin alerts (see main.py). If you don't set this
# secret, those messages are just printed to the workflow log instead —
# open the Actions tab and read the run's log to copy them from there.
TELEGRAM_ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")

# --- Extra channels (optional) ---------------------------------------------
# Each platform is entirely optional: if its token isn't set, that platform
# is silently skipped in channels.py — nothing crashes, Telegram still posts
# normally. Add EITAA_TOKEN / BALE_BOT_TOKEN as GitHub Secrets to turn one on.

# Eitaayar (eitaayar.ir) bot token for your Eitaa channel.
EITAA_TOKEN = os.environ.get("EITAA_TOKEN", "")
# Eitaa channel ID WITHOUT the leading @ (Eitaayar's own convention).
EITAA_CHANNEL_ID = os.environ.get("EITAA_CHANNEL_ID", "inEnglish")

# Bale bot token, from Bale's own @Bot_Father.
BALE_BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
# Bale chat ID — like Telegram, "@channelusername" works directly.
BALE_CHAT_ID = os.environ.get("BALE_CHAT_ID", "@inEnglish")

DB_PATH = "data/posts.db"
TOPICS_PATH = "data/topics.json"
MEMORY_PATH = "data/memory.json"
STRATEGY_PATH = "data/strategy.json"
FEEDBACK_PATH = "data/feedback.json"
SCHEDULE_PATH = "data/format_schedule.json"
STORY_PATH = "data/story.json"
# Polls/quizzes that have been sent but not yet closed+harvested for
# feedback.json (see poll_feedback.py / Audit #5).
PENDING_POLLS_PATH = "data/pending_polls.json"

# Post a "progress recap" (format 8 in the design) instead of the day's
# scheduled format every N published posts, so spaced repetition is a real,
# automatic thing rather than something that only happens if you remember.
RECAP_EVERY_N_POSTS = 14

# When the number of not-yet-covered topics in topics.json drops to this
# level or below, main.py sends an admin alert instead of only printing a
# log line nobody reads until the channel goes silent (Audit #1).
LOW_TOPIC_WARNING_THRESHOLD = 10

# Rolling window for weekly strategy feedback (Audit Problem B).
FEEDBACK_WINDOW_WEEKS = 8

# weekly_strategy.py only lets `best_formats` reshape data/format_schedule.json
# once there are at least this many real feedback entries (auto poll/quiz
# harvests or manual feedback_add.py notes) inside FEEDBACK_WINDOW_WEEKS.
# Below this, best_formats is still computed and saved to strategy.json (it
# still steers what the model writes about via focus_more_on/focus_less_on),
# but there isn't enough real engagement signal yet to justify changing which
# days get which format — early on the model would otherwise be guessing.
MIN_FEEDBACK_FOR_SCHEDULE_UPDATE = 4

# --- Weekly campaigns (campaigns.py) ----------------------------------------
# Tracks the current week's pinned theme category + what's already been
# posted this week, so posts can reference each other instead of each living
# in isolation.
CAMPAIGN_STATE_PATH = "data/campaign_state.json"

# --- Engagement telemetry / reward score (analytics.py) --------------------
# Post-level metrics log. Scope is deliberately limited to what this
# cron-only, Bot-API-only pipeline can actually observe — see analytics.py's
# module docstring before assuming this covers views/reactions/forwards.
ANALYTICS_PATH = "data/analytics.json"

# Composite reward score weights (analytics.compute_reward_score). Must sum
# to 1.0. Engagement = this poll's vote count vs. this channel's own recent
# normal; Learning = quiz correct-rate. vote_poll (no correct answer) scores
# on engagement alone regardless of these weights.
REWARD_WEIGHT_ENGAGEMENT = 0.5
REWARD_WEIGHT_LEARNING = 0.5

# --- Rule-based audience profile (audience_profile.py) ----------------------
# Single aggregate "class profile", not per-user — Telegram channel polls
# must be anonymous (channels can't send non-anonymous polls at all), so
# there's no per-user data to trace even in principle. See the module
# docstring for why this is deliberately NOT a BKT/DKT/clustering model.
AUDIENCE_PROFILE_PATH = "data/audience_profile.json"
AUDIENCE_WEAK_THRESHOLD = 50    # quiz correct-rate % at/below this → weak category
AUDIENCE_STRONG_THRESHOLD = 80  # quiz correct-rate % at/above this → strong category

# --- Sequential A/B testing (experiments.py) --------------------------------
# One experiment active at a time, alternated post-by-post — see the module
# docstring for why a multi-armed bandit or user-level split isn't a valid
# design on a single broadcast channel with no per-user targeting.
EXPERIMENTS_PATH = "data/experiments.json"
