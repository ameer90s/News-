"""News aggregation: GDELT + Google News RSS, de-duplication, windowing, ranking.

Network I/O uses only the standard library (urllib in worker threads) so the
function has no extra dependencies. Every source is optional: if one fails the
other still serves the page; if both fail the last good result is returned.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlparse

from defusedxml import ElementTree as ET

from . import classify as C
from . import radar as RADAR
from . import registry as REG

VALID_HOURS = (6, 12, 24, 48, 72)

GDELT_URL = os.environ.get("GDELT_URL", "https://api.gdeltproject.org/api/v2/doc/doc")
GNEWS_URL = os.environ.get("GNEWS_URL", "https://news.google.com/rss/search")
GNEWS_CONCURRENCY = 6   # Google News is polite-limited: never fire all the site: queries at once

FETCH_TIMEOUT = 20.0    # per upstream request (seconds)
DEADLINE = 24.0         # whole collection: waits for every source up to the platform limit (functions stop at 30s, see vercel.json), leaving ~6s to rank and answer
NEWS_TTL = int(os.environ.get("NEWS_TTL", "90"))   # seconds of in-memory caching per window
MAX_ITEMS = 120
MAX_STORY = 12          # most headlines merged into one developing story
RADAR_MARGIN = 0.05      # a live story joins a Radar story only if it matches it this much better than any other Radar story
RADAR_MATCH = 140       # characters of a Radar story's summary used (with its title) to recognise live headlines about it
MAX_TRANSLATE = 30
UA = "Mozilla/5.0 (compatible; MirsadBot/1.0; +https://vercel.app)"

# (delay before sending, query). GDELT allows ~1 request / 5s, hence the stagger.
GDELT_QUERIES = [
    (0.0, '(الإمارات OR أبوظبي OR دبي OR إيران OR الخليج OR "مضيق هرمز" OR اليمن OR العراق) sourcelang:arabic'),
    (5.5, '(UAE OR Dubai OR "Abu Dhabi" OR Iran OR "Strait of Hormuz" OR "oil prices") sourcelang:english'),
]

# (query, hl, gl, ceid, scope hint)
GNEWS_QUERIES = [
    ('الإمارات OR أبوظبي OR دبي OR الشارقة', "ar", "AE", "AE:ar", "local"),
    ('إيران OR "مضيق هرمز" OR الخليج OR اليمن OR العراق OR السعودية', "ar", "AE", "AE:ar", "regional"),
    ('"أسعار النفط" OR أوبك OR "الاقتصاد العالمي" OR الفيدرالي', "ar", "AE", "AE:ar", "international"),
    ('أمريكا OR روسيا OR الصين OR "الأمم المتحدة" OR أوكرانيا', "ar", "AE", "AE:ar", "international"),
    ('UAE OR "Strait of Hormuz" OR "oil prices" OR Iran', "en-US", "US", "US:en", None),
]

# Stories that matter to the UAE without being about it: diplomacy / international institutions, trade and
# sanctions between major powers, global finance. Queued right after the core queries (see _collect).
IMPACT_QUERIES = [
    ('("الأمم المتحدة" OR "مجلس الأمن" OR "الأمين العام" OR "مجموعة العشرين" OR بريكس) (ترشيح OR تعيين OR اتفاقية OR تصريحات OR قمة OR قرار)',
     "ar", "AE", "AE:ar", "international"),
    ('(تعريفات OR عقوبات OR "حرب تجارية" OR حظر) (ترامب OR الصين OR روسيا OR "الاتحاد الأوروبي" OR الهند)',
     "ar", "AE", "AE:ar", "international"),
    ('"الفيدرالي الأمريكي" OR "أسعار الفائدة" OR الدولار OR "الأسواق العالمية" OR الذهب',
     "ar", "AE", "AE:ar", "international"),
]

_CACHE: dict[int, tuple[float, dict]] = {}
_LAST_GOOD: dict[int, dict] = {}
TRANSLATIONS: dict[str, str] = {}   # id -> Arabic title (best effort, per instance)


class NewsUnavailable(Exception):
    pass


def _log(*a):
    print("[mirsad]", *a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ fetching

def _http_get(url: str, timeout: float, max_bytes: int = 2_000_000) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "ar,en;q=0.8"}
    )
    deadline = time.monotonic() + timeout + 3
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        chunks, size = [], 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("response too large")
            if time.monotonic() > deadline:
                raise TimeoutError("slow response")
            chunks.append(chunk)
        charset = resp.headers.get_content_charset() or "utf-8"
    return b"".join(chunks).decode(charset, "replace")


def _clean_title(t: str | None) -> str:
    t = html.unescape(t or "")
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:240]


def _safe_url(u: str | None) -> bool:
    try:
        p = urlparse(u or "")
        return p.scheme in ("http", "https") and bool(p.netloc)
    except ValueError:
        return False


def _parse_gdelt_date(s: str | None) -> datetime | None:
    try:
        return datetime.strptime(s or "", "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


async def _fetch_gdelt(query: str, hours: int, delay: float) -> list[dict]:
    if delay:
        await asyncio.sleep(delay)
    params = urlencode({
        "query": query, "mode": "artlist", "format": "json",
        "maxrecords": "75", "sort": "datedesc", "timespan": f"{hours}h",
    })
    text = await asyncio.to_thread(_http_get, f"{GDELT_URL}?{params}", FETCH_TIMEOUT)
    try:
        data = json.loads(text)
    except ValueError:
        raise RuntimeError("GDELT returned non-JSON: " + text[:60].replace("\n", " "))
    out = []
    for a in data.get("articles") or []:
        out.append({
            "title": _clean_title(a.get("title")),
            "url": a.get("url"),
            "source": (a.get("domain") or urlparse(a.get("url") or "").netloc or "").removeprefix("www."),
            "published": _parse_gdelt_date(a.get("seendate")),
            "hint": None,
            "host": REG.host_of(a.get("domain") or a.get("url")),
        })
    return out


async def _fetch_gnews(query: str, hours: int, hl: str, gl: str, ceid: str, hint: str | None,
                       gate: asyncio.Semaphore | None = None) -> list[dict]:
    when = f"{hours}h" if hours <= 24 else f"{-(-hours // 24)}d"
    params = urlencode({"q": f"{query} when:{when}", "hl": hl, "gl": gl, "ceid": ceid})
    if gate is None:
        text = await asyncio.to_thread(_http_get, f"{GNEWS_URL}?{params}", FETCH_TIMEOUT)
    else:
        async with gate:
            text = await asyncio.to_thread(_http_get, f"{GNEWS_URL}?{params}", FETCH_TIMEOUT)
    root = ET.fromstring(text.encode("utf-8"))
    out = []
    for it in root.iter("item"):
        src = it.find("source")
        src_name = _clean_title(src.text) if src is not None and src.text else ""
        title = _clean_title(it.findtext("title"))
        if src_name and title.endswith(" - " + src_name):
            title = title[: -len(src_name) - 3].rstrip()
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate") or "")
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            pub = pub.astimezone(timezone.utc)
        except (TypeError, ValueError):
            pub = None
        out.append({
            "title": title, "url": (it.findtext("link") or "").strip(),
            "source": src_name or "Google News", "published": pub, "hint": hint,
            "host": REG.host_of(src.get("url")) if src is not None else "",
        })
    return out


async def _collect(hours: int) -> tuple[list[dict], dict]:
    jobs = [("gdelt", _fetch_gdelt(q, hours, d)) for d, q in GDELT_QUERIES]
    gate = asyncio.Semaphore(GNEWS_CONCURRENCY)
    jobs += [("gnews", _fetch_gnews(q, hours, hl, gl, ceid, hint, gate)) for q, hl, gl, ceid, hint in GNEWS_QUERIES]
    jobs += [("gnews", _fetch_gnews(q, hours, hl, gl, ceid, hint, gate)) for q, hl, gl, ceid, hint in IMPACT_QUERIES]
    # official / specialised / major sources (see core/registry.py) — queued after the core queries
    jobs += [("gnews", _fetch_gnews(q, hours, "ar", "AE", "AE:ar", None, gate)) for q, _kind in REG.gnews_queries()]
    tasks = {asyncio.ensure_future(c): name for name, c in jobs}
    done, pending = await asyncio.wait(tasks.keys(), timeout=DEADLINE)
    for p in pending:
        p.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    raw: list[dict] = []
    status = {"gdelt": "fail", "gnews": "fail"}
    for t in done:
        name = tasks[t]
        try:
            raw.extend(t.result())
            status[name] = "ok"
        except Exception as e:  # one source failing must never stop the page
            _log(f"{name} failed:", type(e).__name__, str(e)[:120])
    for p in pending:
        _log(f"{tasks[p]} timed out")
    return raw, status


# ------------------------------------------------------------ build / dedupe

def _url_key(u: str) -> str:
    p = urlparse(u)
    return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/")) + ("?" + p.query if "news.google.com" in p.netloc else "")


def _tokens(title: str) -> frozenset[str]:
    toks = re.findall(r"[؀-ۿa-z0-9]+", C.norm(title))
    out = set()
    for t in toks:
        if t.startswith("ال") and len(t) > 4:
            t = t[2:]
        if len(t) >= 3 or (t.isdigit() and len(t) == 2):    # two-digit numbers (96 hours, 25 billion) are strong anchors
            if t not in _YEARS:
                out.add(t)
    return frozenset(out)


_YEARS = frozenset({"2024", "2025", "2026", "2027"})


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# generic news words that must never link two different stories (already normalised / prefix-stripped)
_STORY_STOP = frozenset(C.norm(w) for w in """
اعلن يعلن تعلن اعلنت يعلنون خبر اخبار اليوم امس بعد قبل حول بشان وسط مع على علي في من الى عن هذا هذه ذلك التي الذي
جديد جديده جديدة يبحث تبحث بحث يؤكد تؤكد اكد اكدت قال قالت وقال يقول تقول يشارك تشارك مشاركه يستمر مستمر مستمره
وزير وزيره وزراء رئيس رئيسه حكومه مجلس دوله دول خلال الاسبوع الشهر السنه عام الاول الثاني اكثر اقل بين ضمن امام
تحت فوق نحو حتي منذ ايضا كما انه انها بعض كل غير ثم او لا لم لن قد كان تكون يكون هناك ترقب مرحله خطه قرار اتفاق
يلتقي يستقبل تستقبل يبحث يوقع توقع توقعان يطلق تطلق تعلن تدعو يدعو تحذر يحذر ترد يرد يفرض تفرض يبقي تبقي
خارجيه داخليه دفاع اقتصاد ماليه نظيره نظيرها رسميه رسمي جلسه اجتماع لقاء مباحثات محادثات زياره تصريحات بيان
حالي حاليا عمليه تتحدث يتحدث مشتركه مشترك تعاون شراكه مبادره دعم
""".split())


# topical words that name a subject area, not a particular story: sharing only these never links two headlines
_TOPIC = frozenset(C.norm(w) for w in """
اسعار سعر فائده فوائد نفط غاز دولار اقتصاد اقتصادي اقتصاديه سوق اسواق بورصه اسهم ذهب تضخم نمو ركود استثمار تجاره
ارتفاع ارتفاعا انخفاض تراجع صعود هبوط زياده خفض تغيير دون تصاعد توتر توترات تطورات ازمه ازمات مستمره استمرار
جيش قوات هجوم هجمات حرب حروب عمل ساعات خدمات خدمه مشاريع مشروع حركه نقل سفر مسافرين طيران مطار مطارات
سياسه سياسي سياسيه امن امني امنيه منطقه منطقة شرق اوسط الخليج خليج عربي عربيه دولي دوليه عالمي عالميه
""".split())


def _stems(toks: frozenset, vocab: set) -> frozenset:
    """Strip Arabic proclitics (وال/بال/فال/كال/لل and a lone و/ب/ل/ف/ك when the bare word also occurs in the batch)."""
    out = set()
    for t in toks:
        if len(t) >= 6 and t[:3] in ("وال", "بال", "فال", "كال"):
            t = t[3:]
        elif len(t) >= 5 and t.startswith("لل"):
            t = t[2:]
        elif len(t) >= 4 and t[0] in "وبلفك" and t[1:] in vocab:
            t = t[1:]
        out.add(t)
    return frozenset(out)


def _story_rare(stems: frozenset, df: dict, cut: int) -> frozenset:
    return frozenset(t for t in stems if t not in _STORY_STOP and df.get(t, 0) <= cut)


def _same_story(ra: frozenset, rb: frozenset) -> bool:
    """Two headlines tell the same developing story when they share distinctive words (names, places, things).
    Sharing only topical words (prices, interest, oil, tension...) is not enough: one shared word must be specific."""
    common = ra & rb
    if not (common - _TOPIC):
        return False
    shared = len(common)
    if shared >= 3:
        return True
    return shared >= 2 and shared / len(ra | rb) >= 0.22


# ------------------------------------------------------------------ similarity (merging + diversity)

# Forms of the same news word that stemming cannot join (broken plurals, verb vs noun): mapped to one stem for comparison only.
_CANON_SRC = {
    "اعتراض": "تعترض يعترض اعترض اعترضت اعتراضات تعترضان", "استهداف": "تستهدف يستهدف استهدفت استهدفوا",
    "تدمير": "يدمر تدمر دمر دمرت", "صاروخ": "صواريخ",
}
_CANON = {C.norm(w): C.norm(k) for k, ws in _CANON_SRC.items() for w in ws.split()}


def _light(t: str) -> str:
    """Very light Arabic stemming, used only to compare headlines (never shown): plural/dual endings, feminine and
    relative-adjective endings, tanween alef.  'الإيرانيين' / 'إيرانية' / 'إيراني' all become the same stem."""
    if not t or not ("؀" <= t[0] <= "ۿ"):
        return t
    if t in _CANON:
        return _light(_CANON[t])
    if len(t) >= 6 and t.endswith(("ات", "ون", "ين")):
        t = t[:-2]
    for _ in range(2):
        if len(t) >= 4 and t[-1] in "يه":
            t = t[:-1]
    if len(t) >= 5 and t.endswith("ا"):
        t = t[:-1]
    return t


def _al(w: str) -> str:
    w = C.norm(w)
    return w[2:] if w.startswith("ال") and len(w) > 4 else w


_STOP_L = frozenset(_light(_al(w)) for w in _STORY_STOP) | frozenset(
    _light(_al(w)) for w in ("تقارير", "تقرير", "مصادر", "بحسب", "وفق", "نقلت", "أفاد", "أفادت", "يتوقع", "متوقع", "وكالة"))
_TOPIC_L = frozenset(_light(_al(w)) for w in _TOPIC)

# English words -> the Arabic stem they normally appear as, so the same event reported in both languages can be matched.
_XL_SRC = {
    "ترامب": "trump", "ايران": "iran iranian", "طهران": "tehran", "هرمز": "hormuz", "مضيق": "strait", "حوثي": "houthi houthis",
    "السعوديه": "saudi", "الرياض": "riyadh", "الامارات": "uae emirates emirati", "دبي": "dubai", "ابوظبي": "dhabi",
    "اسرائيل": "israel israeli", "غزه": "gaza", "لبنان": "lebanon", "روسيا": "russia russian", "اوكرانيا": "ukraine ukrainian",
    "كييف": "kyiv kiev", "الصين": "china chinese", "نفط": "oil crude", "برنت": "brent", "الفيدرالي": "fed", "ذهب": "gold",
    "دولار": "dollar", "اسهم": "stocks shares", "ضرب": "strike strikes", "هجوم": "attack attacks", "صاروخ": "missile missiles",
    "مسيره": "drone drones", "حاملة": "carrier", "قوات": "forces troops", "وقف": "ceasefire", "عقوبات": "sanctions",
    "تعريفات": "tariffs", "انتخابات": "election elections", "نتنياهو": "netanyahu", "بوتين": "putin", "زيلينسكي": "zelensky",
    "الكويت": "kuwait", "قطر": "qatar", "مصر": "egypt", "العراق": "iraq", "اليمن": "yemen", "سوريا": "syria", "تركيا": "turkey",
    "باكستان": "pakistan", "الهند": "india", "كندا": "canada", "كارني": "carney", "اوتاوا": "ottawa", "ساعه": "hours hour",
    "سفينه": "ship ships vessel vessels tanker", "ناقله": "tanker", "تسرب": "spill leak", "اسعار": "prices price",
    "فائده": "interest", "تضخم": "inflation", "مبادله": "mubadala", "ابولو": "apollo", "اوبك": "opec", "الحرس": "irgc",
    "نووي": "nuclear", "الجيش": "military army", "امريكا": "us usa america american", "واشنطن": "washington",
}
_XL = {en: _light(_al(ar)) for ar, ens in _XL_SRC.items() for en in ens.split()}
_XL_IMAGE = frozenset(_XL.values())


def _lstems(stems: frozenset) -> tuple[frozenset, frozenset]:
    """(all comparison stems, language-neutral stems).  Latin words map to their Arabic stem when known; numbers are neutral."""
    full, neutral = set(), set()
    for t in stems:
        if t.isdigit():
            full.add(t); neutral.add(t)
        elif "a" <= t[0] <= "z":
            m = _XL.get(t)
            if m:
                full.add(m); neutral.add(m)
            else:
                full.add(t)
        else:
            l = _light(t)
            if l in _STOP_L:
                continue
            full.add(l)
            if l in _XL_IMAGE:
                neutral.add(l)
    return frozenset(full), frozenset(neutral)


class _Space:
    """idf-weighted bag-of-stems cosine over the current batch."""

    def __init__(self, cands: list[dict]):
        n = self.n = len(cands)
        df: dict[str, int] = {}
        for c in cands:
            for t in c["lst"]:
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log((n + 1) / (d + 0.5)) for t, d in df.items()}
        for c in cands:
            c["vec"] = {t: self.idf[t] for t in c["lst"]}
            c["vn"] = math.sqrt(sum(w * w for w in c["vec"].values())) or 1.0
            c["xvec"] = {t: self.idf[t] for t in c["xst"]}
            c["xn"] = math.sqrt(sum(w * w for w in c["xvec"].values())) or 1.0

    def attach(self, c: dict) -> None:
        """Vectors for a candidate that was not part of the batch the idf was computed on (unknown words count as rare)."""
        rare = math.log((self.n + 1) / 0.5)
        c["vec"] = {t: self.idf.get(t, rare) for t in c["lst"]}
        c["vn"] = math.sqrt(sum(w * w for w in c["vec"].values())) or 1.0
        c["xvec"] = {t: self.idf.get(t, rare) for t in c["xst"]}
        c["xn"] = math.sqrt(sum(w * w for w in c["xvec"].values())) or 1.0

    @staticmethod
    def cos(a: dict, b: dict) -> tuple[float, frozenset]:
        """Cosine of two headlines (cross-language pairs compare only the language-neutral stems)."""
        if (a["lang"] == "ar") == (b["lang"] == "ar"):
            va, vb, na, nb = a["vec"], b["vec"], a["vn"], b["vn"]
        else:
            va, vb, na, nb = a["xvec"], b["xvec"], a["xn"], b["xn"]
        if len(va) > len(vb):
            va, vb = vb, va
        shared = [t for t in va if t in vb]
        if not shared:
            return 0.0, frozenset()
        return sum(va[t] * vb[t] for t in shared) / (na * nb), frozenset(shared)


def _same_event(a: dict, b: dict, cos: float, shared: frozenset) -> bool:
    """Strict rule for «the same event, worded differently»: several shared specific words AND a high weighted overlap.
    Precision matters more than recall here (a wrong merge hides a different story); the softer diversity penalty
    below deals with the near-misses."""
    ent = {t for t in shared if not t.isdigit() and t not in _TOPIC_L}
    if len(ent) < 1 or len(shared) < 3:
        return False
    if (a["lang"] == "ar") != (b["lang"] == "ar"):
        return len(ent) >= 2 and cos >= 0.6
    if abs((a["published"] - b["published"]).total_seconds()) > 36 * 3600:
        return False
    return cos >= 0.30 or (len(shared) >= 4 and cos >= 0.22)


DIV_MAX = 30.0          # most a near-duplicate can lose in importance
DIV_LO, DIV_HI = 0.06, 0.22
DIV_WINDOW = 40         # compare each story with the 40 best-ranked ones above it
SUPERSEDE_H = 4.0       # a live story this much newer than a Radar-only story on the same subject replaces it
RADAR_STALE = 10.0      # importance a Radar-only story (no live headline matched) loses as its edition ages: the more hours pass
                        # without the live feed repeating it, the less likely it is still news (full effect after 24 h)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_HINT_RANK = {"local": 0, "regional": 1, "international": 2}


def _best_hint(a: str | None, b: str | None) -> str | None:
    """The scope hint kept when one article comes back from several queries. It must not depend on which query answered
    first (that order changes from request to request), so the more specific hint always wins."""
    return a if _HINT_RANK.get(a, 3) <= _HINT_RANK.get(b, 3) else b


def build_items(raw: list[dict], hours: int, now: datetime) -> list[dict]:
    cutoff = now - timedelta(hours=hours)
    cands = []
    for r in raw:
        title, url, pub = r.get("title"), r.get("url"), r.get("published")
        if not title or not _safe_url(url) or pub is None or pub < cutoff:
            continue
        lang = "ar" if r.get("radar") else C.detect_lang(title)     # Radar stories are written in Arabic
        if lang in ("fa", "other"):
            continue
        cands.append({**r, "published": min(pub, now), "lang": lang})

    # Arabic first (it becomes the group's headline), then newest first.
    # The URL is the final tie-breaker: results arrive from concurrent requests in varying order, and the group's id
    # comes from its first member, so identical timestamps must not make ids (and caches keyed on them) change.
    # The Radar's curated stories (when an edition is fresh) come first: they become the headline of any live story they match.
    cands.sort(key=lambda x: (not x.get("radar"), x["lang"] != "ar", -x["published"].timestamp(), _url_key(x["url"])))

    # The same article is usually returned by several queries (core + registry + impact queries, GDELT + Google News).
    # Keep one copy (its first non-empty scope hint); otherwise it would inflate word counts and story sizes.
    # Radar stories are never collapsed into each other (two domains may cite the same article); a live copy of an
    # article the Radar already cites is folded into the Radar story.
    seen: dict[str, dict] = {}
    kept_c: list[dict] = []
    for c in cands:
        k = _url_key(c["url"])
        if c.get("radar"):
            c["key"] = c["radar"]["key"]
            seen.setdefault(k, c)
            kept_c.append(c)
        elif k in seen:
            seen[k]["hint"] = _best_hint(seen[k].get("hint"), c.get("hint"))
        else:
            seen[k] = c
            c["key"] = k
            kept_c.append(c)
    cands = kept_c

    # document frequency of every word in this batch: words that appear in only a few headlines are the
    # distinctive ones (names, places, things) that tie follow-up headlines to the same developing story
    vocab: set[str] = set()
    for c in cands:
        c["tokens"] = _tokens(c["title"] + (" " + c["radar"]["summary"][:RADAR_MATCH] if c.get("radar") else ""))
        vocab.update(c["tokens"])
        vocab.update(_light(t) for t in c["tokens"])     # «وثلاث» ≡ «ثلاث» even when the batch only has «ثلاثة»
    df: dict[str, int] = {}
    for c in cands:
        c["stems"] = _stems(c["tokens"], vocab)
        for t in c["stems"]:
            df[t] = df.get(t, 0) + 1
    rare_cut = max(6, int(0.05 * len(cands)))

    for c in cands:
        c["rare"] = _story_rare(c["stems"], df, rare_cut)
        c["lst"], c["xst"] = _lstems(c["stems"])
    space = _Space(cands)
    for c in cands:
        if c.get("radar"):
            # A Radar title is a tight summary of the event, so for «does a live headline repeat this story» (the diversity
            # pass below) the title alone is the sharper yardstick; title + summary (used above) is for recognising it.
            tp = {"lang": "ar", "published": c["published"], "tp": True}
            tp["lst"], tp["xst"] = _lstems(_stems(_tokens(c["title"]), vocab))
            space.attach(tp)
            c["tpseudo"] = tp

    # --- cluster headlines into stories (union-find): near-duplicate wording or shared distinctive words
    parent = list(range(len(cands)))
    size = [1] * len(cands)
    has_radar = [1 if c.get("radar") else 0 for c in cands]

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri == rj or size[ri] + size[rj] > MAX_STORY:   # a story never grows into a catch-all pile
            return
        if has_radar[ri] and has_radar[rj]:               # the Radar already separated its own stories
            return
        if ri > rj:
            ri, rj = rj, ri
        parent[rj] = ri
        size[ri] += size[rj]
        has_radar[ri] |= has_radar[rj]

    index: dict[str, list[int]] = {}
    for i, c in enumerate(cands):
        for t in c["rare"]:
            index.setdefault(t, []).append(i)
    shared: dict[tuple[int, int], int] = {}
    for lst in index.values():
        for x in range(len(lst)):
            for y in range(x + 1, len(lst)):
                shared[(lst[x], lst[y])] = shared.get((lst[x], lst[y]), 0) + 1
    for (i, j), n_sh in sorted(shared.items()):
        ci, cj = cands[i], cands[j]
        if ci.get("radar") or cj.get("radar"):      # Radar stories are matched separately, below
            continue
        if (ci["lang"] == "ar") != (cj["lang"] == "ar") or n_sh < 2:
            continue
        if _jaccard(ci["tokens"], cj["tokens"]) >= 0.55 and len(ci["tokens"]) >= 3:
            union(i, j)
        elif _same_story(ci["rare"], cj["rare"]) and space.cos(ci, cj)[0] >= 0.14:   # names/places shared AND real overlap
            union(i, j)

    # weighted-overlap pass: same event, differently worded, also across Arabic / English (see _same_event)
    lindex: dict[str, list[int]] = {}
    for i, c in enumerate(cands):
        for t in c["lst"]:
            lindex.setdefault(t, []).append(i)
    pair_n: dict[tuple[int, int], int] = {}
    for lst in lindex.values():
        if len(lst) > 90:                  # ubiquitous words link nothing
            continue
        for x in range(len(lst)):
            for y in range(x + 1, len(lst)):
                pair_n[(lst[x], lst[y])] = pair_n.get((lst[x], lst[y]), 0) + 1
    for (i, j), n_sh in sorted(pair_n.items()):
        if n_sh < 3 or find(i) == find(j) or cands[i].get("radar") or cands[j].get("radar"):
            continue
        cs, sh = space.cos(cands[i], cands[j])
        if _same_event(cands[i], cands[j], cs, sh):
            union(i, j)

    # Radar stories: each cluster of live headlines joins the ONE Radar story it matches best, and only when that match is
    # clearly better than the runner-up (two Radar stories on similar subjects, e.g. two phone calls, must not pull the
    # same headlines together). Headlines that match no Radar story stay as ordinary live stories.
    radar_ix = [i for i, c in enumerate(cands) if c.get("radar")]
    if radar_ix:
        live: dict[int, list[int]] = {}
        for i, c in enumerate(cands):
            if not c.get("radar"):
                live.setdefault(find(i), []).append(i)
        for _root, mem in sorted(live.items()):
            scored = []
            for r in radar_ix:
                best = 0.0
                for m in mem:
                    cs, sh = space.cos(cands[m], cands[r])
                    if _same_event(cands[m], cands[r], cs, sh):
                        best = max(best, cs)
                scored.append((best, r))
            scored.sort(reverse=True)
            runner = scored[1][0] if len(scored) > 1 else 0.0
            if scored[0][0] > 0.0 and scored[0][0] - runner >= RADAR_MARGIN:
                union(mem[0], scored[0][1])

    groups: list[dict] = []
    root_group: dict[int, dict] = {}
    for i, c in enumerate(cands):          # cands are ordered Radar-first (only so the Radar's Arabic title becomes the headline), Arabic-first, newest-first
        key = c["key"]
        reg = REG.lookup(c.get("host"))
        src = {"name": reg[1] if reg else c["source"], "url": c["url"], "title": c["title"], "lang": c["lang"],
               "kind": reg[0] if reg else None}
        srcs = [src]
        if c.get("radar"):                 # the Radar cites its own sources (often a specialised outlet next to a general one)
            srcs = []
            for rs in c["radar"]["sources"]:
                rr = REG.lookup(rs["url"])
                srcs.append({"name": rs["name"], "url": rs["url"], "title": c["title"], "lang": "ar", "kind": rr[0] if rr else None})
        g = root_group.get(find(i))
        if g is None:
            g = {"lang": c["lang"], "published": c["published"], "first": c["published"], "hint": c.get("hint"),
                 "primary_title": c["title"], "primary_url": c["url"], "primary_key": key, "sources": srcs, "keys": {key},
                 "titles": [c["title"]], "members": [c], "radar": c.get("radar"), "radar_c": c if c.get("radar") else None}
            groups.append(g)
            root_group[find(i)] = g
        else:
            if not any(x["url"] == src["url"] or x["name"] == src["name"] for x in g["sources"]):
                g["sources"].append(src)
            g["members"].append(c)
            g["published"] = max(g["published"], c["published"])
            g["first"] = min(g["first"], c["published"])
            g["hint"] = g["hint"] or c.get("hint")
            if key not in g["keys"]:
                g["keys"].add(key)
                if len(g["titles"]) < 12:
                    g["titles"].append(c["title"])

    items = []
    for g in groups:
        n = len(g["sources"])
        rank_src = g["sources"]
        if g.get("radar"):
            # A Radar story cites the sources of a past edition; only today's live headlines count as coverage when the
            # story is ranked, so it competes with the live news on the same terms (a lone headline counts as one source).
            live_names = {(REG.lookup(m.get("host")) or (None, m["source"]))[1] for m in g["members"] if not m.get("radar")}
            rank_src = g["sources"][:1] + [s for s in g["sources"][1:] if s["name"] in live_names]
        n_rank = max(1, len(live_names) if g.get("radar") else n)
        updates = len(g["keys"])
        span_h = (g["published"] - g["first"]).total_seconds() / 3600.0
        # the story is judged by its most telling headline; the newest headline is the one shown
        best = None
        for t in g["titles"]:
            sc = C.classify_scope(t, g["hint"])
            imp, why = C.assess(t, sc, n_rank)
            if best is None or imp > best[0]:
                best = (imp, why, sc, t)
        impact, why, scope, best_title = best
        domain = C.classify_domain(best_title)
        rd = g.get("radar")
        if rd:                             # the Radar already classified and judged this story
            scope, domain = rd["scope"], rd["domain"]
            impact, why = RADAR.impact_of(rd, n_rank)
        # a story that keeps developing (several updates over many hours) gains weight
        story = 0.0
        if updates >= 3:
            story = min(updates - 2, 4) * 2.0 + (4.0 if span_h >= 12 else 0.0) + (3.0 if span_h >= 36 else 0.0)
        iid = hashlib.sha1(g["primary_key"].encode()).hexdigest()[:12]
        items.append({
            "id": iid,
            "title": g["primary_title"] if g["lang"] == "ar" else TRANSLATIONS.get(iid),
            "published": _iso(g["published"]),
            "scope": scope,
            "domain": domain,
            "uae_impact": impact,
            "why": why,
            "updates": updates,
            "importance": C.importance(impact, g["published"], now, hours, n_rank,
                                       max((REG.trust_bonus(s["kind"]) for s in rank_src), default=0.0), story),
            "sources": g["sources"][:6],
            "_m": ([g["radar_c"]["tpseudo"]] if rd else []) + g["members"][:3],
            "_ro": bool(rd) and not live_names,        # a story that only the Radar edition reports (no live headline matched)
            "_t": g["published"],
        })
        if rd:
            items[-1].update(radar=True, summary=rd["summary"], when=rd["when"], ref=rd["ref"])
            # no extra rank for Radar stories: they compete with the live news on the same terms (impact, recency,
            # sources) so the page leads with what is happening now, not with yesterday's edition
            if not live_names:
                age_h = max((now - g["published"]).total_seconds() / 3600.0, 0.0)
                items[-1]["importance"] = round(items[-1]["importance"] - RADAR_STALE * min(1.0, age_h / 24.0), 2)
    items.sort(key=lambda i: i["importance"], reverse=True)

    # Diversity: a story that closely resembles one ranked above it (same subject, another angle or another outlet that
    # was not merged) loses importance in proportion to the resemblance, so the top of every list shows different events.
    kept: list[dict] = []
    older: dict[int, float] = {}          # id(item) -> resemblance to a clearly NEWER story (it is the superseded one)
    for it in items:
        m = 0.0
        for k in kept[:DIV_WINDOW]:
            # today's story about a subject yesterday's Radar edition also covered is not a repeat of it: the older
            # edition story gives way instead (below), so the fresh news is never pushed down by a day-old summary
            supersedes = k["_ro"] and (it["_t"] - k["_t"]).total_seconds() >= SUPERSEDE_H * 3600
            mm = 0.0
            for a in it["_m"]:
                if a.get("tp") and k.get("radar"):      # two Radar stories are compared by title + summary: their short
                    continue                           # titles share place names too easily (Tehran, Riyadh) to say anything
                for b in k["_m"]:
                    if b.get("tp") and it.get("radar"):
                        continue
                    cs, _sh = space.cos(a, b)
                    if (a.get("tp") or b.get("tp")) and (len(_sh) < 3 or (a["lang"] == "ar") != (b["lang"] == "ar")):
                        continue            # a short Radar title says little unless 3+ words are shared, in the same language
                    if cs > mm:
                        mm = cs
            if supersedes:
                older[id(k)] = max(older.get(id(k), 0.0), mm)
            elif mm > m:
                m = mm
        pen = DIV_MAX * min(1.0, max(0.0, (m - DIV_LO) / (DIV_HI - DIV_LO)))
        it["importance"] = round(it["importance"] - pen, 2)
        it["dup"] = round(pen)            # how much it repeats a better-ranked story (0 = distinct)
        kept.append(it)
    for it in kept:
        m = older.get(id(it), 0.0)
        if m > 0.0:
            pen = DIV_MAX * min(1.0, max(0.0, (m - DIV_LO) / (DIV_HI - DIV_LO)))
            it["importance"] = round(it["importance"] - pen, 2)
            it["dup"] = max(it["dup"], round(pen))
    for it in items:
        del it["_m"], it["_ro"], it["_t"]
    items.sort(key=lambda i: i["importance"], reverse=True)
    return items[:MAX_ITEMS]


def _payload(items: list[dict], hours: int, status: dict, stale: bool = False,
             ed: dict | None = None, extra: list[dict] | None = None) -> dict:
    pending = [i["id"] for i in items if not i["title"]][:MAX_TRANSLATE]
    out = {
        "hours": hours,
        "generated_at": _iso(datetime.now(timezone.utc)),
        "stale": stale,
        "sources": status,
        "items": items,
        "to_translate": pending,
    }
    if ed is not None:                     # the Radar edition's analysis, with «[n]» wired to the matching items
        have = {i["id"] for i in items}
        ids = {c["radar"]["key"]: RADAR.item_id(c["radar"]["key"]) for c in (extra or [])
               if RADAR.item_id(c["radar"]["key"]) in have}
        out["radar"] = RADAR.block(ed, ids)
    return out


def remember_translations(mapping: dict[str, str]) -> None:
    for k, v in mapping.items():
        TRANSLATIONS[k] = v
    while len(TRANSLATIONS) > 2000:
        TRANSLATIONS.pop(next(iter(TRANSLATIONS)))


async def get_news(hours: int) -> dict:
    if hours not in VALID_HOURS:
        hours = min(VALID_HOURS, key=lambda h: abs(h - hours))
    now_m = time.monotonic()
    hit = _CACHE.get(hours)
    if hit and now_m - hit[0] < NEWS_TTL:
        return hit[1]

    now = datetime.now(timezone.utc)
    ed = RADAR.current(now)                # the Radar's latest edition while it is fresh, else None
    extra = RADAR.candidates(ed, now) if ed else []
    raw, status = await _collect(hours)
    if status["gdelt"] == "fail" and status["gnews"] == "fail":
        last = _LAST_GOOD.get(hours)
        if last:  # serve the previous good result, re-windowed
            cutoff = now - timedelta(hours=hours)
            items = [i for i in last["items"] if i["published"] >= _iso(cutoff)]
            for i in items:
                i["title"] = i["title"] or TRANSLATIONS.get(i["id"])
            stale = _payload(items, hours, status, stale=True)
            if "radar" in last:
                stale["radar"] = last["radar"]
            stale["generated_at"] = last["generated_at"]
            return stale
        if extra:                          # no live feed at all, but the curated edition can still carry the page
            items = build_items(extra, hours, now)
            if items:
                return _payload(items, hours, status, stale=True, ed=ed, extra=extra)
        raise NewsUnavailable("all news sources failed")

    items = build_items(raw + extra, hours, now)
    payload = _payload(items, hours, status, ed=ed, extra=extra)
    _CACHE[hours] = (now_m, payload)
    if items:
        _LAST_GOOD[hours] = payload
    return payload
