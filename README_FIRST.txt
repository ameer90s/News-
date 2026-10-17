مرصد الإمارات الذكي — GitHub + Vercel + Gemini AI

طريقة الرفع السريعة:
1) ارفع جميع ملفات هذا المجلد إلى ROOT في مستودع GitHub (بدون مجلد فرعي).
2) في Vercel اختر Add New > Project ثم Import للمستودع ثم Deploy. الأخبار تعمل حتى بدون AI.
3) لتفعيل Gemini: Vercel > Project > Settings > Environment Variables
   أضف: GEMINI_API_KEY = المفتاح من Google AI Studio
   اختياري: GEMINI_MODEL = gemini-3.8-flash
   اختياري: AI_TIMEOUT_SECONDS = 8
   ثم اضغط Redeploy.

فحص سريع بعد النشر:
- افتح /api/health وتأكد أن ai.enabled = true و ai.provider = gemini.
- الصفحة الرئيسية يجب أن تعرض الأخبار أولًا، ثم يحسن Gemini الصورة الكبرى والتحليلات.

مهم:
- لا تضع GEMINI_API_KEY داخل GitHub أو app.js أو index.html.
- إذا انتهت الحصة المجانية أو تعطل Gemini، الأخبار والتحليل المحلي يستمران تلقائيًا.
- المشروع يستخدم Gemini عبر HTTPS مباشرة، لذلك لا يحتاج Google SDK ولا حزم إضافية.
