# QA Report — UAE Smart Observatory Gemini v11

## ما تغيّر
- تقوية Glass للأقسام الرئيسية مع إبقاء الخلفية مرئية.
- جعل شريط التنقل السفلي أغمق حتى لا يختلط مع النص خلفه.
- تلوين تأثير سياسي/اقتصادي/عسكري حسب `uae_impact`: منخفض أخضر، متوسط أصفر، مرتفع أحمر.
- تحسين بطاقات التحليل المتكامل بهرمية أبسط وحد علوي بلون التأثير.
- إبقاء رقم الأهمية بجانب عنوان الخبر على الجوال بدل تحويله لشريط كامل.
- تعريب عناوين الأحداث عبر Gemini مع الحفاظ على عناوين المصادر الأصلية داخل قسم المصادر القابل للفتح.
- استبدال BIG PICTURE BRIEF بـ "الصورة الكبرى".

## Gemini
- النموذج الافتراضي: `gemini-3.8-flash`.
- المفتاح يبقى في Vercel فقط تحت `GEMINI_API_KEY`.
- طلب REST يستخدم `systemInstruction` و`generationConfig.responseMimeType=application/json`.
- لا يوجد Gemini SDK أو Google Search Grounding.
- Gemini يعيد الترجمات + الصورة الكبرى + التحليلات في طلب واحد.
- Cache للـAI لمدة 10 دقائق ومفتاح cache جديد V11.
- إذا تعطل Gemini، جلب الأخبار نفسه لا يتوقف.

## اختبارات منفذة
- Python: `app.py` و`main.py` compile بنجاح.
- JavaScript: `app.js` و`sw.js` syntax check بنجاح.
- Gemini request mock: تحقق من endpoint، `systemInstruction`، JSON output، والترجمات.
- News engine mock: 15 مادة، والمجالات الثلاثة ممتلئة.
- Fallback: تعطيل GDELT بالكامل واستمرار Google News RSS بـ 6 مواد.
- Responsive Playwright: 412px و360px و320px بلا horizontal overflow.
- العنوان: سطر واحد؛ 29.99px على 412px.
- الوصف: سطر واحد على المقاسات الثلاثة.
- آخر عناصر التحكم قبل 180px: 148.17px على 412px، و140.5px على 360/320.
- أزرار المدة الخمسة كاملة داخل الشاشة على 412/360/320.
- Spinner: `جاري التحديث...` + disabled + no overflow.
- 48 ساعة: اللون النشط `rgba(155,231,255,0.22)` والحد `rgba(155,231,255,0.6)`.
- AI mock: الصورة الكبرى و6 عناوين أخبار ظاهرة كلها بالعربية في الاختبار.
- قبل وصول AI: العناوين الإنجليزية لا تظهر للمستخدم؛ يظهر مؤقتًا "جاري تعريب الخبر…".
- بطاقات التأثير: 82%=مرتفع أحمر، 58%=متوسط أصفر، 22%=منخفض أخضر.
- لا يوجد زر Install.
- لا توجد مسارات `/static/`.
- `background.webp`, `main.py`, `vercel.json`, `requirements.txt`, `pyproject.toml`, `icon.svg`, `manifest.webmanifest` لم تتغير Byte-for-Byte عن v10.
- Service Worker cache: `strategic-newsroom-v11`; CSS/JS query version = 11.
