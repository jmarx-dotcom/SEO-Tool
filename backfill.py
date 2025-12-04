# backfill.py

from datetime import datetime, date
from typing import List, Dict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from db import init_db, save_article

BASE_URL = "https://www.goettinger-tageblatt.de"


def archive_url_for_date(day: date) -> str:
    """Baut die Archiv-URL für ein Datum, z.B. 2025-07-01 -> .../archiv/artikel-01-07-2025/"""
    return f"{BASE_URL}/archiv/artikel-{day.strftime('%d-%m-%Y')}/"


def collect_article_urls_for_date(day: date) -> List[str]:
    """Sammelt alle Göttingen-Artikel-URLs aus dem Archiv für einen Tag."""
    url = archive_url_for_date(day)
    print(f"▶ Lade Archivseite: {url}")
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    article_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]

        # Absoluten Link bauen
        if href.startswith("/"):
            full = urljoin(BASE_URL, href)
        elif href.startswith("http"):
            full = href
        else:
            continue

        # Nur Lokales Göttingen
        if "/lokales/goettingen-lk/goettingen/" in full:
            article_urls.add(full)

    urls_sorted = sorted(article_urls)
    print(f"✓ {len(urls_sorted)} Göttingen-Artikel-Links gefunden für {day.isoformat()}")
    return urls_sorted


def fetch_article_from_page(url: str, default_date: date) -> Dict:
    """Lädt eine Artikelseite, zieht Titel + Volltext heraus."""
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[WARN] Konnte Artikel nicht laden: {url} ({e})")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")

    # Titel
    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else url

    # Text
    article_tag = soup.find("article")
    if article_tag:
        paragraphs = article_tag.find_all("p")
    else:
        paragraphs = soup.find_all("p")

    texts = [p.get_text(strip=True) for p in paragraphs]
    texts = [t for t in texts if t]
    content = "\n\n".join(texts)

    # Datum: wir nehmen das Archiv-Datum (ist auf Tagesebene korrekt)
    published_at = datetime.combine(default_date, datetime.min.time()).isoformat(timespec="seconds")

    return {
        "url": url,
        "title": title,
        "summary": "",  # könnten wir später noch ausbauen
        "content": content,
        "published_at": published_at,
        "source": "GT Archiv",
    }


def backfill_day(date_str: str) -> Dict:
    """
    Liest für ein Datum (YYYY-MM-DD) alle Lokales-Göttingen-Artikel aus dem Archiv
    und speichert sie in der Datenbank.
    """
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Datum muss im Format YYYY-MM-DD sein, z.B. 2025-07-01")

    init_db()

    urls = collect_article_urls_for_date(day)
    saved = 0

    for url in urls:
        article = fetch_article_from_page(url, day)
        if not article:
            continue

        save_article(
            url=article["url"],
            title=article["title"],
            summary=article["summary"],
            content=article["content"],
            published_at=article["published_at"],
            source=article["source"],
        )
        saved += 1

    return {
        "date": day.isoformat(),
        "urls_found": len(urls),
        "articles_saved": saved,
    }
from datetime import timedelta


def backfill_range(start_date_str: str, end_date_str: str) -> Dict:
    """
    Backfill für einen ganzen Zeitraum (inklusive), z.B. 2024-08-01 bis 2025-07-31.
    Ruft intern backfill_day für jeden Tag auf.
    """
    try:
        start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Start und Ende müssen im Format YYYY-MM-DD sein, z.B. 2025-07-01")

    if end < start:
        raise ValueError("Enddatum muss nach dem Startdatum liegen")

    init_db()

    total_urls = 0
    total_saved = 0
    per_day: Dict[str, Dict] = {}

    current = start
    while current <= end:
        date_str = current.isoformat()
        print(f"▶ Backfill für {date_str}")
        summary = backfill_day(date_str)
        per_day[date_str] = summary
        total_urls += summary.get("urls_found", 0)
        total_saved += summary.get("articles_saved", 0)
        current += timedelta(days=1)

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days": (end - start).days + 1,
        "total_urls_found": total_urls,
        "total_articles_saved": total_saved,
        "per_day": per_day,
    }
