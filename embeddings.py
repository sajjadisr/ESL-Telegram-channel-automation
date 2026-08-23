"""Semantic post-deduplication (closes the gap flagged in database.py's
context_posts_for_generation docstring: a LIKE match on title/keywords
structurally cannot see two posts with unrelated names that happen to reuse
the same example sentence or scenario — that's exactly what let the same
"I drink coffee every morning" example ship twice under different topics).

Design:
  - Every published text/image post gets embedded once (ai.embed_text) and
    appended to data/post_embeddings.jsonl — one JSON line per post, same
    "durable record, git-tracked, one-line diff forever" pattern
    database.py already uses for posts.jsonl (AUDIT_FIXES.md #9), not a
    binary or a growing single JSON blob.
  - Before a draft is accepted, main.generate_reviewed_text embeds it and
    compares by cosine similarity against every stored vector. Above
    DEDUP_SIMILARITY_THRESHOLD (config.py) it's treated as a semantic
    duplicate and fed back into the retry loop with the specific prior
    post's title, the same way a failed review/stray-character check
    already triggers a regenerate — never a silent block, always a chance
    to actually fix it.
  - Every failure mode here (embedding call fails, cache file is empty/
    missing/corrupt) degrades to "no semantic duplicate found" rather than
    raising — dedup is a quality improvement layered on top of the
    existing keyword-based check, not a new way for a run to fail. See
    ai.embed_text's docstring for the same fail-open contract on the API
    side.
"""

import json
import math
import os
import tempfile

from config import EMBEDDINGS_JSONL_PATH, DEDUP_SIMILARITY_THRESHOLD
from ai import embed_text

_cache = {"mtime": None, "records": None}


def _load_records():
    """[(post_id, title, vector), ...] — empty list if the file doesn't
    exist yet or a line is malformed (skipped, not fatal: one bad line
    must never take down every future dedup check).

    Bug fix (#26): this used to re-read and re-parse the entire file from
    scratch on every single call — up to 1+MAX_REVIEW_ATTEMPTS times per
    post, since main.generate_reviewed_text calls check_semantic_duplicate
    once per draft attempt. Now cached in memory, keyed on the file's own
    mtime: unchanged since the last read (the common case — nothing
    appends to this file mid-generation-loop, only after a post is
    actually published) returns the cached list instead of hitting disk
    again; a real change (a new record appended) is still picked up
    immediately, since the mtime won't match.
    """
    if not os.path.exists(EMBEDDINGS_JSONL_PATH):
        _cache["mtime"], _cache["records"] = None, []
        return []
    mtime = os.path.getmtime(EMBEDDINGS_JSONL_PATH)
    if _cache["records"] is not None and _cache["mtime"] == mtime:
        return _cache["records"]
    records = []
    with open(EMBEDDINGS_JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                records.append((rec["post_id"], rec["title"], rec["embedding"]))
            except (json.JSONDecodeError, KeyError) as exc:
                print(f"embeddings: skipping malformed line in {EMBEDDINGS_JSONL_PATH}: {exc}")
    _cache["mtime"], _cache["records"] = mtime, records
    return records


def _append_record(post_id, title, vector):
    with open(EMBEDDINGS_JSONL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(
            {"post_id": post_id, "title": title, "embedding": [round(v, 6) for v in vector]},
            ensure_ascii=False,
        ) + "\n")
    _cache["records"] = None  # invalidate — cheaper than recomputing mtime defensively here


def _rewrite_records(records):
    """Atomically rewrite the whole store from `records`
    ([(post_id, title, vector), ...]) — used by backfill_from_posts'
    force=True path (#27) to actually replace stale entries instead of
    piling up duplicates. Same temp-file-then-os.replace pattern as
    memory.save_json, for the same reason: never leave a truncated file
    behind if the process dies mid-write."""
    directory = os.path.dirname(EMBEDDINGS_JSONL_PATH) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".jsonl")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for post_id, title, vector in records:
                f.write(json.dumps(
                    {"post_id": post_id, "title": title, "embedding": [round(v, 6) for v in vector]},
                    ensure_ascii=False,
                ) + "\n")
        os.replace(tmp_path, EMBEDDINGS_JSONL_PATH)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    _cache["records"] = None


_dimension_mismatch_warned = False


def cosine_similarity(a, b):
    """Returns 0.0 (not an exception) on a dimension mismatch — deliberate:
    a single malformed stored vector must never take down every future
    dedup check. Bug fix (#25): this silent 0.0 used to be the only
    signal, which means a change to EMBEDDING_DIMENSIONALITY would make
    every historical embedding mismatch the new dimensionality and
    silently stop matching anything, with dedup quietly disabled against
    the whole prior history and nothing ever saying so. Now warns once
    per process the first time a mismatch is actually seen, instead of
    never at all — still 0.0 either way, so behavior is unchanged; only
    the visibility is new."""
    global _dimension_mismatch_warned
    if len(a) != len(b):
        if not _dimension_mismatch_warned:
            print(f"embeddings: comparing vectors of different lengths ({len(a)} vs {len(b)}) — "
                  f"treating as unrelated (score 0.0). If this keeps happening, "
                  f"EMBEDDING_DIMENSIONALITY may have changed since older embeddings were stored; "
                  f"consider running scripts/backfill_post_embeddings.py --force to re-embed "
                  f"everything at the current dimensionality.")
            _dimension_mismatch_warned = True
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def most_similar(vector, records, exclude_post_ids=None):
    """records: the [(post_id, title, vector), ...] shape _load_records
    returns. Returns (title, score) for the closest match, or (None, 0.0)
    if records is empty (or every record was excluded).

    exclude_post_ids: optional set of post ids to skip entirely — see
    check_semantic_duplicate's docstring (Bug fix #92) for why a caller
    would ever want to exclude specific prior posts from its own dedup
    check."""
    exclude_post_ids = exclude_post_ids or ()
    best_title, best_score = None, 0.0
    for post_id, title, other_vector in records:
        if post_id in exclude_post_ids:
            continue
        score = cosine_similarity(vector, other_vector)
        if score > best_score:
            best_title, best_score = title, score
    return best_title, best_score


def check_semantic_duplicate(draft_text, threshold=DEDUP_SIMILARITY_THRESHOLD, exclude_post_ids=None):
    """Returns (colliding_title, score) if `draft_text` is a near-duplicate
    of something already stored, or (None, score_of_closest_match)
    otherwise (score is 0.0 if there's nothing stored yet, or if the
    embedding call itself failed — both are "nothing to compare against",
    handled identically by the caller).

    exclude_post_ids: optional set/iterable of post ids to leave out of the
    comparison entirely.

    Bug fix (#92): reader_installment (and any other serialized,
    fixed-content format) needs this — consecutive installments of the
    same story are SUPPOSED to be similar to each other (same characters,
    setting, narrative voice; see reader.py's module docstring), so
    without an exclusion, a story's own earlier chunk was the single
    likeliest thing for a new chunk to collide with, and unlike a genuine
    cross-topic repeat, that collision can never be fixed by rewording —
    the source chunk text is fixed ahead of time. That turned into a
    permanent per-story stuck state: every future run resumes the same
    unpublished chunk (see reader._reconciled_position), fails semantic
    dedup against that same story's already-published chunk again, and
    skips the post — confirmed directly in production logs, the same
    story rejected as "too similar to itself" across multiple separate
    days. Callers that don't pass exclude_post_ids get the exact previous
    behavior (nothing excluded).

    Bug fix (found while fixing ai.embed_text's #10): this used to rely
    entirely on embed_text swallowing every possible failure internally
    and always returning a vector or None. Once embed_text stopped
    silently swallowing genuinely unexpected errors (so real bugs don't
    masquerade as ordinary API failures — see ai.py's #9/#10), this
    function needed its own safety net to keep its own documented
    contract ("dedup... not a new way for a run to fail" — see this
    module's docstring): an unexpected exception here now degrades to
    "nothing to compare against" exactly like embed_text returning None
    already did, instead of crashing the run over a dedup check.
    """
    try:
        vector = embed_text(draft_text)
    except Exception as exc:  # noqa: BLE001 — dedup must never block a publish
        print(f"embeddings: check_semantic_duplicate failed unexpectedly, skipping dedup this time: {exc}")
        return None, 0.0
    if vector is None:
        return None, 0.0
    records = _load_records()
    if not records:
        return None, 0.0
    title, score = most_similar(vector, records, exclude_post_ids=exclude_post_ids)
    if score >= threshold:
        return title, score
    return None, score


def record_post_embedding(post_id, title, content):
    """Call once, right after a post is actually published — embeds the
    final (post-review) content and appends it to the store, so future
    dedup checks can see it. Never raises: a failure here means one post
    doesn't get a stored vector, which degrades a future dedup check back
    to "didn't catch this one," not something worth crashing an
    already-successful publish over."""
    try:
        vector = embed_text(content)
        if vector is None:
            print(f"embeddings: could not embed post {post_id!r} ({title!r}) — not stored.")
            return
        _append_record(post_id, title, vector)
    except Exception as exc:  # noqa: BLE001 — must never break a run that already published
        print(f"embeddings: record_post_embedding failed for post {post_id!r}: {exc}")


def backfill_from_posts(posts, force=False):
    """One-time / catch-up helper: embed a batch of already-published posts
    that predate this feature (or were missed for any reason). `posts` is
    an iterable of (post_id, title, content). Skips ids already present
    unless force=True. Returns the number of posts newly embedded — used
    by scripts/backfill_post_embeddings.py.

    Bug fix (#27): force=True used to re-embed and blindly APPEND another
    row for a post_id that already had one — since _append_record is
    append-only, both the stale and fresh embedding stayed in the file
    forever, doubling (or worse, after repeated force runs) the cost of
    every future similarity scan for a post_id, for no benefit (the fresh
    entry is strictly the one worth keeping). force=True now removes any
    existing entries for the ids being re-embedded first — a real upsert —
    instead of accumulating duplicates.
    """
    posts = list(posts)
    existing_records = _load_records()
    existing_ids = {post_id for post_id, _title, _vector in existing_records}

    if force:
        refresh_ids = {post_id for post_id, _title, _content in posts}
        stale_removed = refresh_ids & existing_ids
        if stale_removed:
            _rewrite_records([r for r in existing_records if r[0] not in stale_removed])
            existing_ids -= stale_removed

    count = 0
    for post_id, title, content in posts:
        if not force and post_id in existing_ids:
            continue
        record_post_embedding(post_id, title, content)
        count += 1
    return count
