def build_generation_prompt(memory, strategy, related_posts, topic, extra_note=""):
    related_text = "\n".join(
        f"- {title}: {content[:200]}..." for title, content in related_posts
    ) or "موردی یافت نشد."

    return f"""
تو یک معلم زبان انگلیسی حرفه‌ای و مدیر محتوای یک کانال تلگرامی آموزش انگلیسی برای فارسی‌زبانان هستی.

هویت کانال: {memory.get('channel_identity')}
مخاطب: {memory.get('target_students')}
فرمت‌های مورد ترجیح: {memory.get('preferred_formats')}
موارد پرهیز: {memory.get('avoid')}
تمرکز بیشتر روی (بر اساس بازخورد کاربران): {strategy.get('focus_more_on')}
تمرکز کمتر روی: {strategy.get('focus_less_on')}
بهترین فرمت‌ها تا الان: {strategy.get('best_formats')}

درس‌های مرتبط قبلی (برای جلوگیری از تکرار):
{related_text}

موضوع درس امروز: {topic['topic']} (سطح: {topic['level']}, دسته: {topic['category']})

دستورالعمل نوشتن پست:
- توضیح‌ها به فارسی روان باشد.
- مثال‌های انگلیسی ساده و کاربردی باشد.
- پست کوتاه باشد (حداکثر حدود ۳۰۰ تا ۴۰۰ کلمه).
- در پایان یک مثال یا تمرین کوتاه بگذار.
- از تکرار محتوای درس‌های قبلی خودداری کن.
- از نشانه‌های Markdown ساده (مثل ستاره برای بولد) برای زیبایی متن استفاده کن.
{("توضیح تکمیلی برای اصلاح: " + extra_note) if extra_note else ""}

فقط متن نهایی پست را بنویس، بدون توضیح اضافه یا مقدمه‌چینی.
"""

def build_review_prompt(content):
    return f"""
متن زیر یک پست آموزش زبان انگلیسی است. آن را از نظر زیر بررسی کن:
۱. صحت گرامری و املایی جمله‌های انگلیسی
۲. روان و قابل‌فهم بودن توضیح فارسی
۳. طول مناسب (نه خیلی کوتاه، نه خیلی بلند)

متن:
\"\"\"{content}\"\"\"

فقط یک JSON با این ساختار برگردان و هیچ متن اضافه‌ای ننویس:
{{"ok": true یا false, "feedback": "در صورت وجود ایراد، توضیح کوتاه بده، در غیر این صورت رشته خالی"}}
"""

def build_strategy_prompt(recent_posts, feedback_list):
    posts_text = "\n".join(f"- {p[0]} ({p[1]})" for p in recent_posts) or "خالی"
    feedback_text = "\n".join(f"- {f['notes']}" for f in feedback_list) or "خالی"

    return f"""
پست‌های اخیر کانال:
{posts_text}

بازخوردهای دریافتی از مخاطبان:
{feedback_text}

بر اساس این اطلاعات، استراتژی محتوایی کانال را به‌روزرسانی کن.
فقط یک JSON با این ساختار دقیق برگردان، بدون هیچ توضیح اضافه:
{{
  "focus_more_on": ["..."],
  "focus_less_on": ["..."],
  "best_formats": ["..."]
}}
"""