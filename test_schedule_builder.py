"""Offline tests for schedule_builder.py's score-driven weighting — this is
now pure Python over analytics.recent_score_summary()'s output, with zero
LLM calls anywhere in the path, so unlike test_image_pipeline.py this needs
no mocking of any model/HTTP boundary at all.

Run: python3 test_schedule_builder.py
"""
import sys

import schedule_builder as sb

FAILED = []
PASSED = []


def check(label, condition, detail=""):
    if condition:
        PASSED.append(label)
        print(f"  OK   {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL {label}  {detail}")


ALL_FORMATS = [
    "micro_scene", "illustrated_pun", "spot_mistake", "vocab_spotlight",
    "idiom_proverb_bridge", "textbook_vs_real", "quiz", "vote_poll",
    "reader_installment", "news_relevel", "progress_recap",
]

print("\n=== format_weight: no data yet -> neutral DEFAULT_WEIGHT ===")
check("no score -> DEFAULT_WEIGHT", sb.format_weight("micro_scene", {}) == sb.DEFAULT_WEIGHT)
check("score of exactly NEUTRAL_SCORE -> DEFAULT_WEIGHT",
      sb.format_weight("micro_scene", {"micro_scene": sb.NEUTRAL_SCORE}) == sb.DEFAULT_WEIGHT)

print("\n=== format_weight: monotonic in score ===")
low = sb.format_weight("micro_scene", {"micro_scene": 0.1})
mid = sb.format_weight("micro_scene", {"micro_scene": 0.5})
high = sb.format_weight("micro_scene", {"micro_scene": 0.95})
check("higher score -> higher weight (low < mid < high)", low < mid < high, (low, mid, high))
check("a perfect score (1.0) yields double DEFAULT_WEIGHT",
      sb.format_weight("micro_scene", {"micro_scene": 1.0}) == sb.DEFAULT_WEIGHT * 2)

print("\n=== format_weight: never zero or negative, even at score 0.0 ===")
worst = sb.format_weight("micro_scene", {"micro_scene": 0.0})
check("score 0.0 -> weight is still positive (>= MIN_WEIGHT)", worst >= sb.MIN_WEIGHT, worst)

print("\n=== build_slot_counts: totals always sum to 7 (one per weekday) ===")
counts_no_data = sb.build_slot_counts(ALL_FORMATS, {})
check("no score data at all -> still allocates all 7 slots",
      sum(counts_no_data.values()) == len(sb.WEEKDAYS), counts_no_data)

counts_mixed = sb.build_slot_counts(ALL_FORMATS, {
    "quiz": 0.95, "vote_poll": 0.9, "micro_scene": 0.2, "vocab_spotlight": 0.5,
})
check("mixed score data -> still allocates all 7 slots",
      sum(counts_mixed.values()) == len(sb.WEEKDAYS), counts_mixed)

print("\n=== build_slot_counts: fixed/floor guarantees hold regardless of score ===")
counts_bad_quiz = sb.build_slot_counts(ALL_FORMATS, {"quiz": 0.0, "vocab_spotlight": 0.0})
check("quiz never drops below its floor even at score 0.0",
      counts_bad_quiz.get("quiz", 0) >= sb.FLOOR_FORMATS["quiz"], counts_bad_quiz)
check("vocab_spotlight never drops below its floor even at score 0.0",
      counts_bad_quiz.get("vocab_spotlight", 0) >= sb.FLOOR_FORMATS["vocab_spotlight"], counts_bad_quiz)
check("illustrated_pun is always exactly 1 regardless of any score",
      sb.build_slot_counts(ALL_FORMATS, {"illustrated_pun": 1.0}).get("illustrated_pun") == 1)

print("\n=== build_slot_counts: no format exceeds MAX_SLOTS_PER_WEEK ===")
counts_lopsided = sb.build_slot_counts(ALL_FORMATS, {"micro_scene": 1.0})
check("even a dominant score never exceeds MAX_SLOTS_PER_WEEK",
      counts_lopsided["micro_scene"] <= sb.MAX_SLOTS_PER_WEEK, counts_lopsided)

print("\n=== build_slot_counts: progress_recap is always excluded ===")
check("progress_recap never appears in slot counts",
      "progress_recap" not in counts_mixed, counts_mixed)

print("\n=== build_slot_counts: higher-scored format gets at least as many slots ===")
counts_favor_quiz = sb.build_slot_counts(ALL_FORMATS, {"quiz": 1.0, "micro_scene": 0.0})
check("a format scored 1.0 gets more slots than one scored 0.0",
      counts_favor_quiz["quiz"] >= counts_favor_quiz["micro_scene"], counts_favor_quiz)

print("\n=== build_slot_counts: deterministic (same input -> same output) ===")
a = sb.build_slot_counts(ALL_FORMATS, {"quiz": 0.8, "micro_scene": 0.3})
b = sb.build_slot_counts(ALL_FORMATS, {"quiz": 0.8, "micro_scene": 0.3})
check("identical score_summary produces identical slot counts every time", a == b, (a, b))

print("\n=== assign_days / diff_schedule: unaffected by the weighting change ===")
current = {day: "micro_scene" for day in sb.WEEKDAYS}
new_schedule = sb.assign_days(counts_mixed, current)
check("assign_days covers every weekday", set(new_schedule.keys()) == set(sb.WEEKDAYS), new_schedule)
changes = sb.diff_schedule(current, new_schedule)
check("diff_schedule only reports days that actually changed",
      all(current[day] != new for day, _old, new in changes), changes)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
sys.exit(0)
