# content-pipeline-architecture.md, implemented

Everything in the punch list (items 1–8) is done in this zip. Files changed,
matching `git status --short`:

```
 M config.py
 M data/topics.json
 M main.py
 M prompts.py
 M requirements.txt
 M topic_selection.py
 M weekly_strategy.py
?? recap_card.py
```

## What changed, item by item

**1. `data/topics.json` schema (additive — nothing existing was touched
structurally, only new optional fields)**
- 5 Idioms entries tagged `has_fa_equivalent` + given a `fa_equivalent`
  field with the actual Persian proverb text: *piece of cake* ↔ مثل آب
  خوردن، *speak of the devil* ↔ چه حلال‌زاده، *kill two birds with one
  stone* ↔ با یک تیر دو نشان زدن، *get cold feet* ↔ پا پس کشیدن، *when pigs
  fly* ↔ وقتی خورشید از مغرب طلوع کنه.
- New **Phrasal verbs** pillar: 20 entries.
- New **Persian transfer errors** pillar: 13 entries, each tagged
  `error_type:preposition|article|word_order|register`.
- **Please sanity-check the 5 proverb pairings with a native speaker before
  `idiom_proverb_bridge` goes live drawing on them.** I picked ones I'm
  genuinely confident about, but I'm not a substitute for a real cultural
  check on something readers will catch instantly if it's wrong — same
  spirit as the blueprint's own "spot-check weekly" advice.

**2. Generalized topic eligibility (`topic_selection.py`, `main.py`)**
- New `_eligible(topic, format_name)` reads `category_filter` /
  `required_tags` off each format's own entry in `prompts.FORMATS`, plus a
  topic's optional `eligible_formats`. `get_next_topic` no longer takes a
  `category_filter` argument — it's derived from the format automatically.
- `main.py::_select_topic` lost its hardcoded
  `if format_name == "illustrated_pun"` branch entirely. Every format is
  now called identically. I traced through the old vs. new logic by hand
  and it's behavior-preserving (verified with a direct test — see below).

**3. Review checklist (`prompts.py::build_review_prompt`)**
- Replaced the hand-spliced, hardcoded-Persian-numeral f-string with an
  assembled `REVIEW_RULES` list + a numeral-rendering helper. Adding a
  format-specific check is now "append one tuple," not "edit the f-string
  and recount everything after it" — demonstrated by
  `idiom_proverb_bridge`'s new proverb-authenticity check (item 4).

**4. Two new formats (`prompts.py`)**
- `idiom_proverb_bridge`: hard-restricted via `category_filter="Idioms"` +
  `required_tags=["has_fa_equivalent"]`. The model is handed the verified
  `fa_equivalent` string directly (via a new `context_block` branch in
  `build_generation_prompt`) rather than asked to recall/invent a pairing —
  this closes a gap I found in the original plan: tagging *that* an idiom
  has an equivalent isn't the same as supplying *which* one.
- `textbook_vs_real`: no category restriction (works on any pillar);
  `error_type:register`-tagged topics are a natural fit but not required.
- Both flow into `schedule_builder.py`'s rotation automatically at
  `DEFAULT_WEIGHT` — confirmed no code change was needed there.

**5. `topic_generation.py` category list**
- No change needed — it already derives categories dynamically from
  `topics.json` (`sorted({t.get("category") for t in existing})`), so the
  two new pillars are picked up automatically. Confirmed by reading the
  code, not assumed.

**6. Pillar-coverage observability (`weekly_strategy.py`)**
- New `topic_selection.all_pillars()` / `pillar_last_covered()` /
  `days_since_pillar_covered()`, surfaced as one new line in the weekly
  intelligence report: which pillar was covered how many days ago (or
  "never"). Visibility only — doesn't change what gets scheduled.

**7. Locked persona (`prompts.py`)**
- New `PERSONA` constant, same pattern as `IMAGE_STYLE`/`IMAGE_PALETTE`.
  Used verbatim in both `build_generation_prompt` and `build_poll_prompt`
  (the doc only asked for the former; I extended it to the latter too,
  since both produce audience-facing voice and the whole point is "don't
  let the persona drift between calls").

**8. Weekly recap → image card (`recap_card.py`, new file)**
- `progress_recap` can now render as a branded PNG card (title + bullet
  list, channel's fixed hex palette) instead of plain text.
- **This needs one asset I could not fetch**: a Persian-capable font
  (recommend [Vazirmatn](https://github.com/rastikerdar/vazirmatn), OFL
  licensed) at `assets/fonts/Vazirmatn-Bold.ttf` (path is
  `config.RECAP_FONT_PATH`). No network access in the sandbox this was
  built in, so it couldn't be downloaded and shipped here.
- Also needs `pip install Pillow arabic-reshaper python-bidi` (added to
  `requirements.txt`) — the latter two handle Persian letter-joining and
  right-to-left reordering, which Pillow doesn't do on its own.
- **Until the font file is added, nothing breaks** — `render_recap_card`
  raises `FontNotAvailable`, and `main.py` catches it and falls back to
  the exact same plain-text recap post that's always worked. The image
  path is purely additive.
- **Not visually verified.** I smoke-tested the compositing logic itself
  (correct PNG output, layout, no crashes — using a placeholder font and a
  stubbed shaping function, since neither the real font nor
  arabic-reshaper/python-bidi could be installed here). I have not seen
  actual Persian text rendered on the card. Look at the first real output
  once you've added the font and adjust `recap_card.py`'s layout constants
  (margins/font sizes/line spacing) if anything looks off.

## Verification done in this sandbox
- All changed files compile (`py_compile`) and import cleanly.
- Direct test: called `get_next_topic` for every format and confirmed each
  draws from the right pool — `idiom_proverb_bridge` → only the 5 tagged
  idioms, `illustrated_pun` → Idioms, `spot_mistake` → Common
  mistakes/Persian transfer errors, `vocab_spotlight` → Vocabulary/Phrasal
  verbs.
- Rendered the actual generation + review prompts for `idiom_proverb_bridge`
  and `spot_mistake` and confirmed the checklist renumbers correctly (11
  items with the tier-check + format-specific proverb check; 10 without,
  no leftover placeholder lines).
- Ran the repo's existing `test_image_pipeline.py` (21 scenarios covering
  `handle_image_format`'s fallback chain) against the modified `main.py` —
  all 21 pass. (The sandbox lacks network access to install the real
  `google-genai` package, so I stubbed it locally just to get past the
  import — the test logic itself ran for real against the real mocked
  HTTP boundaries, same as it would in CI.)
- `data/topics.json` is valid JSON, 154 entries, no duplicate topic names.

## What I did not do
- Did not touch anything under `.github/workflows/` — no scheduling/cron
  changes were called for by this work.
- Did not `git commit` anything in this export — same as the prior
  `APPLY_CHANGES.md` session, this is meant to be diffed against your real
  repo and merged in, not pushed from here.
