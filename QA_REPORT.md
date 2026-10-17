# QA Report — UAE Smart Observatory Gemini v10

Validated before packaging:

## Gemini migration
- OpenAI integration removed from runtime code and environment configuration.
- Gemini provider uses server-side `GEMINI_API_KEY` only.
- Default model: `gemini-3.8-flash`.
- REST request uses Google Gemini GenerateContent endpoint with `x-goog-api-key`.
- JSON response mode enabled; output is normalized before reaching the UI.
- Gemini thinking level set to `low` for lower latency on this short news-analysis task.
- No Google Search grounding is enabled; Gemini analyzes only the event metadata already collected by the app.
- With no key: safe built-in-analysis fallback verified.
- With mocked Gemini success: Big Picture + political/economic/military analyses verified.
- With mocked Gemini/API failure: endpoint returns `used:false`; news/local analysis continue.
- AI cache key bumped to V10 so old OpenAI analysis cache is not reused.

## News pipeline
- GDELT + Google News RSS parsing/ranking path tested with mocked provider responses.
- Test produced 15 articles and populated all 3 topic groups.
- Empty/failed upstream feeds remain handled as an error or stale-cache fallback rather than an endless loading state.
- Live external feed calls cannot be validated from the packaging sandbox because outbound DNS is unavailable there; provider logic itself is covered by deterministic integration tests.

## Frontend / responsive
- Python syntax: `app.py` + `main.py` pass `py_compile`.
- JavaScript syntax: `app.js` passes `node --check`.
- Responsive structural tests passed at 412px / 360px / 320px.
- No horizontal document overflow at tested widths.
- Header title remains one line at all 3 widths; ~30px at 412px.
- Description remains one line and fully fits at 412 / 360 / 320px.
- Header controls end before 180px at all tested widths.
- Refresh loading state: spinner visible, button disabled, controls stay on one row.
- 6/12/24/48/72 hour controls stay fully inside viewport.
- Active period color verified: rgba(155,231,255,0.22) + matching border.
- 3 metric cards remain horizontal and equal-width.
- No Install button and no “توقيت الإمارات” text.
- Small <=330px header padding adjustment added only to guarantee the one-line description at 320px.

## Deployment / unchanged assets
- `background.webp` unchanged.
- `icon.svg` unchanged.
- `manifest.webmanifest` unchanged.
- `main.py` unchanged.
- `vercel.json` unchanged.
- `requirements.txt` unchanged; no Gemini SDK is required.
- `pyproject.toml` unchanged.
- Service worker cache bumped to `strategic-newsroom-v10`.
- Asset query versions bumped to `?v=10`.
- No `/static/` paths remain.
