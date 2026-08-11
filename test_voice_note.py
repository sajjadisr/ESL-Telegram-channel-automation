"""Tests for voice_note.py. pcm_to_ogg_opus is tested against the REAL
ffmpeg binary (no mocking needed for that part — it's a pure, deterministic
subprocess call); only ai.generate_speech (the actual network-calling part)
is mocked.

Run: python3 test_voice_note.py
"""
import math
import os
import struct
import subprocess
import sys
from unittest import mock

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-telegram-token")
os.environ.setdefault("TELEGRAM_CHANNEL_ID", "@testchannel")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")

import voice_note  # noqa: E402

FAILED = []
PASSED = []


def check(label, condition, detail=""):
    if condition:
        PASSED.append(label)
        print(f"  OK   {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL {label}  {detail}")


def _fake_pcm(seconds=0.5, sample_rate=24000, freq=440):
    """A short sine wave as raw s16le mono PCM — good enough input to
    prove the ffmpeg pipeline actually round-trips real audio, not just
    empty bytes."""
    n = int(seconds * sample_rate)
    samples = [int(3000 * math.sin(2 * math.pi * freq * i / sample_rate)) for i in range(n)]
    return struct.pack(f"<{n}h", *samples)


print("\n=== _strip_for_speech: removes HTML tags, keeps the actual text ===")
tagged = "این یه <b>کلمه</b> مهمه: <tg-spoiler>جواب پنهان</tg-spoiler> و بازم متن."
stripped = voice_note._strip_for_speech(tagged)
check("no angle-bracket tags survive", "<" not in stripped and ">" not in stripped, stripped)
check("ordinary (non-spoiler) words are still present", "کلمه" in stripped, stripped)
# Bug fix (#50): a spoiler's CONTENT — not just its <tg-spoiler> tags — must
# never survive into speech, or the hidden answer gets read aloud, defeating
# the entire point of it being a spoiler. This assertion used to check the
# opposite (that "جواب پنهان" / "hidden answer" WAS still present after
# stripping) — that was checking the bug, not correct behavior; updated to
# check the fix instead.
check("spoiler CONTENT is removed, not just its tags", "جواب پنهان" not in stripped, stripped)

print("\n=== pcm_to_ogg_opus: real ffmpeg round-trip ===")
if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
    print("  SKIP  ffmpeg not installed in this environment — skipping real-conversion checks.")
else:
    pcm = _fake_pcm()
    ogg_bytes = voice_note.pcm_to_ogg_opus(pcm)
    check("output is non-empty", len(ogg_bytes) > 0, len(ogg_bytes))
    check("output starts with the OGG container magic bytes", ogg_bytes[:4] == b"OggS", ogg_bytes[:8])
    check("output is meaningfully smaller than raw PCM (actually encoded, not passed through)",
          len(ogg_bytes) < len(pcm), (len(ogg_bytes), len(pcm)))

    print("\n=== pcm_to_ogg_opus: garbage/failure input still behaves predictably ===")
    empty_ogg = voice_note.pcm_to_ogg_opus(b"")
    check("empty PCM input doesn't crash (produces a tiny/empty valid container or raises cleanly)",
          isinstance(empty_ogg, bytes))

print("\n=== build_voice_note: happy path (generate_speech mocked, real ffmpeg) ===")
with mock.patch("voice_note.generate_speech", return_value=_fake_pcm()):
    result = voice_note.build_voice_note("<b>Hello</b> — a test script.")
if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0:
    check("returns real OGG bytes when TTS succeeds", result is not None and result[:4] == b"OggS", result[:8] if result else None)
else:
    check("returns None or bytes without crashing when ffmpeg is unavailable", result is None or isinstance(result, bytes))

print("\n=== build_voice_note: TTS failure degrades to None, never raises ===")
with mock.patch("voice_note.generate_speech", return_value=None):
    result = voice_note.build_voice_note("Some script that TTS couldn't voice.")
check("generate_speech returning None -> build_voice_note returns None (caller falls back to text)",
      result is None, result)

print("\n=== build_voice_note: ffmpeg failure degrades to None, never raises ===")
with mock.patch("voice_note.generate_speech", return_value=_fake_pcm()), \
     mock.patch("voice_note.pcm_to_ogg_opus", side_effect=subprocess.CalledProcessError(1, "ffmpeg")):
    try:
        result = voice_note.build_voice_note("Script text.")
        raised = False
    except Exception:  # noqa: BLE001
        raised = True
        result = None
check("a CalledProcessError from ffmpeg is caught, not propagated", raised is False)
check("...and build_voice_note returns None in that case", result is None)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
sys.exit(0)
