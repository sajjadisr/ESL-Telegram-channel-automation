"""Graded-reader integration (reader_installment format).

Design deliberately avoids the exact failure mode that broke the old
story_installment format — see story-removal-and-fixes.diff. That format's
one root cause: progress lived only in data/story.json, a side file that
fell out of sync with what was actually posted whenever a git push failed
mid-run, and "which episode is this" was recovered by regex-parsing
AI-generated prose instead of a real counter. Two lost/duplicate-episode
incidents later, it was removed.

The fix, mirrored here as two separate concerns:

- Story TEXT lives in data/reader_library.json: an array of stories, each
  already segmented into a fixed, known number of chunks before posting
  ever starts. The ending is decided on day one — a series can't "run out
  of what happens next" mid-stream, because there's nothing left to
  improvise.
- Story PROGRESS lives in posts.db (the story_id/chunk_index columns added
  in database.py) — the same durable, already-committed-every-run store
  everything else in this pipeline uses, queried with a real
  SELECT MAX(chunk_index), not text-parsing. memory.json keeps a
  fast-path cache (READING_KEY) purely as a read optimization, but every
  call reconciles it against posts.db before trusting it — so a failed
  git push (the exact incident the old diff's comment documents) can
  never leave the cache lying about what's already been sent.
"""

from config import READER_LIBRARY_PATH, LOW_STORY_WARNING_THRESHOLD
from memory import load_json
from database import get_last_published_chunk

# Fast-path cache only — {"story_id": str}. Never trusted on its own; see
# _reconciled_position.
#
# Bug fix (#56): this used to also store "next_chunk_index", but nothing
# ever read that field back — _reconciled_position always recomputes the
# next index from posts.db (get_last_published_chunk), never from this
# cache. Removed rather than left as dead, misleadingly-named data.
READING_KEY = "reader_progress"


def _library():
    return load_json(READER_LIBRARY_PATH, [])


def _story_by_id(library, story_id):
    for story in library:
        if story["id"] == story_id:
            return story
    return None


def _started_ids(library):
    return {
        story["id"] for story in library
        if get_last_published_chunk(story["id"]) is not None
    }


def _reconciled_position(memory, library):
    """Returns (story, next_chunk_index), using posts.db as ground truth
    for EVERY story's progress — not just whichever one memory.json's
    cache happens to name.

    Bug fix (#57): the fallback used to only ever find a story that has
    NEVER been started (via _started_ids' exclusion). If the cache's
    story_id was ever lost, reset, or simply wrong while a DIFFERENT
    story was genuinely left partway through, that story became
    permanently orphaned: not resumable (it wasn't the cached one) and
    not eligible as "fresh" either (it already has published chunks) —
    directly contradicting this module's own stated design goal that
    posts.db, not the cache, is the recoverable ground truth. The cache
    was only ever consulted as a same-story shortcut; it was never
    actually used to recover a DIFFERENT story's true progress when the
    two disagreed. Now falls back to scanning every story's real
    progress via get_last_published_chunk (not just checking whether
    it's in the "started" set), and prefers resuming a genuinely partial
    story over starting a fresh one.
    """
    cache = memory.get(READING_KEY, {})
    cached_story_id = cache.get("story_id")

    if cached_story_id:
        story = _story_by_id(library, cached_story_id)
        if story is not None:
            last_chunk = get_last_published_chunk(cached_story_id)
            next_index = 0 if last_chunk is None else last_chunk + 1
            if next_index < len(story["chunks"]):
                return story, next_index
            # Story finished (or the cache pointed past its own length) —
            # fall through to look for something else to read.

    # The cache is missing, wrong, or points at a finished story — recover
    # directly from posts.db instead of assuming nothing else is in
    # progress.
    never_started = []
    for story in library:
        last_chunk = get_last_published_chunk(story["id"])
        if last_chunk is None:
            never_started.append(story)
            continue
        next_index = last_chunk + 1
        if next_index < len(story["chunks"]):
            # A genuinely partial story, found independently of the cache
            # — resume it rather than leaving it stuck.
            return story, next_index

    if never_started:
        return never_started[0], 0

    return None, None


def get_next_installment(memory):
    """Returns (story, chunk_index, chunk_text, is_final_chunk), or
    (None, None, None, None) if the library is empty or every story in it
    is already finished. Updates memory[READING_KEY] as a side effect —
    caller is responsible for eventually saving memory.json (same
    contract every other memory-mutating helper here already follows)."""
    library = _library()
    if not library:
        return None, None, None, None

    story, next_index = _reconciled_position(memory, library)
    if story is None:
        return None, None, None, None

    chunk_text = story["chunks"][next_index]
    is_final = next_index == len(story["chunks"]) - 1

    memory[READING_KEY] = {"story_id": story["id"]}

    return story, next_index, chunk_text, is_final


def remaining_untouched_stories(memory):
    """How many stories in the library haven't been started at all yet —
    used for the low-supply admin alert, mirroring topic_selection's
    remaining_topic_count."""
    library = _library()
    started = _started_ids(library)
    return len([s for s in library if s["id"] not in started])


def low_supply_warning_needed(memory):
    return remaining_untouched_stories(memory) <= LOW_STORY_WARNING_THRESHOLD
