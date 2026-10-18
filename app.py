from __future__ import annotations

import asyncio
import html
import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus, urlparse
import xml.etree.ElementTree as ET

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"

app = FastAPI(title="مرصد الإمارات الذكي", docs_url=None, redoc_url=None)
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.middleware("http")
async def no_cache_api(request, call_next):
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

CATEGORY_QUERIES = {
    "local": "الإمارات OR أبوظبي OR دبي OR الشارقة OR عجمان OR الفجيرة OR رأس الخيمة OR أم القيوين",
    "regional": "الخليج OR السعودية OR إيران OR الشرق الأوسط OR قطر OR عمان OR البحرين OR الكويت OR اليمن OR العراق",
    "international": "الإمارات (النفط OR الاقتصاد العالمي OR الأسواق العالمية OR التجارة OR الصين OR الولايات المتحدة OR أوروبا OR الطاقة)",
}

DOMAIN_KEYWORDS = {
    "political": [
        "سياس", "حكومة", "دبلوماس", "وزير", "رئيس", "قمة", "مفاوض", "اتفاق",
        "عقوبات", "مجلس الأمن", "أمم المتحدة", "انتخاب", "علاقات", "سفارة",
    ],
    "economic": [
        "اقتصاد", "نفط", "غاز", "سوق", "أسهم", "استثمار", "تجارة", "بنك", "فائدة",
        "تضخم", "طاقة", "شركة", "تمويل", "عملة", "نمو", "صادرات", "واردات", "موانئ",
    ],
    "military": [
        "عسكري", "دفاع", "هجوم", "ضربة", "صاروخ", "طائرة مسيرة", "مسيرة", "جيش",
        "قوات", "حرب", "أمن", "مناورة", "اعتراض", "تهديد", "صراع", "اشتباك",
    ],
}

HIGH_IMPACT_TERMS = [
    "الإمارات", "أبوظبي", "دبي", "الخليج", "النفط", "الغاز", "مضيق هرمز", "إيران",
    "السعودية", "الحرب", "هجوم", "عقوبات", "الفائدة", "التجارة", "الطيران", "الموانئ",
]


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


def _strip_source_suffix(title: str, source: str) -> str:
    title = _clean_text(title)
    source = _clean_text(source)
    if source and title.endswith(f" - {source}"):
        title = title[: -(len(source) + 3)].strip()
    return title


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


def _classify_domain(title: str) -> Literal["political", "economic", "military"]:
    lowered = title.lower()
    scores = {
        name: sum(1 for kw in kws if kw in lowered)
        for name, kws in DOMAIN_KEYWORDS.items()
    }
    if max(scores.values(), default=0) == 0:
        return "political"
    return max(scores, key=scores.get)  # type: ignore[return-value]


def _impact_and_importance(title: str, category: str, published: datetime) -> tuple[int, int]:
    lowered = title.lower()
    hits = sum(1 for kw in HIGH_IMPACT_TERMS if kw.lower() in lowered)
    domain = _classify_domain(title)
    domain_hits = sum(1 for kw in DOMAIN_KEYWORDS[domain] if kw in lowered)
    hours_old = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
    recency = max(0, 24 - min(24, int(hours_old)))

    category_base = {"local": 48, "regional": 42, "international": 34}.get(category, 34)
    impact = category_base + hits * 8 + domain_hits * 3
    importance = 44 + hits * 7 + domain_hits * 3 + int(recency * 0.8)
    if "الإمارات" in title or "أبوظبي" in title or "دبي" in title:
        impact += 14
        importance += 10
    return min(95, max(12, impact)), min(98, max(20, importance))


def _item_id(title: str, url: str) -> str:
    import hashlib
    return hashlib.sha1(f"{title}|{url}".encode("utf-8")).hexdigest()[:14]


def _normalize_title(title: str) -> str:
    title = re.sub(r"[^\w\u0600-\u06FF]+", " ", title.lower(), flags=re.UNICODE)
    return SPACE_RE.sub(" ", title).strip()


async def _fetch_google_rss(client: httpx.AsyncClient, category: str, hours: int) -> list[NewsItem]:
    query = f"({CATEGORY_QUERIES[category]}) when:{hours}h"
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=ar&gl=AE&ceid=AE:ar"
    )
    response = await client.get(url, timeout=7.0, follow_redirects=True)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items: list[NewsItem] = []
    for node in root.findall(".//item")[:30]:
        raw_title = _clean_text(node.findtext("title") or "")
        link = _safe_url(node.findtext("link") or "")
        pub_date = node.findtext("pubDate")
        source_node = node.find("source")
        source = _clean_text(source_node.text if source_node is not None and source_node.text else "Google News")
        title = _strip_source_suffix(raw_title, source)
        # The public interface must never show an English headline.
        if not title or not _contains_arabic(title) or not link:
            continue
        published = _parse_date(pub_date)
        impact, importance = _impact_and_importance(title, category, published)
        items.append(
            NewsItem(
                id=_item_id(title, link),
                title=title,
                source=source or "Google News",
                url=link,
                published_at=published.isoformat(),
                category=category,  # type: ignore[arg-type]
                domain=_classify_domain(title),
                uae_impact=impact,
                importance=importance,
            )
        )
    return items


async def _fetch_gdelt(client: httpx.AsyncClient, category: str, hours: int) -> list[NewsItem]:
    query = CATEGORY_QUERIES[category]
    timespan = f"{hours}h"
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?"
        f"query={quote_plus(query)}&mode=ArtList&maxrecords=25&format=json&timespan={timespan}&sort=HybridRel"
    )
    response = await client.get(url, timeout=7.0, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    items: list[NewsItem] = []
    for row in (payload.get("articles") or [])[:25]:
        title = _clean_text(row.get("title") or "")
        link = _safe_url(row.get("url") or "")
        if not title or not _contains_arabic(title) or not link:
            continue
        published = _parse_date(row.get("seendate"))
        source = _clean_text(row.get("domain") or "GDELT")
        impact, importance = _impact_and_importance(title, category, published)
        items.append(
            NewsItem(
                id=_item_id(title, link),
                title=title,
                source=source or "GDELT",
                url=link,
                published_at=published.isoformat(),
                category=category,  # type: ignore[arg-type]
                domain=_classify_domain(title),
                uae_impact=impact,
                importance=importance,
            )
        )
    return items


async def _collect_category(client: httpx.AsyncClient, category: str, hours: int) -> tuple[list[NewsItem], list[str]]:
    errors: list[str] = []
    google: list[NewsItem] = []
    gdelt: list[NewsItem] = []
    try:
        google = await _fetch_google_rss(client, category, hours)
    except Exception as exc:
        errors.append(f"google:{category}:{type(exc).__name__}")
    if len(google) < 4:
        try:
            gdelt = await _fetch_gdelt(client, category, hours)
        except Exception as exc:
            errors.append(f"gdelt:{category}:{type(exc).__name__}")
    return google + gdelt, errors


def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    result: list[NewsItem] = []
    for item in sorted(items, key=lambda x: (x.importance, x.published_at), reverse=True):
        key = _normalize_title(item.title)
        if not key or key in seen:
            continue
        # Also suppress very similar long titles by prefix.
        prefix = key[:70]
        if any(existing.startswith(prefix) or prefix.startswith(existing[:70]) for existing in seen if len(prefix) > 35):
            continue
        seen.add(key)
        result.append(item)
    return result


def _domain_summary(items: list[NewsItem], domain: str) -> dict[str, Any]:
    subset = [x for x in items if x.domain == domain]
    if not subset:
        return {"impact": 0, "level": "منخفض"}
    impact = max(x.uae_impact for x in subset)
    level = "منخفض" if impact <= 33 else "متوسط" if impact <= 66 else "مرتفع"
    return {"impact": impact, "level": level}


def _local_analysis(items: list[NewsItem]) -> dict[str, Any]:
    top = sorted(items, key=lambda x: x.importance, reverse=True)
    top_titles = [x.title for x in top[:3]]
    if top_titles:
        title = "تطورات متقاربة تستحق المتابعة خلال الساعات المقبلة"
        summary = "تتركز الصورة الحالية حول " + "، ثم ".join(top_titles[:2]) + "."
    else:
        title = "لا توجد بيانات كافية لبناء الصورة الكبرى الآن"
        summary = "سيُعاد بناء التحليل تلقائيًا عند توفر أخبار موثوقة بالعربية."

    domain_names = {"political": "السياسي", "economic": "الاقتصادي", "military": "العسكري"}
    domains: dict[str, Any] = {}
    for domain, ar_name in domain_names.items():
        subset = [x for x in top if x.domain == domain]
        if subset:
            domains[domain] = {
                "summary": f"أبرز ما يلفت في المسار {ar_name}: {subset[0].title}",
            }
        else:
            domains[domain] = {"summary": f"لا توجد إشارات {ar_name} كافية ضمن الأخبار الحالية."}
    return {
        "source": "local",
        "big_picture": {"title": title, "summary": summary},
        "domains": domains,
    }


async def _gemini_analysis(items: list[NewsItem]) -> dict[str, Any] | None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not items:
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
    compact = [
        {
            "title": x.title,
            "category": x.category,
            "domain": x.domain,
            "uae_impact": x.uae_impact,
            "source": x.source,
        }
        for x in sorted(items, key=lambda x: x.importance, reverse=True)[:14]
    ]
    prompt = (
        "أنت محلل أخبار لدولة الإمارات. اعتمد حصراً على العناوين والبيانات المرفقة ولا تضف وقائع غير موجودة. "
        "اكتب بالعربية الواضحة والمختصرة. اربط التطورات بأثرها المحتمل على الإمارات بدون مبالغة. "
        "أعد JSON فقط بالمفاتيح التالية: big_picture.title, big_picture.summary, "
        "domains.political.summary, domains.economic.summary, domains.military.summary. "
        "العنوان لا يزيد عن 14 كلمة، والملخص 45-75 كلمة، وكل ملخص قطاعي 20-40 كلمة.\n\n"
        + json.dumps(compact, ensure_ascii=False)
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 900,
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote_plus(model)}:generateContent"
    try:
        async with httpx.AsyncClient(headers={"Content-Type": "application/json"}) as client:
            response = await client.post(url, params={"key": api_key}, json=payload, timeout=14.0)
            response.raise_for_status()
            data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        required = parsed.get("big_picture", {})
        domains = parsed.get("domains", {})
        if not _contains_arabic(str(required.get("title", ""))):
            return None
        result = {
            "source": "gemini",
            "model": model,
            "big_picture": {
                "title": _clean_text(str(required.get("title", "")))[:220],
                "summary": _clean_text(str(required.get("summary", "")))[:900],
            },
            "domains": {},
        }
        for domain in ("political", "economic", "military"):
            summary = _clean_text(str((domains.get(domain) or {}).get("summary", "")))[:500]
            if not _contains_arabic(summary):
                return None
            result["domains"][domain] = {"summary": summary}
        return result
    except Exception:
        return None


@app.get("/")
async def home() -> FileResponse:
    return FileResponse(BASE_DIR / "index.html", media_type="text/html; charset=utf-8")


@app.get("/sw.js")
async def service_worker() -> FileResponse:
    return FileResponse(BASE_DIR / "sw.js", media_type="application/javascript; charset=utf-8", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/manifest.webmanifest")
async def manifest() -> FileResponse:
    return FileResponse(BASE_DIR / "manifest.webmanifest", media_type="application/manifest+json", headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "app": "uae-smart-observatory",
        "version": "1.0.0-fresh",
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY", "").strip()),
    }


@app.get("/api/news")
async def news(hours: int = Query(default=24, ge=6, le=72)) -> dict[str, Any]:
    allowed = min((6, 12, 24, 48, 72), key=lambda x: abs(x - hours))
    async with httpx.AsyncClient(headers={"User-Agent": UA, "Accept-Language": "ar-AE,ar;q=0.9,en;q=0.5"}) as client:
        results = await asyncio.gather(*[_collect_category(client, cat, allowed) for cat in CATEGORY_QUERIES])
    all_items: list[NewsItem] = []
    errors: list[str] = []
    for category_items, category_errors in results:
        all_items.extend(category_items)
        errors.extend(category_errors)
    all_items = _dedupe(all_items)[:30]
    generated = datetime.now(timezone.utc).isoformat()
    return {
        "ok": True,
        "hours": allowed,
        "generated_at": generated,
        "items": [x.model_dump() for x in all_items],
        "impact": {
            "political": _domain_summary(all_items, "political"),
            "economic": _domain_summary(all_items, "economic"),
            "military": _domain_summary(all_items, "military"),
        },
        "sources": {"google_news": True, "gdelt_fallback": True},
        "errors": errors,
    }


@app.post("/api/analysis")
async def analysis(payload: AnalysisRequest) -> dict[str, Any]:
    items = payload.items[:24]
    gemini = await _gemini_analysis(items)
    if gemini:
        return {"ok": True, **gemini}
    return {"ok": True, **_local_analysis(items)}


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)
