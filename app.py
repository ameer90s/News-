from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from pathlib import Path
from datetime import datetime, timezone
import os

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Strategic Newsroom UAE")
CACHE = {"hours": None, "payload": None, "updated_at": None}

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
    }


def _news_engine(hours: int):
    # Heavy imports are deliberately deferred until an API request so Vercel can
    # always import main.py and serve the UI/health endpoint first.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from dataclasses import dataclass, asdict
    from difflib import SequenceMatcher
    from math import exp, log2
    from urllib.parse import urlencode, urlparse
    from urllib.request import Request, urlopen
    import json
    import re

    hours = max(1, min(int(hours), 168))
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    topic_queries = {
        "political": '(government OR diplomacy OR election OR sanctions OR treaty OR parliament OR minister OR president OR "foreign policy" OR negotiations OR ceasefire OR summit)',
        "economic": '(economy OR inflation OR "interest rate" OR GDP OR oil OR gas OR trade OR investment OR markets OR banking OR shipping OR currency OR tariff)',
        "military": '(military OR defence OR defense OR missile OR drone OR airstrike OR army OR navy OR "air force" OR conflict OR ceasefire OR "security forces")',
    }
    scope_queries = {
        "uae": '("United Arab Emirates" OR UAE OR "Abu Dhabi" OR Dubai OR Sharjah)',
        "region": '("Middle East" OR GCC OR Gulf OR Saudi OR Qatar OR Kuwait OR Bahrain OR Oman OR Yemen OR Iraq OR Iran OR Israel OR Palestine OR Lebanon OR Syria OR Jordan OR Egypt OR Turkey)',
        "world": "",
    }
    topic_labels = {"political": "سياسي", "economic": "اقتصادي", "military": "عسكري"}
    scope_labels = {"uae": "الإمارات", "region": "الشرق الأوسط", "world": "العالم"}
    source_weights = {
        "wam.ae": 1.0, "reuters.com": 1.0, "apnews.com": 0.98, "bbc.com": 0.95,
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

    def fetch_one(topic, scope):
        query = f"{topic_queries[topic]} {scope_queries[scope]}".strip()
        params = {"query": query, "mode": "ArtList", "maxrecords": 28, "format": "json", "sort": "HybridRel", "timespan": f"{hours}H"}
        req = Request(f"{endpoint}?{urlencode(params)}", headers={"User-Agent":"Strategic-Newsroom/2.0"})
        with urlopen(req, timeout=5) as r:
            rows = (json.loads(r.read().decode("utf-8", errors="replace")).get("articles", []) or [])
        out, seen = [], set()
        for row in rows:
            url = str(row.get("url", "")).strip()
            title = re.sub(r"\s+", " ", str(row.get("title", "")).strip())
            if not url or not title or url in seen: continue
            seen.add(url)
            out.append(Article(title, url, domain_of(url,row.get("domain")), str(row.get("seendate","")), str(row.get("sourcecountry","")), topic, scope))
        return out

    rows = []
    jobs = [(t,s) for t in topic_queries for s in scope_queries]
    with ThreadPoolExecutor(max_workers=6) as pool:
        fs = [pool.submit(fetch_one,t,s) for t,s in jobs]
        for f in as_completed(fs):
            try: rows.extend(f.result())
            except Exception: pass

    by_url = {}
    for a in rows:
        if a.url not in by_url: by_url[a.url] = a
        else:
            old = by_url[a.url]
            if a.scope not in old.scope.split(" | "): old.scope += f" | {a.scope}"
            if a.topic not in old.topic.split(" | "): old.topic += f" | {a.topic}"
    articles = list(by_url.values())

    def normalize(title):
        text = title.lower()
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"[^\w\u0600-\u06FF\s]", " ", text)
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
    return {"meta":{"updated_at":datetime.now(timezone.utc).isoformat(),"hours":hours,"article_count":len(articles),"database":"disabled-test-mode","analysis":"built-in"},"hero":all_events[0] if all_events else None,"top_events":all_events[:8],"events":events,"analyses":analyses}


@app.get("/api/dashboard")
def dashboard(hours: int = 24):
    hours = max(1, min(int(hours), 168))
    if CACHE.get("payload") and CACHE.get("hours") == hours:
        return CACHE["payload"]
    try:
        payload = _news_engine(hours)
        CACHE.update({"hours": hours, "payload": payload, "updated_at": payload["meta"]["updated_at"]})
        return payload
    except Exception as exc:
        if CACHE.get("payload"):
            return JSONResponse(CACHE["payload"])
        raise HTTPException(status_code=500, detail=f"News refresh failed: {type(exc).__name__}")

@app.post("/api/refresh")
def refresh(hours: int = 24):
    try:
        payload = _news_engine(hours)
        CACHE.update({"hours": hours, "payload": payload, "updated_at": payload["meta"]["updated_at"]})
        return payload
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"News refresh failed: {type(exc).__name__}")
