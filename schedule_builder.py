"""Turns real engagement data (analytics.recent_score_summary — harvested
from quiz correct-rates, poll votes, and, once engagement_harvest.py is
configured, views/forwards for every other format too) into an actual
weekly rotation — the missing link that made this data dead before this
file existed: it used to be computed, nothing ever read it.

Weighting is now a direct, deterministic function of analytics.py's own
numbers (format_weight below) — no LLM call in between. It used to route
through weekly_strategy.py asking a model to re-read recent post titles
and feedback text and guess a binary best_formats list; that step added
nothing a formula over the number the system already computed couldn't do
better, and it silently discarded the actual reward_score value in favor
of a re-derived qualitative guess. See weekly_strategy.py's module
docstring for the other half of that split: the LLM call that's left
keeps doing the one job it's actually suited for (focus_more_on/
focus_less_on topic-level guidance), and no longer touches formats at all.

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
        reallocation can starve its own data supply: if quiz's score ever
        happens to be low relative to other formats, weighting alone
        (no floor) could push its slot count toward zero, which means no
        more quiz feedback ever arrives to correct that in a future week
        either.
    Both can still win *extra* slots if their score favors them too;
    neither can drop to 0.
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
handful of categories — and, unlike the classic seat-allocation use case,
nothing about it requires the input weights to be small integers; it works
identically over the continuous, real-valued weights format_weight below
produces.
"""

WEEKDAYS = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# progress_recap is scheduled by post-count (RECAP_EVERY_N_POSTS), not by
# weekday — it must never appear in format_schedule.json.
# Bug fix (#33 — the most severe bug found in the whole project): this used
# to contain only "progress_recap". reader_installment and news_relevel
# were both missing, and neither has a category_filter in prompts.FORMATS
# (so _eligible() would happily call any ordinary vocab/grammar topic
# "eligible" for either). Both formats fundamentally depend on content
# (a real story chunk, or a real news summary) that ONLY main.py's special
# extra-slot chain supplies via extra_note — the ordinary weekday (slot 1)
# path has no way to supply it. Verified end-to-end: simulating realistic
# scores (other formats underperforming, these two simply unscored, which
# is the normal state before engagement_harvest.py is even configured) made
# build_engagement_schedule assign both formats to regular weekdays. Once
# that happens, resolve_today_format() picks either up as slot 1's format,
# which routes through the ordinary _select_topic/get_next_topic path and
# hands back something like "Present simple tense" with generation
# guidance that says "this is an episode of a pre-written story, continue
# it below" / "here's a real news summary below" and no actual story or
# news content ever supplied — a broken, nonsensical post with nothing
# stopping it from going out live.
EXCLUDED_FROM_ROTATION = {"progress_recap", "reader_installment", "news_relevel"}

FIXED_SLOTS = {"illustrated_pun": 1}
FLOOR_FORMATS = {"vocab_spotlight": 1, "quiz": 1}
MAX_SLOTS_PER_WEEK = 3

# --- Continuous, score-derived weighting ------------------------------------
DEFAULT_WEIGHT = 1.0  # a format with no score yet (never scored, or not
# scored recently enough to survive analytics.ROLLING_WINDOW) is neutral —
# "no data" must never be penalized the same as "data says this is bad".
NEUTRAL_SCORE = 0.5  # a reward_score of 0.5 is what compute_reward_score/
# score_entry already produce when there's no rolling baseline yet, or when
# engagement exactly matches this format's own recent normal — i.e. the
# actual, already-defined "neither good nor bad" point on the [0, 1] scale
# those functions use, not a separate assumption invented here.
REWARD_SCALE = 2.0  # weight = DEFAULT_WEIGHT + REWARD_SCALE * (score - NEUTRAL_SCORE):
# a perfect score (1.0) yields weight 2.0 (double the neutral weight, the
# same ratio the old binary best_formats bonus used), a score of 0.0 yields
# a small positive floor rather than 0 or negative (see MIN_WEIGHT) — D'Hondt
# needs strictly positive weights, and a single bad week shouldn't be able
# to mathematically zero a format out on its own (FLOOR_FORMATS/FIXED_SLOTS
# are the deliberate, named way a format gets guaranteed slots regardless of
# score; an accidental zero-weight from the formula is not that).
MIN_WEIGHT = 0.2


def format_weight(format_name, score_summary):
    """This format's D'Hondt weight for this week, derived directly from
    analytics.recent_score_summary()'s output — no LLM guess involved.
    Formats analytics has no score for yet (score_summary.get returns
    None) get DEFAULT_WEIGHT, same as before any data exists for them."""
    score = score_summary.get(format_name)
    if score is None:
        return DEFAULT_WEIGHT
    return max(MIN_WEIGHT, DEFAULT_WEIGHT + REWARD_SCALE * (score - NEUTRAL_SCORE))


def build_slot_counts(all_format_keys, score_summary):
    """Return {format_name: slots_per_week} summing to len(WEEKDAYS).
    score_summary is analytics.recent_score_summary()'s output —
    {format_name: avg_reward_score_in_[0,1]} for whatever's been scored."""
    eligible = [f for f in all_format_keys if f not in EXCLUDED_FROM_ROTATION]
    weighted_pool = [f for f in eligible if f not in FIXED_SLOTS]

    counts = {f: FLOOR_FORMATS.get(f, 0) for f in weighted_pool}
    weights = {f: format_weight(f, score_summary) for f in weighted_pool}

    slots_to_allocate = len(WEEKDAYS) - sum(FIXED_SLOTS.values()) - sum(counts.values())
    if slots_to_allocate < 0:
        raise ValueError("FIXED_SLOTS + FLOOR_FORMATS exceed the number of days in a week")

    # D'Hondt / Jefferson method: repeatedly give the next slot to whoever
    # currently has the highest weight / (seats_so_far + 1) quotient. Ties
    # (common at this scale) break on weighted_pool's stable order, i.e.
    # FORMATS dict order — deterministic, not random, so a schedule rebuild
    # is reproducible from the same analytics.json.
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


def build_engagement_schedule(all_format_keys, score_summary, current_schedule):
    slot_counts = build_slot_counts(all_format_keys, score_summary)
    return assign_days(slot_counts, current_schedule)


def diff_schedule(old_schedule, new_schedule):
    """Human-readable-ready (day, old, new) tuples for whatever changed."""
    changes = []
    for day in WEEKDAYS:
        old, new = old_schedule.get(day), new_schedule.get(day)
        if old != new:
            changes.append((day, old, new))
    return changes
