import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, TELEGRAM_ADMIN_CHAT_ID

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_message(text, chat_id=None):
    url = f"{API_BASE}/sendMessage"
    if len(text) > 4000:
        text = text[:4000] + "..."
    response = requests.post(url, data={
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
    and show immediate right/wrong feedback on tap."""
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
    response = requests.post(url, data=payload)
    response.raise_for_status()
    return response.json()


def send_admin_image_prompt(prompt_text, label=""):
    """Hands the finished image prompt to the admin privately so they can
    paste it into whatever image tool they use — this project never calls an
    image generator itself. Falls back to printing the prompt to the workflow
    log if TELEGRAM_ADMIN_CHAT_ID isn't set, so nothing is silently lost."""
    header = f"🖼️ پرامپت تصویر برای «{label}»:\n\n" if label else "🖼️ پرامپت تصویر:\n\n"
    full_text = header + prompt_text
    if not TELEGRAM_ADMIN_CHAT_ID:
        print("=== IMAGE PROMPT (TELEGRAM_ADMIN_CHAT_ID not set — printed here instead) ===")
        print(full_text)
        print("=== END IMAGE PROMPT ===")
        return None
    return send_message(full_text, chat_id=TELEGRAM_ADMIN_CHAT_ID)
