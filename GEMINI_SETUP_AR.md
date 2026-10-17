# تفعيل Gemini API — مرصد الإمارات الذكي

## 1) إنشاء المفتاح
1. افتح Google AI Studio.
2. افتح صفحة **API Keys**.
3. اختر **Create API key** وأنشئ مفتاحًا للمشروع.
4. انسخ المفتاح ولا تضعه داخل GitHub.

## 2) وضع المفتاح في Vercel
من مشروع Vercel:
**Settings → Environment Variables**

أضف:
- Name: `GEMINI_API_KEY`
- Value: المفتاح الذي نسخته من Google AI Studio
- Environments: Production + Preview + Development (أو Production فقط إذا رغبت)

اختياري:
- `GEMINI_MODEL` = `gemini-3.8-flash`
- `AI_TIMEOUT_SECONDS` = `8`

بعد الحفظ نفّذ **Redeploy** لآخر Deployment.

## 3) التأكد من التشغيل
افتح بعد النشر:
`/api/health`

المطلوب أن يظهر:
```json
"ai": {
  "enabled": true,
  "provider": "gemini",
  "model": "gemini-3.8-flash"
}
```

ثم افتح الصفحة الرئيسية. الأخبار تظهر أولًا، وبعدها Gemini يحسن الصورة الكبرى وتحليلات السياسي والاقتصادي والعسكري.

## إذا لم يعمل Gemini
الموقع لن يتعطل. سيستخدم التحليل المحلي تلقائيًا في الحالات التالية:
- المفتاح غير موجود أو غير صالح.
- انتهت الحصة المجانية أو ظهر Rate Limit.
- انقطع اتصال Gemini أو انتهت المهلة.

## الأمان
- لا تضع `GEMINI_API_KEY` في `app.js` أو `index.html`.
- لا ترفعه إلى GitHub.
- المشروع يرسل المفتاح من FastAPI إلى Gemini في Header على السيرفر فقط.
