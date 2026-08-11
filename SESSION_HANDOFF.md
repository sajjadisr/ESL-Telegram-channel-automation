# SESSION_HANDOFF.md

For the next Claude session picking up this project. Read
`PROJECT_STATUS.md` first for the full 101-item status table — this file
covers what happened, how it was verified, what's risky, and what to do
next.

## What this session actually did

Started from `english-channel-ai-bug-report.md` (101 items) and applied
surgical fixes file-by-file, testing each fix immediately after writing
it (not batched), and searching for new bugs opportunistically along the
way (7 found beyond the original 101 — listed in `PROJECT_STATUS.md`'s
"Also completed" section).

**Result: 71 of 101 items fully fixed and verified, 6 partially fixed, 22
not started, 2 cannot be resolved from this environment** (see
`PROJECT_STATUS.md` for the itemized breakdown and reasons).

The work stopped mid-way through the list (after `reader.py`, before
`audience_profile.py`) because the user paused it for this handoff — not
because of a blocker. The remaining 24 items (22 not-started + 2
partial-with-more-possible) are entirely code the session never reached,
not code that was attempted and failed.

## Files created

- `clock.py` — timezone-correct `today()`/`today_str()`/`weekday_name()`
  helpers, replacing naive `datetime.date.today()` (Asia/Tehran is
  UTC+3:30 year-round; the runner's system clock is UTC) and
  locale-dependent `strftime("%A")`.

## Files modified (26 total, confirmed via diff against the original upload)

`ai.py, analytics.py, campaigns.py, channels.py, config.py, database.py,
embeddings.py, engagement_harvest.py, feedback_add.py, main.py, memory.py,
news.py, poll_feedback.py, prompts.py, reader.py, recap_card.py,
schedule_builder.py, telegram_bot.py, text_utils.py, topic_selection.py,
voice_note.py, scripts/backfill_post_embeddings.py,
scripts/check_daily_completion.py, scripts/enrich_idiom_proverbs.py,
test_schedule_builder.py, test_voice_note.py`

Every one of these files has inline `# Bug fix (#N): ...` comments at
each change explaining what was wrong and why the fix is correct — read
those in-place rather than relying on this document for the reasoning.

**Untouched (confirmed byte-identical to the original upload):**
`audience_profile.py, experiments.py, research.py, topic_generation.py,
weekly_strategy.py`, all of `scripts/` except the three listed above,
all four `.github/workflows/*.yml`, `.gitignore`, `package-lock.json`,
every file under `data/` except `data/posts.db` (see below), all `*.md`
docs.

**`data/posts.db`** shows as differing but is NOT a data change — it's a
disposable local SQLite cache (see `database.py`'s own comments) that got
rebuilt from `data/posts.jsonl` while running tests in this session.
`data/posts.jsonl` (the real source of truth) is byte-for-byte identical
to the original. No `data/*.json` file was intentionally edited this
session, despite some `PROJECT_STATUS.md` items describing data-level
fixes (#71, #74) — those still need doing.

## Tests/checks actually run, and their results (as of the end of this session)

```
test_image_pipeline.py:        21 passed, 0 failed
test_embeddings.py:            16 passed, 0 failed
test_schedule_builder.py:      20 passed, 0 failed   (was 16 — extended for #89)
test_analytics_engagement.py:  16 passed, 0 failed
test_voice_note.py:            11 passed, 0 failed   (was 10 — one assertion corrected, see below)
------------------------------------------------------
Total:                         84 passed, 0 failed
```
Plus: `ast.parse` on every `.py` file in the tree (all valid), `import
main` (succeeds), and dozens of targeted one-off verification scripts run
per-fix (not preserved as files — each fix's specific reproduction is
described in its own inline comment and in this session's chat history).

**Test environment note:** this sandbox has no real `google-genai` or
`telethon` packages and no network access. Testing used hand-written stub
packages at `/home/claude/stubs/google/genai/` and
`/home/claude/stubs/telethon/` (minimal `Client`/`TelegramClient`
classes sufficient to exercise the retry/fallback/auth logic paths). If
the next session needs to re-run tests, either recreate these stubs or
run in an environment with the real packages installed. Required env
vars for tests: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`,
`GEMINI_API_KEY`, `TELEGRAM_ADMIN_CHAT_ID` (any non-empty values work for
testing — nothing makes a real network call except where a test
deliberately checks the network-error path).

**One existing test was fixed, not just re-run:** `test_voice_note.py`
had an assertion (`"the actual words are still present"`) that literally
checked spoiler content survived text-stripping — that was the bug (#53)
being asserted as correct. Split into two checks: ordinary text survives,
spoiler content does not.

## Unresolved issues discovered this session (not in the original 101)

All listed in `PROJECT_STATUS.md`'s "Also completed" section since all
seven were found *and fixed* in this session. No new *unfixed* issues
were discovered beyond the original 101 — the only new findings were
things noticed and closed while implementing an existing item.

## Important decisions/constraints not obvious from the code

1. **`#95` (send_eitaa's `data=` vs `send_bale`'s `json=`) was deliberately
   left unchanged.** Investigated, not missed. There's no way to verify
   eitaayar.ir's actual required encoding from this environment, and
   changing an unconfirmed third-party integration's request shape
   without a way to test it risks breaking something that may currently
   work by coincidence.
2. **`#38` (`_EXCLUDED_TOPICS` matches nothing) was deliberately left
   unchanged.** There's no real topic name to put in it — the original
   entry ("Common everyday idioms") doesn't exist in `data/topics.json`.
   Any "fix" would mean inventing a value. Currently harmless dead code.
3. **`#76` (missing Persian font) cannot be fixed from this environment** —
   no network access to fetch `Vazirmatn-Bold.ttf` or any real substitute.
   The code already degrades gracefully; `#55`/`#56`'s width/bidi fixes to
   `recap_card.py` were verified using a substitute system font
   (DejaVu Sans Bold) instead, at the pixel level.
4. **The timezone fix (`clock.py`) is a fixed-offset, not `zoneinfo`.**
   Iran suspended DST permanently in September 2022 (verified via web
   search during this session), so a fixed `+3:30` offset is correct and
   needs no timezone database dependency. If Iran ever reinstates DST,
   `config.TEHRAN_UTC_OFFSET_HOURS` is the one place to change.
5. **`main.py`'s `_select_topic` now returns a 4-tuple**
   `(topic, extra_note, invented_idiom_mode, source)`, and
   `topic_selection.get_next_topic` now returns `(topic, source)` instead
   of just `topic`. Any new code calling either must unpack the extra
   value — a caller expecting the old shape will raise a `ValueError`
   on unpacking, not silently misbehave, so this is safe but not
   backward-compatible.
6. **`memory.json`'s `covered_topic_history` entries now have a `source`
   field** (`"fresh"`/`"recycle"`/`"review"`). Entries without one
   (all pre-existing data, since none of `data/*.json` was edited this
   session) are treated as `"review"` by `get_due_review_topic` for
   backward compatibility — this can only make a topic due *later* than
   the old buggy math, never earlier.
7. **`channels.NOT_CONFIGURED` is a real sentinel object, not `None`.**
   Any new code checking `response is None` to mean "not configured" is
   now checking the wrong thing — check `response is channels.NOT_CONFIGURED`
   instead. `_api_ok()` already handles both correctly internally.

## Known risks going into the next session

- **`#83` (audience weak/strong tracker fed the wrong category) is the
  single highest-value unfixed item** — confirmed still present via grep
  just before this handoff was written. It's also the most subtle to fix
  correctly: it spans `main.py` → `handle_poll_format` →
  `save_pending_poll` → `poll_feedback.py` → `audience_profile.py`, and
  needs the *actual quiz subject's category* threaded through that whole
  chain, not just a different value substituted in one spot.
- **Data-file fixes (#71, #74, #75, #77) are pure editing, no code risk**,
  but haven't been done — don't assume `PROJECT_STATUS.md`'s "code fixed"
  note for #71/#74 means the data is also clean.
- **`#96`/`#97` are not really "bugs to fix"** — they're missing features
  / architectural tensions from the design document. Don't attempt these
  as quick surgical patches; they need a scoping conversation first (see
  milestone M9 below).
- **This sandbox cannot install `google-genai`/`telethon`/`arabic_reshaper`/
  `python-bidi` or reach any real API.** Every fix in this session was
  verified with stubs or substitute libraries. Nothing has been tested
  against the real Gemini, Telegram, Telethon, or Eitaa/Bale APIs. This
  is a pre-existing condition of the whole project (documented in its own
  `ENGAGEMENT_LOOP_CHANGES.md`), not something this session made worse.

## Recommended next milestone

**M1 (below)** — it's the smallest, most isolated, and closes out the
"main.py orbit" cleanly before moving to files nobody has touched yet.

---

## Next-session work plan (milestones)

This is a plan, not an instruction to start implementing. Grouped by file
overlap and dependency so each milestone can be done — and tested — in one
sitting without reopening files from a different milestone.

### M1 — Finish the main.py-adjacent quick fixes
- **Issues:** #39 (recap title skips stray-char check)
- **Files:** main.py
- **Prerequisites:** none — `find_stray_script_chars` and
  `build_recap_title_prompt` both already exist and are already imported
  in main.py.
- **Completion criteria:** the recap-card title generation path calls
  `find_stray_script_chars` on the model's output and strips/retries on a
  hit, same pattern as the main content-generation path in
  `generate_reviewed_text`.
- **Verification:** a targeted script mocking `generate_content` to
  return a title containing a stray character, confirming it's stripped
  before being handed to `recap_card.render_recap_card`.

### M2 — Audience profiling correctness
- **Issues:** #41 (weak/strong never clears on "medium"), #83 (wrong
  category fed to the tracker — **highest priority**)
- **Files:** audience_profile.py, poll_feedback.py, main.py
- **Prerequisites:** read `poll_feedback.py`'s `harvest_pending_polls`
  and `main.py`'s poll branch together first — #83 requires understanding
  exactly what "the quiz's actual subject category" should mean when the
  quiz topic itself is `recent_titles[0]` (see main.py's `#30` fix,
  already done, for how that title is now chosen).
- **Completion criteria:** #83: `update_from_quiz_result` receives the
  real topic category the quiz was about, not the week's campaign theme.
  #41: a correct-rate in the 51-79% range clears a stale weak/strong flag
  rather than leaving it stuck.
- **Verification:** unit tests against `audience_profile.update_from_quiz_result`
  directly (no main.py integration test needed) plus one end-to-end check
  that the category value reaching it traces back to the real quiz topic.

### M3 — Poll lifecycle hardening
- **Issues:** #42 (stuck polls retry forever), #82 (harvest-window
  permanent loss)
- **Files:** poll_feedback.py, analytics.py
- **Prerequisites:** none — independent of M2 despite both touching
  poll_feedback.py (different functions: `harvest_pending_polls` for #42,
  `entries_pending_harvest` lives in analytics.py for #82).
- **Completion criteria:** #42: a pending poll that fails to stop after
  N attempts or M days is dropped with an admin alert instead of retried
  forever. #82: a post that never got any engagement reading during its
  window is distinguishable from one that got a final reading, so a later
  fix to the harvest mechanism could still backfill it.
- **Verification:** unit tests with a mock `stop_poll` that always fails,
  confirming the entry eventually stops being retried and an alert fires
  once.

### M4 — Standalone scripts cleanup
- **Issues:** #61, #62, #63, #64 (send_cross_promo.py/send_onboarding_message.py),
  plus finishing #93 (remaining `@InEnglish` in these same two files)
- **Files:** scripts/send_cross_promo.py, scripts/send_onboarding_message.py
- **Prerequisites:** `config.CHANNEL_DISPLAY_NAME` and
  `channels.broadcast_extra_channels`/`_send_platform` already exist and
  are correct (this session's work) — this milestone is purely about
  routing these two scripts through what already exists, not building
  anything new.
- **Completion criteria:** both scripts call `broadcast_extra_channels`
  instead of `send_eitaa`/`send_bale` directly; `send_message` calls are
  wrapped so a Telegram failure doesn't prevent the Eitaa/Bale attempt;
  the pin-message call in send_onboarding_message.py goes through
  `telegram_bot._post_with_retry`; every hardcoded `@InEnglish` replaced
  with `config.CHANNEL_DISPLAY_NAME`.
- **Verification:** these scripts have no existing test file — write
  simple mock-based checks (they're short, ~50-90 lines each) confirming
  a Telegram failure still allows the Eitaa/Bale attempt to proceed.

### M5 — Migration script safety
- **Issues:** #65
- **Files:** scripts/migrate_posts_db_to_jsonl.py
- **Prerequisites:** none, fully independent.
- **Completion criteria:** the script refuses (or warns loudly and
  requires confirmation) before overwriting `data/posts.jsonl` with fewer
  rows than it already has.
- **Verification:** a test with a `posts.jsonl` containing more rows than
  a stale `posts.db`, confirming the script doesn't silently regress it.

### M6 — GitHub Actions workflow fixes
- **Issues:** #69, #70, and optionally #87/#88 (add a caveat comment
  noting these files are a reconstruction)
- **Files:** .github/workflows/monthly_cross_promo.yml,
  .github/workflows/daily_post.yml
- **Prerequisites:** none. Note from this session: these files were
  entirely absent from the original upload and are already a
  best-effort reconstruction (see `NOT_IN_THIS_ZIP.md`) — changes here
  can't be tested by running the workflow, only by reasoning about the
  YAML.
- **Completion criteria:** #69: `monthly_cross_promo.yml` gets a
  `concurrency:` group like the other two workflows. #70: the commit step
  distinguishes a clean run from a partial failure (e.g. a distinct
  commit message, or skip the commit on failure and let the admin alert
  be the record instead).
- **Verification:** YAML lint / `yamllint` if available; otherwise
  careful manual review only — no automated test is possible in this
  sandbox.

### M7 — Data file cleanup (no code)
- **Issues:** #71 (relabel/clean stale story_installment entries), #75
  (decide on data/story.json), #77 (remove package-lock.json), #74's data
  half (needs a live API call — likely defer)
- **Files:** data/memory.json, data/story.json, package-lock.json
- **Prerequisites:** #36's code fix (already done this session) must
  stay as-is — this milestone only touches data, not the `source`-field
  logic itself.
- **Completion criteria:** #71: the two `story_installment`-tagged
  entries in `data/memory.json` either get a `source` field or are
  removed, so they stop counting toward stage under the *old*
  backward-compat default. #75: `data/story.json` either deleted or left
  with an explanatory comment (JSON has no comments — consider a sibling
  `data/story.json.README` or just delete it, since nothing reads it).
  #77: `rm package-lock.json`.
- **Verification:** re-run `topic_selection`'s existing behavior for
  "Present simple tense"/"Daily routine words" before/after the
  `data/memory.json` edit to confirm the stage calculation changes as
  expected.

### M8 — Engagement/analytics feature additions
- **Issues:** #98 (weekly spot-check sample), #99 (few-shot examples),
  #100 (reactions tracking)
- **Files:** weekly_strategy.py, audience_profile.py or prompts.py,
  engagement_harvest.py
- **Prerequisites:** these are three independent, moderate-sized
  additions (not bugs in the strict sense) — consider splitting into
  three separate sessions if time is limited, in the order listed (#100
  is the most contained: one new field read from Telethon's `Message`
  object and stored).
- **Completion criteria:** #98: weekly_strategy's admin report includes
  a real sample of recent post text, not just aggregate numbers. #99:
  the generation prompt is fed actual text from a top-performing post,
  not just a format-level score. #100: `engagement_harvest.py` reads and
  stores `message.reactions`, and `analytics.py`'s reward-score
  computation optionally factors it in.
- **Verification:** each is independently testable — #100 especially,
  since it's a pure data-plumbing change with no generation-quality
  judgment involved.

### M9 — Design-document gaps (scoping needed first, not a coding milestone)
- **Issues:** #90 (dedicated quota tracking, optional), #96 (bot referral
  loops), #97 (preview-before-publish), #101 (reader_installment
  standalone-content tension)
- **Files:** none yet — this is a discussion, not a patch
- **Prerequisites:** a decision from the project owner on scope. #96 is a
  genuinely large feature (per-user DM logic, invite-link tracking) that
  doesn't fit a "surgical fix" session. #97 conflicts with the project's
  entire automated architecture — fixing it for real means adding a
  human-approval gate, which is a design change, not a bug fix. #101 has
  no clean code fix (the tension is between two design goals, not a
  defect).
- **Completion criteria:** N/A until scoped.
- **Verification:** N/A until scoped.

---

## Suggested order

M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9, but M1-M7 have no
cross-dependencies (only M8 loosely benefits from M2 being done first,
since better audience data makes #99's few-shot examples more useful).
A future session can reorder freely except: don't start M9 as code —
it needs a scoping conversation first.
