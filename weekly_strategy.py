from config import FEEDBACK_PATH, STRATEGY_PATH
from database import get_recent_posts
from memory import load_json, save_json
from ai import generate_json
from prompts import FORMATS, build_strategy_prompt
from telegram_bot import send_admin_message


def validate_strategy(data):
    """Reject model output that doesn't match expected schema (Audit #19)."""
    if not isinstance(data, dict):
        return False, "root is not an object"
    for key in ("focus_more_on", "focus_less_on", "best_formats"):
        if key not in data or not isinstance(data[key], list):
            return False, f"missing or invalid list: {key}"
    valid_keys = set(FORMATS.keys())
    bad_formats = [f for f in data["best_formats"] if f not in valid_keys]
    if bad_formats:
        return False, f"unknown format keys: {bad_formats}"
    return True, ""


def main():
    recent_posts = get_recent_posts(limit=15)
    feedback_list = load_json(FEEDBACK_PATH, [])

    prompt = build_strategy_prompt(recent_posts, feedback_list)
    new_strategy = generate_json(prompt, fallback=None)

    if new_strategy is None:
        print("پاسخ هوش مصنوعی قابل‌تفسیر نبود یا خطای API داشت، استراتژی تغییر نکرد.")
        return

    ok, reason = validate_strategy(new_strategy)
    if not ok:
        send_admin_message(
            f"⚠️ به‌روزرسانی استراتژی هفتگی رد شد — خروجی مدل معتبر نبود: {reason}\n"
            f"استراتژی قبلی نگه داشته شد."
        )
        print("Strategy validation failed:", reason, new_strategy)
        return

    save_json(STRATEGY_PATH, new_strategy)
    print("استراتژی به‌روزرسانی شد:", new_strategy)


if __name__ == "__main__":
    main()
