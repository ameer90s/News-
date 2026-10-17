const STATE = {
  hours: 24,
  payload: null,
  requestId: 0,
  aiPending: false,
};

const topicMap = {
  political: { label: 'سياسي', riskId: 'politicalRisk', impactId: 'politicalImpact', analysisId: 'politicalAnalysis', eventsId: 'politicalEvents' },
  economic: { label: 'اقتصادي', riskId: 'economicRisk', impactId: 'economicImpact', analysisId: 'economicAnalysis', eventsId: 'economicEvents' },
  military: { label: 'عسكري', riskId: 'militaryRisk', impactId: 'militaryImpact', analysisId: 'militaryAnalysis', eventsId: 'militaryEvents' },
};

let refreshErrorTimer = null;

window.addEventListener('beforeinstallprompt', (e) => e.preventDefault());

function storageGet(key) {
  try { return window.localStorage.getItem(key); } catch { return null; }
}

function storageSet(key, value) {
  try { window.localStorage.setItem(key, value); } catch {}
}

function esc(v = '') {
  return String(v).replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}

function setStatus(text) {
  document.getElementById('statusLive').textContent = text;
}

function formatDubaiTime(date = new Date()) {
  try {
    return new Intl.DateTimeFormat('ar-AE-u-nu-latn', {
      timeZone: 'Asia/Dubai',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    }).format(date).replace(/\s+/g, ' ').trim();
  } catch {
    try {
      return new Intl.DateTimeFormat('en-US', {
        timeZone: 'Asia/Dubai',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
      }).format(date).replace(/AM/i, 'ص').replace(/PM/i, 'م');
    } catch {
      return '--:--';
    }
  }
}

function updateDubaiClock() {
  const clock = document.getElementById('dubaiClock');
  if (!clock) return;
  const now = new Date();
  clock.textContent = formatDubaiTime(now);
  clock.dateTime = now.toISOString();
}

function setLastUpdated(date = new Date(), persist = true) {
  const el = document.getElementById('lastUpdatedTime');
  if (!el) return;
  el.textContent = formatDubaiTime(date);
  el.dateTime = date.toISOString();
  if (persist) storageSet('strategicNewsroomLastUpdatedAt', String(date.getTime()));
}

function restoreLastUpdated() {
  const stored = Number(storageGet('strategicNewsroomLastUpdatedAt'));
  if (Number.isFinite(stored) && stored > 0) setLastUpdated(new Date(stored), false);
}

function showTemporaryError(message) {
  const errorBox = document.getElementById('refreshError');
  if (!errorBox) return;
  window.clearTimeout(refreshErrorTimer);
  errorBox.textContent = message;
  errorBox.hidden = false;
  refreshErrorTimer = window.setTimeout(() => {
    errorBox.hidden = true;
    errorBox.textContent = '';
  }, 4500);
}

function clearTemporaryError() {
  const errorBox = document.getElementById('refreshError');
  if (!errorBox) return;
  window.clearTimeout(refreshErrorTimer);
  errorBox.hidden = true;
  errorBox.textContent = '';
}

function setRefreshLoading(isLoading) {
  const btn = document.getElementById('refreshBtn');
  if (!btn) return;
  const label = btn.querySelector('.refresh-label');
  btn.disabled = isLoading;
  btn.classList.toggle('is-loading', isLoading);
  btn.setAttribute('aria-busy', isLoading ? 'true' : 'false');
  if (label) label.textContent = isLoading ? 'جاري التحديث...' : 'تحديث';
}

function fitHeaderTitle() {
  const title = document.getElementById('appTitle');
  const row = document.querySelector('.brand-row');
  const clock = document.querySelector('.uae-clock-card');
  if (!title || !row || !clock) return;

  title.style.fontSize = '';
  title.style.maxWidth = '';

  requestAnimationFrame(() => {
    const rowStyle = getComputedStyle(row);
    const gap = parseFloat(rowStyle.columnGap || rowStyle.gap || '0') || 0;
    const available = Math.max(0, row.clientWidth - clock.getBoundingClientRect().width - gap);
    title.style.maxWidth = `${available}px`;

    let size = parseFloat(getComputedStyle(title).fontSize) || 30;
    let attempts = 0;
    while (title.scrollWidth > available + 0.5 && size > 17 && attempts < 6) {
      const ratio = available / Math.max(title.scrollWidth, 1);
      size = Math.max(17, size * ratio * 0.985);
      title.style.fontSize = `${size}px`;
      attempts += 1;
    }
  });
}

function fitHeaderDescription() {
  const description = document.querySelector('.brand-description');
  if (!description) return;

  description.style.transform = '';
  description.style.transformOrigin = 'right center';

  requestAnimationFrame(() => {
    const available = description.clientWidth;
    const needed = description.scrollWidth;
    if (needed > available && available > 0) {
      const scale = Math.max(0.94, available / needed);
      description.style.transform = `scaleX(${scale})`;
    }
  });
}

function fitHeaderText() {
  fitHeaderTitle();
  fitHeaderDescription();
}

function containsArabic(text = '') {
  return /[\u0600-\u06FF]/.test(String(text));
}

function displayTitle(event = {}) {
  const translated = String(event.title_ar || '').trim();
  if (translated) return translated;
  const original = String(event.title || '').trim();
  if (!original) return 'خبر بدون عنوان';
  if (containsArabic(original)) return original;
  if (STATE.aiPending) return 'جاري تعريب الخبر…';
  return original;
}

function impactLevel(value, hasData = true) {
  if (!hasData) return 'none';
  const n = Math.max(0, Math.min(100, Number(value || 0)));
  if (n >= 67) return 'high';
  if (n >= 34) return 'mid';
  return 'low';
}

function impactLabel(value, hasData = true) {
  const level = impactLevel(value, hasData);
  if (level === 'high') return 'مرتفع';
  if (level === 'mid') return 'متوسط';
  if (level === 'low') return 'منخفض';
  return '—';
}

function riskFromScore(score = 0, hasData = true) {
  if (!hasData) return '—';
  if (score >= 72) return 'مرتفع';
  if (score >= 52) return 'متوسط';
  return 'منخفض';
}

function tagClass(score = 0) {
  if (score >= 72) return 'high';
  if (score >= 52) return 'mid';
  return '';
}

function analysisHtml(a = {}, title = '') {
  const narratives = (a.narratives || []).map((x) => `<li>${esc(x)}</li>`).join('');
  const scenarios = (a.scenarios || []).map((x) => `<li>${esc(x)}</li>`).join('');
  const watch = (a.what_to_watch || []).map((x) => `<li>${esc(x)}</li>`).join('');
  const actors = (a.actors || []).length ? `<p><strong>الأطراف / الجهات:</strong> ${(a.actors || []).map(esc).join('، ')}</p>` : '';
  return `
    <article class="analysis-panel">
      <h4>${esc(title || a.headline || 'التحليل')}</h4>
      <p><strong>الخلاصة:</strong> ${esc(a.summary || '')}</p>
      <p><strong>لماذا يهم؟</strong> ${esc(a.why_it_matters || '')}</p>
      <p><strong>الخلفية / الصورة الأوسع:</strong> ${esc(a.background || '')}</p>
      ${actors}
      <p><strong>الروايات:</strong></p>
      <ul>${narratives}</ul>
      <p><strong>السيناريوهات:</strong></p>
      <ul>${scenarios}</ul>
      <p><strong>ما نراقبه:</strong></p>
      <ul>${watch}</ul>
      <p><strong>زاوية الإمارات:</strong> ${esc(a.uae_angle || '')}</p>
      <p><strong>مستوى الثقة:</strong> ${esc(a.confidence || 'أولي')}</p>
    </article>
  `;
}

function eventCard(e) {
  const sources = (e.articles || []).map((a) => `
    <div class="source-item">
      <a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a>
      <small>${esc(a.domain || '')} • ${esc(a.source_country || '')}</small>
    </div>`).join('');

  return `
    <article class="news-card">
      <div class="top">
        <div class="score-box"><b>${esc(e.score)}</b><small>أهمية</small></div>
        <div class="news-main">
          <h4>${esc(displayTitle(e))}</h4>
          <div class="news-meta">
            <span class="tag ${tagClass(e.score)}">الثقة: ${esc(e.confidence)}</span>
            <span class="tag uae">أثر الإمارات: ${esc(e.uae_impact)}%</span>
            <span class="tag">مصادر: ${esc(e.source_count)}</span>
            <span class="tag">${(e.scopes || []).map(esc).join(' • ')}</span>
          </div>
        </div>
      </div>
      <details class="sources">
        <summary>عرض المصادر الأصلية</summary>
        ${sources}
      </details>
    </article>`;
}

function renderBreaking(topEvents = []) {
  const html = (topEvents || []).slice(0, 6).map((e) => `<span>• ${esc(displayTitle(e))}</span>`).join('');
  document.getElementById('breakingItems').innerHTML = html || '<span>جاري تجهيز أهم الأخبار الهامة...</span>';
}

function renderHome(payload) {
  const hero = payload.hero;
  if (hero) {
    const bigPicture = payload.big_picture || {};
    document.getElementById('heroTitle').textContent = bigPicture.title || displayTitle(hero);
    document.getElementById('heroText').textContent = bigPicture.summary || `الأهمية ${hero.score}/100 • الثقة ${hero.confidence} • الأثر على الإمارات ${hero.uae_impact}%`;
  }
  document.getElementById('topCount').textContent = `${(payload.top_events || []).length} أحداث`;
  document.getElementById('topEvents').innerHTML = (payload.top_events || []).length ? payload.top_events.map(eventCard).join('') : '<div class="empty">لا توجد نتائج كافية.</div>';
  document.getElementById('overviewCards').innerHTML = Object.keys(topicMap).map((topic) => {
    const a = payload.analyses?.[topic] || {};
    const topEvent = (payload.events?.[topic] || [])[0] || {};
    const hasImpact = topEvent.uae_impact !== undefined && topEvent.uae_impact !== null && topEvent.uae_impact !== '';
    const level = impactLevel(topEvent.uae_impact, hasImpact);
    const levelClass = level === 'none' ? '' : `impact-${level}`;
    const impactText = hasImpact ? `${impactLabel(topEvent.uae_impact, true)} • ${topEvent.uae_impact}%` : 'غير متاح';
    return `
      <article class="analysis-card ${levelClass}">
        <div class="analysis-card-head">
          <h4>${esc(topicMap[topic].label)}</h4>
          <span class="impact-badge ${levelClass}">التأثير ${esc(impactText)}</span>
        </div>
        <p class="analysis-summary">${esc(a.summary || '')}</p>
        <p class="uae-angle"><strong>زاوية الإمارات:</strong> ${esc(a.uae_angle || '')}</p>
        <p class="confidence-line">الثقة: ${esc(a.confidence || 'أولي')}</p>
      </article>`;
  }).join('');
}

function renderTopics(payload) {
  Object.entries(topicMap).forEach(([topic, meta]) => {
    const events = payload.events?.[topic] || [];
    const analysis = payload.analyses?.[topic] || {};
    const topEvent = events.reduce((best, current) => {
      return Number(current?.score || 0) > Number(best?.score || 0) ? current : best;
    }, events[0] || {});

    const hasImpact = events.length > 0 && topEvent.uae_impact !== undefined && topEvent.uae_impact !== null && topEvent.uae_impact !== '';
    const impactValue = hasImpact ? Math.max(0, Math.min(100, Number(topEvent.uae_impact || 0))) : 0;
    const level = impactLevel(impactValue, hasImpact);
    const riskEl = document.getElementById(meta.riskId);
    if (riskEl) riskEl.textContent = impactLabel(impactValue, hasImpact);

    const metricCard = riskEl?.closest('.metric-card');
    if (metricCard) {
      metricCard.classList.remove('impact-low', 'impact-mid', 'impact-high');
      if (level !== 'none') metricCard.classList.add(`impact-${level}`);
      metricCard.style.setProperty('--impact-value', `${impactValue}%`);
    }

    const impact = document.getElementById(meta.impactId);
    if (impact) {
      impact.hidden = !hasImpact;
      impact.textContent = hasImpact ? `التأثير ${impactValue}%` : '';
    }

    document.getElementById(meta.analysisId).innerHTML = analysisHtml(analysis, `تحليل ${meta.label}`);
    document.getElementById(meta.eventsId).innerHTML = events.length ? events.map(eventCard).join('') : '<div class="empty">لا توجد نتائج كافية.</div>';
  });
}

function render(payload) {
  STATE.payload = payload;
  renderHome(payload);
  renderTopics(payload);
  renderBreaking(payload.top_events || []);
}

function compactAIEvent(event = {}, id = '') {
  return {
    id,
    title: event.title || '',
    score: event.score ?? null,
    confidence: event.confidence || '',
    source_count: event.source_count ?? 0,
    sources: (event.sources || []).slice(0, 5),
    scopes: (event.scopes || []).slice(0, 5),
    uae_impact: event.uae_impact ?? null,
    newest: event.newest || '',
  };
}

function buildAIContext(payload) {
  const events = {};
  Object.keys(topicMap).forEach((topic) => {
    events[topic] = (payload.events?.[topic] || []).slice(0, 12).map((event, index) => compactAIEvent(event, `${topic}_${index}`));
  });
  return { hours: STATE.hours, events };
}

function buildAISignature(payload) {
  const raw = Object.keys(topicMap).flatMap((topic) =>
    (payload.events?.[topic] || []).slice(0, 3).map((e) => `${topic}:${e.title}:${e.newest || ''}`)
  ).join('|');
  let hash = 5381;
  for (let i = 0; i < raw.length; i += 1) hash = ((hash << 5) + hash) ^ raw.charCodeAt(i);
  return `${STATE.hours}:${hash >>> 0}`;
}

function getCachedAI(signature) {
  try {
    const cached = JSON.parse(storageGet('strategicNewsroomAICacheV11') || 'null');
    if (!cached || cached.signature !== signature || !cached.data) return null;
    if (Date.now() - Number(cached.cachedAt || 0) > 10 * 60 * 1000) return null;
    return cached.data;
  } catch {
    return null;
  }
}

function saveCachedAI(signature, data) {
  storageSet('strategicNewsroomAICacheV11', JSON.stringify({ signature, data, cachedAt: Date.now() }));
}

function applyAIResult(payload, aiResult) {
  if (!aiResult?.used || !aiResult.analyses) return false;

  const titleMap = new Map();
  const translations = aiResult.translations || {};
  Object.keys(topicMap).forEach((topic) => {
    (payload.events?.[topic] || []).slice(0, 12).forEach((event, index) => {
      let translated = String(translations[`${topic}_${index}`] || '').trim();
      if (!translated && index === 0) translated = String(aiResult.analyses?.[topic]?.headline || '').trim();
      if (!translated) return;
      event.title_ar = translated;
      if (event.title) titleMap.set(event.title, translated);
    });
  });
  (payload.top_events || []).forEach((event) => {
    const translated = titleMap.get(event.title);
    if (translated) event.title_ar = translated;
  });
  if (payload.hero) {
    const translated = titleMap.get(payload.hero.title);
    if (translated) payload.hero.title_ar = translated;
  }

  payload.analyses = { ...(payload.analyses || {}), ...aiResult.analyses };
  if (aiResult.big_picture?.summary || aiResult.big_picture?.title) payload.big_picture = aiResult.big_picture;
  payload.meta = payload.meta || {};
  payload.meta.ai = {
    ...(payload.meta.ai || {}),
    enabled: true,
    used: true,
    provider: aiResult.provider || 'gemini',
    model: aiResult.model || payload.meta.ai?.model || '',
  };
  payload.meta.analysis = 'ai';
  return true;
}

async function enhanceWithAI(payload, requestId) {
  if (!payload?.meta?.ai?.enabled) return false;

  const signature = buildAISignature(payload);
  const cachedAI = getCachedAI(signature);
  if (cachedAI) {
    const used = applyAIResult(payload, cachedAI);
    if (used && requestId === STATE.requestId) render(payload);
    return used;
  }

  setStatus('الأخبار جاهزة — جاري التحليل بالذكاء الاصطناعي...');
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timeoutId = controller ? window.setTimeout(() => controller.abort(), 12000) : null;
  try {
    const res = await fetch('/api/ai-analysis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildAIContext(payload)),
      signal: controller?.signal,
    });
    if (!res.ok) return false;
    const aiResult = await res.json();
    if (!aiResult?.used) return false;
    saveCachedAI(signature, aiResult);
    const used = applyAIResult(payload, aiResult);
    if (used && requestId === STATE.requestId) render(payload);
    return used;
  } catch {
    return false;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
}

async function loadDashboard(forceRefresh = false, showRefreshState = false) {
  const requestId = ++STATE.requestId;
  setStatus(forceRefresh ? 'جاري التحديث والتحليل...' : 'جاري تحميل غرفة الأخبار...');
  clearTemporaryError();
  if (showRefreshState) setRefreshLoading(true);
  else setRefreshLoading(false);

  const endpoint = forceRefresh ? `/api/refresh?hours=${STATE.hours}` : `/api/dashboard?hours=${STATE.hours}`;
  const method = forceRefresh ? 'POST' : 'GET';

  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timeoutId = controller ? window.setTimeout(() => controller.abort(), 16000) : null;

  try {
    const res = await fetch(endpoint, { method, signal: controller?.signal });
    if (!res.ok) throw new Error(`Network error ${res.status}`);
    const payload = await res.json();
    if (!payload?.meta || Number(payload.meta.article_count || 0) <= 0 || !(payload.top_events || []).length) {
      throw new Error('Empty news payload');
    }
    if (requestId !== STATE.requestId) return;

    // Render the structure immediately. English source headlines are masked briefly while
    // Gemini translates them; Arabic source headlines remain visible as-is.
    STATE.aiPending = Boolean(payload?.meta?.ai?.enabled);
    render(payload);
    storageSet('strategicNewsroomCache', JSON.stringify(payload));
    setLastUpdated(new Date(payload.meta.updated_at || Date.now()));

    const aiUsed = await enhanceWithAI(payload, requestId);
    if (requestId !== STATE.requestId) return;
    STATE.aiPending = false;
    render(payload);
    storageSet('strategicNewsroomCache', JSON.stringify(payload));
    setStatus(aiUsed ? 'جاهز — تم التعريب والتحليل بالذكاء الاصطناعي' : 'جاهز');
  } catch (e) {
    if (requestId !== STATE.requestId) return;
    STATE.aiPending = false;
    const cached = storageGet('strategicNewsroomCache');
    if (cached) {
      try {
        render(JSON.parse(cached));
        setStatus('تعذر التحديث الآن — عرض آخر نسخة محفوظة');
        showTemporaryError('تعذر التحديث الآن — تم عرض آخر نسخة محفوظة.');
      } catch {
        storageSet('strategicNewsroomCache', '');
      }
    } else {
      setStatus('الخادم غير متاح الآن');
      showTemporaryError('تعذر تحميل الأخبار الآن. حاولي مرة أخرى بعد قليل.');
      document.getElementById('heroTitle').textContent = 'تعذر تحميل الأخبار الآن';
      document.getElementById('heroText').textContent = 'اضغطي تحديث للمحاولة مرة أخرى.';
      document.getElementById('topEvents').innerHTML = '<div class="empty">تعذر تحميل الأخبار الآن. حاولي مرة أخرى بعد قليل.</div>';
      document.getElementById('breakingItems').innerHTML = '<span>تعذر تحميل آخر الأخبار الآن.</span>';
    }
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
    if (showRefreshState && requestId === STATE.requestId) setRefreshLoading(false);
  }
}

function activateView(viewName) {
  document.querySelectorAll('.view').forEach((v) => v.classList.remove('active'));
  document.querySelectorAll('.bottom-tab').forEach((b) => b.classList.remove('active'));
  const view = document.getElementById(viewName);
  if (view) view.classList.add('active');
  const tab = document.querySelector(`.bottom-tab[data-view="${viewName}"]`);
  if (tab) tab.classList.add('active');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function setupTabs() {
  document.querySelectorAll('.bottom-tab').forEach((btn) => {
    btn.addEventListener('click', () => activateView(btn.dataset.view));
  });
}

function setupFilters() {
  document.querySelectorAll('#hourFilters .chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('#hourFilters .chip').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      STATE.hours = Number(chip.dataset.hours);
      loadDashboard(true, false);
    });
  });
}

function setupActions() {
  document.getElementById('refreshBtn').addEventListener('click', () => loadDashboard(true, true));
  document.getElementById('shareBtn').addEventListener('click', async () => {
    const hero = STATE.payload?.hero;
    const text = hero ? `مرصد الإمارات الذكي
أهم حدث الآن: ${displayTitle(hero)}
الأهمية: ${hero.score}/100
الثقة: ${hero.confidence}` : 'مرصد الإمارات الذكي';
    if (navigator.share) {
      try { await navigator.share({ title: 'مرصد الإمارات الذكي', text, url: location.href }); } catch {}
    } else {
      await navigator.clipboard.writeText(text);
      alert('تم نسخ الملخص');
    }
  });
}

function setupHeader() {
  updateDubaiClock();
  window.setInterval(updateDubaiClock, 1000);
  restoreLastUpdated();
  fitHeaderText();

  window.addEventListener('resize', fitHeaderText, { passive: true });
  if (document.fonts?.ready) document.fonts.ready.then(fitHeaderText).catch(() => {});
}

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});

// Core dashboard boot must not depend on optional header enhancements.
setupTabs();
setupFilters();
setupActions();
loadDashboard(false, false);

try {
  setupHeader();
} catch (error) {
  // Keep the news dashboard running even if a device blocks an optional
  // browser feature used only by the clock/header.
  console.warn('Header enhancement skipped:', error);
}
