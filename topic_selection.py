"""Topic pool selection with spaced-repetition recycling (Audit #17, #18)."""

import datetime

import clock

from config import TOPICS_PATH, REVIEW_INTERVALS_DAYS, MAINTENANCE_INTERVAL_DAYS
from memory import load_json
from prompts import FORMATS

# Meta-label, not a teachable idiom — excluded from illustrated_pun (Audit #7).
_EXCLUDED_TOPICS = {"Common everyday idioms"}


def migrate_covered_topics(memory):
    """Upgrade legacy covered_topics: [str] → covered_topic_history: [{topic, format, date}]."""
    if "covered_topic_history" in memory:
        return memory
    history = []
    for topic_name in memory.get("covered_topics", []):
        history.append({"topic": topic_name, "format": "unknown", "date": ""})
    memory["covered_topic_history"] = history
    memory.pop("covered_topics", None)
    return memory


def _topic_history(memory):
    migrate_covered_topics(memory)
    return memory.setdefault("covered_topic_history", [])


def _last_coverage(memory, topic_name):
    entries = [e for e in _topic_history(memory) if e.get("topic") == topic_name]
    return entries[-1] if entries else None


def _all_topics():
    return [t for t in load_json(TOPICS_PATH, []) if t["topic"] not in _EXCLUDED_TOPICS]


def remaining_topic_count(memory):
    """Topics never taught yet."""
    history_topics = {e["topic"] for e in _topic_history(memory)}
    return len([t for t in _all_topics() if t["topic"] not in history_topics])


def recyclable_topic_count(memory, format_name):
    """Topics already taught (in any format) that are ELIGIBLE for
    `format_name` specifically — i.e. what get_next_topic could still
    recycle for this format once its own fresh pool runs out.

    Bug fix (#35): this used to take no format_name at all and just count
    every previously-taught topic, regardless of whether it was actually
    eligible for anything in particular — silently ignoring the "for a
    different format" half of its own docstring's promise. Not currently
    called anywhere in this codebase (verified), so this had zero runtime
    effect yet, but a function whose implementation doesn't match its own
    documented contract is a bug waiting for its first real caller to
    trust the docstring and get a wrong answer.
    """
    history_topics = {e["topic"] for e in _topic_history(memory)}
    return len([
        t for t in _all_topics()
        if t["topic"] in history_topics and _eligible(t, format_name)
    ])


def record_topic_coverage(memory, topic_name, format_name, date_str, source="fresh"):
    """`source` is one of "fresh" (never-taught-before topic, the normal
    case), "recycle" (get_next_topic's pool-exhaustion fallback — reused
    ahead of its spaced-repetition schedule because nothing untaught was
    left), or "review" (get_due_review_topic's scheduled spaced-repetition
    review). See get_due_review_topic's stage calculation for why this
    distinction matters (bug #36)."""
    _topic_history(memory).append(
        {"topic": topic_name, "format": format_name, "date": date_str, "source": source}
    )


def _eligible(topic, format_name):
    """The declared format↔content contract (content-pipeline-architecture.md
    §5) — replaces the single hardcoded `if format_name == "illustrated_pun"`
    special case that used to live in main.py::_select_topic. Every check
    here reads from the format's own entry in prompts.FORMATS or the topic's
    own fields; nothing about a specific format name is hardcoded here, so
    adding a new format is "add one dict entry", never "add another branch".

    Two independent, additive checks:

    1. `category_filter` on the format (e.g. illustrated_pun -> "Idioms",
       spot_mistake -> ["Common mistakes", "Persian transfer errors"]).
       Absent/falsy on a format means "any category" — every pre-existing
       format that never had a category restriction keeps behaving exactly
       as before.
    2. `required_tags` on the format (e.g. idiom_proverb_bridge ->
       ["has_fa_equivalent"]) — a hard content requirement checked against
       the topic's own `tags` list, and it fails CLOSED: a topic with no
       tags at all (every entry that predates the tags/eligible_formats
       schema, and anything topic_generation.py self-refills later, since
       it never sets tags either) simply doesn't qualify until a human
       tags it. That's deliberate — the whole point of restricting this
       at the schema level instead of trusting the prompt to self-censor
       (§4) is that an unverified cultural pairing is exactly the kind of
       "confidently wrong" claim a native reader catches immediately, so
       the safe default is "not eligible yet", not "eligible unless
       someone remembered to exclude it".

    A topic's own optional `eligible_formats` (§3) is a further, opt-in
    RESTRICTION layered on top of both checks above — for the case where a
    topic matches a format's category/tags but should still be excluded
    from it for some other reason. Absent, it imposes no extra restriction,
    which is what makes this fully additive: every topic without the field
    is exactly as eligible as it was before this function existed."""
    fmt = FORMATS.get(format_name, {})

    category_filter = fmt.get("category_filter")
    if category_filter:
        allowed_categories = (
            {category_filter} if isinstance(category_filter, str) else set(category_filter)
        )
        if topic["category"] not in allowed_categories:
            return False

    required_tags = fmt.get("required_tags")
    if required_tags:
        topic_tags = set(topic.get("tags", []))
        if not set(required_tags).issubset(topic_tags):
            return False

    allowed_formats = topic.get("eligible_formats")
    if allowed_formats is not None and format_name not in allowed_formats:
        return False

    return True


def get_next_topic(memory, format_name, theme_category=None):
    """Pick the next topic. Never returns (None, None) while at least one
    topic in topics.json is eligible for this format (see _eligible) —
    when the fresh pool is exhausted, recycle with a different format
    (Audit #17).

    Returns (topic_dict, source), where source is "fresh" (never taught
    before, in any format) or "recycle" (pool exhausted for this format;
    reusing the least-recently-taught eligible topic ahead of its normal
    spaced-repetition schedule). Callers should pass `source` straight
    through to record_topic_coverage — see that function and
    get_due_review_topic's stage calculation for why the distinction
    matters (bug #36: a forced recycle used to be recorded identically to
    a genuine scheduled review, silently inflating a topic's apparent
    review progress).

    format_name alone now fully determines which topics are even
    candidates (via _eligible / prompts.FORMATS) — callers no longer pass
    a category_filter, so main.py::_select_topic calls this the exact same
    way for illustrated_pun as for every other format.

    theme_category (campaigns.py) is a SOFT preference only, applied within
    the fresh pool: it never overrides a format's declared eligibility and
    never blocks publishing by making a topic unavailable — if nothing
    fresh matches the week's theme, we fall back to the normal
    fresh/recycle order exactly as before campaigns existed."""
    candidates = [t for t in _all_topics() if _eligible(t, format_name)]
    if not candidates:
        return None, None

    history_topics = {e["topic"] for e in _topic_history(memory)}

    # Fresh topics first, preferring this week's theme category if one is set.
    fresh = [t for t in candidates if t["topic"] not in history_topics]
    if fresh:
        if theme_category:
            themed = [t for t in fresh if t["category"] == theme_category]
            if themed:
                return themed[0], "fresh"
        return fresh[0], "fresh"

    # Recycle: prefer topics last taught in a different format, oldest first.
    def recycle_key(topic):
        last = _last_coverage(memory, topic["topic"])
        same_format = last and last.get("format") == format_name
        date_str = last.get("date") or "0000-00-00"
        try:
            age = datetime.date.fromisoformat(date_str)
        except ValueError:
            age = datetime.date.min
        return (same_format, age)

    return sorted(candidates, key=recycle_key)[0], "recycle"


def _topic_by_name(name):
    for t in _all_topics():
        if t["topic"] == name:
            return t
    return None


def pending_vocab_spotlight_callback(memory, format_name):
    """The most recently vocab_spotlight-taught topic that hasn't been
    covered again by anything since, if it's eligible for `format_name` —
    or None.

    Bug fix (#40): vocab_spotlight's own guidance (prompts.py) says this
    post "is supposed to prepare the ground for a future scene or idiom"
    — but nothing anywhere actually connected a spotlighted word to a
    later micro_scene/idiom_proverb_bridge topic pick; every format's
    topic selection was completely independent, making that line
    aspirational text with no mechanism behind it. This gives it one:
    a soft, best-effort preference, checked by main.py::_select_topic
    before it falls through to the normal fresh/recycle pool — never a
    hard requirement (returns None freely), and never a way to violate a
    format's declared eligibility (checked via _eligible same as
    everything else).
    """
    if format_name not in ("micro_scene", "idiom_proverb_bridge"):
        return None
    spotlighted = [e for e in _topic_history(memory) if e.get("format") == "vocab_spotlight"]
    if not spotlighted:
        return None
    spotlighted.sort(key=lambda e: e.get("date") or "0000-00-00")
    for entry in reversed(spotlighted):  # most recently spotlighted first
        name = entry["topic"]
        last = _last_coverage(memory, name)
        # Still "pending a callback" only if nothing (this format or any
        # other) has covered it again since it was spotlighted.
        if last is entry:
            topic = _topic_by_name(name)
            if topic is not None and _eligible(topic, format_name):
                return topic
    return None


def all_pillars():
    """Every distinct topics.json `category` currently in use. Derived from
    the data, not a hardcoded list, so a brand-new pillar (e.g. adding
    "Phrasal verbs" to topics.json) shows up in pillar-coverage reporting
    automatically — the same principle topic_generation.py already uses
    for its own category list."""
    return sorted({t["category"] for t in _all_topics()})


def pillar_last_covered(memory, pillar):
    """Most recent date any topic in this pillar (topics.json `category`)
    was covered — the per-pillar twin of _last_coverage's per-topic
    tracking (content-pipeline-architecture.md §6). Returns None if this
    pillar has never been covered at all, including a pillar that didn't
    exist yet when older history entries were recorded."""
    dates = []
    for entry in _topic_history(memory):
        if not entry.get("date"):
            continue
        topic = _topic_by_name(entry["topic"])
        if topic is not None and topic.get("category") == pillar:
            dates.append(entry["date"])
    return max(dates) if dates else None


def days_since_pillar_covered(memory, pillar, today=None):
    """None if the pillar has never been covered (caller should treat that
    as "worse than any number of days", not skip it)."""
    today = today or clock.today()
    last = pillar_last_covered(memory, pillar)
    if last is None:
        return None
    try:
        last_date = datetime.date.fromisoformat(last)
    except ValueError:
        return None
    return (today - last_date).days


def get_due_review_topic(memory, today=None):
    """Pick the most-overdue topic for spaced review, per config.REVIEW_INTERVALS_DAYS
    (Audit: "review only after the fresh pool is exhausted" doesn't match the
    spacing-effect literature — this is the scheduled-review complement to
    get_next_topic's fresh/recycle logic, used only on main.py's reserved
    review slots).

    Returns (topic_dict, stage, last_format) — stage is how many times this
    topic has already been reviewed (0 = taught once, never reviewed), so
    the caller can pick a format different from last_format the way
    get_next_topic's recycle_key already does. Returns (None, None, None)
    if nothing is due yet.

    Once a topic clears every stage in REVIEW_INTERVALS_DAYS ("graduated"),
    it doesn't stop being scheduled — it drops into a standing
    MAINTENANCE_INTERVAL_DAYS refresh cycle (Bahrick's "permastore" finding:
    infrequent long-interval refreshers keep foreign-vocabulary retention
    alive for decades). This repeats indefinitely, not just once.

    Honest limit, not a bug: if fresh content keeps being introduced forever
    at a constant rate, the pool of graduated topics needing periodic
    maintenance grows without bound, while daily review capacity doesn't —
    so eventually maintenance demand exceeds capacity no matter how this is
    tuned. Picking the single most-overdue candidate each call (below) is
    the deliberate, standard way real spaced-repetition schedulers degrade
    under an oversubscribed backlog: old content gets refreshed less often
    than the nominal interval, but never silently dropped, and nothing
    breaks — it's a graceful, expected outcome, not an error state."""
    today = today or clock.today()

    by_topic = {}
    for entry in _topic_history(memory):
        by_topic.setdefault(entry["topic"], []).append(entry)

    due_candidates = []
    for name, entries in by_topic.items():
        entries = sorted(entries, key=lambda e: e.get("date") or "0000-00-00")

        # Bug fix (#36): stage used to be len(entries) - 1, counting EVERY
        # history entry the same way — including ones added by
        # get_next_topic's pool-exhaustion recycling fallback, which is
        # completely ungated by review timing (it can fire immediately,
        # just because the fresh pool ran dry). That silently inflated a
        # topic's apparent spaced-repetition progress: a topic recycled a
        # couple of times could look "graduated" into the 90-day
        # maintenance bucket after very little genuine review. Only
        # "fresh" (the one real first exposure) and "review" (an actual
        # scheduled spaced-repetition event) entries advance stage now;
        # a "recycle" entry still updates the LAST-COVERED DATE used for
        # the next due-date below (the reader did see it again, so it's
        # reasonable to count from that), it just doesn't fast-track
        # graduation to a longer interval the way a real review does.
        # Entries from before this fix (or from schema migration) have no
        # "source" field at all — treated as "review" (the old, more
        # conservative behavior: counted toward stage), not "recycle", so
        # this fix can never retroactively RAISE anyone's due-ness.
        real_exposures = [e for e in entries if e.get("source", "review") != "recycle"]
        stage = max(len(real_exposures) - 1, 0)
        interval = (
            REVIEW_INTERVALS_DAYS[stage] if stage < len(REVIEW_INTERVALS_DAYS)
            else MAINTENANCE_INTERVAL_DAYS  # graduated -> standing low-frequency refresh
        )

        try:
            last_date = datetime.date.fromisoformat(entries[-1].get("date", ""))
        except ValueError:
            continue  # no reliable date to schedule from — skip rather than guess

        due_date = last_date + datetime.timedelta(days=interval)
        if due_date > today:
            continue  # not due yet

        topic = _topic_by_name(name)
        if topic is None:
            continue  # topic since removed from topics.json

        overdue_by = (today - due_date).days
        due_candidates.append((overdue_by, topic, stage, entries[-1].get("format")))

    if not due_candidates:
        return None, None, None

    due_candidates.sort(key=lambda c: -c[0])  # most overdue first
    _, topic, stage, last_format = due_candidates[0]
    return topic, stage, last_format
