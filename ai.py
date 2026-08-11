import base64
import json
import re
import time

import requests
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from config import (
    GEMINI_API_KEY, GEMINI_API_KEY_BACKUP,
    GROQ_API_KEY, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN,
)


class GeminiAuthError(RuntimeError):
    """Raised when every configured Gemini key fails with an authentication
    error (invalid/revoked key, or the "AQ." vs "AIza" key-format problem —
    see config.GEMINI_API_KEY_BACKUP) rather than a transient issue.

    Kept distinct from a generic API failure so:
    - _call_model / _generate_image_with_model can stop retrying immediately
      instead of burning ~18s of backoff on a call that will fail identically
      every time, and
    - main.py's top-level handler can send an admin alert that names the
      actual, actionable cause instead of a generic "something broke, check
      the log" message.
    """


class AllTextProvidersFailedError(RuntimeError):
    """Raised when EVERY configured text provider has failed for a call —
    Gemini (both keys, if GEMINI_API_KEY_BACKUP is set) AND the Groq
    fallback (see _call_groq), or Gemini failed and Groq isn't configured
    at all.

    Distinct from GeminiAuthError: that one can fire the moment Gemini's
    keys are exhausted, but generate_content/generate_content_smart catch it
    internally and try Groq before giving up — so by the time this raises,
    there is genuinely no working text model anywhere, which is a more
    urgent, differently-worded admin alert (see main.py's top-level
    handler) than "Gemini specifically has a bad credential."
    """


# 401 is the code Google's API returns for every one of these; the reason
# strings are matched too since some client-side error shapes only surface
# them in the message text, not a structured field.
_AUTH_ERROR_MARKERS = (
    "ACCESS_TOKEN_TYPE_UNSUPPORTED",  # the "AQ." key vs generativelanguage.googleapis.com problem
    "API_KEY_INVALID",
    "API key not valid",
    "UNAUTHENTICATED",
)


def _is_auth_error(exc):
    """True if `exc` looks like a broken/invalid credential rather than a
    transient (network, quota, 5xx) failure. Checked against both the HTTP
    status code and known reason strings, since this SDK doesn't expose a
    single consistent field for it across error types."""
    if exc is None:
        return False
    if getattr(exc, "code", None) == 401:
        return True
    text = str(exc)
    return any(marker in text for marker in _AUTH_ERROR_MARKERS)


_client = genai.Client(api_key=GEMINI_API_KEY)

# Each entry tried in order. A second key (GEMINI_API_KEY_BACKUP, ideally
# from a wholly separate Google account) only ever gets used if the primary
# key fails with an auth error specifically — transient errors on the
# primary still retry on the primary, same as before. See GEMINI_API_KEY_BACKUP
# in config.py for why this exists.
_clients = [("primary key", _client)]
if GEMINI_API_KEY_BACKUP:
    _clients.append(("backup key", genai.Client(api_key=GEMINI_API_KEY_BACKUP)))


class _ClientExhausted(Exception):
    """Internal control-flow signal used by _call_with_fallback below: one
    client's attempts are used up. `is_auth` tells the caller whether
    falling through to the next configured client (if any) is worth
    trying at all."""
    def __init__(self, exc, is_auth):
        super().__init__(str(exc))
        self.exc = exc
        self.is_auth = is_auth


def _try_one_client(label, client_label, client, attempt_fn):
    for attempt in range(1, MAX_API_ATTEMPTS + 1):
        try:
            return attempt_fn(client)
        except (genai_errors.ServerError, genai_errors.ClientError, genai_errors.APIError) as exc:
            if _is_auth_error(exc):
                print(f"{label}: auth error on the {client_label} (not retrying this key): {exc}")
                raise _ClientExhausted(exc, is_auth=True) from exc
            if attempt < MAX_API_ATTEMPTS:
                print(f"{label}: call failed (attempt {attempt}/{MAX_API_ATTEMPTS}) on the "
                      f"{client_label}: {exc}. Retrying...")
                time.sleep(_RETRY_BASE_DELAY_SECONDS * attempt)
                continue
            print(f"{label}: call failed after {MAX_API_ATTEMPTS} attempts on the {client_label}: {exc}")
            raise _ClientExhausted(exc, is_auth=False) from exc


def _call_with_fallback(label, attempt_fn):
    """Shared retry-then-maybe-fall-through logic for every Gemini call in
    this module (draft/review text, grounded search, embeddings, image
    generation, speech generation).

    `attempt_fn(client)` performs ONE attempt against `client` and returns
    the result, or raises one of the caught SDK exception types.

    Bug fix (#7/#8): this exact retry loop used to be duplicated five
    times (_call_model, _call_model_grounded, embed_text,
    _generate_image_with_model, _generate_speech_with_model), and in
    every copy, exhausting MAX_API_ATTEMPTS retries on a plain TRANSIENT
    error (a network blip, quota limit, or 5xx) fell through to the next
    configured client exactly the same way an auth error did — even
    though this module's own documentation, and config.py's comment on
    GEMINI_API_KEY_BACKUP, are explicit that the backup key should be
    reserved for auth errors specifically ("transient errors on the
    primary still retry on the primary"). The reasoning: a transient
    failure usually means Gemini's service (or the network path to it) is
    having a bad moment for BOTH keys alike, so spending the backup key's
    separate quota on the same failure doesn't help and wastes it for
    when it's actually needed. Verified directly: forcing a pure
    transient 503 on every attempt no longer reaches a configured backup
    client at all; only an auth-shaped error does.
    """
    last_exc = None
    for client_label, client in _clients:
        try:
            return _try_one_client(label, client_label, client, attempt_fn)
        except _ClientExhausted as signal:
            last_exc = signal.exc
            if not signal.is_auth:
                break  # transient failure exhausted -- per the documented design, stop here
            continue  # auth error -- worth trying the next configured client, if any
    if _is_auth_error(last_exc):
        raise GeminiAuthError(
            f"{label}: failed with an authentication error on "
            f"{'every configured key' if len(_clients) > 1 else 'the configured key'}: {last_exc}"
        ) from last_exc
    raise last_exc

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
# Search-grounded verification calls (research.py's idiom/proverb lookup,
# and any future "this claim needs to be checked against reality, not
# generated from memory" use). Same REVIEW_MODEL tier, not DRAFT_MODEL: this
# runs far less often than a draft call (once per never-before-seen idiom,
# not once per post), and it's spent on exactly the kind of claim where a
# same-model-family review pass checking itself isn't independent
# verification (see REVIEW_MODEL's own comment above) — a live search result
# is a genuinely different source, not just a bigger model guessing harder.
GROUNDING_MODEL = REVIEW_MODEL

# gemini-embedding-001: GA, tops the MTEB Multilingual leaderboard, and lists
# Persian among its supported languages — used by embeddings.py for semantic
# post-deduplication (cosine similarity instead of database.py's keyword
# LIKE match). 768 dims (MRL-truncated from the model's native larger size)
# is plenty of resolution for near-duplicate detection at this channel's
# scale (a few posts/day) while keeping data/post_embeddings.jsonl small
# enough to commit to git like every other data/ file.
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONALITY = 768

IMAGE_MODEL = "gemini-3.1-flash-lite-image"
# Tried only if IMAGE_MODEL comes back empty (hard failure after retries,
# OR a 200 with no image part — e.g. a safety block that's specific to
# that model's filters). A different Nano Banana generation is a genuinely
# independent failure mode — different weights, different infra — so one
# more attempt here is worth it before handle_image_format gives up and
# falls back to the fully-manual admin hand-off.
FALLBACK_IMAGE_MODEL = "gemini-2.5-flash-image"

# Voice notes (main.py's voice_note format) — Gemini's native Speech
# Generation, an LLM that knows not only what to say but how to say it,
# not a traditional phoneme-stitching TTS engine. Same two-tier fallback
# shape as the image models above: try the newest/most capable tier
# first, fall back to the previous generation if it comes back empty.
# Persian ("fa") is an explicitly supported input language (see
# ai.google.dev/gemini-api/docs/speech-generation's language table) —
# confirmed against the current docs, not assumed, since this channel's
# posts mix majority-English text with short Persian glosses and the
# model has to read both correctly in one pass.
TTS_MODEL = "gemini-3.1-flash-tts-preview"
FALLBACK_TTS_MODEL = "gemini-2.5-flash-preview-tts"
# One of 30 prebuilt voices (none are language-tagged, so this is a
# judgment call, not a confirmed "best for Persian" pick) — Umbriel is
# documented as "easy-going", the closest single-word match to this
# channel's warm, unhurried teacher persona (prompts.py's PERSONA_NOTE).
# Worth an actual listen in AI Studio's Voice Library
# (aistudio.google.com/generate-speech) before treating this as final.
TTS_VOICE_NAME = "Umbriel"
# TTS output is raw PCM (24kHz, mono, 16-bit signed little-endian) per
# Google's docs — never WAV/MP3 — see generate_speech's docstring for why
# that's the right thing for voice_note.py to receive, not a bug to fix.
TTS_SAMPLE_RATE_HZ = 24000

# 30s per HTTP call — long enough for a normal generation, short enough that
# a genuine hang doesn't block the job until CI's own timeout kills it.
_HTTP_OPTIONS = types.HttpOptions(timeout=30_000)

MAX_API_ATTEMPTS = 3
_RETRY_BASE_DELAY_SECONDS = 3

# --- Free-tier fallback providers -------------------------------------------
# Reached only once every Gemini option above has already failed on a given
# call (see the module docstring on AllTextProvidersFailedError above, and
# the comment on generate_image below for the image side). Both run on
# infrastructure that has nothing to do with Google, so neither is affected
# by whatever is currently wrong with Gemini — that's the whole point: they
# cover the failure mode a second Gemini key can't (see GEMINI_API_KEY_BACKUP
# in config.py). Because Gemini is always tried first, in full, on every
# call, the pipeline goes back to using it automatically the moment it
# starts working again — nothing here needs to be switched back by hand.

# openai/gpt-oss-120b: OpenAI's open-weight 120B model, hosted free (no
# credit card) on Groq's LPU inference. Chosen over Groq's other free
# models (Llama 3.3 70B, etc.) for output quality — it's the strongest
# model on Groq's free tier, and this project's volume (POSTS_PER_DAY
# drafts/reviews, plus retries) comfortably fits Groq's free daily token
# budget for it. Same model used for both the DRAFT_MODEL and REVIEW_MODEL
# fallback path — unlike Gemini's two-tier split, there's no quota pressure
# here forcing a cheaper/smaller model for the high-volume draft calls.
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MAX_ATTEMPTS = 2
_GROQ_RETRY_BASE_DELAY_SECONDS = 3


def _call_groq(prompt):
    """Text fallback. Returns a plain string on success, or None if Groq
    isn't configured (no GROQ_API_KEY) or every attempt failed. Callers
    treat None exactly like "no fallback available" and re-raise the
    original Gemini failure — a missing/broken Groq key must never mask
    the real Gemini error with a confusing unrelated one."""
    if not GROQ_API_KEY:
        return None
    for attempt in range(1, GROQ_MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(
                GROQ_CHAT_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # noqa: BLE001 — any failure here just means "no fallback"
            if attempt < GROQ_MAX_ATTEMPTS:
                print(f"Groq fallback call failed (attempt {attempt}/{GROQ_MAX_ATTEMPTS}): "
                      f"{exc}. Retrying...")
                time.sleep(_GROQ_RETRY_BASE_DELAY_SECONDS * attempt)
            else:
                print(f"Groq fallback call failed after {GROQ_MAX_ATTEMPTS} attempts: {exc}")
    return None


# Flux Schnell on Cloudflare Workers AI: a fast, well-regarded open-weight
# image model, free (no credit card) within Workers AI's daily neuron
# budget — comfortably enough for this project's volume (at most one
# illustrated_pun image/day).
CLOUDFLARE_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"


def _call_cloudflare_image(prompt):
    """Image fallback, reached only once both Gemini image tiers
    (IMAGE_MODEL, FALLBACK_IMAGE_MODEL) have failed to produce an image.
    Returns image bytes, or None if Cloudflare isn't configured or the call
    failed. generate_image's only caller (handle_image_format in main.py)
    already treats a None return as "auto image generation failed" and
    falls back to its existing manual admin hand-off, so nothing downstream
    needs to change for this to slot in."""
    if not (CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN):
        return None
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}"
        f"/ai/run/{CLOUDFLARE_IMAGE_MODEL}"
    )
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
            json={"prompt": prompt},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        b64_image = (data.get("result") or {}).get("image")
        if not b64_image:
            print("Cloudflare image fallback: response had no image field.")
            return None
        return base64.b64decode(b64_image)
    except Exception as exc:  # noqa: BLE001 — any failure here just means "no fallback"
        print(f"Cloudflare image fallback call failed: {exc}")
        return None


def _call_model(model_name, prompt):
    """Call the given Gemini model with retry-with-backoff for transient
    errors (quota blips, network errors, Google-side 5xx). Raises the last
    error if every attempt fails — callers decide how to degrade (Audit #4).

    An auth error (bad/expired/wrong-format key) is NOT retried on the same
    key — it will fail identically every time, so retrying just burns time
    and clutters the log. Instead it falls through to the next configured
    client (see GEMINI_API_KEY_BACKUP), and only raises GeminiAuthError once
    every client has failed that way. A transient error does NOT fall
    through — see _call_with_fallback's docstring (bug #7/#8)."""
    def _attempt(client):
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(http_options=_HTTP_OPTIONS),
        )
        return (response.text or "").strip()
    return _call_with_fallback(f"Gemini call to {model_name}", _attempt)


def generate_content(prompt):
    """Drafting calls. Cheap/high-quota tier — safe to call repeatedly.

    Falls back to Groq (_call_groq) if every configured Gemini key/model
    has failed for this call. Raises AllTextProvidersFailedError only if
    Groq isn't configured or also fails — see that class's docstring."""
    try:
        return _call_model(DRAFT_MODEL, prompt)
    except (GeminiAuthError, genai_errors.ServerError, genai_errors.ClientError,
            genai_errors.APIError) as exc:
        print(f"generate_content: Gemini failed ({exc}); trying Groq fallback.")
        fallback = _call_groq(prompt)
        if fallback is not None:
            return fallback
        raise AllTextProvidersFailedError(
            f"Both Gemini and the Groq fallback failed to generate content: {exc}"
        ) from exc


def generate_content_smart(prompt):
    """Review, poll/quiz, and weekly-strategy calls. Smarter, low-quota
    tier — called far less often than generate_content, by design, so the
    daily cap isn't hit.

    Falls back to Groq (_call_groq) if every configured Gemini key/model
    has failed for this call. Raises AllTextProvidersFailedError only if
    Groq isn't configured or also fails — see that class's docstring."""
    try:
        return _call_model(REVIEW_MODEL, prompt)
    except (GeminiAuthError, genai_errors.ServerError, genai_errors.ClientError,
            genai_errors.APIError) as exc:
        print(f"generate_content_smart: Gemini failed ({exc}); trying Groq fallback.")
        fallback = _call_groq(prompt)
        if fallback is not None:
            return fallback
        raise AllTextProvidersFailedError(
            f"Both Gemini and the Groq fallback failed to generate content: {exc}"
        ) from exc


def _call_model_grounded(model_name, prompt):
    """Same retry/fallback contract as _call_model (transient errors retried
    with backoff, auth errors fall through to the next configured client,
    transient exhaustion does NOT — see _call_with_fallback), but with the
    Google Search grounding tool enabled — the model issues real search
    queries and grounds its answer in what comes back, instead of
    answering from memory alone. No Groq fallback here (see
    generate_grounded_json's docstring for why) — a grounded call that fails
    on every Gemini client just fails, it doesn't quietly degrade to an
    ungrounded guess from a different provider."""
    def _attempt(client):
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                http_options=_HTTP_OPTIONS,
            ),
        )
        return (response.text or "").strip()
    return _call_with_fallback(f"Gemini grounded call to {model_name}", _attempt)


def _extract_json_payload(raw):
    """Parse a JSON object/array out of a model response, tolerating more
    than just markdown code fences.

    Bug fix (#12): this used to be two blind .replace() calls stripping
    ```json / ``` markers and nothing else — a response wrapped in ANY
    other preamble or postamble (e.g. "Here's the poll:\\n{...}", or a
    trailing sentence after the closing brace) failed to parse even
    though the actual JSON payload inside it was perfectly valid and
    easy to recover. Now: try the cheap fence-strip first (handles the
    common case with no extra work), and if that alone doesn't parse,
    fall back to locating the outermost {...} or [...] span in the
    response and parsing just that span.
    """
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
    ends = [i for i in (cleaned.rfind("}"), cleaned.rfind("]")) if i != -1]
    if starts and ends:
        start, end = min(starts), max(ends)
        if end > start:
            return json.loads(cleaned[start:end + 1])  # lets JSONDecodeError propagate if this also fails
    raise json.JSONDecodeError("No JSON object/array found in response", cleaned, 0)


def generate_grounded_json(prompt, fallback=None):
    """Like generate_json, but the call is Search-grounded (see
    _call_model_grounded) — for claims that need checking against the real
    world, not just fluent generation (e.g. research.py's "is this actually
    a well-known Persian proverb" lookup). Returns `fallback` on any
    EXPECTED failure (API error after retries, or an unparseable response)
    — callers must treat that exactly like "couldn't verify this one right
    now, try again later / skip it", never publish something on the
    strength of a fallback value. Deliberately no Groq fallback and no
    `strict=True` option like generate_json: a caller that needs unverified
    content badly enough to accept an ungrounded guess should call
    generate_json directly, not silently get one back from a function named
    for the thing it just failed to do.

    Bug fix (#9's reasoning applied here too): this used to catch bare
    Exception around the model call, which would silently turn a genuine
    bug in this code into "using fallback" exactly like an expected API
    failure. Now narrowed to the specific exception types _call_model_
    grounded can actually raise for an expected failure; anything else
    propagates as the bug it is.
    """
    try:
        raw = _call_model_grounded(GROUNDING_MODEL, prompt)
    except (GeminiAuthError, genai_errors.ServerError, genai_errors.ClientError,
            genai_errors.APIError) as exc:
        print("generate_grounded_json: model call failed, using fallback:", exc)
        return fallback

    try:
        return _extract_json_payload(raw)
    except json.JSONDecodeError:
        print("generate_grounded_json: response was not valid JSON, using fallback. Raw response:",
              raw[:300])
        return fallback


def embed_text(text):
    """Returns a unit-ish list[float] embedding vector for `text` (see
    EMBEDDING_MODEL/EMBEDDING_DIMENSIONALITY above), or None if every
    configured client failed after retries, or if a client responded but
    produced no embedding values (a soft failure, not an API error).

    Callers (embeddings.py's semantic-dedup check) MUST treat None as "skip
    the semantic check this time" — never as a reason to block or crash a
    run. A transient embedding-API hiccup degrading dedup back to the
    existing keyword-based check for one post is an acceptable trade;
    blocking publishing on it would not be.

    Bug fix (#10): this used to have its own extra bare `except Exception`
    around the whole attempt, on top of the specific genai_errors catch —
    meaning an unexpected bug (not just a real API failure) would silently
    break out of the retry loop and move to the next client, or fall all
    the way through to "skipping" with no real visibility into what
    actually happened. That extra catch is gone; only the same specific
    exception types every other Gemini call in this module treats as an
    expected, retryable/fallback-able failure are caught here now (via
    _call_with_fallback) — anything else is a bug and surfaces as one.
    """
    def _attempt(client):
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=EMBEDDING_DIMENSIONALITY,
                task_type="SEMANTIC_SIMILARITY",
            ),
        )
        embeddings = response.embeddings or []
        if not embeddings or not embeddings[0].values:
            print("embed_text: response had no embedding values.")
            return None
        return list(embeddings[0].values)
    try:
        return _call_with_fallback("embed_text", _attempt)
    except (GeminiAuthError, genai_errors.ServerError, genai_errors.ClientError,
            genai_errors.APIError) as exc:
        print(f"embed_text: every configured client failed ({exc}); skipping "
              f"(dedup degrades gracefully).")
        return None


def _generate_image_with_model(model_name, prompt):
    """One model's worth of retried attempts (see _call_model — same
    retry-with-backoff convention). Returns image bytes, or None if the
    model responded but produced no image part (a soft failure — e.g. a
    safety block — not an API error). Raises after MAX_API_ATTEMPTS on a
    hard API failure; generate_image below decides whether to try the
    fallback model."""
    def _attempt(client):
        response = client.models.generate_content(
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
    return _call_with_fallback(f"Gemini image call to {model_name}", _attempt)


def generate_image(prompt):
    """Generate one image from a fully-composed prompt (see
    prompts.compose_image_prompt) — used by handle_image_format to auto-post
    illustrated_pun instead of handing the prompt to the admin.

    Tries IMAGE_MODEL first, then FALLBACK_IMAGE_MODEL if the first
    produced nothing — whether that's because every retry raised, or
    because it returned a normal response with no image part. Only after
    BOTH models fail does this give up.

    Unlike _call_model-based functions, this never raises for a normal
    model-level failure (safety block, 5xx, timeout) — it always returns
    bytes or None, since "try the next thing" already happened internally.
    handle_image_format still wraps the call in a try/except as a
    last-resort net, but shouldn't need it in practice.

    Deliberate exception: GeminiAuthError still propagates uncaught. A
    broken credential isn't a "this one model had a bad day" problem — it
    means every Gemini call in the run is about to fail the same way — so
    swallowing it here would just make the image quietly disappear every
    day instead of surfacing the real, fixable cause to the admin alert."""
    try:
        image_bytes = _generate_image_with_model(IMAGE_MODEL, prompt)
    except (genai_errors.ServerError, genai_errors.ClientError, genai_errors.APIError) as exc:
        print(f"generate_image: {IMAGE_MODEL} unavailable after retries ({exc}).")
        image_bytes = None

    if image_bytes is not None:
        return image_bytes

    print(f"generate_image: falling back to {FALLBACK_IMAGE_MODEL}.")
    try:
        image_bytes = _generate_image_with_model(FALLBACK_IMAGE_MODEL, prompt)
    except (genai_errors.ServerError, genai_errors.ClientError, genai_errors.APIError) as exc:
        print(f"generate_image: fallback model {FALLBACK_IMAGE_MODEL} also failed "
              f"after retries: {exc}")
        image_bytes = None

    if image_bytes is not None:
        return image_bytes

    # Both Gemini image tiers are exhausted — try the Cloudflare Workers AI
    # fallback (_call_cloudflare_image) before giving up. Still returns
    # bytes or None either way, same contract as the two attempts above, so
    # handle_image_format's existing manual admin hand-off is unaffected
    # if this also comes back empty (or isn't configured).
    print("generate_image: both Gemini image models failed; trying Cloudflare Workers AI fallback.")
    return _call_cloudflare_image(prompt)


_tts_voice_reminder_printed = False


def _generate_speech_with_model(model_name, text):
    """One model's worth of retried attempts (same retry-with-backoff
    convention as _call_model / _generate_image_with_model). Returns raw
    PCM bytes (see TTS_SAMPLE_RATE_HZ above), or None if the model
    responded but produced no audio part (a soft failure). Raises after
    MAX_API_ATTEMPTS on a hard API failure; generate_speech below decides
    whether to try the fallback model.

    Google's own docs flag that this preview model occasionally returns
    text tokens instead of audio tokens on a small percentage of
    requests, surfacing as a 500 ServerError — already covered by the
    same retry-with-backoff loop every other call in this file uses, no
    special-casing needed here.

    Bug fix (#91): TTS_VOICE_NAME was picked by matching a one-word
    personality label ("easy-going"), never confirmed by anyone actually
    listening to it, and none of Gemini's prebuilt voices are
    language-tagged for Persian even though this channel's content mixes
    English and Persian in one pass. That can't be fixed from here (it
    needs a human to actually listen), so instead of shipping the
    uncertainty silently, this prints a one-time-per-process reminder the
    first time speech generation actually runs, so it stays visible in
    every run's log instead of only in a code comment nobody re-reads.
    """
    global _tts_voice_reminder_printed
    if not _tts_voice_reminder_printed:
        print(f"generate_speech: using voice '{TTS_VOICE_NAME}' — chosen by personality-label "
              f"match, not confirmed by listening to it or against Persian pronunciation "
              f"quality specifically. Worth an actual listen in AI Studio's Voice Library "
              f"(aistudio.google.com/generate-speech) if voice_note output quality is ever in "
              f"question.")
        _tts_voice_reminder_printed = True

    def _attempt(client):
        response = client.models.generate_content(
            model=model_name,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=TTS_VOICE_NAME,
                        )
                    )
                ),
                http_options=_HTTP_OPTIONS,
            ),
        )
        for part in response.parts or []:
            if getattr(part, "inline_data", None) is not None:
                return part.inline_data.data
        print(f"generate_speech ({model_name}): responded with no audio part.")
        return None
    return _call_with_fallback(f"Gemini speech call to {model_name}", _attempt)


def generate_speech(text):
    """Generate spoken audio for `text` — used by voice_note.py to turn a
    post's script into an actual voice note. Returns raw PCM bytes (24kHz,
    mono, 16-bit signed little-endian — see TTS_SAMPLE_RATE_HZ) on
    success, or None if both model tiers failed.

    Deliberately returns raw PCM, not a finished audio file: Telegram's
    sendVoice requires OGG/Opus specifically, and PCM -> OGG/Opus is one
    ffmpeg call (voice_note.pcm_to_ogg_opus) — wrapping it in a WAV header
    here first would just be one extra, pointless conversion step for
    every caller to undo.

    Same two-tier fallback pattern as generate_image: try TTS_MODEL, then
    FALLBACK_TTS_MODEL if the first produced nothing (hard failure after
    retries, OR a normal response with no audio part) — no third,
    non-Gemini fallback here the way generate_image has Cloudflare, since
    there's no equivalent free-tier TTS provider already wired into this
    project. If both fail, voice_note.py falls back to a plain text post,
    the same "auto path breaks -> don't lose the day's post" pattern
    handle_image_format already uses for images.

    Deliberate exception: GeminiAuthError still propagates uncaught, same
    reasoning as generate_image — a broken credential means every Gemini
    call this run is about to fail the same way, and that needs to reach
    the admin alert, not disappear into a silent per-format fallback."""
    try:
        pcm = _generate_speech_with_model(TTS_MODEL, text)
    except (genai_errors.ServerError, genai_errors.ClientError, genai_errors.APIError) as exc:
        print(f"generate_speech: {TTS_MODEL} unavailable after retries ({exc}).")
        pcm = None

    if pcm is not None:
        return pcm

    print(f"generate_speech: falling back to {FALLBACK_TTS_MODEL}.")
    try:
        pcm = _generate_speech_with_model(FALLBACK_TTS_MODEL, text)
    except (genai_errors.ServerError, genai_errors.ClientError, genai_errors.APIError) as exc:
        print(f"generate_speech: fallback model {FALLBACK_TTS_MODEL} also failed after retries: {exc}")
        pcm = None

    return pcm


# Characters this channel should ever contain: Latin (English), Persian/Arabic
# script, digits, common punctuation, and emoji actually used by the format
# templates (🟢🟡🔴🎬☕🍳⏰🤔👇 etc). Anything outside these ranges is almost
# certainly language-leakage from the model (e.g. a stray Hangul/CJK/Cyrillic
# character dropped mid-sentence) rather than intentional content.
#
# Bug fix (#11): this used to omit the Arrows block (U+2190-21FF) and
# Miscellaneous Symbols and Arrows (U+2B00-2BFF, which includes the solid
# arrow emoji and the star "⭐"). Verified directly: a plain "→" — a
# completely natural way to show a grammar transformation, e.g.
# "I do → I don't", exactly the kind of thing a grammar/spot_mistake post
# would use — used to be flagged as "stray" and silently deleted from
# real published content by generate_reviewed_text's cleanup step.
_ALLOWED_CHARS_PATTERN = re.compile(
    "[^\u0000-\u024F"      # Basic Latin, Latin-1 Supplement, Latin Extended-A/B
    "\u0600-\u06FF"        # Arabic block (covers Persian letters)
    "\u0750-\u077F"        # Arabic Supplement
    "\uFB50-\uFDFF"        # Arabic Presentation Forms-A
    "\uFE70-\uFEFF"        # Arabic Presentation Forms-B
    "\u200C\u200D"         # ZWNJ / ZWJ, used constantly in Persian typography
    "\u2000-\u206F"        # General punctuation (em dash, ellipsis, etc.)
    "\u2190-\u21FF"        # Arrows (→ ← ↑ ↓ etc. — Audit: #11)
    "\u2300-\u23FF"        # Misc technical (⏰⌚⏳⏱ etc. — Audit #5)
    "\u2600-\u27BF"        # Misc symbols / dingbats (🟢🟡🔴 etc. live partly here)
    "\u2B00-\u2BFF"        # Misc symbols and arrows (⭐⬅️➡️ etc. — Audit: #11)
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
    """Like generate_content_smart, but extracts and parses a JSON
    object/array from the result (see _extract_json_payload).

    strict=False (default): on a JSON parse failure, log the problem and
    return `fallback` instead of raising — used where a degraded-but-
    published result is better than no post at all (e.g. the review pass,
    see review_content below). A model-call failure is handled entirely
    inside generate_content_smart (Gemini errors -> Groq fallback), so
    there's nothing left for this function to catch there except the
    genuinely-unexpected, which is deliberately NOT caught (see bug #9
    below).

    strict=True: also raise on a JSON parse failure instead of silently
    returning `fallback`. Used for the quiz/poll path (Audit #4), which has
    no other review step — a parse failure there should surface as an error
    the admin can see, not silently publish a generic placeholder question.

    AllTextProvidersFailedError always propagates regardless of `strict`: it
    means every configured text provider (Gemini AND the Groq fallback, see
    that class's docstring) failed on this call, not just a single-source
    hiccup — folding that into a generic "review failed, using fallback"
    would hide the one failure mode that's actually worth a specific admin
    alert (see main.py's top-level handler).

    Bug fix (#9): the model-call step used to be wrapped in a bare
    `except Exception`, which treated ANY failure — including a genuine
    bug in this code, like a TypeError from a malformed prompt object —
    identically to an expected API failure, silently returning `fallback`
    either way. generate_content_smart already handles every EXPECTED
    failure mode internally; this function no longer adds a second,
    broader catch on top of that, so an unexpected bug now surfaces as
    itself (in both strict and non-strict mode) instead of masquerading
    as "model call failed".
    """
    raw = generate_content_smart(prompt)  # AllTextProvidersFailedError propagates; so would a real bug

    try:
        return _extract_json_payload(raw)
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