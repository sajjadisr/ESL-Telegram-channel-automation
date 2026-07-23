import json
import re
import google.generativeai as genai
from config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)

# Two tiers, used deliberately for different jobs:
# - draft_model (flash-lite): every DRAFT generation call. Flash-lite has a
#   much higher free-tier daily quota, and drafting is by far the highest-
#   volume call in the pipeline — every post, every retry, every image-format
#   scene sentence, and the weekly strategy update.
# - review_model (flash): the smarter, low-quota (20/day free) tier, spent
#   ONLY on the review/quality-gate pass and on poll/quiz content (which has
#   no other review step before publishing). This is what actually catches
#   language-leakage glitches and Persian-heavy drift — keeping it off the
#   drafting path means the daily quota lasts through a normal day's runs
#   instead of getting exhausted by mid-morning.
draft_model = genai.GenerativeModel("gemini-3.5-flash-lite")
review_model = genai.GenerativeModel("gemini-3.5-flash")


def generate_content(prompt):
    """Drafting calls. Cheap/high-quota tier — safe to call repeatedly."""
    response = draft_model.generate_content(prompt)
    return response.text.strip()


def generate_content_smart(prompt):
    """Review and poll/quiz calls. Smarter, low-quota tier — called far less
    often than generate_content, by design, so the daily cap isn't hit."""
    response = review_model.generate_content(prompt)
    return response.text.strip()


# Characters this channel should ever contain: Latin (English), Persian/Arabic
# script, digits, common punctuation, and emoji actually used by the format
# templates (🟢🟡🔴🎬☕🍳⏰🤔👇 etc). Anything outside these ranges is almost
# certainly language-leakage from the model (e.g. a stray Hangul/CJK/Cyrillic
# character dropped mid-sentence) rather than intentional content.
_ALLOWED_CHARS_PATTERN = re.compile(
    "[^\u0000-\u024F"      # Basic Latin, Latin-1 Supplement, Latin Extended-A/B
    "\u0600-\u06FF"        # Arabic block (covers Persian letters)
    "\u0750-\u077F"        # Arabic Supplement
    "\uFB50-\uFDFF"        # Arabic Presentation Forms-A
    "\uFE70-\uFEFF"        # Arabic Presentation Forms-B
    "\u200C\u200D"         # ZWNJ / ZWJ, used constantly in Persian typography
    "\u2000-\u206F"        # General punctuation (em dash, ellipsis, etc.)
    "\u2600-\u27BF"        # Misc symbols / dingbats (🟢🟡🔴 etc. live partly here)
    "\U0001F300-\U0001FAFF"  # Emoji blocks
    r"\s]"
)


def find_stray_script_chars(text):
    """Return any characters in text that fall outside the allowed Persian /
    English / punctuation / emoji ranges. A non-empty result means the model
    leaked characters from an unrelated script into the post."""
    return sorted(set(_ALLOWED_CHARS_PATTERN.findall(text)))


def generate_json(prompt, fallback=None):
    """Like generate_content_smart, but strips ```json fences and parses the
    result. Used for review_content and build_poll_prompt output — review is
    the quality gate, and poll/quiz content has no other review pass before
    publishing, so both deliberately use the smarter tier."""
    raw = generate_content_smart(prompt)
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback


def review_content(review_prompt):
    return generate_json(review_prompt, fallback={"ok": True, "feedback": ""})