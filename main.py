from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os, re, time, json, hashlib
import httpx, feedparser
from urllib.parse import quote

BASE = Path(__file__).parent
STATIC = BASE / "static"
app = FastAPI(title="مرصد الإمارات الذكي")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

CACHE = {"at": 0, "hours": 24, "items": []}
UA = "Mozilla/5.0 UAE-Smart-Observatory/1.0"
AR = re.compile(r"[\u0600-\u06FF]")

TOPICS = [
    ("محلية", "الإمارات OR أبوظبي OR دبي OR الشارقة OR عجمان OR الفجيرة OR رأس الخيمة OR أم القيوين"),
    ("إقليمية", "الخليج OR السعودية OR قطر OR الكويت OR البحرين OR عمان OR إيران OR الشرق الأوسط"),
    ("دولية", "النفط OR الغاز OR الأسواق العالمية OR التجارة OR الأمن الدولي OR الذكاء الاصطناعي")
]

def score(title, category):
    t = title.lower()
    n = 42
    hot = ["الإمارات","أبوظبي","دبي","الخليج","نفط","غاز","اقتصاد","أسواق","أمن","عسكري","إيران","طاقة","تجارة"]
    n += sum(6 for k in hot if k in t)
    if category == "محلية": n += 10
    return max(18, min(96, n))

def domain(title):
    t = title.lower()
    if any(k in t for k in ["جيش","عسكري","دفاع","صاروخ","هجوم","أمن","حرب"]): return "military"
    if any(k in t for k in ["اقتصاد","نفط","غاز","سوق","أسهم","تجارة","استثمار","طاقة","بنك"]): return "economic"
    return "political"

async def google_ar(hours):
    out=[]
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent":UA}, follow_redirects=True) as c:
        for cat,q in TOPICS:
            url=f"https://news.google.com/rss/search?q={quote(q)}%20when:{hours}h&hl=ar&gl=AE&ceid=AE:ar"
            try:
                r=await c.get(url); r.raise_for_status(); feed=feedparser.loads(r.content)
                for e in feed.entries[:12]:
                    title=re.sub(r"\s+-\s+[^-]+$", "", e.get("title","")).strip()
                    if not title or not AR.search(title): continue
                    src=(e.get("source") or {}).get("title") if isinstance(e.get("source"),dict) else "Google News"
                    impact=score(title,cat)
                    out.append({"id":hashlib.md5((title+e.get('link','')).encode()).hexdigest()[:12],"title":title,"url":e.get("link","#"),"source":src or "Google News","published":e.get("published",""),"category":cat,"domain":domain(title),"uae_impact":impact})
            except Exception:
                pass
    seen=set(); clean=[]
    for x in sorted(out,key=lambda z:z["uae_impact"], reverse=True):
        key=re.sub(r"\W+","",x["title"])[:55]
        if key in seen: continue
        seen.add(key); clean.append(x)
    return clean[:24]

async def gemini_json(prompt):
    key=os.getenv("GEMINI_API_KEY")
    if not key: return None
    model=os.getenv("GEMINI_MODEL","gemini-2.5-flash")
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.25,"responseMimeType":"application/json"}}
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r=await c.post(url,json=payload); r.raise_for_status(); data=r.json()
        txt=data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(txt)
    except Exception:
        return None

@app.get("/")
def home(): return FileResponse(STATIC/"index.html")

@app.get("/api/news")
async def news(hours:int=Query(24,ge=6,le=72)):
    now=time.time()
    if CACHE["items"] and CACHE["hours"]==hours and now-CACHE["at"]<300:
        return {"items":CACHE["items"],"cached":True}
    items=await google_ar(hours)
    if items:
        CACHE.update({"at":now,"hours":hours,"items":items})
    elif CACHE["items"]:
        items=CACHE["items"]
    return {"items":items,"cached":False}

@app.post("/api/analyze")
async def analyze(payload:dict):
    items=(payload.get("items") or [])[:10]
    if not items: return JSONResponse({"ai":False,"analysis":local_analysis([])})
    compact=[{"title":x.get("title"),"category":x.get("category"),"impact":x.get("uae_impact")} for x in items]
    prompt="""أنت محلل استراتيجي إماراتي. حلل الأخبار التالية بالعربية فقط، بلا تهويل أو اختلاق. أعد JSON حصراً بهذا الشكل:
{"big_picture":{"title":"...","summary":"..."},"political":"...","economic":"...","military":"..."}
العنوان قصير، والملخص 2-3 جمل، وكل تحليل مجال جملة أو جملتان ويركز على الأثر المحتمل على الإمارات. الأخبار:\n"""+json.dumps(compact,ensure_ascii=False)
    result=await gemini_json(prompt)
    if result: return {"ai":True,"analysis":result}
    return {"ai":False,"analysis":local_analysis(items)}

def local_analysis(items):
    if not items:
        return {"big_picture":{"title":"لا توجد بيانات كافية بعد","summary":"سيتم تحديث الصورة الكبرى عند توفر أخبار عربية حديثة من المصادر."},"political":"لا توجد إشارات كافية حالياً.","economic":"لا توجد إشارات كافية حالياً.","military":"لا توجد إشارات كافية حالياً."}
    top=items[0]
    def text(d,label):
        vals=[x for x in items if x.get("domain")==d]
        if not vals: return f"لا توجد إشارات {label} بارزة ضمن الأخبار الحالية."
        avg=round(sum(x.get("uae_impact",0) for x in vals)/len(vals))
        return f"المؤشرات {label} الحالية تسجل تأثيراً تقديرياً بحدود {avg}% استناداً إلى الأخبار المعروضة."
    return {"big_picture":{"title":top.get("title","الصورة الكبرى"),"summary":"تعكس الأخبار الحالية مزيجاً من التطورات المحلية والإقليمية والدولية. يتم ترتيبها وفق أهميتها وتأثيرها المحتمل على الإمارات."},"political":text("political","السياسية"),"economic":text("economic","الاقتصادية"),"military":text("military","العسكرية")}
