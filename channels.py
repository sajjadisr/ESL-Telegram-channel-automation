"""Broadcasts a finished post to Eitaa and Bale, in addition to Telegram."""

import re

import requests

from config import EITAA_TOKEN, EITAA_CHANNEL_ID, BALE_BOT_TOKEN, BALE_CHAT_ID
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


def format_quiz_for_extra_channels(question, options, is_quiz=False, explanation=""):
    """Text fallback for platforms without native polls (Audit #3)."""
    lines = ["📝 <b>کوییز هفتگی</b>" if is_quiz else "📊 <b>نظرسنجی</b>", "", question, ""]
    for i, opt in enumerate(options, 1):
        lines.append(f"{i}. {opt}")
    if is_quiz and explanation:
        lines.extend(["", f"💡 {explanation}"])
    lines.append("")
    lines.append("👇 گزینه‌ات رو توی کامنت‌ها بگو!")
    return "\n".join(lines)


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
    if response is not None and hasattr(response, "ok") and not response.ok:
        send_admin_message(
            f"⚠️ API {name} پاسخ خطا داد: {getattr(response, 'text', response)!s}\n"
            f"تلگرام احتمالاً منتشر شده؛ لطفاً {name} رو چک کن."
        )
    return response


def send_eitaa(text):
    if not (EITAA_TOKEN and EITAA_CHANNEL_ID):
        return None
    url = f"https://eitaayar.ir/api/{EITAA_TOKEN}/sendMessage"
    body = truncate_html_safe(to_plain_text(text), suffix="...")
    try:
        response = requests.post(
            url, data={"chat_id": EITAA_CHANNEL_ID, "text": body}, timeout=20,
        )
    except requests.RequestException as exc:
        print("Eitaa network error:", exc)
        return None
    if not response.ok:
        print("Eitaa API error response:", response.text)
    return response


def send_bale(text):
    if not (BALE_BOT_TOKEN and BALE_CHAT_ID):
        return None
    url = f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/sendMessage"
    body = truncate_html_safe(to_bale_html(text), suffix="...")
    payload = {"chat_id": BALE_CHAT_ID, "text": body, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=20)
    except requests.RequestException as exc:
        print("Bale network error:", exc)
        return None
    if not response.ok:
        print("Bale API error response:", response.text)
    return response


def broadcast_extra_channels(text):
    results = {}
    for name, fn in [("eitaa", send_eitaa), ("bale", send_bale)]:
        results[name] = _send_platform(name, fn, text)
    return results
