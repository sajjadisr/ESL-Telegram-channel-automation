"""Backfills verified Persian-proverb equivalents for every Idioms-category
topic in data/topics.json that doesn't have one yet, using search-grounded
lookups (research.py) instead of a one-time hand-picked list.

Why this exists: CONTENT_PIPELINE_CHANGES.md's original 5 pairings were
picked by hand in one session and flagged "please sanity-check with a
native speaker before this goes live" — that check never happened, and a
fixed list of 5 doesn't grow with the channel. This script is the
replacement: it can run against any number of Idioms topics, is re-runnable
safely, and every pairing it publishes carries a source citation instead of
resting on one session's confidence.

Safe to re-run any time — skips topics that are already tagged
has_fa_equivalent OR fa_equivalent_needs_review, so re-running only ever
processes genuinely new topics (e.g. ones topic_generation.py's self-refill
added since the last run). That's what makes this "keep finding ideas",
not "hardcode once and stop": the pool grows automatically as topics.json
grows.

High-confidence, sourced results get written back with has_fa_equivalent +
fa_equivalent + fa_equivalent_source, making them eligible for
idiom_proverb_bridge (topic_selection._eligible's required_tags check).
Below-threshold results are tagged fa_equivalent_needs_review instead —
visible to a human in the data file, never silently eligible.

Usage: python scripts/enrich_idiom_proverbs.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TOPICS_PATH
from memory import load_json, save_json
import research


def main():
    topics = load_json(TOPICS_PATH, [])
    idioms = [t for t in topics if t.get("category") == "Idioms"]
    candidates = [
        t for t in idioms
        if "has_fa_equivalent" not in t.get("tags", [])
        and "fa_equivalent_needs_review" not in t.get("tags", [])
    ]

    if not candidates:
        print("Nothing to do — every Idioms topic already has a verified equivalent, "
              "a queued-for-review candidate, or has already been checked.")
        return

    print(f"Checking {len(candidates)} idiom(s) with no equivalent on file yet...")
    newly_published = queued_for_review = found_nothing = call_failed = 0

    for topic in candidates:
        idiom = topic["topic"]
        result = research.find_persian_proverb_equivalent(idiom)

        if result is None:
            call_failed += 1
            print(f"  [skip]   {idiom!r} — lookup call failed, will retry next run.")
            continue

        confidence = (result.get("confidence") or "none").lower()
        fa_equivalent = (result.get("fa_equivalent") or "").strip()

        if not fa_equivalent or confidence == "none":
            found_nothing += 1
            print(f"  [none]   {idiom!r} — no convincing equivalent found.")
            continue

        tags = topic.setdefault("tags", [])
        if research.meets_publish_threshold(result):
            topic["fa_equivalent"] = fa_equivalent
            topic["fa_equivalent_source"] = result.get("source", "")
            if "has_fa_equivalent" not in tags:
                tags.append("has_fa_equivalent")
            newly_published += 1
            print(f"  [ok]     {idiom!r} -> {fa_equivalent!r}  (source: {result.get('source', '')})")
        else:
            topic["fa_equivalent_candidate"] = fa_equivalent
            topic["fa_equivalent_source"] = result.get("source", "")
            if "fa_equivalent_needs_review" not in tags:
                tags.append("fa_equivalent_needs_review")
            queued_for_review += 1
            print(f"  [review] {idiom!r} -> {fa_equivalent!r}  (confidence: {confidence} — "
                  f"needs a human glance before it can go live)")

    save_json(TOPICS_PATH, topics)
    print(
        f"\nDone. Published: {newly_published}. Queued for review: {queued_for_review}. "
        f"No equivalent found: {found_nothing}. Call failed (will retry next run): {call_failed}."
    )


if __name__ == "__main__":
    main()
