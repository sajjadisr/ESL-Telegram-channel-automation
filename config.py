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

# --- Per-platform message-length limits (Platform-awareness audit) --------
# text_utils.truncate_html_safe() used to take one shared 4000-char default
# for all three platforms. That happened to be a safe number for all of
# them, but only by coincidence — it wasn't actually derived from each
# platform's own limit, so it couldn't be tuned per-platform if one of them
# turned out to differ. These are now explicit and separately sourced:
#   - Telegram: documented hard limit, 4096 chars after entities parsing
#     (core.telegram.org/bots/api#sendmessage). CONFIRMED.
#   - Bale: its own Bot API docs state the identical "4096 characters after
#     entities parsing" limit (docs.python-bale-bot.ir). CONFIRMED.
#   - Eitaa: the third-party eitaayar.ir API (used here) does not publish a
#     character limit anywhere in its docs. 4096 is an ASSUMPTION based on
#     it behaving like a Telegram-Bot-API-shaped service, not a confirmed
#     spec — if Eitaa posts start getting rejected/cut server-side, shrink
#     this first rather than assuming it's a bug elsewhere.
TELEGRAM_MAX_MESSAGE_LEN = 4096  # confirmed
BALE_MAX_MESSAGE_LEN = 4096      # confirmed
EITAA_MAX_MESSAGE_LEN = 4096     # unconfirmed assumption — see comment above

# Margin subtracted from the limits above before truncating (truncate_html_safe
# nibbles a few more characters off the end to avoid splitting a tag, and this
# leaves headroom for that so the final text never risks landing back over
# the real limit).
MESSAGE_LEN_SAFETY_MARGIN = 96

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

# How many posts main.py will publish per calendar day. daily_post.yml's
# cron has one trigger per slot below — keep them in sync if you change this.
POSTS_PER_DAY = 3

# Expanding spaced-repetition ladder (days since the last exposure) before a
# previously-covered topic becomes "due" for review — see
# topic_selection.get_due_review_topic(). Roughly follows the spacing-effect
# literature (Cepeda et al., 2006): optimal review gap is ~10-20% of how
# long you want the memory to last, so review sooner while it's fresh.
#
# Deliberately short (2 stages, not 5): each topic introduced generates
# len(REVIEW_INTERVALS_DAYS) review-events that the reserved review
# capacity below has to absorb. With POSTS_PER_DAY slots split as
# (fresh_per_day) + (review_capacity_per_day) = POSTS_PER_DAY, the system
# only avoids an ever-growing backlog if:
#     fresh_per_day * len(REVIEW_INTERVALS_DAYS) <= review_capacity_per_day
# A longer ladder is more thorough per topic but demands much more daily
# review capacity, which crowds out fresh content (or backs up if it
# doesn't get that capacity) — 2 stages is the pragmatic balance for a
# 3-post/day channel; see FRESH_TOPICS_PER_DAY below for the matching half
# of this trade-off. Most of the retention benefit comes from going from
# zero reviews to one; additional stages have rapidly diminishing returns.
REVIEW_INTERVALS_DAYS = [1, 7]

# After a topic clears every stage above ("graduated"), it doesn't stop
# being reviewed forever — it drops into a standing low-frequency
# maintenance cycle instead. This is the Bahrick "permastore" finding
# (foreign-vocabulary retention held for decades with only occasional
# very-long-interval refreshers) — cheap insurance against early lessons
# quietly rotting once the channel has been running for months or years.
MAINTENANCE_INTERVAL_DAYS = 90

# How many of today's POSTS_PER_DAY runs introduce brand-new material.
# The remaining (POSTS_PER_DAY - FRESH_TOPICS_PER_DAY) slots are reserved
# for due reviews (see REVIEW_INTERVALS_DAYS above for why this has to be
# kept in balance, not just set to "as many as feel right"). The first
# slot of the day always keeps its normal weekday-scheduled format (quiz
# day, idiom day, etc. still happen); slots beyond the fresh quota check
# for a due review before falling back to a safe default fresh format.
FRESH_TOPICS_PER_DAY = 1

# Post a "progress recap" (format 8 in the design) instead of the day's
# scheduled format every N published posts, so spaced repetition is a real,
# automatic thing rather than something that only happens if you remember.
RECAP_EVERY_N_POSTS = 14

# When the number of not-yet-covered topics in topics.json drops to this
# level or below, main.py both alerts the admin (Audit #1) AND asks the
# model to propose new topics itself (topic_generation.py) — the pool has
# to be self-renewing for the channel to run for years without someone
# hand-editing data/topics.json.
LOW_TOPIC_WARNING_THRESHOLD = 10

# How many new candidate topics to request in one go when the pool runs
# low. Deliberately more than one topic's worth of runway (LOW_TOPIC_
# WARNING_THRESHOLD itself) so this doesn't fire on every single run once
# the pool dips below threshold — one successful top-up should clear the
# warning for a while.
AUTO_GENERATE_TOPIC_COUNT = 20

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
