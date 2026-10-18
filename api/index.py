"""FastAPI entrypoint (Vercel serves this file as /api/index; vercel.json rewrites /api/* to it)."""
import os
import sys

# Make the project root importable both on Vercel and when run locally (uvicorn api.index:app).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from core import ai, sources  # noqa: E402

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

NO_STORE = {"Cache-Control": "no-store"}


def _json(data, status=200):
    return JSONResponse(data, status_code=status, headers=NO_STORE)


@app.get("/api/news")
async def api_news(hours: int = 24):
    try:
        return _json(await sources.get_news(hours))
    except sources.NewsUnavailable:
        return _json({"error": "news_unavailable"}, 503)


@app.post("/api/translate")
async def api_translate(request: Request):
    try:
        body = await request.json()
    except ValueError:
        return _json({"ok": False, "reason": "bad_request"}, 400)
    return _json(await ai.translate(body))


@app.post("/api/analyze")
async def api_analyze(request: Request):
    try:
        body = await request.json()
    except ValueError:
        return _json({"ok": False, "reason": "bad_request"}, 400)
    return _json(await ai.analyze(body))


@app.get("/api/health")
async def api_health():
    return _json({"ok": True, "ai_configured": ai.configured(), "model": ai.model_name()})


# Local development only: serve ./public. On Vercel the CDN serves public/ itself.
if not os.environ.get("VERCEL"):
    from fastapi.staticfiles import StaticFiles  # noqa: E402

    _public = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
    if os.path.isdir(_public):
        app.mount("/", StaticFiles(directory=_public, html=True), name="public")
