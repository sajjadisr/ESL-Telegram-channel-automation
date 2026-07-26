import datetime
import json

from config import (
    MEMORY_PATH, STRATEGY_PATH, SCHEDULE_PATH, STORY_PATH,
    RECAP_EVERY_N_POSTS, LOW_TOPIC_WARNING_THRESHOLD, AUTO_GENERATE_TOPIC_COUNT,
    POSTS_PER_DAY, FRESH_TOPICS_PER_DAY,
)
from database import (
    save_post, search_related_posts, count_posts, get_titles_for_recap,
    get_recent_posts, count_posts_on_date, remediate_stray_chars_in_db,
    sync_story_state_from_db,
)
from memory import load_json, save_json
from ai import (
    generate_content, generate_json, review_content, find_stray_script_chars,
    generate_image, GeminiAuthError, AllTextProvidersFailedError,
)
from prompts import (
    FORMATS, build_generation_prompt, build_review_prompt, build_poll_prompt,
    build_scene_prompt, compose_image_prompt,
)
from telegram_bot import (
    send_message, send_poll, send_admin_image_prompt, send_admin_message, send_photo, send_document,
)
from channels import broadcast_extra_channels, broadcast_extra_channels_photo, format_quiz_for_extra_channels
from poll_feedback import harvest_pending_polls, save_pending_poll
from topic_selection import (
    migrate_covered_topics, get_next_topic, get_due_review_topic,
    remaining_topic_count, record_topic_coverage,
)
from topic_generation import generate_and_append_topics
import campaigns
import audience_profile
import experiments
import analytics

MAX_REVIEW_ATTEMPTS = 2
ILLUSTRATED_PUN_CATEGORY = "Idioms"

# Fallback format for "extra" daily slots (beyond FRESH_TOPICS_PER_DAY) on a
# day whose scheduled format needs a poll or a manual image — those formats
# stay capped at their normal weekday cadence (see main()'s slot logic);
# repeating them within the same day is a near-duplicate quiz or a second
# manual-posting task, neither of which is what going to 3x/day was for.
DEFAULT_EXTRA_SLOT_FORMAT = "micro_scene"

INVENTED_IDIOM_TOPIC = {
    "topic": "Free-choice idiom",
    "level": "A2",
    "category": "Idioms",
}


def maybe_alert_low_topic_supply(memory):
    remaining = remaining_topic_count(memory)
    if remaining <= LOW_TOPIC_WARNING_THRESHOLD:
        added = []
        try:
            added = generate_and_append_topics(AUTO_GENERATE_TOPIC_COUNT)
        except Exception as exc:
            print("maybe_alert_low_topic_supply: auto-generation failed:", exc)
        if added:
            send_admin_message(
                f"ℹ️ موضوعات تازه داشت کم می‌شد ({remaining} مونده بود)، سیستم خودش "
                f"{len(added)} موضوع جدید (سطح A1–A2) به data/topics.json اضافه کرد. "
                f"لازم نیست کاری بکنی — فقط برای اطلاع."
            )
        else:
            send_admin_message(
                f"⚠️ فقط {remaining} موضوع تازه (هرگز تدریس‌نشده) توی data/topics.json باقی مونده، "
                f"و تلاش خودکار برای اضافه‌کردن موضوع جدید این‌بار جواب نداد. یه نگاه بنداز — "
                f"شاید لازم باشه دستی چندتا موضوع مبتدی (A1–A2) اضافه کنی."
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
    review = review_content(build_review_prompt(content, format_name, topic_text=topic.get("topic")))
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
        review = review_content(build_review_prompt(content, format_name, topic_text=topic.get("topic")))
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
    """Auto-generates and posts the image (Audit: this used to hand the
    finished prompt to the admin to paste into an image tool by hand, every
    single run) — to Telegram, Eitaa, and Bale. Falls back one rung at a
    time (see below) rather than jumping straight to the full manual
    hand-off the moment any one step wobbles, so a bad run never silently
    loses the post — worst case still costs the admin the five minutes it
    always used to cost.

    Returns (content, status, extra_channel_results) — same shape the
    caller already expects from the non-image branch, so a successful
    auto-post now correctly counts as status="published" instead of always
    being "pending_manual" (see the comment on record_topic_coverage below
    for why that distinction used to not matter there, but does matter for
    get_recent_posts/count_posts/recap eligibility, which all filter on
    status='published')."""
    caption = generate_reviewed_text(memory, strategy, related, topic, format_name,
                                      story=story, extra_note=extra_note,
                                      campaign_note=campaign_note, profile_note=profile_note)

    scene_prompt = build_scene_prompt(topic["topic"])
    scene_sentence = _review_scene_sentence(generate_content(scene_prompt))
    image_prompt = compose_image_prompt(scene_sentence)

    image_bytes = None
    try:
        # generate_image already retries per-model and falls back across
        # two model tiers internally (ai.py) — this try/except is just a
        # last-resort net for anything unforeseen, same spirit as main()'s
        # own top-level catch-all.
        image_bytes = generate_image(image_prompt)
    except Exception as exc:  # noqa: BLE001 — a broken image call must not crash the run
        print("handle_image_format: generate_image raised unexpectedly, falling back to manual:", exc)

    if image_bytes is not None:
        try:
            send_photo(image_bytes, caption)
        except Exception as exc:  # noqa: BLE001 — a Telegram send failure must not crash the run
            print("handle_image_format: send_photo failed, trying sendDocument fallback:", exc)
            try:
                send_document(image_bytes, caption)
            except Exception as exc2:  # noqa: BLE001
                print("handle_image_format: send_document fallback also failed, falling back to manual:", exc2)
                image_bytes = None

    if image_bytes is not None:
        # Auto cross-post to Eitaa/Bale too. Each platform independently
        # falls back to a text-only caption if its own photo upload fails
        # (see _send_platform_photo in channels.py) — Eitaa's endpoint in
        # particular is a best-effort guess (no precise public docs), so
        # this is what keeps a wrong guess there from costing the post.
        extra_results = broadcast_extra_channels_photo(image_bytes, caption)
        return (
            f"[AUTO — image posted to Telegram + Eitaa/Bale]\n{caption}\n---\n{image_prompt}",
            "published",
            extra_results,
        )

    admin_text = (
        f"📝 کپشن آماده برای «{topic['topic']}»:\n\n{caption}\n\n"
        f"— تولید یا انتشار خودکار عکس این‌بار جواب نداد، پس این‌بار رو دستی انجام بده: "
        f"بعد از ساختن تصویر، این کپشن رو همراه عکس دستی توی کانال تلگرام بذار.\n"
        f"— همین کپشن + عکس رو توی ایتا و بله هم منتشر کن (این‌بار خودکار کراس‌پست نشد)."
    )
    send_admin_image_prompt(admin_text, label="کپشن")
    send_admin_image_prompt(image_prompt, label=topic["topic"])

    return (
        f"[MANUAL — auto image generation/delivery failed, caption + image prompt sent to admin]\n"
        f"{caption}\n---\n{image_prompt}",
        "pending_manual",
        None,
    )


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
    slot_number = posted_today + 1  # 1-indexed: which run of today's POSTS_PER_DAY this is

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

    # Only the day's FIRST slot keeps the raw weekday-scheduled format —
    # that's what preserves "quiz day" / "idiom day" / etc. "Extra" slots
    # (slot_number > FRESH_TOPICS_PER_DAY) exist because of the move to
    # POSTS_PER_DAY > 1, and are handled differently below: they never
    # repeat a needs_poll/needs_image format within the same day (Audit:
    # that produced 3 near-duplicate quiz posts, or 3 separate manual-
    # image tasks, on days scheduled for those formats), and they check
    # for a due spaced-repetition review (topic_selection.get_due_review_
    # topic — config.REVIEW_INTERVALS_DAYS) before falling back to fresh
    # material. This is also the load-bearing balance for the review
    # scheduler: config.REVIEW_INTERVALS_DAYS is sized so that
    # FRESH_TOPICS_PER_DAY fresh topics/day don't generate more review
    # demand than (POSTS_PER_DAY - FRESH_TOPICS_PER_DAY) slots/day can
    # serve — see the comment on REVIEW_INTERVALS_DAYS in config.py before
    # changing either number.
    review_topic, review_stage, review_last_format = (None, None, None)
    if slot_number > FRESH_TOPICS_PER_DAY:
        if fmt["needs_poll"] or fmt["needs_image"]:
            format_name = DEFAULT_EXTRA_SLOT_FORMAT
            fmt = FORMATS[format_name]
        review_topic, review_stage, review_last_format = get_due_review_topic(memory)
        if review_topic:
            format_name = "vocab_spotlight" if review_last_format == "spot_mistake" else "spot_mistake"
            fmt = FORMATS[format_name]

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

    if review_topic:
        topic = review_topic
        invented_idiom_mode = False
        ordinal = {0: "بار اول", 1: "بار دوم", 2: "بار سوم", 3: "بار چهارم"}.get(review_stage, "چند بارِ قبل")
        extra_note = (
            f"این یه پست «مرور»ه، نه معرفی یه نکته‌ی کاملاً جدید — این نکته قبلاً آموزش داده شده "
            f"(این {ordinal} مرورشه)، الان هدف اینه که دوباره و این بار محکم‌تر توی ذهن بمونه. "
            f"لحنش «یادته؟ بیا یه بار دیگه با یه مثال/زاویه‌ی تازه ببینیمش» باشه، نه معرفی از صفر."
        )
    else:
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
        # handle_image_format now auto-generates and posts the image itself
        # (falling back to the old manual admin hand-off only if that
        # fails), so status/extra_results come from what actually happened
        # this run rather than being hardcoded to "pending_manual"/None.
        content, status, extra_results = handle_image_format(
            memory, strategy, related, topic, format_name,
            story=story, extra_note=extra_note,
            campaign_note=campaign_note, profile_note=profile_note,
        )
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

    # Was `if status == "published" and not invented_idiom_mode:` — that
    # silently excluded illustrated_pun forever, since it always sets
    # status="pending_manual" (handed to the admin for manual posting) and
    # so never satisfied "== published". The topic was never marked
    # covered, so get_next_topic() kept returning the exact same idiom on
    # every single illustrated_pun run (confirmed: topics.json's first
    # Idioms entry, "Break the ice", forever). Coverage should track "we
    # picked this topic and generated content for it", not "it got posted
    # automatically" — status is irrelevant here.
    if not invented_idiom_mode:
        record_topic_coverage(memory, topic["topic"], format_name, today_str)
        save_json(MEMORY_PATH, memory)

    print(f"پست منتشر شد ({format_name}): {topic['topic']}")


if __name__ == "__main__":
    try:
        main()
    except AllTextProvidersFailedError as exc:
        # Gemini AND the free Groq fallback (ai._call_groq) both failed (or
        # Groq isn't configured at all) — genuinely no working text model
        # right now, not just "Gemini has a bad credential" (GeminiAuthError,
        # caught below, is now rare: generate_content/generate_content_smart
        # already catch it internally and try Groq before this ever raises).
        try:
            send_admin_message(
                "🔴 اجرای امروز شکست خورد: نه Gemini جواب داد، نه fallback رایگان Groq.\n\n"
                f"{exc}\n\n"
                "برای رفع:\n"
                "۱) توی Google AI Studio پیشوند کلید Gemini رو چک کن — اگر با AQ. شروع "
                "میشه (به‌جای AIza)، احتمالاً همون مشکل قدیمیه.\n"
                "۲) اگه سکرت GROQ_API_KEY هنوز تنظیم نشده، یه کلید رایگان (بدون نیاز به "
                "کارت بانکی) از console.groq.com بگیر و به‌عنوان سکرت GitHub اضافه‌ش کن — "
                "پایپ‌لاین خودکار روش fallback می‌کنه تا Gemini درست بشه.\n"
                "۳) اگه GROQ_API_KEY از قبل تنظیم شده، لاگ اجرا رو توی تب Actions چک کن — "
                "احتمالاً Groq هم موقتاً quota یا خطای شبکه داشته."
            )
        except Exception as alert_exc:
            print("Also failed to send the admin failure alert:", alert_exc)
        raise
    except GeminiAuthError as exc:
        # Should be rare in practice now — generate_content/generate_content_smart
        # catch this internally and try the Groq fallback before ever
        # re-raising as AllTextProvidersFailedError (handled above). Kept as
        # a defensive net in case some future code path calls the Gemini
        # client directly without going through those two functions.
        try:
            send_admin_message(
                "🔴 اجرای امروز شکست خورد: خطای احراز هویت Gemini (نه quota، نه شبکه).\n\n"
                f"{exc}\n\n"
                "این معمولاً یعنی گوگل کلید رو به فرمت جدید «AQ.» تغییر داده (به‌جای «AIza»)، "
                "و اون فرمت جدید فعلاً توسط API رد میشه — حتی از طریق SDK رسمی.\n\n"
                "برای رفع:\n"
                "۱) توی Google AI Studio پیشوند کلید رو چک کن — اگر با AQ. شروع میشه، "
                "همینه.\n"
                "۲) یه کلید جدید بساز و سکرت GEMINI_API_KEY رو توی گیت‌هاب آپدیت کن (بعضی "
                "وقتا کلید جدید بازم AIza میده).\n"
                "۳) اگه یه اکانت گوگل جداگانه داری، کلیدش رو به‌عنوان سکرت جدید "
                "GEMINI_API_KEY_BACKUP اضافه کن — پایپ‌لاین خودکار روش fallback می‌کنه."
            )
        except Exception as alert_exc:
            print("Also failed to send the admin failure alert:", alert_exc)
        raise
    except Exception as exc:
        # Last-resort net: ai.py already retries transient errors 3x before
        # raising, so anything reaching here is a real failure (quota
        # exhausted, a response shape change, a code bug, etc — auth errors
        # are handled separately above). Without this, the run just crashes
        # with a traceback GitHub Actions shows nobody unless they're
        # actively watching the Actions tab — see send_admin_message's own
        # fallback (prints to the log) if TELEGRAM_ADMIN_CHAT_ID isn't set.
        # Re-raised after, so the workflow run still correctly shows as
        # failed either way.
        try:
            send_admin_message(
                f"🔴 اجرای امروز کلاً با خطا شکست خورد و هیچ پستی منتشر نشد: {exc}\n"
                f"این با هشدارهای معمولی (مثل کمبود موضوع) فرق داره — این یعنی خودِ پایپ‌لاین "
                f"مشکل داره (مثلاً quota، یا یه خطای غیرمنتظره). لاگ اجرا رو توی "
                f"تب Actions گیت‌هاب چک کن."
            )
        except Exception as alert_exc:
            print("Also failed to send the admin failure alert:", alert_exc)
        raise