const STATE = {
  hours: 24,
  payload: null,
  loading: false,
  requestId: 0,
};

const CACHE_KEY = 'strategicNewsroomCache';
const UAE_TZ = 'Asia/Dubai';
const UAE_LOCALE = 'ar-AE-u-nu-latn'; // Arabic AM/PM marker (ص / م) with 0-9 digits, e.g. 12:25 م

const topicMap = {
  political: { label: 'سياسي', riskId: 'politicalRisk', impactId: 'politicalImpact', analysisId: 'politicalAnalysis', eventsId: 'politicalEvents' },
  economic: { label: 'اقتصادي', riskId: 'economicRisk', impactId: 'economicImpact', analysisId: 'economicAnalysis', eventsId: 'economicEvents' },
  military: { label: 'عسكري', riskId: 'militaryRisk', impactId: 'militaryImpact', analysisId: 'militaryAnalysis', eventsId: 'militaryEvents' },
};

function esc(v = '') {
  return String(v).replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}

// Screen-reader announcement only (nothing visible under the buttons).
function announce(text) {
  const live = document.getElementById('statusLive');
  if (live) live.textContent = text;
}

// Small, temporary error message — shown only when something fails.
let errorTimer = null;
function showError(text) {
  const box = document.getElementById('refreshError');
  if (!box) return;
  box.textContent = text;
  box.hidden = false;
  clearTimeout(errorTimer);
  errorTimer = setTimeout(clearError, 6000);
}

function clearError() {
  const box = document.getElementById('refreshError');
  if (!box) return;
  clearTimeout(errorTimer);
  box.hidden = true;
  box.textContent = '';
}

function setLoading(isLoading) {
  STATE.loading = isLoading;
  const btn = document.getElementById('refreshBtn');
  const label = btn.querySelector('.btn-label');
  btn.classList.toggle('loading', isLoading);
  btn.disabled = isLoading;
  btn.setAttribute('aria-busy', String(isLoading));
  label.textContent = isLoading ? 'جاري التحديث...' : 'تحديث';
}

// Live clock: 12:25 م (no seconds), refreshed every second so the minute flips on time.
const clockFormatter = new Intl.DateTimeFormat(UAE_LOCALE, {
  hour: 'numeric', minute: '2-digit', hour12: true, timeZone: UAE_TZ
});
const shortTimeFormatter = new Intl.DateTimeFormat(UAE_LOCALE, {
  hour: 'numeric', minute: '2-digit', hour12: true, timeZone: UAE_TZ
});
const shortDateFormatter = new Intl.DateTimeFormat(UAE_LOCALE, { day: 'numeric', month: 'numeric', timeZone: UAE_TZ });
const dayKeyFormatter = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: UAE_TZ });

function formatUAETime(date = new Date()) {
  return clockFormatter.format(date);
}

// "آخر تحديث": time only (12:25 م); adds day/month only if the data is from another day.
function formatLastUpdated(isoString) {
  if (!isoString) return '—';
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return '—';
  const time = shortTimeFormatter.format(d);
  if (dayKeyFormatter.format(d) === dayKeyFormatter.format(new Date())) return time;
  return `${shortDateFormatter.format(d)} ${time}`;
}

function updateUAEClock() {
  const el = document.getElementById('uaeTime');
  if (el) el.textContent = formatUAETime();
}

// Safety net: keep the title and the description on ONE line, never cut,
// even with a different system font or a bigger text-size setting on the phone.
function fitOneLine(el, minPx) {
  if (!el) return;
  el.style.fontSize = '';
  let size = parseFloat(getComputedStyle(el).fontSize) || 16;
  let guard = 0;
  while (el.scrollWidth > el.clientWidth + 1 && size > minPx && guard < 80) {
    size -= 0.25;
    guard += 1;
    el.style.fontSize = `${size}px`;
  }
}

function fitTitle() {
  fitOneLine(document.getElementById('appTitle'), 12);
  fitOneLine(document.getElementById('appSubtitle'), 8);
}

function setupTitleFit() {
  let frame = 0;
  const schedule = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(fitTitle);
  };
  fitTitle();
  window.addEventListener('resize', schedule);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitTitle).catch(() => {});
}

function riskFromScore(score = 0) {
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
      <small>${[a.domain, a.source_country].filter(Boolean).map(esc).join(' • ')}</small>
    </div>`).join('');

  return `
    <article class="news-card">
      <div class="top">
        <div class="score-box"><b>${esc(e.score)}</b><small>أهمية</small></div>
        <div>
          <h4>${esc(e.title)}</h4>
          <div class="news-meta">
            <span class="tag ${tagClass(e.score)}">الثقة: ${esc(e.confidence)}</span>
            <span class="tag uae">أثر الإمارات: ${esc(e.uae_impact)}%</span>
            <span class="tag">مصادر: ${esc(e.source_count)}</span>
            <span class="tag">${(e.scopes || []).map(esc).join(' • ')}</span>
          </div>
        </div>
      </div>
      <details class="sources">
        <summary>عرض المصادر والروايات</summary>
        ${sources}
      </details>
    </article>`;
}

function renderBreaking(topEvents = []) {
  const html = (topEvents || []).slice(0, 6).map((e) => `<span>• ${esc(e.title)}</span>`).join('');
  document.getElementById('breakingItems').innerHTML = html || '<span>جاري تجهيز أهم الأخبار الهامة...</span>';
}

function renderHome(payload) {
  const hero = payload.hero;
  if (hero) {
    document.getElementById('heroTitle').textContent = hero.title;
    document.getElementById('heroText').textContent = `الأهمية ${hero.score}/100 • الثقة ${hero.confidence} • الأثر على الإمارات ${hero.uae_impact}%`;
  }
  document.getElementById('topCount').textContent = `${(payload.top_events || []).length} أحداث`;
  document.getElementById('topEvents').innerHTML = (payload.top_events || []).length ? payload.top_events.map(eventCard).join('') : '<div class="empty">لا توجد نتائج كافية.</div>';
  document.getElementById('overviewCards').innerHTML = Object.keys(topicMap).map((topic) => {
    const a = payload.analyses?.[topic] || {};
    return `
      <article class="analysis-card">
        <h4>${esc(topicMap[topic].label)}</h4>
        <p>${esc(a.summary || '')}</p>
        <p><strong>زاوية الإمارات:</strong> ${esc(a.uae_angle || '')}</p>
        <p><strong>الثقة:</strong> ${esc(a.confidence || 'أولي')}</p>
      </article>`;
  }).join('');
}

function renderTopics(payload) {
  Object.entries(topicMap).forEach(([topic, meta]) => {
    const events = payload.events?.[topic] || [];
    const analysis = payload.analyses?.[topic] || {};
    document.getElementById(meta.riskId).textContent = riskFromScore(events[0]?.score || 0);
    const impact = events[0]?.uae_impact;
    const impactEl = document.getElementById(meta.impactId);
    if (impactEl) impactEl.textContent = (impact === undefined || impact === null || impact === '') ? 'التأثير: —' : `التأثير: ${impact}%`;
    document.getElementById(meta.analysisId).innerHTML = analysisHtml(analysis, `تحليل ${meta.label}`);
    document.getElementById(meta.eventsId).innerHTML = events.length ? events.map(eventCard).join('') : '<div class="empty">لا توجد نتائج كافية.</div>';
  });
}

function render(payload) {
  STATE.payload = payload;
  renderHome(payload);
  renderTopics(payload);
  renderBreaking(payload.top_events || []);
  document.getElementById('lastUpdated').textContent = formatLastUpdated(payload.meta?.updated_at);
}

function readCache() {
  try {
    const cached = localStorage.getItem(CACHE_KEY);
    return cached ? JSON.parse(cached) : null;
  } catch {
    return null;
  }
}

async function loadDashboard(forceRefresh = false) {
  // Only the latest request may update the screen or end the loading state.
  const requestId = ++STATE.requestId;
  setLoading(true);
  clearError();
  announce(forceRefresh ? 'جاري التحديث...' : 'جاري تحميل غرفة الأخبار...');
  const endpoint = forceRefresh ? `/api/refresh?hours=${STATE.hours}` : `/api/dashboard?hours=${STATE.hours}`;
  const method = forceRefresh ? 'POST' : 'GET';
  try {
    const res = await fetch(endpoint, { method });
    if (!res.ok) throw new Error('Network error');
    const payload = await res.json();
    if (requestId !== STATE.requestId) return;
    if (!Number(payload.meta?.article_count || 0)) {
      // The news sources returned nothing right now: keep the last news on screen instead of blanking it.
      const cached = readCache();
      if (cached && Number(cached.meta?.article_count || 0) > 0) {
        render(cached);
        showError('لم تصل أخبار جديدة الآن — تُعرض آخر نسخة محفوظة');
      } else {
        render(payload);
        showError('لم تصل أخبار من المصادر الآن، أعد المحاولة بعد دقيقة');
      }
      return;
    }
    render(payload);
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(payload)); } catch {}
    if (payload.meta?.stale) showError('تعذّر جلب أخبار جديدة الآن — تُعرض آخر نسخة');
    announce('اكتمل التحديث');
  } catch (e) {
    if (requestId !== STATE.requestId) return;
    const cached = readCache();
    if (cached) {
      render(cached);
      showError('تعذّر التحديث الآن — تُعرض آخر نسخة محفوظة');
    } else {
      showError('تعذّر الاتصال بالخادم الآن');
      document.getElementById('topEvents').innerHTML = '<div class="empty">تعذر تحميل البيانات الآن. حاولي مرة أخرى بعد قليل.</div>';
      renderBreaking([]);
    }
  } finally {
    if (requestId === STATE.requestId) setLoading(false);
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
      loadDashboard(true);
    });
  });
}

function setupActions() {
  document.getElementById('refreshBtn').addEventListener('click', () => {
    if (STATE.loading) return; // no second press until the current request finishes
    loadDashboard(true);
  });
  document.getElementById('shareBtn').addEventListener('click', async () => {
    const hero = STATE.payload?.hero;
    const text = hero ? `مرصد الإمارات الذكي\nأهم حدث الآن: ${hero.title}\nالأهمية: ${hero.score}/100\nالثقة: ${hero.confidence}` : 'مرصد الإمارات الذكي';
    if (navigator.share) {
      try { await navigator.share({ title: 'مرصد الإمارات الذكي', text, url: location.href }); } catch {}
    } else {
      await navigator.clipboard.writeText(text);
      alert('تم نسخ الملخص');
    }
  });
}

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' }).catch(() => {});
// No in-page install UI: also stop the browser's automatic install mini-bar from appearing.
window.addEventListener('beforeinstallprompt', (e) => e.preventDefault());
updateUAEClock();
setInterval(updateUAEClock, 1000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) updateUAEClock(); });
setupTitleFit();
setupTabs();
setupFilters();
setupActions();
loadDashboard(false);
