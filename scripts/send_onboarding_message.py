"""Post a welcome message to Telegram (pinned) and Eitaa/Bale."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from config import CHANNEL_DISPLAY_NAME, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
from telegram_bot import send_message, _post_with_retry
from channels import broadcast_extra_channels

ONBOARDING_TEXT = f"""👋 <b>به {CHANNEL_DISPLAY_NAME} خوش اومدی!</b>

اینجا هر روز، به‌صورت خودکار، یه پست کوتاه برای یادگیری انگلیسیِ سطح مبتدی (A1–A2) منتشر می‌شه — بدون نیاز به دونستن گرامر پیچیده یا واژگان سخت.

📅 <b>برنامه‌ی هفتگی:</b>
🟢 اکثر روزها: یه صحنه‌ی کوتاه، نکته‌ی واژگان، یا داستان دنباله‌دار
🟡 گاهی: شوخی تصویری با یه اصطلاح انگلیسی
🔴 آخر هفته: کوییز برای مرور چیزی که یاد گرفتیم

📌 <b>از کجا شروع کنم؟</b>
همینجا! هر پست خودکفاست — لازم نیست از اول بخونی. فقط با ما همراه باش و هر روز یه چیز کوچیک یاد بگیر.

سوالی داشتی یا نظری دادی، خوشحال می‌شیم بشنویم 🙌"""


def main():
    result = None
    try:
        result = send_message(ONBOARDING_TEXT)
    except Exception as exc:
        print("Onboarding message: Telegram send failed, continuing with extra channels:", exc)

    broadcast_extra_channels(ONBOARDING_TEXT)

    message_id = result.get("result", {}).get("message_id") if result else None
    if message_id is None:
        print("Message sent (or attempted) but couldn't read message_id — pin manually in Telegram if needed.")
        return

    pin_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/pinChatMessage"
    try:
        pin_response = _post_with_retry(
            pin_url,
            json={"chat_id": TELEGRAM_CHANNEL_ID, "message_id": message_id, "disable_notification": True},
        )
    except Exception as exc:
        print("Onboarding pin failed after retries:", exc)
        return

    if pin_response.ok:
        print("Onboarding message sent to all configured channels; pinned on Telegram.")
    else:
        print("Onboarding sent, but Telegram pinning failed:", pin_response.text)


if __name__ == "__main__":
    main()
