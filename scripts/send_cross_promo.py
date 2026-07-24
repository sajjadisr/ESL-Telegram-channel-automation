"""Post a short cross-link message to each platform with platform-appropriate text.

Run manually: python scripts/send_cross_promo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import EITAA_TOKEN, EITAA_CHANNEL_ID, BALE_BOT_TOKEN, BALE_CHAT_ID
from telegram_bot import send_message
from channels import send_eitaa, send_bale


def _eitaa_configured():
    return bool(EITAA_TOKEN and EITAA_CHANNEL_ID)


def _bale_configured():
    return bool(BALE_BOT_TOKEN and BALE_CHAT_ID)


def _telegram_text():
    lines = [
        "📢 یادت باشه @InEnglish رو فقط اینجا دنبال نکن!",
        "",
        "این کانال روی چند پلتفرم دیگه هم با همین محتوا فعاله — هرکدوم که برات راحت‌تره:",
        "🔹 تلگرام: همین‌جا (@InEnglish)",
    ]
    if _bale_configured():
        lines.append("🔹 بله: @InEnglish")
    if _eitaa_configured():
        lines.append("🔹 ایتا: @InEnglish")
    if not (_bale_configured() or _eitaa_configured()):
        lines.append("(پلتفرم‌های دیگه هنوز فعال نشدن.)")
    lines.extend(["", "اگه یکی از دوستات فقط تو یکی از این پلتفرم‌هاست، این پست رو براش فوروارد کن 🙌"])
    return "\n".join(lines)


def _extra_text(platform):
    if platform == "eitaa":
        base = ["📢 یادت باشه @InEnglish رو فقط اینجا دنبال نکن!", "", "این کانال روی چند پلتفرم دیگه هم فعاله:", "🔹 ایتا: همین‌جا (@InEnglish)", "🔹 تلگرام: @InEnglish"]
        if _bale_configured():
            base.append("🔹 بله: @InEnglish")
    else:
        base = ["📢 یادت باشه @InEnglish رو فقط اینجا دنبال نکن!", "", "این کانال روی چند پلتفرم دیگه هم فعاله:", "🔹 بله: همین‌جا (@InEnglish)", "🔹 تلگرام: @InEnglish"]
        if _eitaa_configured():
            base.append("🔹 ایتا: @InEnglish")
    base.extend(["", "اگه یکی از دوستات فقط تو یکی از این پلتفرم‌هاست، این پست رو براش فوروارد کن 🙌"])
    return "\n".join(base)


def main():
    send_message(_telegram_text())
    if _eitaa_configured():
        send_eitaa(_extra_text("eitaa"))
    if _bale_configured():
        send_bale(_extra_text("bale"))
    print("Cross-promo message sent (per-platform text).")


if __name__ == "__main__":
    main()
