"""Broadcasts a finished post to Eitaa and Bale, in addition to Telegram."""

import html
import re

import requests

import config
from telegram_bot import send_admin_message
from text_utils import truncate_html_safe

# Bug fix (#18): this used to be re.compile(r"<[^>]+>") -- ANY "<...>" span,
# which eats legitimate content that isn't a tag at all (e.g. a sentence
# using a literal "<" or ">" as a comparison, or an emoticon like "<3").
# Restricting the match to an explicit allowlist of tag names this project
# (and Telegram's own supported HTML subset) actually uses means a bare
# "<" that isn't immediately followed by one of these exact names can never
# match, so it survives untouched.
_KNOWN_TAGS = "b|strong|i|em|u|ins|s|strike|del|code|pre|a|blockquote|tg-spoiler|tg-emoji|span"
_TAG_STRIP = re.compile(rf"</?(?:{_KNOWN_TAGS})(?:\s[^>]*)?>", re.IGNORECASE)
_SPOILER = re.compile(r"<tg-spoiler>(.*?)</tg-spoiler>", flags=re.DOTALL)


class _NotConfigured:
    """Sentinel returned by send_eitaa/send_bale/send_eitaa_photo/
    send_bale_photo when that platform's credentials aren't set.

    Bug fix (#22): this used to be plain None, indistinguishable from
    "we tried and it failed" once a real failure ALSO started propagating
    as/through None. Analytics (_summarize_delivery) and anything else
    downstream can now tell "deliberately never turned on" apart from
    "configured but broken" using the return value alone.
    """
    def __repr__(self):
        return "NOT_CONFIGURED"

    def __bool__(self):
        return False


NOT_CONFIGURED = _NotConfigured()


def _reveal_spoiler(text):
    return _SPOILER.sub(r"[پاسخ: \1]", text)


def to_plain_text(html_text):
    """Bug fix (#19): html.unescape() added. This used to leave entities
    like &amp;/&quot;/&#39; literally in the Eitaa/Bale plain-text output
    instead of decoding them back to the characters they represent."""
    return html.unescape(_TAG_STRIP.sub("", _reveal_spoiler(html_text)))


def to_bale_html(html_text):
    return _reveal_spoiler(html_text)


def format_poll_results_for_extra_channels(question, tally, total_votes, is_quiz=False, correct_index=None):
    """Audit: format_quiz_for_extra_channels's vote_poll fallback tells
    Eitaa/Bale readers to go vote on Telegram, but nothing was ever sent
    back to them once the poll actually closed — harvest_pending_polls()
    computes the real tally and then only saves it internally. This is the
    follow-up message that closes that dead end: a short "results are in"
    recap, posted to Eitaa/Bale once poll_feedback.py has the real numbers.
    (Telegram doesn't need this — its native poll UI already shows live/
    final results to whoever voted there, in-client.)"""
    lines = ["📊 <b>نتیجه‌ی نظرسنجی</b>" if not is_quiz else "📊 <b>نتیجه‌ی کوییز</b>", "", question, ""]
    for i, item in enumerate(tally):
        marker = f"{item['text']}: {item['votes']} رأی"
        if is_quiz and isinstance(correct_index, int) and i == correct_index:
            marker += " ✅"
        lines.append(marker)
    lines.append("")
    lines.append(f"(مجموع {total_votes} رأی)")
    return "\n".join(lines)


def format_quiz_for_extra_channels(question, options, is_quiz=False, explanation="",
                                    correct_index=None):
    """Text fallback for platforms without native polls (Audit #3).

    Platform-awareness fix: this used to close with "بگو توی کامنت‌ها"
    (tell us in the comments), which assumes a comments/discussion feature.
    Neither Eitaa's nor Bale's bot API exposes anything like Telegram's
    linked-discussion-group comments, and this project has no way to know
    whether the *Telegram* channel even has one linked either (that's a
    channel setting, not something visible to a cron-only Bot-API script) —
    so a "comment your answer" CTA can't be relied on to work on any of the
    three. Instead: for a quiz (there's a right answer), the correct option
    is revealed inline via the same <tg-spoiler> convention used elsewhere,
    so Eitaa/Bale readers get a complete, self-contained answer instead of
    an ask they may have no way to act on. For a vote (no right answer,
    nothing to reveal), the CTA points to the Telegram channel instead,
    where the real, live poll actually exists.

    Bug fixes:
    - #85: the quiz label used to unconditionally say "کوییز هفتگی" (Weekly
      Quiz). quiz only has a FLOOR of one slot/week in schedule_builder.py —
      it can win extra slots the same week if its score favors it — so
      "weekly" isn't a guarantee. Now just "کوییز" (Quiz), which is true
      regardless of how many times it runs this week.
    - #93: the vote-poll fallback used to hardcode "@InEnglish" as the
      Telegram channel to go check, completely independent of the actual
      configured channel. Now uses config.CHANNEL_DISPLAY_NAME.
    """
    lines = ["📝 <b>کوییز</b>" if is_quiz else "📊 <b>نظرسنجی</b>", "", question, ""]
    for i, opt in enumerate(options, 1):
        marker = f"{i}. {opt}"
        if is_quiz and isinstance(correct_index, int) and i - 1 == correct_index:
            lines.append(f"<tg-spoiler>{marker} ✅</tg-spoiler>")
        else:
            lines.append(marker)
    if is_quiz and explanation:
        lines.extend(["", f"💡 {explanation}"])
    lines.append("")
    if is_quiz:
        lines.append("🔎 جواب درست داخل اسپویلِ بالا مخفی شده — قبل از دیدنش خودت امتحان کن!")
    else:
        lines.append(f"🗳️ برای رأی دادن و دیدن نتیجه‌ی زنده، نسخه‌ی تلگرام کانال رو ببین: {config.CHANNEL_DISPLAY_NAME}")
    return "\n".join(lines)


def _api_ok(response):
    """True/False/None verdict on whether a send actually succeeded, by
    cross-checking the HTTP status against the response body.

    Why this exists: eitaayar.ir's own docs are explicit that a failed
    send isn't reliably told apart from a successful one by HTTP status
    alone — you have to look at the "ok" field in the JSON body (a failed
    send can still come back looking like an ordinary response). Bale's
    Bot API mirrors Telegram's {"ok": ..., "description": ...} envelope
    closely enough that the same defensive check costs nothing there
    either. Telegram itself (telegram_bot.py) is NOT routed through this —
    its Bot API reliably matches HTTP status to the "ok" field, so
    raise_for_status() there is already the right, platform-specific
    check; duplicating this looser check on top of it would only hide a
    real Telegram error behind a False that never gets raised.

    Returns True (delivered), False (explicit failure — HTTP-level or an
    "ok": false body), None for NOT_CONFIGURED (deliberately not "false" —
    that's not a failure, so _send_platform shouldn't alert on it), or None
    when there isn't enough information to tell either way (not a
    requests.Response at all).
    """
    if response is NOT_CONFIGURED or response is None or not hasattr(response, "ok"):
        return None
    if not response.ok:
        return False
    try:
        body = response.json()
    except ValueError:
        return True  # 2xx with a non-JSON/empty body — take the HTTP status at face value
    if isinstance(body, dict) and body.get("ok") is False:
        return False
    return True


def _api_error_detail(response):
    """Best-effort human-readable failure reason, preferring the platform's
    own "description"/"message" field (from the JSON body) over the raw
    HTTP response text, since the body is usually the more specific of
    the two — see _api_ok's docstring for why the body has to be checked
    at all."""
    try:
        body = response.json()
    except (ValueError, AttributeError):
        return getattr(response, "text", str(response))
    if isinstance(body, dict):
        return body.get("description") or body.get("message") or str(body)
    return str(body)


def _send_platform(name, fn, *args):
    """Bug fix (#15/#16): send_eitaa/send_bale used to catch their own
    requests.RequestException internally and return None on a genuine
    network failure — indistinguishable from "nothing went wrong yet, no
    information available", which meant _api_ok(None) was never False,
    so the alert below never fired for a real, definite delivery failure.
    Those functions no longer swallow network errors (they let them
    propagate); this is where they're actually caught and alerted on now.
    """
    try:
        response = fn(*args)
    except Exception as exc:  # noqa: BLE001
        print(f"{name} send failed unexpectedly:", exc)
        send_admin_message(
            f"⚠️ ارسال به {name} امروز شکست خورد: {exc}\n"
            f"تلگرام احتمالاً منتشر شده؛ لطفاً {name} رو چک کن."
        )
        return None
    if _api_ok(response) is False:
        send_admin_message(
            f"⚠️ API {name} پاسخ خطا داد: {_api_error_detail(response)}\n"
            f"تلگرام احتمالاً منتشر شده؛ لطفاً {name} رو چک کن."
        )
    return response


def _send_platform_photo(name, photo_fn, text_fn, image_bytes, caption):
    """Send image+caption on one extra channel; if the photo upload itself
    doesn't clearly succeed — network error, non-OK response, or an
    exception — fall back to sending the caption as plain text via
    text_fn, the same already-proven function broadcast_extra_channels
    uses. This matters most for Eitaa: its file-upload endpoint isn't
    precisely documented anywhere public (see send_eitaa_photo's
    docstring), so this fallback is what keeps a wrong guess there from
    costing the channel its post entirely — worst case is exactly what
    happened before this feature existed (caption only, no photo).

    Bug fix: if the platform simply isn't configured, photo_fn and text_fn
    share the exact same credential check, so attempting the text fallback
    is guaranteed to be equally not-configured — skip it instead of
    printing a misleading "photo upload didn't succeed" for a platform
    that was never turned on in the first place.
    """
    try:
        response = photo_fn(image_bytes, caption)
    except Exception as exc:  # noqa: BLE001
        print(f"{name} photo send failed unexpectedly:", exc)
        response = None

    if response is NOT_CONFIGURED:
        return {"photo": NOT_CONFIGURED}

    if _api_ok(response) is True:
        return {"photo": response}

    if response is not None:
        print(f"{name} photo API error response:", _api_error_detail(response))
    print(f"{name}: photo upload didn't succeed — falling back to a text-only caption "
          f"so the channel isn't left with nothing.")
    return {"photo": response, "text_fallback": _send_platform(name, text_fn, caption)}


def send_eitaa(text):
    """Bug fix (#15): used to catch requests.RequestException here and
    return None — indistinguishable from "not configured" or "no info
    yet", so a genuine network failure never reached _send_platform's
    alert logic. Now lets it propagate; _send_platform is what catches
    and alerts on it."""
    if not (config.EITAA_TOKEN and config.EITAA_CHANNEL_ID):
        return NOT_CONFIGURED
    url = f"https://eitaayar.ir/api/{config.EITAA_TOKEN}/sendMessage"
    max_len = config.EITAA_MAX_MESSAGE_LEN - config.MESSAGE_LEN_SAFETY_MARGIN
    body = truncate_html_safe(to_plain_text(text), max_len=max_len, suffix="...")
    response = requests.post(
        url, data={"chat_id": config.EITAA_CHANNEL_ID, "text": body}, timeout=20,
    )
    if _api_ok(response) is False:
        print("Eitaa API error response:", _api_error_detail(response))
    return response


def send_eitaa_photo(image_bytes, caption):
    """Best-effort: eitaayar.ir has no precise, official English API
    reference for file uploads. This follows the shape used by the
    community eitaapykit/eitaa wrapper — send_file(chat_id, caption,
    file) — extrapolated onto the same REST pattern send_eitaa above
    already relies on (https://eitaayar.ir/api/{token}/sendFile, mirroring
    .../sendMessage). If the endpoint or field name guessed here is wrong,
    this fails the same defensive way every other extra-channel call does
    (_api_ok catches it), and _send_platform_photo's caller falls back to
    a text-only caption — so a wrong guess degrades gracefully instead of
    silently losing the post.

    Bug fixes: (#15) network errors now propagate instead of being
    swallowed into None, same reasoning as send_eitaa. (#17) caption is
    now capped at 1024 chars like every other photo-caption path in this
    codebase (Telegram's sendPhoto/sendDocument/sendVoice, and
    send_bale_photo) — it used to use the full ~4000-char text-message
    limit instead, risking a caption-too-long rejection if Eitaa enforces
    a photo-specific limit the way Telegram does.
    """
    if not (config.EITAA_TOKEN and config.EITAA_CHANNEL_ID):
        return NOT_CONFIGURED
    url = f"https://eitaayar.ir/api/{config.EITAA_TOKEN}/sendFile"
    max_len = min(config.EITAA_MAX_MESSAGE_LEN - config.MESSAGE_LEN_SAFETY_MARGIN, 1024)
    caption_text = truncate_html_safe(to_plain_text(caption), max_len=max_len, suffix="...")
    response = requests.post(
        url,
        data={"chat_id": config.EITAA_CHANNEL_ID, "caption": caption_text},
        files={"file": ("image.png", image_bytes, "image/png")},
        timeout=30,
    )
    if _api_ok(response) is False:
        print("Eitaa sendFile API error response:", _api_error_detail(response))
    return response


def send_bale(text):
    """Bug fix (#15): see send_eitaa's docstring — network errors now
    propagate instead of being swallowed into None."""
    if not (config.BALE_BOT_TOKEN and config.BALE_CHAT_ID):
        return NOT_CONFIGURED
    url = f"https://tapi.bale.ai/bot{config.BALE_BOT_TOKEN}/sendMessage"
    max_len = config.BALE_MAX_MESSAGE_LEN - config.MESSAGE_LEN_SAFETY_MARGIN
    body = truncate_html_safe(to_bale_html(text), max_len=max_len, suffix="...")
    payload = {"chat_id": config.BALE_CHAT_ID, "text": body, "parse_mode": "HTML"}
    response = requests.post(url, json=payload, timeout=20)
    if _api_ok(response) is False:
        print("Bale API error response:", _api_error_detail(response))
    return response


def send_bale_photo(image_bytes, caption):
    """Bale's Bot API is a documented, close mirror of Telegram's Bot API
    (same tapi.bale.ai/bot{token}/<method> shape, same official sample
    code using a Telegram-bot-style client pointed at Bale's base URL) —
    unlike Eitaa, this isn't a guess: sendPhoto works the same way,
    multipart upload with a "photo" field and an HTML caption.

    Bug fix (#15): see send_eitaa's docstring — network errors now
    propagate instead of being swallowed into None."""
    if not (config.BALE_BOT_TOKEN and config.BALE_CHAT_ID):
        return NOT_CONFIGURED
    url = f"https://tapi.bale.ai/bot{config.BALE_BOT_TOKEN}/sendPhoto"
    max_len = config.BALE_MAX_MESSAGE_LEN - config.MESSAGE_LEN_SAFETY_MARGIN
    caption_text = truncate_html_safe(to_bale_html(caption), max_len=min(max_len, 1024), suffix="...")
    response = requests.post(
        url,
        data={"chat_id": config.BALE_CHAT_ID, "caption": caption_text, "parse_mode": "HTML"},
        files={"photo": ("image.png", image_bytes, "image/png")},
        timeout=30,
    )
    if _api_ok(response) is False:
        print("Bale sendPhoto API error response:", _api_error_detail(response))
    return response


def broadcast_extra_channels(text):
    results = {}
    for name, fn in [("eitaa", send_eitaa), ("bale", send_bale)]:
        results[name] = _send_platform(name, fn, text)
    return results


def broadcast_extra_channels_photo(image_bytes, caption):
    """Auto cross-post the generated image to Eitaa/Bale (Audit: this
    format used to never cross-post automatically at all — the admin got
    the caption+prompt and had to post everywhere by hand). Each platform
    falls back to a text-only caption if its own photo upload fails, via
    _send_platform_photo, so the worst case per platform is exactly the
    old manual-caption behavior rather than nothing."""
    results = {}
    for name, photo_fn, text_fn in [
        ("eitaa", send_eitaa_photo, send_eitaa),
        ("bale", send_bale_photo, send_bale),
    ]:
        results[name] = _send_platform_photo(name, photo_fn, text_fn, image_bytes, caption)
    return results
