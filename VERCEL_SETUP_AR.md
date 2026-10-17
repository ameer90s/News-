# خطوات Vercel المختصرة

1. GitHub: ارفعي **المحتويات داخل المجلد** وليس ملف ZIP.
2. Vercel → Add New → Project → اختاري الـ Repository → Deploy.
3. داخل المشروع: Storage/Marketplace → Neon → Create → Connect.
4. تأكدي أن Neon متصل ببيئة **Production**.
5. Vercel → Settings → Environment Variables: أضيفي `OPENAI_API_KEY` إذا تبين التحليل بالذكاء الاصطناعي.
6. Redeploy.
7. افتحي `/api/health` وتحققي أن `database` = `postgresql`.

لا تحتاجين Railway، ولا Start Command، ولا `Procfile`.
