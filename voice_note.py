"""Turns a generated post script into an actual Telegram voice note:
Gemini TTS (ai.generate_speech) for the audio, ffmpeg for the PCM -> OGG/
Opus conversion Telegram's sendVoice requires (telegram_bot.send_voice).

Why this format exists at all: telegram-esl-virality-blueprint.md's case
for it is that pronunciation is exactly the thing text can't teach — no
phonetic respelling conveys what a sound actually sounds like, or where a
Persian speaker's mouth habitually goes wrong on it. Every other format in
this codebase is text; this is the one place actual audio earns its slot
(see prompts.FORMATS["voice_note"]'s category_filter/guidance for how that
constrains which topics it's even offered for).
"""

import re
import subprocess

from ai import generate_speech, TTS_SAMPLE_RATE_HZ

# Telegram/Persian-language content in this channel uses a handful of HTML
# tags (<b>, <i>, <tg-spoiler>, etc. — see prompts.py's REVIEW_RULES) that
# render fine as text but must never be read aloud literally ("less than b
# greater than..."). Stripped for the TTS call only — the original,
# tag-and-all content is still what's posted as the voice note's caption
# and what's used everywhere else (dedup embedding, database, analytics).
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def _strip_for_speech(text):
    return _HTML_TAG_PATTERN.sub("", text)


def pcm_to_ogg_opus(pcm_bytes, sample_rate=TTS_SAMPLE_RATE_HZ):
    """Raw PCM (ai.generate_speech's output: 24kHz, mono, 16-bit signed
    little-endian) -> OGG/Opus bytes, the one format Telegram's sendVoice
    actually accepts. Runs ffmpeg as a subprocess with the PCM piped in on
    stdin and the encoded file piped out on stdout — no temp files needed.

    Raises subprocess.CalledProcessError (ffmpeg ran but failed) or
    FileNotFoundError (ffmpeg isn't installed) on failure — callers must
    treat either as "voice generation failed this time", the same as any
    other content step that can fail, not as a fatal setup error worth
    crashing main() over. ffmpeg is a system dependency, not a pip package
    — see requirements.txt's comment on this."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-f", "s16le",             # input: raw signed 16-bit little-endian PCM
            "-ar", str(sample_rate),   # input sample rate
            "-ac", "1",                # input channel count (mono)
            "-i", "pipe:0",
            "-c:a", "libopus",
            "-b:a", "48k",             # comfortably above what Opus needs for clear speech
            "-f", "ogg",
            "pipe:1",
        ],
        input=pcm_bytes,
        capture_output=True,
        check=True,
    )
    return result.stdout


def build_voice_note(script_text):
    """script_text: the already-generated, already-reviewed post content
    (main.generate_reviewed_text's output) — this only adapts it for TTS
    and converts the result, it doesn't generate or review anything
    itself. Returns OGG/Opus bytes, or None if either step failed (TTS
    itself returned nothing after both model tiers, or ffmpeg isn't
    available/failed) — main.handle_voice_format falls back to posting
    script_text as a plain text post in that case, the same "auto path
    breaks -> don't lose the day's post" pattern handle_image_format uses
    for images."""
    speech_text = _strip_for_speech(script_text)
    pcm = generate_speech(speech_text)
    if pcm is None:
        return None
    try:
        return pcm_to_ogg_opus(pcm)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"voice_note: ffmpeg conversion failed: {exc}")
        return None
