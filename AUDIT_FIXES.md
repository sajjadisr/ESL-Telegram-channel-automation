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
- `channels.py` was already doing the right thing (per-platform
  try/except, `timeout=20` on every call) — used as the reference pattern
  for the Telegram/Gemini fixes above.
- Secrets hygiene was already good (audit confirmed no changes needed).
