"""Post a "what this channel is / how often it posts / where to start"
welcome message to the Telegram channel and pin it.

Run manually, once (or whenever you want to refresh the pinned message):

    python scripts/send_onboarding_message.py

This is intentionally NOT wired into the daily workflow — it's a one-time
write, not a recurring cost (Audit #9: "No onboarding for new subscribers").
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
from telegram_bot import send_message

ONBOARDING_TEXT = """👋 <b>به @InEnglish خوش اومدی!</b>

اینجا هر روز، به‌صورت خودکار، یه پست کوتاه برای یادگیری انگلیسیِ سطح مبتدی (A1–A2) منتشر می‌شه — بدون نیاز به دونستن گرامر پیچیده یا واژگان سخت.

📅 <b>برنامه‌ی هفتگی:</b>
🟢 اکثر روزها: یه صحنه‌ی کوتاه، نکته‌ی واژگان، یا داستان دنباله‌دار
🟡 گاهی: شوخی تصویری با یه اصطلاح انگلیسی
🔴 آخر هفته: کوییز یا نظرسنجی برای مرور چیزی که یاد گرفتیم

📌 <b>از کجا شروع کنم؟</b>
همینجا! هر پست خودکفاست — لازم نیست از اول بخونی. فقط با ما همراه باش و هر روز یه چیز کوچیک یاد بگیر.

سوالی داشتی یا نظری دادی، خوشحال می‌شیم بشنویم 🙌"""


def main():
    result = send_message(ONBOARDING_TEXT)
    message_id = result.get("result", {}).get("message_id")
    if message_id is None:
        print("Message sent but couldn't read message_id from response — pin it manually in the app.")
        return

    pin_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/pinChatMessage"
    pin_response = requests.post(
        pin_url,
        json={"chat_id": TELEGRAM_CHANNEL_ID, "message_id": message_id, "disable_notification": True},
        timeout=20,
    )
    if pin_response.ok:
        print("Onboarding message sent and pinned.")
    else:
        print("Onboarding message sent, but pinning failed:", pin_response.text)
        print("Pin it manually from the Telegram app if you'd like it to stay at the top.")


if __name__ == "__main__":
    main()
