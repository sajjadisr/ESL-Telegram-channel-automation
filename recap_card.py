"""Weekly recap rendered as a branded image card (content-pipeline-
architecture.md §8), instead of the plain-text-only post progress_recap has
always been.

Uses the channel's fixed visual identity (prompts.IMAGE_PALETTE's hex
values) so the card reads as "the same channel", not a generic template.

--- Required asset this repo does NOT bundle ---
Rendering Persian text onto an image needs a font file that actually
contains Persian glyphs — the sandbox this was built in has no network
access, so no such font could be downloaded and shipped here. Before this
feature can produce real output:

  1. Download an OFL-licensed Persian font, e.g. Vazirmatn:
     https://github.com/rastikerdar/vazirmatn
  2. Place the Bold weight at config.RECAP_FONT_PATH
     (default: assets/fonts/Vazirmatn-Bold.ttf)
  3. pip install the two new requirements.txt entries: Pillow,
     arabic-reshaper, python-bidi (arabic_reshaper + python-bidi handle
     Persian letter-joining and right-to-left reordering — Pillow's
     draw.text does neither on its own).

Until the font file is in place, render_recap_card raises
FontNotAvailable, and main.py's caller is expected to catch that and fall
back to the plain-text progress_recap post — the image card is additive,
never a hard requirement for the recap to go out.

--- Not visually verified ---
Without that font file and a way to view the rendered PNG, the layout
below (margins, font sizes, line spacing) is a reasonable starting point,
not a pixel-checked final design — look at the first real output and
adjust constants before trusting it unattended.
"""

import io
import os

from config import RECAP_FONT_PATH
from prompts import IMAGE_PALETTE_HEX


class FontNotAvailable(Exception):
    pass


def _shape(text):
    """Reshape (letter-joining) + bidi-reorder Persian text so Pillow's
    left-to-right glyph placement draws it correctly. Import is local to
    this function, not module-level, so the rest of the codebase (which
    never rasterizes Persian text) doesn't gain a hard dependency on these
    two packages just by importing this module."""
    import arabic_reshaper
    from bidi.algorithm import get_display

    return get_display(arabic_reshaper.reshape(text))


def _fit_font(draw, text, base_size, max_width, min_size=28, step=4):
    """Bug fix (#52): render_recap_card used to draw the title/bullet text
    at a fixed font size with no width check at all — a longer-than-
    expected title or topic name would silently run off the left edge of
    the canvas, since Pillow's draw.text doesn't wrap or shrink on its
    own. This tries base_size first, then steps down until either the
    shaped text fits max_width or min_size is reached (returned as-is at
    that point — see _fit_and_truncate below for the backstop that
    guarantees no overflow even then)."""
    from PIL import ImageFont

    size = base_size
    while size > min_size:
        font = ImageFont.truetype(RECAP_FONT_PATH, size)
        if draw.textlength(text, font=font) <= max_width:
            return font, size
        size -= step
    return ImageFont.truetype(RECAP_FONT_PATH, min_size), min_size


def _fit_and_truncate(draw, text, base_size, max_width, min_size=28, step=4, suffix="…"):
    """_fit_font, plus a hard backstop: if the text still doesn't fit even
    at min_size (an extreme case — a single word too long to shrink into
    width, e.g. a very long English phrase with no spaces), truncate it
    with an ellipsis so it can never actually overflow max_width,
    whatever the input. Returns (text_to_draw, font)."""
    font, size = _fit_font(draw, text, base_size, max_width, min_size, step)
    if draw.textlength(text, font=font) <= max_width:
        return text, font
    truncated = text
    while truncated and draw.textlength(truncated + suffix, font=font) > max_width:
        truncated = truncated[:-1]
    return (truncated + suffix if truncated else suffix), font


def render_recap_card(title, bullets, size=1080):
    """title: str (Persian). bullets: list[str] — short lines, already in
    their final display form (topic names as they should appear; mixed
    Persian/English is fine, _shape handles mixed-direction runs).

    Returns PNG bytes. Raises FontNotAvailable if RECAP_FONT_PATH doesn't
    exist (see module docstring).

    Bug fix (#53): bullet lines used to be drawn as _shape(f"‹ {bullet}")
    — baking a directional punctuation mark directly into the string
    before bidi-reordering. Whether "‹" ends up visually on the correct
    (left) side of the reshaped RTL text depends on how python-bidi
    classifies a neutral character adjacent to a strong-RTL run, which
    this project's own change notes admit was never actually verified
    against the real shaping library (only a stub was exercised — and
    this sandbox has no network access to install the real one either).
    Rather than ship an unverified guess, the marker is now drawn as an
    independent graphical rectangle at a fixed position, exactly like the
    accent bar near the top of this function already is — sidestepping
    the bidi-interaction question entirely instead of hoping it resolves
    the way it's meant to.
    """
    if not os.path.exists(RECAP_FONT_PATH):
        raise FontNotAvailable(
            f"{RECAP_FONT_PATH} not found. See recap_card.py's module "
            "docstring for what to download and where to put it."
        )

    # Local imports: Pillow is only a hard dependency for this one feature,
    # same reasoning as the arabic_reshaper/bidi imports in _shape above.
    from PIL import Image, ImageDraw

    bg = IMAGE_PALETTE_HEX["deep_purple"]
    accent = IMAGE_PALETTE_HEX["burnt_orange"]
    title_color = IMAGE_PALETTE_HEX["coral"]
    body_color = IMAGE_PALETTE_HEX["warm_sand"]

    img = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(img)

    margin = 90
    right_edge = size - margin
    text_max_width = size - 2 * margin

    # Small accent bar as the only "logo-like" visual anchor — IMAGE_NEGATIVE
    # rules out actual logos/brand marks in the AI-generated illustrations,
    # keeping the same restraint here rather than adding a wordmark.
    draw.rectangle([margin, margin, margin + 140, margin + 10], fill=accent)

    y = margin + 60
    title_text, title_font = _fit_and_truncate(draw, _shape(title), 64, text_max_width)
    draw.text((right_edge, y), title_text, font=title_font, fill=title_color, anchor="ra")
    y += 130

    line_height = 68
    max_y = size - margin
    marker_width, marker_height, marker_gap = 14, 14, 16
    for bullet in bullets:
        if y + line_height > max_y:
            break  # ran out of vertical space — caller already caps the
            # bullet count (progress_recap draws at most 8 titles), this
            # is just a hard stop so a longer list can't overflow the canvas
        bullet_text, bullet_font = _fit_and_truncate(
            draw, _shape(bullet), 42, text_max_width - marker_width - marker_gap,
        )
        text_baseline_y = y + (line_height - marker_height) // 2
        draw.rectangle(
            [right_edge - marker_width, text_baseline_y,
             right_edge, text_baseline_y + marker_height],
            fill=accent,
        )
        draw.text((right_edge - marker_width - marker_gap, y), bullet_text,
                   font=bullet_font, fill=body_color, anchor="ra")
        y += line_height

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
