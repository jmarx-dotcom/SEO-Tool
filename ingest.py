# ingest.py

import calendar
from datetime import datetime
from typing import Optional

import feedparser

from config import FEEDS
from db import init_db, save_article


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


def ingest_feed(feed_url: str):
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

        save_article(
            url=url,
            title=title,
            summary=summary,
            content="",  # Volltext holen wir später aus der HTML-Seite
            published_at=published_at,
            source=source_title,
        )
        count += 1

    print(f"✓ {count} Einträge aus {feed_url} verarbeitet.")


def main():
    init_db()
    for feed_url in FEEDS:
        ingest_feed(feed_url)


if __name__ == "__main__":
    main()
