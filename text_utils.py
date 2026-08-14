"""Shared text helpers for Telegram/Eitaa/Bale posting."""

import re

# Telegram's actual supported HTML subset (core.telegram.org/bots/api#html-style).
_KNOWN_TAGS = "b|strong|i|em|u|ins|s|strike|del|code|pre|a|blockquote|tg-spoiler|tg-emoji|span"

_OPEN_TAG_CUTOFF = re.compile(r"<[^/>][^>]*$")  # a tag's own syntax cut mid-way, e.g. "...<b clas"
_TAG_TOKEN = re.compile(rf"<(?P<close>/)?(?P<name>{_KNOWN_TAGS})(?:\s[^>]*)?>", re.IGNORECASE)

# Bounded safety valve for the re-trim loop in truncate_html_safe (see below) --
# in practice this project's content never nests more than one or two tags
# deep, so this converges in 1 iteration almost always.
_MAX_TRIM_ITERATIONS = 5


def escape_html(text):
    """Escape &, <, > so arbitrary text (model output, review feedback,
    exception messages) can't be misread as markup by Telegram's HTML
    parser when spliced into a parse_mode=HTML message.

    Telegram only requires these three characters escaped outside of
    actual tags (core.telegram.org/bots/api#html-style); order matters —
    '&' has to go first or it would double-escape the entities this same
    call just produced for '<' and '>'.

    Use this on any *dynamic* fragment (an f-string variable), never on
    a whole message that's expected to contain real formatting tags —
    e.g. weekly_strategy.py's report header hardcodes an intentional
    <b>...</b> and must NOT be passed through this."""
    text = str(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _open_tags_at_end(text):
    """Which known tags are still open (unclosed) at the end of `text`,
    innermost-last, by walking every open/close token in order."""
    stack = []
    for match in _TAG_TOKEN.finditer(text):
        name = match.group("name").lower()
        if match.group("close"):
            if name in stack:
                # Pop up to and including this tag. Handles the well-formed
                # case (it's exactly the top of the stack) and also a
                # malformed/out-of-order source (still converges instead of
                # leaving a phantom entry stuck on the stack forever).
                while stack and stack[-1] != name:
                    stack.pop()
                if stack:
                    stack.pop()
        else:
            stack.append(name)
    return stack


def truncate_html_safe(text, max_len=4000, suffix="..."):
    """Truncate `text` to at most `max_len` characters without producing
    broken HTML.

    Bug fixes:
    - This used to only repair a truncation landing INSIDE a tag's own
      opening syntax (e.g. mid-"<b clas"). It did nothing for the far more
      common case of a cut landing AFTER a complete opening tag but
      BEFORE its matching closing tag (e.g. after "<b>" but before
      "</b>") — that left a dangling, unterminated tag in real published
      output, which Telegram's HTML parser rejects with a 400 error.
      Verified: truncating ".....<b>important word</b>....." used to
      produce "...<b>important..." (an unclosed <b>); it now produces
      "...<b>important</b>...".
    - The old _CLOSE_TAG regex (anchored to the START of the string) could
      never fire on a truncation from the END of a string — removed as
      dead code; its job is now done properly by the tag-stack scan below.
    """
    if len(text) <= max_len:
        return text
    cut = text[: max_len - len(suffix)]
    cut = _OPEN_TAG_CUTOFF.sub("", cut)

    for _ in range(_MAX_TRIM_ITERATIONS):
        closing = "".join(f"</{name}>" for name in reversed(_open_tags_at_end(cut)))
        overage = len(cut) + len(closing) + len(suffix) - max_len
        if overage <= 0:
            return cut + closing + suffix
        cut = _OPEN_TAG_CUTOFF.sub("", cut[:-overage])
    # Fell through the safety valve (would need pathologically deep nesting
    # to ever happen with this project's actual content) — return the best
    # attempt rather than loop forever.
    closing = "".join(f"</{name}>" for name in reversed(_open_tags_at_end(cut)))
    return cut + closing + suffix


def strip_spoilers_for_context(text):
    """Remove tg-spoiler answers before feeding prior posts into prompts (Audit #26)."""
    return re.sub(
        r"<tg-spoiler>(.*?)</tg-spoiler>",
        "[پاسخ مخفی]",
        text,
        flags=re.DOTALL,
    )
