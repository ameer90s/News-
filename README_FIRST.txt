هذه نسخة تشخيصية مصححة لـ Vercel ولا تحتاج أي Environment Variables.

المهم عند الرفع:
1) main.py و pyproject.toml و vercel.json يجب أن تكون في جذر المشروع نفسه، وليست داخل مجلد إضافي.
2) لا تضبط Root Directory على مجلد فرعي. اتركها فارغة / Project Root.
3) Deploy مباشرة بدون Variables.
4) جرّب /api/health أولاً. المفروض يظهر status=ok و entrypoint=main:app.

هذه النسخة تستخدم تحليل داخلي ولا تستخدم قاعدة بيانات أو OpenAI أثناء الاختبار.
بعد التأكد أن Vercel يشتغل، نرجع PostgreSQL وOpenAI بدون المساس بالواجهة.
