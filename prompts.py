import datetime

import clock

from config import FEEDBACK_WINDOW_WEEKS, CHANNEL_DISPLAY_NAME
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
# Same four colors as IMAGE_PALETTE above, as a lookup dict — for code that
# composites pixels directly (recap_card.py) rather than describing the
# palette in prose to an image-generation model.
IMAGE_PALETTE_HEX = {
    "burnt_orange": "#e76f51",
    "coral": "#f4a261",
    "warm_sand": "#e9c46a",
    "deep_purple": "#264653",
}
IMAGE_NEGATIVE = (
    "Square format. No text, no letters, no words or captions anywhere in the "
    "image. No logos or brand marks. No photorealistic human faces — keep "
    "faces simple and stylized."
)

# Fixed persona (telegram-esl-virality-blueprint.md §3.1: "lock a persona and
# don't drift... inconsistency is the fastest way for AI-generated content to
# read as AI-generated content"). Same pattern as IMAGE_STYLE/IMAGE_PALETTE
# above: pasted verbatim into every prompt that produces audience-facing
# voice (generation + poll/quiz), not independently re-worded per builder.
PERSONA = (
    f"تو یک معلم زبان انگلیسی حرفه‌ای و مدیر محتوای کانال تلگرامی {CHANNEL_DISPLAY_NAME} هستی — "
    "آموزش انگلیسی به فارسی‌زبانان مبتدی (سطح A1–A2)."
)

# ---------------------------------------------------------------------------
# The weekly rotation (SKILL.md → "The weekly rotation"). Each key here is a
# format_schedule.json value. needs_image / needs_voice / needs_poll tell
# main.py which code path to route the post through.
# ---------------------------------------------------------------------------
FORMATS = {
    "micro_scene": {
        "label": "میکرو-صحنه",
        "needs_image": False,
        "needs_poll": None,
        "use_tiers": True,
        # No category_filter: micro_scene is the default fresh-content
        # carrier and draws from any pillar (content-pipeline-architecture.md §4).
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
        # Was main.py's ILLUSTRATED_PUN_CATEGORY constant + a hardcoded
        # `if format_name == "illustrated_pun"` branch in _select_topic;
        # now a declared part of the format itself, so topic_selection's
        # generalized _eligible() check enforces it without main.py
        # needing to know illustrated_pun exists (content-pipeline-
        # architecture.md §5).
        "category_filter": "Idioms",
        "guidance": (
            "این فرمت فقط برای اصطلاحاتی جواب می‌ده که فاصله‌ی واضحی بین معنی تحت‌اللفظی و معنی واقعی دارن "
            "(مثل break the ice، piece of cake، under the weather). کپشن رو کوتاه نگه دار (۳ تا ۵ خط) — خود "
            "تصویر قراره جوک رو حمل کنه، متن فقط توضیح کوتاهش می‌ده."
        ),
    },
    "spot_mistake": {
        "label": "پیدا کردن اشتباه",
        "needs_image": False,
        "needs_poll": None,
        "use_tiers": False,
        "category_filter": ["Common mistakes", "Persian transfer errors"],
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
        "category_filter": ["Vocabulary", "Phrasal verbs"],
        # Fix (live incident, 2026-08-15): same gap as progress_recap below
        # — never explicitly said "in English", unlike micro_scene/
        # reader_installment/news_relevel. Already failed review for it
        # once in production (Aug 12, "نورافکن واژگان": mostly Persian
        # narration, English limited to a few words).
        "guidance": (
            "یه کلمه یا عبارت رو معرفی کن، معنیش رو بگو، و توی یه جمله‌ی خیلی ساده و روزمره نشونش بده. جمله‌ی "
            "نمونه باید به انگلیسیِ ساده باشه (نه فارسی) — طبق قانون تعادل زبان بالا، فارسی فقط برای معنیِ خودِ "
            "کلمه، کوتاه و داخل پرانتز، مجازه. این پست قراره زمینه رو برای یه صحنه یا اصطلاح آینده آماده کنه، "
            "پس ساده و مستقیم نگهش دار."
        ),
    },
    "idiom_proverb_bridge": {
        "label": "پل اصطلاح و ضرب‌المثل",
        "needs_image": False,
        "needs_poll": None,
        "use_tiers": False,
        # Hard restriction, not a prompt instruction (§4): only ever draw a
        # topic already tagged has_fa_equivalent AND carrying a verified
        # fa_equivalent string (topics.json) — this format's whole job is a
        # cultural claim a native reader catches immediately if it's wrong,
        # so it must never be asked to invent or recall a pairing on its own.
        "category_filter": "Idioms",
        "required_tags": ["has_fa_equivalent"],
        "guidance": (
            "این اصطلاح انگلیسی یه معادل ضرب‌المثل/اصطلاح فارسیِ واقعی و شناخته‌شده داره که پایین‌تر (توی "
            "«معادل فارسی») برات دقیقاً آورده شده — همون رو عیناً استفاده کن، خودت یکی دیگه اختراع نکن یا "
            "عوضش نکن. اول اصطلاح انگلیسی و معنیش رو با یه مثال کوتاه نشون بده، بعد معادل فارسی رو بیار و "
            "توی یه یا دو جمله نشون بده چقدر شبیه هم‌اند — لحن باید «نگاه کن، خودمون هم دقیقاً همین جمله رو "
            "داریم!» باشه، نه یه توضیح خشک زبان‌شناسی."
        ),
    },
    "textbook_vs_real": {
        "label": "کتابی در مقابل واقعی",
        "needs_image": False,
        "needs_poll": None,
        "use_tiers": True,
        # No category_filter: this contrast (formal/textbook phrasing vs.
        # what people actually say) can apply to a grammar point, a fixed
        # phrase, or a Persian-transfer register error alike — it's a
        # *shape* difference from spot_mistake, not tied to one pillar.
        # error_type:register-tagged topics are simply a good natural fit,
        # not a hard requirement (§4 lists it as "preferred", not required).
        "guidance": (
            "نشون بده معلم‌های مدرسه/کتاب‌های قدیمی معمولاً چی برای این نکته یاد می‌دن، در مقابل چیزی که یه "
            "آدم واقعی امروز توی مکالمه‌ی روزمره می‌گه. هر دو باید صحیح باشن — این «غلط در مقابل درست» نیست، "
            "«رسمی/کتابی در مقابل خودمونی/رایج» است. لحنش باید شیطنت‌آمیز و کمی غافلگیرکننده باشه («توی کتاب "
            "اینو یاد گرفتی، ولی هیچ‌کس اینجوری حرف نمی‌زنه»)، نه تحقیرآمیز نسبت به معلم‌ها یا کتاب‌های درسی."
        ),
    },
    "progress_recap": {
        "label": "مرور پیشرفت",
        "needs_image": False,
        "needs_poll": None,
        "use_tiers": False,
        "topic_is_lexical_item": False,  # reviews a whole list of past titles, not one item
        # Fix (live incident, 2026-08-15): every other format's guidance
        # either says "in simple English" outright (micro_scene,
        # reader_installment, news_relevel) or describes a task that's
        # structurally English by nature. This one never said it, and
        # unlike the others, its own input (recap_titles below) is a list
        # of past post titles that are themselves a Persian/English mix —
        # so the last thing the model reads before drafting is Persian-
        # leaning material, not just LANGUAGE_BALANCE stated many lines
        # earlier. Result: this format kept generating mostly-Persian
        # recaps, failing REVIEW_RULES' language-balance check on all 3
        # attempts, every single time it came up — and because it's
        # scheduled by post-count (RECAP_EVERY_N_POSTS), not weekday, a
        # stuck recap blocks every subsequent run too, since the count
        # never advances. Confirmed via the review rejection reason
        # recorded in send_admin_message's history: "بیشتر متن به زبان
        # فارسی روایت شده و بخش انگلیسی آن بسیار ناچیز است."
        "guidance": (
            "لیست موضوعات هفته‌های اخیر (پایین اومده) رو به یه پست کوتاه و گرم تبدیل کن — «این چند هفته با هم "
            "چی یاد گرفتیم» — نه یه لیست خشک، با یه جمله‌ی تشویقی در پایان. طبق قانون تعادل زبان بالا، بدنه‌ی "
            "اصلیِ این پست (جمله‌هایی که موضوعات رو مرور می‌کنن) باید به انگلیسیِ ساده نوشته بشه، نه فارسی — "
            "حتی اگه عنوان بعضی از موضوعات لیست‌شده پایین‌تر فارسی یا ترکیبیه، خودت با انگلیسیِ ساده بهشون "
            "اشاره کن (مثلاً «we learned about family words like mother and father»، نه روایت فارسی از "
            "همون موضوع). فارسی فقط برای همون یکی-دو جمله‌ی گرم/تشویقی مجازه، دقیقاً طبق قانون تعادل زبان."
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
    # --- Authentic-content formats (reader.py / news.py) --------------------
    # Both feed the model real source material (a pre-written story chunk,
    # or a real news summary) via extra_note, instead of inventing a scene
    # from a bare topic name the way micro_scene etc. do. See main.py's
    # extra-slot logic for how/when each one gets picked.
    "reader_installment": {
        "label": "داستان مرحله‌ای",
        "needs_image": False,
        "needs_poll": None,
        "use_tiers": False,
        # Bug fix (#34): this format's "topic" (reader.py builds it as
        # "<story title> — قسمت N") is a compound label for a story
        # installment, not a discrete vocabulary/grammar item — and its
        # own guidance below explicitly asks the model to RETELL the
        # source event in its own simple words, never to invent new
        # events OR to reproduce the source verbatim. Before this fix,
        # build_generation_prompt's TARGET_SALIENCE block (bold the exact
        # topic phrase the first time it appears) and its matching
        # REVIEW_RULES check were applied here anyway, demanding
        # something structurally at odds with "retell in your own
        # words": the compound title string was never going to appear
        # verbatim in a simple retelling, so the review check could only
        # ever fail, wasting a regeneration attempt (and REVIEW_MODEL
        # quota — see ai.py #90) every single time this format runs.
        "topic_is_lexical_item": False,
        "guidance": (
            "این یه قسمت از یه داستانِ از قبل نوشته‌شده‌ست — متن اصلیِ همین قسمت پایین‌تر (توی «توضیح "
            "تکمیلی») اومده. کارت اینه که همون رویداد رو با انگلیسیِ ساده‌ی سطح A1–A2 دوباره روایت کنی، نه "
            "این‌که داستان تازه بسازی یا رویدادها/شخصیت‌ها رو عوض کنی. اگه این اولین قسمت این داستانه، یه "
            "معرفیِ خیلی کوتاه از شخصیت‌ها/فضا بده؛ در غیر این صورت یه جمله‌ی «تا اینجا داستان...» بذار. اگه "
            "قسمت آخره، پایانش رو کامل و رضایت‌بخش تموم کن (بدون قلاب برای فردا)؛ در غیر این صورت با یه قلاب "
            "یا سوال واقعی برای قسمت بعد تموم کن."
        ),
    },
    "news_relevel": {
        "label": "خبر ساده‌شده",
        "needs_image": False,
        "needs_poll": None,
        "use_tiers": True,
        # Bug fix (#34): same reasoning as reader_installment above — this
        # format's "topic" is a full news headline (news.py sets it to
        # news_item["title"]), and the guidance below explicitly says
        # "with your own sentences, not by copying the source's
        # sentences" — directly at odds with the salience block's demand
        # that the exact topic phrase appear verbatim once.
        "topic_is_lexical_item": False,
        "guidance": (
            "یه خبر واقعی و تازه (خلاصه‌ش پایین‌تر توی «توضیح تکمیلی» اومده) رو با انگلیسیِ ساده‌ی سطح "
            "A1–A2 دوباره تعریف کن — با جمله‌های خودت، نه با کپی‌کردن جمله‌های منبع. این خبره، پس لازم نیست "
            "قلابش شخصیت/شوخی باشه؛ قلابش خودِ اتفاق واقعیه — چرا این خبر جالبه یا به زندگی روزمره ربط داره. "
            "از حدس‌زدن جزئیاتی که توی خلاصه نیومده خودداری کن."
        ),
    },
    "voice_note": {
        "label": "پیام صوتی",
        "needs_image": False,
        "needs_voice": True,
        "needs_poll": None,
        "use_tiers": False,
        # Persian transfer errors + raw Vocabulary/Phrasal verbs are the
        # cases where text structurally can't do the job — see
        # voice_note.py's module docstring for why this format exists at
        # all. Everything else already has a text format that covers it
        # better; this one only earns its slot on content where hearing it
        # is the actual point.
        "category_filter": ["Persian transfer errors", "Vocabulary", "Phrasal verbs"],
        # Fix (live incident, 2026-08-15): same gap as progress_recap and
        # vocab_spotlight above. Already failed review for it four times in
        # production (Aug 13, "پیام صوتی": mostly Persian narration each
        # time, occasionally stacked with other issues in the same rejection).
        "guidance": (
            "این یه اسکریپت برای یه پیام صوتیه، نه یه پست متنی معمولی — قراره با صدای واقعی خونده بشه، پس "
            "طبیعی و گفتاری بنویس، نه برای خوندن با چشم. روی تلفظ تمرکز کن: کلمه یا عبارت مورد نظر رو حداقل "
            "دوبار واضح و آروم تکرار کن، بعد توی یه جمله‌ی کوتاه و طبیعی به‌کارش ببر و اون جمله رو هم بیار. "
            "خودِ کلمه/عبارت هدف و جمله‌ی مثال باید انگلیسی باشن، طبق قانون تعادل زبان بالا — فارسی فقط برای "
            "جمله‌های کوتاه توضیحی/تشویقیِ اطرافش مجازه. اگه این دقیقاً همون چیزیه که فارسی‌زبان‌ها معمولاً "
            "اشتباه تلفظ می‌کنن، مستقیم بهش اشاره کن («خیلیا اینو اینجوری میگن... ولی تلفظ درستش اینه»). "
            "کوتاه نگهش دار — حدود ۷۰ تا ۱۰۰ کلمه، یعنی ۳۰ تا ۴۵ ثانیه گفتار."
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
                             extra_note="", recap_titles=None,
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
    if format_name == "progress_recap" and recap_titles:
        items = "\n".join(f"- {t}" for t in recap_titles)
        context_block = f"""
موضوعاتی که این چند هفته پوشش داده شدن:
{items}
"""
    elif format_name == "idiom_proverb_bridge":
        # topic_selection._eligible already guarantees this topic is tagged
        # has_fa_equivalent, but fa_equivalent itself (the actual verified
        # proverb string) is a separate topics.json field — hand it over
        # explicitly rather than relying on the model to recall or invent
        # one (see prompts.FORMATS["idiom_proverb_bridge"]'s comment).
        fa_equivalent = topic.get("fa_equivalent")
        if fa_equivalent:
            context_block = f"\nمعادل فارسی (عیناً همین رو استفاده کن): {fa_equivalent}\n"

    tier_block = TIER_INSTRUCTIONS if fmt["use_tiers"] else ""

    # Bug fix (#34): this used to be `if format_name != "progress_recap":`,
    # a hardcoded single-format exception. reader_installment and
    # news_relevel need the exact same exception (see their FORMATS
    # entries' topic_is_lexical_item comments) but were never given it —
    # driven by the FORMATS-dict flag now instead of a format-name
    # string check, matching this codebase's own stated design principle
    # (topic_selection._eligible's docstring) that adding a new format
    # should never mean "add another hardcoded branch here".
    # Bug fix (this session): topic_is_lexical_item can now also be set on
    # the TOPIC itself (data/topics.json), not just the format — e.g.
    # "Numbers and time" or "At the supermarket" are broad Vocabulary
    # themes, not single boldable words/phrases, even though the formats
    # that can draw them (voice_note, vocab_spotlight, ...) default to
    # expecting a single item. The topic-level value wins when set; same
    # override precedence as build_review_prompt below, and for the same
    # reason — generation telling the model to bold a theme name while
    # review no longer requires it would just be a mismatched, confusing
    # signal instead of a fix.
    effective_lexical = topic.get("topic_is_lexical_item")
    if effective_lexical is None:
        effective_lexical = fmt.get("topic_is_lexical_item", True)
    salience_block = ""
    single_item_block = ""
    if effective_lexical:
        salience_block = TARGET_SALIENCE.format(topic_text=topic["topic"])
        single_item_block = SINGLE_ITEM_FOCUS

    profile_block = ("\nپروفایل مخاطب (بر اساس داده‌ی واقعی کوییز/نظرسنجی):\n" + profile_note) if profile_note else ""
    campaign_block = ("\nزمینه‌ی کمپین این هفته:\n" + campaign_note) if campaign_note else ""

    return f"""{PERSONA}

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

پست‌های اخیر کانال (چه هم‌موضوع چه موضوع‌های دیگه — برای جلوگیری از تکرار):
{related_text}

موضوع درس امروز: {topic['topic']} (سطح: {topic['level']}, دسته: {topic['category']})

قوانین کلی:
- پست کوتاه باشه (حداکثر حدود ۳۰۰ تا ۴۰۰ کلمه؛ فرمت‌های تصویری و پازلی باید کوتاه‌تر باشن).
- هر پست باید یه قلاب واقعی داشته باشه — صرفاً نشون‌دادن کاربرد درست کافی نیست.
- از تکرار محتوای درس‌های قبلی خودداری کن. این شامل تکرار همون مثال/جمله/شوخیِ پست‌های بالا هم می‌شه، حتی اگه موضوع امروز با موضوع اون پست فرق داشته باشه — مثلاً اگه یه پست قبلی برای توضیح یه نکته از «قهوه خوردن هر روز صبح» استفاده کرده، امروز (حتی برای یه نکته‌ی گرامری/واژگانی متفاوت) سراغ یه موقعیت و مثال کاملاً تازه برو، نه همون سناریو با یه لباس دیگه.
{("توضیح تکمیلی برای اصلاح: " + extra_note) if extra_note else ""}

فقط متن نهایی پست رو بنویس (با تگ‌های HTML لازم)، بدون توضیح اضافه یا مقدمه‌چینی."""


_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def _persian_numeral(n):
    return "".join(_PERSIAN_DIGITS[int(d)] for d in str(n))


# Assembled checklist (content-pipeline-architecture.md §7) — replaces the
# old hand-spliced f-string that hardcoded Persian numerals ۱ through ۱۱ and
# threaded tier_check/salience_check conditionals directly into it. Every
# rule here is (applicability_condition, text); build_review_prompt below
# filters to what actually applies for this format/topic and renders the
# numbering programmatically, so adding a new format-specific check (like
# idiom_proverb_bridge's proverb-authenticity line) is "append one tuple",
# never "edit the f-string and recount by hand".
#
# The first 9 are unconditional — they applied to every format before this
# refactor and still do. Conditions after that mirror what the old
# tier_check/salience_check placeholders used to encode, except the rule is
# now omitted entirely when it doesn't apply, instead of being kept as a
# numbered "(این فرمت ... لازم نداره — رد شو.)" placeholder line.
REVIEW_RULES = [
    (lambda fmt: True, "صحت گرامری و املایی جمله‌های انگلیسی."),
    (lambda fmt: True, "آیا پست یک قلاب واقعی دارد (شوخی/غافلگیری/تعامل) یا فقط یک مثال گرامری خشک است؟"),
    (lambda fmt: True, "آیا فارسی متن، محاوره‌ای و روان است (نه ترجمه‌ای/کتابی) و آیا از تگ‌های HTML به‌جای Markdown استفاده شده؟"),
    (lambda fmt: fmt["use_tiers"],
     "هر سه لایه‌ی 🟢🟡🔴 حاضرن و لایه‌ی 🔴 هنوز در سطح مبتدی مونده (نه نکته‌ی پیشرفته)."),
    (lambda fmt: True, "آیا محتوا واقعاً در سطح مبتدی (A1–A2) قابل‌فهمه، یا از واژگان/گرامر سطح بالاتر استفاده شده؟"),
    (lambda fmt: True, "طول مناسب (نه خیلی کوتاه، نه خیلی بلند)."),
    (lambda fmt: True,
     "تعادل زبان: آیا بیشتر متن (روایت/دیالوگ اصلی) واقعاً به انگلیسیه، و فارسی فقط برای گلاسِ کلمات سخت یا یه "
     "جمله‌ی کوتاه به کار رفته؟ اگه بیشتر پست به فارسی روایت شده و فقط یکی-دو جمله‌ی انگلیسی توش قایم شده، این "
     "باید رد بشه (ok: false)."),
    (lambda fmt: True,
     "آیا متن هیچ کاراکتر عجیب یا از یه زبان/الفبای دیگه (نه فارسی، نه انگلیسی، نه اموجی معمولی) توش نیست؟ "
     "اگه هست، رد کن."),
    (lambda fmt: True,
     "این متن عیناً توی ایتا و بله هم منتشر می‌شه. آیا جایی از متن به یه قابلیت اشاره می‌کنه که معلوم نیست "
     "همه‌جا وجود داشته باشه — مثل «توی کامنت‌ها بگو»، «زیر پست بنویس»، «ریپلای کن»، «ری‌اکت بده»؟ اگه هست، "
     "رد کن (ok: false)."),
    (lambda fmt: fmt.get("topic_is_lexical_item", True),
     "آیا «{topic_text}» (یا معادل انگلیسیش) دقیقاً یک بار با تگ <b>...</b> پررنگ شده؟ اگه اصلاً پررنگ نشده، "
     "یا بیشتر از یک بار پررنگ شده، رد کن."),
    (lambda fmt: fmt.get("topic_is_lexical_item", True),
     "آیا توی همین پست چند تا عضو دیگه از همون دسته (مثلاً چند تا رنگ، چند تا عضو خانواده، چند تا روز هفته) "
     "هم پشت سر هم معرفی شدن؟ اگه آره، رد کن — این پست باید فقط روی یک مورد تمرکز کنه."),
    # idiom_proverb_bridge's one format-specific check (§4) — the concrete
    # example this refactor was done for: this is "append one tuple", not
    # "edit the f-string and renumber everything after it".
    (lambda fmt: fmt is FORMATS.get("idiom_proverb_bridge"),
     "آیا ضرب‌المثل فارسی‌ای که توی پست اشاره شده، چیزیه که یه فارسی‌زبان واقعاً می‌شناسه — نه ساختگی، نه "
     "زورکی، و نه صرفاً ترجمه‌ی کلمه‌به‌کلمه‌ی خودِ اصطلاح انگلیسی؟ اگه مطمئن نیستی این ضرب‌المثل واقعاً "
     "رایجه، رد کن (ok: false)."),
]


def build_review_prompt(content, format_name, topic_text=None, topic_is_lexical_item=None):
    """topic_is_lexical_item, when given (not None), overrides the format's
    own default for this one call. Needed because whether a topic is a
    single boldable word/phrase (e.g. "Color: red") vs. a broad theme
    (e.g. "Numbers and time", "Travel vocabulary") is a property of the
    TOPIC, not the FORMAT — the same format (voice_note, vocab_spotlight,
    ...) draws both kinds from topics.json. Without this, a broad-theme
    topic paired with a format that defaults topic_is_lexical_item=True
    gets stuck forever: rules 9/10 below demand the topic text itself
    appear bolded exactly once, which a natural-sounding script can't do
    for a theme name, so review never passes, the post never publishes,
    the topic never gets marked covered, and it's selected again next
    time unchanged (see topic_selection.get_next_topic — always returns
    the first not-yet-covered eligible topic, deterministically)."""
    fmt = FORMATS[format_name]
    if topic_is_lexical_item is not None:
        fmt = {**fmt, "topic_is_lexical_item": topic_is_lexical_item}
    applicable = [text for cond, text in REVIEW_RULES if cond(fmt)]
    checklist = "\n".join(
        f"{_persian_numeral(i + 1)}. {text.format(topic_text=topic_text)}"
        for i, text in enumerate(applicable)
    )
    return f"""متن زیر یک پست کانال تلگرامی آموزش انگلیسی مبتدی‌محور ({CHANNEL_DISPLAY_NAME}) است. آن را از نظر موارد زیر بررسی کن:
{checklist}

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

    return f"""{PERSONA}

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
    cutoff = clock.today() - datetime.timedelta(weeks=window_weeks)
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
    """focus_more_on/focus_less_on only — best_formats used to be requested
    here too, but format selection is now a deterministic function of
    analytics.recent_score_summary() (see schedule_builder.py's module
    docstring), so this prompt no longer asks the model to guess at it.
    This function's only remaining job is genuinely qualitative topic-level
    judgment a formula over a reward_score can't produce."""
    posts_text = "\n".join(f"- {p[0]} ({p[1]})" for p in recent_posts) or "خالی"
    recent_feedback = filter_recent_feedback(feedback_list)
    feedback_text = "\n".join(f"- {f['notes']}" for f in recent_feedback) or "خالی"

    return f"""پست‌های اخیر کانال:
{posts_text}

بازخوردهای دریافتی از مخاطبان (شامل نتایج واقعی کوییز/نظرسنجی‌ها در صورت وجود):
{feedback_text}

بر اساس این اطلاعات، استراتژی محتوایی کانال را به‌روزرسانی کن (کانال فقط مبتدی‌محور است، پیشنهادها هم باید مبتدی‌محور بمانند).
اگه بازخوردی شامل «درصد پاسخ درست» یه کوییز بود و درصد پایین بود (مثلاً زیر ۵۰٪)، اون موضوع رو به‌عنوان یه نکته‌ای که باید بیشتر تمرین/مرور بشه در نظر بگیر.

فقط یک JSON با این ساختار دقیق برگردان، بدون هیچ توضیح اضافه:
{{
  "focus_more_on": ["..."],
  "focus_less_on": ["..."]
}}
"""


def build_recap_title_prompt(recap_titles):
    """One short, warm Persian sentence for the recap image card's title
    (recap_card.py) — e.g. "این چند هفته با هم چی یاد گرفتیم؟". Deliberately
    NOT run through build_generation_prompt's full pipeline/review loop:
    this is one decorative line on an image, not audience-facing teaching
    content, so the lighter weight is a proportionate choice, not a
    shortcut taken on something that needs the same scrutiny as an actual
    lesson."""
    items = "\n".join(f"- {t}" for t in recap_titles)
    return f"""{PERSONA}

موضوعاتی که این چند هفته پوشش داده شدن:
{items}

یک جمله‌ی کوتاه، گرم و محاوره‌ای فارسی (حداکثر ۸-۹ کلمه) بنویس که عنوان یه پست «مرور پیشرفت» باشه — چیزی مثل "این چند هفته با هم چی یاد گرفتیم؟". فقط همون یک جمله رو بنویس، بدون گیومه، بدون توضیح اضافه."""


def build_topic_generation_prompt(existing_topics, count, categories):
    """topic_generation.py's self-refill prompt — asks the model to propose
    brand-new curriculum entries when data/topics.json is running low, so
    the pool renews itself instead of needing someone to hand-edit the
    file. existing_topics is the full list of topic strings already in
    topics.json (fresh AND covered) so the model can avoid near-duplicates
    itself, on top of the code-side dedup check that runs after this."""
    existing_text = "\n".join(f"- {t}" for t in existing_topics) or "(هنوز چیزی نیست)"
    categories_text = "، ".join(categories)
    return f"""تو داری موضوعات جدید برای کانال تلگرامی آموزش انگلیسی مبتدی‌محور {CHANNEL_DISPLAY_NAME} (سطح A1-A2) پیشنهاد می‌دی. این کانال قبلاً موضوعات زیر رو پوشش داده یا برای پوشش برنامه‌ریزی کرده — {count} موضوع کاملاً جدید و متفاوت پیشنهاد بده که هیچ‌کدوم از این‌ها نباشه و حتی خیلی شبیهشون هم نباشه:

{existing_text}

قوانین مهم:
- هر موضوع باید مشخص و تک‌مورده باشه، نه اسم یه کل دسته — مثلاً «رنگ قرمز» یا «آبی و دوستانش» به‌جای «رنگ‌ها»، «پدر و مادر» به‌جای «اعضای خانواده». این برای جلوگیری از تداخل حافظه‌ست (وقتی چند تا کلمه‌ی هم‌دسته با هم معرفی می‌شن، یادگیریشون کندتر می‌شه) — پس هر موضوع باید محدود و مشخص باشه، نه یه دسته‌ی کامل.
- فقط سطح A1-A2 (مبتدی واقعی) — نه گرامر پیشرفته، نه واژگان تخصصی.
- دسته (category) هر موضوع باید دقیقاً یکی از این‌ها باشه: {categories_text}.
- سطح (level) باید A1 یا A2 باشه.

فقط یک آرایه‌ی JSON برگردون، دقیقاً با این ساختار برای هر عضو، بدون هیچ توضیح اضافه:
[{{"topic": "...", "level": "A1", "category": "..."}}, ...]
"""