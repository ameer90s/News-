from __future__ import annotations

import asyncio
import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus, urlparse

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"

app = FastAPI(title="مرصد الإمارات الذكي", docs_url=None, redoc_url=None)
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.middleware("http")
async def cache_policy(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


UA = (
    "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 "
    "Chrome/140.0 Mobile Safari/537.36 UAE-Smart-Observatory/1.0"
)
ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
SPACE_RE = re.compile(r"\s+")

CATEGORY_LABELS = {
    "local": "محلية",
    "regional": "إقليمية",
    "international": "دولية",
}

SEARCH_QUERIES = {
    "local": [
        "الإمارات",
        "أبوظبي",
        "دبي الإمارات",
        "اقتصاد الإمارات",
    ],
    "regional": [
        "الخليج الشرق الأوسط",
        "إيران الخليج",
        "السعودية الخليج",
        "الشرق الأوسط النفط",
    ],
    "international": [
        "الاقتصاد العالمي الإمارات",
        "أسعار النفط العالم",
        "التجارة العالمية الخليج",
        "الولايات المتحدة الصين الأسواق",
    ],
}

DOMAIN_KEYWORDS = {
    "political": [
        "سياس", "حكومة", "دبلوماس", "رئيس", "وزير", "قمة", "مفاوض", "اتفاق",
        "عقوبات", "انتخاب", "أمم المتحدة", "مجلس الأمن", "سفارة", "علاقات",
    ],
    "economic": [
        "اقتصاد", "نفط", "غاز", "طاقة", "سوق", "أسهم", "استثمار", "تجارة",
        "بنك", "فائدة", "تضخم", "عملة", "نمو", "موانئ", "طيران", "شركة",
    ],
    "military": [
        "عسكري", "دفاع", "هجوم", "ضربة", "صاروخ", "مسيرة", "جيش", "قوات",
        "حرب", "اشتباك", "اعتراض", "تهديد", "أمني", "أمن", "صراع",
    ],
}

IMPACT_TERMS = {
    "high": [
        "الإمارات", "أبوظبي", "دبي", "الخليج", "مضيق هرمز", "إيران", "السعودية",
        "النفط", "الغاز", "حرب", "هجوم", "عقوبات", "الطيران", "الموانئ",
    ],
    "medium": [
        "الشرق الأوسط", "الفائدة", "التضخم", "الأسواق", "الصين", "الولايات المتحدة",
        "أوروبا", "التجارة", "الطاقة", "أوبك",
    ],
}

CACHE: dict[str, tuple[float, Any]] = {}
CACHE_SECONDS = 300


class NewsItem(BaseModel):
    id: str
    title: str
    source: str
    url: str
    published_at: str
    category: Literal["local", "regional", "international"]
    domain: Literal["political", "economic", "military"]
    uae_impact: int = Field(ge=0, le=100)
    importance: int = Field(ge=0, le=100)


class AnalysisRequest(BaseModel):
    items: list[NewsItem] = Field(default_factory=list, max_length=24)


def _contains_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(text or ""))


def _clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return SPACE_RE.sub(" ", text).strip()


def _safe_url(value: str) -> str:
    value = (value or "").strip()
    try:
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return value
    except Exception:
        pass
    return ""


def _parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _domain_for(title: str) -> str:
    scores = {key: 0 for key in DOMAIN_KEYWORDS}
    lower = title.lower()
    for domain, words in DOMAIN_KEYWORDS.items():
        scores[domain] = sum(1 for word in words if word in lower)
    if max(scores.values()) == 0:
        return "political"
    return max(scores, key=scores.get)


def _score(title: str, category: str) -> tuple[int, int]:
    impact = 22
    importance = 45
    if category == "local":
        impact += 24
        importance += 18
    elif category == "regional":
        impact += 16
        importance += 12
    else:
        impact += 6
        importance += 4

    lower = title.lower()
    high_hits = sum(1 for term in IMPACT_TERMS["high"] if term in lower)
    medium_hits = sum(1 for term in IMPACT_TERMS["medium"] if term in lower)
    impact += min(32, high_hits * 8 + medium_hits * 4)
    importance += min(30, high_hits * 6 + medium_hits * 3)

    domain = _domain_for(title)
    if domain == "military":
        impact += 8
        importance += 6
    elif domain == "economic":
        impact += 4
        importance += 4

    return min(100, impact), min(100, importance)


def _extract_source(item: ET.Element) -> str:
    source_node = item.find("source")
    if source_node is not None and source_node.text:
        return _clean_text(source_node.text)
    return "Google News"


def _extract_link(item: ET.Element) -> str:
    link_node = item.find("link")
    if link_node is not None and link_node.text:
        return _safe_url(link_node.text)
    return ""


async def _fetch_google_rss(client: httpx.AsyncClient, query: str, category: str) -> list[NewsItem]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=ar&gl=AE&ceid=AE:ar"
    )
    response = await client.get(url, headers={"User-Agent": UA}, timeout=9.0)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    results: list[NewsItem] = []
    for item in root.findall("./channel/item")[:14]:
        title = _clean_text(item.findtext("title") or "")
        source = _extract_source(item)
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].strip()
        # واجهة المرصد عربية فقط. أي عنوان غير عربي لا يدخل الواجهة.
        if not title or not _contains_arabic(title):
            continue
        link = _extract_link(item)
        if not link:
            continue
        published = _parse_date(item.findtext("pubDate"))
        impact, importance = _score(title, category)
        results.append(
            NewsItem(
                id=str(abs(hash((title, link))))[:18],
                title=title,
                source=source or "مصدر إخباري",
                url=link,
                published_at=published.isoformat(),
                category=category,
                domain=_domain_for(title),
                uae_impact=impact,
                importance=importance,
            )
        )
    return results


async def _collect_news(hours: int) -> list[NewsItem]:
    cache_key = f"news:{hours}"
    now = time.time()
    cached = CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1]

    tasks = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for category, queries in SEARCH_QUERIES.items():
            for query in queries:
                tasks.append(_fetch_google_rss(client, query, category))
        batches = await asyncio.gather(*tasks, return_exceptions=True)

    cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
    merged: list[NewsItem] = []
    seen: set[str] = set()
    for batch in batches:
        if isinstance(batch, Exception):
            continue
        for item in batch:
            if _parse_date(item.published_at).timestamp() < cutoff:
                continue
            normalized = re.sub(r"\W+", "", item.title).lower()[:90]
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(item)

    merged.sort(key=lambda x: (x.importance, x.uae_impact, x.published_at), reverse=True)
    merged = merged[:48]
    if merged:
        CACHE[cache_key] = (now, merged)
    return merged


def _local_analysis(items: list[NewsItem]) -> dict[str, Any]:
    if not items:
        return {
            "mode": "local",
            "headline": "لا توجد أخبار كافية لبناء الصورة الكبرى الآن",
            "summary": "سيعيد المرصد المحاولة تلقائيًا عند التحديث التالي.",
            "domains": {
                "political": "لا توجد بيانات سياسية كافية حاليًا.",
                "economic": "لا توجد بيانات اقتصادية كافية حاليًا.",
                "military": "لا توجد بيانات عسكرية كافية حاليًا.",
            },
        }

    top = sorted(items, key=lambda x: (x.importance, x.uae_impact), reverse=True)[:5]
    headline = top[0].title
    categories = {CATEGORY_LABELS[x.category] for x in top}
    summary = (
        f"تتركز الصورة الحالية حول {headline}. "
        f"وتتقاطع التطورات مع أخبار {' و'.join(sorted(categories))}، "
        "مع أولوية لمراقبة انعكاساتها المحتملة على الإمارات والطاقة والأسواق والحركة الإقليمية."
    )

    domains: dict[str, str] = {}
    labels = {"political": "سياسي", "economic": "اقتصادي", "military": "عسكري"}
    for domain in ("political", "economic", "military"):
        domain_items = [x for x in items if x.domain == domain]
        if domain_items:
            lead = max(domain_items, key=lambda x: (x.importance, x.uae_impact))
            domains[domain] = (
                f"يركز المسار {labels[domain]} على: {lead.title} "
                f"مع تأثير تقديري على الإمارات يبلغ {lead.uae_impact}%."
            )
        else:
            domains[domain] = f"لا توجد إشارات {labels[domain]} قوية ضمن نافذة الأخبار الحالية."

    return {"mode": "local", "headline": headline, "summary": summary, "domains": domains}


async def _gemini_analysis(items: list[NewsItem]) -> dict[str, Any] | None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not items:
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip() or "gemini-flash-latest"
    payload_items = [
        {
            "title": x.title,
            "category": CATEGORY_LABELS[x.category],
            "domain": x.domain,
            "impact": x.uae_impact,
            "source": x.source,
        }
        for x in sorted(items, key=lambda x: x.importance, reverse=True)[:12]
    ]
    prompt = (
        "أنت محلل أخبار لمرصد إماراتي. حلل الأخبار التالية بالعربية الفصحى المختصرة. "
        "لا تخترع وقائع ولا تضف معلومات غير موجودة في الأخبار. ركز على التأثير المحتمل على الإمارات. "
        "أعد JSON فقط بدون Markdown بهذه المفاتيح: headline, summary, political, economic, military. "
        "headline جملة قصيرة، summary من 2 إلى 3 جمل، وبقية الحقول جملة أو جملتان.\n\n"
        + json.dumps(payload_items, ensure_ascii=False)
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=body,
                timeout=12.0,
            )
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        required = ["headline", "summary", "political", "economic", "military"]
        if not all(isinstance(parsed.get(k), str) and parsed[k].strip() for k in required):
            return None
        if not all(_contains_arabic(parsed[k]) for k in required):
            return None
        return {
            "mode": "ai",
            "headline": parsed["headline"].strip(),
            "summary": parsed["summary"].strip(),
            "domains": {
                "political": parsed["political"].strip(),
                "economic": parsed["economic"].strip(),
                "military": parsed["military"].strip(),
            },
        }
    except Exception:
        return None


@app.get("/")
async def home():
    return FileResponse(BASE_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
async def service_worker():
    return FileResponse(BASE_DIR / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(BASE_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/favicon.ico")
async def favicon():
    path = ASSETS_DIR / "favicon.svg"
    if path.exists():
        return FileResponse(path, media_type="image/svg+xml")
    return Response(status_code=204)


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "entrypoint": "main.py",
        "app": "main:app",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/news")
async def news(hours: int = Query(24, ge=6, le=72)):
    try:
        items = await asyncio.wait_for(_collect_news(hours), timeout=15.0)
    except Exception:
        items = []
    return {
        "ok": bool(items),
        "hours": hours,
        "count": len(items),
        "items": [x.model_dump() for x in items],
        "message": "" if items else "تعذر جلب الأخبار العربية الآن. حاول التحديث بعد قليل.",
    }


@app.post("/api/analysis")
async def analysis(request: AnalysisRequest):
    items = request.items
    ai = await _gemini_analysis(items)
    if ai:
        return ai
    return _local_analysis(items)


@app.exception_handler(Exception)
async def unhandled_exception(_, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"ok": False, "message": "حدث خطأ مؤقت في الخادم."},
        headers={"Cache-Control": "no-store"},
    )
