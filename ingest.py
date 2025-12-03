# ingest.py

import calendar
from datetime import datetime
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup

from config import FEEDS
from db import init_db, save_article


def fetch_fulltext(url: str) -> str:
    """Versucht, den Artikelvolltext von der URL zu holen."""
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[WARN] Konnte {url} nicht laden: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1. Versuchen, einen <article>-Block zu finden
    article = soup.find("article")
    if article:
        paragraphs = article.find_all("p")
    else:
        # 2. Fallback: alle <p>-Tags auf der Seite
        paragraphs = soup.find_all("p")

    texts = [p.get_text(strip=True) for p in paragraphs]
    texts = [t for t in texts if t]  # nur nicht-leere Absätze behalten

    return "\n\n".join(texts)


def parse_published(entry) -> Optional[str]:
    """Veröffentlichungsdatum aus dem RSS-Entry holen und in ISO-Format wandeln."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt = datetime.utcfromtimestamp(calendar.timegm(entry.published_parsed))
        return dt.isoformat(timespec="seconds")
    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
        dt = datetime.utcfromtimestamp(calendar.timegm(entry.updated_parsed))
        return dt.isoformat(timespec="seconds")
    else:
        return None


def ingest_feed(feed_url: str) -> int:
    print(f"▶ Lese Feed: {feed_url}")
    feed = feedparser.parse(feed_url)

    source_title = feed.feed.get("title", feed_url)

    count = 0
    for entry in feed.entries:
        url = entry.get("link")
        title = entry.get("title", "").strip()
        summary = entry.get("summary", "").strip()

        if not url or not title:
            continue

        published_at = parse_published(entry)

        # Volltext von der Artikelseite holen
        content = fetch_fulltext(url)

        save_article(
            url=url,
            title=title,
            summary=summary,
            content=content,
            published_at=published_at,
            source=source_title,
        )
        count += 1

    print(f"✓ {count} Einträge aus {feed_url} verarbeitet.")
    return count


def ingest_all():
    """Alle konfigurierten Feeds einlesen und eine kleine Zusammenfassung zurückgeben."""
    init_db()
    total = 0
    per_feed = {}

    for feed_url in FEEDS:
        count = ingest_feed(feed_url)
        per_feed[feed_url] = count
        total += count

    return {
        "total_articles_processed": total,
        "per_feed": per_feed,
    }


def main():
    init_db()
    for feed_url in FEEDS:
        ingest_feed(feed_url)


if __name__ == "__main__":
    main()
