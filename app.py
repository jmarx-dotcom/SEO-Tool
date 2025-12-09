# app.py

import os

from fastapi import FastAPI, HTTPException, Query, Form
from fastapi.responses import JSONResponse

from datetime import datetime, timedelta
from db import search_articles, init_db, get_republish_candidates
from ingest import ingest_all
from backfill import backfill_day as backfill_day_func, backfill_range as backfill_range_func

app = FastAPI(title="Lokal-Archiv-Tool")

# Beim Start sicherstellen, dass die Datenbank & Tabelle existieren
init_db()

# Secret-Token, das wir in Render als Environment Variable setzen
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "changeme")


@app.get("/search")
def search(
    q: str = Query(..., description="Suchbegriff"),
    limit: int = 20,
    from_date: str | None = Query(None, description="Startdatum YYYY-MM-DD"),
    to_date: str | None = Query(None, description="Enddatum YYYY-MM-DD"),
):
    """
    Einfache Suche über Titel, Summary und Content.
    Optional: Datumsfilter von/bis (YYYY-MM-DD).

    Beispiele:
    - /search?q=Weihnachtsmarkt&limit=10
    - /search?q=Hochschulsport&from_date=2025-07-01&to_date=2025-07-31
    """
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Parameter 'q' darf nicht leer sein.")

    results = search_articles(q, limit=limit, from_date=from_date, to_date=to_date)
    return JSONResponse(
        {
            "query": q,
            "from_date": from_date,
            "to_date": to_date,
            "count": len(results),
            "results": results,
        }
    )


@app.get("/ingest")
def trigger_ingest(token: str = Query(..., description="Secret-Token zum Auslösen des Ingests")):
    """
    RSS-Feeds einlesen und Artikel in der Datenbank speichern.
    Aufruf: /ingest?token=DEIN_GEHEIMES_TOKEN
    """
    if token != INGEST_TOKEN:
        raise HTTPException(status_code=403, detail="Ungültiger Token")

    summary = ingest_all()
    return {"status": "ok", **summary}


@app.post("/slack/archiv")
async def slack_archiv(
    text: str = Form(""),
    user_name: str | None = Form(None),
    channel_id: str | None = Form(None),
):
    """
    Slash-Command-Endpoint für Slack: /archiv <Suchbegriffe>

    Optional: Datumsfilter im Text, z.B.:
    /archiv Hochschulsport seit:2025-07-01 bis:2025-07-31
    """
    raw = text.strip()

    if not raw:
        return {
            "response_type": "ephemeral",
            "text": "Bitte gib einen Suchbegriff an, z.B. `/archiv Weihnachtsmarkt`.",
        }

    parts = raw.split()
    query_parts: list[str] = []
    from_date: str | None = None
    to_date: str | None = None

    for part in parts:
        if part.startswith("seit:"):
            from_date = part.removeprefix("seit:")
        elif part.startswith("bis:"):
            to_date = part.removeprefix("bis:")
        else:
            query_parts.append(part)

    query = " ".join(query_parts).strip()

    if not query:
        return {
            "response_type": "ephemeral",
            "text": "Bitte gib einen Suchbegriff an, z.B. `/archiv Weihnachtsmarkt seit:2025-07-01`.",
        }

    results = search_articles(query, limit=5, from_date=from_date, to_date=to_date)

    if not results:
        extra = ""
        if from_date or to_date:
            extra = f" im Zeitraum {from_date or '...'} bis {to_date or '...'}"
        return {
            "response_type": "ephemeral",
            "text": f"Keine Treffer für `{query}`{extra}.",
        }

    lines = []
    for art in results:
        title = art.get("title") or "(ohne Titel)"
        url = art.get("url") or ""
        published_at = art.get("published_at") or "ohne Datum"
        source = art.get("source") or ""

        line = (
            f"*{title}*\n"
            f"{published_at} · {source}\n"
            f"<{url}|Artikel öffnen>"
        )
        lines.append(line)

    dates_info = ""
    if from_date or to_date:
        dates_info = f" (Zeitraum {from_date or '...'} bis {to_date or '...'})"

    text_response = f"Suchergebnisse für *`{query}`*{dates_info}:\n\n" + "\n\n".join(lines)

    return {
        "response_type": "in_channel",
        "text": text_response,
    }


@app.get("/backfill_day")
def backfill_day_endpoint(
    date: str = Query(..., description="Datum im Format YYYY-MM-DD"),
    token: str = Query(..., description="Secret-Token zum Auslösen des Backfills"),
):
    """
    Backfill für einen Tag: holt alle Lokales-Göttingen-Artikel aus dem Archiv.
    Aufruf: /backfill_day?date=2025-07-01&token=DEIN_TOKEN
    """
    if token != INGEST_TOKEN:
        raise HTTPException(status_code=403, detail="Ungültiger Token")

    try:
        summary = backfill_day_func(date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok", **summary}


@app.get("/backfill_range")
def backfill_range_endpoint(
    start: str = Query(..., description="Startdatum YYYY-MM-DD"),
    end: str = Query(..., description="Enddatum YYYY-MM-DD"),
    token: str = Query(..., description="Secret-Token zum Auslösen des Backfills"),
):
    """
    Backfill für einen Zeitraum von Start bis Ende (inklusive).
    Beispiel:
    /backfill_range?start=2025-07-01&end=2025-07-31&token=DEIN_TOKEN
    """
    if token != INGEST_TOKEN:
        raise HTTPException(status_code=403, detail="Ungültiger Token")

    try:
        summary = backfill_range_func(start, end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok", **summary}


@app.get("/")
def index():
    return {
        "message": "Lokal-Archiv-Tool läuft.",
        "hint": "Nutze /search?q=Suchbegriff",
        "example": "/search?q=Weihnachtsmarkt&limit=5",
    }
