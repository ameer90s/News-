from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db, save_articles, history_summary, database_backend
from .engine import fetch_matrix, rank_events, TOPIC_LABELS
from .analysis import analyze_topic

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Strategic Newsroom & Intelligence Room")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR, check_dir=False), name="static")

CACHE: dict = {"updated_at": None, "hours": None, "payload": None}


def build_payload(hours: int = 24):
    maxrecords = int(os.getenv("MAX_RECORDS", "45"))
    fetched_at = datetime.now(timezone.utc).isoformat()

    # News collection must work even when no database or API key is configured.
    articles = fetch_matrix(hours=hours, maxrecords=maxrecords)

    history = {"article_count": 0, "source_count": 0, "oldest": None, "newest": None}
    db_warning = None
    try:
        init_db()
        save_articles([a.to_dict() for a in articles], fetched_at)
        history = history_summary(90)
    except Exception as exc:
        # Persistence is optional during the first Vercel test. The newsroom still runs.
        db_warning = f"Persistence unavailable: {type(exc).__name__}"

    events = {topic: rank_events(articles, topic=topic, top_n=12) for topic in TOPIC_LABELS}
    analyses = {topic: analyze_topic(topic, events[topic], history) for topic in TOPIC_LABELS}
    all_events = sorted([e for lst in events.values() for e in lst], key=lambda x: x["score"], reverse=True)
    meta = {
        "updated_at": fetched_at,
        "hours": hours,
        "history": history,
        "article_count": len(articles),
        "database": database_backend(),
    }
    if db_warning:
        meta["warning"] = db_warning

    payload = {
        "meta": meta,
        "hero": all_events[0] if all_events else None,
        "top_events": all_events[:8],
        "events": events,
        "analyses": analyses,
    }
    CACHE.update({"updated_at": fetched_at, "hours": hours, "payload": payload})
    return payload


@app.get("/api/health")
def health():
    return {"status": "ok", "updated_at": CACHE.get("updated_at"), "database": database_backend()}


@app.post("/api/refresh")
def refresh(hours: int = 24):
    try:
        return build_payload(hours)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard")
def dashboard(hours: int = 24):
    if CACHE.get("payload") and CACHE.get("hours") == hours:
        return CACHE["payload"]
    try:
        return build_payload(hours)
    except Exception as e:
        if CACHE.get("payload"):
            cached = CACHE["payload"].copy()
            cached["meta"]["warning"] = f"Using cached payload after refresh error: {e}"
            return JSONResponse(cached)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/topic/{topic}")
def topic_view(topic: str, hours: int = 24):
    if topic not in TOPIC_LABELS:
        raise HTTPException(status_code=404, detail="Unknown topic")
    payload = dashboard(hours)
    return {
        "meta": payload["meta"],
        "events": payload["events"][topic],
        "analysis": payload["analyses"][topic],
    }


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    target = STATIC_DIR / full_path
    if target.exists() and target.is_file():
        return FileResponse(target)
    return FileResponse(STATIC_DIR / "index.html")
