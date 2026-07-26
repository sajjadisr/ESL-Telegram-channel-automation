import sqlite3

from ai import find_stray_script_chars
from config import DB_PATH

# Formats whose titles are not real curriculum topics (Audit #6).
_META_FORMATS = ("progress_recap", "quiz", "vote_poll")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
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
    return conn


def save_post(date, format_name, category, level, title, content, keywords, status):
    conn = get_conn()
    conn.execute(
        "INSERT INTO posts (date, format, category, level, title, content, keywords, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (date, format_name, category, level, title, content, keywords, status),
    )
    conn.commit()
    conn.close()


def update_post_content(post_id, content):
    conn = get_conn()
    conn.execute("UPDATE posts SET content = ? WHERE id = ?", (content, post_id))
    conn.commit()
    conn.close()


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
    """Backfill pass: fix stray script chars in all published posts (Audit #16)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, content FROM posts WHERE status = 'published'"
    ).fetchall()
    fixed = []
    for post_id, content in rows:
        stray = find_stray_script_chars(content)
        if not stray:
            continue
        cleaned = content
        for ch in stray:
            cleaned = cleaned.replace(ch, "")
        conn.execute("UPDATE posts SET content = ? WHERE id = ?", (cleaned, post_id))
        fixed.append({"id": post_id, "removed": stray})
    conn.commit()
    conn.close()
    return fixed

