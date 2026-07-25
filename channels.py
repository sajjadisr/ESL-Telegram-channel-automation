"""Broadcasts a finished post to Eitaa and Bale, in addition to Telegram."""

import re

import requests

from config import (
    EITAA_TOKEN, EITAA_CHANNEL_ID, EITAA_MAX_MESSAGE_LEN,
    BALE_BOT_TOKEN, BALE_CHAT_ID, BALE_MAX_MESSAGE_LEN,
    MESSAGE_LEN_SAFETY_MARGIN,
)
from telegram_bot import send_admin_message
from text_utils import truncate_html_safe

_TAG_STRIP = re.compile(r"<[^>]+>")
_SPOILER = re.compile(r"<tg-spoiler>(.*?)</tg-spoiler>", flags=re.DOTALL)


def _reveal_spoiler(text):
    return _SPOILER.sub(r"[پاسخ: \1]", text)


def to_plain_text(html_text):
    return _TAG_STRIP.sub("", _reveal_spoiler(html_text))


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
    """
    lines = ["📝 <b>کوییز هفتگی</b>" if is_quiz else "📊 <b>نظرسنجی</b>", "", question, ""]
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
        lines.append("🗳️ برای رأی دادن و دیدن نتیجه‌ی زنده، نسخه‌ی تلگرام کانال رو ببین: @InEnglish")
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
    "ok": false body), or None when there isn't enough information to
    tell either way (not a requests.Response at all).
    """
    if response is None or not hasattr(response, "ok"):
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


def _send_platform(name, fn, text):
    try:
        response = fn(text)
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


def send_eitaa(text):
    if not (EITAA_TOKEN and EITAA_CHANNEL_ID):
        return None
    url = f"https://eitaayar.ir/api/{EITAA_TOKEN}/sendMessage"
    max_len = EITAA_MAX_MESSAGE_LEN - MESSAGE_LEN_SAFETY_MARGIN
    body = truncate_html_safe(to_plain_text(text), max_len=max_len, suffix="...")
    try:
        response = requests.post(
            url, data={"chat_id": EITAA_CHANNEL_ID, "text": body}, timeout=20,
        )
    except requests.RequestException as exc:
        print("Eitaa network error:", exc)
        return None
    if _api_ok(response) is False:
        print("Eitaa API error response:", _api_error_detail(response))
    return response


def send_bale(text):
    if not (BALE_BOT_TOKEN and BALE_CHAT_ID):
        return None
    url = f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/sendMessage"
    max_len = BALE_MAX_MESSAGE_LEN - MESSAGE_LEN_SAFETY_MARGIN
    body = truncate_html_safe(to_bale_html(text), max_len=max_len, suffix="...")
    payload = {"chat_id": BALE_CHAT_ID, "text": body, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=20)
    except requests.RequestException as exc:
        print("Bale network error:", exc)
        return None
    if _api_ok(response) is False:
        print("Bale API error response:", _api_error_detail(response))
    return response


def broadcast_extra_channels(text):
    results = {}
    for name, fn in [("eitaa", send_eitaa), ("bale", send_bale)]:
        results[name] = _send_platform(name, fn, text)
    return results
