import os

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# Optional. Your own Telegram numeric chat ID (message @userinfobot to get it).
# Used ONLY to hand you image-generation prompts to paste into an image tool
# yourself (this project never calls an image generator). If you don't set
# this secret, image prompts are just printed to the workflow log instead —
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

# Post a "progress recap" (format 8 in the design) instead of the day's
# scheduled format every N published posts, so spaced repetition is a real,
# automatic thing rather than something that only happens if you remember.
RECAP_EVERY_N_POSTS = 14
