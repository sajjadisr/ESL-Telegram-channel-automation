"""Self-refill for data/topics.json (Weakness: a hand-curated topic pool is
a hard ceiling on how long this channel can run without someone editing a
file). When the pool runs low, ask the model for more instead of only
alerting the admin — see main.py's maybe_alert_low_topic_supply.

Deliberately conservative: this only ever *appends* validated entries. It
never edits or removes anything already in topics.json, and a failure here
(bad API call, unparseable response, everything getting deduped away) is
swallowed and logged, never raised — a missed top-up just means the
existing low-topic admin alert still fires next time, which is the
pre-existing safety net this is layered on top of, not a replacement for.
"""

import difflib
import re

from ai import generate_json
from config import TOPICS_PATH
from memory import load_json, save_json
from prompts import build_topic_generation_prompt

# Above this similarity ratio (difflib SequenceMatcher on lowercased,
# whitespace-normalized strings), a proposed topic is treated as a
# near-duplicate of something that already exists and is dropped — this is
# on top of the model's own instruction to avoid duplicates, not instead of
# it, since a model can and will occasionally ignore that instruction.
_DUPLICATE_SIMILARITY_THRESHOLD = 0.82

VALID_LEVELS = {"A1", "A2"}

_LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


def _normalize(text):
    text = " ".join(text.lower().split())
    return _LEADING_ARTICLE.sub("", text)


def _is_duplicate(candidate_name, existing_names_normalized):
    normalized = _normalize(candidate_name)
    for existing in existing_names_normalized:
        if not existing:
            continue
        # Containment catches near-misses edit-distance ratio underweights
        # on short phrases (e.g. "the colors" vs "colors" scores only
        # ~0.75 on SequenceMatcher, below the threshold, despite being the
        # same topic once the article's stripped above).
        if normalized in existing or existing in normalized:
            return True
        if difflib.SequenceMatcher(None, normalized, existing).ratio() >= _DUPLICATE_SIMILARITY_THRESHOLD:
            return True
    return False


def generate_and_append_topics(count):
    """Best-effort: ask the model for `count` new topics, keep only the
    ones that pass validation and aren't near-duplicates of anything
    already in topics.json, append them, and save. Returns the list of
    topics actually added (may be shorter than `count`, or empty)."""
    existing = load_json(TOPICS_PATH, [])
    existing_names = [t["topic"] for t in existing]
    categories = sorted({t.get("category", "General") for t in existing}) or ["Vocabulary"]

    prompt = build_topic_generation_prompt(existing_names, count, categories)
    try:
        proposed = generate_json(prompt, fallback=[], strict=False)
    except Exception as exc:
        print("topic_generation: model call failed, skipping this top-up:", exc)
        return []

    if not isinstance(proposed, list):
        print("topic_generation: model didn't return a JSON array, skipping.")
        return []

    existing_normalized = [_normalize(n) for n in existing_names]
    added = []
    for item in proposed:
        if not isinstance(item, dict):
            continue
        name = (item.get("topic") or "").strip()
        level = item.get("level")
        category = item.get("category")
        if not name or level not in VALID_LEVELS or category not in categories:
            continue
        if _is_duplicate(name, existing_normalized + [_normalize(a["topic"]) for a in added]):
            continue
        added.append({"topic": name, "level": level, "category": category})

    if added:
        save_json(TOPICS_PATH, existing + added)
        print(f"topic_generation: added {len(added)}/{len(proposed)} proposed topics.")
    else:
        print("topic_generation: nothing passed validation this round.")

    return added
