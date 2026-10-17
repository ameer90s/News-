from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from math import exp, log2
from typing import Iterable
from urllib.parse import urlparse
import os
import re
import requests

GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

TOPIC_QUERIES = {
    "political": '(government OR diplomacy OR election OR sanctions OR treaty OR parliament OR minister OR president OR "foreign policy" OR negotiations OR ceasefire OR summit)',
    "economic": '(economy OR inflation OR "interest rate" OR GDP OR oil OR gas OR trade OR investment OR markets OR banking OR shipping OR currency OR tariff)',
    "military": '(military OR defence OR defense OR missile OR drone OR airstrike OR army OR navy OR "air force" OR conflict OR ceasefire OR "security forces")',
}

SCOPE_QUERIES = {
    "uae": '("United Arab Emirates" OR UAE OR "Abu Dhabi" OR Dubai OR Sharjah)',
    "region": '("Middle East" OR GCC OR Gulf OR Saudi OR Qatar OR Kuwait OR Bahrain OR Oman OR Yemen OR Iraq OR Iran OR Israel OR Palestine OR Lebanon OR Syria OR Jordan OR Egypt OR Turkey)',
    "world": '',
}

TOPIC_LABELS = {"political": "سياسي", "economic": "اقتصادي", "military": "عسكري"}
SCOPE_LABELS = {"uae": "الإمارات", "region": "الشرق الأوسط", "world": "العالم"}

SOURCE_WEIGHTS = {
    "wam.ae": 1.00,
    "reuters.com": 1.00,
    "apnews.com": 0.98,
    "bbc.com": 0.95,
    "ft.com": 0.95,
    "bloomberg.com": 0.95,
    "aljazeera.com": 0.92,
    "cnbc.com": 0.90,
    "cnn.com": 0.88,
    "france24.com": 0.88,
    "dw.com": 0.88,
    "thenationalnews.com": 0.88,
    "gulfnews.com": 0.84,
    "khaleejtimes.com": 0.82,
    "arabnews.com": 0.84,
}

HIGH_IMPACT_TERMS = {
    "political": ["sanction", "treaty", "election", "cabinet", "diplom", "ceasefire", "negotiat", "summit"],
    "economic": ["oil", "gas", "inflation", "interest rate", "tariff", "shipping", "hormuz", "market", "bank", "investment", "trade"],
    "military": ["missile", "drone", "airstrike", "ceasefire", "navy", "air force", "attack", "conflict", "hormuz"],
}

UAE_TERMS = ["uae", "united arab emirates", "abu dhabi", "dubai", "sharjah", "gcc", "gulf", "hormuz", "oil", "gas", "shipping", "airspace", "trade", "port", "aviation", "investment", "dirham"]

@dataclass
class Article:
    title: str
    url: str
    domain: str
    seen_at: str
    source_country: str
    topic: str
    scope: str

    def to_dict(self):
        return asdict(self)


def _domain(url: str, given: str | None = None) -> str:
    if given:
        g = given.lower().replace("www.", "").strip()
        if g:
            return g
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _parse_seen(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    value = str(value).strip()
    formats = ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ")
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def fetch_gdelt(topic: str, scope: str, hours: int = 24, maxrecords: int = 60) -> list[Article]:
    query = f"{TOPIC_QUERIES[topic]} {SCOPE_QUERIES[scope]}".strip()
    params = {
        "query": query,
        "mode": "ArtList",
        "maxrecords": max(10, min(int(maxrecords), 100)),
        "format": "json",
        "sort": "HybridRel",
        "timespan": f"{max(1, int(hours))}H",
    }
    headers = {"User-Agent": "Strategic-Newsroom/1.0"}
    timeout = int(os.getenv("REQUEST_TIMEOUT", "18"))
    r = requests.get(GDELT_ENDPOINT, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    rows = r.json().get("articles", []) or []
    out, seen = [], set()
    for row in rows:
        url = str(row.get("url", "")).strip()
        title = re.sub(r"\s+", " ", str(row.get("title", "")).strip())
        if not url or not title or url in seen:
            continue
        seen.add(url)
        out.append(Article(
            title=title,
            url=url,
            domain=_domain(url, row.get("domain")),
            seen_at=str(row.get("seendate", "")),
            source_country=str(row.get("sourcecountry", "")),
            topic=topic,
            scope=scope,
        ))
    return out


def fetch_matrix(hours: int = 24, maxrecords: int = 60) -> list[Article]:
    all_rows: list[Article] = []
    for topic in TOPIC_QUERIES:
        for scope in SCOPE_QUERIES:
            try:
                all_rows.extend(fetch_gdelt(topic, scope, hours, maxrecords))
            except Exception:
                continue
    by_url: dict[str, Article] = {}
    for a in all_rows:
        if a.url not in by_url:
            by_url[a.url] = a
        else:
            old = by_url[a.url]
            if a.scope not in old.scope.split(" | "):
                old.scope += f" | {a.scope}"
            if a.topic not in old.topic.split(" | "):
                old.topic += f" | {a.topic}"
    return list(by_url.values())


def normalize_title(title: str) -> str:
    text = title.lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^\w\u0600-\u06FF\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    stop = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "from", "as", "at", "by", "في", "من", "إلى", "على", "عن", "مع", "و", "أو", "بعد", "قبل"}
    return " ".join(w for w in text.split() if w not in stop and len(w) > 1)


def title_similarity(a: str, b: str) -> float:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    sa, sb = set(na.split()), set(nb.split())
    j = len(sa & sb) / max(1, len(sa | sb))
    return 0.62 * seq + 0.38 * j


def cluster_articles(articles: list[Article], threshold: float = 0.58) -> list[list[Article]]:
    clusters: list[list[Article]] = []
    for article in sorted(articles, key=lambda x: _parse_seen(x.seen_at), reverse=True):
        best_i, best_sim = None, 0.0
        for i, cluster in enumerate(clusters):
            sim = max(title_similarity(article.title, r.title) for r in cluster[:3])
            if sim > best_sim:
                best_i, best_sim = i, sim
        if best_i is not None and best_sim >= threshold:
            clusters[best_i].append(article)
        else:
            clusters.append([article])
    return clusters


def source_weight(domain: str) -> float:
    domain = domain.lower()
    for known, weight in SOURCE_WEIGHTS.items():
        if domain == known or domain.endswith('.' + known):
            return weight
    return 0.62


def uae_score(text: str) -> float:
    lower = text.lower()
    matches = sum(1 for t in UAE_TERMS if t in lower)
    if "uae" in lower or "united arab emirates" in lower or "abu dhabi" in lower:
        matches += 2
    return min(1.0, matches / 5.0)


def impact_score(topic: str, text: str) -> float:
    lower = text.lower()
    terms = HIGH_IMPACT_TERMS.get(topic, [])
    hits = sum(1 for t in terms if t in lower)
    return min(1.0, hits / 4.0)


def event_record(cluster: list[Article]) -> dict:
    cluster = sorted(cluster, key=lambda a: _parse_seen(a.seen_at), reverse=True)
    lead = max(cluster, key=lambda a: source_weight(a.domain))
    domains = sorted({a.domain for a in cluster if a.domain})
    scopes = sorted({SCOPE_LABELS[s.strip()] if s.strip() in SCOPE_LABELS else s.strip() for a in cluster for s in a.scope.split(" | ") if s.strip()})
    topic_key = cluster[0].topic.split(" | ")[0]

    now = datetime.now(timezone.utc)
    newest = max(_parse_seen(a.seen_at) for a in cluster)
    age_h = max(0.0, (now - newest).total_seconds() / 3600.0)
    recency = exp(-age_h / 22.0)
    coverage = min(1.0, log2(len(domains) + 1) / 3.0)
    authority = max(source_weight(a.domain) for a in cluster)
    all_titles = " ".join(a.title for a in cluster)
    impact = impact_score(topic_key, all_titles)
    uae = uae_score(all_titles)
    score = round((0.28 * coverage + 0.22 * recency + 0.22 * authority + 0.18 * impact + 0.10 * uae) * 100, 1)
    strong = sum(1 for d in domains if source_weight(d) >= 0.90)
    confidence = "مرتفع" if len(domains) >= 4 and strong >= 1 else ("متوسط" if len(domains) >= 2 or strong >= 1 else "أولي")

    return {
        "title": lead.title,
        "topic": topic_key,
        "topic_label": TOPIC_LABELS.get(topic_key, topic_key),
        "score": score,
        "confidence": confidence,
        "source_count": len(domains),
        "sources": domains,
        "scopes": scopes,
        "newest": newest.isoformat(),
        "uae_impact": round(uae * 100),
        "articles": [a.to_dict() for a in cluster],
    }


def rank_events(articles: list[Article], topic: str | None = None, top_n: int = 12) -> list[dict]:
    subset = [a for a in articles if (not topic or topic in a.topic.split(" | "))]
    clusters = cluster_articles(subset)
    events = [event_record(c) for c in clusters]
    events.sort(key=lambda e: (e["score"], e["source_count"], e["newest"]), reverse=True)
    return events[:top_n]
