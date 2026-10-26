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
from . import registry as REG

VALID_HOURS = (6, 12, 24, 48, 72)

GDELT_URL = os.environ.get("GDELT_URL", "https://api.gdeltproject.org/api/v2/doc/doc")
GNEWS_URL = os.environ.get("GNEWS_URL", "https://news.google.com/rss/search")
GNEWS_CONCURRENCY = 6   # Google News is polite-limited: never fire all the site: queries at once

FETCH_TIMEOUT = 9.0     # per upstream request (seconds)
DEADLINE = 12.5         # whole collection; the browser gives up at ~15s
NEWS_TTL = int(os.environ.get("NEWS_TTL", "90"))   # seconds of in-memory caching per window
MAX_ITEMS = 120
MAX_STORY = 12          # most headlines merged into one developing story
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
        if len(t) >= 3:
            out.add(t)
    return frozenset(out)


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


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_items(raw: list[dict], hours: int, now: datetime) -> list[dict]:
    cutoff = now - timedelta(hours=hours)
    cands = []
    for r in raw:
        title, url, pub = r.get("title"), r.get("url"), r.get("published")
        if not title or not _safe_url(url) or pub is None or pub < cutoff:
            continue
        lang = C.detect_lang(title)
        if lang in ("fa", "other"):
            continue
        cands.append({**r, "published": min(pub, now), "lang": lang})

    # Arabic first (it becomes the group's headline), then newest first.
    # The URL is the final tie-breaker: results arrive from concurrent requests in varying order, and the group's id
    # comes from its first member, so identical timestamps must not make ids (and caches keyed on them) change.
    cands.sort(key=lambda x: (x["lang"] != "ar", -x["published"].timestamp(), _url_key(x["url"])))

    # The same article is usually returned by several queries (core + registry + impact queries, GDELT + Google News).
    # Keep one copy (its first non-empty scope hint); otherwise it would inflate word counts and story sizes.
    seen: dict[str, dict] = {}
    for c in cands:
        k = _url_key(c["url"])
        if k in seen:
            seen[k]["hint"] = seen[k].get("hint") or c.get("hint")
        else:
            seen[k] = c
    cands = list(seen.values())

    # document frequency of every word in this batch: words that appear in only a few headlines are the
    # distinctive ones (names, places, things) that tie follow-up headlines to the same developing story
    vocab: set[str] = set()
    for c in cands:
        c["tokens"] = _tokens(c["title"])
        vocab.update(c["tokens"])
    df: dict[str, int] = {}
    for c in cands:
        c["stems"] = _stems(c["tokens"], vocab)
        for t in c["stems"]:
            df[t] = df.get(t, 0) + 1
    rare_cut = max(6, int(0.05 * len(cands)))

    for c in cands:
        c["rare"] = _story_rare(c["stems"], df, rare_cut)

    # --- cluster headlines into stories (union-find): near-duplicate wording or shared distinctive words
    parent = list(range(len(cands)))
    size = [1] * len(cands)

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri == rj or size[ri] + size[rj] > MAX_STORY:   # a story never grows into a catch-all pile
            return
        if ri > rj:
            ri, rj = rj, ri
        parent[rj] = ri
        size[ri] += size[rj]

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
        if (ci["lang"] == "ar") != (cj["lang"] == "ar") or n_sh < 2:
            continue
        if _same_story(ci["rare"], cj["rare"]) or (len(ci["tokens"]) >= 3 and _jaccard(ci["tokens"], cj["tokens"]) >= 0.55):
            union(i, j)

    groups: list[dict] = []
    root_group: dict[int, dict] = {}
    for i, c in enumerate(cands):          # cands are ordered Arabic-first, newest-first: the first member is the headline
        key = _url_key(c["url"])
        reg = REG.lookup(c.get("host"))
        src = {"name": reg[1] if reg else c["source"], "url": c["url"], "title": c["title"], "lang": c["lang"],
               "kind": reg[0] if reg else None}
        g = root_group.get(find(i))
        if g is None:
            g = {"lang": c["lang"], "published": c["published"], "first": c["published"], "hint": c.get("hint"),
                 "primary_title": c["title"], "primary_url": c["url"], "sources": [src], "keys": {key}, "titles": [c["title"]]}
            groups.append(g)
            root_group[find(i)] = g
        else:
            if not any(x["url"] == src["url"] or x["name"] == src["name"] for x in g["sources"]):
                g["sources"].append(src)
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
        updates = len(g["keys"])
        span_h = (g["published"] - g["first"]).total_seconds() / 3600.0
        # the story is judged by its most telling headline; the newest headline is the one shown
        best = None
        for t in g["titles"]:
            sc = C.classify_scope(t, g["hint"])
            imp, why = C.assess(t, sc, n)
            if best is None or imp > best[0]:
                best = (imp, why, sc, t)
        impact, why, scope, best_title = best
        domain = C.classify_domain(best_title)
        # a story that keeps developing (several updates over many hours) gains weight
        story = 0.0
        if updates >= 3:
            story = min(updates - 2, 4) * 2.0 + (4.0 if span_h >= 12 else 0.0) + (3.0 if span_h >= 36 else 0.0)
        iid = hashlib.sha1(_url_key(g["primary_url"]).encode()).hexdigest()[:12]
        items.append({
            "id": iid,
            "title": g["primary_title"] if g["lang"] == "ar" else TRANSLATIONS.get(iid),
            "published": _iso(g["published"]),
            "scope": scope,
            "domain": domain,
            "uae_impact": impact,
            "why": why,
            "updates": updates,
            "importance": C.importance(impact, g["published"], now, hours, n,
                                       max((REG.trust_bonus(s["kind"]) for s in g["sources"]), default=0.0), story),
            "sources": g["sources"][:6],
        })
    items.sort(key=lambda i: i["importance"], reverse=True)
    return items[:MAX_ITEMS]


def _payload(items: list[dict], hours: int, status: dict, stale: bool = False) -> dict:
    pending = [i["id"] for i in items if not i["title"]][:MAX_TRANSLATE]
    return {
        "hours": hours,
        "generated_at": _iso(datetime.now(timezone.utc)),
        "stale": stale,
        "sources": status,
        "items": items,
        "to_translate": pending,
    }


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
    raw, status = await _collect(hours)
    if status["gdelt"] == "fail" and status["gnews"] == "fail":
        last = _LAST_GOOD.get(hours)
        if last:  # serve the previous good result, re-windowed
            cutoff = now - timedelta(hours=hours)
            items = [i for i in last["items"] if i["published"] >= _iso(cutoff)]
            for i in items:
                i["title"] = i["title"] or TRANSLATIONS.get(i["id"])
            stale = _payload(items, hours, status, stale=True)
            stale["generated_at"] = last["generated_at"]
            return stale
        raise NewsUnavailable("all news sources failed")

    items = build_items(raw, hours, now)
    payload = _payload(items, hours, status)
    _CACHE[hours] = (now_m, payload)
    if items:
        _LAST_GOOD[hours] = payload
    return payload
