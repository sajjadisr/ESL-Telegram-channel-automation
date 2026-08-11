import time

import requests

import config
from text_utils import truncate_html_safe

REQUEST_TIMEOUT = 20  # seconds — an actual network hang no longer blocks the job.
MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_SECONDS = 3

# Bug fix: Telegram's own Bot API changelog (core.telegram.org/bots/api-changelog)
# has moved this twice recently -- max raised 10 -> 12 (Bot API 9.1, Jul 2025),
# min lowered 2 -> 1 (Bot API 10.0, May 2026). These were previously not
# validated at all here; now checked against the CURRENT documented bounds
# instead of a guessed/stale range.
POLL_MIN_OPTIONS = 1
POLL_MAX_OPTIONS = 12


def _api_base():
    """Bug fix: this used to be a module-level constant computed once at
    import time from config.TELEGRAM_BOT_TOKEN. Since that constant no
    longer crashes at import if unset (see config.require), building the
    URL lazily here means a missing token is caught by the explicit
    require() call below with a clear error, rather than silently baking
    an empty/wrong token into a URL for the rest of the process."""
    return f"https://api.telegram.org/bot{config.require('TELEGRAM_BOT_TOKEN')}"


def _resolve_chat_id(chat_id):
    """Bug fix: validates the EFFECTIVE chat id (after the caller's
    override, if any, is applied) rather than blindly trusting
    config.TELEGRAM_CHANNEL_ID to be non-empty. Raises a clear error
    instead of silently sending to an empty chat_id and getting back a
    confusing Telegram error."""
    effective = chat_id or config.TELEGRAM_CHANNEL_ID
    if not effective:
        raise RuntimeError(
            "No Telegram chat id to send to: TELEGRAM_CHANNEL_ID is not set "
            "and no explicit chat_id was passed to this call."
        )
    return effective


def _post_with_retry(url, **kwargs):
    """POST with a timeout and retry-with-backoff for transient errors.

    Bug fix (duplicate-send risk): a requests.exceptions.Timeout means we
    genuinely don't know whether Telegram received and processed the
    request before our socket gave up waiting for the response -- retrying
    blindly in that case can create a real duplicate post/poll on the live
    channel. A requests.exceptions.ConnectionError (refused, DNS failure,
    reset before any response) means the request never reached the server
    in a way that could have been processed, so retrying that IS safe, and
    so is retrying a 5xx (Telegram's own server explicitly signaling it did
    NOT complete the request). Only the Timeout case is now treated
    differently: it's raised immediately, distinctly labeled, rather than
    silently retried.
    """
    last_exc = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(url, timeout=REQUEST_TIMEOUT, **kwargs)
        except requests.exceptions.Timeout as exc:
            raise RuntimeError(
                f"Telegram request timed out waiting for a response ({exc}). "
                f"This is deliberately NOT auto-retried: Telegram may have "
                f"already received and processed the original request, and "
                f"blindly retrying could double-post. Check the channel "
                f"before manually retrying this specific action."
            ) from exc
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
    chat_id = _resolve_chat_id(chat_id)
    url = f"{_api_base()}/sendMessage"
    text = truncate_html_safe(text)
    response = _post_with_retry(url, data={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    })
    if not response.ok:
        print("Telegram API error response:", response.text)
    response.raise_for_status()
    return response.json()


def send_photo(image_bytes, caption, chat_id=None):
    """Post a generated image with its caption in one message. Telegram
    caps photo captions at 1024 chars — separate from the 4096-char limit
    truncate_html_safe's default targets for sendMessage — so this passes
    max_len explicitly rather than relying on the default."""
    chat_id = _resolve_chat_id(chat_id)
    url = f"{_api_base()}/sendPhoto"
    caption = truncate_html_safe(caption, max_len=1024)
    response = _post_with_retry(
        url,
        data={
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML",
        },
        files={"photo": ("image.png", image_bytes, "image/png")},
    )
    if not response.ok:
        print("Telegram sendPhoto API error response:", response.text)
    response.raise_for_status()
    return response.json()


def send_document(image_bytes, caption, chat_id=None):
    """Fallback for send_photo. Telegram's photo pipeline re-encodes and
    enforces its own dimension/aspect-ratio rules on top of the documented
    10MB/10000px/20:1 limits; sendDocument skips all of that and uploads
    the bytes as-is, so it's a reasonable last resort if sendPhoto rejects
    an otherwise-fine image. The post shows up as a file attachment rather
    than an inline photo — worse presentation, but still fully automatic,
    which beats falling all the way back to a manual admin hand-off."""
    chat_id = _resolve_chat_id(chat_id)
    url = f"{_api_base()}/sendDocument"
    caption = truncate_html_safe(caption, max_len=1024)
    response = _post_with_retry(
        url,
        data={
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML",
        },
        files={"document": ("image.png", image_bytes, "image/png")},
    )
    if not response.ok:
        print("Telegram sendDocument API error response:", response.text)
    response.raise_for_status()
    return response.json()


def send_voice(ogg_bytes, caption, chat_id=None):
    """Post a generated voice note with its caption. Telegram's sendVoice
    requires the audio as OGG encoded with Opus specifically (Bot API
    docs) — anything else is silently rejected or misplayed, which is why
    voice_note.py always converts to that exact format before this is
    ever called. Caption cap is the same 1024 chars as sendPhoto/
    sendDocument."""
    chat_id = _resolve_chat_id(chat_id)
    url = f"{_api_base()}/sendVoice"
    caption = truncate_html_safe(caption, max_len=1024)
    response = _post_with_retry(
        url,
        data={
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML",
        },
        files={"voice": ("voice_note.ogg", ogg_bytes, "audio/ogg")},
    )
    if not response.ok:
        print("Telegram sendVoice API error response:", response.text)
    response.raise_for_status()
    return response.json()


def send_poll(question, options, is_quiz=False, correct_option_id=None, explanation=None):
    """Native Telegram poll/quiz — a real poll object, not text. Vote polls
    (is_quiz=False) have no right answer; quiz polls mark one option correct
    and show immediate right/wrong feedback on tap.

    Sent as JSON (not form-encoded): requests.post(..., data=payload) with a
    list-valued field ("options") repeats the key instead of producing the
    single JSON-array-string Telegram's sendPoll actually expects, which is
    exactly why this used to fail with 400 Bad Request every time.

    Bug fixes:
    - Option count is now validated against Telegram's CURRENT documented
      bounds (POLL_MIN_OPTIONS/POLL_MAX_OPTIONS above) before ever sending,
      raising a clear, specific error instead of letting a malformed
      request fail at Telegram with a generic 400.
    - The payload now sends correct_option_ids (a list) instead of the
      singular correct_option_id: Telegram's Bot API changelog documents
      that sendPoll's correct_option_id parameter was replaced by
      correct_option_ids in Bot API 9.6. This project's quizzes only ever
      have one right answer, so it's sent as a single-element list.
    """
    if not (POLL_MIN_OPTIONS <= len(options) <= POLL_MAX_OPTIONS):
        raise ValueError(
            f"send_poll: {len(options)} options given, but Telegram requires "
            f"between {POLL_MIN_OPTIONS} and {POLL_MAX_OPTIONS}."
        )
    if is_quiz and not isinstance(correct_option_id, int):
        raise ValueError("send_poll: is_quiz=True requires an integer correct_option_id.")
    if is_quiz and not (0 <= correct_option_id < len(options)):
        raise ValueError(
            f"send_poll: correct_option_id {correct_option_id!r} is out of range "
            f"for {len(options)} options."
        )

    chat_id = _resolve_chat_id(None)
    url = f"{_api_base()}/sendPoll"
    payload = {
        "chat_id": chat_id,
        "question": question[:300],
        "options": [opt[:100] for opt in options],
        "is_anonymous": True,
        "type": "quiz" if is_quiz else "regular",
    }
    if is_quiz:
        payload["correct_option_ids"] = [correct_option_id]
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
    chat_id = _resolve_chat_id(chat_id)
    url = f"{_api_base()}/stopPoll"
    payload = {"chat_id": chat_id, "message_id": message_id}
    try:
        response = _post_with_retry(url, json=payload)
    except (requests.RequestException, RuntimeError) as exc:
        print("Telegram stopPoll network error:", exc)
        return None
    if not response.ok:
        print("Telegram stopPoll API error response:", response.text)
        return None
    return response.json()


def send_admin_message(text):
    """Generic 'message the admin' primitive. Never raises — alerting must not
    crash the run (Audit #21)."""
    if not config.TELEGRAM_ADMIN_CHAT_ID:
        print("=== ADMIN MESSAGE (TELEGRAM_ADMIN_CHAT_ID not set — printed here instead) ===")
        print(text)
        print("=== END ADMIN MESSAGE ===")
        return None
    try:
        return send_message(text, chat_id=config.TELEGRAM_ADMIN_CHAT_ID)
    except Exception as exc:  # noqa: BLE001 — alert path must never take down main()
        print("send_admin_message failed (admin alert lost, run continues):", exc)
        return None


def send_admin_image_prompt(prompt_text, label=""):
    """Hands the finished image prompt to the admin so they can paste it
    into whatever image tool they use — this project never calls an image
    generator itself."""
    header = f"🖼️ پرامپت تصویر برای «{label}»:\n\n" if label else "🖼️ پرامپت تصویر:\n\n"
    return send_admin_message(header + prompt_text)
