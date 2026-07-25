"""Topic pool selection with spaced-repetition recycling (Audit #17, #18)."""

import datetime

from config import TOPICS_PATH
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
