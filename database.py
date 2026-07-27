import json
import os
import sqlite3

from ai import find_stray_script_chars
from config import DB_PATH, POSTS_JSONL_PATH

# Formats whose titles are not real curriculum topics (Audit #6).
_META_FORMATS = ("progress_recap", "quiz", "vote_poll")

# --- Git-hygiene fix (posts.db bloat, flagged in AUDIT_FIXES.md #9) --------
# DB_PATH is now a disposable local cache, gitignored, never committed.
# POSTS_JSONL_PATH is the actual durable record: every insert/update is
# appended as one line of JSON, so a new post is a one-line diff forever —
# no rewritten SQLite pages, no ever-growing binary in git history.
#
# get_conn() rebuilds DB_PATH from POSTS_JSONL_PATH whenever the file is
# missing, which on CI is every single run (fresh checkout, gitignored).
# Every query function below (search_related_posts, get_recent_posts, etc.)
# is completely unchanged — SQLite is still the query engine, it just stops
# being the thing git tracks.


def _create_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            format TEXT,
            category TEXT,
            level TEXT,
            title TEXT,
            content TEXT,
            keywords TEXT,
            status TEXT
        )
    """)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(posts)")]
    if "format" not in cols:
        conn.execute("ALTER TABLE posts ADD COLUMN format TEXT")
    # Graded-reader progress tracking (reader.py). Added the same way
    # `format` was added above — a real column, queried with SELECT MAX(),
    # not recovered by regex-parsing AI-generated prose the way the old
    # story_installment format did (see story-removal-and-fixes.diff).
    if "story_id" not in cols:
        conn.execute("ALTER TABLE posts ADD COLUMN story_id TEXT")
    if "chunk_index" not in cols:
        conn.execute("ALTER TABLE posts ADD COLUMN chunk_index INTEGER")


def _append_jsonl(record):
    with open(POSTS_JSONL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _rebuild_db_from_jsonl():
    """Replay data/posts.jsonl into a fresh DB_PATH. Explicit ids are used
    on replay (not autoincrement order) so row identity is exact regardless
    of anything about how the log was written — get_last_published_chunk,
    update_post_content, etc. all key off this same id."""
    conn = sqlite3.connect(DB_PATH)
    _create_schema(conn)
    if os.path.exists(POSTS_JSONL_PATH):
        with open(POSTS_JSONL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec["op"] == "insert":
                    conn.execute(
                        "INSERT INTO posts (id, date, format, category, level, title, "
                        "content, keywords, status, story_id, chunk_index) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (rec["id"], rec["date"], rec["format"], rec["category"],
                         rec["level"], rec["title"], rec["content"], rec["keywords"],
                         rec["status"], rec.get("story_id"), rec.get("chunk_index")),
                    )
                elif rec["op"] == "update":
                    conn.execute(
                        "UPDATE posts SET content = ? WHERE id = ?",
                        (rec["content"], rec["id"]),
                    )
    conn.commit()
    conn.close()


def get_conn():
    if not os.path.exists(DB_PATH):
        _rebuild_db_from_jsonl()
    conn = sqlite3.connect(DB_PATH)
    _create_schema(conn)
    return conn


def save_post(date, format_name, category, level, title, content, keywords, status,
              story_id=None, chunk_index=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO posts (date, format, category, level, title, content, keywords, status, "
        "story_id, chunk_index) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (date, format_name, category, level, title, content, keywords, status,
         story_id, chunk_index),
    )
    post_id = cur.lastrowid
    conn.commit()
    conn.close()
    _append_jsonl({
        "op": "insert", "id": post_id, "date": date, "format": format_name,
        "category": category, "level": level, "title": title, "content": content,
        "keywords": keywords, "status": status, "story_id": story_id,
        "chunk_index": chunk_index,
    })
    return post_id


def get_last_published_chunk(story_id):
    """Ground truth for "what's the next chunk of this story" — a real
    query against the durable, already-committed-every-run posts table,
    not a cache that can silently go stale (see reader.py)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT MAX(chunk_index) FROM posts WHERE story_id = ? AND status = 'published'",
        (story_id,),
    ).fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else None


def update_post_content(post_id, content):
    conn = get_conn()
    conn.execute("UPDATE posts SET content = ? WHERE id = ?", (content, post_id))
    conn.commit()
    conn.close()
    _append_jsonl({"op": "update", "id": post_id, "content": content})


def get_recent_posts(limit=15, published_only=True):
    """Recent posts for quiz topic selection. Skips recap/quiz rows and unpublished
    pending_manual illustrated_pun drafts (Audit #6, #23)."""
    conn = get_conn()
    clauses = ["format NOT IN ({})".format(",".join("?" * len(_META_FORMATS)))]
    params = list(_META_FORMATS)
    if published_only:
        clauses.append("status = 'published'")
    where = " AND ".join(clauses)
    rows = conn.execute(
        f"SELECT title, category, level, keywords, content FROM posts "
        f"WHERE {where} ORDER BY id DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    conn.close()
    return rows


def search_related_posts(keyword, category=None, limit=3, published_only=True):
    conn = get_conn()
    clauses = ["(keywords LIKE ? OR title LIKE ?)"]
    params = [f"%{keyword}%", f"%{keyword}%"]
    if category:
        clauses.append("category = ?")
        params.append(category)
    if published_only:
        clauses.append("status = 'published'")
    where = " AND ".join(clauses)
    params.append(limit)
    rows = conn.execute(
        f"SELECT title, content FROM posts WHERE {where} ORDER BY id DESC LIMIT ?",
        params,
    ).fetchall()
    conn.close()
    return rows


def context_posts_for_generation(topic_keyword, category=None, recency_limit=5, topic_limit=3):
    """Posts to show the model as "already used, don't repeat" context.

    search_related_posts alone misses cross-topic repeats: it matches only
    by topic-name substring (+ optional exact category match), so two
    topics with unrelated names/categories that happen to share the most
    natural example sentence (e.g. "Present simple tense" [Grammar] and
    "Daily routine words" [Vocabulary] both naturally illustrated with "I
    drink coffee every morning") never see each other as related — that's
    what let the same coffee joke get reused two days in a row.

    This unions two views: the most recent published posts overall
    (catches cross-topic repeats, regardless of keyword/category) and
    whatever search_related_posts finds for this specific topic (catches
    same-topic repeats that may have scrolled out of "recent"). Returns
    (title, content) tuples, most-relevant first, de-duplicated by title.
    """
    topic_specific = search_related_posts(topic_keyword, category=category, limit=topic_limit)
    recent_pairs = [(row[0], row[4]) for row in get_recent_posts(limit=recency_limit)]

    seen_titles = set()
    combined = []
    for title, content in list(topic_specific) + recent_pairs:
        if title in seen_titles:
            continue
        seen_titles.add(title)
        combined.append((title, content))
    return combined


def count_posts(published_only=False):
    conn = get_conn()
    if published_only:
        n = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE status = 'published'"
        ).fetchone()[0]
    else:
        n = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    conn.close()
    return n


def count_posts_on_date(date_str):
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM posts WHERE date = ?", (date_str,)).fetchone()[0]
    conn.close()
    return n


def get_titles_for_recap(limit=8):
    """Distinct taught topics for progress recap — published curriculum posts only."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT title FROM posts "
        "WHERE status = 'published' AND format NOT IN ({}) "
        "ORDER BY id DESC LIMIT ?".format(",".join("?" * len(_META_FORMATS))),
        (*_META_FORMATS, limit),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows][::-1]


def remediate_stray_chars_in_db():
    """Backfill pass: fix stray script chars in all published posts (Audit #16).
    Goes through update_post_content (not raw SQL) so every content change
    still lands in posts.jsonl — otherwise a fix applied here would hold for
    the rest of this run's local DB but silently revert on the next fresh
    checkout, since the durable record wouldn't know about it."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, content FROM posts WHERE status = 'published'"
    ).fetchall()
    conn.close()
    fixed = []
    for post_id, content in rows:
        stray = find_stray_script_chars(content)
        if not stray:
            continue
        cleaned = content
        for ch in stray:
            cleaned = cleaned.replace(ch, "")
        update_post_content(post_id, cleaned)
        fixed.append({"id": post_id, "removed": stray})
    return fixed

