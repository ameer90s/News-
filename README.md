# Strategic Newsroom & Intelligence Room — Vercel + PostgreSQL

هذه النسخة جاهزة للنشر على **Vercel** مباشرة باستخدام FastAPI/Python، مع **PostgreSQL (Neon) في الإنتاج** وSQLite محليًا للتجربة.

## البنية

- `main.py` — نقطة دخول Vercel/FastAPI.
- `app/main.py` — API + تقديم واجهة الـ PWA.
- `app/db.py` — يختار قاعدة البيانات تلقائيًا:
  - إذا وُجد `DATABASE_URL` → PostgreSQL.
  - إذا لم يوجد محليًا → SQLite.
  - على Vercel بدون `DATABASE_URL` يوجد fallback مؤقت في `/tmp` فقط، وغير مناسب للتاريخ طويل المدى.
- `app/static/` — الواجهة والخلفية والـ PWA.
- `pyproject.toml` — Python 3.12+ واعتماديات Vercel.

## النشر على Vercel

1. ارفعي محتويات هذا المجلد إلى GitHub.
2. في Vercel اختاري **Add New → Project** ثم Import للـ GitHub repository.
3. لا تحتاجين Start Command ولا Railway config؛ Vercel يدعم FastAPI مباشرة.
4. بعد إنشاء المشروع، أضيفي PostgreSQL:
   - Vercel → المشروع → **Storage / Marketplace**.
   - اختاري **Neon Postgres**.
   - Create database ثم **Connect** للمشروع.
   - فعّلي **Production** (وPreview أيضًا إذا رغبتِ).
   - التكامل يضيف `DATABASE_URL` تلقائيًا.
5. اعملي **Redeploy** بعد ربط Neon إذا لم يبدأ Vercel إعادة النشر تلقائيًا.
6. اختياري: من **Environment Variables** أضيفي:
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL=gpt-4.1-mini`

## كيف أتأكد أن PostgreSQL يعمل؟

بعد النشر افتحي:

`/api/health`

المفروض يظهر:

```json
{"status":"ok","database":"postgresql"}
```

إذا ظهر `sqlite-ephemeral` فهذا يعني أن `DATABASE_URL` غير مرتبط ببيئة Vercel الحالية.

## تشغيل محلي

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

بدون `DATABASE_URL` سيستخدم SQLite محليًا. إذا أردتِ اختبار Postgres محليًا ضعي رابط Neon في `.env` أو كمتغير بيئة باسم `DATABASE_URL`.

## ملاحظات الإنتاج

- استخدمي رابط Neon pooled الذي يوفره تكامل Vercel في `DATABASE_URL`.
- لا تعتمدي على SQLite داخل Vercel لحفظ سجل 30–90 يومًا؛ نظام الملفات المؤقت ليس تخزينًا دائمًا.
- الجداول تُنشأ تلقائيًا عند أول تشغيل، ولا تحتاجين تنفيذ SQL يدويًا.
