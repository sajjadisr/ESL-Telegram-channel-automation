"""One-time migration: export the rows currently in data/posts.db into
data/posts.jsonl, so the jsonl log starts with real history instead of
starting empty.

Run this ONCE, locally, from the repo root, against your real data/posts.db:

    python scripts/migrate_posts_db_to_jsonl.py

Then:
    git add data/posts.jsonl
    git rm --cached data/posts.db
    git commit -m "Migrate posts.db to posts.jsonl (git hygiene)"
    git push

Why `git rm --cached` and not just relying on .gitignore: .gitignore only
stops NEW files from being tracked. data/posts.db was already committed
before that line was ever added, so git has kept tracking and diffing it on
every commit regardless — the .gitignore entry alone was never doing
anything. `--cached` removes it from git's index only; your local file stays
on disk untouched (harmless either way, since database.py now rebuilds it
from posts.jsonl automatically whenever it's missing).

Safe to run more than once — it reads posts.db fresh each time and
overwrites posts.jsonl from scratch, it doesn't append to whatever's already
there.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DB_PATH, POSTS_JSONL_PATH


def migrate(force=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM posts ORDER BY id").fetchall()
    conn.close()

    if Path(POSTS_JSONL_PATH).exists():
        existing_rows = sum(1 for _ in open(POSTS_JSONL_PATH, "r", encoding="utf-8"))
        if existing_rows > len(rows) and not force:
            raise RuntimeError(
                f"Refusing to overwrite {POSTS_JSONL_PATH}: it already contains {existing_rows} rows, "
                f"which is more than the {len(rows)} rows available in {DB_PATH}. "
                "Delete or rename the existing JSONL, or rerun with --force if you really want to overwrite."
            )

    with open(POSTS_JSONL_PATH, "w", encoding="utf-8") as f:
        for row in rows:
            record = {
                "op": "insert",
                "id": row["id"],
                "date": row["date"],
                "format": row["format"],
                "category": row["category"],
                "level": row["level"],
                "title": row["title"],
                "content": row["content"],
                "keywords": row["keywords"],
                "status": row["status"],
                "story_id": row["story_id"] if "story_id" in row.keys() else None,
                "chunk_index": row["chunk_index"] if "chunk_index" in row.keys() else None,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Migrated {len(rows)} row(s) from {DB_PATH} to {POSTS_JSONL_PATH}.")


def parse_args():
    parser = argparse.ArgumentParser(description="Migrate posts.db to posts.jsonl safely.")
    parser.add_argument("--force", action="store_true", help="Overwrite posts.jsonl even if it contains more rows than the database export.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    migrate(force=args.force)


if __name__ == "__main__":
    migrate()
