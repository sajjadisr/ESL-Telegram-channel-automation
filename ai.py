import json
import re
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from config import GEMINI_API_KEY

_client = genai.Client(api_key=GEMINI_API_KEY)

# Two tiers, used deliberately for different jobs:
# - DRAFT_MODEL (flash-lite): every DRAFT generation call. Flash-lite has a
#   much higher free-tier daily quota, and drafting is by far the highest-
#   volume call in the pipeline — every post, every retry, every image-format
#   scene sentence.
# - REVIEW_MODEL (flash): the smarter, low-quota (20/day free) tier, spent
#   on the review/quality-gate pass, poll/quiz content (which has no other
#   review step before publishing), and the weekly strategy update (low-
#   frequency, high-consequence — see weekly_strategy.py / Audit #6).
DRAFT_MODEL = "gemini-3.5-flash-lite"
REVIEW_MODEL = "gemini-3.5-flash"

# Image generation for illustrated_pun (handle_image_format in main.py).
# Deliberately NOT client.models.generate_images with an Imagen model
# (imagen-4.0-generate-001 etc.) — Google's Gemini API release notes list
# every Imagen model as shutting down August 17, 2026. This uses the
# Gemini-native "Nano Banana" image family instead, through the same
# generate_content endpoint as the text models above.
# gemini-3.1-flash-lite-image (Nano Banana 2 Lite) is the cheapest/fastest
# GA tier — same reasoning as DRAFT_MODEL being flash-lite for text: a
# small flat-icon illustration doesn't need the Pro tier's text-rendering/
# reasoning strength, and this runs far less often than DRAFT_MODEL does.
IMAGE_MODEL = "gemini-3.1-flash-lite-image"
# Tried only if IMAGE_MODEL comes back empty (hard failure after retries,
# OR a 200 with no image part — e.g. a safety block that's specific to
# that model's filters). A different Nano Banana generation is a genuinely
# independent failure mode — different weights, different infra — so one
# more attempt here is worth it before handle_image_format gives up and
# falls back to the fully-manual admin hand-off.
FALLBACK_IMAGE_MODEL = "gemini-2.5-flash-image"

# 30s per HTTP call — long enough for a normal generation, short enough that
# a genuine hang doesn't block the job until CI's own timeout kills it.
_HTTP_OPTIONS = types.HttpOptions(timeout=30_000)

MAX_API_ATTEMPTS = 3
_RETRY_BASE_DELAY_SECONDS = 3


def _call_model(model_name, prompt):
    """Call the given Gemini model with retry-with-backoff for transient
    errors (quota blips, network errors, Google-side 5xx). Raises the last
    error if every attempt fails — callers decide how to degrade (Audit #4)."""
    last_exc = None
    for attempt in range(1, MAX_API_ATTEMPTS + 1):
        try:
            response = _client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(http_options=_HTTP_OPTIONS),
            )
            return (response.text or "").strip()
        except (genai_errors.ServerError, genai_errors.ClientError, genai_errors.APIError) as exc:
            last_exc = exc
            if attempt < MAX_API_ATTEMPTS:
                print(f"Gemini call to {model_name} failed (attempt {attempt}/{MAX_API_ATTEMPTS}): "
                      f"{exc}. Retrying...")
                time.sleep(_RETRY_BASE_DELAY_SECONDS * attempt)
            else:
                print(f"Gemini call to {model_name} failed after {MAX_API_ATTEMPTS} attempts: {exc}")
    raise last_exc


def generate_content(prompt):
    """Drafting calls. Cheap/high-quota tier — safe to call repeatedly."""
    return _call_model(DRAFT_MODEL, prompt)


def generate_content_smart(prompt):
    """Review, poll/quiz, and weekly-strategy calls. Smarter, low-quota
    tier — called far less often than generate_content, by design, so the
    daily cap isn't hit."""
    return _call_model(REVIEW_MODEL, prompt)


def _generate_image_with_model(model_name, prompt):
    """One model's worth of retried attempts (see _call_model — same
    retry-with-backoff convention). Returns image bytes, or None if the
    model responded but produced no image part (a soft failure — e.g. a
    safety block — not an API error). Raises after MAX_API_ATTEMPTS on a
    hard API failure; generate_image below decides whether to try the
    fallback model."""
    last_exc = None
    for attempt in range(1, MAX_API_ATTEMPTS + 1):
        try:
            response = _client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio="1:1"),
                    http_options=_HTTP_OPTIONS,
                ),
            )
            for part in response.parts or []:
                if getattr(part, "inline_data", None) is not None:
                    return part.inline_data.data
            print(f"generate_image ({model_name}): responded with no image part "
                  f"(likely a safety block).")
            return None
        except (genai_errors.ServerError, genai_errors.ClientError, genai_errors.APIError) as exc:
            last_exc = exc
            if attempt < MAX_API_ATTEMPTS:
                print(f"Gemini image call to {model_name} failed (attempt "
                      f"{attempt}/{MAX_API_ATTEMPTS}): {exc}. Retrying...")
                time.sleep(_RETRY_BASE_DELAY_SECONDS * attempt)
            else:
                print(f"Gemini image call to {model_name} failed after "
                      f"{MAX_API_ATTEMPTS} attempts: {exc}")
    raise last_exc


def generate_image(prompt):
    """Generate one image from a fully-composed prompt (see
    prompts.compose_image_prompt) — used by handle_image_format to auto-post
    illustrated_pun instead of handing the prompt to the admin.

    Tries IMAGE_MODEL first, then FALLBACK_IMAGE_MODEL if the first
    produced nothing — whether that's because every retry raised, or
    because it returned a normal response with no image part. Only after
    BOTH models fail does this give up.

    Unlike _call_model-based functions, this never raises — it always
    returns bytes or None, since "try the next thing" already happened
    internally. handle_image_format still wraps the call in a try/except
    as a last-resort net, but shouldn't need it in practice."""
    try:
        image_bytes = _generate_image_with_model(IMAGE_MODEL, prompt)
    except (genai_errors.ServerError, genai_errors.ClientError, genai_errors.APIError) as exc:
        print(f"generate_image: {IMAGE_MODEL} unavailable after retries ({exc}).")
        image_bytes = None

    if image_bytes is not None:
        return image_bytes

    print(f"generate_image: falling back to {FALLBACK_IMAGE_MODEL}.")
    try:
        return _generate_image_with_model(FALLBACK_IMAGE_MODEL, prompt)
    except (genai_errors.ServerError, genai_errors.ClientError, genai_errors.APIError) as exc:
        print(f"generate_image: fallback model {FALLBACK_IMAGE_MODEL} also failed "
              f"after retries: {exc}")
        return None


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
    "\u2300-\u23FF"        # Misc technical (⏰⌚⏳⏱ etc. — Audit #5)
    "\u2600-\u27BF"        # Misc symbols / dingbats (🟢🟡🔴 etc. live partly here)
    "\uFE0F"               # Emoji variation selector (❤️ etc. — Audit #5)
    "\U0001F300-\U0001FAFF"  # Emoji blocks
    r"\s]"
)


def find_stray_script_chars(text):
    """Return any characters in text that fall outside the allowed Persian /
    English / punctuation / emoji ranges. A non-empty result means the model
    leaked characters from an unrelated script into the post."""
    return sorted(set(_ALLOWED_CHARS_PATTERN.findall(text)))


def generate_json(prompt, fallback=None, strict=False):
    """Like generate_content_smart, but strips ```json fences and parses the
    result.

    strict=False (default): on a failed API call OR a JSON parse failure,
    log the problem and return `fallback` instead of raising — used where a
    degraded-but-published result is better than no post at all (e.g. the
    review pass, see review_content below).

    strict=True: raise instead of silently returning `fallback` on either
    failure mode. Used for the quiz/poll path (Audit #4), which has no other
    review step — a parse failure there should surface as an error the admin
    can see, not silently publish a generic placeholder question.
    """
    try:
        raw = generate_content_smart(prompt)
    except Exception as exc:
        if strict:
            raise
        print("generate_json: model call failed after retries, using fallback:", exc)
        return fallback

    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        if strict:
            raise ValueError(f"Could not parse JSON from model response: {raw[:300]!r}") from exc
        print("generate_json: response was not valid JSON, using fallback. Raw response:", raw[:300])
        return fallback


def review_content(review_prompt):
    """Quality gate for every text-post format. Fails CLOSED: if the review
    model's response can't be parsed, or the call itself fails after
    retries, the fallback is 'ok': False so the caller's retry loop treats
    it as a failing review rather than silently waving the post through
    (Audit #4 — this was previously 'ok': True, the wrong failure direction
    for a quality gate)."""
    return generate_json(
        review_prompt,
        fallback={"ok": False, "feedback": "بررسی کیفیت انجام نشد (خطای مدل یا پاسخ نامعتبر)."},
    )
