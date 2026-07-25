from config import FEEDBACK_PATH, STRATEGY_PATH, SCHEDULE_PATH, MIN_FEEDBACK_FOR_SCHEDULE_UPDATE
from database import get_recent_posts
from memory import load_json, save_json
from ai import generate_json
from prompts import FORMATS, build_strategy_prompt, filter_recent_feedback
from schedule_builder import build_engagement_schedule, diff_schedule
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

    update_schedule_from_engagement(new_strategy, feedback_list)


def update_schedule_from_engagement(strategy, feedback_list):
    """Reshape data/format_schedule.json around strategy['best_formats'] —
    otherwise best_formats is computed every week and never actually used
    anywhere (it used to just sit in strategy.json unread)."""
    recent_feedback = filter_recent_feedback(feedback_list)
    if len(recent_feedback) < MIN_FEEDBACK_FOR_SCHEDULE_UPDATE:
        print(
            f"فقط {len(recent_feedback)} بازخورد واقعی توی این بازه هست "
            f"(حداقل لازم: {MIN_FEEDBACK_FOR_SCHEDULE_UPDATE}) — برنامه‌ی هفتگی "
            f"فعلاً بر اساس best_formats تغییر نمی‌کنه، چون هنوز داده‌ی کافی نیست."
        )
        return

    current_schedule = load_json(SCHEDULE_PATH, {})
    best_formats = strategy.get("best_formats", [])
    new_schedule = build_engagement_schedule(list(FORMATS.keys()), best_formats, current_schedule)

    changes = diff_schedule(current_schedule, new_schedule)
    if not changes:
        print("برنامه‌ی هفتگی همون چیزیه که بر اساس best_formats انتظار می‌رفت — تغییری لازم نبود.")
        return

    save_json(SCHEDULE_PATH, new_schedule)

    day_labels = {
        "Saturday": "شنبه", "Sunday": "یکشنبه", "Monday": "دوشنبه",
        "Tuesday": "سه‌شنبه", "Wednesday": "چهارشنبه", "Thursday": "پنجشنبه", "Friday": "جمعه",
    }
    change_lines = "\n".join(
        f"- {day_labels.get(day, day)}: {FORMATS.get(old, {}).get('label', old)} ← "
        f"{FORMATS.get(new, {}).get('label', new)}"
        for day, old, new in changes
    )
    send_admin_message(
        f"📅 برنامه‌ی هفتگی بر اساس بازخورد واقعی ({len(recent_feedback)} مورد اخیر) به‌روز شد:\n"
        f"{change_lines}\n\n"
        f"فرمت‌های برتر این هفته: {', '.join(FORMATS.get(f, {}).get('label', f) for f in best_formats) or 'هیچکدام'}"
    )
    print("برنامه‌ی هفتگی به‌روزرسانی شد:", new_schedule)


if __name__ == "__main__":
    main()
