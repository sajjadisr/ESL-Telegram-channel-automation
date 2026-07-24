"""Shared text helpers for Telegram/Eitaa/Bale posting."""

import re

_OPEN_TAG = re.compile(r"<[^/>][^>]*$")
_CLOSE_TAG = re.compile(r"^[^<]*>")


def truncate_html_safe(text, max_len=4000, suffix="..."):
    """Truncate without splitting an HTML tag mid-way (Audit #10)."""
    if len(text) <= max_len:
        return text
    cut = text[: max_len - len(suffix)]
    cut = _OPEN_TAG.sub("", cut)
    cut = _CLOSE_TAG.sub("", cut)
    return cut + suffix


def strip_spoilers_for_context(text):
    """Remove tg-spoiler answers before feeding prior posts into prompts (Audit #26)."""
    return re.sub(
        r"<tg-spoiler>(.*?)</tg-spoiler>",
        "[پاسخ مخفی]",
        text,
        flags=re.DOTALL,
    )
