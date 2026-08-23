import json

import clock

from config import (
    MEMORY_PATH, STRATEGY_PATH, SCHEDULE_PATH,
    RECAP_EVERY_N_POSTS, LOW_TOPIC_WARNING_THRESHOLD, AUTO_GENERATE_TOPIC_COUNT,
    POSTS_PER_DAY, FRESH_TOPICS_PER_DAY, GEMINI_REVIEW_DAILY_FREE_QUOTA,
)
from database import (
    save_post, search_related_posts, context_posts_for_generation, count_posts,
    get_titles_for_recap, get_recent_posts, count_posts_on_date, remediate_stray_chars_in_db,
    get_post_ids_for_story,
)
from memory import load_json, save_json
from ai import (
    generate_content, generate_json, review_content, find_stray_script_chars,
    generate_image, GeminiAuthError, AllTextProvidersFailedError, get_quota_snapshot,
)
from prompts import (
    FORMATS, build_generation_prompt, build_review_prompt, build_poll_prompt,
    build_scene_prompt, compose_image_prompt, build_recap_title_prompt,
)
import telegram_bot
from telegram_bot import (
    send_message, send_poll, send_admin_image_prompt, send_admin_message, send_photo, send_document,
    send_voice,
)
from channels import broadcast_extra_channels, broadcast_extra_channels_photo, format_quiz_for_extra_channels
from poll_feedback import harvest_pending_polls, save_pending_poll
from topic_selection import (
    migrate_covered_topics, get_next_topic, get_due_review_topic,
    remaining_topic_count, record_topic_coverage, pending_vocab_spotlight_callback,
)
from topic_generation import generate_and_append_topics
from text_utils import escape_html
import campaigns
import audience_profile
import experiments
import analytics
import reader
import news
import recap_card
import embeddings
import engagement_harvest
import voice_note

MAX_REVIEW_ATTEMPTS = 2

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


TOPIC_SUPPLY_ALERTED_KEY = "topic_supply_alerted"
STORY_SUPPLY_ALERTED_KEY = "story_supply_alerted"
QUOTA_ALERT_DATE_KEY = "quota_pressure_alert_date"


def maybe_alert_low_topic_supply(memory):
    """Bug fix (#79): this used to re-send the "still low" admin alert on
    every single qualifying run for as long as the underlying problem
    persisted (e.g. auto-generated candidates kept colliding with
    existing topics via topic_generation._is_duplicate) — unlike
    news.health_alert_needed's deliberate one-alert-per-streak design
    just below. Now mirrors that same pattern: alerts once per low-supply
    episode, then stays quiet (still retrying generation each run, since
    each attempt is an independent roll of the dice and might succeed
    even after a prior one didn't) until supply actually recovers, at
    which point it's ready to alert again if it ever dips a second time.
    """
    remaining = remaining_topic_count(memory)
    if remaining > LOW_TOPIC_WARNING_THRESHOLD:
        memory[TOPIC_SUPPLY_ALERTED_KEY] = False  # recovered — rearm for the next time
        return
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
        return
    if not memory.get(TOPIC_SUPPLY_ALERTED_KEY, False):
        send_admin_message(
            f"⚠️ فقط {remaining} موضوع تازه (هرگز تدریس‌نشده) توی data/topics.json باقی مونده، "
            f"و تلاش خودکار برای اضافه‌کردن موضوع جدید این‌بار جواب نداد. یه نگاه بنداز — "
            f"شاید لازم باشه دستی چندتا موضوع مبتدی (A1–A2) اضافه کنی."
        )
        memory[TOPIC_SUPPLY_ALERTED_KEY] = True


def maybe_alert_low_story_supply(memory):
    """Mirrors maybe_alert_low_topic_supply, but for the graded-reader
    library — no auto-generation here (a good story needs real curation,
    not a one-line prompt), so this is alert-only.

    Bug fix (#80): this had NO alerted-flag at all (unlike
    maybe_alert_low_topic_supply's partial version of this same fix, or
    news.health_alert_needed's original). Since there's no auto-recovery
    path here, an unresolved low supply used to re-send the identical
    alert on every single qualifying run — potentially for weeks, until a
    human manually curates and adds new stories. Now alerts once per
    episode, like its two siblings."""
    if not reader.low_supply_warning_needed(memory):
        memory[STORY_SUPPLY_ALERTED_KEY] = False  # recovered — rearm for the next time
        return
    if memory.get(STORY_SUPPLY_ALERTED_KEY, False):
        return
    remaining = reader.remaining_untouched_stories(memory)
    send_admin_message(
        f"⚠️ فقط {remaining} داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. "
        f"وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — "
        f"یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن."
    )
    memory[STORY_SUPPLY_ALERTED_KEY] = True


def maybe_alert_news_health(memory):
    """Mirrors maybe_alert_low_story_supply, but for news.py's feed health.
    fetch_news_item() degrading to None on any single run is expected and
    silent by design (a feed hiccup shouldn't page anyone) — this only
    fires once consecutive empty attempts cross config.NEWS_FAILURE_ALERT_
    THRESHOLD, which is what a *permanent* break (BBC retiring/renaming a
    feed URL, the domain getting blocked, etc.) looks like from here.
    news.health_alert_needed() marks the streak as alerted as a side
    effect, so this won't re-fire every run — only once per bad streak."""
    if news.health_alert_needed(memory):
        streak = memory.get(news.NEWS_FAILURE_STREAK_KEY, 0)
        send_admin_message(
            f"⚠️ فرمت «خبر ساده‌شده» {streak} بار پشت‌سرهم هیچ خبری برنگردونده — "
            f"یعنی یا فیدهای BBC توی config.NEWS_FEEDS دیگه کار نمی‌کنن (لینک عوض شده/حذف شده)، "
            f"یا یه چیز دیگه شبکه‌ای بلوکش کرده. تا وقتی درست نشه، این فرمت بی‌سروصدا رد می‌شه و "
            f"جای اون از استخر موضوعات عادی استفاده می‌شه — یه نگاه بنداز."
        )


def maybe_alert_quota_pressure(memory):
    """Alerts once per calendar day the first time this run notices the
    REVIEW_MODEL tier (quality review, poll/quiz generation, and weekly
    strategy — see generate_content_smart's own docstring) fell back to
    Groq at least once today (see ai.get_quota_snapshot /
    ai._record_provider_call). That fallback firing at all means Gemini's
    REVIEW_MODEL free tier (config.GEMINI_REVIEW_DAILY_FREE_QUOTA/day)
    was exhausted or unreachable for at least one call today — worth
    knowing because a review pass done by the Groq fallback instead of
    Gemini has not been confirmed to enforce the same rules (e.g.
    LANGUAGE_BALANCE) as reliably; see the 2026-08-15 progress_recap
    incident this was added alongside (#90 in PROJECT_STATUS.md).

    Unlike maybe_alert_low_topic_supply/maybe_alert_low_story_supply, the
    underlying condition here resets every day on its own (a fresh
    quota), so this doesn't need a "recovered" rearm branch — it just
    checks whether today's date already has an alert recorded and, if
    not, sends one and stamps today's date.

    Deliberately called alongside the other three health-checks near the
    TOP of main(), not after this run's own generation — not because it
    only needs prior-run data (ai._record_provider_call writes
    QUOTA_TRACKING_PATH unconditionally on every call, independent of
    main.py's control flow entirely), but because several branches below
    this point return early without reaching the end of main() (see the
    several `if content is None: return` sites after a permanently-
    failed review) and thus never reach save_json(MEMORY_PATH, memory) —
    a pre-existing gap, not introduced here (worth a real fix
    separately: the cleanest one is probably wrapping main()'s whole body
    so the memory save always happens on the way out, not threading a
    save through every early return by hand). Placing this check at the
    top, like its three siblings, means it always runs once per
    invocation regardless of that gap — at worst a fallback used on the
    day's LAST scheduled run is only surfaced on the next day's first
    run, which is an acceptable delay for a non-urgent informational
    alert."""
    snapshot = get_quota_snapshot()
    groq_smart_calls = snapshot.get("groq_smart_calls", 0)
    if groq_smart_calls < 1:
        return
    today = clock.today_str()
    if memory.get(QUOTA_ALERT_DATE_KEY) == today:
        return
    gemini_smart_calls = snapshot.get("gemini_smart_calls", 0)
    send_admin_message(
        f"⚠️ امروز {groq_smart_calls} بار (از مجموع {gemini_smart_calls + groq_smart_calls} تلاش) "
        f"لایه‌ی «هوشمند» (بازبینیِ کیفیت، کوییز/نظرسنجی، یا استراتژی هفتگی) به‌جای Gemini از fallback "
        f"رایگان Groq استفاده کرد — یعنی سهمیه‌ی رایگان روزانه‌ی Gemini برای این لایه "
        f"({GEMINI_REVIEW_DAILY_FREE_QUOTA} درخواست) امروز یه‌جا تموم شده یا موقتاً در دسترس نبوده. "
        f"مرحله‌ی بازبینی وقتی با Groq انجام شده ممکنه قوانین (مثل تعادل زبان) رو کمتر دقیق چک کرده "
        f"باشه — لازم نیست کاری بکنی، فقط برای اطلاع؛ اگه این هشدار زیاد تکرار شد، یعنی وقتشه یا "
        f"POSTS_PER_DAY/تعداد retry بازبینی رو کم کنی، یا یه اکانت Gemini دومی (GEMINI_API_KEY_BACKUP) اضافه کنی."
    )
    memory[QUOTA_ALERT_DATE_KEY] = today


def resolve_today_format():
    post_count = count_posts(published_only=True)
    if post_count > 0 and post_count % RECAP_EVERY_N_POSTS == 0:
        return "progress_recap", True
    schedule = load_json(SCHEDULE_PATH, {})
    weekday_name = clock.weekday_name()
    return schedule.get(weekday_name, "micro_scene"), False


def generate_reviewed_text(memory, strategy, related, topic, format_name,
                            recap_titles=None, extra_note="",
                            campaign_note="", profile_note="",
                            dedup_exclude_ids=None):
    """Returns the finished, review-passing text, or None if it still
    fails review after MAX_REVIEW_ATTEMPTS retries — callers must treat
    None exactly like handle_poll_format's None: skip today's post
    gracefully, don't publish anything.

    dedup_exclude_ids: optional set of post ids to leave out of the
    semantic-duplicate check (embeddings.check_semantic_duplicate) — see
    that function's Bug fix #92. reader_installment passes its own
    story's earlier published chunks here, since those are SUPPOSED to
    read as similar (same story) and would otherwise fail dedup forever.

    Bug fix (#25): this used to always return the last draft regardless of
    whether it ever actually passed review — even after every one of
    MAX_REVIEW_ATTEMPTS retries came back ok: False, main() would publish
    it anyway, with no admin alert and no skip path (unlike the poll path,
    which raises in strict mode, or the image path's manual hand-off).
    That quietly undermined the review gate's whole "fail closed" point:
    a review call itself failing was already handled (see AUDIT_FIXES.md),
    but a review call that SUCCEEDED and correctly said "this is bad" was
    not. Now, if the final draft still isn't ok, this alerts the admin
    with the specific reason and returns None instead of publishing
    something its own review gate never approved.
    """
    def _draft(note=""):
        prompt = build_generation_prompt(
            memory, strategy, related, topic, format_name,
            extra_note=note, recap_titles=recap_titles,
            campaign_note=campaign_note, profile_note=profile_note,
        )
        return generate_content(prompt)

    def _check(text):
        """One full pass of every automated gate a draft has to clear:
        quality review, stray-script-character scan, and semantic dedup
        (embeddings.check_semantic_duplicate) — the last one closes a gap
        the keyword-based `related` context can't see: a reused example
        sentence/scenario under a topic with an unrelated name or category
        (see embeddings.py's module docstring for the concrete incident
        this fixes). Returns (ok, review, stray_chars, dup_title)."""
        review = review_content(build_review_prompt(
            text, format_name, topic_text=topic.get("topic"),
            topic_is_lexical_item=topic.get("topic_is_lexical_item"),
        ))
        stray = find_stray_script_chars(text)
        dup_title, _dup_score = embeddings.check_semantic_duplicate(
            text, exclude_post_ids=dedup_exclude_ids,
        )
        ok = review.get("ok") is True and not stray and dup_title is None
        return ok, review, stray, dup_title

    content = _draft(extra_note)
    ok, review, stray, dup_title = _check(content)
    attempts = 0
    while not ok and attempts < MAX_REVIEW_ATTEMPTS:
        note = review.get("feedback", "") or ""
        if stray:
            note = (note + " " if note else "") + (
                "متن قبلی چند کاراکتر عجیب و نامربوط داشت (نه فارسی، نه انگلیسی، نه اموجی معمولی: "
                + " ".join(stray) + "). دوباره بنویس و فقط از حروف فارسی، انگلیسی، و اموجی معمولی استفاده کن."
            )
        if dup_title:
            note = (note + " " if note else "") + (
                f"متن قبلی از نظر معنایی خیلی شبیه یه پست قبلیِ دیگه (به اسم «{dup_title}») بود — مثلاً "
                "همون مثال، سناریو، یا جمله، حتی اگه موضوعش ظاهراً فرق داشت. یه مثال/سناریو/جمله‌ی کاملاً "
                "تازه انتخاب کن، نه فقط یه تغییر جزئی روی همون قبلی."
            )
        content = _draft(note=(extra_note + " " + note).strip())
        ok, review, stray, dup_title = _check(content)
        attempts += 1

    if stray:
        for ch in stray:
            content = content.replace(ch, "")
        # Stripping stray characters can turn an otherwise-fine draft from
        # "not ok" into genuinely fine — recompute without spending another
        # review/dedup call (both already ran against this exact content;
        # only the stray-char verdict is now stale).
        ok = review.get("ok") is True and dup_title is None

    if not ok:
        reason = review.get("feedback") or (
            f"محتوا از نظر معنایی خیلی شبیه پست قبلیِ «{dup_title}» بود" if dup_title
            else "دلیل مشخص نیست"
        )
        send_admin_message(
            f"⚠️ پستِ «{FORMATS[format_name]['label']}» امروز بعد از {MAX_REVIEW_ATTEMPTS + 1} تلاش هم "
            f"از مرحله‌ی بازبینی رد نشد و منتشر نشد: {escape_html(reason)}\n"
            f"لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه."
        )
        print(f"generate_reviewed_text: giving up on {format_name} after "
              f"{MAX_REVIEW_ATTEMPTS + 1} attempts — still not ok:", reason)
        return None
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
            f"⚠️ ساخت {fmt['label']} امروز شکست خورد (پاسخ مدل قابل‌تفسیر نبود یا خطای API داشت): "
            f"{escape_html(exc)}\nاین دور پستی منتشر نشد؛ لازم نیست کاری بکنی، فقط برای اطلاع."
        )
        print(f"handle_poll_format: giving up for {format_name} —", exc)
        return None

    question = data.get("question", topic["topic"])
    # Capped at telegram_bot.POLL_MAX_OPTIONS (12, Telegram's current
    # documented maximum — send_poll itself validates this too, but
    # trimming here first means a model response with, say, 13 options
    # loses only the excess rather than being rejected outright). The
    # minimum here (2) is a CONTENT-quality bar, not a copy of Telegram's
    # technical one — Telegram itself now accepts as few as 1, but a
    # single-option "quiz" or "poll" isn't meaningful content regardless
    # of what the API permits.
    options = data.get("options", [])[:telegram_bot.POLL_MAX_OPTIONS]
    if len(options) < 2:
        send_admin_message(
            f"⚠️ {fmt['label']} امروز کمتر از ۲ گزینه برگردوند — پست منتشر نشد."
        )
        return None

    correct_index = None
    try:
        if is_quiz:
            correct_index = data.get("correct_index")
            if not isinstance(correct_index, int) or not (0 <= correct_index < len(options)):
                send_admin_message(
                    f"⚠️ کوییز امروز correct_index نامعتبر برگردوند "
                    f"({escape_html(repr(correct_index))}) — پست منتشر نشد."
                )
                return None
            result = send_poll(question, options, is_quiz=True,
                                correct_option_id=correct_index, explanation=data.get("explanation", ""))
        else:
            result = send_poll(question, options, is_quiz=False)
    except Exception as exc:
        # Bug fix (#23): send_poll used to be called with no try/except
        # anywhere in this function — unlike handle_image_format's
        # graceful multi-level fallback, any failure here (Telegram
        # rejecting the request after _post_with_retry's own retries are
        # exhausted, or the new-in-this-fix immediate-raise on a
        # Timeout — see telegram_bot.py's #14 fix) used to crash the
        # entire run instead of gracefully skipping just today's poll.
        send_admin_message(
            f"⚠️ ارسالِ {fmt['label']} امروز شکست خورد: {escape_html(exc)}\nاین دور پستی منتشر نشد."
        )
        print(f"handle_poll_format: send_poll failed for {format_name} —", exc)
        return None

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
            message_id,
            question,
            is_quiz=is_quiz,
            correct_index=correct_index,
            theme_category=theme_category,
            topic_category=topic.get("category"),
            experiment_id=experiment_id,
            variant_label=variant_label,
            extra_channel_results=extra_results,
        )
    return json.dumps(data, ensure_ascii=False)


def handle_image_format(memory, strategy, related, topic, format_name, extra_note="",
                         campaign_note="", profile_note=""):
    """Auto-generates and posts the image (Audit: this used to hand the
    finished prompt to the admin to paste into an image tool by hand, every
    single run) — to Telegram, Eitaa, and Bale. Falls back one rung at a
    time (see below) rather than jumping straight to the full manual
    hand-off the moment any one step wobbles, so a bad run never silently
    loses the post — worst case still costs the admin the five minutes it
    always used to cost.

    Returns (content, status, extra_channel_results, message_id) — the same
    first three the caller already expects from the non-image branch (a
    successful auto-post now correctly counts as status="published"
    instead of always being "pending_manual" — see the comment on
    record_topic_coverage below for why that distinction used to not
    matter there, but does matter for get_recent_posts/count_posts/recap
    eligibility, which all filter on status='published'), plus the
    Telegram message_id (None if nothing was actually posted to Telegram
    this run) so callers can feed it to analytics.record_text_post for
    engagement_harvest.py to look up later."""
    caption = generate_reviewed_text(memory, strategy, related, topic, format_name,
                                      extra_note=extra_note,
                                      campaign_note=campaign_note, profile_note=profile_note)
    if caption is None:
        # generate_reviewed_text already alerted the admin with the specific
        # reason — nothing worth generating an image for.
        return None, None, None, None

    scene_prompt = build_scene_prompt(topic["topic"])
    scene_sentence = _review_scene_sentence(generate_content(scene_prompt))
    image_prompt = compose_image_prompt(scene_sentence)

    image_bytes = None
    message_id = None
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
            result = send_photo(image_bytes, caption)
            message_id = (result or {}).get("result", {}).get("message_id")
        except Exception as exc:  # noqa: BLE001 — a Telegram send failure must not crash the run
            print("handle_image_format: send_photo failed, trying sendDocument fallback:", exc)
            try:
                result = send_document(image_bytes, caption)
                message_id = (result or {}).get("result", {}).get("message_id")
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
            message_id,
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
        None,
    )


def handle_voice_format(memory, strategy, related, topic, format_name, extra_note="",
                         campaign_note="", profile_note=""):
    """Auto-generates and posts a voice note (Gemini TTS + ffmpeg PCM ->
    OGG/Opus — see voice_note.py) — the pronunciation-focused format
    telegram-esl-virality-blueprint.md makes the case for (see
    prompts.FORMATS["voice_note"]'s comment): no amount of text conveys
    what a sound actually sounds like.

    Falls back to a plain TEXT post (not a manual admin hand-off, unlike
    handle_image_format) if generation fails at any step — a script
    written to be read aloud is still perfectly good Persian/English text
    to just post, so there's a fully-automatic degraded option here that
    images don't have (an image PROMPT isn't a substitute for the image;
    a voice SCRIPT is a substitute for the audio).

    Eitaa/Bale cross-posting is text-only for this format — unlike
    handle_image_format's photo cross-post, audio upload isn't a confirmed
    working path on either platform's API, and getting that wrong would
    silently drop the post there instead of degrading it; text always
    works.

    Returns (content, status, extra_channel_results, message_id), the same
    shape as handle_image_format."""
    script = generate_reviewed_text(memory, strategy, related, topic, format_name,
                                     extra_note=extra_note,
                                     campaign_note=campaign_note, profile_note=profile_note)
    if script is None:
        # generate_reviewed_text already alerted the admin with the specific
        # reason — nothing worth generating audio (or posting as text) for.
        return None, None, None, None

    ogg_bytes = None
    message_id = None
    try:
        # generate_speech already retries per-model and falls back across
        # two model tiers internally (ai.py); pcm_to_ogg_opus can still
        # raise if ffmpeg itself is missing/broken — this try/except is
        # the last-resort net for either, same spirit as
        # handle_image_format's equivalent.
        ogg_bytes = voice_note.build_voice_note(script)
    except Exception as exc:  # noqa: BLE001 — a broken TTS/ffmpeg call must not crash the run
        print("handle_voice_format: build_voice_note raised unexpectedly, falling back to text:", exc)

    if ogg_bytes is not None:
        try:
            result = send_voice(ogg_bytes, script)
            message_id = (result or {}).get("result", {}).get("message_id")
        except Exception as exc:  # noqa: BLE001 — a Telegram send failure must not crash the run
            print("handle_voice_format: send_voice failed, falling back to text:", exc)
            ogg_bytes = None

    if ogg_bytes is not None:
        extra_results = broadcast_extra_channels(script)  # text-only on Eitaa/Bale — see docstring
        return (script, "published", extra_results, message_id)

    print("handle_voice_format: voice generation/delivery unavailable this run, posting text instead.")
    # Bug fix (#27): this last-resort text fallback — reached only once
    # BOTH the TTS call and send_voice have already failed — used to be
    # the one call in this whole function with no try/except, unlike its
    # two siblings just above. If this specific send_message call failed
    # (network error, Telegram rejecting the HTML), the exception used to
    # propagate uncaught and crash the entire run, defeating the point of
    # having a "safety net under the safety net" text fallback at all.
    try:
        result = send_message(script)
        message_id = (result or {}).get("result", {}).get("message_id")
    except Exception as exc:  # noqa: BLE001 — this IS the last resort; it must not crash the run either
        send_admin_message(
            f"⚠️ فرمت «{FORMATS[format_name]['label']}» امروز نه صدا و نه حتی نسخه‌ی متنی‌ش منتشر شد: "
            f"{escape_html(exc)}\nمتن آماده بود ولی ارسالش هم شکست خورد — این دور پستی منتشر نشد."
        )
        print("handle_voice_format: even the text fallback's send_message failed:", exc)
        return None, None, None, None
    extra_results = broadcast_extra_channels(script)
    return (script, "published", extra_results, message_id)


def _try_recap_image(recap_titles, caption):
    """Best-effort image-card recap (content-pipeline-architecture.md §8).
    Returns (message_id, extra_channel_results) if it was rendered and
    posted successfully (Telegram + Eitaa/Bale), or None if the caller
    should fall back to the plain-text post instead.

    Every failure path here is a silent log line, not an admin alert —
    unlike handle_image_format's illustrated_pun (where a failed image IS
    the post and someone has to make it manually), the plain-text recap has
    always been the fully-working default for this format, so the image
    card is a nice-to-have upgrade, not something worth paging anyone about
    when it's not available yet (e.g. before RECAP_FONT_PATH's font file
    has been added — see recap_card.py)."""
    try:
        title = generate_content(build_recap_title_prompt(recap_titles)).strip().strip('"').strip("«»")
    except Exception as exc:  # noqa: BLE001
        print("recap image: title generation failed, falling back to text recap:", exc)
        return None

    stray = find_stray_script_chars(title)
    if stray:
        print("recap image: title contained stray characters, stripping before render:", stray)
        for ch in stray:
            title = title.replace(ch, "")
        title = title.strip().strip('"').strip("«»")
        if not title:
            print("recap image: title became empty after stripping stray characters, falling back to text recap")
            return None

    try:
        image_bytes = recap_card.render_recap_card(title, recap_titles)
    except recap_card.FontNotAvailable as exc:
        print("recap image: font not available, falling back to text recap:", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        print("recap image: render_recap_card raised unexpectedly, falling back to text recap:", exc)
        return None

    try:
        result = send_photo(image_bytes, caption)
    except Exception as exc:  # noqa: BLE001
        print("recap image: send_photo failed, trying sendDocument fallback:", exc)
        try:
            result = send_document(image_bytes, caption)
        except Exception as exc2:  # noqa: BLE001
            print("recap image: send_document fallback also failed, falling back to text recap:", exc2)
            return None

    message_id = (result or {}).get("result", {}).get("message_id")
    extra_results = broadcast_extra_channels_photo(image_bytes, caption)
    return message_id, extra_results


def _select_topic(memory, format_name, theme_category=None):
    """Return (topic, extra_note, invented_idiom_mode, source). topic is
    None if this format's eligible pool is completely empty AND it has no
    "invent one" fallback (see below) — callers MUST check for that and
    skip gracefully (see main()'s handling right after this is called),
    the same way a poll/review failure is already handled, rather than
    letting a bare None reach generate_reviewed_text/build_generation_prompt.

    Every format goes through the exact same get_next_topic call now —
    which topics are even candidates is decided by topic_selection._eligible
    from each format's own declared contract in prompts.FORMATS (category_filter
    / required_tags), not by a special case here (content-pipeline-
    architecture.md §5). theme_category (campaigns.py) is only ever a soft
    preference within whatever pool a format is already restricted to; it
    can't override a format's declared eligibility.

    illustrated_pun is the only format with an "invent one on the spot"
    fallback when its pool runs dry — safe there because the format's own
    review gate already re-checks whatever the model invents. Bug fix
    (#29): every OTHER format used to have no fallback of any kind if
    get_next_topic ever returned None for it — this function's own
    docstring already flagged that as a real possibility ("illustrated_pun
    is the only format this has ever happened to IN PRACTICE", not "the
    only one that ever could"), and idiom_proverb_bridge is genuinely the
    most exposed: its eligible pool is currently just 5 topics (see
    research.py's #54/#57 fix for why that pool grows slowly), and
    unlike illustrated_pun, "invent one on the spot" is specifically the
    WRONG fallback for it — the whole point of requiring a verified
    fa_equivalent is to never ask the model to invent or recall an
    idiom/proverb pairing on its own. So instead of leaving topic=None to
    crash deep inside prompt-building with an opaque TypeError, that case
    is now surfaced here as a clear, checkable signal.
    """
    extra_note = ""
    invented_idiom_mode = False

    callback_topic = pending_vocab_spotlight_callback(memory, format_name)
    if callback_topic is not None:
        # This topic was already taught once (via vocab_spotlight) -- this
        # is a deliberate follow-up, not a first-ever exposure, so it's
        # tagged "review" for get_due_review_topic's stage purposes (see
        # #36), same as any other genuine, intentional re-exposure.
        extra_note = (
            "این کلمه/عبارت رو چند روز پیش توی یه پست «واژه‌ی روز» معرفی کردیم؛ الان زمینه‌شه که "
            "توی یه سناریوی طبیعی (نه یادآوریِ خشک) دوباره ببینیمش."
        )
        return callback_topic, extra_note, False, "review"

    topic, source = get_next_topic(memory, format_name, theme_category=theme_category)

    if topic is None and format_name == "illustrated_pun":
        invented_idiom_mode = True
        source = "fresh"
        topic = dict(INVENTED_IDIOM_TOPIC)
        extra_note = (
            "توی data/topics.json دیگه اصطلاح (Idiom) پوشش‌داده‌نشده‌ای باقی نمونده. "
            "به‌جاش یه اصطلاح ساده و رایج انگلیسی (سطح A1-A2) که فاصله‌ی واضحی بین معنی "
            "تحت‌اللفظی و معنی واقعی داره خودت انتخاب کن و همون رو موضوع این پست کن."
        )

    return topic, extra_note, invented_idiom_mode, source


def main():
    harvest_pending_polls()
    engagement_harvest.harvest_engagement_metrics()

    today_str = clock.today_str()
    posted_today = count_posts_on_date(today_str)
    if posted_today >= POSTS_PER_DAY:
        print(
            f"امروز ({today_str}) قبلاً {posted_today} پست از {POSTS_PER_DAY} پست مجاز روزانه "
            f"منتشر شده؛ این اجرا رد می‌شه."
        )
        return
    slot_number = posted_today + 1  # 1-indexed: which run of today's POSTS_PER_DAY this is

    # Bug fix (#6): remediate_stray_chars_in_db used to run unconditionally
    # at the very top of main(), before the daily-cap check above — so
    # even a catch-up cron run that was about to immediately no-op (the
    # "posted_today >= POSTS_PER_DAY" case) still paid for a full
    # SELECT-every-published-post-and-regex-scan-each-one pass, up to 6
    # times a day, forever, as the channel grows. Moved to after the cap
    # check (skipped entirely on a no-op run) and gated to slot_number==1
    # (runs at most once per day even on a day that does post), matching
    # its actual purpose as an occasional cleanup pass rather than
    # something every single invocation needs to redo.
    if slot_number == 1:
        fixed = remediate_stray_chars_in_db()
        if fixed:
            print("Remediated stray characters in posts:", fixed)

    memory = load_json(MEMORY_PATH, {})
    migrate_covered_topics(memory)
    strategy = load_json(STRATEGY_PATH, {})

    # Weakness 5 (campaigns) / Weakness 1 (audience profile) context —
    # computed once per run, reused by whichever branch below actually
    # generates content.
    campaign_state = campaigns.get_or_start_week(memory)
    campaign_note = campaigns.campaign_context_block(campaign_state)
    profile_note = audience_profile.profile_context_block()

    format_name, recap_preempted = resolve_today_format()
    fmt = FORMATS[format_name]

    # Bug fix (#24): these three used to sit after the progress_recap and
    # needs_poll branches' early returns, so any run whose format resolved
    # to progress_recap or a poll/quiz skipped all three checks entirely.
    # They're unconditional admin health-checks (a real, if imperfect,
    # safety net for "the topic pool is running low" / "the story library
    # is running low" / "the news feed looks dead") that have nothing to
    # do with which format happens to run today, so they're now called
    # right here, before any format-specific branch can return early.
    maybe_alert_low_topic_supply(memory)
    maybe_alert_low_story_supply(memory)
    maybe_alert_news_health(memory)
    maybe_alert_quota_pressure(memory)

    if recap_preempted:
        schedule = load_json(SCHEDULE_PATH, {})
        weekday = clock.weekday_name()
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
        if content is None:
            return  # generate_reviewed_text already alerted the admin with the specific reason

        recap_image_result = _try_recap_image(recap_titles, content)
        if recap_image_result is None:
            # Image path unavailable (no font — see recap_card.py) or
            # failed somewhere — fall back to the plain-text post, which
            # is how this format has always worked and needs no asset.
            result = send_message(content)
            message_id = (result or {}).get("result", {}).get("message_id")
            extra_results = broadcast_extra_channels(content)
        else:
            message_id, extra_results = recap_image_result

        save_post(date=today_str, format_name=format_name,
                   category="Recap", level="-", title="Progress recap",
                   content=content, keywords="recap", status="published")
        campaigns.record_post(campaign_state, today_str, format_name, "Progress recap")
        analytics.record_text_post(format_name, "Progress recap", extra_channel_results=extra_results,
                                    message_id=message_id)
        print("پست مرور پیشرفت منتشر شد.")
        return

    # Only the day's FIRST slot keeps the raw weekday-scheduled format —
    # that's what preserves "quiz day" / "idiom day" / etc. "Extra" slots
    # (slot_number > FRESH_TOPICS_PER_DAY) exist because of the move to
    # POSTS_PER_DAY > 1, and are handled differently below: they never
    # repeat a needs_poll/needs_image/needs_voice format within the same day (Audit:
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
    reader_data = None
    news_item = None
    if slot_number > FRESH_TOPICS_PER_DAY:
        todays_weekday_format = format_name  # captured before any rerouting below (bug #28)
        if fmt["needs_poll"] or fmt["needs_image"] or fmt.get("needs_voice"):
            format_name = DEFAULT_EXTRA_SLOT_FORMAT
            fmt = FORMATS[format_name]

        # Extra slots beyond the weekday-scheduled one, in priority order:
        # 1) the first extra slot always tries the graded reader (fixed
        #    cadence keeps a serialized story moving one episode/day);
        # 2) any later extra slot tries a due spaced-repetition review
        #    first (existing behavior, unchanged in priority);
        # 3) failing that, real news re-leveled at A1/A2;
        # 4) failing that, falls through to the normal fresh/recycle topic
        #    pool below, exactly as before this feature existed.
        extra_slot_index = slot_number - FRESH_TOPICS_PER_DAY

        if extra_slot_index == 1:
            story, chunk_index, chunk_text, is_final = reader.get_next_installment(memory)
            if story is not None:
                format_name = "reader_installment"
                fmt = FORMATS[format_name]
                reader_data = (story, chunk_index, chunk_text, is_final)

        if reader_data is None:
            review_topic, review_stage, review_last_format = get_due_review_topic(memory)
            if review_topic:
                review_format = "vocab_spotlight" if review_last_format == "spot_mistake" else "spot_mistake"
                if review_format == todays_weekday_format:
                    # Bug fix (#28): this alternation has no way to know
                    # what slot 1 (an earlier, separate invocation of
                    # main() today) already posted — if today's weekday
                    # format happens to be the SAME format the alternation
                    # would pick, the result is the same format twice in
                    # one day, exactly like the existing needs_poll/image/
                    # voice guard above already prevents. Confirmed this
                    # already happened once in the shipped sample data
                    # (data/campaign_state.json: "spot_mistake" used twice
                    # on 2026-07-28, a real Tuesday whose scheduled format
                    # is spot_mistake). Reroute the same way the guard
                    # above does, and let the topic stay due for the next
                    # slot that has room for it instead.
                    format_name = DEFAULT_EXTRA_SLOT_FORMAT
                    fmt = FORMATS[format_name]
                    review_topic = None
                else:
                    format_name = review_format
                    fmt = FORMATS[format_name]
            else:
                news_item = news.fetch_news_item(memory)
                if news_item:
                    format_name = "news_relevel"
                    fmt = FORMATS[format_name]

    if fmt["needs_poll"]:
        recent_rows = get_recent_posts(limit=7)
        recent_titles = [row[0] for row in recent_rows]
        if not recent_titles:
            print("هنوز پستی برای ساختن کوییز/نظرسنجی از روش وجود نداره؛ این دور رد می‌شه.")
            return
        # Bug fix (#30): recent_titles[0] used to be used verbatim both as
        # the review's "topic" AND as search_related_posts' search
        # keyword. That breaks down when the most recent post was a
        # reader_installment/news_relevel: their titles are long,
        # compound strings (e.g. "The Ant and the Grasshopper — قسمت 2",
        # or a full news headline) that are exceedingly unlikely to
        # appear as a literal substring in any other post's title/
        # keywords — search_related_posts' `LIKE '%...%'` match would
        # come back empty, silently starving that day's poll prompt of
        # any related-post context. Prefer the most recent title that
        # ISN'T one of those two categories (get_recent_posts' category
        # column, already fetched — no extra query needed); only fall
        # back to recent_titles[0] verbatim if every one of the last 7
        # posts happens to be a reader/news post.
        review_worthy = [(row[0], row[1]) for row in recent_rows if row[1] not in ("Reader", "News")]
        if review_worthy:
            topic_title, topic_category = review_worthy[0]
        else:
            topic_title, topic_category = recent_titles[0], recent_rows[0][1]
        topic = {"topic": topic_title, "level": "-", "category": topic_category}
        related = search_related_posts(topic_title)

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

        content = handle_poll_format(
            strategy, related, topic, format_name,
            recent_titles=recent_titles if fmt["needs_poll"] == "quiz" else None,
            campaign_note=campaign_note, profile_note=profile_note, variant_note=variant_note,
            theme_category=campaign_state.get("theme_category"),
            experiment_id=experiment_id, variant_label=variant_label,
        )
        if content is None:
            return
        # Bug fix (#26): record_assignment used to be called BEFORE
        # handle_poll_format, unconditionally — so a poll that failed to
        # generate/send (any of the several `return None` paths inside
        # handle_poll_format) still permanently recorded a variant "use",
        # silently skewing assign_variant's "fewest uses so far" balancing
        # with a phantom assignment for a post that never actually went
        # out. Moved to here, after handle_poll_format has already
        # returned successfully — matching every other "record what just
        # happened" call in this file (campaigns.record_post, analytics.
        # record_text_post, save_post all already run after their post
        # succeeds, not before).
        if active_exp:
            experiments.record_assignment(experiment_id, variant_label)
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

    if reader_data is not None:
        story, chunk_index, chunk_text, is_final = reader_data
        invented_idiom_mode = False
        source = "fresh"  # unused (reader chunks aren't topics.json entries; no coverage recorded)
        topic = {
            "topic": f"{story['title']} — قسمت {chunk_index + 1}",
            "level": story.get("level", "A1"),
            "category": "Reader",
        }
        continuation_note = (
            "این آخرین قسمت این داستانه — پایانش رو کامل و رضایت‌بخش تموم کن، بدون قلاب برای فردا."
            if is_final else
            "این قسمتِ آخرِ داستان نیست — با یه قلاب یا سوال واقعی برای قسمت بعد تموم کن."
        )
        extra_note = (
            f"متن اصلیِ همین قسمت (بازنویسی‌ش کن به انگلیسیِ ساده‌ی A1-A2، رویدادها/شخصیت‌ها رو عوض نکن):\n"
            f"{chunk_text}\n\n{continuation_note}"
        )
    elif news_item is not None:
        invented_idiom_mode = False
        source = "fresh"  # unused (news items aren't topics.json entries; no coverage recorded)
        topic = {"topic": news_item["title"], "level": "A2", "category": "News"}
        extra_note = (
            "خلاصه‌ی یه خبر واقعی و تازه (با جمله‌های خودت و در سطح A1-A2 بازنویسی‌ش کن، جمله‌های منبع رو "
            "کپی نکن، و چیزی که توی خلاصه نیومده رو حدس نزن):\n"
            f"{news_item['summary']}"
        )
    elif review_topic:
        topic = review_topic
        invented_idiom_mode = False
        source = "review"  # a genuine scheduled spaced-repetition review (bug #36)
        ordinal = {0: "بار اول", 1: "بار دوم", 2: "بار سوم", 3: "بار چهارم"}.get(review_stage, "چند بارِ قبل")
        extra_note = (
            f"این یه پست «مرور»ه، نه معرفی یه نکته‌ی کاملاً جدید — این نکته قبلاً آموزش داده شده "
            f"(این {ordinal} مرورشه)، الان هدف اینه که دوباره و این بار محکم‌تر توی ذهن بمونه. "
            f"لحنش «یادته؟ بیا یه بار دیگه با یه مثال/زاویه‌ی تازه ببینیمش» باشه، نه معرفی از صفر."
        )
    else:
        topic, extra_note, invented_idiom_mode, source = _select_topic(
            memory, format_name, theme_category=campaign_state.get("theme_category"),
        )
    if not topic:
        # Bug fix (#29): a format whose eligible pool is genuinely empty
        # (and has no "invent one" fallback — see _select_topic's #29 fix)
        # used to reach here with no way for the admin to tell WHICH
        # format ran dry; now names it explicitly.
        send_admin_message(
            f"🔴 هیچ موضوعِ واجد شرایطی برای «{fmt['label']}» توی data/topics.json پیدا نشد — پستی منتشر نشد."
        )
        return

    related = context_posts_for_generation(topic["topic"], category=topic.get("category"))

    if fmt["needs_image"]:
        # handle_image_format now auto-generates and posts the image itself
        # (falling back to the old manual admin hand-off only if that
        # fails), so status/extra_results come from what actually happened
        # this run rather than being hardcoded to "pending_manual"/None.
        content, status, extra_results, message_id = handle_image_format(
            memory, strategy, related, topic, format_name,
            extra_note=extra_note,
            campaign_note=campaign_note, profile_note=profile_note,
        )
        if content is None:
            return  # the caption never passed review; already alerted, nothing else to do
    elif fmt.get("needs_voice"):
        content, status, extra_results, message_id = handle_voice_format(
            memory, strategy, related, topic, format_name,
            extra_note=extra_note,
            campaign_note=campaign_note, profile_note=profile_note,
        )
        if content is None:
            return  # the script never passed review (or even the text fallback failed); already alerted
    else:
        # Bug fix (#92): a reader_installment chunk is a continuation of a
        # specific story and is SUPPOSED to resemble that same story's
        # earlier, already-published chunks — excluding them is what stops
        # the semantic-dedup check from rejecting every future installment
        # as "too similar to itself" (see database.get_post_ids_for_story
        # and embeddings.check_semantic_duplicate for the full reasoning).
        dedup_exclude_ids = (
            get_post_ids_for_story(reader_data[0]["id"]) if reader_data is not None else None
        )
        content = generate_reviewed_text(memory, strategy, related, topic, format_name,
                                          extra_note=extra_note,
                                          campaign_note=campaign_note, profile_note=profile_note,
                                          dedup_exclude_ids=dedup_exclude_ids)
        if content is None:
            return  # generate_reviewed_text already alerted the admin with the specific reason
        result = send_message(content)
        message_id = (result or {}).get("result", {}).get("message_id")
        extra_results = broadcast_extra_channels(content)
        status = "published"

    campaigns.record_post(campaign_state, today_str, format_name, topic["topic"])
    analytics.record_text_post(format_name, topic["topic"], extra_channel_results=extra_results,
                                message_id=message_id)

    post_id = save_post(
        date=today_str,
        format_name=format_name,
        category=topic["category"],
        level=topic["level"],
        title=topic["topic"],
        content=content,
        keywords=topic["topic"],
        status=status,
        story_id=reader_data[0]["id"] if reader_data is not None else None,
        chunk_index=reader_data[1] if reader_data is not None else None,
    )
    # Semantic-dedup store (embeddings.py) — the drafting-time check inside
    # generate_reviewed_text/handle_image_format already compared this
    # content against everything published so far; recording it now is what
    # makes it visible to TOMORROW's check. A failure here never blocks
    # anything — see record_post_embedding's docstring.
    embeddings.record_post_embedding(post_id, topic["topic"], content)

    # Was `if status == "published" and not invented_idiom_mode:` — that
    # silently excluded illustrated_pun forever, since it always sets
    # status="pending_manual" (handed to the admin for manual posting) and
    # so never satisfied "== published". The topic was never marked
    # covered, so get_next_topic() kept returning the exact same idiom on
    # every single illustrated_pun run (confirmed: topics.json's first
    # Idioms entry, "Break the ice", forever). Coverage should track "we
    # picked this topic and generated content for it", not "it got posted
    # automatically" — status is irrelevant here.
    #
    # reader_data/news_item aren't topics.json entries at all — recording
    # them into covered_topic_history would just be noise that grows
    # memory.json forever without ever matching a real topic (get_next_topic
    # and get_due_review_topic only look up names that exist in
    # topics.json).
    if reader_data is None and news_item is None and not invented_idiom_mode:
        record_topic_coverage(memory, topic["topic"], format_name, today_str, source=source)

    # NEW FIX (found while wiring up #36): this save used to be
    # conditional — `if reader_data is not None or news_item is not None
    # or not invented_idiom_mode:` — which was written to skip an
    # "unnecessary" write on the one path with nothing new to persist
    # (invented_idiom_mode with no reader_data/news_item, since that's
    # also exactly when record_topic_coverage above is skipped). But
    # several things earlier in this same run can mutate `memory` in ways
    # that have NOTHING to do with which branch ran: maybe_alert_low_
    # topic_supply / maybe_alert_low_story_supply's alerted-flags, and
    # news.health_alert_needed's failure-streak/alerted-flag, are all
    # mutated unconditionally near the top of this function, every run.
    # The old condition could silently discard any of those mutations
    # exactly when invented_idiom_mode was true with no reader/news —
    # e.g. news.health_alert_needed marking a streak "already alerted"
    # would be lost, and the very next run would alert the admin again
    # for a problem it was already told about. Saving unconditionally
    # costs one small JSON write; not saving risked silently losing
    # real state.
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
                f"{escape_html(exc)}\n\n"
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
                f"{escape_html(exc)}\n\n"
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
                f"🔴 اجرای امروز کلاً با خطا شکست خورد: {escape_html(exc)}\n"
                f"این با هشدارهای معمولی (مثل کمبود موضوع) فرق داره — این یعنی خودِ پایپ‌لاین "
                f"مشکل داره (مثلاً quota، یا یه خطای غیرمنتظره).\n"
                f"⚠️ توجه: این خطا ممکنه بعد از ارسال موفق پست به تلگرام/ایتا/بله رخ داده باشه "
                f"(مثلاً توی مرحله‌ی ثبت/آنالیتیکس) — لطفاً قبل از فکر کردن به «امروز پستی نرفت»، "
                f"خودِ کانال رو چک کن. لاگ اجرا رو توی تب Actions گیت‌هاب هم ببین."
            )
        except Exception as alert_exc:
            print("Also failed to send the admin failure alert:", alert_exc)
        raise