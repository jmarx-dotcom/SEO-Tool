# app.py

import os

from fastapi import FastAPI, HTTPException, Query
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


@app.get("/")
def index():
    return {
        "message": "Lokal-Archiv-Tool läuft.",
        "hint": "Nutze /search?q=Suchbegriff",
        "example": "/search?q=Weihnachtsmarkt&limit=5",
    }
