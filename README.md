# مرصد الإمارات الذكي — Fresh Rebuild

هذا المشروع بُني من الصفر ولا يعتمد على أي نسخة سابقة.

## الرفع على Vercel
1. ارفع **محتويات هذا المجلد إلى جذر GitHub مباشرة**. يجب أن يظهر `app.py` و`requirements.txt` في جذر المستودع.
2. اربط المستودع بـ Vercel. لا تضف `vercel.json`؛ Vercel يدعم FastAPI تلقائياً.
3. في Vercel → Project Settings → Environment Variables أضف:
   - `GEMINI_API_KEY` = مفتاح Gemini من Google AI Studio.
   - اختياري: `GEMINI_MODEL` = `gemini-3.8-flash`.
4. أعد Deploy.

## فحص سريع بعد النشر
- `/` يجب أن يفتح الواجهة.
- `/api/health` يجب أن يعيد JSON وفيه `"ok": true`.
- `/api/news?hours=24` يجب أن يعيد JSON للأخبار (قد تختلف النتائج حسب توفر مصادر الأخبار).

## ملاحظات
- الأخبار تظهر قبل تحليل Gemini.
- إذا فشل Gemini، يبقى المرصد والأخبار يعملان ويظهر تحليل محلي بدون شارة AI.
- الواجهة لا تعرض عنوان خبر إنجليزي؛ الأخبار غير العربية تُستبعد من الواجهة.
- `sw.js` لا يخزن `/api/` في الكاش.
- لا يوجد زر تثبيت، ويتم منع `beforeinstallprompt` في الواجهة.
