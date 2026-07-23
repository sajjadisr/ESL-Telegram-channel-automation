import json
from config import FEEDBACK_PATH, STRATEGY_PATH
from database import get_recent_posts
from memory import load_json, save_json
from ai import generate_content
from prompts import build_strategy_prompt

def main():
    recent_posts = get_recent_posts(limit=15)
    feedback_list = load_json(FEEDBACK_PATH, [])

    prompt = build_strategy_prompt(recent_posts, feedback_list)
    raw = generate_content(prompt)
    cleaned = raw.replace("```json", "").replace("```", "").strip()

    try:
        new_strategy = json.loads(cleaned)
        save_json(STRATEGY_PATH, new_strategy)
        print("استراتژی به‌روزرسانی شد:", new_strategy)
    except json.JSONDecodeError:
        print("پاسخ هوش مصنوعی قابل‌تفسیر نبود، استراتژی تغییر نکرد.")
        print(raw)

if __name__ == "__main__":
    main()