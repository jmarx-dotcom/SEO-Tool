# app.py

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from db import search_articles

app = FastAPI(title="Lokal-Archiv-Tool")


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


@app.get("/")
def index():
    return {
        "message": "Lokal-Archiv-Tool läuft.",
        "hint": "Nutze /search?q=Suchbegriff",
        "example": "/search?q=Weihnachtsmarkt&limit=5",
    }
