# Engagement loop redesign — what changed and why

This covers the four structural gaps raised in chat (measurement, schedule
weighting, dedup, idiom/proverb sourcing) plus voice notes. Each one follows
the same underlying move: pull a decision out of "ask an LLM to eyeball it
and guess" and put it wherever a deterministic, sourced, or measured answer
actually exists.

## 1. Real engagement measurement for every format — `engagement_harvest.py`

`analytics.py` could only ever score quiz/vote_poll (the only formats with a
Bot-API-native metric: the vote tally). Everything else was logged with
`metrics=None` forever — an honest gap, but a gap.

`engagement_harvest.py` closes it with a Telethon (MTProto) userbot session
that *reads* — never increments — a channel message's `views`/`forwards`.
That's information the plain Bot API structurally cannot expose; a userbot
session can.

- `message_id` is now captured and stored for every published post (was
  poll-only before), in `main.py` and `analytics.record_text_post` /
  `record_poll_metrics`.
- `analytics.entries_pending_harvest()` / `apply_harvested_engagement()` do
  the read-then-score work; `main()` calls
  `engagement_harvest.harvest_engagement_metrics()` every run, right next to
  the existing `harvest_pending_polls()`.
- Forwards count more than raw views (`FORWARD_WEIGHT_MULTIPLIER`, config.py)
  — a forward is a subscriber vouching for the post to someone else, the
  actual growth mechanic on a channel with no algorithmic feed
  (`telegram-esl-virality-blueprint.md`, Part 0).
- **Fully optional, fails silent-and-safe**: without `TELEGRAM_API_ID` /
  `TELEGRAM_API_HASH` / `TELETHON_SESSION_STRING` configured, it prints one
  line and changes nothing. Nothing else in the pipeline depends on it.

**Needs your action, once:** run `scripts/generate_telethon_session.py`
locally (interactive login — phone + code, this can't be done for you) and
save the three resulting values as GitHub secrets. See that script's
docstring.

## 2. Schedule weighting is now a formula over real data, not an LLM guess — `schedule_builder.py` / `weekly_strategy.py`

`weekly_strategy.py`'s weekly LLM call used to output a binary
`best_formats` list, re-derived from post titles + feedback text — and it
never even read `analytics.recent_score_summary()`, the precise number the
system already had.

- `schedule_builder.format_weight(format_name, score_summary)` is a pure
  function: `weight = DEFAULT_WEIGHT + REWARD_SCALE * (score - NEUTRAL_SCORE)`,
  floored above zero. No model call anywhere in the path.
- `weekly_strategy.update_schedule_from_engagement()` now reads
  `analytics.recent_score_summary()` directly — no `strategy`/`feedback_list`
  params anymore.
- The weekly LLM call (`build_strategy_prompt`) now **only** produces
  `focus_more_on` / `focus_less_on` — the genuinely qualitative,
  topic-level judgment a formula over a score can't produce.
  `best_formats` is gone from the schema (`validate_strategy` updated to
  match). `audience_profile.py`'s one other reference to
  `strategy["best_formats"]` was updated to read
  `analytics.recent_score_summary()` directly too.
- This gets *better* automatically as #1 backfills more formats — right now
  it's real data for quiz/vote_poll (unchanged) plus whatever
  `engagement_harvest.py` has filled in.

## 3. Semantic dedup — `embeddings.py`

`database.search_related_posts` is a keyword `LIKE` — it structurally can't
catch two posts with unrelated titles that reuse the same example sentence
(the "coffee every morning" incident `context_posts_for_generation`'s
docstring already documents).

- Every published post is embedded (`gemini-embedding-001`, 768 dims) and
  appended to `data/post_embeddings.jsonl` — one line per post, same
  git-hygiene pattern as `posts.jsonl`.
- `main.generate_reviewed_text`'s retry loop now checks the draft's cosine
  similarity against every stored vector (`DEDUP_SIMILARITY_THRESHOLD =
  0.90`, config.py). Above threshold, it's fed back into the same
  regenerate loop the review/stray-character checks already use — the model
  is told *which* prior post it collided with and asked for a genuinely
  different example, never silently blocked.
- Fails open everywhere: an embedding-API hiccup degrades back to the
  existing keyword check for that one post, never blocks or crashes a run.

**Needs your action, once:** run `scripts/backfill_post_embeddings.py` so
dedup covers your existing published history too, not just posts going
forward.

## 4. Idiom↔proverb pairings via search grounding, not a hand-picked list — `research.py`

The original 5 pairings in `topics.json` were hand-picked in one session,
with an explicit "please sanity-check with a native speaker before this
goes live" that never happened. The fix isn't a bigger hand-picked list —
it's a live, generalizable, sourced lookup:

- `ai.generate_grounded_json` (new) calls Gemini with the Google Search
  grounding tool enabled — the model issues real search queries and grounds
  its answer in what comes back, a genuinely independent source, not the
  same model family (`REVIEW_MODEL`) checking itself.
- `research.find_persian_proverb_equivalent(idiom)` uses this to check
  whether a real, citable Persian equivalent exists for any English idiom —
  not just the original 5.
- `scripts/enrich_idiom_proverbs.py` runs this over every Idioms-category
  topic that doesn't have an answer on file yet. High-confidence, sourced
  results get written to `topics.json` with `has_fa_equivalent` +
  `fa_equivalent_source` (making them eligible for `idiom_proverb_bridge`,
  unchanged eligibility gate in `topic_selection.py`); everything else is
  tagged `fa_equivalent_needs_review` instead of silently going live.
  Re-runnable any time — as `topic_generation.py` adds new Idioms topics,
  this keeps the pool growing instead of being frozen at whatever was
  picked once.
- `idiom_proverb_bridge`'s generation prompt is unchanged: it's still handed
  a verified string and told "use exactly this," never asked to invent one.

**Needs your action, periodically:** run
`scripts/enrich_idiom_proverbs.py` (not wired into a GitHub Actions
workflow — `.github/workflows/` isn't in this zip export, see
`NOT_IN_THIS_ZIP.md`). Also worth an occasional human glance at
`fa_equivalent_needs_review` entries in `topics.json`.

## 5. Voice notes — `voice_note.py`, `ai.generate_speech`

New format, `voice_note`: Gemini's native Speech Generation
(`TTS_MODEL = "gemini-3.1-flash-tts-preview"`, two-tier fallback like the
image models) + one `ffmpeg` call to convert the raw PCM to OGG/Opus
(Telegram's `sendVoice` requires exactly that format). Restricted to
`Persian transfer errors` / `Vocabulary` / `Phrasal verbs` topics — the
cases where hearing the sound is structurally the point, which is the only
reason this format earns a slot alongside everything text already covers
well. Falls back to posting the script as plain text (not a manual
hand-off) if TTS or ffmpeg fails.

Seeded onto Thursday in `data/format_schedule.json` (replacing a duplicate
`spot_mistake` day) so it's live now rather than waiting for the next
automatic reweight.

**Worth a sanity check, not blocking:** `TTS_MODEL` and `TTS_VOICE_NAME`
(`ai.py`) were confirmed against Google's current public docs (fetched live
during this session) since this is a preview API, but neither has been
heard against a live call from this sandbox (no network path to
`generativelanguage.googleapis.com` here) — worth one actual listen in AI
Studio's Voice Library before treating the voice pick as final.

## Verification done in this sandbox
- Whole repo: `python3 -m compileall` clean, and a full `import main` smoke
  test (pulls in every new module transitively) succeeds.
- `test_image_pipeline.py` — the repo's existing 21-scenario suite — updated
  for `handle_image_format`'s new 4-tuple return and to mock
  `embeddings.embed_text` (so it doesn't attempt a real network call); all
  21 still pass.
- Four new offline test files, 58 checks total, all passing, no network
  access needed for any of them:
  - `test_schedule_builder.py` (16) — weighting formula, floors/caps, D'Hondt
    allocation, determinism.
  - `test_embeddings.py` (16) — cosine similarity math, threshold behavior,
    fail-open on API failure.
  - `test_analytics_engagement.py` (16) — per-format rolling averages,
    `apply_harvested_engagement`'s idempotency and baseline-snapshot
    behavior, `entries_pending_harvest`'s filters.
  - `test_voice_note.py` (10) — HTML-stripping, and a **real** `ffmpeg`
    PCM→OGG/Opus round-trip (not mocked — the container has ffmpeg
    installed), plus TTS/ffmpeg failure paths degrading to `None` cleanly.
- Confirmed exact SDK call shapes — `embed_content`/`EmbedContentConfig`,
  `types.Tool(google_search=...)`, speech generation's
  `response_modalities=["AUDIO"]` + `SpeechConfig`, Telethon's
  `get_messages`/`Message.views`/`.forwards`/`StringSession` — against the
  actually-installed `google-genai` and `telethon` packages' source, and
  against Google's current public speech-generation docs (fetched live),
  rather than from training-data memory, since several of these are newer
  APIs.
- Did **not** run anything against the live Gemini, Telegram, or Telethon
  APIs — no credentials available in this sandbox, and this environment's
  network policy doesn't reach `generativelanguage.googleapis.com` or
  `api.telegram.org` anyway.

## What I did not do
- Did not touch `.github/workflows/` (not in this zip export — see
  `NOT_IN_THIS_ZIP.md`). `engagement_harvest.harvest_engagement_metrics()`
  runs automatically every `main()` call; `scripts/enrich_idiom_proverbs.py`
  and `scripts/backfill_post_embeddings.py` are standalone and need to be
  run manually, or added to a workflow, to actually execute on a schedule.
- Did not verify `ffmpeg` is present on your actual CI runner — GitHub's
  `ubuntu-latest` hosted runners ship it preinstalled, so this is very
  likely a non-issue, but worth confirming once against the real workflow
  file rather than assumed here.
- Did not `git commit` anything in this export — same as the prior
  `APPLY_CHANGES.md` / `CONTENT_PIPELINE_CHANGES.md` sessions, this is
  meant to be diffed against your real repo and merged in.
