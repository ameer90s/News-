"""FastAPI entrypoint (Vercel serves this file as /api/index; vercel.json rewrites /api/* to it)."""
import asyncio
import os
import sys
import time
from urllib.parse import urlencode

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


# --------------------------------------------------------------------------- path-agnostic fallback
# vercel.json rewrites /api/(.*) to /api/index. Depending on the Vercel runtime the app may then see the
# rewritten path instead of the original one, which would make every route above answer 404. This fallback
# recognises the request by method / query / body shape instead of by path, so the API works either way.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def _probe(url: str) -> dict:
    t0 = time.monotonic()
    try:
        text = await asyncio.to_thread(sources._http_get, url, 8.0)
        return {"ok": True, "ms": int((time.monotonic() - t0) * 1000), "bytes": len(text),
                "head": text[:90].replace("\n", " ")}
    except Exception as e:  # noqa: BLE001 - diagnostics must report, never raise
        return {"ok": False, "ms": int((time.monotonic() - t0) * 1000), "error": type(e).__name__,
                "detail": str(e)[:140]}


async def _diag(request: Request, seen: str, mode: str) -> dict:
    """Temporary diagnostics: ?diag=1 shows how the request reached the app, ?diag=net also probes the news sources."""
    scope = request.scope
    keep = {k: v for k, v in request.headers.items()
            if k.startswith(("x-vercel", "x-matched", "x-forwarded-host", "x-forwarded-proto")) or k == "host"}
    out = {
        "seen_path": seen,
        "raw_path": (scope.get("raw_path") or b"").decode("latin-1"),
        "root_path": scope.get("root_path"),
        "method": request.method,
        "query": dict(request.query_params),
        "headers": keep,
        "python": sys.version.split()[0],
        "vercel": bool(os.environ.get("VERCEL")),
        "region": os.environ.get("VERCEL_REGION"),
        "file": os.path.abspath(__file__),
        "root_files": sorted(os.listdir(_ROOT))[:40],
        "routes": sorted({getattr(r, "path", "?") for r in app.routes}),
        "ai_configured": ai.configured(),
        "model": ai.model_name(),
    }
    if mode == "net":
        gd = f"{sources.GDELT_URL}?" + urlencode({"query": "الإمارات sourcelang:arabic", "mode": "artlist",
                                                  "format": "json", "maxrecords": "5", "timespan": "6h"})
        gn = f"{sources.GNEWS_URL}?" + urlencode({"q": "الإمارات when:24h", "hl": "ar", "gl": "AE", "ceid": "AE:ar"})
        gs = f"{sources.GNEWS_URL}?" + urlencode({"q": "site:wam.ae when:72h", "hl": "ar", "gl": "AE", "ceid": "AE:ar"})
        r = await asyncio.gather(_probe(gd), _probe(gn), _probe(gs))
        out["net"] = {"gdelt": r[0], "gnews": r[1], "gnews_site": r[2]}
    return out


async def _fallback(request: Request, rest: str):
    seen = "/" + rest.lstrip("/")
    q = request.query_params
    if "diag" in q:
        return _json(await _diag(request, seen, q.get("diag", "1")))
    last = seen.rstrip("/").rsplit("/", 1)[-1]
    if request.method == "POST":
        try:
            body = await request.json()
        except ValueError:
            return _json({"ok": False, "reason": "bad_request"}, 400)
        if not isinstance(body, dict):
            return _json({"ok": False, "reason": "bad_request"}, 400)
        op = last if last in ("translate", "analyze") else ("analyze" if "hours" in body else "translate")
        return _json(await (ai.analyze(body) if op == "analyze" else ai.translate(body)))
    op = last if last in ("news", "health") else ("news" if "hours" in q else "health")
    if op == "health":
        return await api_health()
    try:
        hours = int(q.get("hours", "24"))
    except ValueError:
        hours = 24
    return await api_news(hours)


@app.api_route("/api/{rest:path}", methods=["GET", "POST"])
async def api_fallback(rest: str, request: Request):
    return await _fallback(request, "api/" + rest)


if os.environ.get("VERCEL"):
    # on Vercel only API traffic reaches this function, so whatever path it is shown, treat it as an API call
    @app.api_route("/{rest:path}", methods=["GET", "POST"])
    async def vercel_fallback(rest: str, request: Request):
        return await _fallback(request, rest)


# Local development only: serve ./public. On Vercel the CDN serves public/ itself.
if not os.environ.get("VERCEL"):
    from fastapi.staticfiles import StaticFiles  # noqa: E402

    _public = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
    if os.path.isdir(_public):
        app.mount("/", StaticFiles(directory=_public, html=True), name="public")
