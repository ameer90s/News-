from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from pathlib import Path
from datetime import datetime, timezone, timedelta
import time
import os

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Strategic Newsroom UAE")
CACHE = {"hours": None, "payload": None, "updated_at": None}
# Last payload that actually contained news, per time window: {hours: (fetched_at_epoch, payload)}
GOOD = {}
FRESH_SECONDS = 600        # /api/dashboard reuses news younger than 10 minutes
MIN_REFRESH_SECONDS = 30   # /api/refresh within 30 s reuses the same result (protects the news sources)

# ---- Flat-file frontend routes (all files live beside main.py) ----
@app.get("/")
def root():
    return FileResponse(BASE_DIR / "index.html", media_type="text/html; charset=utf-8")

@app.get("/styles.css")
def styles():
    return FileResponse(BASE_DIR / "styles.css", media_type="text/css; charset=utf-8")

@app.get("/app.js")
def app_js():
    return FileResponse(BASE_DIR / "app.js", media_type="application/javascript; charset=utf-8")

@app.get("/background.webp")
def background():
    return FileResponse(BASE_DIR / "background.webp", media_type="image/webp")

@app.get("/icon.svg")
def icon():
    return FileResponse(BASE_DIR / "icon.svg", media_type="image/svg+xml")

@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(BASE_DIR / "manifest.webmanifest", media_type="application/manifest+json")

@app.get("/sw.js")
def service_worker():
    return FileResponse(BASE_DIR / "sw.js", media_type="application/javascript; charset=utf-8")

@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "deployment": "vercel-mobile-flat",
        "variables_required": False,
        "updated_at": CACHE.get("updated_at"),
        "last_sources": (CACHE.get("payload") or {}).get("meta", {}).get("sources"),
    }


def _news_engine(hours: int):
    # Heavy imports are deliberately deferred until an API request so Vercel can
    # always import main.py and serve the UI/health endpoint first.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from dataclasses import dataclass, asdict
    from difflib import SequenceMatcher
    from email.utils import parsedate_to_datetime
    from functools import lru_cache
    from math import exp, log2
    from urllib.parse import urlencode, urlparse
    from urllib.request import Request, urlopen
    import xml.etree.ElementTree as ET
    import json
    import re

    started = time.monotonic()
    hours = max(1, min(int(hours), 168))
    now_utc = datetime.now(timezone.utc)
    since = now_utc - timedelta(hours=hours)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; UAE-Smart-Monitor/2.2)",
        "Accept": "application/rss+xml, application/xml;q=0.9, application/json;q=0.8, */*;q=0.5",
    }
    per_query = 30  # items kept per search (keeps clustering fast)

    # ---- Source 1 (main): Google News RSS search — free, no key, no 5-second limit.
    # Queries are short on purpose: Google ignores the tail of very long queries.
    gn_topics = {
        "political": '(diplomacy OR government OR minister OR president OR sanctions OR summit OR talks OR election)',
        "economic": '(economy OR oil OR trade OR investment OR markets OR inflation OR tariff OR shipping)',
        "military": '(military OR missile OR drone OR airstrike OR defense OR army OR navy OR attack)',
    }
    gn_scopes = {
        "uae": '(UAE OR "United Arab Emirates" OR "Abu Dhabi" OR Dubai)',
        "region": '("Middle East" OR Gulf OR Saudi OR Iran OR Israel OR Gaza OR Yemen OR Iraq)',
        "world": "",
    }
    when = f"{hours}h" if hours <= 48 else f"{-(-hours // 24)}d"

    # ---- Source 2 (fallback only): GDELT. It allows ONE request every 5 seconds per IP and
    # blocks bursts, so the old 9-parallel-requests approach always came back empty.
    gdelt_endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"
    gdelt_query = '("United Arab Emirates" OR UAE OR "Abu Dhabi" OR Dubai OR Gulf OR "Middle East" OR Saudi OR Iran OR Israel)'

    topic_labels = {"political": "سياسي", "economic": "اقتصادي", "military": "عسكري"}
    scope_labels = {"uae": "الإمارات", "region": "الشرق الأوسط", "world": "العالم"}
    source_weights = {
        "wam.ae": 1.0, "reuters.com": 1.0, "apnews.com": 0.98, "bbc.com": 0.95, "bbc.co.uk": 0.95,
        "ft.com": 0.95, "bloomberg.com": 0.95, "aljazeera.com": 0.92, "cnbc.com": 0.90,
        "cnn.com": 0.88, "france24.com": 0.88, "dw.com": 0.88, "thenationalnews.com": 0.88,
        "gulfnews.com": 0.84, "khaleejtimes.com": 0.82, "arabnews.com": 0.84,
    }
    impact_terms = {
        "political": ["sanction", "treaty", "election", "cabinet", "diplom", "ceasefire", "negotiat", "summit"],
        "economic": ["oil", "gas", "inflation", "interest rate", "tariff", "shipping", "hormuz", "market", "bank", "investment", "trade"],
        "military": ["missile", "drone", "airstrike", "ceasefire", "navy", "air force", "attack", "conflict", "hormuz"],
    }
    uae_terms = ["uae", "united arab emirates", "abu dhabi", "dubai", "sharjah", "gcc", "gulf", "hormuz", "oil", "gas", "shipping", "airspace", "trade", "port", "aviation", "investment", "dirham"]

    # Local classifiers (used for GDELT fallback articles, which come from one combined query)
    topic_patterns = {
        "political": re.compile(r"\b(diplomat\w*|government|minister\w*|president\w*|sanction\w*|summit|talks|election\w*|parliament|treaty|ceasefire|negotiat\w*|cabinet|foreign policy)\b", re.I),
        "economic": re.compile(r"\b(econom\w*|oil|gas|trade|invest\w*|market\w*|inflation|tariff\w*|shipping|bank\w*|gdp|currency|stocks?|opec|energy)\b", re.I),
        "military": re.compile(r"\b(military|missiles?|drones?|airstrikes?|defen[cs]e|army|navy|air force|attacks?|strikes?|troops|conflict|war)\b", re.I),
    }
    uae_pattern = re.compile(r"\b(uae|united arab emirates|emirati|abu dhabi|dubai|sharjah)\b", re.I)
    region_pattern = re.compile(r"\b(middle east|gulf|gcc|saudi\w*|qatar\w*|kuwait\w*|bahrain\w*|oman\w*|yemen\w*|iraq\w*|iran\w*|israel\w*|gaza|palestin\w*|lebanon|syria\w*|jordan\w*|egypt\w*|turk\w*|houthis?|hormuz)\b", re.I)

    @dataclass
    class Article:
        title: str
        url: str
        domain: str
        seen_at: str
        source_country: str
        topic: str
        scope: str
        def to_dict(self): return asdict(self)

    def domain_of(url, given=None):
        if given:
            g = str(given).lower().replace("www.", "").strip()
            if g: return g
        try: return urlparse(url).netloc.lower().replace("www.", "")
        except Exception: return ""

    def parse_seen(value):
        if not value: return datetime.now(timezone.utc)
        for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ"):
            try: return datetime.strptime(str(value).strip(), fmt).replace(tzinfo=timezone.utc)
            except ValueError: pass
        return datetime.now(timezone.utc)

    def fmt_seen(dt):
        return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def fetch_google(topic, scope):
        q = " ".join(x for x in (gn_topics[topic], gn_scopes[scope]) if x)
        url = "https://news.google.com/rss/search?" + urlencode({"q": f"{q} when:{when}", "hl": "en-US", "gl": "US", "ceid": "US:en"})
        with urlopen(Request(url, headers=headers), timeout=6) as r:
            root = ET.fromstring(r.read())
        out = []
        for item in root.iter("item"):
            title = re.sub(r"\s+", " ", (item.findtext("title") or "").strip())
            link = (item.findtext("link") or "").strip()
            src = item.find("source")
            src_name = (src.text or "").strip() if src is not None and src.text else ""
            src_url = src.get("url", "") if src is not None else ""
            if src_name and title.endswith(f" - {src_name}"):
                title = title[: -(len(src_name) + 3)].strip()
            try:
                dt = parsedate_to_datetime(item.findtext("pubDate") or "")
                dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                dt = now_utc
            if not title or not link or dt < since:
                continue
            out.append(Article(title, link, domain_of(src_url) or src_name.lower(), fmt_seen(dt), "", topic, scope))
            if len(out) >= per_query:
                break
        return out

    def fetch_gdelt_once(timeout):
        params = {"query": gdelt_query, "mode": "ArtList", "maxrecords": 75, "format": "json", "sort": "HybridRel", "timespan": f"{hours}h"}
        with urlopen(Request(f"{gdelt_endpoint}?{urlencode(params)}", headers=headers), timeout=timeout) as r:
            text = r.read().decode("utf-8", errors="replace")
        rows = (json.loads(text).get("articles", []) or [])  # a rate-limit reply is plain text -> raises -> caller ignores
        out, seen = [], set()
        for row in rows:
            url = str(row.get("url", "")).strip()
            title = re.sub(r"\s+", " ", str(row.get("title", "")).strip())
            if not url or not title or url in seen: continue
            seen.add(url)
            topics = [t for t, p in topic_patterns.items() if p.search(title)]
            if not topics: continue
            scope = "uae" if uae_pattern.search(title) else ("region" if region_pattern.search(title) else "world")
            out.append(Article(title, url, domain_of(url, row.get("domain")), str(row.get("seendate", "")), str(row.get("sourcecountry", "")), " | ".join(topics), scope))
        return out

    rows, source_counts, failed = [], {"google_news": 0, "gdelt": 0}, 0
    jobs = [(t, s) for t in gn_topics for s in gn_scopes]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        fs = [pool.submit(fetch_google, t, s) for t, s in jobs]
        for f in as_completed(fs):
            try:
                got = f.result()
                rows.extend(got)
                source_counts["google_news"] += len(got)
            except Exception:
                failed += 1

    if not rows:
        remaining = 9.0 - (time.monotonic() - started)
        if remaining > 1.5:
            try:
                got = fetch_gdelt_once(min(6.0, remaining))
                rows.extend(got)
                source_counts["gdelt"] = len(got)
            except Exception:
                failed += 1

    by_url = {}
    for a in rows:
        if a.url not in by_url: by_url[a.url] = a
        else:
            old = by_url[a.url]
            if a.scope not in old.scope.split(" | "): old.scope += f" | {a.scope}"
            for t in a.topic.split(" | "):
                if t not in old.topic.split(" | "): old.topic += f" | {t}"
    articles = list(by_url.values())

    @lru_cache(maxsize=4096)
    def normalize(title):
        text = title.lower()
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"[^\w؀-ۿ\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        stop={"the","a","an","and","or","of","to","in","on","for","with","from","as","at","by","في","من","إلى","على","عن","مع","و","أو","بعد","قبل"}
        return " ".join(w for w in text.split() if w not in stop and len(w)>1)

    def sim(a,b):
        na,nb=normalize(a),normalize(b)
        if not na or not nb:return 0
        seq=SequenceMatcher(None,na,nb).ratio(); sa,sb=set(na.split()),set(nb.split())
        j=len(sa&sb)/max(1,len(sa|sb)); return .62*seq+.38*j

    def cluster(subset):
        clusters=[]
        for a in sorted(subset,key=lambda x:parse_seen(x.seen_at),reverse=True):
            best_i,best_s=None,0
            for i,c in enumerate(clusters):
                s=max(sim(a.title,r.title) for r in c[:3])
                if s>best_s:best_i,best_s=i,s
            if best_i is not None and best_s>=.58:clusters[best_i].append(a)
            else:clusters.append([a])
        return clusters

    def sw(domain):
        for known,w in source_weights.items():
            if domain==known or domain.endswith('.'+known): return w
        return .62

    def record(c):
        c=sorted(c,key=lambda a:parse_seen(a.seen_at),reverse=True)
        lead=max(c,key=lambda a:sw(a.domain)); domains=sorted({a.domain for a in c if a.domain})
        scopes=sorted({scope_labels.get(s.strip(),s.strip()) for a in c for s in a.scope.split(' | ') if s.strip()})
        topic=c[0].topic.split(' | ')[0]; newest=max(parse_seen(a.seen_at) for a in c)
        age=max(0,(datetime.now(timezone.utc)-newest).total_seconds()/3600); recency=exp(-age/22)
        coverage=min(1,log2(len(domains)+1)/3); authority=max(sw(a.domain) for a in c)
        text=' '.join(a.title for a in c).lower(); impact=min(1,sum(1 for t in impact_terms.get(topic,[]) if t in text)/4)
        matches=sum(1 for t in uae_terms if t in text) + (2 if ('uae' in text or 'united arab emirates' in text or 'abu dhabi' in text) else 0)
        uae=min(1,matches/5); score=round((.28*coverage+.22*recency+.22*authority+.18*impact+.10*uae)*100,1)
        strong=sum(1 for d in domains if sw(d)>=.90); conf='مرتفع' if len(domains)>=4 and strong>=1 else ('متوسط' if len(domains)>=2 or strong>=1 else 'أولي')
        return {"title":lead.title,"topic":topic,"topic_label":topic_labels.get(topic,topic),"score":score,"confidence":conf,"source_count":len(domains),"sources":domains,"scopes":scopes,"newest":newest.isoformat(),"uae_impact":round(uae*100),"articles":[a.to_dict() for a in c]}

    def rank(topic):
        subset=[a for a in articles if topic in a.topic.split(' | ')]
        events=[record(c) for c in cluster(subset)]
        return sorted(events,key=lambda e:(e['score'],e['source_count'],e['newest']),reverse=True)[:12]

    events={t:rank(t) for t in topic_labels}

    def analyze(topic, evs):
        label=topic_labels[topic]
        if not evs:
            return {"headline":f"لا توجد مادة كافية في المجال {label}","summary":"لم تجمع المنصة مادة كافية ضمن النافذة الزمنية المحددة.","why_it_matters":"الصورة غير مكتملة حاليًا.","background":"أعد التحديث أو وسّع الفترة.","narratives":["لا توجد روايات كافية للمقارنة."],"actors":[],"scenarios":["انتظار تقارير إضافية."],"what_to_watch":["تأكيدات رسمية","مصادر إضافية"],"uae_angle":"لا يتوافر أثر واضح حاليًا.","confidence":"أولي"}
        h=evs[0]
        return {"headline":h['title'],"summary":f"في المجال {label} يتصدر حاليًا: {h['title']}.","why_it_matters":"لأنه من أعلى الأحداث أهمية في التغطية الحالية وقد يعكس اتجاهًا أوسع.","background":"القراءة تربط الحدث بالسياق الإقليمي والدولي بدل الاكتفاء بالعنوان.","narratives":["الرواية المباشرة للحدث كما تظهر في المصادر الرئيسية.","الرواية الإقليمية والدولية الأوسع وتأثيرها المحتمل."],"actors":h.get('sources',[])[:5],"scenarios":["استمرار التطور وارتفاع أهميته.","تهدئة وتراجع الأثر.","اتساع الأثر إلى ملفات سياسية أو اقتصادية أو أمنية أخرى."],"what_to_watch":["بيانات رسمية","تأكيدات مستقلة","تغير حجم التغطية"],"uae_angle":"يُقاس الأثر على الإمارات عبر الطاقة والتجارة والملاحة والأسواق والتحولات الإقليمية.","confidence":h.get('confidence','أولي')}

    analyses={t:analyze(t,events[t]) for t in topic_labels}
    all_events=sorted([e for lst in events.values() for e in lst],key=lambda x:x['score'],reverse=True)
    meta = {
        "updated_at": datetime.now(timezone.utc).isoformat(), "hours": hours, "article_count": len(articles),
        "database": "disabled-test-mode", "analysis": "built-in",
        "sources": source_counts, "failed_requests": failed, "took_seconds": round(time.monotonic() - started, 2),
    }
    return {"meta":meta,"hero":all_events[0] if all_events else None,"top_events":all_events[:8],"events":events,"analyses":analyses}


def _get_news(hours: int, force: bool):
    """Fetch news, reuse a recent good result, and never let an empty result replace good news."""
    hours = max(1, min(int(hours), 168))
    now = time.time()
    good = GOOD.get(hours)
    if good and now - good[0] < (MIN_REFRESH_SECONDS if force else FRESH_SECONDS):
        return good[1]
    payload = _news_engine(hours)
    if payload["meta"].get("article_count", 0) > 0:
        GOOD[hours] = (now, payload)
        CACHE.update({"hours": hours, "payload": payload, "updated_at": payload["meta"]["updated_at"]})
        return payload
    if good:  # sources returned nothing right now -> keep showing the last good news for this window
        stale = dict(good[1])
        stale["meta"] = {**good[1]["meta"], "stale": True, "sources": payload["meta"].get("sources")}
        return stale
    return payload


@app.get("/api/dashboard")
def dashboard(hours: int = 24):
    try:
        return _get_news(hours, force=False)
    except Exception as exc:
        if CACHE.get("payload"):
            return JSONResponse(CACHE["payload"])
        raise HTTPException(status_code=500, detail=f"News refresh failed: {type(exc).__name__}")

@app.post("/api/refresh")
def refresh(hours: int = 24):
    try:
        return _get_news(hours, force=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"News refresh failed: {type(exc).__name__}")
