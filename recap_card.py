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


def render_recap_card(title, bullets, size=1080):
    """title: str (Persian). bullets: list[str] — short lines, already in
    their final display form (topic names as they should appear; mixed
    Persian/English is fine, _shape handles mixed-direction runs).

    Returns PNG bytes. Raises FontNotAvailable if RECAP_FONT_PATH doesn't
    exist (see module docstring)."""
    if not os.path.exists(RECAP_FONT_PATH):
        raise FontNotAvailable(
            f"{RECAP_FONT_PATH} not found. See recap_card.py's module "
            "docstring for what to download and where to put it."
        )

    # Local imports: Pillow is only a hard dependency for this one feature,
    # same reasoning as the arabic_reshaper/bidi imports in _shape above.
    from PIL import Image, ImageDraw, ImageFont

    bg = IMAGE_PALETTE_HEX["deep_purple"]
    accent = IMAGE_PALETTE_HEX["burnt_orange"]
    title_color = IMAGE_PALETTE_HEX["coral"]
    body_color = IMAGE_PALETTE_HEX["warm_sand"]

    img = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype(RECAP_FONT_PATH, 64)
    body_font = ImageFont.truetype(RECAP_FONT_PATH, 42)

    margin = 90
    right_edge = size - margin

    # Small accent bar as the only "logo-like" visual anchor — IMAGE_NEGATIVE
    # rules out actual logos/brand marks in the AI-generated illustrations,
    # keeping the same restraint here rather than adding a wordmark.
    draw.rectangle([margin, margin, margin + 140, margin + 10], fill=accent)

    y = margin + 60
    draw.text((right_edge, y), _shape(title), font=title_font, fill=title_color, anchor="ra")
    y += 130

    line_height = 68
    max_y = size - margin
    for bullet in bullets:
        if y + line_height > max_y:
            break  # ran out of vertical space — caller already caps the
            # bullet count (progress_recap draws at most 8 titles), this
            # is just a hard stop so a longer list can't overflow the canvas
        draw.text((right_edge, y), _shape(f"‹ {bullet}"), font=body_font, fill=body_color, anchor="ra")
        y += line_height

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
