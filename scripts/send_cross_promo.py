"""Post a short "also on Telegram/Bale/Eitaa" cross-link message to all
configured channels. Nothing in a normal post ever mentions the other
platforms, so someone who finds the channel on one has no path to the
others (Audit #9). Meant to run infrequently (e.g. monthly) — see the
matching workflow at .github/workflows/monthly_cross_promo.yml.

Run manually:

    python scripts/send_cross_promo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import EITAA_TOKEN, EITAA_CHANNEL_ID, BALE_BOT_TOKEN, BALE_CHAT_ID
from telegram_bot import send_message
from channels import broadcast_extra_channels

CROSS_PROMO_TEXT = """📢 یادت باشه @InEnglish رو فقط اینجا دنبال نکن!

این کانال روی چند پلتفرم دیگه هم با همین محتوا فعاله — هرکدوم که برات راحت‌تره:
🔹 تلگرام: همین‌جا
🔹 بله و ایتا: همون آیدی @InEnglish

اگه یکی از دوستات فقط تو یکی از این پلتفرم‌هاست، این پست رو براش فوروارد کن 🙌"""


def main():
    configured_extra = bool(EITAA_TOKEN and EITAA_CHANNEL_ID) or bool(BALE_BOT_TOKEN and BALE_CHAT_ID)
    if not configured_extra:
        print("No extra platform (Eitaa/Bale) is configured — nothing to cross-promote yet. "
              "Sending to Telegram only.")

    send_message(CROSS_PROMO_TEXT)
    broadcast_extra_channels(CROSS_PROMO_TEXT)
    print("Cross-promo message sent.")


if __name__ == "__main__":
    main()
