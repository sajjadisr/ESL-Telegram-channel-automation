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


def has_post_on_date(date_str):
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM posts WHERE date = ?", (date_str,)).fetchone()[0]
    conn.close()
    return n > 0


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


def sync_story_state_from_db():
    """Repair story.json from published story_installment rows (Audit #2)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT content FROM posts WHERE format = 'story_installment' AND status = 'published' "
        "ORDER BY id ASC"
    ).fetchall()
    conn.close()
    if not rows:
        return {"last_installment": 0, "recent_summary": ""}
    last_content = rows[-1][0]
    return {
        "last_installment": len(rows),
        "recent_summary": last_content[:200],
    }
