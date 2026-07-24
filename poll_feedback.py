"""Turns real Telegram poll/quiz results into automatic feedback.json
entries and updates successful_patterns in memory (Audit Problem B)."""

import datetime
import re

from config import FEEDBACK_PATH, MEMORY_PATH, PENDING_POLLS_PATH
from memory import load_json, save_json
from telegram_bot import stop_poll

MAX_SUCCESSFUL_PATTERNS = 20
_HIGH_CORRECT_RATE = 70
_LOW_CORRECT_RATE = 40


def save_pending_poll(message_id, question, is_quiz=False, correct_index=None):
    pending = load_json(PENDING_POLLS_PATH, [])
    pending.append({
        "message_id": message_id,
        "question": question,
        "is_quiz": is_quiz,
        "correct_index": correct_index,
        "sent_date": str(datetime.date.today()),
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

    save_json(FEEDBACK_PATH, feedback_list)
    save_json(PENDING_POLLS_PATH, still_pending)
    save_json(MEMORY_PATH, memory)
