# Intelligence architecture: where each piece actually lives

This maps the architecture terms from the last conversation onto real code
already in this repo — not a redesign, an inventory. Read this alongside
`AUDIT_FIXES.md`, which documents *why* each piece exists (the audit
finding it fixed). This doc is about *what's automatic vs. what isn't*,
and what actually still needs attention for the channel to run for years
without hand-holding.

Snapshot at time of writing: `data/analytics.json`, `data/feedback.json`,
and `data/campaign_state.json` all show their first entries around
2026-07-25/26. This is a very young channel. Everything below already
exists in code, but most of it hasn't had months of real data to act on
yet — that's expected, not a bug.

---

## 1. Feedback Loop

`poll_feedback.harvest_pending_polls()` — runs first thing in `main()`
(`main.py` line 1 of `main()`), before anything else touches topics, story
state, or generation. It closes any Telegram poll/quiz sent in a prior run
(`stop_poll`), computes the real vote tally and (for quizzes) correct-rate,
and writes a real entry to `data/feedback.json` — no more typing into
`feedback_add.py` by hand (that script still exists, but only as a manual
supplement, not the primary path anymore).

## 2. Closed-Loop System

The full circuit, traced end to end:

1. A quiz/vote_poll goes out → `save_pending_poll()` records it.
2. Next run, `harvest_pending_polls()` closes it → writes
   `feedback.json` (raw note), `analytics.json` (`compute_reward_score`),
   and `audience_profile.json` (`update_from_quiz_result` — weak/strong
   categories, rolling accuracy).
3. Weekly, `weekly_strategy.py` reads `feedback.json` + recent posts →
   writes `strategy.json` (`focus_more_on`/`focus_less_on`/`best_formats`)
   → then `schedule_builder.build_engagement_schedule()` reallocates
   `format_schedule.json`'s weekly slots using `best_formats` as real
   weight (D'Hondt apportionment, `schedule_builder.py`).
4. Every generation call pulls `audience_profile.profile_context_block()`
   and `campaigns.campaign_context_block()` straight into the prompt
   (`prompts.build_generation_prompt`, the `profile_block`/`campaign_block`
   lines) — confirmed by reading the actual f-string, not just the call
   signature.
5. That shapes the next post, which eventually produces the next poll,
   closing the circuit.

Nothing here is decorative — I traced each handoff into the function that
actually consumes it, not just files that produce output nobody reads.

## 3. Learning Loop

Two separate mechanisms, both content-side:

- **Spaced repetition**: `topic_selection.get_due_review_topic()` —
  `REVIEW_INTERVALS_DAYS = [1]` for newly-taught topics, then
  `MAINTENANCE_INTERVAL_DAYS = 90` forever after a topic "graduates."
  `config.py`'s own comment on this is explicit about the tradeoff: at
  `POSTS_PER_DAY = 3` with `FRESH_TOPICS_PER_DAY = 1`, review capacity is
  fixed, so if fresh content keeps arriving forever, the maintenance
  backlog eventually exceeds capacity — handled by always picking the
  single most-overdue topic, a graceful degradation, not a crash.
- **Audience-level learning**: `audience_profile.py` turns real quiz
  correct-rates into `weak_categories`/`strong_categories`, fed back into
  every generation prompt (see #2, step 4) so the model can weight
  practice toward what the audience actually gets wrong — not a
  per-user model (Telegram channel polls are anonymous by platform
  constraint; the module docstring explains why BKT/DKT/clustering don't
  apply here), but a real aggregate signal, not invented.

## 4. Optimization Loop

`schedule_builder.py`'s D'Hondt/Jefferson slot allocation — every week,
`format_schedule.json` gets rebuilt so formats flagged in
`strategy.best_formats` win more of the 7 weekly slots, capped by
`MAX_SLOTS_PER_WEEK` (no runaway toward one format) and floored for
`quiz`/`vocab_spotlight` (so the format that *generates* the optimization
signal, and the one that seeds vocabulary for others, can never be
starved to zero by their own data). This only kicks in once
`MIN_FEEDBACK_FOR_SCHEDULE_UPDATE` real feedback entries exist
(`config.py`) — currently 1 entry exists in `feedback.json`, so this
hasn't triggered yet; that's the right behavior, not a bug (see
`weekly_strategy.update_schedule_from_engagement`'s own guard).

`experiments.py` is the other optimization mechanism — sequential A/B
testing on quiz/vote_poll hook style (`data/experiments.json` already has
one active: `hook_style_v1`). See the note under "What's deliberately
NOT automatic" below — this one stops short of full optimization on
purpose.

## 5. Autonomous Feedback Loop

"Autonomous" here means specifically: *runs without a human doing
anything*, as opposed to "automatic" (runs on a schedule but still needs a
human to read output and act). Two things qualify:

- `harvest_pending_polls()` — no admin action needed to close a poll and
  score it; it happens on the next scheduled run.
- `topic_generation.generate_and_append_topics()` — when
  `topics.json`'s uncovered pool drops to `LOW_TOPIC_WARNING_THRESHOLD`,
  `main.maybe_alert_low_topic_supply()` doesn't just alert — it asks the
  model itself for `AUTO_GENERATE_TOPIC_COUNT` new topics, validates them
  (level must be A1/A2, category must already exist, near-duplicate check
  via `difflib` + substring containment), and appends only what passes.
  The admin alert becomes informational ("topics were added, no action
  needed") rather than a work item, *unless* auto-generation itself fails.

`reader.py`'s low-supply check is the one deliberate exception —
`maybe_alert_low_story_supply()` is alert-only, no auto-generation,
because (per the module's own comment) a good graded story needs real
curation, not a one-line prompt. That's a considered boundary, not a gap.

## 6. Agentic Workflow

`main()` itself is the agent loop for a single run — it makes a sequence
of real decisions, not a fixed script:

harvest pending polls → check daily post cap → resolve today's format
(recap override? weekday schedule?) → for extra slots beyond the first,
choose in priority order (reader installment → due review → news →
fallback fresh/recycle) → generate → review → retry up to
`MAX_REVIEW_ATTEMPTS` with feedback fed back into the next draft → publish
to Telegram + best-effort Eitaa/Bale → record to `posts.db` +
`analytics.json` + `campaign_state.json` + `memory.json` — and at several
points, alerts a human instead of guessing (invalid quiz JSON, no
options returned, image generation exhausted, all Gemini + Groq providers
failing). That last part is what keeps this "agentic" instead of
"autonomous-and-unaccountable" — every failure mode either self-heals or
surfaces to the admin explicitly, never silently.

## 7. Self-Improving System Architecture

The three concrete self-improvement mechanisms, all already covered above
individually — listed together here because this is the term where
"does it actually compound over time" matters most:

- `topic_generation.py` — the content *pool* grows itself.
- `schedule_builder.py` — the *schedule* reshapes itself around real
  engagement.
- `MAINTENANCE_INTERVAL_DAYS` — old lessons get refreshed indefinitely
  instead of quietly rotting once the channel's been running for years
  (Bahrick permastore reasoning, cited directly in `topic_selection.py`).

None of these need a human to keep functioning. They need a human to
*review* (the weekly Telegram digest from
`weekly_strategy.send_weekly_intelligence_report()`), which is a
deliberate design choice, covered next.

---

## What's deliberately NOT automatic

`experiments.py`'s own docstring is explicit: *"nothing here auto-adopts a
winner."* Once both variants of an active experiment hit
`MIN_SAMPLES_TO_FLAG_EXPERIMENT` (3 — small on purpose, since this channel
runs roughly one quiz and one vote_poll a week), the weekly report tells
the admin the result is readable and stops there. A human reads it and
decides whether to keep the winning variant.

This was a considered choice already in the code, not an oversight I'm
flagging — the reasoning holds up: at ~1 quiz/week, "enough samples" is a
matter of months, and auto-adopting on `n=3` per variant would be
statistically shaky. I didn't change it without being asked.

**If you want this fully hands-off too**, the concrete next step would be:
once both variants clear the sample threshold, automatically pick the
higher `avg_score` variant, retire the experiment, fold its `prompt_note`
into `strategy.json` as a standing instruction, and start a new experiment
from a queue. That's a real code change (not just flipping a flag) since
it touches what "winning" means when `avg_score` is close — happy to build
it if you want it, but I'd rather you decide that tradeoff than have it
silently applied.

---

## The actual gap: `.github/workflows/` was missing from this zip

See `NOT_IN_THIS_ZIP.md` for the full account. Short version: this zip
had no scheduled trigger for `main.py` or `weekly_strategy.py` at all —
everything documented above is real code, but none of it runs on its own
without a cron job invoking it. Two of your own diffs prove those workflow
files already exist in your actual repo; I reconstructed them from the
fragments those diffs contained plus `config.py`'s own documented secrets,
clearly marked as reconstructions at the top of each file. Diff them
against what's actually deployed before trusting them over your real ones.

## Known, deliberately-deferred limitation (unchanged from `AUDIT_FIXES.md`)

`data/posts.db` is a binary SQLite file, committed to git on every run,
forever. `AUDIT_FIXES.md` item 9 already flagged this ("worth a periodic
`git count-objects -v` / `git gc` check, or migrating to a JSON export...
once volume grows") and explicitly deferred it. I didn't act on it now,
for a concrete reason: `git gc` run inside a GitHub Actions checkout only
repacks that ephemeral clone — it has zero effect on the actual
GitHub-hosted repository's history, so adding it as a workflow step would
look like a fix without being one. The real fix, if/when this becomes a
practical problem, is switching `posts.db`'s git-tracked representation to
something line-diffable (e.g. an appended JSON-Lines export alongside the
DB, with the DB itself gitignored and rebuilt from it), not a gc call. At
this channel's current volume (data files starting 2026-07-25) this isn't
causing any real problem yet — worth revisiting in a year, not now.
