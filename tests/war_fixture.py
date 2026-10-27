"""A realistic 'war-cycle' news batch modelled on 27 Oct 2026: the same few events reported by many outlets with different wording,
plus unrelated filler. EVENTS maps an event key -> list of (hours_ago, headline, outlet, host, hint)."""
from datetime import datetime, timedelta, timezone

now = datetime(2026, 10, 27, 3, 0, tzinfo=timezone.utc)

EVENTS = {
    "strike96": [
        (2, "ترامب يقترب من قرار بشأن إيران وتقارير عن جاهزية للضرب خلال 96 ساعة", "العربية", "alarabiya.net", None),
        (3, "CNN: القوات الأمريكية قادرة على تنفيذ عمليات كبيرة ضد إيران خلال 96 ساعة من الأمر", "سكاي نيوز عربية", "skynewsarabia.com", None),
        (5, "ترامب: هدنة أبريل كانت مضيعة للوقت والقرار بشأن إيران قريب", "الشرق الأوسط", "aawsat.com", None),
        (6, "واشنطن تدرس ضرب منشآت الطاقة والمنشآت النووية الإيرانية خلال 96 ساعة", "الجزيرة", "aljazeera.net", None),
        (7, "حاملة طائرات أمريكية ثالثة تتجه إلى المنطقة وسط ترقب قرار ضرب إيران", "الاتحاد", "aletihad.ae", "regional"),
        (4, "Trump nears decision on Iran as US forces ready for strikes within 96 hours, CNN reports", "CNN", "cnn.com", "international"),
        (8, "US military could launch major operation against Iran within 96 hours of an order, officials say", "Reuters", "reuters.com", "international"),
    ],
    "hormuz": [
        (3, "رئيس الأركان الإيراني يعلن السيطرة الكاملة على مضيق هرمز ويحذر السفن المخالفة", "العربية", "alarabiya.net", None),
        (4, "عبداللهي: مضيق هرمز مغلق إلا للسفن الملتزمة بالقواعد الإيرانية", "الخليج", "alkhaleej.ae", None),
        (5, "UKMTO تبلغ عن حريق في سفينة قبالة الفاو العراقية قرب مضيق هرمز", "سكاي نيوز عربية", "skynewsarabia.com", None),
        (9, "قلق دولي من تصاعد التوتر في مضيق هرمز وتأثيره على حركة الملاحة", "الشرق الأوسط", "aawsat.com", None),
        (10, "حركة السفن في هرمز دون ثلث المعتاد وسط مخاوف على الإمدادات", "الجزيرة", "aljazeera.net", None),
        (6, "Iran says it has full control of Strait of Hormuz, warns violating ships", "Reuters", "reuters.com", "international"),
    ],
    "houthi_ksa": [
        (2, "اعتراض صاروخ باليستي نحو الرياض وثلاثة صواريخ باتجاه المنطقة الشرقية", "العربية", "alarabiya.net", None),
        (3, "السعودية تعترض صاروخاً حوثياً وثلاث طائرات مسيّرة", "الاتحاد", "aletihad.ae", None),
        (5, "الحوثيون يدّعون استهداف مطار الرياض ومحطات ضخ نفطية", "الجزيرة", "aljazeera.net", None),
        (6, "الحوثيون يزعمون استهداف محطات ضخ خط الأنابيب شرق غرب في السعودية", "الشرق الأوسط", "aawsat.com", None),
        (7, "التحالف: تدمير خمسة أنفاق صواريخ وست منصات إطلاق حوثية", "سكاي نيوز عربية", "skynewsarabia.com", None),
        (8, "Saudi Arabia intercepts Houthi ballistic missile aimed at Riyadh and drones", "Arab News", "arabnews.com", "regional"),
    ],
    "oil_price": [
        (2, "برنت يستقر عند 115.81 دولاراً مع آمال تخفيف التوتر", "العربية", "alarabiya.net", None),
        (3, "النفط يتراجع بعد مكاسب أسبوعية بلغت 6% وسط ترقب محادثات طهران", "الشرق الأوسط", "aawsat.com", None),
        (4, "أسعار النفط تتراجع مع آمال خفض التصعيد بين واشنطن وطهران", "سكاي نيوز عربية", "skynewsarabia.com", None),
        (5, "مربان يصعد 3.16% إلى نحو 118 دولاراً وترقب أسعار الوقود لنوفمبر", "الخليج", "alkhaleej.ae", "local"),
        (6, "Oil steadies near $116 as hopes grow for Iran talks", "Reuters", "reuters.com", "international"),
        (7, "Brent crude eases 0.8% after weekly gain of 6% as traders watch US-Iran talks", "Bloomberg", "bloomberg.com", "international"),
    ],
    "uae_markets": [
        (2, "سوقا دبي وأبوظبي يتعافيان بعد أدنى إغلاق منذ يونيو", "الاتحاد", "aletihad.ae", "local"),
        (3, "مؤشر دبي يرتفع 0.3% وأبوظبي 0.6% بدعم سالك والدار وبنك أبوظبي التجاري", "البيان", "albayan.ae", "local"),
        (4, "ارتفاع الأسهم الإماراتية في ختام التعاملات وسط ترقب لقرار الفيدرالي", "الخليج", "alkhaleej.ae", "local"),
        (6, "UAE stocks rebound after lowest close since June", "Gulf News", "gulfnews.com", "local"),
    ],
    "ottawa": [
        (4, "ولي عهد أبوظبي يصل إلى أوتاوا في زيارة رسمية للقاء كارني", "وام", "wam.ae", "local"),
        (5, "محمد بن زايد وكارني يبحثان تعزيز الشراكة الاقتصادية بين الإمارات وكندا", "الاتحاد", "aletihad.ae", "local"),
        (6, "الإمارات وكندا: تجارة بقيمة 4.2 مليار دولار والشراكة الاقتصادية الشاملة على الطاولة", "البيان", "albayan.ae", "local"),
    ],
    "israel_vote": [
        (3, "الإسرائيليون يصوتون اليوم في انتخابات متقاربة بين نتنياهو وآيزنكوت", "الجزيرة", "aljazeera.net", None),
        (5, "انتخابات إسرائيل: نتنياهو وآيزنكوت في سباق محتدم والنتائج قد تتأخر أياماً", "العربية", "alarabiya.net", None),
        (8, "تقارير عن خلاف داخل المؤسسة الأمنية الإسرائيلية حول خطة لضرب إيران قبل الاقتراع", "الشرق الأوسط", "aawsat.com", None),
    ],
    "spill": [
        (5, "صور أقمار صناعية تظهر اتساع التسرب النفطي نحو ساحل أم القيوين", "الخليج", "alkhaleej.ae", "local"),
        (7, "تسرب نفطي قرب أم القيوين والسلطات لم تسمِّ المصدر بعد", "البيان", "albayan.ae", "local"),
    ],
}

FILLER = [  # unrelated, single-story headlines (different topics so they must stay separate)
    ("الكويت تحكم بالإعدام على ثلاثة في قضية مؤامرة لاغتيال نائب رئيس الوزراء", "العربية", "alarabiya.net", None, 9),
    ("بوتين يلتقي الرئيس الإيراني وأمير قطر في موسكو على هامش منتدى الدول المصدرة للغاز", "الجزيرة", "aljazeera.net", None, 11),
    ("قصف روسي على كييف يصيب سكناً جامعياً ويقتل شخصاً", "الشرق الأوسط", "aawsat.com", None, 12),
    ("أبولو تستحوذ على حصة أقلية في مبادلة كابيتال", "الاتحاد", "aletihad.ae", "local", 10),
    ("حمدان بن محمد يرفع أهداف حرم دبي للذكاء الاصطناعي إلى ألف شركة بحلول 2030", "وام", "wam.ae", "local", 13),
    ("عبدالله بن زايد ووزير الخارجية المصري يبحثان هاتفياً التطورات الإقليمية", "وام", "wam.ae", "local", 6),
    ("الغاز الأوروبي يبلغ أعلى مستوى منذ 2022 مع اقتراب الشتاء", "بلومبرغ الشرق", "asharqbusiness.com", "international", 14),
    ("وول ستريت ترتفع بدعم التكنولوجيا وعائد العشر سنوات عند 5%", "سي إن بي سي عربية", "cnbcarabia.com", "international", 15),
    ("Helsing unveils Contra counter-drone system with two interceptor missiles", "Breaking Defense", "breakingdefense.com", "international", 16),
    ("دبي تعلن خطة جديدة لتوسيع شبكة المترو لتشمل مناطق إضافية", "البيان", "albayan.ae", "local", 17),
    ("ريال مدريد يفوز على برشلونة في مباراة الكلاسيكو", "الرياضية", "sports.example", None, 18),
    ("أمطار غزيرة تضرب عدة مناطق في الدولة وتحذيرات من السيول", "الخليج", "alkhaleej.ae", "local", 19),
    ("مصر: البرلمان يفوض السيسي بتقديم دعم عسكري للسعودية عند طلبها", "الأهرام", "ahram.org.eg", "regional", 8),
    ("وفد سعودي باكستاني تركي يلتقي بزشكيان ورضائي في طهران", "الشرق الأوسط", "aawsat.com", "regional", 7),
]


def build_raw():
    raw, n = [], 0
    truth = {}
    for ev, rows in EVENTS.items():
        for h, title, src, host, hint in rows:
            n += 1
            url = f"https://{host}/a/{n}"
            raw.append({"title": title, "url": url, "source": src, "published": now - timedelta(hours=h), "hint": hint, "host": host})
            truth[url] = ev
    for title, src, host, hint, h in FILLER:
        n += 1
        url = f"https://{host}/a/{n}"
        raw.append({"title": title, "url": url, "source": src, "published": now - timedelta(hours=h), "hint": hint, "host": host})
        truth[url] = "filler:" + str(n)
    return raw, truth
