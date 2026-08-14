from config import (
    FEEDBACK_PATH, STRATEGY_PATH, SCHEDULE_PATH, MIN_FEEDBACK_FOR_SCHEDULE_UPDATE, ANALYTICS_PATH,
    MEMORY_PATH,
)
from database import get_recent_posts
from memory import load_json, save_json
from ai import generate_json
from prompts import FORMATS, build_strategy_prompt
from schedule_builder import build_engagement_schedule, diff_schedule
from telegram_bot import send_admin_message
from text_utils import escape_html
import analytics
import audience_profile
import experiments
import topic_selection

MIN_SAMPLES_TO_FLAG_EXPERIMENT = 3  # per variant — small on purpose, this
# channel runs at most ~1 quiz and ~1 vote_poll a week, so "enough data" is
# already a matter of months, not something to set high and wait forever for.


def build_intelligence_report_text():
    """Weekly digest of the three review-driven systems (reward score,
    audience profile, active A/B test) — see analytics.py / audience_profile.py
    / experiments.py for what each one can and can't observe."""
    lines = ["📊 <b>گزارش هفتگی هوشمندی کانال</b>"]

    score_summary = analytics.recent_score_summary()
    if score_summary:
        score_lines = "، ".join(
            f"{FORMATS.get(f, {}).get('label', f)}: {s}" for f, s in score_summary.items()
        )
        lines.append(f"میانگین امتیاز ترکیبی اخیر (تعامل + یادگیری) بر اساس فرمت: {score_lines}")
    else:
        lines.append("هنوز هیچ کوییز/نظرسنجی‌ای بسته و امتیازدهی نشده — امتیاز ترکیبی فعلاً موجود نیست.")

    recent_posts = get_recent_posts(limit=3)
    if recent_posts:
        sample_titles = "، ".join(f"«{p[0]}»" for p in recent_posts[:3])
        lines.append(f"نمونه‌های اخیر پست برای بررسی دستی: {sample_titles}")

    profile = audience_profile.get_profile()
    if profile.get("avg_quiz_accuracy") is not None:
        lines.append(f"میانگین درصد پاسخ درست کوییزهای اخیر: {profile['avg_quiz_accuracy']}٪")
    if profile.get("weak_categories"):
        lines.append("دسته‌های ضعیف مخاطب (طبق کوییزهای واقعی): " + "، ".join(profile["weak_categories"]))
    if profile.get("strong_categories"):
        lines.append("دسته‌های قوی مخاطب: " + "، ".join(profile["strong_categories"]))

    # Pillar-coverage observability (§6, Stage 1 — visibility only, no
    # change to what actually gets scheduled). schedule_builder already
    # balances *formats* across the week; nothing before this watched
    # whether a whole *pillar* (topics.json category) quietly went dark for
    # weeks just because of which formats happened to draw which topics.
    memory = load_json(MEMORY_PATH, {})
    pillar_bits = []
    for pillar in topic_selection.all_pillars():
        days = topic_selection.days_since_pillar_covered(memory, pillar)
        pillar_bits.append(f"{pillar}: {'هنوز پوشش نداده' if days is None else f'{days} روز پیش'}")
    if pillar_bits:
        lines.append("پوشش دسته‌ها (آخرین بار هر دسته کِی پوشش داده شده): " + "، ".join(pillar_bits))

    active_exp = experiments.get_active_experiment()
    if active_exp:
        all_analytics = load_json(ANALYTICS_PATH, [])
        results = experiments.summarize_results(active_exp, all_analytics)
        result_lines = "؛ ".join(
            f"{label}: n={r['n']}، میانگین رأی={r['avg_votes']}، میانگین امتیاز={r['avg_score']}"
            for label, r in results.items()
        )
        lines.append(f"آزمایش فعال «{active_exp['name']}»: {result_lines}")
        min_n = min((r["n"] for r in results.values()), default=0)
        if min_n >= MIN_SAMPLES_TO_FLAG_EXPERIMENT:
            lines.append(
                "هر دو حالت این آزمایش الان نمونه‌ی کافی دارن — یه نگاه بنداز و خودت تصمیم بگیر "
                "کدوم رو نگه داری (سیستم چیزی رو خودکار انتخاب نمی‌کنه)."
            )

    lines.append(
        "یادآوری: آمار بالا فقط از تلگرامه. ایتا و بله فعلاً فقط وضعیت ارسال (موفق/ناموفق) رو "
        "گزارش می‌دن، نه رأی یا تعامل واقعی — این دو تا رو کنار آمار تلگرام به‌عنوان چیز "
        "قابل‌مقایسه نبین."
    )
    return "\n".join(lines)


def send_weekly_intelligence_report():
    """Independent of whether the strategy-generation call in main() below
    succeeds this run — the report describes existing data, so it always
    goes out."""
    send_admin_message(build_intelligence_report_text())


def validate_strategy(data):
    """Reject model output that doesn't match expected schema (Audit #19).

    best_formats is no longer part of this schema — see schedule_builder.py's
    module docstring for why: format selection is now a deterministic
    function of analytics.recent_score_summary(), computed in
    update_schedule_from_engagement below with zero LLM calls. This
    function's only remaining job is focus_more_on/focus_less_on, the
    genuinely qualitative topic-level judgment a formula can't produce."""
    if not isinstance(data, dict):
        return False, "root is not an object"
    for key in ("focus_more_on", "focus_less_on"):
        if key not in data or not isinstance(data[key], list):
            return False, f"missing or invalid list: {key}"
    return True, ""


def main():
    send_weekly_intelligence_report()

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
            f"⚠️ به‌روزرسانی استراتژی هفتگی رد شد — خروجی مدل معتبر نبود: {escape_html(reason)}\n"
            f"استراتژی قبلی نگه داشته شد."
        )
        print("Strategy validation failed:", reason, new_strategy)
        return

    save_json(STRATEGY_PATH, new_strategy)
    print("استراتژی به‌روزرسانی شد:", new_strategy)

    update_schedule_from_engagement()


def update_schedule_from_engagement():
    """Reshape data/format_schedule.json around analytics.recent_score_
    summary() — real, measured per-format performance (poll votes/quiz
    correct-rate always; views/forwards too, for every format, once
    engagement_harvest.py is configured) — computed with zero LLM calls in
    between. See schedule_builder.py's module docstring for the full
    reasoning behind retiring the old best_formats LLM guess.

    No longer takes strategy/feedback_list — format weighting doesn't come
    from either anymore, so this function's only remaining dependency is
    analytics.json itself."""
    score_summary = analytics.recent_score_summary()
    scored_count = analytics.recent_scored_count()
    if scored_count < MIN_FEEDBACK_FOR_SCHEDULE_UPDATE:
        print(
            f"فقط {scored_count} پست امتیازدهی‌شده‌ی واقعی توی این بازه هست "
            f"(حداقل لازم: {MIN_FEEDBACK_FOR_SCHEDULE_UPDATE}) — برنامه‌ی هفتگی "
            f"فعلاً بر اساس امتیاز واقعی تغییر نمی‌کنه، چون هنوز داده‌ی کافی نیست."
        )
        return

    current_schedule = load_json(SCHEDULE_PATH, {})
    new_schedule = build_engagement_schedule(list(FORMATS.keys()), score_summary, current_schedule)

    changes = diff_schedule(current_schedule, new_schedule)
    if not changes:
        print("برنامه‌ی هفتگی همون چیزیه که بر اساس امتیازهای واقعی انتظار می‌رفت — تغییری لازم نبود.")
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
    score_lines = "، ".join(
        f"{FORMATS.get(f, {}).get('label', f)}: {s}" for f, s in score_summary.items()
    ) or "هیچکدام"
    send_admin_message(
        f"📅 برنامه‌ی هفتگی بر اساس امتیاز واقعی تعامل ({scored_count} پست اخیر امتیازدهی‌شده) به‌روز شد:\n"
        f"{change_lines}\n\n"
        f"میانگین امتیاز اخیر بر اساس فرمت: {score_lines}"
    )
    print("برنامه‌ی هفتگی به‌روزرسانی شد:", new_schedule)


if __name__ == "__main__":
    main()
