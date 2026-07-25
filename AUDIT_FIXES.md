# Audit fixes applied

This documents every change made in response to `Audit.md`, plus the
original `sendPoll` bug from the failed run.

## Critical bug (from the workflow failure log)
- **`telegram_bot.py`**: `send_poll` now sends `json=payload` instead of
  `data=payload`. Form-encoding a list-valued field repeats the key
  (`options=...&options=...`) instead of producing the single JSON-array
  string Telegram's `sendPoll` requires — this was the direct cause of the
  `400 Bad Request` in the failed run.

## 🔴 Critical
1. **Topic runway / low-supply alert** — `data/topics.json` grew from 16 to
   67 topics (added 15 idioms, plus more grammar/vocabulary/common-mistakes
   entries). `main.py` now alerts the admin via Telegram
   (`maybe_alert_low_topic_supply`) once uncovered topics drop to
   `LOW_TOPIC_WARNING_THRESHOLD` (default 10, in `config.py`), instead of
   only printing to a log nobody reads.
2. **Same-day duplicate-run guard** — `database.has_post_on_date()` +
   a check at the top of `main()`. If a post is already recorded for today,
   the run exits immediately, before touching topics, story state, or
   sending anything.
3. **`illustrated_pun` ↔ idiom mismatch** — `get_next_topic()` now accepts
   a `category_filter`. `main.py` requests an `"Idioms"` topic specifically
   for `illustrated_pun`; if the idiom pool is ever exhausted, it falls back
   to a generic topic with an explicit prompt note telling the model to
   invent a suitable idiom itself.

## 🟡 Important
4. **Review fail-open → fail-closed, retries, timeouts** —
   - `ai.py` migrated to the `google-genai` SDK, with a `_call_model` retry
     wrapper (3 attempts, exponential backoff) around every Gemini call.
   - `review_content`'s fallback is now `{"ok": False, ...}` instead of
     `{"ok": True, ...}` — a broken/unparseable review blocks publishing
     (triggers a regenerate) instead of silently waving content through.
   - `generate_json(..., strict=True)` raises instead of silently returning
     a fallback; used for the quiz/poll path specifically, which has no
     other review pass — `main.py` catches this, alerts the admin, and
     skips that day's poll instead of publishing the old hardcoded
     "الف/ب" placeholder question.
   - `telegram_bot.py`: every `requests.post` now has `timeout=20` and goes
     through `_post_with_retry` (3 attempts, backoff on network errors and
     5xx; 4xx is not retried since retrying an invalid payload can't help).
5. **Real poll/quiz feedback loop** — new `poll_feedback.py`:
   - `save_pending_poll()` is called right after a poll/quiz send succeeds
     (`handle_poll_format` in `main.py`), storing the `message_id` in
     `data/pending_polls.json`.
   - `harvest_pending_polls()` runs first thing in `main()`, before
     anything else: closes any pending poll via `stopPoll` (works for
     anonymous polls too, unlike the `poll_answer` webhook a cron-only bot
     could never receive anyway), computes vote/correct-rate, and appends a
     real entry to `data/feedback.json` — no more manual `feedback_add.py`
     typing required.
   - `weekly_strategy.py`'s prompt now surfaces quiz correct-rates as a
     signal, and `best_formats` is constrained to the format keys that
     actually exist in `FORMATS` (previously it could recommend "audio
     clips" or "flashcards", which nothing in the codebase implements).
6. **SDK migration + model-tier swap** —
   - `requirements.txt`: `google-generativeai==0.8.3` → `google-genai==2.14.0`.
   - `weekly_strategy.py` now calls `generate_json` (smart/`REVIEW_MODEL`
     tier) instead of `generate_content` (cheap/high-quota tier), and
     reuses the shared JSON-fence-stripping/parsing logic from `ai.py`
     instead of hand-rolling it again.

## 🟢 Nice-to-have
7. **Onboarding + cross-promo** — `scripts/send_onboarding_message.py`
   (one-time: posts + pins a welcome message) and
   `scripts/send_cross_promo.py` (posts a "also on Bale/Eitaa" message to
   all configured platforms), with an optional
   `.github/workflows/monthly_cross_promo.yml` to automate the latter.
8. **Category-aware dedup** — `database.search_related_posts()` now
   accepts an optional `category` and matches on it in addition to the
   existing `LIKE` keyword match, so near-duplicate topics in the same
   category ("Grocery shopping" vs. "Food and restaurant vocabulary") are
   at least visible to the model even when they don't share keywords.
9. **Git hygiene** — no code change; `data/posts.db` is still committed
   daily as noted in the audit. Worth a periodic `git count-objects -v` /
   `git gc` check, or migrating to a JSON export instead of the raw
   SQLite file, once volume grows.

## Not changed
- Secrets hygiene was already good (audit confirmed no changes needed).

## 🔴 Platform-awareness audit (Eitaa/Bale) — supersedes the "channels.py
   was already doing the right thing" note below
This round looked specifically at whether the code treats Telegram, Eitaa,
and Bale as the three genuinely different platforms they are, rather than
as one API with two clones. The earlier note that `channels.py` was
"already doing the right thing" was true for retries/timeouts, but missed
something more specific — both fixes below are grounded in each platform's
actual, verified behavior, not assumptions:

1. **HTTP-status-only success check was wrong for Eitaa/Bale.**
   `channels._send_platform` and `analytics._summarize_delivery` both only
   checked `response.ok` (HTTP status). eitaayar.ir's own docs are explicit
   that a failed send isn't reliably distinguished from a successful one by
   HTTP status alone — you have to check the `"ok"` field in the JSON body,
   which can be `false` on an otherwise-normal-looking response. Bale's Bot
   API mirrors Telegram's `{"ok": ..., "description": ...}` envelope
   closely enough that the same defensive check is worth having there too.
   Concretely, this means a silent failure (bad chat ID, revoked token,
   etc.) on Eitaa or Bale could previously get logged as `"delivered"`
   everywhere (admin alert, analytics, pending-poll delivery health) even
   though nothing was actually posted.
   - Added `channels._api_ok()` / `channels._api_error_detail()`, which
     check the JSON body in addition to HTTP status, with a clear fallback
     to "trust the HTTP status" when the body isn't JSON or has no `"ok"`
     key. `_send_platform`, `send_eitaa`, `send_bale`, and
     `analytics._summarize_delivery` all now go through this instead of
     checking `.ok` directly.
   - **Telegram's own path (`telegram_bot.py`) was deliberately left
     alone** — its Bot API reliably matches HTTP status to the `"ok"`
     field, so `raise_for_status()` there is already the correct,
     platform-specific check. Routing it through the looser Eitaa/Bale
     check would only risk hiding a real Telegram error.
   - Per-platform message-length limits (`config.py`) are now named
     constants instead of one shared magic `4000` — `TELEGRAM_MAX_MESSAGE_LEN`
     / `BALE_MAX_MESSAGE_LEN` (both 4096, confirmed against each platform's
     own docs) and `EITAA_MAX_MESSAGE_LEN` (4096, explicitly flagged as an
     *unconfirmed assumption* — eitaayar.ir doesn't publish one).

2. **"Comment your answer" CTA assumed a feature none of the three
   platforms are confirmed to have.** `channels.format_quiz_for_extra_channels`
   (the Eitaa/Bale text fallback for polls, since neither platform has
   native polls) closed with "👇 گزینه‌ات رو توی کامنت‌ها بگو!" (tell us in
   the comments). Neither Eitaa's nor Bale's bot API exposes anything like
   a comments/discussion feature on channel posts, and even on Telegram
   that only works if the channel has a discussion group linked — a
   channel-level setting this cron-only script has no way to check. The
   same root cause also let the *AI-generated* text for ordinary posts
   (which broadcasts unmodified to all three platforms via
   `send_message` + `broadcast_extra_channels`) invent a comment-dependent
   closing line on its own — `prompts.LANGUAGE_BALANCE` only ever gave it
   generic permission for "one short invitation to interact," with no
   constraint on what that invitation could assume existed.
   - `format_quiz_for_extra_channels` now takes `correct_index`: for a quiz,
     the correct option is revealed inline via the existing `<tg-spoiler>`
     convention instead of asking for an answer nobody can act on; for a
     vote (no right answer to reveal), the closing line now points readers
     to the Telegram channel, where the real, live poll exists.
   - Added `prompts.CROSS_PLATFORM_ENGAGEMENT_RULE`, wired into
     `build_generation_prompt`, telling the model that its output is
     broadcast unmodified to Eitaa and Bale too and to avoid any CTA
     ("comment below," "reply," "react") that assumes a feature it can't
     guarantee — with self-contained alternatives suggested instead.
   - Added a matching check (`۹.`) to `build_review_prompt`'s checklist as
     defense-in-depth, in case the generation pass still produces one.
