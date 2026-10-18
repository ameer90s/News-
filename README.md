# مرصد الإمارات الذكي — Fresh Build
هذا المشروع بُني من الصفر ولا يعتمد على أي إصدار سابق.

## Vercel
1. ارفع محتويات المجلد إلى GitHub.
2. اربط المستودع بـ Vercel.
3. أضف Environment Variable باسم `GEMINI_API_KEY`.
4. اختياري: `GEMINI_MODEL` (الافتراضي في الكود: `gemini-2.5-flash`).
5. Deploy.

## السلوك
- الأخبار العربية تُجلب من Google News Arabic UAE RSS، ولا تُعرض العناوين غير العربية.
- الأخبار تظهر قبل تحليل Gemini.
- إذا فشل Gemini يبقى الموقع والأخبار يعملان مع تحليل محلي fallback.
- API routes غير مخزنة في Service Worker.
- لا يوجد زر Install ويتم منع beforeinstallprompt.
