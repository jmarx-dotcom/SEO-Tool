# db.py

import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "articles.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def expand_search_variants(term: str) -> list[str]:
    """
    Baut verschiedene Varianten eines Suchbegriffs:
    - original (kleingeschrieben)
    - ohne Akzente (ä -> a)
    - mit ae/oe/ue/ss (ä -> ae, ß -> ss)
    """
    term_lower = term.lower()
    variants = set([term_lower])

    # Variante ohne Akzente (ä -> a, ü -> u ...)
    no_accents = "".join(
        c for c in unicodedata.normalize("NFD", term_lower)
        if unicodedata.category(c) != "Mn"
    )
    variants.add(no_accents)

    # Variante mit ae/oe/ue/ss
    trans = term_lower
    trans = trans.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    trans = trans.replace("ß", "ss")
    variants.add(trans)

    return sorted(v for v in variants if v)



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


def search_articles(
    query: str,
    limit: int = 20,
    from_date: str | None = None,
    to_date: str | None = None,
):
    """Textsuche in Titel, Summary und Content mit optionalem Datumsfilter (YYYY-MM-DD) und Umlaut-Varianten."""
    conn = get_connection()
    cur = conn.cursor()

    variants = expand_search_variants(query)
    where_clauses = []
    params: list = []

    # Für jede Variante bauen wir ein OR-Paket:
    # (LOWER(title) LIKE ?) OR (LOWER(summary) LIKE ?) OR (LOWER(content) LIKE ?)
    for v in variants:
        pattern = f"%{v}%"
        where_clauses.append(
            "(LOWER(title) LIKE ? OR LOWER(summary) LIKE ? OR LOWER(content) LIKE ?)"
        )
        params.extend([pattern, pattern, pattern])

    # Alle Varianten mit OR verknüpfen
    text_where = " OR ".join(where_clauses)

    full_where_clauses = [f"({text_where})"]

    # Datumsfilter
    if from_date:
        full_where_clauses.append("published_at >= ?")
        params.append(from_date)
    if to_date:
        full_where_clauses.append("published_at <= ?")
        params.append(to_date + "T23:59:59")

    where_sql = " AND ".join(full_where_clauses)

    sql = f"""
        SELECT id, url, title, summary, published_at, source
        FROM articles
        WHERE {where_sql}
        ORDER BY 
            (published_at IS NULL),
            published_at DESC,
            id DESC
        LIMIT ?
    """

    params.append(limit)

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]
