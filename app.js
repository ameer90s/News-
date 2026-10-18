(() => {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  let hours = 24;
  let scope = 'all';
  let allNews = [];

  const title = $('#appTitle');
  const refreshBtn = $('#refreshBtn');
  const newsList = $('#newsList');
  const emptyNews = $('#emptyNews');
  const newsState = $('#newsState');
  const toast = $('#toast');

  const arabicDigitsToEnglish = (value) => value.replace(/[٠-٩]/g, d => '٠١٢٣٤٥٦٧٨٩'.indexOf(d));

  function uaeTime() {
    const parts = new Intl.DateTimeFormat('ar-AE-u-nu-latn', {
      timeZone: 'Asia/Dubai', hour: 'numeric', minute: '2-digit', hour12: true
    }).formatToParts(new Date());
    const h = parts.find(p => p.type === 'hour')?.value || '--';
    const m = parts.find(p => p.type === 'minute')?.value || '--';
    const day = parts.find(p => p.type === 'dayPeriod')?.value || '';
    return arabicDigitsToEnglish(`${h}:${m} ${day}`).replace('ص', 'ص').replace('م', 'م');
  }

  function updateClock() { $('#uaeClock').textContent = uaeTime(); }
  function setLastUpdated() { $('#lastUpdated').textContent = uaeTime(); }
  setInterval(updateClock, 1000); updateClock();

  function fitTitle() {
    title.style.fontSize = '';
    let size = parseFloat(getComputedStyle(title).fontSize);
    const row = title.parentElement;
    const available = row.clientWidth - $('.clock-card').offsetWidth - 14;
    while (title.scrollWidth > available && size > 18) {
      size -= .5; title.style.fontSize = `${size}px`;
    }
  }
  window.addEventListener('resize', fitTitle); requestAnimationFrame(fitTitle);

  function showToast(message) {
    toast.textContent = message; toast.classList.remove('hidden');
    clearTimeout(showToast.timer); showToast.timer = setTimeout(() => toast.classList.add('hidden'), 2600);
  }

  function levelFor(value) {
    if (value <= 33) return ['منخفض', 'low'];
    if (value <= 66) return ['متوسط', 'medium'];
    return ['مرتفع', 'high'];
  }

  function relTime(iso) {
    const ms = Date.now() - new Date(iso).getTime();
    const mins = Math.max(0, Math.floor(ms / 60000));
    if (mins < 60) return `منذ ${mins || 1} دقيقة`;
    const h = Math.floor(mins / 60); if (h < 24) return `منذ ${h} ساعة`;
    return `منذ ${Math.floor(h / 24)} يوم`;
  }

  function scopeLabel(v) { return ({local:'محلية',regional:'إقليمية',international:'دولية'})[v] || 'الكل'; }

  function renderNews() {
    const data = scope === 'all' ? allNews : allNews.filter(n => n.category === scope);
    newsList.innerHTML = '';
    emptyNews.classList.toggle('hidden', data.length > 0);
    data.slice(0, 12).forEach(item => {
      const [label, cls] = levelFor(item.uae_impact);
      const a = document.createElement('a'); a.className = 'news-card'; a.href = item.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
      a.innerHTML = `
        <div class="news-score ${cls}"><span>${label}</span><b>${item.uae_impact}%</b></div>
        <div class="news-copy"><h3></h3><div class="news-meta"><span>${item.source}</span><span>•</span><span>${relTime(item.published_at)}</span></div></div>
        <span class="scope-chip">${scopeLabel(item.category)}</span>`;
      a.querySelector('h3').textContent = item.title;
      newsList.appendChild(a);
    });
  }

  function updateImpacts(items) {
    ['political','economic','military'].forEach(domain => {
      const candidates = items.filter(x => x.domain === domain);
      const value = candidates.length ? Math.max(...candidates.map(x => x.uae_impact)) : 0;
      const [label, cls] = levelFor(value);
      const card = document.querySelector(`[data-domain="${domain}"]`);
      card.classList.remove('low','medium','high'); card.classList.add(cls);
      $(`#${domain}Level`).textContent = candidates.length ? label : 'لا بيانات';
      $(`#${domain}Impact`).textContent = candidates.length ? `${value}%` : '--%';
    });
  }

  async function fetchWithTimeout(url, options = {}, timeout = 15000) {
    const controller = new AbortController(); const id = setTimeout(() => controller.abort(), timeout);
    try { return await fetch(url, {...options, signal: controller.signal, cache: 'no-store'}); }
    finally { clearTimeout(id); }
  }

  async function loadAnalysis(items) {
    if (!items.length) {
      $('#bigHeadline').textContent = 'لا توجد أخبار كافية لبناء الصورة الكبرى الآن';
      $('#bigSummary').textContent = 'سيعيد المرصد المحاولة عند التحديث التالي.';
      return;
    }
    try {
      const res = await fetchWithTimeout('/api/analysis', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({items:items.slice(0,24)})}, 14000);
      if (!res.ok) throw new Error('analysis');
      const data = await res.json();
      $('#bigHeadline').textContent = data.headline;
      $('#bigSummary').textContent = data.summary;
      $('#politicalAnalysis').textContent = data.domains.political;
      $('#economicAnalysis').textContent = data.domains.economic;
      $('#militaryAnalysis').textContent = data.domains.military;
      const ai = data.mode === 'ai';
      $('#aiBadge').classList.toggle('hidden', !ai); $('#analysisBadge').classList.toggle('hidden', !ai);
    } catch {
      $('#bigHeadline').textContent = allNews[0]?.title || 'الصورة الكبرى غير متاحة مؤقتًا';
      $('#bigSummary').textContent = 'الأخبار متاحة، بينما تعذر تحديث التحليل الآن.';
      $('#aiBadge').classList.add('hidden'); $('#analysisBadge').classList.add('hidden');
    }
  }

  async function loadDashboard(showSpinner = true) {
    if (showSpinner) { refreshBtn.disabled = true; refreshBtn.classList.add('loading'); $('.refresh-label').textContent = 'جاري التحديث...'; }
    newsState.textContent = 'جاري التحميل...';
    try {
      const res = await fetchWithTimeout(`/api/news?hours=${hours}`, {}, 16000);
      if (!res.ok) throw new Error('news');
      const data = await res.json(); allNews = Array.isArray(data.items) ? data.items : [];
      renderNews(); updateImpacts(allNews); setLastUpdated();
      newsState.textContent = allNews.length ? `${allNews.length} خبر` : (data.message || 'لا توجد نتائج');
      loadAnalysis(allNews);
    } catch {
      allNews = []; renderNews(); updateImpacts([]); newsState.textContent = 'تعذر التحديث'; showToast('تعذر جلب الأخبار الآن. حاول مرة أخرى.');
      $('#bigHeadline').textContent = 'تعذر تحديث الصورة الكبرى مؤقتًا'; $('#bigSummary').textContent = 'حاول التحديث بعد قليل.';
    } finally {
      refreshBtn.disabled = false; refreshBtn.classList.remove('loading'); $('.refresh-label').textContent = 'تحديث';
    }
  }

  refreshBtn.addEventListener('click', () => loadDashboard(true));
  $('#shareBtn').addEventListener('click', async () => {
    try { if (navigator.share) await navigator.share({title:'مرصد الإمارات الذكي', url:location.href}); else { await navigator.clipboard.writeText(location.href); showToast('تم نسخ الرابط'); } }
    catch (_) {}
  });

  $$('.period-row button').forEach(btn => btn.addEventListener('click', () => {
    $$('.period-row button').forEach(x => x.classList.remove('active')); btn.classList.add('active'); hours = Number(btn.dataset.hours); loadDashboard(true);
  }));
  $$('.scope-tabs button').forEach(btn => btn.addEventListener('click', () => {
    $$('.scope-tabs button').forEach(x => x.classList.remove('active')); btn.classList.add('active'); scope = btn.dataset.scope; renderNews();
  }));
  $$('.bottom-nav [data-jump]').forEach(btn => btn.addEventListener('click', () => document.querySelector(`[data-domain="${btn.dataset.jump}"]`)?.scrollIntoView({behavior:'smooth', block:'center'})));

  window.addEventListener('beforeinstallprompt', e => e.preventDefault());
  if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
  loadDashboard(false);
})();
