"""Run once after deploying embeddings.py (semantic dedup) so it covers
every post already published, not just posts going forward. Safe to
re-run any time — skips posts that already have a stored vector (see
embeddings.backfill_from_posts).

Usage: python scripts/backfill_post_embeddings.py [--force]

--force re-embeds and replaces EVERY post's stored vector, even ones that
already have one — use this after changing config.EMBEDDING_DIMENSIONALITY
or EMBEDDING_MODEL, since old vectors at the previous dimensionality will
otherwise just silently stop matching anything (see embeddings.
cosine_similarity's docstring). Bug fix: backfill_from_posts(force=True)
used to append a second, duplicate vector for each post instead of
replacing the stale one — it now does a proper upsert, so re-running this
with --force is safe to do more than once.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_all_posts_for_embedding
import embeddings


def main():
    force = "--force" in sys.argv[1:]
    posts = get_all_posts_for_embedding()
    if not posts:
        print("No published posts found — nothing to backfill.")
        return
    if force:
        print(f"Found {len(posts)} published post(s). Re-embedding ALL of them (--force)...")
    else:
        print(f"Found {len(posts)} published post(s). Embedding any not already stored...")
    count = embeddings.backfill_from_posts(posts, force=force)
    print(f"Done. Newly embedded: {count}. Already had a vector: {len(posts) - count}.")


if __name__ == "__main__":
    main()
