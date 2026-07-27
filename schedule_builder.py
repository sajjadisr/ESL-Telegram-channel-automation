"""Turns strategy.json's `best_formats` (real engagement signal, harvested
from quiz correct-rates and poll votes by poll_feedback.py) into an actual
weekly rotation — the missing link that made `best_formats` dead data before
this file existed: weekly_strategy.py computed it, nothing ever read it.

Design constraints baked in on purpose:
  - illustrated_pun is capped at exactly 1/week regardless of engagement —
    it's the one format that breaks full automation (manual image posting),
    so scheduling more of them raises the admin's weekly workload independent
    of how well they perform.
  - vocab_spotlight and quiz each get a floor of 1/week, for two different
    structural reasons a plain engagement score can't see:
      * vocab_spotlight seeds vocabulary for later posts — a role that
        doesn't show up as a poll/vote signal at all, since it produces no
        poll.
      * quiz is the *only* format that produces the correct-rate feedback
        that analytics.compute_reward_score's REWARD_WEIGHT_LEARNING half
        depends on (see config.py). Without a floor, a data-driven
        reallocation can starve its own data supply: if best_formats ever
        happens to exclude "quiz" (e.g. because strategy.json was built
        from too little feedback to include it yet — see
        MIN_FEEDBACK_FOR_SCHEDULE_UPDATE in config.py), the D'Hondt method
        below would zero out its slots entirely, which means no more quiz
        feedback ever arrives to correct that in a future week either.
    Both can still win *extra* slots if engagement flags them as
    best_formats too; neither can drop to 0.
  - story_installment used to have the same kind of floor (serial
    continuity was its structural role), but the format itself has been
    retired: it was locked into a slot every week by this floor regardless
    of how it performed, and it never once appeared in strategy.json's
    best_formats — the freed slot(s) now go through the same weighted
    allocation as everything else, so they land on whatever the real
    engagement data currently favors instead of on a fixed assumption.
  - No single format may exceed MAX_SLOTS_PER_WEEK, so one good week of
    quiz feedback can't turn the whole channel into daily quizzes.

Allocation method: this is a small integer-allocation problem (~7 slots
across ~6-7 formats), and the "obvious" approach — largest-remainder /
Hamilton apportionment — turns out to produce almost no visible weighting
at this scale (a well-known property of that method with few categories).
We use the D'Hondt / Jefferson method instead (the one most seat-allocation
systems use), which reliably shows proportional weighting even with a
handful of categories.
"""

WEEKDAYS = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# progress_recap is scheduled by post-count (RECAP_EVERY_N_POSTS), not by
# weekday — it must never appear in format_schedule.json.
EXCLUDED_FROM_ROTATION = {"progress_recap"}

FIXED_SLOTS = {"illustrated_pun": 1}
FLOOR_FORMATS = {"vocab_spotlight": 1, "quiz": 1}
MAX_SLOTS_PER_WEEK = 3
BEST_FORMAT_WEIGHT = 2
DEFAULT_WEIGHT = 1


def build_slot_counts(all_format_keys, best_formats):
    """Return {format_name: slots_per_week} summing to len(WEEKDAYS)."""
    eligible = [f for f in all_format_keys if f not in EXCLUDED_FROM_ROTATION]
    weighted_pool = [f for f in eligible if f not in FIXED_SLOTS]

    counts = {f: FLOOR_FORMATS.get(f, 0) for f in weighted_pool}
    weights = {f: (BEST_FORMAT_WEIGHT if f in best_formats else DEFAULT_WEIGHT) for f in weighted_pool}

    slots_to_allocate = len(WEEKDAYS) - sum(FIXED_SLOTS.values()) - sum(counts.values())
    if slots_to_allocate < 0:
        raise ValueError("FIXED_SLOTS + FLOOR_FORMATS exceed the number of days in a week")

    # D'Hondt / Jefferson method: repeatedly give the next slot to whoever
    # currently has the highest weight / (seats_so_far + 1) quotient. Ties
    # (common at this scale) break on weighted_pool's stable order, i.e.
    # FORMATS dict order — deterministic, not random, so a schedule rebuild
    # is reproducible from the same strategy.json.
    for _ in range(slots_to_allocate):
        candidates = [f for f in weighted_pool if counts[f] < MAX_SLOTS_PER_WEEK]
        if not candidates:
            break  # everyone's at the cap; nowhere left to put the slot
        best = max(candidates, key=lambda f: weights[f] / (counts[f] + 1))
        counts[best] += 1

    counts.update(FIXED_SLOTS)
    return counts


def assign_days(slot_counts, current_schedule):
    """Map slot_counts onto WEEKDAYS, keeping each day's current format
    where possible so subscribers' sense of "quiz day" / "idiom day"
    doesn't reshuffle more than the actual count changes require."""
    remaining = dict(slot_counts)
    new_schedule = {}
    unassigned_days = []

    for day in WEEKDAYS:
        fmt = current_schedule.get(day)
        if fmt in remaining and remaining[fmt] > 0:
            new_schedule[day] = fmt
            remaining[fmt] -= 1
        else:
            unassigned_days.append(day)

    pool = []
    for fmt, count in remaining.items():
        pool.extend([fmt] * count)

    for day, fmt in zip(unassigned_days, pool):
        new_schedule[day] = fmt

    return new_schedule


def build_engagement_schedule(all_format_keys, best_formats, current_schedule):
    slot_counts = build_slot_counts(all_format_keys, best_formats)
    return assign_days(slot_counts, current_schedule)


def diff_schedule(old_schedule, new_schedule):
    """Human-readable-ready (day, old, new) tuples for whatever changed."""
    changes = []
    for day in WEEKDAYS:
        old, new = old_schedule.get(day), new_schedule.get(day)
        if old != new:
            changes.append((day, old, new))
    return changes
