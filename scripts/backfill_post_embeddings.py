"""Run once after deploying embeddings.py (semantic dedup) so it covers
every post already published, not just posts going forward. Safe to
re-run any time — skips posts that already have a stored vector (see
embeddings.backfill_from_posts).

Usage: python scripts/backfill_post_embeddings.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_all_posts_for_embedding
import embeddings


def main():
    posts = get_all_posts_for_embedding()
    if not posts:
        print("No published posts found — nothing to backfill.")
        return
    print(f"Found {len(posts)} published post(s). Embedding any not already stored...")
    count = embeddings.backfill_from_posts(posts)
    print(f"Done. Newly embedded: {count}. Already had a vector: {len(posts) - count}.")


if __name__ == "__main__":
    main()
