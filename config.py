import os

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# Optional second Gemini API key, ideally from a DIFFERENT Google account/
# project than GEMINI_API_KEY. Google has repeatedly, without warning,
# switched individual accounts over to issuing only "AQ."-prefixed API keys
# instead of the classic "AIza" format — and those AQ. keys get rejected by
# generativelanguage.googleapis.com with a 401 (see ai.GeminiAuthError). This
# is an account-level issue, not something fixable in code, so the only real
# mitigation is a second, independent credential: if the primary key starts
# failing with an auth error, ai.py tries this one before giving up. Leave
# unset to run with just the one key (existing behavior, unchanged).
GEMINI_API_KEY_BACKUP = os.environ.get("GEMINI_API_KEY_BACKUP", "").strip()

# Optional. Free-tier (no credit card) text-generation fallback via Groq,
# used only once EVERY configured Gemini key/model above has failed for a
# given call — see ai.py's Groq section for the retry/fallback order. This
# exists because GEMINI_API_KEY_BACKUP doesn't cover every failure mode: the
# "AQ." key rollout described above is Google rejecting a *key format*, not
# one specific credential, so it can hit every key on every Google account,
# including a second/backup one. Groq runs on entirely separate
# infrastructure, so it isn't affected by whatever is currently wrong with
# Gemini. Get a free key at console.groq.com (no card required). Leave
# unset to run with Gemini only (existing behavior, unchanged) — if Gemini
# fails and this isn't set, the run fails exactly as it did before this was
# added.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

# Optional. Free-tier (no credit card) image-generation fallback via
# Cloudflare Workers AI, used only once BOTH Gemini image tiers
# (ai.IMAGE_MODEL and ai.FALLBACK_IMAGE_MODEL) have failed to produce an
# image. Both values come from the same Cloudflare account:
# dash.cloudflare.com -> Workers AI -> the account ID is in the right
# sidebar / URL; create an API token with "Workers AI: Read" permission
# (Read is enough - this only calls the /ai/run endpoint). Leave either
# unset to skip this fallback; handle_image_format's existing manual
# admin hand-off still applies exactly as before.
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()

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
# The durable record is this file, not DB_PATH above. DB_PATH is a local
# SQLite cache that database.py rebuilds from POSTS_JSONL_PATH whenever it's
# missing (a fresh CI checkout, every single run, since it's gitignored) —
# see database.py's module docstring. posts.db itself is never committed.
POSTS_JSONL_PATH = "data/posts.jsonl"
TOPICS_PATH = "data/topics.json"
MEMORY_PATH = "data/memory.json"
STRATEGY_PATH = "data/strategy.json"
FEEDBACK_PATH = "data/feedback.json"
SCHEDULE_PATH = "data/format_schedule.json"
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
REVIEW_INTERVALS_DAYS = [1]
# Was [1, 7] before the graded-reader/news formats were added. Rebalanced
# because one of the two "extra" daily slots is now reserved for
# reader_installment (see main.py's extra-slot logic) — review capacity
# dropped from 2 slots/day to 1, and the math above only avoids a growing
# backlog if fresh_per_day * len(REVIEW_INTERVALS_DAYS) <= review_capacity,
# i.e. 1 * 1 <= 1. The honest tradeoff: the day-7 reinforcement pass is
# gone, so retention leans more on the standing MAINTENANCE_INTERVAL_DAYS
# refresh below than it used to.

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

# --- Graded-reader integration (reader.py) ----------------------------------
# Pre-chunked story queue. Each story is fully segmented into a fixed,
# known number of chunks BEFORE posting starts — the ending is decided on
# day one, so a series can never "run out of what happens next" mid-run.
# Progress is tracked in posts.db (story_id/chunk_index columns), not here —
# see reader.py's module docstring for why the old story_installment format
# broke and how this avoids repeating it.
READER_LIBRARY_PATH = "data/reader_library.json"

# When the number of not-yet-started stories in the library drops to this
# level or below, main.py alerts the admin the same way
# maybe_alert_low_topic_supply already does for topics.json. Unlike topics,
# there's no auto-generation here — a good graded story needs real curation
# (level, length, actual plot), not a one-line prompt — so this is
# alert-only.
LOW_STORY_WARNING_THRESHOLD = 2

# --- Real news, re-leveled (news.py) ----------------------------------------
# RSS, not an API: no credential to expire, get rate-limited, or need
# billing attention — the only failure mode is "is the internet reachable",
# which every other step already depends on too. Several long-running,
# well-documented feeds rather than one, so one being briefly down doesn't
# stall the day's post.
NEWS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "https://feeds.bbci.co.uk/news/also_in_the_news/rss.xml",
]

# Rolling dedup window (news.py keeps this many recently-used links in
# memory.json — same file that already tracks avoid/covered topics — so a
# feed re-serving the same headline tomorrow doesn't repeat it).
NEWS_SEEN_MAX = 200

# Mechanical keyword denylist, not an editorial judgment call: skips
# headlines/summaries containing these terms so heavy news doesn't land
# next to a café dialogue about ordering coffee. Plain-text, lowercase,
# edit freely.
NEWS_DENYLIST_KEYWORDS = [
    "killed", "dead", "death", "dies", "war", "attack", "shooting", "bomb",
    "terror", "murder", "rape", "abuse", "suicide", "massacre", "genocide",
    "assault", "explosion", "conflict", "violence", "shot", "stabbed",
]

# HTTP timeout (seconds) for each individual feed request. feedparser.parse()
# has no timeout parameter of its own, so news.py fetches the raw bytes with
# `requests` first — same explicit-timeout discipline ai.py/channels.py/
# telegram_bot.py already use elsewhere in this codebase — then hands the
# bytes to feedparser. Without this, a feed that connects but then stalls
# (rather than actively refusing) could block the run indefinitely, since
# Python's socket default timeout is "wait forever."
NEWS_REQUEST_TIMEOUT = 10

# Sent as the User-Agent on every feed request instead of feedparser's
# default "feedparser/6.x +https://github.com/kurtmckee/feedparser" string,
# which some CDN/WAF layers soft-block or throttle as an obvious bot,
# especially from datacenter/CI IP ranges. Edit freely if you rename the
# channel or its public link.
NEWS_USER_AGENT = "Mozilla/5.0 (compatible; inEnglishBot/1.0; +https://t.me/inEnglish)"

# How many consecutive fetch_news_item() calls must come back empty before
# main.py alerts the admin once (see news.health_alert_needed). Deliberately
# measured in *attempts*, not calendar days — the news slot doesn't run
# every day, so a day-based threshold would fire at inconsistent real-world
# intervals. This is what turns "BBC quietly retired/renamed a feed URL"
# from silent-forever degradation (fetch_news_item keeps returning None,
# main.py keeps falling back to the normal topic pool, nobody notices) into
# a one-time heads-up instead.
NEWS_FAILURE_ALERT_THRESHOLD = 5