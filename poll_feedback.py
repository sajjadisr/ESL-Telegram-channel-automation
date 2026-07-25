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
import re

from config import FEEDBACK_PATH, MEMORY_PATH, PENDING_POLLS_PATH
from memory import load_json, save_json
from telegram_bot import stop_poll
import analytics
import audience_profile

MAX_SUCCESSFUL_PATTERNS = 20
_HIGH_CORRECT_RATE = 70
_LOW_CORRECT_RATE = 40


def save_pending_poll(message_id, question, is_quiz=False, correct_index=None,
                       theme_category=None, experiment_id=None, variant_label=None,
                       extra_channel_results=None):
    pending = load_json(PENDING_POLLS_PATH, [])
    pending.append({
        "message_id": message_id,
        "question": question,
        "is_quiz": is_quiz,
        "correct_index": correct_index,
        "sent_date": str(datetime.date.today()),
        "theme_category": theme_category,
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
        result = stop_poll(entry["message_id"])
        if not result or not result.get("ok"):
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

        feedback_list.append({
            "post_title": entry.get("question", ""),
            "notes": " ".join(note_parts),
            "date": str(datetime.date.today()),
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
        )

        # Weakness 1 (audience profile) — only quizzes carry a graded,
        # topic-attributable signal (vote_poll has no right answer).
        if correct_rate is not None:
            audience_profile.update_from_quiz_result(entry.get("theme_category"), correct_rate)

    save_json(FEEDBACK_PATH, feedback_list)
    save_json(PENDING_POLLS_PATH, still_pending)
    save_json(MEMORY_PATH, memory)
