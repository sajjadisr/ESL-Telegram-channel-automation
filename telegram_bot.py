import time

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, TELEGRAM_ADMIN_CHAT_ID

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

REQUEST_TIMEOUT = 20  # seconds — an actual network hang no longer blocks the job.
MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_SECONDS = 3


def _post_with_retry(url, **kwargs):
    """POST with a timeout and retry-with-backoff for transient errors
    (network blips, Telegram 5xx). 4xx errors are NOT retried — a bad
    request/payload fails the same way every time, so retrying just wastes
    time; it's returned as-is so the caller can log/raise on it."""
    last_exc = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(url, timeout=REQUEST_TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < MAX_ATTEMPTS:
                print(f"Telegram network error (attempt {attempt}/{MAX_ATTEMPTS}): {exc}. Retrying...")
                time.sleep(_RETRY_BASE_DELAY_SECONDS * attempt)
                continue
            raise
        if response.status_code >= 500 and attempt < MAX_ATTEMPTS:
            print(f"Telegram server error {response.status_code} (attempt {attempt}/{MAX_ATTEMPTS}). Retrying...")
            time.sleep(_RETRY_BASE_DELAY_SECONDS * attempt)
            continue
        return response
    raise last_exc


def send_message(text, chat_id=None):
    url = f"{API_BASE}/sendMessage"
    if len(text) > 4000:
        text = text[:4000] + "..."
    response = _post_with_retry(url, data={
        "chat_id": chat_id or TELEGRAM_CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
    })
    if not response.ok:
        print("Telegram API error response:", response.text)
    response.raise_for_status()
    return response.json()


def send_poll(question, options, is_quiz=False, correct_option_id=None, explanation=None):
    """Native Telegram poll/quiz — a real poll object, not text. Vote polls
    (is_quiz=False) have no right answer; quiz polls mark one option correct
    and show immediate right/wrong feedback on tap.

    Sent as JSON (not form-encoded): requests.post(..., data=payload) with a
    list-valued field ("options") repeats the key instead of producing the
    single JSON-array-string Telegram's sendPoll actually expects, which is
    exactly why this used to fail with 400 Bad Request every time."""
    url = f"{API_BASE}/sendPoll"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "question": question[:300],
        "options": [opt[:100] for opt in options],
        "is_anonymous": True,
        "type": "quiz" if is_quiz else "regular",
    }
    if is_quiz:
        payload["correct_option_id"] = correct_option_id
        if explanation:
            payload["explanation"] = explanation[:200]
    response = _post_with_retry(url, json=payload)
    if not response.ok:
        print("Telegram API error response:", response.text)
    response.raise_for_status()
    return response.json()


def stop_poll(message_id, chat_id=None):
    """Close a previously-sent poll and return Telegram's final tally
    (per-option voter_count) — works for anonymous polls too, unlike the
    poll_answer webhook update, which anonymous polls never send and which a
    cron-only bot could never receive live anyway. This is how
    poll_feedback.py turns yesterday's quiz/poll into real feedback.json
    signal without needing a listening server (Audit #5).

    Returns None (and logs) on failure instead of raising, since a poll that
    can't be stopped (already closed, transient error, etc.) shouldn't take
    down the rest of the run — the caller just leaves it pending and tries
    again next time."""
    url = f"{API_BASE}/stopPoll"
    payload = {"chat_id": chat_id or TELEGRAM_CHANNEL_ID, "message_id": message_id}
    try:
        response = _post_with_retry(url, json=payload)
    except requests.RequestException as exc:
        print("Telegram stopPoll network error:", exc)
        return None
    if not response.ok:
        print("Telegram stopPoll API error response:", response.text)
        return None
    return response.json()


def send_admin_message(text):
    """Generic 'message the admin' primitive. Falls back to printing to the
    workflow log if TELEGRAM_ADMIN_CHAT_ID isn't set, so nothing is silently
    lost. Used for image-generation prompts AND operational alerts (low
    topic supply, broken quiz JSON, etc. — Audit #1, #4)."""
    if not TELEGRAM_ADMIN_CHAT_ID:
        print("=== ADMIN MESSAGE (TELEGRAM_ADMIN_CHAT_ID not set — printed here instead) ===")
        print(text)
        print("=== END ADMIN MESSAGE ===")
        return None
    return send_message(text, chat_id=TELEGRAM_ADMIN_CHAT_ID)


def send_admin_image_prompt(prompt_text, label=""):
    """Hands the finished image prompt to the admin so they can paste it
    into whatever image tool they use — this project never calls an image
    generator itself."""
    header = f"🖼️ پرامپت تصویر برای «{label}»:\n\n" if label else "🖼️ پرامپت تصویر:\n\n"
    return send_admin_message(header + prompt_text)
