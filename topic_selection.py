"""Topic pool selection with spaced-repetition recycling (Audit #17, #18)."""

import datetime

from config import TOPICS_PATH, REVIEW_INTERVALS_DAYS, MAINTENANCE_INTERVAL_DAYS
from memory import load_json

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


def recyclable_topic_count(memory):
    """Topics taught before but eligible for a different format."""
    count = 0
    for topic in _all_topics():
        last = _last_coverage(memory, topic["topic"])
        if last is None:
            continue
        count += 1
    return count


def record_topic_coverage(memory, topic_name, format_name, date_str):
    _topic_history(memory).append(
        {"topic": topic_name, "format": format_name, "date": date_str}
    )


def get_next_topic(memory, format_name, category_filter=None, theme_category=None):
    """Pick the next topic. Never returns None while topics.json is non-empty —
    when the fresh pool is exhausted, recycle with a different format (Audit #17).

    theme_category (campaigns.py) is a SOFT preference only, applied within
    the fresh pool: it never overrides category_filter (illustrated_pun's
    hard requirement) and never blocks publishing by making a topic
    unavailable — if nothing fresh matches the week's theme, we fall back
    to the normal fresh/recycle order exactly as before campaigns existed."""
    candidates = _all_topics()
    if category_filter:
        candidates = [t for t in candidates if t["category"] == category_filter]
    if not candidates:
        return None

    history_topics = {e["topic"] for e in _topic_history(memory)}

    # Fresh topics first, preferring this week's theme category if one is set.
    fresh = [t for t in candidates if t["topic"] not in history_topics]
    if fresh:
        if theme_category:
            themed = [t for t in fresh if t["category"] == theme_category]
            if themed:
                return themed[0]
        return fresh[0]

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

    return sorted(candidates, key=recycle_key)[0]


def _topic_by_name(name):
    for t in _all_topics():
        if t["topic"] == name:
            return t
    return None


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
    today = today or datetime.date.today()

    by_topic = {}
    for entry in _topic_history(memory):
        by_topic.setdefault(entry["topic"], []).append(entry)

    due_candidates = []
    for name, entries in by_topic.items():
        entries = sorted(entries, key=lambda e: e.get("date") or "0000-00-00")
        stage = len(entries) - 1
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
