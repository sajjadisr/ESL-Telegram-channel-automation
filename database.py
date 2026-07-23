import sqlite3
from config import DB_PATH


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
    # Lightweight migration: if this DB was created before the "format"
    # column existed, add it instead of forcing a manual reset.
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


def get_recent_posts(limit=15):
    conn = get_conn()
    rows = conn.execute(
        "SELECT title, category, level, keywords, content FROM posts "
        "ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


def search_related_posts(keyword, limit=3):
    conn = get_conn()
    rows = conn.execute(
        "SELECT title, content FROM posts WHERE keywords LIKE ? OR title LIKE ? "
        "ORDER BY id DESC LIMIT ?",
        (f"%{keyword}%", f"%{keyword}%", limit),
    ).fetchall()
    conn.close()
    return rows


def count_posts():
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    conn.close()
    return n


def get_titles_for_recap(limit=8):
    """Most recent distinct taught items, oldest-first, for a progress recap post."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT title FROM posts ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows][::-1]
