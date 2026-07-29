"""Offline tests for analytics.py's generalized engagement scoring —
_engagement_value / rolling_avg_engagement / score_entry /
apply_harvested_engagement. Pure Python over plain dicts/lists; the only
file I/O (load_json/save_json against ANALYTICS_PATH) is redirected to a
temp file so this never touches the real data/analytics.json.

Run: python3 test_analytics_engagement.py
"""
import os
import sys
import tempfile
from unittest import mock

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-telegram-token")
os.environ.setdefault("TELEGRAM_CHANNEL_ID", "@testchannel")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")

import analytics  # noqa: E402
from memory import save_json, load_json  # noqa: E402

FAILED = []
PASSED = []


def check(label, condition, detail=""):
    if condition:
        PASSED.append(label)
        print(f"  OK   {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL {label}  {detail}")


print("\n=== _engagement_value: picks the right unit per entry shape ===")
check("poll entry -> vote_count",
      analytics._engagement_value({"vote_count": 12, "views": None}) == 12)
check("harvested text/image entry -> views + forwards*multiplier",
      analytics._engagement_value({"vote_count": None, "views": 100, "forwards": 5})
      == 100 + 5 * analytics.FORWARD_WEIGHT_MULTIPLIER)
check("forwards missing/None on a views entry -> treated as 0, not a crash",
      analytics._engagement_value({"vote_count": None, "views": 50, "forwards": None}) == 50)
check("neither vote_count nor views -> None (nothing measurable yet)",
      analytics._engagement_value({"vote_count": None, "views": None}) is None)

print("\n=== rolling_avg_engagement: per-format, ignores other formats ===")
history = [
    {"format": "micro_scene", "vote_count": None, "views": 100, "forwards": 0},
    {"format": "micro_scene", "vote_count": None, "views": 200, "forwards": 0},
    {"format": "quiz", "vote_count": 40, "views": None},  # different format, must not mix in
]
avg = analytics.rolling_avg_engagement(history, "micro_scene")
check("average only includes same-format entries", avg == 150, avg)
check("a format with no history at all -> None",
      analytics.rolling_avg_engagement(history, "vote_poll") is None)

print("\n=== score_entry: neutral (0.5) with no baseline, capped at 2x avg ===")
no_baseline_entry = {"format": "vocab_spotlight", "vote_count": None, "views": 80, "forwards": 0}
check("no rolling average yet -> neutral 0.5",
      analytics.score_entry(no_baseline_entry, []) == 0.5)

capped_history = [{"format": "micro_scene", "vote_count": None, "views": 100, "forwards": 0}] * 3
huge_entry = {"format": "micro_scene", "vote_count": None, "views": 10000, "forwards": 0}
score = analytics.score_entry(huge_entry, capped_history)
check("a huge outlier is capped at 2x avg -> engagement component maxes at 1.0",
      score == 1.0, score)

print("\n=== score_entry: correct_rate folds in learning half for quizzes ===")
quiz_history = [{"format": "quiz", "vote_count": 20, "views": None}] * 3
quiz_entry = {"format": "quiz", "vote_count": 20, "views": None, "correct_rate": 100}
quiz_score = analytics.score_entry(quiz_entry, quiz_history)
check("engagement at baseline (0.5) + perfect correct_rate (1.0) -> weighted average",
      abs(quiz_score - (analytics.REWARD_WEIGHT_ENGAGEMENT * 0.5 + analytics.REWARD_WEIGHT_LEARNING * 1.0)) < 1e-6,
      quiz_score)

print("\n=== apply_harvested_engagement: writes views/forwards + reward_score ===")
with tempfile.TemporaryDirectory() as tmpdir:
    path = os.path.join(tmpdir, "analytics.json")
    with mock.patch("analytics.ANALYTICS_PATH", path):
        seed = [
            {"date": "2026-07-01", "format": "micro_scene", "vote_count": None,
             "views": 100, "forwards": 2, "message_id": 1, "reward_score": 0.5,
             "correct_rate": None},
            {"date": "2026-07-20", "format": "micro_scene", "vote_count": None,
             "views": None, "forwards": None, "message_id": 2, "reward_score": None,
             "correct_rate": None},
        ]
        save_json(path, seed)

        updated = analytics.apply_harvested_engagement({2: (500, 10)})
        check("exactly one entry updated", updated == 1, updated)

        result = load_json(path, [])
        touched = next(e for e in result if e["message_id"] == 2)
        check("views/forwards were written onto the right entry",
              touched["views"] == 500 and touched["forwards"] == 10, touched)
        check("reward_score is no longer None once harvested",
              touched["reward_score"] is not None, touched["reward_score"])
        check("a high view count relative to the (single-entry) baseline scores well",
              touched["reward_score"] > 0.5, touched["reward_score"])

        # Calling again with no new data must be a safe no-op.
        updated_again = analytics.apply_harvested_engagement({2: (500, 10)})
        check("re-applying to an already-harvested entry updates nothing (idempotent)",
              updated_again == 0, updated_again)

        # Empty updates dict must short-circuit without touching the file.
        updated_empty = analytics.apply_harvested_engagement({})
        check("empty updates dict -> 0, no-op", updated_empty == 0)

print("\n=== entries_pending_harvest: respects the message_id/views/date filters ===")
with tempfile.TemporaryDirectory() as tmpdir:
    path = os.path.join(tmpdir, "analytics.json")
    with mock.patch("analytics.ANALYTICS_PATH", path):
        import datetime
        today = datetime.date.today()
        old_date = today - datetime.timedelta(days=999)
        seed = [
            {"date": str(today), "message_id": 10, "views": None},   # pending
            {"date": str(today), "message_id": 11, "views": 50},     # already harvested
            {"date": str(today), "message_id": None, "views": None},  # no message_id (manual/no send)
            {"date": str(old_date), "message_id": 12, "views": None},  # too old, outside window
        ]
        save_json(path, seed)
        pending = analytics.entries_pending_harvest(window_days=14)
        check("only the in-window, message_id-having, not-yet-harvested entry is pending",
              pending == [10], pending)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
sys.exit(0)
