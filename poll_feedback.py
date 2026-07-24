"""Turns real Telegram poll/quiz results into automatic feedback.json
entries — no human typing required.

Why this works with a cron-only bot: anonymous polls (is_anonymous=True,
what this project sends) never generate a poll_answer webhook update, and
even if they did, a bot that only runs once a day via GitHub Actions isn't
listening to receive it. But Telegram's stopPoll endpoint returns the final
per-option vote tally for ANY poll — anonymous or not — the moment you close
it. So instead of listening in real time, we just close yesterday's poll at
the start of today's run and read the tally out of the response.

Flow:
  1. handle_poll_format() in main.py calls save_pending_poll() right after a
     poll/quiz is successfully sent.
  2. main() calls harvest_pending_polls() first thing on the NEXT run, before
     anything else — closes it, computes the vote/correct-answer rate, and
     appends a real entry to feedback.json.
"""

import datetime

from config import FEEDBACK_PATH, PENDING_POLLS_PATH
from memory import load_json, save_json
from telegram_bot import stop_poll


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


def harvest_pending_polls():
    """Stop and read the vote tally for any poll(s) saved from a prior run,
    append a feedback.json entry for each, then clear the pending list.
    Safe to call every run — a no-op if nothing is pending. Polls Telegram
    fails to stop (network hiccup, already closed, etc.) are kept pending
    and retried on a future run rather than silently dropped."""
    pending = load_json(PENDING_POLLS_PATH, [])
    if not pending:
        return

    feedback_list = load_json(FEEDBACK_PATH, [])
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
        if entry.get("is_quiz") and isinstance(correct_index, int) and total_votes:
            if 0 <= correct_index < len(tally):
                correct_rate = tally[correct_index]["votes"] / total_votes * 100
                note_parts.append(f"درصد پاسخ درست: {correct_rate:.0f}٪.")
        note_parts.append(
            "توزیع آرا: " + "، ".join(f"{t['text']}={t['votes']}" for t in tally)
        )

        feedback_list.append({
            "post_title": entry.get("question", ""),
            "notes": " ".join(note_parts),
            "date": str(datetime.date.today()),
            "source": "auto_poll_harvest",
        })
        print("Harvested poll feedback:", " ".join(note_parts))

    save_json(FEEDBACK_PATH, feedback_list)
    save_json(PENDING_POLLS_PATH, still_pending)
