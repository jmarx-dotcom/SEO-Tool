# app.py

import os
from datetime import datetime, timedelta

import requests
from fastapi import FastAPI, HTTPException, Query, Form
from fastapi.responses import JSONResponse

from db import search_articles, init_db, get_republish_candidates
from ingest import ingest_all
from backfill import backfill_day as backfill_day_func, backfill_range as backfill_range_func

app = FastAPI(title="Lokal-Archiv-Tool")

# Beim Start sicherstellen, dass die Datenbank & Tabelle existieren
init_db()

# Secret-Token, das wir in Render als Environment Variable setzen
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "changeme")

# Slack-Webhook für Push-Nachrichten (Incoming Webhook URL in Render als SLACK_WEBHOOK_URL setzen)
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")


def post_to_slack(text: str) -> None:
    """Einfache Hilfsfunktion, um Text an einen Slack-Webhook zu schicken."""
    if not SLACK_WEBHOOK_URL:
        # Wenn kein Webhook gesetzt ist, einfach nichts schicken
        return
    try:
        resp = requests.post(
            SLACK_WEBHOOK_URL,
            json={"text": text},
            timeout=5,
        )
        # Fehler nicht hochwerfen, sondern nur im Worst Case ignorieren
        _ = resp.text  # verhindert "unused variable" in manchen Lintern
    except Exception:
        # Fürs Logging könnte man hier noch print/loggen, für MVP ignorieren
        pass


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


@app.get("/republish_candidates")
def republish_candidates_endpoint(
    topic: str | None = Query(None, description="Optionales Themen-Keyword, z.B. 'Weihnachtsmarkt'"),
    limit: int = 50,
    from_date: str | None = Query(
        None, description="Startdatum YYYY-MM-DD (optional, Standard ~3 Jahre zurück)"
    ),
    to_date: str | None = Query(
        None, description="Enddatum YYYY-MM-DD (optional, Standard: älter als 6 Monate)"
    ),
):
    """
    Liefert Artikel, die sich als Republishing-Kandidaten eignen könnten.

    Standard:
    - älter als 6 Monate
    - maximal ca. 3 Jahre zurück
    - 'Hard News' (Unfall, Polizei, Brand etc.) werden über den Titel ausgeschlossen

    limit: Anzahl der Ergebnisse (Standard 50)
    """
    today = datetime.utcnow().date()

    if not to_date:
        # maximaler Aktualitätsstand für Republish-Kandidaten: 6 Monate alt
        max_date = today - timedelta(days=180)
        to_date = max_date.isoformat()

    if not from_date:
        # Standard: ca. 3 Jahre zurück
        min_date = today - timedelta(days=3 * 365)
        from_date = min_date.isoformat()

    # 1. Versuchen mit 'schlauer' Republish-Logik
    results = get_republish_candidates(topic, from_date, to_date, limit=limit)

    # 2. Fallback: wenn nichts gefunden, normale Volltextsuche
    if not results and topic:
        results = search_articles(topic, limit=limit, from_date=from_date, to_date=to_date)

    return {
        "topic": topic,
        "from_date": from_date,
        "to_date": to_date,
        "count": len(results),
        "results": results,
    }


@app.post("/slack/republish")
async def slack_republish(
    text: str = Form(""),
    user_name: str | None = Form(None),
    channel_id: str | None = Form(None),
):
    """
    Slash-Command-Endpoint für Slack: /republish <Thema> [seit:YYYY-MM-DD] [bis:YYYY-MM-DD] [limit:ZAHL]

    Beispiele:
    - /republish Weihnachtsmarkt
    - /republish Weihnachtsmarkt seit:2023-01-01
    - /republish Weihnachtsmarkt seit:2023-01-01 bis:2024-12-31 limit:50
    """
    raw = text.strip()

    # Defaults: ca. 3 Jahre zurück, bis vor 6 Monaten
    today = datetime.utcnow().date()
    default_to = (today - timedelta(days=180)).isoformat()
    default_from = (today - timedelta(days=3 * 365)).isoformat()

    if not raw:
        return {
            "response_type": "ephemeral",
            "text": (
                "Bitte gib ein Thema an, z.B. `/republish Weihnachtsmarkt` "
                "oder `/republish Weihnachtsmarkt seit:2023-01-01 limit:50`."
            ),
        }

    parts = raw.split()
    topic_parts: list[str] = []
    from_date: str | None = None
    to_date: str | None = None
    limit_value: int = 20  # Default in Slack
    max_limit: int = 100   # Harte Obergrenze, um Slack nicht zu sprengen

    for part in parts:
        if part.startswith("seit:"):
            from_date = part.removeprefix("seit:")
        elif part.startswith("bis:"):
            to_date = part.removeprefix("bis:")
        elif part.startswith("limit:"):
            limit_str = part.removeprefix("limit:")
            try:
                limit_parsed = int(limit_str)
                if limit_parsed > 0:
                    limit_value = min(limit_parsed, max_limit)
            except ValueError:
                # Ignorieren, wenn keine gültige Zahl
                pass
        else:
            topic_parts.append(part)

    topic = " ".join(topic_parts).strip() or None

    if not from_date:
        from_date = default_from
    if not to_date:
        to_date = default_to

    # 1. Versuchen mit 'schlauer' Republish-Logik
    results = get_republish_candidates(topic, from_date, to_date, limit=limit_value)

    # 2. Fallback: wenn nichts gefunden, normale Volltextsuche
    if not results and topic:
        results = search_articles(topic, limit=limit_value, from_date=from_date, to_date=to_date)

    if not results:
        return {
            "response_type": "ephemeral",
            "text": (
                f"Keine Republish-Kandidaten für `{topic or 'alle Themen'}` "
                f"im Zeitraum {from_date} bis {to_date} gefunden."
            ),
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

    topic_info = f"`{topic}`" if topic else "alle Themen"
    text_response = (
        f"{len(results)} Republish-Kandidaten für {topic_info} "
        f"(Zeitraum {from_date} bis {to_date}, Limit {limit_value}):\n\n"
        + "\n\n".join(lines)
    )

    return {
        "response_type": "in_channel",
        "text": text_response,
    }


@app.get("/seo/weekly_digest")
def seo_weekly_digest(
    token: str = Query(..., description="Secret-Token zum Auslösen des SEO-Digests"),
    topic: str | None = Query(
        None,
        description="Optionales Themen-Keyword, z.B. 'Weihnachtsmarkt'. Wenn leer, alle Themen.",
    ),
    limit: int = 20,
):
    """
    Baut einen SEO-/Republishing-Digest und schickt ihn per Slack-Webhook.

    Standard:
    - Zeitraum: ca. 3 Jahre zurück bis vor 6 Monaten
    - Hard-News werden wie in get_republish_candidates ausgeschlossen
    - Wenn topic gesetzt ist, werden die Kandidaten thematisch gefiltert.
    """
    if token != INGEST_TOKEN:
        raise HTTPException(status_code=403, detail="Ungültiger Token")

    today = datetime.utcnow().date()
    to_date = (today - timedelta(days=180)).isoformat()
    from_date = (today - timedelta(days=3 * 365)).isoformat()

    # 1. Kandidaten via Republish-Logik holen
    candidates = get_republish_candidates(topic, from_date, to_date, limit=limit)

    # 2. Fallback: normale Volltextsuche, falls ein Thema gesetzt ist und nichts gefunden wurde
    if not candidates and topic:
        candidates = search_articles(topic, limit=limit, from_date=from_date, to_date=to_date)

    if not candidates:
        text = (
            f"SEO-Weekly: Keine Republish-Kandidaten für {topic or 'alle Themen'} "
            f"im Zeitraum {from_date} bis {to_date} gefunden."
        )
        post_to_slack(text)
        return {
            "status": "ok",
            "sent": False,
            "reason": "no_candidates",
            "topic": topic,
            "from_date": from_date,
            "to_date": to_date,
        }

    lines = []
    for art in candidates:
        title = art.get("title") or "(ohne Titel)"
        url = art.get("url") or ""
        published_at_raw = art.get("published_at") or "ohne Datum"
        published_date = published_at_raw.split("T")[0] if "T" in published_at_raw else published_at_raw
        source = art.get("source") or ""

        line = (
            f"*{title}*\n"
            f"{published_date} · {source}\n"
            f"<{url}|Artikel öffnen>"
        )
        lines.append(line)

    topic_info = f"`{topic}`" if topic else "alle Themen"
    header = (
        f"SEO-Weekly: Republish-Kandidaten für {topic_info} "
        f"(Zeitraum {from_date} bis {to_date}, max. {limit} Stück):"
    )
    text = header + "\n\n" + "\n\n".join(lines)

    post_to_slack(text)

    return {
        "status": "ok",
        "sent": True,
        "topic": topic,
        "from_date": from_date,
        "to_date": to_date,
        "count": len(candidates),
    }


@app.get("/")
def index():
    return {
        "message": "Lokal-Archiv-Tool läuft.",
        "hint": "Nutze /search?q=Suchbegriff",
        "example": "/search?q=Weihnachtsmarkt&limit=5",
    }
