import datetime

from config import FEEDBACK_WINDOW_WEEKS
from text_utils import strip_spoilers_for_context
#
# Design source: the inenglish-telegram-content skill (SKILL.md + references).
# Anything here that looks like a rule ("must", "never") is enforcing something
# specific from that design, not a stylistic preference — see the comment next
# to each block for which part of the design it comes from.

# ---------------------------------------------------------------------------
# Fixed visual identity (visual-identity.md). Kept as constants, not left for
# the model to improvise per post — that's the whole point of a "fixed"
# identity: it has to be pasted verbatim every time, not rewritten.
# ---------------------------------------------------------------------------
IMAGE_STYLE = (
    "Clean modern editorial-icon illustration style, generous flat color fields, "
    "soft rounded edges, minimal fine detail, gentle or no shadows — not "
    "photorealistic, not cartoon-mascot style."
)
IMAGE_PALETTE = (
    "Color palette: burnt orange #e76f51, coral #f4a261, warm sand #e9c46a, "
    "deep purple #264653 background."
)
IMAGE_NEGATIVE = (
    "Square format. No text, no letters, no words or captions anywhere in the "
    "image. No logos or brand marks. No photorealistic human faces — keep "
    "faces simple and stylized."
)

# ---------------------------------------------------------------------------
# The weekly rotation (SKILL.md → "The weekly rotation"). Each key here is a
# format_schedule.json value. needs_image / needs_poll tell main.py which
# code path to route the post through.
# ---------------------------------------------------------------------------
FORMATS = {
    "micro_scene": {
        "label": "میکرو-صحنه",
        "needs_image": False,
        "needs_poll": None,
        "use_tiers": True,
        "guidance": (
            "یه صحنه‌ی کوتاه و واقعی به زبان انگلیسیِ ساده بساز (۲ تا ۴ خط دیالوگ یا روایت، خودِ دیالوگ/روایت "
            "انگلیسیه، نه فارسی) که توش موضوع امروز به‌طور طبیعی پیش بیاد — نه یه جمله‌ی نمونه‌ی خشک. صحنه باید "
            "یه قلاب واقعی داشته باشه: شوخی، غافلگیری، یا یه لحظه‌ی قابل‌ارتباط. اگه فقط داری کاربرد درست جمله "
            "رو نشون می‌دی، این میکرو-صحنه نیست، یه مثال گرامری با لباس مبدله — دوباره بنویسش."
        ),
    },
    "illustrated_pun": {
        "label": "شوخی تصویری",
        "needs_image": True,
        "needs_poll": None,
        "use_tiers": False,
        "guidance": (
            "این فرمت فقط برای اصطلاحاتی جواب می‌ده که فاصله‌ی واضحی بین معنی تحت‌اللفظی و معنی واقعی دارن "
            "(مثل break the ice، piece of cake، under the weather). کپشن رو کوتاه نگه دار (۳ تا ۵ خط) — خود "
            "تصویر قراره جوک رو حمل کنه، متن فقط توضیح کوتاهش می‌ده."
        ),
    },
    "story_installment": {
        "label": "قسمت داستان دنباله‌دار",
        "needs_image": False,
        "needs_poll": None,
        "use_tiers": False,
        "guidance": (
            "این قسمت بعدیِ داستان دنباله‌داره، با همون دو شخصیت ثابت (مشخصاتشون پایین اومده). خودِ داستان — "
            "روایت و دیالوگ شخصیت‌ها — باید به انگلیسیِ ساده (A1–A2) نوشته بشه، نه فارسی؛ فارسی فقط برای گلاسِ "
            "کلمات سخت یا یه جمله‌ی کوتاه در ابتدا/انتها مجازه (طبق قانون تعادل زبان). یه موقعیت کوتاه و "
            "قابل‌ارتباط بساز که توش موضوع امروز به‌طور طبیعی پیش بیاد. آخرش رو با یه کنجکاوی کوچیک برای قسمت "
            "بعد تموم کن."
        ),
    },
    "spot_mistake": {
        "label": "پیدا کردن اشتباه",
        "needs_image": False,
        "needs_poll": None,
        "use_tiers": False,
        "guidance": (
            "یه جمله‌ی غلط بساز که دقیقاً همون اشتباه رایجیه که فارسی‌زبان‌ها موقع استفاده از این نکته می‌کنن. "
            "جمله‌ی غلط رو نشون بده، بعد جواب درست + یه توضیح خیلی کوتاه رو داخل یه تگ <tg-spoiler>...</tg-spoiler> "
            "بذار تا تا قبل از تپ‌کردن پنهون بمونه."
        ),
    },
    "vocab_spotlight": {
        "label": "نورافکن واژگان",
        "needs_image": False,
        "needs_poll": None,
        "use_tiers": True,
        "guidance": (
            "یه کلمه یا عبارت رو معرفی کن، معنیش رو بگو، و توی یه جمله‌ی خیلی ساده و روزمره نشونش بده. این "
            "پست قراره زمینه رو برای یه صحنه یا اصطلاح آینده آماده کنه، پس ساده و مستقیم نگهش دار."
        ),
    },
    "progress_recap": {
        "label": "مرور پیشرفت",
        "needs_image": False,
        "needs_poll": None,
        "use_tiers": False,
        "guidance": (
            "لیست موضوعات هفته‌های اخیر (پایین اومده) رو به یه پست کوتاه و گرم تبدیل کن — «این چند هفته با هم "
            "چی یاد گرفتیم» — نه یه لیست خشک، با یه جمله‌ی تشویقی در پایان."
        ),
    },
    "quiz": {
        "label": "کوییز",
        "needs_image": False,
        "needs_poll": "quiz",
        "use_tiers": False,
        "guidance": (
            "این هفته رو مرور کن. سوال باید از موضوعات واقعی هفته‌ی اخیر (لیست پایین) باشه، نه چیز اختراعی. "
            "توضیح (explanation) باید حداکثر ۲۰۰ کاراکتر و خیلی خودمونی باشه."
        ),
    },
    "vote_poll": {
        "label": "نظرسنجی",
        "needs_image": False,
        "needs_poll": "vote",
        "use_tiers": False,
        "guidance": (
            "یه سوال کوتاه درباره‌ی کاربرد واقعی زبان بساز که جواب «درست/غلط» نداره — حداقل دو گزینه‌ی رایج "
            "و هر دو قابل‌قبول. این نظرسنجیه نه کوییز، پس گزینه‌ی «درست» نباید وجود داشته باشه."
        ),
    },
}

# ---------------------------------------------------------------------------
# Shared blocks — reused across every text-based format so a rule (register,
# HTML tags, beginner calibration) can't quietly drift between formats.
# ---------------------------------------------------------------------------

BEGINNER_CALIBRATION = """این کانال فقط برای زبان‌آموزان مبتدی (تقریباً سطح CEFR A1–A2) هست، نه «هر سطحی».
یعنی:
- فقط از واژگان پرتکرار روزمره و ساختارهای ساده (حال ساده، گذشته ساده، آینده‌ی ساده) استفاده کن.
- اگه یه اصطلاح یا نکته برای فهمیدنش نیاز به دونستن گرامر یا واژگان سطح متوسط به بالا داره، اصلاً سراغش نرو.
- توضیح‌ها هم باید با جمله‌های ساده باشن؛ توضیح‌دادن یه اصطلاح با یه اصطلاح سخت‌تر، کل هدف رو خراب می‌کنه."""

LANGUAGE_BALANCE = """تعادل زبان (این مهم‌ترین قانونه، جدی بگیرش):
- بیشتر پست باید به زبان انگلیسیِ ساده باشه — روایت، دیالوگ، جمله‌ها همه انگلیسی. اینجا داریم با غوطه‌وری (immersion) آموزش می‌دیم، نه با یه روایت فارسی که یه جمله‌ی انگلیسی توش قایم شده.
- فارسی فقط برای این موارد مجازه، و باید کوتاه باشه (چند کلمه تا یه نیم‌جمله، نه پاراگراف):
  • معنیِ یه کلمه یا اصطلاح جدید و سخت، معمولاً داخل پرانتز درست بعد از خود کلمه — مثلاً: "She's exhausted (خیلی خسته‌ست)."
  • نکته‌های کوتاهِ گرامری زیر تگ‌های 🟢/🟡/🔴.
  • حداکثر یک جمله‌ی کوتاهِ گرمِ فارسی در ابتدا یا انتهای پست برای طعنه/شوخی/دعوت به تعامل، فقط اگه واقعاً لازم باشه.
- هرگز یه صحنه یا دیالوگ رو به فارسی روایت نکن و بعدش فقط یه جمله‌ی انگلیسی داخلش بذاری؛ برعکسش کن: صحنه/دیالوگ به انگلیسیِ ساده (واژگان و گرامر A1–A2) نوشته بشه، فارسی فقط برای گلاسِ (gloss) کلمات سخت بیاد.
- اگه یه جمله‌ی انگلیسی برای این سطح خیلی سخته، جمله رو ساده‌تر کن؛ به فارسی برنگرد."""

PERSIAN_REGISTER = """هر جا فارسی به کار می‌ری (طبق قانون تعادل زبان بالا)، فارسیِ خودمونی و گفتاری باشه (محاوره‌ای)، نه فارسیِ کتابی یا ترجمه‌شده:
- می‌خوام نه می‌خواهم، میگه نه می‌گوید، نمی‌دونم نه نمی‌دانم.
- از ترکیب‌های تحت‌اللفظیِ ترجمه‌شده (calque) پرهیز کن — از روی معنی بنویس، نه از روی ساختار جمله‌ی انگلیسی.
- دو صفت/قید هم‌معنی رو کنار هم نذار (فقط یکیش کافیه).
- ی و ک فارسی (نه ي و ك عربی) و نیم‌فاصله رو رعایت کن (می‌رم نه میرم، کتاب‌ها نه کتابها).
- یک سبک عدد (فارسی یا انگلیسی) رو انتخاب کن و توی کل پست همونو نگه دار."""

TELEGRAM_FORMATTING = """فرمت‌بندی برای تلگرام:
- به‌جای Markdown از تگ‌های HTML استفاده کن: <b>پررنگ</b>، <i>ایتالیک</i>، <tg-spoiler>مخفی تا تپ</tg-spoiler>.
- هرگز از ستاره (*) یا زیرخط (_) به‌عنوان بولد/ایتالیک استفاده نکن.
- جمله‌ها کوتاه باشن، خط‌شکنی طبیعی داشته باش (موبایل، نه دسکتاپ).
- قلاب (شوخی/غافلگیری/تعامل) باید همون خط اول باشه، نه بعد از یه مقدمه‌چینی."""

# Noticing hypothesis (Schmidt): learners are far more likely to notice —
# and later produce — a form they consciously attended to at the moment of
# input. A plain <b> tag around the day's target item, exactly once at its
# first appearance, costs nothing and is the cheapest evidence-backed lever
# available here.
TARGET_SALIENCE = """برجسته‌سازی نکته‌ی هدف (این به یادگیری کمک می‌کنه، حتماً رعایت کن):
- خودِ کلمه یا عبارت هدفِ امروز («{topic_text}») رو همون بار اولی که توی متن انگلیسی میاد، با تگ <b>...</b> پررنگ کن.
- فقط همون یک بار پررنگش کن، نه هر جا دوباره تکرار شد — هدف جلب توجه به همون یه مورده، نه پررنگ‌کاری کل متن."""

# Interference from semantic clustering (Tinkham 1993/1997; Waring 1997):
# introducing several members of the same word-set (colors, body parts,
# family members, days of the week...) in one sitting measurably slows
# acquisition compared to one item at a time — competing items interfere
# with each other's memory trace, especially for still-unfamiliar words.
# Several entries in data/topics.json name a whole category rather than one
# item ("Colors", "Body parts", "Family members") — this rule keeps the
# model from silently teaching the whole set in a single post.
SINGLE_ITEM_FOCUS = """تمرکز روی یک مورد (این برای جلوگیری از تداخل حافظه‌ست، جدی بگیرش):
- اگه موضوع امروز خودش اسم یه دسته/مجموعه‌ست (مثل «رنگ‌ها»، «اعضای بدن»، «اعضای خانواده»، «روزهای هفته»)، فقط یکی از اعضای اون دسته رو برای امروز انتخاب کن و کامل روی همون تمرکز کن.
- توی یه پست چند تا کلمه‌ی هم‌خانواده/هم‌دسته (مثل چند تا رنگ با هم، یا چند تا عضو خانواده با هم) رو پشت سر هم معرفی نکن — این دقیقاً همون چیزیه که حافظه رو گیج می‌کنه، نه که کمکش کنه. بقیه‌ی اعضای دسته می‌تونن پست‌های جداگونه‌ی بعدی باشن."""

# Platform-awareness fix: this exact text (whatever the model writes here)
# gets sent unmodified to Eitaa and Bale too (channels.broadcast_extra_channels),
# not just Telegram — so a closing line that only makes sense on one of the
# three quietly breaks on the other two. Without this rule, the model's only
# guidance was LANGUAGE_BALANCE's generic permission for "one short
# invitation to interact," which is exactly what produced a "بگو توی
# کامنت‌ها" (say it in the comments) closer that doesn't work anywhere:
# Eitaa and Bale have no comments feature on channel posts at all, and even
# on Telegram it only works if the channel has a discussion group linked —
# something this cron-only script has no way to check.
CROSS_PLATFORM_ENGAGEMENT_RULE = """دعوت به تعامل (این متن عیناً توی ایتا و بله هم منتشر می‌شه، نه فقط تلگرام — پس هر خطی که اینجا بنویسی باید همه‌جا معنی بده):
- هرگز به قابلیتی اشاره نکن که معلوم نیست همه‌جا وجود داشته باشه: «توی کامنت‌ها بگو»، «زیر پست بنویس»، «ریپلای کن»، «با ایموجی ری‌اکت بده». نه ایتا نه بله زیر پست‌های کانال کامنت ندارن، و حتی تلگرام هم این قابلیت رو فقط وقتی داره که یه گروه گفتگو بهش لینک شده باشه — که معلوم نیست باشه.
- اگه می‌خوای دعوت به تعامل کنی، یه چیز خودکفا بساز که به هیچ قابلیتی نیاز نداشته باشه: یه سوال خطاب به خودِ خواننده برای فکر کردن (نه جایی جواب دادن)، دعوت به امتحان‌کردنِ همون جمله در موقعیت واقعی، یا دعوت به فوروارد کردن برای یه دوست."""

TIER_INSTRUCTIONS = """از سیستم لایه‌ای زیر استفاده کن (هر سه اختیاریه ولی معمولاً هر سه لازمن):
🟢 نکته‌ی اصلی — همون چیزی که همین امروز قابل استفاده‌ست، بدون نیاز به تحلیل.
🟡 توی بافت — همون مورد توی یه جمله‌ی ساده و واقعی؛ این لایه باید ۹۰ تا ۹۸ درصدش کلمات آشنا باشه، فقط همین یه مورد جدید باشه.
🔴 یه نکته‌ی کوچیک مرتبط — یه کلمه/عبارت نزدیک که هنوز مبتدیه (نه نکته‌ی پیشرفته)، مثلاً فرم رسمی/غیررسمیش یا یه عبارت مشابه که به‌زودی می‌شنوه."""


def _format_related(related_posts):
    lines = []
    for title, content in related_posts:
        safe = strip_spoilers_for_context(content)
        if len(safe) > 200:
            lines.append(f"- {title}: {safe[:200]}...")
        else:
            lines.append(f"- {title}: {safe}")
    return "\n".join(lines) or "موردی یافت نشد."


def build_generation_prompt(memory, strategy, related_posts, topic, format_name,
                             extra_note="", story=None, recap_titles=None,
                             campaign_note="", profile_note=""):
    """For every text-post format (everything except quiz/vote_poll, which are
    handled by build_poll_prompt because they need structured JSON, not prose).

    campaign_note (campaigns.campaign_context_block): this week's theme +
    what's already been posted this week, so posts can reference each other.
    profile_note (audience_profile.profile_context_block): the aggregate
    audience profile (weak/strong categories, recent quiz accuracy)."""
    fmt = FORMATS[format_name]
    related_text = _format_related(related_posts)

    context_block = ""
    if format_name == "story_installment" and story:
        chars = "\n".join(f"- {c['name']}: {c['role']}" for c in story.get("characters", []))
        context_block = f"""
شخصیت‌های ثابت داستان (دقیقاً همینا رو نگه دار، شخصیت جدید اضافه نکن):
{chars}
قسمت قبلی چی شد: {story.get('recent_summary') or 'این اولین قسمته.'}
شماره‌ی این قسمت: {story.get('last_installment', 0) + 1}
"""
    if format_name == "progress_recap" and recap_titles:
        items = "\n".join(f"- {t}" for t in recap_titles)
        context_block = f"""
موضوعاتی که این چند هفته پوشش داده شدن:
{items}
"""

    tier_block = TIER_INSTRUCTIONS if fmt["use_tiers"] else ""

    # Both rules are about a specific target item — progress_recap reviews a
    # whole list of past titles, not one item, so neither applies there.
    salience_block = ""
    single_item_block = ""
    if format_name != "progress_recap":
        salience_block = TARGET_SALIENCE.format(topic_text=topic["topic"])
        single_item_block = SINGLE_ITEM_FOCUS

    profile_block = ("\nپروفایل مخاطب (بر اساس داده‌ی واقعی کوییز/نظرسنجی):\n" + profile_note) if profile_note else ""
    campaign_block = ("\nزمینه‌ی کمپین این هفته:\n" + campaign_note) if campaign_note else ""

    return f"""تو یک معلم زبان انگلیسی حرفه‌ای و مدیر محتوای کانال تلگرامی @InEnglish هستی — آموزش انگلیسی به فارسی‌زبانان مبتدی.

هویت کانال: {memory.get('channel_identity')}
مخاطب: {memory.get('target_students')}
موارد پرهیز: {memory.get('avoid')}
الگوهای موفق اخیر (ادامه بده): {memory.get('successful_patterns', [])}
تمرکز بیشتر روی (بر اساس بازخورد کاربران): {strategy.get('focus_more_on')}
تمرکز کمتر روی: {strategy.get('focus_less_on')}
{profile_block}
{campaign_block}

{BEGINNER_CALIBRATION}

{LANGUAGE_BALANCE}

فرمت امروز: {fmt['label']}
{fmt['guidance']}
{tier_block}
{context_block}
{PERSIAN_REGISTER}

{TELEGRAM_FORMATTING}

{salience_block}

{single_item_block}

{CROSS_PLATFORM_ENGAGEMENT_RULE}

درس‌های مرتبط قبلی (برای جلوگیری از تکرار):
{related_text}

موضوع درس امروز: {topic['topic']} (سطح: {topic['level']}, دسته: {topic['category']})

قوانین کلی:
- پست کوتاه باشه (حداکثر حدود ۳۰۰ تا ۴۰۰ کلمه؛ فرمت‌های تصویری و پازلی باید کوتاه‌تر باشن).
- هر پست باید یه قلاب واقعی داشته باشه — صرفاً نشون‌دادن کاربرد درست کافی نیست.
- از تکرار محتوای درس‌های قبلی خودداری کن.
{("توضیح تکمیلی برای اصلاح: " + extra_note) if extra_note else ""}

فقط متن نهایی پست رو بنویس (با تگ‌های HTML لازم)، بدون توضیح اضافه یا مقدمه‌چینی."""


def build_review_prompt(content, format_name, topic_text=None):
    fmt = FORMATS[format_name]
    tier_check = "۴. هر سه لایه‌ی 🟢🟡🔴 حاضرن و لایه‌ی 🔴 هنوز در سطح مبتدی مونده (نه نکته‌ی پیشرفته)." \
        if fmt["use_tiers"] else "۴. (این فرمت لایه‌بندی لازم نداره — رد شو.)"
    salience_check = (
        f"۱۰. آیا «{topic_text}» (یا معادل انگلیسیش) دقیقاً یک بار با تگ <b>...</b> پررنگ شده؟ "
        "اگه اصلاً پررنگ نشده، یا بیشتر از یک بار پررنگ شده، رد کن.\n"
        "۱۱. آیا توی همین پست چند تا عضو دیگه از همون دسته (مثلاً چند تا رنگ، چند تا عضو خانواده، "
        "چند تا روز هفته) هم پشت سر هم معرفی شدن؟ اگه آره، رد کن — این پست باید فقط روی یک مورد تمرکز کنه."
        if format_name != "progress_recap" else "۱۰. (این فرمت هدف واحد نداره — رد شو.)"
    )
    return f"""متن زیر یک پست کانال تلگرامی آموزش انگلیسی مبتدی‌محور (@InEnglish) است. آن را از نظر موارد زیر بررسی کن:
۱. صحت گرامری و املایی جمله‌های انگلیسی.
۲. آیا پست یک قلاب واقعی دارد (شوخی/غافلگیری/تعامل) یا فقط یک مثال گرامری خشک است؟
۳. آیا فارسی متن، محاوره‌ای و روان است (نه ترجمه‌ای/کتابی) و آیا از تگ‌های HTML به‌جای Markdown استفاده شده؟
{tier_check}
۵. آیا محتوا واقعاً در سطح مبتدی (A1–A2) قابل‌فهمه، یا از واژگان/گرامر سطح بالاتر استفاده شده؟
۶. طول مناسب (نه خیلی کوتاه، نه خیلی بلند).
۷. تعادل زبان: آیا بیشتر متن (روایت/دیالوگ اصلی) واقعاً به انگلیسیه، و فارسی فقط برای گلاسِ کلمات سخت یا یه جمله‌ی کوتاه به کار رفته؟ اگه بیشتر پست به فارسی روایت شده و فقط یکی-دو جمله‌ی انگلیسی توش قایم شده، این باید رد بشه (ok: false).
۸. آیا متن هیچ کاراکتر عجیب یا از یه زبان/الفبای دیگه (نه فارسی، نه انگلیسی، نه اموجی معمولی) توش نیست؟ اگه هست، رد کن.
۹. این متن عیناً توی ایتا و بله هم منتشر می‌شه. آیا جایی از متن به یه قابلیت اشاره می‌کنه که معلوم نیست همه‌جا وجود داشته باشه — مثل «توی کامنت‌ها بگو»، «زیر پست بنویس»، «ریپلای کن»، «ری‌اکت بده»؟ اگه هست، رد کن (ok: false).
{salience_check}

متن:
\"\"\"{content}\"\"\"

فقط یک JSON با این ساختار برگردان و هیچ متن اضافه‌ای ننویس:
{{"ok": true یا false, "feedback": "در صورت وجود ایراد، توضیح کوتاه بده، در غیر این صورت رشته خالی"}}
"""


def build_poll_prompt(related_posts, topic, format_name, recent_titles=None,
                       campaign_note="", profile_note="", variant_note=""):
    """For quiz / vote_poll formats — output is structured JSON, sent through
    Telegram's native sendPoll endpoint by telegram_bot.py, never as text.

    variant_note (experiments.variant_prompt_note): the active A/B test's
    instruction for whichever variant this post was assigned, if any
    experiment is currently running."""
    fmt = FORMATS[format_name]
    related_text = _format_related(related_posts)
    recent_block = ""
    if recent_titles:
        recent_block = "موضوعات واقعی این هفته (سوال باید از اینا باشه):\n" + \
            "\n".join(f"- {t}" for t in recent_titles)
    context_note = ""
    if profile_note:
        context_note += "\nپروفایل مخاطب (بر اساس داده‌ی واقعی کوییز/نظرسنجی):\n" + profile_note
    if campaign_note:
        context_note += "\nزمینه‌ی کمپین این هفته:\n" + campaign_note

    is_quiz = fmt["needs_poll"] == "quiz"
    json_shape = (
        '{"question": "...", "options": ["...", "...", "...", "..."], '
        '"correct_index": 0, "explanation": "..."}'
        if is_quiz else
        '{"question": "...", "options": ["...", "..."]}'
    )

    return f"""تو مدیر محتوای کانال تلگرامی @InEnglish هستی — آموزش انگلیسی به فارسی‌زبانان مبتدی (A1–A2).

فرمت: {fmt['label']}
{fmt['guidance']}

{BEGINNER_CALIBRATION}
{context_note}

{recent_block}

درس‌های اخیر (زمینه، نه لزوماً منبع سوال):
{related_text}

موضوع پایه (در صورت نیاز): {topic['topic']}

فقط یک JSON با دقیقاً این ساختار برگردان، بدون Markdown، بدون ```json، بدون هیچ توضیح اضافه:
{json_shape}

نکات:
- همه‌ی متن‌ها (سوال، گزینه‌ها، توضیح) باید فارسیِ محاوره‌ای و گرم باشن؛ کلمات/جملات انگلیسی داخل گزینه‌ها می‌تونن بیان.
{"- explanation حداکثر ۲۰۰ کاراکتر." if is_quiz else ""}
{"- correct_index باید ایندکس (از ۰) گزینه‌ی درست باشه." if is_quiz else "- این نظرسنجیه، گزینه‌ی «درست» نداشته باش."}
{("- " + variant_note) if variant_note else ""}
"""


def build_scene_prompt(topic_text):
    """Ask the model for ONE English sentence describing the literal scene for
    an illustrated pun — the fixed style/palette/negative are added in code
    (compose_image_prompt), never left for the model to invent."""
    return f"""Write exactly one sentence in English describing a simple, literal visual scene that depicts the idiom "{topic_text}" at face value (the literal meaning, which is the joke). No commentary, no quotes, just the one sentence describing the scene."""


def compose_image_prompt(scene_sentence):
    """Wrap a scene sentence with the fixed visual identity (visual-identity.md)
    — the same style/palette/negative string every time, verbatim."""
    scene = scene_sentence.strip().strip('"')
    return f"{scene} {IMAGE_STYLE} {IMAGE_PALETTE} {IMAGE_NEGATIVE}"


def filter_recent_feedback(feedback_list, window_weeks=FEEDBACK_WINDOW_WEEKS):
    """Feedback entries from the last `window_weeks` weeks. Shared by the
    strategy prompt (below) and by weekly_strategy.py's decision on whether
    there's enough real signal yet to let engagement reshape the schedule."""
    cutoff = datetime.date.today() - datetime.timedelta(weeks=window_weeks)
    recent = []
    for entry in feedback_list:
        try:
            entry_date = datetime.date.fromisoformat(entry.get("date", ""))
        except ValueError:
            continue
        if entry_date >= cutoff:
            recent.append(entry)
    return recent


def build_strategy_prompt(recent_posts, feedback_list):
    posts_text = "\n".join(f"- {p[0]} ({p[1]})" for p in recent_posts) or "خالی"
    recent_feedback = filter_recent_feedback(feedback_list)
    feedback_text = "\n".join(f"- {f['notes']}" for f in recent_feedback) or "خالی"
    # best_formats must reference formats that actually exist in FORMATS —
    # a prior version of this prompt let the model invent formats (audio
    # clips, flashcards) that nothing in the codebase implements, which
    # just misleads anyone reading strategy.json expecting it to reflect
    # what's live (Audit #5).
    valid_formats = "\n".join(f"- {name} ({fmt['label']})" for name, fmt in FORMATS.items())

    return f"""پست‌های اخیر کانال:
{posts_text}

بازخوردهای دریافتی از مخاطبان (شامل نتایج واقعی کوییز/نظرسنجی‌ها در صورت وجود):
{feedback_text}

بر اساس این اطلاعات، استراتژی محتوایی کانال را به‌روزرسانی کن (کانال فقط مبتدی‌محور است، پیشنهادها هم باید مبتدی‌محور بمانند).
اگه بازخوردی شامل «درصد پاسخ درست» یه کوییز بود و درصد پایین بود (مثلاً زیر ۵۰٪)، اون موضوع رو به‌عنوان یه نکته‌ای که باید بیشتر تمرین/مرور بشه در نظر بگیر.

best_formats فقط باید از بین فرمت‌های واقعاً موجود در سیستم انتخاب بشه (دقیقاً همین نام‌های کلید انگلیسی رو برگردون، نه فرمت‌های تخیلی مثل فایل صوتی یا فلش‌کارت که هنوز پیاده‌سازی نشدن):
{valid_formats}

فقط یک JSON با این ساختار دقیق برگردان، بدون هیچ توضیح اضافه:
{{
  "focus_more_on": ["..."],
  "focus_less_on": ["..."],
  "best_formats": ["یکی یا چند تا از کلیدهای بالا، مثلاً micro_scene"]
}}
"""


def build_topic_generation_prompt(existing_topics, count, categories):
    """topic_generation.py's self-refill prompt — asks the model to propose
    brand-new curriculum entries when data/topics.json is running low, so
    the pool renews itself instead of needing someone to hand-edit the
    file. existing_topics is the full list of topic strings already in
    topics.json (fresh AND covered) so the model can avoid near-duplicates
    itself, on top of the code-side dedup check that runs after this."""
    existing_text = "\n".join(f"- {t}" for t in existing_topics) or "(هنوز چیزی نیست)"
    categories_text = "، ".join(categories)
    return f"""تو داری موضوعات جدید برای کانال تلگرامی آموزش انگلیسی مبتدی‌محور @InEnglish (سطح A1-A2) پیشنهاد می‌دی. این کانال قبلاً موضوعات زیر رو پوشش داده یا برای پوشش برنامه‌ریزی کرده — {count} موضوع کاملاً جدید و متفاوت پیشنهاد بده که هیچ‌کدوم از این‌ها نباشه و حتی خیلی شبیهشون هم نباشه:

{existing_text}

قوانین مهم:
- هر موضوع باید مشخص و تک‌مورده باشه، نه اسم یه کل دسته — مثلاً «رنگ قرمز» یا «آبی و دوستانش» به‌جای «رنگ‌ها»، «پدر و مادر» به‌جای «اعضای خانواده». این برای جلوگیری از تداخل حافظه‌ست (وقتی چند تا کلمه‌ی هم‌دسته با هم معرفی می‌شن، یادگیریشون کندتر می‌شه) — پس هر موضوع باید محدود و مشخص باشه، نه یه دسته‌ی کامل.
- فقط سطح A1-A2 (مبتدی واقعی) — نه گرامر پیشرفته، نه واژگان تخصصی.
- دسته (category) هر موضوع باید دقیقاً یکی از این‌ها باشه: {categories_text}.
- سطح (level) باید A1 یا A2 باشه.

فقط یک آرایه‌ی JSON برگردون، دقیقاً با این ساختار برای هر عضو، بدون هیچ توضیح اضافه:
[{{"topic": "...", "level": "A1", "category": "..."}}, ...]
"""