"""Turns real Telegram poll/quiz results into automatic feedback.json
entries and updates successful_patterns in memory (Audit Problem B).

Also the harvest point for analytics.py (Weakness 4 — engagement telemetry
+ reward score) and audience_profile.py (Weakness 1 — the aggregate
audience profile): both need the actual vote tally, which only exists
once stop_poll() closes the poll, a day or more after it was sent — so
theme_category/experiment_id/variant_label are captured at SEND time (see
main.py) and carried on the pending_polls.json entry through to here,
rather than re-derived later from the (free-form, Persian) question text."""

import datetime

import clock
import re

from config import FEEDBACK_PATH, MEMORY_PATH, PENDING_POLLS_PATH
from memory import load_json, save_json
from telegram_bot import stop_poll
from channels import broadcast_extra_channels, format_poll_results_for_extra_channels
import analytics
import audience_profile

MAX_SUCCESSFUL_PATTERNS = 20
_HIGH_CORRECT_RATE = 70
_LOW_CORRECT_RATE = 40
MAX_PENDING_POLL_RETRIES = 5
MAX_PENDING_POLL_DAYS = 7

# Bug fix (this session): a poll used to get stop_poll()'d the moment the
# *next* daily_post.yml trigger fired — harvest_pending_polls() runs
# unconditionally at the very top of main(), and with 3 primary + 3
# catch-up cron slots ~5-6 hours apart, that meant every poll closed for
# good just a few hours after posting, regardless of how few subscribers
# had a realistic chance to see and vote on it yet. This module's own
# docstring above says results are only meaningful "a day or more after
# it was sent" — but nothing ever actually enforced that; the retry/
# age-out constants above only govern what happens once a close ATTEMPT
# has already failed, not when the first attempt is allowed to happen.
# MIN_POLL_OPEN_DAYS gates that: a poll is left alone (still_pending,
# no stop_poll call at all) until it's no longer the same calendar day
# it was sent on.
MIN_POLL_OPEN_DAYS = 1


def save_pending_poll(message_id, question, is_quiz=False, correct_index=None,
                       theme_category=None, topic_category=None,
                       experiment_id=None, variant_label=None,
                       extra_channel_results=None):
    pending = load_json(PENDING_POLLS_PATH, [])
    pending.append({
        "message_id": message_id,
        "question": question,
        "is_quiz": is_quiz,
        "correct_index": correct_index,
        "sent_date": clock.today_str(),
        "first_attempt_date": clock.today_str(),
        "retry_count": 0,
        "theme_category": theme_category,
        "topic_category": topic_category,
        "experiment_id": experiment_id,
        "variant_label": variant_label,
        "extra_channel_delivery": analytics._summarize_delivery(extra_channel_results),
    })
    save_json(PENDING_POLLS_PATH, pending)


def _append_successful_pattern(memory, pattern):
    patterns = memory.setdefault("successful_patterns", [])
    if pattern in patterns:
        patterns.remove(pattern)
    patterns.insert(0, pattern)
    memory["successful_patterns"] = patterns[:MAX_SUCCESSFUL_PATTERNS]


def _update_patterns_from_quiz(memory, question, correct_rate):
    if correct_rate >= _HIGH_CORRECT_RATE:
        _append_successful_pattern(memory, f"quiz_high: {question[:80]}")
    elif correct_rate <= _LOW_CORRECT_RATE:
        _append_successful_pattern(memory, f"quiz_needs_review: {question[:80]}")


def harvest_pending_polls():
    pending = load_json(PENDING_POLLS_PATH, [])
    if not pending:
        return

    feedback_list = load_json(FEEDBACK_PATH, [])
    memory = load_json(MEMORY_PATH, {})
    still_pending = []

    for entry in pending:
        entry.setdefault("retry_count", 0)
        entry.setdefault("first_attempt_date", entry.get("sent_date") or clock.today_str())

        # Don't even attempt to close a poll until it's been open at
        # least MIN_POLL_OPEN_DAYS — see the constant's comment above.
        # No retry_count bump here: this isn't a failed attempt, it's
        # deliberately not attempting yet.
        try:
            sent_date = datetime.date.fromisoformat(entry.get("sent_date") or "")
            days_open = (clock.today() - sent_date).days
        except ValueError:
            days_open = MIN_POLL_OPEN_DAYS  # no/malformed sent_date on an old entry — don't block it forever, just proceed as usual
        if days_open < MIN_POLL_OPEN_DAYS:
            still_pending.append(entry)
            continue

        result = stop_poll(entry["message_id"])
        if not result or not result.get("ok"):
            entry["retry_count"] = entry.get("retry_count", 0) + 1
            try:
                first_date = datetime.date.fromisoformat(entry["first_attempt_date"])
            except ValueError:
                first_date = clock.today()
            age_days = max(0, (clock.today() - first_date).days)
            if entry["retry_count"] >= MAX_PENDING_POLL_RETRIES or age_days >= MAX_PENDING_POLL_DAYS:
                send_admin_message(
                    f"⚠️ نظرسنجی/کوییز با message_id={entry['message_id']} بعد از "
                    f"{entry['retry_count']} تلاش یا {age_days} روز هنوز بسته نشده؛ از فهرست منتظرها خارج شد. "
                    "لطفاً اگر هنوز باز است، دستی بررسی کنید."
                )
                print(
                    "harvest_pending_polls: giving up on pending poll",
                    entry["message_id"],
                    f"after {entry['retry_count']} retries and {age_days} days",
                )
                continue
            still_pending.append(entry)
            continue

        poll = result.get("result", {})
        options = poll.get("options", [])
        total_votes = sum(opt.get("voter_count", 0) for opt in options)
        tally = [
            {"text": opt.get("text", ""), "votes": opt.get("voter_count", 0)}
            for opt in options
        ]

        note_parts = [f"نظرسنجی «{entry.get('question', '')}» با {total_votes} رأی بسته شد."]
        correct_index = entry.get("correct_index")
        correct_rate = None
        if entry.get("is_quiz") and isinstance(correct_index, int) and total_votes:
            if 0 <= correct_index < len(tally):
                correct_rate = tally[correct_index]["votes"] / total_votes * 100
                note_parts.append(f"درصد پاسخ درست: {correct_rate:.0f}٪.")
                _update_patterns_from_quiz(memory, entry.get("question", ""), correct_rate)
        note_parts.append(
            "توزیع آرا: " + "، ".join(f"{t['text']}={t['votes']}" for t in tally)
        )

        # Audit: vote_poll's Eitaa/Bale fallback (channels.py) points
        # readers to "go vote on Telegram" since there's no right answer to
        # reveal at send time — but nothing ever followed up with them
        # once the poll actually closed. Quiz doesn't need this: its
        # correct answer is already revealed inline in the original
        # fallback message, so this is vote_poll-only, and only fires if
        # the original fallback was actually sent somewhere (extra_
        # channel_delivery is only set when broadcast_extra_channels ran).
        if not entry.get("is_quiz") and total_votes and entry.get("extra_channel_delivery"):
            results_text = format_poll_results_for_extra_channels(
                entry.get("question", ""), tally, total_votes, is_quiz=False,
            )
            broadcast_extra_channels(results_text)

        feedback_list.append({
            "post_title": entry.get("question", ""),
            "notes": " ".join(note_parts),
            "date": clock.today_str(),
            "source": "auto_poll_harvest",
            **({"correct_rate": correct_rate} if correct_rate is not None else {}),
        })
        print("Harvested poll feedback:", " ".join(note_parts))

        # Weakness 4 (engagement telemetry + reward score) — score this
        # poll/quiz now that we finally have a real vote tally.
        analytics.record_poll_metrics(
            question=entry.get("question", ""),
            format_name="quiz" if entry.get("is_quiz") else "vote_poll",
            is_quiz=bool(entry.get("is_quiz")),
            total_votes=total_votes,
            correct_rate=correct_rate,
            experiment_id=entry.get("experiment_id"),
            variant_label=entry.get("variant_label"),
            extra_channel_delivery=entry.get("extra_channel_delivery"),
            message_id=entry.get("message_id"),
        )

        # Weakness 1 (audience profile) — only quizzes carry a graded,
        # topic-attributable signal (vote_poll has no right answer).
        if correct_rate is not None:
            audience_profile.update_from_quiz_result(entry.get("topic_category") or entry.get("theme_category"), correct_rate)

    save_json(FEEDBACK_PATH, feedback_list)
    save_json(PENDING_POLLS_PATH, still_pending)
    save_json(MEMORY_PATH, memory)
