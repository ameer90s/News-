"""FastAPI entrypoint (Vercel serves this file as /api/index; vercel.json rewrites /api/* to it)."""
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
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


@app.post("/api/enrich")
async def api_enrich(request: Request):
    try:
        body = await request.json()
    except ValueError:
        return _json({"ok": False, "reason": "bad_request"}, 400)
    return _json(await ai.enrich(body))


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


_AI_PROBE_AT = 0.0


def _gemini_http(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    """One raw Gemini call for diagnostics. Returns (http_status, small summary). Never includes the key."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    req = urllib.request.Request(
        url, method=method, data=None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read(600_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raw = e.read(4000).decode("utf-8", "replace")
        try:
            err = json.loads(raw).get("error")
        except (ValueError, AttributeError):
            err = None
        if not isinstance(err, dict):
            err = {"message": raw[:160]}
        return e.code, {"status": err.get("status"), "message": str(err.get("message", ""))[:220]}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": type(e).__name__, "detail": str(e)[:120]}


def _ai_probe() -> dict:
    out: dict = {"configured": ai.configured(), "model": ai.model_name(), "model_from_env": bool(os.environ.get("GEMINI_MODEL"))}
    if not ai.configured():
        out["result"] = "GEMINI_API_KEY is not set"
        return out
    t0 = time.monotonic()
    code, data = _gemini_http("POST", f"{ai.GEMINI_BASE}/models/{ai.model_name()}:generateContent", {
        "contents": [{"role": "user", "parts": [{"text": "اكتب كلمة واحدة: جاهز"}]}],
        "generationConfig": {"maxOutputTokens": 16, "temperature": 0}})
    out["http"] = code
    out["ms"] = int((time.monotonic() - t0) * 1000)
    if code == 200:
        out["result"] = "ok"
        cands = data.get("candidates") or []
        out["finish"] = (cands[0].get("finishReason") if cands else None)
    else:
        out["result"] = data
    if code == 404:  # wrong model name: list what this key can actually use
        c2, d2 = _gemini_http("GET", f"{ai.GEMINI_BASE}/models?pageSize=200")
        if c2 == 200:
            names = [m.get("name", "").removeprefix("models/") for m in d2.get("models", [])
                     if "generateContent" in (m.get("supportedGenerationMethods") or [])]
            out["usable_models"] = [n for n in names if "gemini" in n and "flash" in n][:14]
    return out


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
    if mode == "ai":
        global _AI_PROBE_AT
        if time.monotonic() - _AI_PROBE_AT < 15:      # a public URL that spends API quota: allow one probe per 15 s
            out["ai"] = {"result": "wait 15 seconds between probes"}
        else:
            _AI_PROBE_AT = time.monotonic()
            out["ai"] = await asyncio.to_thread(_ai_probe)
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
        op = last if last in ("enrich", "translate", "analyze") else (
            "enrich" if "translate" in body else ("analyze" if "hours" in body else "translate"))
        fn = {"enrich": ai.enrich, "analyze": ai.analyze, "translate": ai.translate}[op]
        return _json(await fn(body))
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
