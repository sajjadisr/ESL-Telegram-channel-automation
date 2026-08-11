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

# Bug fix (#49): this used to be re.compile(r"<[^>]+>") — the same
# any-angle-brackets pattern as channels.py's old _TAG_STRIP (#18) and
# news.py's old _clean_summary (#47), capable of eating a literal "<"/">"
# text span that isn't a tag at all (e.g. a beginner-English lesson using
# the literal symbols for a comparison). Restricted to the same explicit
# allowlist of real tag names channels.py uses (this is this project's
# own generated content, using Telegram's supported HTML subset — not
# arbitrary third-party HTML the way news.py's RSS summaries are).
_KNOWN_TAGS = "b|strong|i|em|u|ins|s|strike|del|code|pre|a|blockquote|tg-spoiler|tg-emoji|span"
_HTML_TAG_PATTERN = re.compile(rf"</?(?:{_KNOWN_TAGS})(?:\s[^>]*)?>", re.IGNORECASE)
_SPOILER_CONTENT_PATTERN = re.compile(r"<tg-spoiler>.*?</tg-spoiler>", re.DOTALL | re.IGNORECASE)


def _strip_for_speech(text):
    """Bug fix (#50): a <tg-spoiler>...</tg-spoiler> span used to have
    only its TAGS removed here, leaving the previously-hidden text intact
    to be read aloud as ordinary spoken content — defeating the entire
    point of a spoiler the moment voice_note's guidance ever overlaps
    with a format that uses one (e.g. spot_mistake's hidden-answer
    convention). Not currently reachable given voice_note's specific
    topic categories (verified: none of Persian transfer errors/
    Vocabulary/Phrasal verbs currently produce spoiler-tagged content),
    but a real landmine if that guidance ever changes — fixed
    defensively now rather than waiting for it to actually happen. The
    entire spoiler span (tags AND content) is removed before the general
    tag-stripping pass runs, so a hidden answer can never be spoken.
    """
    return _HTML_TAG_PATTERN.sub("", _SPOILER_CONTENT_PATTERN.sub("", text))


FFMPEG_TIMEOUT_SECONDS = 30  # generous for a short voice note; see pcm_to_ogg_opus's #51 fix


def pcm_to_ogg_opus(pcm_bytes, sample_rate=TTS_SAMPLE_RATE_HZ):
    """Raw PCM (ai.generate_speech's output: 24kHz, mono, 16-bit signed
    little-endian) -> OGG/Opus bytes, the one format Telegram's sendVoice
    actually accepts. Runs ffmpeg as a subprocess with the PCM piped in on
    stdin and the encoded file piped out on stdout — no temp files needed.

    Raises subprocess.CalledProcessError (ffmpeg ran but failed),
    FileNotFoundError (ffmpeg isn't installed), or subprocess.TimeoutExpired
    (bug fix #51: every other external call in this codebase — Gemini's
    HTTP options, Telegram's REQUEST_TIMEOUT, RSS's NEWS_REQUEST_TIMEOUT —
    has an explicit timeout; this subprocess call didn't, so a hung or
    misbehaving ffmpeg process could block the entire run indefinitely
    with no application-level safety net) on failure — callers must treat
    any of these as "voice generation failed this time", the same as any
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
        timeout=FFMPEG_TIMEOUT_SECONDS,
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
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"voice_note: ffmpeg conversion failed: {exc}")
        return None
