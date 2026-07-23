import os

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

DB_PATH = "data/posts.db"
TOPICS_PATH = "data/topics.json"
MEMORY_PATH = "data/memory.json"
STRATEGY_PATH = "data/strategy.json"
FEEDBACK_PATH = "data/feedback.json"