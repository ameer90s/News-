from __future__ import annotations
from typing import Any
import os
import json

TOPIC_AR = {"political": "السياسي", "economic": "الاقتصادي", "military": "العسكري"}

SYSTEM_PROMPT = """
أنت محلل استراتيجي لغرفة أخبار واستخبارات مفتوحة المصدر.
لا تكتفِ بسرد الخبر؛ وسّع مدارك القارئ.
اعتمد فقط على الأخبار المرسلة إليك، وميّز بوضوح بين الحقائق المتاحة والاستنتاجات.
اكتب بالعربية الفصحى المبسطة، بنبرة محلل استراتيجي موجزة وواضحة.
"""


def _scopes_count(events: list[dict]) -> dict[str, int]:
    counts = {"الإمارات": 0, "الشرق الأوسط": 0, "العالم": 0}
    for e in events:
        for s in e.get("scopes", []):
            if s in counts:
                counts[s] += 1
    return counts


def _fallback(topic: str, events: list[dict], history: dict | None = None) -> dict[str, Any]:
    top = events[:6]
    if not top:
        return {
            "headline": f"لا توجد مادة كافية في المجال {TOPIC_AR.get(topic, topic)}",
            "summary": "لم تجمع المنصة مادة كافية ضمن النافذة الزمنية المحددة.",
            "why_it_matters": "غياب التغطية الكافية يجعل أي حكم واسع غير موثوق.",
            "background": "يستحسن توسيع النافذة الزمنية أو إعادة التحديث لاحقًا.",
            "narratives": ["لا توجد روايات كافية للمقارنة."],
            "actors": [],
            "scenarios": ["سيناريو المحافظة على ضبابية الصورة حتى ورود تقارير إضافية."],
            "what_to_watch": ["ورود مصادر إضافية", "تأكيدات رسمية", "تكرار التغطية من منافذ متعددة"],
            "uae_angle": "لا تتوافر مادة كافية لتقدير أثر واضح على الإمارات.",
            "confidence": "أولي",
        }
    scopes = _scopes_count(top)
    highest = top[0]
    uae_hits = [e for e in top if e.get("uae_impact", 0) >= 45]
    militarized = topic == "military"
    economic = topic == "economic"
    political = topic == "political"

    why = []
    if highest["score"] >= 70:
        why.append("لأن الحدث يتصدر من حيث الأهمية وحداثة التغطية وتعدد المصادر")
    if highest["source_count"] >= 3:
        why.append("ولأن عدة مصادر تناولته من زوايا متقاربة أو متكاملة")
    if uae_hits:
        why.append("كما أن له صلة مباشرة أو غير مباشرة بدولة الإمارات أو الخليج")
    if economic:
        why.append("وفي المجال الاقتصادي، تتحول أخبار الطاقة والتجارة والشحن بسرعة إلى أثر أوسع على الأسواق")
    if militarized:
        why.append("وفي المجال العسكري، سرعة التصعيد أو التهدئة تغيّر التقييم خلال ساعات")
    if political:
        why.append("وفي المجال السياسي، اختلاف الروايات بين المصادر قد يكون بحد ذاته مؤشرًا مهمًا")

    narratives = []
    narratives.append("رواية أولى تركز على الحدث المباشر والعنوان العاجل كما تصوغه الوكالات الكبرى.")
    if scopes["الإمارات"]:
        narratives.append("رواية محلية/خليجية تميل إلى إبراز الصلة الإقليمية أو الانعكاس العملي على الدولة والمنطقة.")
    if scopes["العالم"]:
        narratives.append("رواية دولية أوسع تضع الحدث ضمن ميزان القوى أو الاقتصاد العالمي أو الأمن الدولي.")

    actors = sorted({source.split('.')[0] for e in top for source in e.get("sources", [])})[:8]

    scenarios = []
    scenarios.append("سيناريو الاستمرار: بقاء الحدث في صدارة التغطية إذا ظهرت تصريحات جديدة أو تطور ميداني/اقتصادي إضافي.")
    scenarios.append("سيناريو التهدئة: تراجع الأهمية إذا جاءت توضيحات أو تبين أن التطور محدود الأثر.")
    scenarios.append("سيناريو الاتساع: انتقال الخبر من نطاق متخصص إلى أثر سياسي/اقتصادي/أمني أوسع إذا تراكمت أحداث مرتبطة به.")

    watch = []
    watch.append("أي بيان رسمي أو تأكيد مستقل من مصادر إضافية")
    watch.append("هل تتوسع التغطية من نطاق محلي/إقليمي إلى عالمي أو بالعكس")
    if economic:
        watch.extend(["تغير أسعار الطاقة أو الشحن", "رد فعل الأسواق أو السياسات النقدية/التجارية"])
    if militarized:
        watch.extend(["مؤشرات التصعيد أو التهدئة", "تكرار الحديث عن وقف إطلاق نار أو ضربات أو تحركات عسكرية"])
    if political:
        watch.extend(["نتائج القمم أو المفاوضات", "مواقف الحكومات والوزراء والبرلمانات"])

    history_note = ""
    if history:
        history_note = f" المنصة تحتفظ أيضًا بسجل تاريخي؛ المتوافر حاليًا نحو {history.get('article_count', 0)} مادة من {history.get('source_count', 0)} مصدر خلال آخر 90 يومًا."

    uae = ""
    if uae_hits:
        uae = "تظهر زاوية الإمارات هنا كإضافة تحليلية: قد يكون الأثر مباشرًا إذا تعلق الحدث بالطاقة أو التجارة أو الملاحة أو المجال الجوي أو الخليج، وغير مباشر إذا كان الحدث جزءًا من تحولات جيوسياسية أو مالية أوسع."
    else:
        uae = "لا يبدو الحدث في صيغته الحالية ذا صلة إماراتية مباشرة عالية، لكن قد تنشأ صلته إذا توسعت تداعياته إقليميًا أو عالميًا."

    return {
        "headline": highest["title"],
        "summary": f"في المجال {TOPIC_AR.get(topic, topic)}، يتصدر حاليًا حدث: {highest['title']}. التغطية الأهم موزعة بين الإمارات ({scopes['الإمارات']})، والشرق الأوسط ({scopes['الشرق الأوسط']})، والعالم ({scopes['العالم']}).{history_note}",
        "why_it_matters": "، ".join(why) if why else "لأنه يمثل نقطة تركيز في التغطية الحالية ويمكن أن يكشف اتجاهًا أوسع من مجرد عنوان منفرد.",
        "background": "الهدف هنا ليس متابعة الخبر كواقعة معزولة، بل وضعه ضمن صورة أكبر: هل هو بداية مسار؟ هل هو امتداد لملف قائم؟ وهل يعكس توترًا أو تحولًا في السياسة أو الاقتصاد أو الأمن؟",
        "narratives": narratives,
        "actors": actors,
        "scenarios": scenarios,
        "what_to_watch": watch[:6],
        "uae_angle": uae,
        "confidence": "متوسط" if highest["confidence"] != "أولي" else "أولي",
    }


def _compact(events: list[dict]) -> list[dict]:
    payload = []
    for e in events[:8]:
        payload.append({
            "title": e.get("title"),
            "score": e.get("score"),
            "confidence": e.get("confidence"),
            "uae_impact": e.get("uae_impact"),
            "sources": e.get("sources", []),
            "scopes": e.get("scopes", []),
            "articles": [{"title": a.get("title"), "domain": a.get("domain"), "seen_at": a.get("seen_at")} for a in e.get("articles", [])[:4]],
        })
    return payload


def analyze_topic(topic: str, events: list[dict], history: dict | None = None) -> dict[str, Any]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return _fallback(topic, events, history)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        prompt = f"""
حلل المجال: {TOPIC_AR.get(topic, topic)}

أعد JSON فقط بالمفاتيح التالية:
{{
  "headline": "...",
  "summary": "...",
  "why_it_matters": "...",
  "background": "...",
  "narratives": ["..."],
  "actors": ["..."],
  "scenarios": ["..."],
  "what_to_watch": ["..."],
  "uae_angle": "...",
  "confidence": "مرتفع|متوسط|أولي"
}}

قيود:
- لا تختلق معلومات غير موجودة.
- التحليل يوسع المدارك ولا يكتفي بإعادة صياغة العناوين.
- زاوية الإمارات جزء إضافي فقط.
- ميّز ضمنيًا بين الخبر المؤكد والاستنتاج.

البيانات: {json.dumps(_compact(events), ensure_ascii=False)}
السجل التاريخي: {json.dumps(history or {}, ensure_ascii=False)}
"""
        response = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), instructions=SYSTEM_PROMPT, input=prompt)
        text = (getattr(response, 'output_text', '') or '').strip()
        return json.loads(text)
    except Exception:
        return _fallback(topic, events, history)
