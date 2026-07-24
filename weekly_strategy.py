from config import FEEDBACK_PATH, STRATEGY_PATH
from database import get_recent_posts
from memory import load_json, save_json
from ai import generate_json
from prompts import build_strategy_prompt


def main():
    recent_posts = get_recent_posts(limit=15)
    feedback_list = load_json(FEEDBACK_PATH, [])

    prompt = build_strategy_prompt(recent_posts, feedback_list)

    # This call runs once a week but steers every post for the next 7 days —
    # the highest-consequence, lowest-frequency call in the whole system.
    # It was previously on generate_content (the cheap/high-quota drafting
    # tier meant for high-volume calls); generate_json routes through the
    # smarter REVIEW_MODEL tier instead, and reuses the same ```json fence
    # -stripping + parsing logic every other structured-output call in the
    # codebase already uses, rather than hand-rolling it again (Audit #6).
    new_strategy = generate_json(prompt, fallback=None)

    if new_strategy is None:
        print("پاسخ هوش مصنوعی قابل‌تفسیر نبود یا خطای API داشت، استراتژی تغییر نکرد.")
        return

    save_json(STRATEGY_PATH, new_strategy)
    print("استراتژی به‌روزرسانی شد:", new_strategy)


if __name__ == "__main__":
    main()
