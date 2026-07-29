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

from config import EMBEDDINGS_JSONL_PATH, DEDUP_SIMILARITY_THRESHOLD
from ai import embed_text


def _load_records():
    """[(post_id, title, vector), ...] — empty list if the file doesn't
    exist yet or a line is malformed (skipped, not fatal: one bad line
    must never take down every future dedup check)."""
    if not os.path.exists(EMBEDDINGS_JSONL_PATH):
        return []
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
    return records


def _append_record(post_id, title, vector):
    with open(EMBEDDINGS_JSONL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(
            {"post_id": post_id, "title": title, "embedding": [round(v, 6) for v in vector]},
            ensure_ascii=False,
        ) + "\n")


def cosine_similarity(a, b):
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def most_similar(vector, records):
    """records: the [(post_id, title, vector), ...] shape _load_records
    returns. Returns (title, score) for the closest match, or (None, 0.0)
    if records is empty."""
    best_title, best_score = None, 0.0
    for _post_id, title, other_vector in records:
        score = cosine_similarity(vector, other_vector)
        if score > best_score:
            best_title, best_score = title, score
    return best_title, best_score


def check_semantic_duplicate(draft_text, threshold=DEDUP_SIMILARITY_THRESHOLD):
    """Returns (colliding_title, score) if `draft_text` is a near-duplicate
    of something already stored, or (None, score_of_closest_match)
    otherwise (score is 0.0 if there's nothing stored yet, or if the
    embedding call itself failed — both are "nothing to compare against",
    handled identically by the caller)."""
    vector = embed_text(draft_text)
    if vector is None:
        return None, 0.0
    records = _load_records()
    if not records:
        return None, 0.0
    title, score = most_similar(vector, records)
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
    by scripts/backfill_post_embeddings.py."""
    existing_ids = {post_id for post_id, _title, _vector in _load_records()} if not force else set()
    count = 0
    for post_id, title, content in posts:
        if post_id in existing_ids:
            continue
        record_post_embedding(post_id, title, content)
        count += 1
    return count
