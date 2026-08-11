"""End-of-day dead-man's-switch for daily_post.yml.

The primary + catch-up triggers in daily_post.yml (see its schedule
comments) make an individual missed/delayed cron mostly self-healing, but
they can't cover a day where GitHub Actions never actually ran anything for
this repo at all — a platform-wide outage, a workflow accidentally disabled,
a secrets/permissions change that breaks the checkout step, etc. That's the
one gap left, and it's exactly the kind of failure that's otherwise silent:
main.py's own admin alerts (see main.py's __main__ block) only fire from
*inside* a run that actually started.

This runs once, late in the Tehran day, after slot 3 and its catch-up have
both had their chance, and just asks: did today actually reach
POSTS_PER_DAY? If not, someone should know today, not stumble onto it days
later. Deliberately minimal — this checks a count and sends one message,
it isn't a monitoring system.

Run manually: python scripts/check_daily_completion.py
"""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clock
from config import POSTS_PER_DAY
from database import count_posts_on_date
from telegram_bot import send_admin_message


def main():
    today_str = clock.today_str()
    posted_today = count_posts_on_date(today_str)

    if posted_today < POSTS_PER_DAY:
        send_admin_message(
            f"🔴 امروز ({today_str}) فقط {posted_today} از {POSTS_PER_DAY} پست منتشر شد.\n\n"
            f"یعنی امروز حداقل یکی از اجراهای زمان‌بندی‌شده‌ی daily_post.yml (اصلی یا "
            f"جبرانی) اصلاً اجرا نشده یا با خطا شکست خورده — چیزی فراتر از یه تاخیر ساده. "
            f"تب Actions گیت‌هاب رو چک کن؛ اگه لازم بود، از دکمه‌ی «Run workflow» روی "
            f"daily_post.yml برای جبران دستی باقی‌مونده‌ی امروز استفاده کن."
        )
        print(f"ALERT sent: only {posted_today}/{POSTS_PER_DAY} posts today ({today_str}).")
    else:
        print(f"OK: {posted_today}/{POSTS_PER_DAY} posts published today ({today_str}).")


if __name__ == "__main__":
    main()
