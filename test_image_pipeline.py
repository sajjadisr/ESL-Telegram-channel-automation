"""
Offline control-flow test for the auto image generation/posting pipeline
(ai.generate_image, telegram_bot.send_photo/send_document,
channels.*_photo, main.handle_image_format).

Nothing here hits a real network — api.telegram.org, tapi.bale.ai,
eitaayar.ir, and generativelanguage.googleapis.com aren't even reachable
from this sandbox's egress allowlist, so this mocks every HTTP boundary
and asserts on the resulting control flow instead. Real credentials would
still be needed for one true end-to-end smoke test before this goes live.

Run: python3 test_image_pipeline.py
"""
import os
import sys
from types import SimpleNamespace
from unittest import mock

# --- required env vars so config.py doesn't KeyError on import -------------
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-telegram-token")
os.environ.setdefault("TELEGRAM_CHANNEL_ID", "@testchannel")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_ID", "12345")
os.environ.setdefault("EITAA_TOKEN", "test-eitaa-token")
os.environ.setdefault("EITAA_CHANNEL_ID", "inEnglish")
os.environ.setdefault("BALE_BOT_TOKEN", "test-bale-token")
os.environ.setdefault("BALE_CHAT_ID", "@inEnglish")

import ai  # noqa: E402
import telegram_bot  # noqa: E402
import channels  # noqa: E402
import main  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402

# Retry-with-backoff (ai.py, telegram_bot.py) sleeps between attempts —
# real and correct in production, just pointless to actually wait through
# in a test that deliberately triggers several retry exhaustions.
_sleep_patcher = mock.patch("time.sleep", lambda *a, **k: None)
_sleep_patcher.start()

FAILED = []
PASSED = []


def check(label, condition, detail=""):
    if condition:
        PASSED.append(label)
        print(f"  OK   {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL {label}  {detail}")


# --- fakes for the Gemini client -------------------------------------------

class FakeTextResponse:
    def __init__(self, text):
        self.text = text


class FakeImagePart:
    def __init__(self, data):
        self.inline_data = SimpleNamespace(data=data)


class FakeImageResponse:
    def __init__(self, parts):
        self.parts = parts


def make_gemini_side_effect(image_behavior):
    """image_behavior: dict mapping model name -> one of
    "success" | "no_image_part" | "raise" """

    def side_effect(model, contents, config):
        if model in (ai.DRAFT_MODEL,):
            return FakeTextResponse("<b>Break the ice</b> means to start a conversation.")
        if model in (ai.REVIEW_MODEL,):
            return FakeTextResponse('{"ok": true, "feedback": ""}')
        if model in (ai.IMAGE_MODEL, ai.FALLBACK_IMAGE_MODEL):
            behavior = image_behavior.get(model, "success")
            if behavior == "raise":
                raise genai_errors.ServerError(503, {"error": {"message": "overloaded"}})
            if behavior == "no_image_part":
                return FakeImageResponse(parts=[])
            return FakeImageResponse(parts=[FakeImagePart(b"\x89PNG-fake-bytes")])
        raise AssertionError(f"unexpected model in test: {model}")

    return side_effect


# --- fakes for outbound HTTP -------------------------------------------

class FakeHTTPResponse:
    def __init__(self, ok=True, json_body=None, status_code=200):
        self.ok = ok
        self.status_code = status_code
        self._json = json_body if json_body is not None else {"ok": ok}
        self.text = str(self._json)

    def json(self):
        return self._json

    def raise_for_status(self):
        if not self.ok:
            import requests
            raise requests.HTTPError(f"{self.status_code} error", response=self)


def make_post_with_retry(telegram_behavior):
    """telegram_behavior: dict mapping 'sendPhoto'/'sendDocument' -> "ok" | "fail" """

    def fake_post_with_retry(url, **kwargs):
        for method in ("sendPhoto", "sendDocument", "sendMessage", "sendPoll"):
            if url.endswith(method):
                behavior = telegram_behavior.get(method, "ok")
                if behavior == "ok":
                    return FakeHTTPResponse(ok=True, json_body={"ok": True, "result": {"message_id": 1}})
                return FakeHTTPResponse(ok=False, status_code=400, json_body={"ok": False, "description": "bad request"})
        raise AssertionError(f"unexpected telegram url in test: {url}")

    return fake_post_with_retry


def make_channels_post(eitaa_behavior="ok", bale_behavior="ok"):
    def fake_post(url, **kwargs):
        if "eitaayar.ir" in url:
            if eitaa_behavior == "ok":
                return FakeHTTPResponse(ok=True, json_body={"ok": True})
            return FakeHTTPResponse(ok=False, status_code=400, json_body={"ok": False, "description": "eitaa rejected it"})
        if "tapi.bale.ai" in url:
            if bale_behavior == "ok":
                return FakeHTTPResponse(ok=True, json_body={"ok": True})
            return FakeHTTPResponse(ok=False, status_code=400, json_body={"ok": False, "description": "bale rejected it"})
        raise AssertionError(f"unexpected channels url in test: {url}")

    return fake_post


TOPIC = {"topic": "Break the ice", "category": "Idioms", "level": "A2"}
MEMORY = {}
STRATEGY = {}
RELATED = []


def run_handle_image_format(image_behavior, telegram_behavior, eitaa_behavior="ok", bale_behavior="ok"):
    with mock.patch.object(ai._client.models, "generate_content",
                            side_effect=make_gemini_side_effect(image_behavior)), \
         mock.patch.object(telegram_bot, "_post_with_retry",
                            side_effect=make_post_with_retry(telegram_behavior)), \
         mock.patch.object(channels.requests, "post",
                            side_effect=make_channels_post(eitaa_behavior, bale_behavior)), \
         mock.patch.object(main, "send_admin_message") as admin_msg, \
         mock.patch.object(main, "send_admin_image_prompt") as admin_prompt:
        content, status, extra_results = main.handle_image_format(
            MEMORY, STRATEGY, RELATED, TOPIC, "illustrated_pun",
        )
    return content, status, extra_results, admin_msg, admin_prompt


print("\n=== Scenario A: everything succeeds (Telegram + Eitaa + Bale, primary image model) ===")
content, status, extra_results, admin_msg, admin_prompt = run_handle_image_format(
    image_behavior={ai.IMAGE_MODEL: "success"},
    telegram_behavior={"sendPhoto": "ok"},
    eitaa_behavior="ok", bale_behavior="ok",
)
check("status is published", status == "published", status)
check("content marked AUTO", content.startswith("[AUTO"), content[:40])
check("eitaa got a real photo response (no text_fallback)",
      "text_fallback" not in extra_results["eitaa"], extra_results["eitaa"])
check("bale got a real photo response (no text_fallback)",
      "text_fallback" not in extra_results["bale"], extra_results["bale"])
check("admin was NOT pinged with a manual prompt", admin_prompt.call_count == 0, admin_prompt.call_count)

print("\n=== Scenario B: primary image model fails, fallback model succeeds ===")
content, status, extra_results, admin_msg, admin_prompt = run_handle_image_format(
    image_behavior={ai.IMAGE_MODEL: "raise", ai.FALLBACK_IMAGE_MODEL: "success"},
    telegram_behavior={"sendPhoto": "ok"},
)
check("status is published via fallback model", status == "published", status)

print("\n=== Scenario C: primary model returns no image part (safety block), fallback succeeds ===")
content, status, extra_results, admin_msg, admin_prompt = run_handle_image_format(
    image_behavior={ai.IMAGE_MODEL: "no_image_part", ai.FALLBACK_IMAGE_MODEL: "success"},
    telegram_behavior={"sendPhoto": "ok"},
)
check("status is published via fallback after a safety block", status == "published", status)

print("\n=== Scenario D: BOTH image models fail -> full manual fallback ===")
content, status, extra_results, admin_msg, admin_prompt = run_handle_image_format(
    image_behavior={ai.IMAGE_MODEL: "raise", ai.FALLBACK_IMAGE_MODEL: "raise"},
    telegram_behavior={"sendPhoto": "ok"},
)
check("status is pending_manual", status == "pending_manual", status)
check("content marked MANUAL", content.startswith("[MANUAL"), content[:40])
check("extra_results is None (nothing broadcast)", extra_results is None, extra_results)
check("admin WAS pinged with caption + prompt", admin_prompt.call_count == 2, admin_prompt.call_count)

print("\n=== Scenario E: image OK, Telegram sendPhoto fails, sendDocument fallback succeeds ===")
content, status, extra_results, admin_msg, admin_prompt = run_handle_image_format(
    image_behavior={ai.IMAGE_MODEL: "success"},
    telegram_behavior={"sendPhoto": "fail", "sendDocument": "ok"},
)
check("status is published via sendDocument fallback", status == "published", status)
check("admin was NOT pinged with a manual prompt", admin_prompt.call_count == 0, admin_prompt.call_count)

print("\n=== Scenario F: image OK, BOTH sendPhoto and sendDocument fail -> full manual fallback ===")
content, status, extra_results, admin_msg, admin_prompt = run_handle_image_format(
    image_behavior={ai.IMAGE_MODEL: "success"},
    telegram_behavior={"sendPhoto": "fail", "sendDocument": "fail"},
)
check("status is pending_manual when Telegram totally fails", status == "pending_manual", status)
check("admin WAS pinged with caption + prompt", admin_prompt.call_count == 2, admin_prompt.call_count)

print("\n=== Scenario G: Telegram OK, Eitaa photo upload fails -> Eitaa falls back to text-only caption ===")
content, status, extra_results, admin_msg, admin_prompt = run_handle_image_format(
    image_behavior={ai.IMAGE_MODEL: "success"},
    telegram_behavior={"sendPhoto": "ok"},
    eitaa_behavior="fail", bale_behavior="ok",
)
check("status still published (Telegram is what matters for status)", status == "published", status)
check("eitaa result includes a text_fallback", "text_fallback" in extra_results["eitaa"], extra_results["eitaa"])
check("bale result has no text_fallback (photo worked)",
      "text_fallback" not in extra_results["bale"], extra_results["bale"])

print("\n=== Scenario H: Telegram OK, BOTH Eitaa and Bale photo uploads fail -> both fall back to text ===")
content, status, extra_results, admin_msg, admin_prompt = run_handle_image_format(
    image_behavior={ai.IMAGE_MODEL: "success"},
    telegram_behavior={"sendPhoto": "ok"},
    eitaa_behavior="fail", bale_behavior="fail",
)
check("eitaa fell back to text", "text_fallback" in extra_results["eitaa"], extra_results["eitaa"])
check("bale fell back to text", "text_fallback" in extra_results["bale"], extra_results["bale"])
check("status still published (Telegram succeeded)", status == "published", status)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
sys.exit(0)
