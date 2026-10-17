# مرصد الإمارات الذكي — GitHub + Vercel + Gemini Free Tier

## 1) GitHub
ارفع **كل الملفات** إلى جذر المستودع مباشرة. لا تنشئ مجلد `static` أو `api`.

## 2) Vercel
- **Add New → Project**
- Import لمستودع GitHub
- **Deploy** بالإعدادات الحالية.

## 3) مفتاح Gemini
أنشئ مفتاحًا من **Google AI Studio → API keys**، ثم في Vercel افتح:
**Project → Settings → Environment Variables**

أضف:
- `GEMINI_API_KEY` = مفتاح Gemini

اختياريًا:
- `GEMINI_MODEL` = `gemini-3.8-flash`
- `AI_TIMEOUT_SECONDS` = `8`

ثم نفّذ **Redeploy**.

> المفتاح يبقى على السيرفر فقط. لا تضعه في GitHub أو JavaScript.

## 4) التأكد
بعد النشر افتح `/api/health`. عند ضبط المفتاح يجب أن ترى:
- `ai.enabled: true`
- `ai.provider: gemini`
- `ai.model: gemini-3.8-flash`

## طريقة العمل
- الأخبار: GDELT + Google News RSS.
- الترتيب والتحليل الاحتياطي: محلي داخل FastAPI.
- Gemini: طلب واحد اختياري بعد ظهور الأخبار لتحسين Big Picture وتحليلات السياسي/الاقتصادي/العسكري.
- إذا فشل Gemini أو انتهت الحصة أو لم يوجد مفتاح: الموقع يستمر بالتحليل المحلي ولا تتوقف الأخبار.
- يوجد Cache للـAI في المتصفح لمدة 10 دقائق لنفس مجموعة الأحداث.

## ملاحظة الفئة المجانية
`gemini-3.8-flash` مدرج حاليًا ضمن Free Tier في Gemini Developer API، لكن حدود الاستخدام والأهلية مرتبطة بمشروع Google/الحساب وقد تتغير. البرنامج لا يستخدم Google Search Grounding، لذلك لا يعتمد على حصة أداة البحث المدفوعة.
