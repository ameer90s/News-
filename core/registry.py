"""Registry of the official / specialised / major news sources the monitor pulls from.

One list drives everything: which domains are queried (Google News `site:` queries), how a source is
labelled in Arabic, which tag the sheet shows, and the small ranking bonus a trustworthy source earns.
Add or remove a domain here and nothing else needs to change.
"""
from __future__ import annotations

# kind -> (Arabic tag shown in the UI, importance bonus)
KINDS = {
    "official":    ("رسمي", 5.0),
    "specialized": ("متخصص", 3.0),
    "agency":      ("وكالة/قناة كبرى", 2.0),
    "press":       ("صحافة محلية", 1.0),
}

# (domain, kind, Arabic display name)
SOURCES: list[tuple[str, str, str]] = [
    # ---- official: UAE government, regulators, exchanges + official regional / international bodies
    ("wam.ae", "official", "وكالة أنباء الإمارات (وام)"),
    ("mofa.gov.ae", "official", "وزارة الخارجية الإماراتية"),
    ("mod.gov.ae", "official", "وزارة الدفاع الإماراتية"),
    ("moi.gov.ae", "official", "وزارة الداخلية الإماراتية"),
    ("mof.gov.ae", "official", "وزارة المالية الإماراتية"),
    ("moec.gov.ae", "official", "وزارة الاقتصاد الإماراتية"),
    ("centralbank.ae", "official", "مصرف الإمارات المركزي"),
    ("mediaoffice.abudhabi", "official", "المكتب الإعلامي لحكومة أبوظبي"),
    ("mediaoffice.ae", "official", "المكتب الإعلامي لحكومة دبي"),
    ("u.ae", "official", "البوابة الرسمية لحكومة الإمارات"),
    ("adx.ae", "official", "سوق أبوظبي للأوراق المالية"),
    ("dfm.ae", "official", "سوق دبي المالي"),
    ("gcc-sg.org", "official", "الأمانة العامة لمجلس التعاون"),
    ("news.un.org", "official", "أخبار الأمم المتحدة"),
    ("opec.org", "official", "منظمة أوبك"),
    ("imf.org", "official", "صندوق النقد الدولي"),
    # ---- specialised: economy / energy / defence / regional politics
    ("zawya.com", "specialized", "زاوية"),
    ("argaam.com", "specialized", "أرقام"),
    ("mubasher.info", "specialized", "مباشر"),
    ("asharqbusiness.com", "specialized", "الشرق للأخبار الاقتصادية"),
    ("cnbcarabia.com", "specialized", "CNBC عربية"),
    ("oilprice.com", "specialized", "OilPrice"),
    ("defense-arab.com", "specialized", "الدفاع العربي"),
    ("defensenews.com", "specialized", "Defense News"),
    ("breakingdefense.com", "specialized", "Breaking Defense"),
    ("janes.com", "specialized", "Janes"),
    ("almonitor.com", "specialized", "المونيتور"),
    ("crisisgroup.org", "specialized", "مجموعة الأزمات الدولية"),
    # ---- major agencies and channels
    ("reuters.com", "agency", "رويترز"),
    ("apnews.com", "agency", "أسوشيتد برس"),
    ("bloomberg.com", "agency", "بلومبرغ"),
    ("skynewsarabia.com", "agency", "سكاي نيوز عربية"),
    ("alarabiya.net", "agency", "العربية"),
    ("aljazeera.net", "agency", "الجزيرة"),
    ("bbc.com", "agency", "BBC"),
    ("france24.com", "agency", "فرانس 24"),
    ("arabic.cnn.com", "agency", "CNN بالعربية"),
    ("aa.com.tr", "agency", "الأناضول"),
    ("dw.com", "agency", "DW"),
    # ---- UAE press
    ("alkhaleej.ae", "press", "الخليج"),
    ("albayan.ae", "press", "البيان"),
    ("aletihad.ae", "press", "الاتحاد"),
    ("emaratalyoum.com", "press", "الإمارات اليوم"),
    ("thenationalnews.com", "press", "ذا ناشيونال"),
    ("khaleejtimes.com", "press", "خليج تايمز"),
    ("gulfnews.com", "press", "جلف نيوز"),
]

_BY_DOMAIN = {d: (k, n) for d, k, n in SOURCES}

# Topic filter for sources that publish about the whole world (agencies, specialised outlets): without it a
# `site:` query would return their entire output instead of what matters for the UAE.
TOPIC_FILTER = ('(الإمارات OR الخليج OR "الشرق الأوسط" OR إيران OR هرمز OR "أسعار النفط" OR أوبك '
                'OR UAE OR Gulf OR Hormuz OR "oil prices" OR Iran)')


def host_of(value: str | None) -> str:
    v = (value or "").strip().lower()
    if "://" in v:
        v = v.split("://", 1)[1]
    return v.split("/", 1)[0].split(":", 1)[0].removeprefix("www.")


def lookup(host_or_url: str | None) -> tuple[str, str] | None:
    """(kind, arabic_name) when the host is a registered source (sub-domains match), else None."""
    h = host_of(host_or_url)
    while h:
        hit = _BY_DOMAIN.get(h)
        if hit:
            return hit
        if "." not in h:
            return None
        h = h.split(".", 1)[1]
    return None


def trust_bonus(kind: str | None) -> float:
    return KINDS[kind][1] if kind in KINDS else 0.0


# UAE-based outlets: everything they publish is already UAE news, so their queries carry no topic filter.
_UAE_DOMESTIC_EXTRA = {"emaratalyoum.com", "thenationalnews.com", "khaleejtimes.com", "gulfnews.com", "u.ae"}


def is_uae_domestic(domain: str) -> bool:
    return domain.endswith(".ae") or domain.endswith(".abudhabi") or domain in _UAE_DOMESTIC_EXTRA


def gnews_queries() -> list[tuple[str, str]]:
    """[(query, kind)] — Google News `site:` queries covering every registered domain."""
    out: list[tuple[str, str]] = []
    for kind in ("official", "specialized", "agency", "press"):
        doms = [d for d, k, _ in SOURCES if k == kind]
        for domestic in (True, False):
            group = [d for d in doms if is_uae_domestic(d) == domestic]
            # one query returns at most ~100 items: keep the busiest official feeds from crowding out the rest
            per_query = 6 if (kind == "official" and domestic) else 12
            for i in range(0, len(group), per_query):
                sites = " OR ".join("site:" + d for d in group[i:i + per_query])
                out.append((f"({sites})" if domestic else f"{TOPIC_FILTER} ({sites})", kind))
    return out
