# db.py

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "articles.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            summary TEXT,
            content TEXT,
            published_at TEXT,
            source TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def save_article(*, url, title, summary="", content="", published_at=None, source=""):
    """Artikel in der Datenbank speichern oder updaten."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat(timespec="seconds")

    cur.execute(
        """
        INSERT INTO articles (url, title, summary, content, published_at, source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            title = excluded.title,
            summary = excluded.summary,
            content = excluded.content,
            published_at = excluded.published_at,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (url, title, summary, content, published_at, source, now, now),
    )

    conn.commit()
    conn.close()


def search_articles(query: str, limit: int = 20):
    """Einfache Textsuche in Titel, Summary und Content."""
    conn = get_connection()
    cur = conn.cursor()
    like = f"%{query}%"
    cur.execute(
        """
        SELECT id, url, title, summary, published_at, source
        FROM articles
        WHERE title LIKE ? OR summary LIKE ? OR content LIKE ?
        ORDER BY published_at DESC NULLS LAST, id DESC
        LIMIT ?
        """,
        (like, like, like, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]
