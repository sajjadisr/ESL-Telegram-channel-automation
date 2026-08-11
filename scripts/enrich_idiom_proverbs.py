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

Usage: python scripts/enrich_idiom_proverbs.py [--recheck-queued]

Safe to re-run any time — by default, skips topics that already carry a
SOURCED has_fa_equivalent (a real fa_equivalent_source, meaning THIS script
already verified them) or are already queued for review, so a normal run
only ever processes genuinely new topics (e.g. ones topic_generation.py's
self-refill added since the last run).

Bug fix (#54): this used to skip anything tagged has_fa_equivalent at all —
which included the original 5 hand-picked, explicitly-UNVERIFIED pairings
from CONTENT_PIPELINE_CHANGES.md (they were shipped already carrying that
tag). Since this script's whole stated purpose is to REPLACE that
unverified guesswork, but its own filter guaranteed those exact 5 entries
could never be reached, the thing this script was built to fix stayed
unfixed no matter how many times it ran. Now distinguishes "verified by
this script" (has_fa_equivalent AND a real fa_equivalent_source) from
"tagged has_fa_equivalent but never actually sourced" — the latter is
treated as a candidate again, so the original 5 finally get the same
grounded check every other idiom gets.

Bug fix (#55): fa_equivalent_needs_review used to be a permanent
exclusion — once queued, a topic could never be re-attempted even if a
later search might turn up a better source. Pass --recheck-queued to
also re-attempt those (not on by default, so a normal run doesn't
re-spend quota on topics unlikely to have changed since the last check).

High-confidence, sourced results get written back with has_fa_equivalent +
fa_equivalent + fa_equivalent_source, making them eligible for
idiom_proverb_bridge (topic_selection._eligible's required_tags check).
Below-threshold results are tagged fa_equivalent_needs_review instead —
visible to a human in the data file, never silently eligible.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TOPICS_PATH
from memory import load_json, save_json
import research


def _is_candidate(topic, recheck_queued):
    tags = topic.get("tags", [])
    if "has_fa_equivalent" in tags:
        # Bug fix (#54): only skip if it's actually SOURCED (verified by
        # this script, not just hand-asserted) — see module docstring.
        return not (topic.get("fa_equivalent_source") or "").strip()
    if "fa_equivalent_needs_review" in tags:
        return recheck_queued  # bug fix (#55): opt-in re-attempt
    return True


def main():
    recheck_queued = "--recheck-queued" in sys.argv[1:]
    topics = load_json(TOPICS_PATH, [])
    idioms = [t for t in topics if t.get("category") == "Idioms"]
    candidates = [t for t in idioms if _is_candidate(t, recheck_queued)]

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
