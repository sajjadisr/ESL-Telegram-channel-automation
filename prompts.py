# Format definitions and prompt builders for the @InEnglish channel.
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

TIER_INSTRUCTIONS = """از سیستم لایه‌ای زیر استفاده کن (هر سه اختیاریه ولی معمولاً هر سه لازمن):
🟢 نکته‌ی اصلی — همون چیزی که همین امروز قابل استفاده‌ست، بدون نیاز به تحلیل.
🟡 توی بافت — همون مورد توی یه جمله‌ی ساده و واقعی؛ این لایه باید ۹۰ تا ۹۸ درصدش کلمات آشنا باشه، فقط همین یه مورد جدید باشه.
🔴 یه نکته‌ی کوچیک مرتبط — یه کلمه/عبارت نزدیک که هنوز مبتدیه (نه نکته‌ی پیشرفته)، مثلاً فرم رسمی/غیررسمیش یا یه عبارت مشابه که به‌زودی می‌شنوه."""


def _format_related(related_posts):
    return "\n".join(
        f"- {title}: {content[:200]}..." for title, content in related_posts
    ) or "موردی یافت نشد."


def build_generation_prompt(memory, strategy, related_posts, topic, format_name,
                             extra_note="", story=None, recap_titles=None):
    """For every text-post format (everything except quiz/vote_poll, which are
    handled by build_poll_prompt because they need structured JSON, not prose)."""
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

    return f"""تو یک معلم زبان انگلیسی حرفه‌ای و مدیر محتوای کانال تلگرامی @InEnglish هستی — آموزش انگلیسی به فارسی‌زبانان مبتدی.

هویت کانال: {memory.get('channel_identity')}
مخاطب: {memory.get('target_students')}
موارد پرهیز: {memory.get('avoid')}
تمرکز بیشتر روی (بر اساس بازخورد کاربران): {strategy.get('focus_more_on')}
تمرکز کمتر روی: {strategy.get('focus_less_on')}

{BEGINNER_CALIBRATION}

{LANGUAGE_BALANCE}

فرمت امروز: {fmt['label']}
{fmt['guidance']}
{tier_block}
{context_block}
{PERSIAN_REGISTER}

{TELEGRAM_FORMATTING}

درس‌های مرتبط قبلی (برای جلوگیری از تکرار):
{related_text}

موضوع درس امروز: {topic['topic']} (سطح: {topic['level']}, دسته: {topic['category']})

قوانین کلی:
- پست کوتاه باشه (حداکثر حدود ۳۰۰ تا ۴۰۰ کلمه؛ فرمت‌های تصویری و پازلی باید کوتاه‌تر باشن).
- هر پست باید یه قلاب واقعی داشته باشه — صرفاً نشون‌دادن کاربرد درست کافی نیست.
- از تکرار محتوای درس‌های قبلی خودداری کن.
{("توضیح تکمیلی برای اصلاح: " + extra_note) if extra_note else ""}

فقط متن نهایی پست رو بنویس (با تگ‌های HTML لازم)، بدون توضیح اضافه یا مقدمه‌چینی."""


def build_review_prompt(content, format_name):
    fmt = FORMATS[format_name]
    tier_check = "۴. هر سه لایه‌ی 🟢🟡🔴 حاضرن و لایه‌ی 🔴 هنوز در سطح مبتدی مونده (نه نکته‌ی پیشرفته)." \
        if fmt["use_tiers"] else "۴. (این فرمت لایه‌بندی لازم نداره — رد شو.)"
    return f"""متن زیر یک پست کانال تلگرامی آموزش انگلیسی مبتدی‌محور (@InEnglish) است. آن را از نظر موارد زیر بررسی کن:
۱. صحت گرامری و املایی جمله‌های انگلیسی.
۲. آیا پست یک قلاب واقعی دارد (شوخی/غافلگیری/تعامل) یا فقط یک مثال گرامری خشک است؟
۳. آیا فارسی متن، محاوره‌ای و روان است (نه ترجمه‌ای/کتابی) و آیا از تگ‌های HTML به‌جای Markdown استفاده شده؟
{tier_check}
۵. آیا محتوا واقعاً در سطح مبتدی (A1–A2) قابل‌فهمه، یا از واژگان/گرامر سطح بالاتر استفاده شده؟
۶. طول مناسب (نه خیلی کوتاه، نه خیلی بلند).
۷. تعادل زبان: آیا بیشتر متن (روایت/دیالوگ اصلی) واقعاً به انگلیسیه، و فارسی فقط برای گلاسِ کلمات سخت یا یه جمله‌ی کوتاه به کار رفته؟ اگه بیشتر پست به فارسی روایت شده و فقط یکی-دو جمله‌ی انگلیسی توش قایم شده، این باید رد بشه (ok: false).
۸. آیا متن هیچ کاراکتر عجیب یا از یه زبان/الفبای دیگه (نه فارسی، نه انگلیسی، نه اموجی معمولی) توش نیست؟ اگه هست، رد کن.

متن:
\"\"\"{content}\"\"\"

فقط یک JSON با این ساختار برگردان و هیچ متن اضافه‌ای ننویس:
{{"ok": true یا false, "feedback": "در صورت وجود ایراد، توضیح کوتاه بده، در غیر این صورت رشته خالی"}}
"""


def build_poll_prompt(related_posts, topic, format_name, recent_titles=None):
    """For quiz / vote_poll formats — output is structured JSON, sent through
    Telegram's native sendPoll endpoint by telegram_bot.py, never as text."""
    fmt = FORMATS[format_name]
    related_text = _format_related(related_posts)
    recent_block = ""
    if recent_titles:
        recent_block = "موضوعات واقعی این هفته (سوال باید از اینا باشه):\n" + \
            "\n".join(f"- {t}" for t in recent_titles)

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


def build_strategy_prompt(recent_posts, feedback_list):
    posts_text = "\n".join(f"- {p[0]} ({p[1]})" for p in recent_posts) or "خالی"
    feedback_text = "\n".join(f"- {f['notes']}" for f in feedback_list) or "خالی"
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