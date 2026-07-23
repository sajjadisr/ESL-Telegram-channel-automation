"""Broadcasts a finished post to Eitaa and Bale, in addition to Telegram.

Each platform is independent by design:
- A missing token/ID for a platform just skips that platform (see config.py).
- A network error or API error on one platform is caught and logged, never
  raised — one platform failing must never stop the others from posting, and
  must never crash the whole daily-post run (Telegram already succeeded by
  the time this runs, and that shouldn't be undone by an Eitaa/Bale hiccup).

Formatting note: posts are generated with Telegram-flavoured HTML
(<b>, <i>, <tg-spoiler>). Bale's Bot API is modeled closely on Telegram's and
documented to support the same parse_mode="HTML" with the same standard tags,
so Bale gets the HTML almost as-is (only <tg-spoiler>, a Telegram-only tag
with no Bale equivalent, gets converted). Eitaa (via Eitaayar) has no
confirmed HTML/Markdown support in its channel-posting API, so it gets clean
plain text instead of risking literal "<b>" tags showing up in the channel.
"""

import re

import requests

from config import EITAA_TOKEN, EITAA_CHANNEL_ID, BALE_BOT_TOKEN, BALE_CHAT_ID

_TAG_STRIP = re.compile(r"<[^>]+>")
_SPOILER = re.compile(r"<tg-spoiler>(.*?)</tg-spoiler>", flags=re.DOTALL)


def _reveal_spoiler(text):
    """Bale/Eitaa have no tap-to-reveal spoiler feature, so the hidden
    answer (used by spot_mistake) is shown directly instead, marked so it
    still reads as "the answer" rather than plain body text."""
    return _SPOILER.sub(r"[پاسخ: \1]", text)


def to_plain_text(html_text):
    """Strip all HTML tags for platforms with no confirmed rich-formatting
    support (Eitaa)."""
    return _TAG_STRIP.sub("", _reveal_spoiler(html_text))


def to_bale_html(html_text):
    """Bale supports the same HTML tags as Telegram, just not tg-spoiler."""
    return _reveal_spoiler(html_text)


def send_eitaa(text):
    if not (EITAA_TOKEN and EITAA_CHANNEL_ID):
        return None
    url = f"https://eitaayar.ir/api/{EITAA_TOKEN}/sendMessage"
    body = to_plain_text(text)
    if len(body) > 4000:
        body = body[:4000] + "..."
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
    body = to_bale_html(text)
    if len(body) > 4000:
        body = body[:4000] + "..."
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
    """Send the same finished post to every configured extra channel.
    Call this alongside telegram_bot.send_message, not instead of it."""
    results = {}
    for name, fn in [("eitaa", send_eitaa), ("bale", send_bale)]:
        try:
            results[name] = fn(text)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: one
            # platform's unexpected failure must never take down the run.
            print(f"{name} send failed unexpectedly:", exc)
            results[name] = None
    return results
