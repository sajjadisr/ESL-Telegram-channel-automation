import sqlite3
from config import DB_PATH

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            category TEXT,
            level TEXT,
            title TEXT,
            content TEXT,
            keywords TEXT,
            status TEXT
        )
    """)
    return conn

def save_post(date, category, level, title, content, keywords, status):
    conn = get_conn()
    conn.execute(
        "INSERT INTO posts (date, category, level, title, content, keywords, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (date, category, level, title, content, keywords, status),
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