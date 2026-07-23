import datetime
import json

from config import (
    MEMORY_PATH, STRATEGY_PATH, TOPICS_PATH, SCHEDULE_PATH, STORY_PATH,
    RECAP_EVERY_N_POSTS,
)
from database import (
    save_post, search_related_posts, count_posts, get_titles_for_recap, get_recent_posts,
)
from memory import load_json, save_json
from ai import generate_content, generate_json, review_content, find_stray_script_chars
from prompts import (
    FORMATS, build_generation_prompt, build_review_prompt, build_poll_prompt,
    build_scene_prompt, compose_image_prompt,
)
from telegram_bot import send_message, send_poll, send_admin_image_prompt

MAX_REVIEW_ATTEMPTS = 2


def get_next_topic(memory):
    topics = load_json(TOPICS_PATH, [])
    covered = set(memory.get("covered_topics", []))
    for t in topics:
        if t["topic"] not in covered:
            return t
    return None


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
                            story=None, recap_titles=None):
    """Generate → review → regenerate-with-feedback loop, shared by every
    text-post format (micro_scene, illustrated_pun caption, story_installment,
    spot_mistake, vocab_spotlight, progress_recap)."""
    def _draft(extra_note=""):
        prompt = build_generation_prompt(
            memory, strategy, related, topic, format_name,
            extra_note=extra_note, story=story, recap_titles=recap_titles,
        )
        return generate_content(prompt)

    def _needs_retry(text, review):
        return not review.get("ok", True) or bool(find_stray_script_chars(text))

    content = _draft()
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
        content = _draft(extra_note=note)
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

    fallback = (
        {"question": f"{topic['topic']} رو چطور به کار می‌بری؟", "options": ["الف", "ب"],
         "correct_index": 0, "explanation": ""}
        if is_quiz else
        {"question": f"نظرت درباره‌ی {topic['topic']} چیه؟", "options": ["الف", "ب"]}
    )
    data = generate_json(prompt, fallback=fallback)

    question = data.get("question", topic["topic"])
    options = data.get("options", ["الف", "ب"])[:10]
    if len(options) < 2:
        options = options + ["گزینه‌ی دیگه"]

    if is_quiz:
        correct_index = data.get("correct_index", 0)
        if not isinstance(correct_index, int) or not (0 <= correct_index < len(options)):
            correct_index = 0
        send_poll(question, options, is_quiz=True,
                  correct_option_id=correct_index, explanation=data.get("explanation", ""))
    else:
        send_poll(question, options, is_quiz=False)

    return json.dumps(data, ensure_ascii=False)


def handle_image_format(memory, strategy, related, topic, format_name, story=None):
    """Formats that need an illustration are NOT auto-posted to the channel —
    there's no image generator connected, so posting a photo-less "illustrated"
    post would look broken. Instead, the finished caption AND the image prompt
    are sent to the admin so they can generate the image and post both by hand."""
    caption = generate_reviewed_text(memory, strategy, related, topic, format_name, story=story)

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
        save_post(date=str(datetime.date.today()), format_name=format_name,
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
        save_post(date=str(datetime.date.today()), format_name=format_name,
                   category="Review", level="-", title=f"{fmt['label']}: {', '.join(recent_titles[:3])}",
                   content=content, keywords="review", status="published")
        print(f"پست منتشر شد ({format_name}).")
        return

    topic = get_next_topic(memory)
    if not topic:
        print("تمام موضوعات data/topics.json پوشش داده شده. لطفاً موضوعات مبتدی (A1–A2) بیشتری اضافه کنید.")
        return

    related = search_related_posts(topic["topic"])

    if fmt["needs_image"]:
        content = handle_image_format(memory, strategy, related, topic, format_name, story=story)
        status = "pending_manual"
    else:
        content = generate_reviewed_text(memory, strategy, related, topic, format_name, story=story)
        send_message(content)
        status = "published"

        if format_name == "story_installment":
            story["last_installment"] = story.get("last_installment", 0) + 1
            story["recent_summary"] = content[:200]
            save_json(STORY_PATH, story)

    save_post(
        date=str(datetime.date.today()),
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