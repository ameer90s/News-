"""Text helpers and rule-based classification: scope, domain, UAE impact.

Everything here is pure (no I/O) so it can be unit-tested offline.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

SCOPES = ("local", "regional", "international")
DOMAINS = ("political", "economic", "military")

# ---------------------------------------------------------------- text utils

_TASHKEEL = re.compile(r"[ً-ٰٟـ]")  # harakat + tatweel
_PERSIAN_ONLY = re.compile(r"[پچژگ]")  # پ چ ژ گ
_PERSIAN_SOFT = re.compile(r"[کی]")  # ک ی
_URDU = re.compile(r"[ھےںٹڈڑ]")

_FOLD = (
    ("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"),
    ("ى", "ي"), ("ة", "ه"), ("ؤ", "و"), ("ئ", "ي"),
)


def norm(text: str) -> str:
    """Fold Arabic letter variants and strip diacritics, then lowercase."""
    s = unicodedata.normalize("NFKC", text or "")
    s = _TASHKEEL.sub("", s)
    for a, b in _FOLD:
        s = s.replace(a, b)
    return s.lower()


def detect_lang(text: str) -> str:
    """Return 'ar', 'fa' (Arabic script but Persian/Urdu), 'en' (Latin) or 'other'."""
    ar = lat = oth = 0
    for ch in text or "":
        if not ch.isalpha():
            continue
        o = ord(ch)
        if 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF:
            ar += 1
        elif o < 0x250:
            lat += 1
        else:
            oth += 1
    total = ar + lat + oth
    if total == 0:
        return "other"
    if ar / total >= 0.6:
        if _PERSIAN_ONLY.search(text) or _URDU.search(text) or len(_PERSIAN_SOFT.findall(text)) >= 2:
            return "fa"
        return "ar"
    if lat / total >= 0.6:
        return "en"
    return "other"


def is_arabic(text: str) -> bool:
    return detect_lang(text) == "ar"


# ------------------------------------------------------------------ keywords

_PREFIX = r"[وف]?(?:ال|بال|كال|لل|ب|ل|ك)?"
_SUFFIX = r"(?:ي|ه|ها|هم|ين|ون|ات|يه|يين)?"
_AR = r"؀-ۿ"


def _compile(words: str) -> re.Pattern:
    parts = []
    for raw in words.split("|"):
        w = norm(raw.strip())
        if not w:
            continue
        if re.search(r"[a-z]", w):
            tail = r"\b" if len(w) <= 4 else ""
            parts.append(r"\b" + re.escape(w) + tail)
        else:
            parts.append(f"(?<![{_AR}]){_PREFIX}{re.escape(w)}{_SUFFIX}(?![{_AR}])")
    return re.compile("|".join(parts))


def _count(pattern: re.Pattern, text: str) -> int:
    return len(set(pattern.findall(text)))


LOCAL = _compile(
    "امارات|ابوظبي|دبي|شارقه|عجمان|راس الخيمه|فجيره|ام القيوين|ادنوك|محمد بن زايد|محمد بن راشد|"
    "uae|emirates|dubai|abu dhabi|sharjah|emirati"
)

REGIONAL = _compile(
    "خليج|سعوديه|كويت|قطر|دوحه|بحرين|منامه|عمان|مسقط|ايران|طهران|عراق|بغداد|يمن|حوثي|صنعاء|"
    "سوريا|دمشق|لبنان|بيروت|حزب الله|اسرائيل|غزه|فلسطين|ضفه الغربيه|اردن|قاهره|تركيا|هرمز|"
    "بحر العرب|بحر الاحمر|شرق الاوسط|مجلس التعاون|"
    "iran|iraq|yemen|houthi|saudi|gulf|hormuz|kuwait|qatar|oman|bahrain|israel|gaza|lebanon|"
    "syria|hezbollah|middle east|red sea|tehran|riyadh"
)

_MILITARY = _compile(
    "هجوم|هجمات|ضربه|ضربات|غاره|غارات|صاروخ|صواريخ|مسيره|مسيرات|جيش|عسكري|قوات|دفاع|قاعده|قواعد|"
    "حرب|قصف|اشتباك|استهداف|اعتراض|بحريه|اسطول|سلاح|اسلحه|تسليح|مناورات|نووي|تخصيب|اغتيال|"
    "وقف اطلاق النار|انفجار|مقاتله|مقاتلات|جنود|"
    "war|strike|missile|drone|military|attack|troops|navy|defense|defence|nuclear|airstrike|"
    "ceasefire|army|weapons|warship"
)

_ECONOMIC = _compile(
    "نفط|غاز|اسعار|اسهم|بورصه|سوق|اسواق|اقتصاد|تضخم|فائده|دولار|بنك|مصرف|استثمار|تجاره|جمارك|"
    "رسوم|عقوبات|عقوبه|اوبك|برميل|ذهب|عقار|ميزانيه|نمو|ركود|صادرات|واردات|سندات|عملات|عمله|"
    "ناتج|شركه|ارباح|اكتتاب|بيتكوين|"
    "oil|gas|stocks|market|economy|inflation|rate|rates|dollar|bank|trade|tariff|opec|gold|"
    "crude|brent|price|prices|investment|sanctions|gdp|shares|earnings|bitcoin"
)

_POLITICAL = _compile(
    "رئيس|وزير|حكومه|انتخابات|مفاوضات|اتفاق|قمه|سياسي|سياسه|دبلوماسي|سفير|برلمان|قرار|مجلس الامن|"
    "امم المتحده|محادثات|تحالف|زياره|لقاء|رئاسه|مجلس|"
    "president|minister|government|talks|summit|election|diplomat|treaty|parliament"
)

_HIGH = _compile(
    "هجوم|هجمات|ضربه|ضربات|صاروخ|صواريخ|مسيره|مسيرات|استهداف|هرمز|اغلاق|حصار|عقوبات|عقوبه|نووي|"
    "حرب|تصعيد|توتر|قصف|اعتراض|ازمه|طوارئ|تهديد|تهديدات|انفجار|اغتيال|"
    "strike|attack|missile|drone|hormuz|sanction|war|escalat|tension|blockade|threat|crisis|explosion"
)

_MEDIUM = _compile(
    "نفط|اوبك|غاز|اسعار|طيران|مطار|ملاحه|ممر|شحن|موانئ|ناقله|ناقلات|فائده|تضخم|بورصه|اسهم|دولار|"
    "ذهب|صادرات|استثمار|"
    "oil|opec|gas|shipping|flight|airport|port|tanker|inflation|stocks|dollar|gold|brent|crude"
)

_LOW = _compile(
    "رياضه|كره|مباراه|دوري|لاعب|نادي|مسلسل|فنان|حفل|مهرجان|موضه|"
    "football|soccer|match|league|celebrity|festival|concert"
)


# ------------------------------------------------------------ classification

def classify_scope(text: str, hint: str | None = None) -> str:
    t = norm(text)
    loc, reg = _count(LOCAL, t), _count(REGIONAL, t)
    if loc and (not reg or loc > reg):
        return "local"
    if reg:
        return "regional"
    return hint if hint in SCOPES else "international"


def classify_domain(text: str) -> str:
    t = norm(text)
    scores = {
        "military": 1.3 * _count(_MILITARY, t),
        "economic": 1.2 * _count(_ECONOMIC, t),
        "political": 1.0 * _count(_POLITICAL, t),
    }
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "political"


_BASE_IMPACT = {"local": 30, "regional": 36, "international": 15}


def estimate_impact(text: str, scope: str, n_sources: int = 1) -> int:
    """Heuristic 0-100 'potential impact on the UAE'. Gemini may refine it later."""
    t = norm(text)
    score = _BASE_IMPACT.get(scope, 15)
    high = _count(_HIGH, t)
    score += min(high, 3) * 14
    score += 10 if (scope == "regional" and high) else 0  # hostile events nearby weigh more on the UAE
    score += min(_count(_MEDIUM, t), 3) * 6
    score -= 10 if _count(_LOW, t) else 0
    score += min(max(n_sources - 1, 0), 3) * 3
    return int(max(5, min(96, score)))


def importance(impact: int, published: datetime, now: datetime, hours: int, n_sources: int, trust: float = 0.0) -> float:
    """`trust` is a small bonus (0-5) for official / specialised publishers, see core/registry.py."""
    age_h = max((now - published).total_seconds() / 3600.0, 0.0)
    recency = max(0.0, 1.0 - age_h / float(hours))
    return round(impact * 0.65 + recency * 20.0 + min(max(n_sources - 1, 0), 3) * 5.0 + trust, 2)


def impact_level(value: int | float | None) -> str:
    if value is None:
        return "none"
    v = round(value)
    return "low" if v <= 33 else ("mid" if v <= 66 else "high")
