"""Post a short cross-link message to each platform with platform-appropriate text.

Run manually: python scripts/send_cross_promo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CHANNEL_DISPLAY_NAME, EITAA_TOKEN, EITAA_CHANNEL_ID, BALE_BOT_TOKEN, BALE_CHAT_ID
from telegram_bot import send_message
from channels import broadcast_extra_channels


def _eitaa_configured():
    return bool(EITAA_TOKEN and EITAA_CHANNEL_ID)


def _bale_configured():
    return bool(BALE_BOT_TOKEN and BALE_CHAT_ID)


def _telegram_text():
    lines = [
        f"📢 یادت باشه {CHANNEL_DISPLAY_NAME} رو فقط اینجا دنبال نکن!",
        "",
        "این کانال روی چند پلتفرم دیگه هم با همین محتوا فعاله — هرکدوم که برات راحت‌تره:",
        f"🔹 تلگرام: همین‌جا ({CHANNEL_DISPLAY_NAME})",
    ]
    if _bale_configured():
        lines.append(f"🔹 بله: {CHANNEL_DISPLAY_NAME}")
    if _eitaa_configured():
        lines.append(f"🔹 ایتا: {CHANNEL_DISPLAY_NAME}")
    if not (_bale_configured() or _eitaa_configured()):
        lines.append("(پلتفرم‌های دیگه هنوز فعال نشدن.)")
    lines.extend(["", "اگه یکی از دوستات فقط تو یکی از این پلتفرم‌هاست، این پست رو براش فوروارد کن 🙌"])
    return "\n".join(lines)


def _extra_text():
    lines = [
        f"📢 یادت باشه {CHANNEL_DISPLAY_NAME} رو فقط اینجا دنبال نکن!",
        "",
        "این کانال روی چند پلتفرم دیگه هم فعاله:",
        f"🔹 تلگرام: {CHANNEL_DISPLAY_NAME}",
    ]
    if _bale_configured():
        lines.append(f"🔹 بله: {CHANNEL_DISPLAY_NAME}")
    if _eitaa_configured():
        lines.append(f"🔹 ایتا: {CHANNEL_DISPLAY_NAME}")
    lines.extend(["", "اگه یکی از دوستات فقط تو یکی از این پلتفرم‌هاست، این پست رو براش فوروارد کن 🙌"])
    return "\n".join(lines)


def main():
    try:
        send_message(_telegram_text())
    except Exception as exc:
        print("Cross-promo: Telegram send failed, continuing with extra channels:", exc)

    extra_results = broadcast_extra_channels(_extra_text())
    print("Cross-promo message sent. Extra channel results:", extra_results)


if __name__ == "__main__":
    main()
