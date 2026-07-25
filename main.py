import datetime
import json

from config import (
    MEMORY_PATH, STRATEGY_PATH, SCHEDULE_PATH, STORY_PATH,
    RECAP_EVERY_N_POSTS, LOW_TOPIC_WARNING_THRESHOLD, POSTS_PER_DAY,
)
from database import (
    save_post, search_related_posts, count_posts, get_titles_for_recap,
    get_recent_posts, count_posts_on_date, remediate_stray_chars_in_db,
    sync_story_state_from_db,
)
from memory import load_json, save_json
from ai import generate_content, generate_json, review_content, find_stray_script_chars
from prompts import (
    FORMATS, build_generation_prompt, build_review_prompt, build_poll_prompt,
    build_scene_prompt, compose_image_prompt,
)
from telegram_bot import send_message, send_poll, send_admin_image_prompt, send_admin_message
from channels import broadcast_extra_channels, format_quiz_for_extra_channels
from poll_feedback import harvest_pending_polls, save_pending_poll
from topic_selection import (
    migrate_covered_topics, get_next_topic, remaining_topic_count,
    record_topic_coverage,
)
import campaigns
import audience_profile
import experiments
import analytics

MAX_REVIEW_ATTEMPTS = 2
ILLUSTRATED_PUN_CATEGORY = "Idioms"

INVENTED_IDIOM_TOPIC = {
    "topic": "Free-choice idiom",
    "level": "A2",
    "category": "Idioms",
}


def maybe_alert_low_topic_supply(memory):
    remaining = remaining_topic_count(memory)
    if remaining <= LOW_TOPIC_WARNING_THRESHOLD:
        send_admin_message(
            f"⚠️ فقط {remaining} موضوع تازه (هرگز تدریس‌نشده) توی data/topics.json باقی مونده. "
            f"بعدش سیستم خودش موضوعات قبلی رو با فرمت‌های جدید دوباره می‌آره، "
            f"ولی بهتره موضوعات مبتدی (A1–A2) بیشتری هم اضافه کنی."
        )


def resolve_today_format():
    post_count = count_posts(published_only=True)
    if post_count > 0 and post_count % RECAP_EVERY_N_POSTS == 0:
        return "progress_recap", True
    schedule = load_json(SCHEDULE_PATH, {})
    weekday_name = datetime.date.today().strftime("%A")
    return schedule.get(weekday_name, "micro_scene"), False


def generate_reviewed_text(memory, strategy, related, topic, format_name,
                            story=None, recap_titles=None, extra_note="",
                            campaign_note="", profile_note=""):
    def _draft(note=""):
        prompt = build_generation_prompt(
            memory, strategy, related, topic, format_name,
            extra_note=note, story=story, recap_titles=recap_titles,
            campaign_note=campaign_note, profile_note=profile_note,
        )
        return generate_content(prompt)

    def _needs_retry(text, review):
        return review.get("ok") is not True or bool(find_stray_script_chars(text))

    content = _draft(extra_note)
    review = review_content(build_review_prompt(content, format_name))
    attempts = 0
    while _needs_retry(content, review) and attempts < MAX_REVIEW_ATTEMPTS:
        stray = find_stray_script_chars(content)
        note = review.get("feedback", "") or ""
        if stray:
            note = (note + " " if note else "") + (
                "متن قبلی چند کاراکتر عجیب و نامربوط داشت (نه فارسی، نه انگلیسی، نه اموجی معمولی: "
                + " ".join(stray) + "). دوباره بنویس و فقط از حروف فارسی، انگلیسی، و اموجی معمولی استفاده کن."
            )
        content = _draft(note=(extra_note + " " + note).strip())
        review = review_content(build_review_prompt(content, format_name))
        attempts += 1

    stray = find_stray_script_chars(content)
    if stray:
        for ch in stray:
            content = content.replace(ch, "")
    return content


def _review_scene_sentence(sentence):
    stray = find_stray_script_chars(sentence)
    cleaned = sentence
    for ch in stray:
        cleaned = cleaned.replace(ch, "")
    return cleaned


def handle_poll_format(strategy, related, topic, format_name, recent_titles=None,
                        campaign_note="", profile_note="", variant_note="",
                        theme_category=None, experiment_id=None, variant_label=None):
    fmt = FORMATS[format_name]
    is_quiz = fmt["needs_poll"] == "quiz"
    prompt = build_poll_prompt(
        related, topic, format_name, recent_titles=recent_titles,
        campaign_note=campaign_note, profile_note=profile_note, variant_note=variant_note,
    )

    try:
        data = generate_json(prompt, strict=True)
    except Exception as exc:
        send_admin_message(
            f"⚠️ ساخت {fmt['label']} امروز شکست خورد (پاسخ مدل قابل‌تفسیر نبود یا خطای API داشت): {exc}\n"
            f"این دور پستی منتشر نشد؛ لازم نیست کاری بکنی، فقط برای اطلاع."
        )
        print(f"handle_poll_format: giving up for {format_name} —", exc)
        return None

    question = data.get("question", topic["topic"])
    options = data.get("options", [])[:10]
    if len(options) < 2:
        send_admin_message(
            f"⚠️ {fmt['label']} امروز کمتر از ۲ گزینه برگردوند — پست منتشر نشد."
        )
        return None

    correct_index = None
    if is_quiz:
        correct_index = data.get("correct_index")
        if not isinstance(correct_index, int) or not (0 <= correct_index < len(options)):
            send_admin_message(
                f"⚠️ کوییز امروز correct_index نامعتبر برگردوند ({correct_index!r}) — پست منتشر نشد."
            )
            return None
        result = send_poll(question, options, is_quiz=True,
                            correct_option_id=correct_index, explanation=data.get("explanation", ""))
    else:
        result = send_poll(question, options, is_quiz=False)

    quiz_text = format_quiz_for_extra_channels(
        question, options, is_quiz=is_quiz, explanation=data.get("explanation", "") or "",
        correct_index=correct_index,
    )
    # Eitaa/Bale get a text fallback, not a native poll (see channels.py) —
    # and, as of the platform-awareness fix, no ask to "comment your
    # answer" either, since neither platform's bot API exposes a comments
    # feature. Quiz fallbacks reveal the correct option inline instead;
    # vote fallbacks point to the Telegram version, where the real poll
    # is. We still capture the send result as delivery-health telemetry
    # (analytics.py), never as engagement, since neither platform reports
    # vote counts back to us.
    extra_results = broadcast_extra_channels(quiz_text)

    message_id = (result or {}).get("result", {}).get("message_id")
    if message_id is not None:
        save_pending_poll(
            message_id, question, is_quiz=is_quiz, correct_index=correct_index,
            theme_category=theme_category, experiment_id=experiment_id, variant_label=variant_label,
            extra_channel_results=extra_results,
        )

    return json.dumps(data, ensure_ascii=False)


def handle_image_format(memory, strategy, related, topic, format_name, story=None, extra_note="",
                         campaign_note="", profile_note=""):
    caption = generate_reviewed_text(memory, strategy, related, topic, format_name,
                                      story=story, extra_note=extra_note,
                                      campaign_note=campaign_note, profile_note=profile_note)

    scene_prompt = build_scene_prompt(topic["topic"])
    scene_sentence = _review_scene_sentence(generate_content(scene_prompt))
    image_prompt = compose_image_prompt(scene_sentence)

    admin_text = (
        f"📝 کپشن آماده برای «{topic['topic']}»:\n\n{caption}\n\n"
        f"— بعد از ساختن تصویر، این کپشن رو همراه عکس دستی توی کانال تلگرام بذار.\n"
        f"— همین کپشن + عکس رو توی ایتا و بله هم منتشر کن (این فرمت خودکار کراس‌پست نمی‌شه)."
    )
    send_admin_image_prompt(admin_text, label="کپشن")
    send_admin_image_prompt(image_prompt, label=topic["topic"])

    return f"[MANUAL — caption + image prompt sent to admin]\n{caption}\n---\n{image_prompt}"


def _select_topic(memory, format_name, theme_category=None):
    """Return (topic, extra_note, invented_idiom_mode). theme_category
    (campaigns.py) is only a soft preference, and only applies outside
    illustrated_pun — that format's category_filter is a hard requirement
    (Idioms only), not something a weekly theme should override."""
    extra_note = ""
    invented_idiom_mode = False

    if format_name == "illustrated_pun":
        topic = get_next_topic(memory, format_name, category_filter=ILLUSTRATED_PUN_CATEGORY)
        if topic is None:
            invented_idiom_mode = True
            topic = dict(INVENTED_IDIOM_TOPIC)
            extra_note = (
                "توی data/topics.json دیگه اصطلاح (Idiom) پوشش‌داده‌نشده‌ای باقی نمونده. "
                "به‌جاش یه اصطلاح ساده و رایج انگلیسی (سطح A1-A2) که فاصله‌ی واضحی بین معنی "
                "تحت‌اللفظی و معنی واقعی داره خودت انتخاب کن و همون رو موضوع این پست کن."
            )
    else:
        topic = get_next_topic(memory, format_name, theme_category=theme_category)

    return topic, extra_note, invented_idiom_mode


def main():
    harvest_pending_polls()

    fixed = remediate_stray_chars_in_db()
    if fixed:
        print("Remediated stray characters in posts:", fixed)

    today_str = str(datetime.date.today())
    posted_today = count_posts_on_date(today_str)
    if posted_today >= POSTS_PER_DAY:
        print(
            f"امروز ({today_str}) قبلاً {posted_today} پست از {POSTS_PER_DAY} پست مجاز روزانه "
            f"منتشر شده؛ این اجرا رد می‌شه."
        )
        return

    memory = load_json(MEMORY_PATH, {})
    migrate_covered_topics(memory)
    strategy = load_json(STRATEGY_PATH, {})
    story = load_json(STORY_PATH, {"characters": [], "last_installment": 0, "recent_summary": ""})

    synced = sync_story_state_from_db()
    if synced["last_installment"] > story.get("last_installment", 0):
        story.update(synced)
        save_json(STORY_PATH, story)

    # Weakness 5 (campaigns) / Weakness 1 (audience profile) context —
    # computed once per run, reused by whichever branch below actually
    # generates content.
    campaign_state = campaigns.get_or_start_week(memory)
    campaign_note = campaigns.campaign_context_block(campaign_state)
    profile_note = audience_profile.profile_context_block(strategy)

    format_name, recap_preempted = resolve_today_format()
    fmt = FORMATS[format_name]

    if recap_preempted:
        schedule = load_json(SCHEDULE_PATH, {})
        weekday = datetime.date.today().strftime("%A")
        displaced = schedule.get(weekday, "micro_scene")
        send_admin_message(
            f"ℹ️ امروز به‌جای «{FORMATS.get(displaced, {}).get('label', displaced)}» "
            f"پست مرور پیشرفت (هر {RECAP_EVERY_N_POSTS} پست) منتشر می‌شه."
        )

    if format_name == "progress_recap":
        recap_titles = get_titles_for_recap(limit=8)
        if not recap_titles:
            print("هنوز چیزی برای مرور پیشرفت ثبت نشده؛ این دور رد می‌شه.")
            return
        topic = {"topic": "مرور پیشرفت", "level": "-", "category": "Recap"}
        content = generate_reviewed_text(memory, strategy, [], topic, format_name,
                                          recap_titles=recap_titles,
                                          campaign_note=campaign_note, profile_note=profile_note)
        send_message(content)
        extra_results = broadcast_extra_channels(content)
        save_post(date=today_str, format_name=format_name,
                   category="Recap", level="-", title="Progress recap",
                   content=content, keywords="recap", status="published")
        campaigns.record_post(campaign_state, today_str, format_name, "Progress recap")
        analytics.record_text_post(format_name, "Progress recap", extra_channel_results=extra_results)
        print("پست مرور پیشرفت منتشر شد.")
        return

    if fmt["needs_poll"]:
        recent_titles = [row[0] for row in get_recent_posts(limit=7)]
        if not recent_titles:
            print("هنوز پستی برای ساختن کوییز/نظرسنجی از روش وجود نداره؛ این دور رد می‌شه.")
            return
        topic = {"topic": recent_titles[0], "level": "-", "category": "Review"}
        related = search_related_posts(topic["topic"])

        # Weakness 6 (sequential A/B testing) — quiz/vote_poll are the only
        # formats with a measurable outcome (a poll vote tally), so this is
        # the only place an experiment ever applies. See experiments.py for
        # why this is a sequential test, not a bandit or a user-level split.
        active_exp = experiments.get_active_experiment()
        variant_label, variant_note, experiment_id = None, "", None
        if active_exp:
            variant_label = experiments.assign_variant(active_exp)
            variant_note = experiments.variant_prompt_note(active_exp, variant_label)
            experiment_id = active_exp["id"]
            experiments.record_assignment(experiment_id, variant_label)

        content = handle_poll_format(
            strategy, related, topic, format_name,
            recent_titles=recent_titles if fmt["needs_poll"] == "quiz" else None,
            campaign_note=campaign_note, profile_note=profile_note, variant_note=variant_note,
            theme_category=campaign_state.get("theme_category"),
            experiment_id=experiment_id, variant_label=variant_label,
        )
        if content is None:
            return
        title = f"{fmt['label']}: {', '.join(recent_titles[:3])}"
        save_post(date=today_str, format_name=format_name,
                   category="Review", level="-", title=title,
                   content=content, keywords="review", status="published")
        campaigns.record_post(campaign_state, today_str, format_name, title)
        # No analytics.record_*() here on purpose — the vote tally doesn't
        # exist yet. poll_feedback.harvest_pending_polls() scores this once
        # the poll actually closes (usually the next run).
        print(f"پست منتشر شد ({format_name}).")
        return

    maybe_alert_low_topic_supply(memory)

    topic, extra_note, invented_idiom_mode = _select_topic(
        memory, format_name, theme_category=campaign_state.get("theme_category"),
    )
    if not topic:
        send_admin_message(
            "🔴 هیچ موضوعی در data/topics.json پیدا نشد — پستی منتشر نشد."
        )
        return

    related = search_related_posts(topic["topic"], category=topic.get("category"))

    if fmt["needs_image"]:
        content = handle_image_format(memory, strategy, related, topic, format_name,
                                       story=story, extra_note=extra_note,
                                       campaign_note=campaign_note, profile_note=profile_note)
        status = "pending_manual"
        # illustrated_pun's caption+image are handed to the admin for manual
        # posting everywhere (see handle_image_format) — nothing was
        # actually broadcast to Eitaa/Bale here, so there's no delivery
        # result to record.
        extra_results = None
    else:
        content = generate_reviewed_text(memory, strategy, related, topic, format_name,
                                          story=story, extra_note=extra_note,
                                          campaign_note=campaign_note, profile_note=profile_note)
        send_message(content)
        extra_results = broadcast_extra_channels(content)
        status = "published"

        if format_name == "story_installment":
            story["last_installment"] = story.get("last_installment", 0) + 1
            story["recent_summary"] = content[:200]
            save_json(STORY_PATH, story)

    campaigns.record_post(campaign_state, today_str, format_name, topic["topic"])
    analytics.record_text_post(format_name, topic["topic"], extra_channel_results=extra_results)

    save_post(
        date=today_str,
        format_name=format_name,
        category=topic["category"],
        level=topic["level"],
        title=topic["topic"],
        content=content,
        keywords=topic["topic"],
        status=status,
    )

    if status == "published" and not invented_idiom_mode:
        record_topic_coverage(memory, topic["topic"], format_name, today_str)
        save_json(MEMORY_PATH, memory)

    print(f"پست منتشر شد ({format_name}): {topic['topic']}")


if __name__ == "__main__":
    main()
