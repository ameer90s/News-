const STATE = {
  hours: 24,
  payload: null,
};

const topicMap = {
  political: { label: 'سياسي', riskId: 'politicalRisk', analysisId: 'politicalAnalysis', eventsId: 'politicalEvents' },
  economic: { label: 'اقتصادي', riskId: 'economicRisk', analysisId: 'economicAnalysis', eventsId: 'economicEvents' },
  military: { label: 'عسكري', riskId: 'militaryRisk', analysisId: 'militaryAnalysis', eventsId: 'militaryEvents' },
};

function esc(v = '') {
  return String(v).replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}

function setStatus(text) {
  document.getElementById('statusLive').textContent = text;
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
      <small>${esc(a.domain || '')} • ${esc(a.source_country || '')}</small>
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

async function loadDashboard(forceRefresh = false) {
  setStatus(forceRefresh ? 'جاري التحديث والتحليل...' : 'جاري تحميل غرفة الأخبار...');
  const endpoint = forceRefresh ? `/api/refresh?hours=${STATE.hours}` : `/api/dashboard?hours=${STATE.hours}`;
  const method = forceRefresh ? 'POST' : 'GET';
  try {
    const res = await fetch(endpoint, { method });
    if (!res.ok) throw new Error('Network error');
    const payload = await res.json();
    render(payload);
    localStorage.setItem('strategicNewsroomCache', JSON.stringify(payload));
    setStatus(`تم التحديث • ${payload.meta?.article_count || 0} مادة تقريبًا`);
  } catch (e) {
    const cached = localStorage.getItem('strategicNewsroomCache');
    if (cached) {
      render(JSON.parse(cached));
      setStatus('تعذر التحديث الآن — عرض آخر نسخة محفوظة');
    } else {
      setStatus('الخادم غير متاح الآن');
      document.getElementById('topEvents').innerHTML = '<div class="empty">تعذر تحميل البيانات الآن. حاولي مرة أخرى بعد قليل.</div>';
      renderBreaking([]);
    }
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
  document.getElementById('refreshBtn').addEventListener('click', () => loadDashboard(true));
  document.getElementById('shareBtn').addEventListener('click', async () => {
    const hero = STATE.payload?.hero;
    const text = hero ? `مرصد الإمارات الذكي
أهم حدث الآن: ${hero.title}
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

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js').catch(() => {});
setupTabs();
setupFilters();
setupActions();
loadDashboard(false);
