"""Unit checks for story grouping + ranking (offline, pure functions). Usage: python3 story_test.py <project>"""
import sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, sys.argv[1])
from core import sources as S

now = datetime(2026, 10, 25, 19, 10, tzinfo=timezone.utc)
def ago(h): return now - timedelta(hours=h)
n = 0
def raw(title, hrs, src, host, hint=None):
    global n; n += 1
    return {"title": title, "url": f"https://{host}/a/{n}", "source": src, "published": ago(hrs), "hint": hint, "host": host}

story = [  # the nomination story, wording differs per outlet / day
    raw("لانا نسيبة مرشحة من الإمارات لمنصب الأمين العام للأمم المتحدة", 90, "بحرين المستقبل", "bhfuture.net"),
    raw("ترحيب دولي بترشيح لانا نسيبة لمنصب الأمين العام للأمم المتحدة", 60, "سكاي نيوز عربية", "skynewsarabia.com"),
    raw("الأمم المتحدة: عملية اختيار الأمين العام مستمرة وسط ترقب لمرشحين جدد", 30, "الأمم المتحدة", "news.un.org"),
    raw("نسيبة تتحدث عن رؤيتها لمنصب الأمين العام في حال انتخابها", 12, "الاتحاد", "aletihad.ae"),
    raw("تصريحات متبادلة حول ترشيح الإمارات لانا نسيبة لقيادة الأمم المتحدة", 3, "العربية", "alarabiya.net"),
]
others = [
    raw("ترامب يفرض تعريفات جمركية جديدة على واردات الصين", 5, "رويترز", "reuters.com"),
    raw("ترامب يلتقي قادة الكونغرس لبحث الميزانية الفيدرالية", 6, "العربية", "alarabiya.net"),
    raw("الصين ترد على التعريفات الأمريكية بإجراءات مماثلة", 4, "الجزيرة", "aljazeera.net"),
    raw("دبي تعلن خطة جديدة لتوسيع شبكة المترو لتشمل مناطق إضافية", 8, "البيان", "albayan.ae"),
    raw("أبوظبي تطلق مبادرة جديدة لدعم الشركات الناشئة في قطاع التقنية", 9, "الاتحاد", "aletihad.ae"),
    raw("الشارقة تعلن افتتاح معرض الكتاب الدولي بمشاركة دور نشر عالمية", 10, "الخليج", "alkhaleej.ae"),
    raw("دبي تستقبل أكثر من مليون زائر خلال أسبوع جيتكس", 11, "البيان", "albayan.ae"),
    raw("قلق دولي من تصاعد التوتر في مضيق هرمز وتأثيره على حركة الملاحة", 7, "العربية", "alarabiya.net"),
    raw("ارتفاع أسعار النفط مع تصاعد التوتر قرب مضيق هرمز", 6, "بلومبرغ", "bloomberg.com"),
    raw("مصرف الإمارات المركزي يثبّت أسعار الفائدة دون تغيير", 14, "الاتحاد", "aletihad.ae"),
    raw("الفيدرالي الأمريكي يبقي أسعار الفائدة دون تغيير ويشير إلى حذر", 13, "سي إن بي سي", "cnbcarabia.com"),
    raw("الجيش الإماراتي يشارك في مناورات مشتركة مع دول حليفة", 15, "وام", "wam.ae"),
    raw("اليمن: جهود أممية لتجديد الهدنة وتخفيف الأزمة الإنسانية", 16, "الأمم المتحدة", "news.un.org"),
    raw("العراق يعلن خطة لزيادة صادرات النفط عبر الموانئ الجنوبية", 17, "الشرق الأوسط", "aawsat.com"),
    raw("ريال مدريد يفوز على برشلونة في مباراة الكلاسيكو", 18, "الرياضية", "sports.example"),
    raw("وزير الخارجية الإماراتي يلتقي رئيس الوزراء الهندي في أبوظبي", 20, "وام", "wam.ae"),
    raw("وزير الخارجية السعودي يلتقي نظيره الإيراني في الرياض", 21, "العربية", "alarabiya.net"),
    raw("أمطار غزيرة تضرب عدة مناطق في الدولة وتحذيرات من السيول", 22, "الخليج", "alkhaleej.ae"),
    raw("ارتفاع أسعار الذهب إلى مستويات قياسية جديدة", 23, "مباشر", "mubasher.info"),
    raw("الإمارات والهند توقعان اتفاقية جديدة للتعاون التجاري", 24, "وام", "wam.ae"),
] + [raw(w, 2 + i, "الخليج", "alkhaleej.ae") for i, w in enumerate([
    "افتتاح مركز تسوق جديد في مدينة العين", "ورشة للأطفال حول الرسم في مكتبة الشارقة العامة", "حملة تطوعية لتنظيف شواطئ رأس الخيمة",
    "انطلاق مهرجان التمور في ليوا بمشاركة مزارعين", "مباراة ودية لفريق الشباب على ملعب راشد", "صيانة دورية لجسور الطرق الرئيسية في عجمان",
    "افتتاح حديقة عامة جديدة في أم القيوين", "دورة تدريبية لتعليم البرمجة للطلبة الموهوبين", "معرض فني يستعرض تراث الصيد البحري القديم",
    "زيادة ساعات عمل المكتبات خلال فترة الامتحانات", "إطلاق تطبيق لحجز مواقف السيارات في وسط المدينة", "سباق الهجن السنوي ينطلق نهاية الأسبوع",
    "توزيع وجبات إفطار على العمال في المناطق الصناعية", "تكريم متطوعين ساهموا في حملات التبرع بالدم", "ندوة عن الأمن السيبراني للشركات الصغيرة",
    "تجربة حافلات كهربائية على خط الكورنيش", "ساعات عمل جديدة لمراكز الخدمة الحكومية", "عرض مسرحي للأطفال في قصر الثقافة",
    "افتتاح فرع جديد لمستشفى متخصص في الأمراض الجلدية", "ملتقى للمستثمرين العقاريين يناقش مشاريع الواجهة البحرية"])]

items = S.build_items(story + others, 72, now)
by_title = {}
fails = 0
def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name, "" if cond else extra)
    if not cond: fails += 1

nus = [i for i in items if any("نسيبة" in s["title"] for s in i["sources"])]
check("the 4 in-window nomination headlines collapse into ONE story (the 90h-old one is outside 72h)", len(nus) == 1 and nus[0]["updates"] == 4, [(i["title"][:30], i["updates"]) for i in nus])
st = nus[0]
print("   story:", st["title"], "| impact", st["uae_impact"], "| why:", st["why"], "| rank", items.index(st) + 1, "of", len(items))
check("story shows the NEWEST headline", "تصريحات متبادلة" in st["title"])
check("story impact is at least mid (judged by its strongest headline)", st["uae_impact"] >= 55, st["uae_impact"])
check("story ranks in the top 5", items.index(st) < 5, items.index(st))
check("story carries a Gemini-independent reason line", bool(st["why"]))
rate = [i for i in items if any("الفائدة" in s["title"] for s in i["sources"])]
check("Fed rate hold and UAE central-bank rate hold stay SEPARATE stories", len(rate) == 2, [(i["title"][:30], i["updates"]) for i in rate])
items90 = S.build_items(story + others, 120, now)
nus90 = [i for i in items90 if any("نسيبة" in s["title"] for s in i["sources"])]
check("with a 120h window all 5 nomination headlines merge into one story", len(nus90) == 1 and nus90[0]["updates"] == 5, [(i["title"][:30], i["updates"]) for i in nus90])
trump = [i for i in items if any("التعريفات" in s["title"] or "تعريفات" in s["title"] for s in i["sources"])]
check("tariff headlines (same subject) group together", len(trump) == 1 and trump[0]["updates"] >= 2, [(i["title"][:30], i["updates"]) for i in trump])
cong = [i for i in items if any("الكونغرس" in s["title"] for s in i["sources"])]
check("unrelated Trump/Congress headline is NOT merged into the tariff story", len(cong) == 1 and cong[0]["updates"] == 1, [(i["title"][:30], i["updates"]) for i in cong])
hormuz = [i for i in items if any("هرمز" in s["title"] for s in i["sources"])]
check("Hormuz headlines merge into one story", len(hormuz) == 1 and hormuz[0]["updates"] == 2, [(i["title"][:30], i["updates"]) for i in hormuz])
fm = [i for i in items if any("وزير الخارجية" in s["title"] for s in i["sources"])]
check("two different foreign-minister meetings are NOT merged", len(fm) == 2, [(i["title"][:40], i["updates"]) for i in fm])
metro = [i for i in items if any("المترو" in s["title"] for s in i["sources"])][0]
check("trivial local news stays low and below the nomination story", metro["uae_impact"] <= 33 and items.index(metro) > items.index(st), (metro["uae_impact"], items.index(metro)))
sport = [i for i in items if any("ريال مدريد" in s["title"] for s in i["sources"])][0]
check("sports item stays very low", sport["uae_impact"] <= 15, sport["uae_impact"])
FILL = ["مركز تسوق", "ورشة للأطفال", "حملة تطوعية", "مهرجان التمور", "مباراة ودية", "صيانة دورية", "حديقة عامة", "دورة تدريبية", "معرض فني", "ساعات العمل", "تطبيق لحجز", "الهجن", "وجبات إفطار", "متطوعين", "الأمن السيبراني", "حافلات كهربائية", "مراكز الخدمة", "عرض مسرحي", "مستشفى متخصص", "ملتقى للمستثمرين"]
filler = [i for i in items if any(f in i["title"] for f in FILL)]
check("20 unrelated local filler headlines stay separate", all(i["updates"] == 1 for i in filler), max(i["updates"] for i in filler))
big = [i for i in items if i["updates"] > 6]
check("no story grows beyond 6 updates here", not big, [(i["title"][:30], i["updates"]) for i in big])

# --- the same articles returned by many queries (very common live: UAE query + registry + impact queries) must not
# hide the distinctive words of a story
import copy
dup = list(story + others)
for rep in range(8):
    dup += [dict(r, hint=("international" if rep % 2 else "local")) for r in story + others]
itemsD = S.build_items(dup, 72, now)
nusD = [i for i in itemsD if any("نسيبة" in s["title"] for s in i["sources"])]
check("duplicates across 9 queries: nomination story still ONE story with 4 updates", len(nusD) == 1 and nusD[0]["updates"] == 4, [(i["title"][:30], i["updates"]) for i in nusD])
check("duplicates across queries: same number of stories as with single copies", len(itemsD) == len(items), (len(itemsD), len(items)))
print("\ntop 10:")
for k, i in enumerate(items[:10], 1):
    print(f" {k:2d}. [{i['uae_impact']:3d}] imp={i['importance']:6.2f} upd={i['updates']} {i['scope'][:3]} | {i['title'][:62]}")
print("\nFAILS:", fails)
sys.exit(1 if fails else 0)
