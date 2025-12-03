# app.py

import os

from fastapi import FastAPI, HTTPException, Query, Form
from fastapi.responses import JSONResponse

from db import search_articles
from ingest import ingest_all

app = FastAPI(title="Lokal-Archiv-Tool")

# Secret-Token, das wir in Render als Environment Variable setzen
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "changeme")


@app.get("/search")
def search(q: str = Query(..., description="Suchbegriff"), limit: int = 20):
    """
    Einfache Suche über Titel, Summary und Content.
    Aufruf: /search?q=Weihnachtsmarkt&limit=10
    """
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Parameter 'q' darf nicht leer sein.")

    results = search_articles(q, limit=limit)
    return JSONResponse({"query": q, "count": len(results), "results": results})


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
    user_name: str = Form(None),
    channel_id: str = Form(None),
):
    """
    Slash-Command-Endpoint für Slack: /archiv <Suchbegriffe>

    Slack schickt ein POST mit form-url-encoded Daten, u.a.:
    - text: alles, was nach /archiv eingegeben wurde
    """
    query = text.strip()

    if not query:
        # Nur für die Person sichtbar, die den Command genutzt hat
        return {
            "response_type": "ephemeral",
            "text": "Bitte gib einen Suchbegriff an, z.B. `/archiv Weihnachtsmarkt`.",
        }

    results = search_articles(query, limit=5)

    if not results:
        return {
            "response_type": "ephemeral",
            "text": f"Keine Treffer für `{query}`.",
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

    text_response = f"Suchergebnisse für *`{query}`*:\n\n" + "\n\n".join(lines)

    # in_channel = für alle im Channel sichtbar; wenn du erstmal "privat" testen willst, nimm "ephemeral"
    return {
        "response_type": "in_channel",
        "text": text_response,
    }


@app.get("/")
def index():
    return {
        "message": "Lokal-Archiv-Tool läuft.",
        "hint": "Nutze /search?q=Suchbegriff",
        "example": "/search?q=Weihnachtsmarkt&limit=5",
    }
