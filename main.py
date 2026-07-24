import datetime
import json

from config import (
    MEMORY_PATH, STRATEGY_PATH, TOPICS_PATH, SCHEDULE_PATH, STORY_PATH,
    RECAP_EVERY_N_POSTS, LOW_TOPIC_WARNING_THRESHOLD,
)
from database import (
    save_post, search_related_posts, count_posts, get_titles_for_recap,
    get_recent_posts, has_post_on_date,
)
from memory import load_json, save_json
from ai import generate_content, generate_json, review_content, find_stray_script_chars
from prompts import (
    FORMATS, build_generation_prompt, build_review_prompt, build_poll_prompt,
    build_scene_prompt, compose_image_prompt,
)
from telegram_bot import send_message, send_poll, send_admin_image_prompt, send_admin_message
from channels import broadcast_extra_channels
from poll_feedback import harvest_pending_polls, save_pending_poll

MAX_REVIEW_ATTEMPTS = 2

# Idioms only work for illustrated_pun (its own prompt guidance says so) but
# get_next_topic() used to hand out whatever the next uncovered topic was,
# regardless of category — see Audit #3.
ILLUSTRATED_PUN_CATEGORY = "Idioms"


def get_next_topic(memory, category_filter=None):
    """Return the next not-yet-covered topic. If category_filter is given,
    restrict to that category and return None if the pool for that category
    is empty (the caller decides the fallback — see main())."""
    topics = load_json(TOPICS_PATH, [])
    covered = set(memory.get("covered_topics", []))
    candidates = [t for t in topics if t["topic"] not in covered]
    if category_filter:
        candidates = [t for t in candidates if t["category"] == category_filter]
    return candidates[0] if candidates else None


def remaining_topic_count(memory):
    topics = load_json(TOPICS_PATH, [])
    covered = set(memory.get("covered_topics", []))
    return len([t for t in topics if t["topic"] not in covered])


def maybe_alert_low_topic_supply(memory):
    """Post count is a metric to monitor, not a one-time top-up — once the
    uncovered-topic pool gets low, alert the admin instead of only printing
    to a log nobody reads until posts silently stop (Audit #1)."""
    remaining = remaining_topic_count(memory)
    if remaining <= LOW_TOPIC_WARNING_THRESHOLD:
        send_admin_message(
            f"⚠️ فقط {remaining} موضوع پوشش‌داده‌نشده توی data/topics.json باقی مونده. "
            f"لطفاً به‌زودی موضوعات مبتدی (A1–A2) بیشتری اضافه کن، وگرنه کانال روزهایی که "
            f"باید موضوع جدید معرفی کنه ساکت می‌مونه."
        )


def resolve_today_format():
    """Recap takes priority over the day's scheduled format whenever the post
    count hits the threshold — this is what makes spaced repetition automatic
    instead of something that only happens if a human remembers to do it."""
    if count_posts() > 0 and count_posts() % RECAP_EVERY_N_POSTS == 0:
        return "progress_recap"
    schedule = load_json(SCHEDULE_PATH, {})
    weekday_name = datetime.date.today().strftime("%A")  # e.g. "Monday"
    return schedule.get(weekday_name, "micro_scene")


def generate_reviewed_text(memory, strategy, related, topic, format_name,
                            story=None, recap_titles=None, extra_note=""):
    """Generate → review → regenerate-with-feedback loop, shared by every
    text-post format (micro_scene, illustrated_pun caption, story_installment,
    spot_mistake, vocab_spotlight, progress_recap)."""
    def _draft(note=""):
        prompt = build_generation_prompt(
            memory, strategy, related, topic, format_name,
            extra_note=note, story=story, recap_titles=recap_titles,
        )
        return generate_content(prompt)

    def _needs_retry(text, review):
        return not review.get("ok", True) or bool(find_stray_script_chars(text))

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

    # Last resort: if retries are exhausted and stray characters are still
    # present, strip them rather than publish a glitched post.
    stray = find_stray_script_chars(content)
    if stray:
        for ch in stray:
            content = content.replace(ch, "")
    return content


def handle_poll_format(strategy, related, topic, format_name, recent_titles=None):
    fmt = FORMATS[format_name]
    is_quiz = fmt["needs_poll"] == "quiz"
    prompt = build_poll_prompt(related, topic, format_name, recent_titles=recent_titles)

    # Strict: a JSON parse failure here should surface as an error the admin
    # can see, not silently publish a generic placeholder quiz/poll (Audit
    # #4 — this used to fall back to a fixed "الف/ب" question with no
    # signal that anything went wrong).
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
        options = (options + ["گزینه‌ی الف", "گزینه‌ی ب"])[:2]

    correct_index = None
    if is_quiz:
        correct_index = data.get("correct_index", 0)
        if not isinstance(correct_index, int) or not (0 <= correct_index < len(options)):
            correct_index = 0
        result = send_poll(question, options, is_quiz=True,
                            correct_option_id=correct_index, explanation=data.get("explanation", ""))
    else:
        result = send_poll(question, options, is_quiz=False)

    message_id = (result or {}).get("result", {}).get("message_id")
    if message_id is not None:
        save_pending_poll(message_id, question, is_quiz=is_quiz, correct_index=correct_index)

    return json.dumps(data, ensure_ascii=False)


def handle_image_format(memory, strategy, related, topic, format_name, story=None, extra_note=""):
    """Formats that need an illustration are NOT auto-posted to the channel —
    there's no image generator connected, so posting a photo-less "illustrated"
    post would look broken. Instead, the finished caption AND the image prompt
    are sent to the admin so they can generate the image and post both by hand."""
    caption = generate_reviewed_text(memory, strategy, related, topic, format_name,
                                      story=story, extra_note=extra_note)

    scene_prompt = build_scene_prompt(topic["topic"])
    scene_sentence = generate_content(scene_prompt)
    image_prompt = compose_image_prompt(scene_sentence)

    admin_text = (
        f"📝 کپشن آماده برای «{topic['topic']}»:\n\n{caption}\n\n"
        f"— بعد از ساختن تصویر، این کپشن رو همراه عکس دستی توی کانال بذار."
    )
    send_admin_image_prompt(admin_text, label="کپشن")
    send_admin_image_prompt(image_prompt, label=topic["topic"])

    return f"[MANUAL — caption + image prompt sent to admin]\n{caption}\n---\n{image_prompt}"


def main():
    # Close out and score any poll/quiz sent on a prior run before doing
    # anything else, so feedback.json reflects real audience data instead
    # of staying permanently empty (Audit #5).
    harvest_pending_polls()

    # Same-day duplicate-run guard: nothing previously stopped two triggers
    # (workflow_dispatch + cron firing, or two manual runs) on the same day
    # from both publishing and both consuming a topic — this already
    # happened once (two story_installment posts on 2026-07-23, see Audit
    # #2). Applies to every format, including recap/quiz, since a duplicate
    # recap or quiz is just as wasteful as a duplicate topic post.
    today_str = str(datetime.date.today())
    if has_post_on_date(today_str):
        print(f"یک پست برای {today_str} از قبل ثبت شده؛ این اجرا برای جلوگیری از تکرار رد می‌شه.")
        return

    memory = load_json(MEMORY_PATH, {})
    strategy = load_json(STRATEGY_PATH, {})
    story = load_json(STORY_PATH, {"characters": [], "last_installment": 0, "recent_summary": ""})

    format_name = resolve_today_format()
    fmt = FORMATS[format_name]

    if format_name == "progress_recap":
        recap_titles = get_titles_for_recap(limit=8)
        if not recap_titles:
            print("هنوز چیزی برای مرور پیشرفت ثبت نشده؛ این دور رد می‌شه.")
            return
        topic = {"topic": "مرور پیشرفت", "level": "-", "category": "Recap"}
        content = generate_reviewed_text(memory, strategy, [], topic, format_name,
                                          recap_titles=recap_titles)
        send_message(content)
        broadcast_extra_channels(content)
        save_post(date=today_str, format_name=format_name,
                   category="Recap", level="-", title="Progress recap",
                   content=content, keywords="recap", status="published")
        print("پست مرور پیشرفت منتشر شد.")
        return

    if fmt["needs_poll"]:
        # Quiz/vote days recycle what was already taught — they don't consume
        # a new curriculum topic, since the whole point is spaced repetition,
        # not introducing something new.
        recent_titles = [row[0] for row in get_recent_posts(limit=7)]
        if not recent_titles:
            print("هنوز پستی برای ساختن کوییز/نظرسنجی از روش وجود نداره؛ این دور رد می‌شه.")
            return
        topic = {"topic": recent_titles[0], "level": "-", "category": "Review"}
        related = search_related_posts(topic["topic"])
        content = handle_poll_format(
            strategy, related, topic, format_name,
            recent_titles=recent_titles if fmt["needs_poll"] == "quiz" else None,
        )
        if content is None:
            # handle_poll_format already alerted the admin; don't record a
            # phantom post for a day nothing was actually published.
            return
        save_post(date=today_str, format_name=format_name,
                   category="Review", level="-", title=f"{fmt['label']}: {', '.join(recent_titles[:3])}",
                   content=content, keywords="review", status="published")
        print(f"پست منتشر شد ({format_name}).")
        return

    maybe_alert_low_topic_supply(memory)

    extra_note = ""
    if format_name == "illustrated_pun":
        # This format only works for idioms — hand it an idiom-category
        # topic specifically instead of whatever's next in line (Audit #3).
        topic = get_next_topic(memory, category_filter=ILLUSTRATED_PUN_CATEGORY)
        if topic is None:
            # Idiom pool exhausted for now: fall back to a generic topic and
            # tell the model to invent a suitable idiom itself, rather than
            # forcing a "Past simple tense" idiom joke that shouldn't exist.
            topic = get_next_topic(memory)
            extra_note = (
                "توی data/topics.json دیگه اصطلاح (Idiom) پوشش‌داده‌نشده‌ای باقی نمونده. "
                "به‌جاش یه اصطلاح ساده و رایج انگلیسی (سطح A1-A2) که فاصله‌ی واضحی بین معنی "
                "تحت‌اللفظی و معنی واقعی داره خودت انتخاب کن و همون رو موضوع این پست کن — "
                "لازم نیست به موضوع پیشنهادی زیر پایبند بمونی."
            )
    else:
        topic = get_next_topic(memory)

    if not topic:
        print("تمام موضوعات data/topics.json پوشش داده شده. لطفاً موضوعات مبتدی (A1–A2) بیشتری اضافه کنید.")
        send_admin_message(
            "🔴 تمام موضوعات data/topics.json پوشش داده شده — از امروز پست موضوع‌محور جدیدی منتشر نمی‌شه "
            "تا وقتی موضوعات بیشتری اضافه کنی."
        )
        return

    related = search_related_posts(topic["topic"], category=topic["category"])

    if fmt["needs_image"]:
        content = handle_image_format(memory, strategy, related, topic, format_name,
                                       story=story, extra_note=extra_note)
        status = "pending_manual"
    else:
        content = generate_reviewed_text(memory, strategy, related, topic, format_name,
                                          story=story, extra_note=extra_note)
        send_message(content)
        broadcast_extra_channels(content)
        status = "published"

        if format_name == "story_installment":
            story["last_installment"] = story.get("last_installment", 0) + 1
            story["recent_summary"] = content[:200]
            save_json(STORY_PATH, story)

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

    memory.setdefault("covered_topics", []).append(topic["topic"])
    save_json(MEMORY_PATH, memory)
    print(f"پست منتشر شد ({format_name}): {topic['topic']}")


if __name__ == "__main__":
    main()
