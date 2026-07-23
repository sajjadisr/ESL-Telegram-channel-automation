import json
import re
import google.generativeai as genai
from config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-3.5-flash")


def generate_content(prompt):
    response = model.generate_content(prompt)
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
    """Like generate_content, but strips ```json fences and parses the result.
    Used for review_content, build_poll_prompt output, and the strategy step —
    anywhere the model is asked to return JSON only."""
    raw = generate_content(prompt)
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback


def review_content(review_prompt):
    return generate_json(review_prompt, fallback={"ok": True, "feedback": ""})