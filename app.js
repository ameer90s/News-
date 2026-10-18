(() => {
  'use strict';

  const state = {
    hours: 24,
    category: 'all',
    items: [],
    impact: {},
    loading: false,
    latestExpanded: false,
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const arabicMap = { local: 'محلية', regional: 'إقليمية', international: 'دولية' };

  function dubaiTime() {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Dubai', hour: 'numeric', minute: '2-digit', hour12: true,
    }).formatToParts(new Date());
    const hour = parts.find(p => p.type === 'hour')?.value || '--';
    const minute = parts.find(p => p.type === 'minute')?.value || '--';
    const period = parts.find(p => p.type === 'dayPeriod')?.value === 'AM' ? 'ص' : 'م';
    return `${hour}:${minute} ${period}`;
  }

  function updateClock() {
    const el = $('#uaeClock');
    if (!el) return;
    const text = dubaiTime();
    el.textContent = text;
    el.dateTime = new Date().toISOString();
  }

  function setLastUpdated() {
    $('#lastUpdated').textContent = `آخر تحديث: ${dubaiTime()}`;
  }

  function showNotice(message = '') {
    const el = $('#notice');
    el.textContent = message;
    el.classList.toggle('show', Boolean(message));
    clearTimeout(showNotice.timer);
    if (message) showNotice.timer = setTimeout(() => showNotice(''), 5000);
  }

  function setRefreshing(value) {
    state.loading = value;
    const btn = $('#refreshBtn');
    btn.disabled = value;
    btn.classList.toggle('loading', value);
    $('.btn-text', btn).textContent = value ? 'جاري التحديث...' : 'تحديث';
  }

  async function fetchJSON(url, options = {}, timeout = 15000) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal, cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } finally {
      clearTimeout(id);
    }
  }

  function levelFor(value) {
    return value <= 33 ? ['low', 'منخفض'] : value <= 66 ? ['medium', 'متوسط'] : ['high', 'مرتفع'];
  }

  function renderImpact() {
    for (const domain of ['political', 'economic', 'military']) {
      const card = $(`.impact-card[data-domain="${domain}"]`);
      const value = Number(state.impact?.[domain]?.impact || 0);
      const [cls, label] = levelFor(value);
      card.classList.remove('low', 'medium', 'high');
      card.classList.add(cls);
      $('.impact-level', card).textContent = label;
      $('.impact-value', card).textContent = `التأثير: ${value}%`;
    }
  }

  function safeURL(value) {
    try {
      const u = new URL(value, location.origin);
      return ['http:', 'https:'].includes(u.protocol) ? u.href : '#';
    } catch { return '#'; }
  }

  function timeAgo(iso) {
    const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
    if (mins < 60) return `منذ ${Math.max(1, mins)} دقيقة`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `منذ ${hours} ساعة`;
    return `منذ ${Math.round(hours / 24)} يوم`;
  }

  function newsCard(item) {
    const [levelClass, levelLabel] = levelFor(Number(item.uae_impact || 0));
    const a = document.createElement('a');
    a.className = 'news-card';
    a.href = safeURL(item.url);
    a.target = '_blank';
    a.rel = 'noopener noreferrer';

    const pill = document.createElement('div');
    pill.className = `impact-pill ${levelClass}`;
    const label = document.createElement('span'); label.textContent = levelLabel;
    const pct = document.createElement('strong'); pct.textContent = `${Number(item.uae_impact || 0)}%`;
    pill.append(label, pct);

    const main = document.createElement('div'); main.className = 'news-main';
    const title = document.createElement('h3'); title.className = 'news-title'; title.textContent = item.title;
    const meta = document.createElement('div'); meta.className = 'news-meta';
    const source = document.createElement('span'); source.textContent = item.source || 'المصدر';
    const dot = document.createElement('span'); dot.className = 'dot'; dot.textContent = '•';
    const age = document.createElement('span'); age.textContent = timeAgo(item.published_at);
    const chip = document.createElement('span'); chip.className = 'category-chip'; chip.textContent = arabicMap[item.category] || '';
    meta.append(source, dot, age, chip);
    main.append(title, meta);
    a.append(pill, main);
    return a;
  }

  function renderLatest() {
    const host = $('#latestNewsList');
    host.replaceChildren();
    const sorted = [...state.items].sort((a, b) => new Date(b.published_at) - new Date(a.published_at));
    const max = state.latestExpanded ? 8 : 3;
    const list = sorted.slice(0, max);
    if (!list.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'لم تصل أخبار عربية موثوقة الآن. جرّب التحديث بعد قليل.';
      host.append(empty);
      return;
    }
    list.forEach(item => host.append(newsCard(item)));
    $('#showMoreLatest').textContent = state.latestExpanded ? 'عرض أقل ←' : 'عرض الكل ←';
  }

  function renderTopNews() {
    const host = $('#topNewsList');
    host.replaceChildren();
    let list = [...state.items].sort((a, b) => b.importance - a.importance);
    if (state.category !== 'all') list = list.filter(x => x.category === state.category);
    list = list.slice(0, 8);
    $('#emptyState').hidden = list.length > 0;
    list.forEach(item => host.append(newsCard(item)));
  }

  function localFallback(items) {
    const top = [...items].sort((a, b) => b.importance - a.importance);
    const first = top[0];
    const second = top[1];
    return {
      source: 'local',
      big_picture: {
        title: first ? 'أبرز التطورات الحالية وتأثيرها المحتمل على الإمارات' : 'لا توجد بيانات كافية الآن',
        summary: first
          ? `تتصدر المتابعة حالياً: ${first.title}${second ? `، بالتوازي مع ${second.title}` : ''}. يستند هذا الملخص إلى الأخبار الظاهرة فقط.`
          : 'سيتم تحديث الصورة الكبرى تلقائياً عند توفر أخبار عربية موثوقة.'
      },
      domains: {
        political: { summary: top.find(x => x.domain === 'political')?.title || 'لا توجد إشارات سياسية كافية ضمن الأخبار الحالية.' },
        economic: { summary: top.find(x => x.domain === 'economic')?.title || 'لا توجد إشارات اقتصادية كافية ضمن الأخبار الحالية.' },
        military: { summary: top.find(x => x.domain === 'military')?.title || 'لا توجد إشارات عسكرية كافية ضمن الأخبار الحالية.' },
      }
    };
  }

  function applyAnalysis(data) {
    const gemini = data?.source === 'gemini';
    $('#bigAiBadge').hidden = !gemini;
    $('#analysisAiBadge').hidden = !gemini;
    $('#bigTitle').textContent = data?.big_picture?.title || 'الصورة الكبرى';
    $('#bigSummary').textContent = data?.big_picture?.summary || 'لا تتوفر خلاصة حالياً.';
    $('#politicalAnalysis').textContent = data?.domains?.political?.summary || 'لا تتوفر قراءة سياسية حالياً.';
    $('#economicAnalysis').textContent = data?.domains?.economic?.summary || 'لا تتوفر قراءة اقتصادية حالياً.';
    $('#militaryAnalysis').textContent = data?.domains?.military?.summary || 'لا تتوفر قراءة عسكرية حالياً.';
  }

  async function loadAnalysis(items) {
    applyAnalysis(localFallback(items));
    if (!items.length) return;
    try {
      const data = await fetchJSON('/api/analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: items.slice(0, 24) }),
      }, 16000);
      if (data?.ok) applyAnalysis(data);
    } catch {
      // Keep the deterministic local fallback; news remains fully usable.
    }
  }

  async function loadDashboard() {
    if (state.loading) return;
    setRefreshing(true);
    try {
      const data = await fetchJSON(`/api/news?hours=${state.hours}`, {}, 15000);
      state.items = Array.isArray(data.items) ? data.items.filter(x => /[\u0600-\u06FF]/.test(x.title || '')) : [];
      state.impact = data.impact || {};
      renderImpact();
      renderLatest();
      renderTopNews();
      setLastUpdated();
      void loadAnalysis(state.items);
      if (!state.items.length) showNotice('لم تصل أخبار عربية موثوقة حالياً. سيبقى المرصد جاهزاً للمحاولة التالية.');
    } catch (err) {
      state.items = [];
      state.impact = {};
      renderImpact();
      renderLatest();
      renderTopNews();
      applyAnalysis(localFallback([]));
      showNotice('تعذر جلب الأخبار حالياً. حاول التحديث بعد قليل.');
    } finally {
      setRefreshing(false);
    }
  }

  function fitSingleLine(el, minPx) {
    if (!el) return;
    el.style.fontSize = '';
    let size = parseFloat(getComputedStyle(el).fontSize);
    while (el.scrollWidth > el.clientWidth + 1 && size > minPx) {
      size -= 0.3;
      el.style.fontSize = `${size}px`;
    }
  }

  function fitHeader() {
    fitSingleLine($('#appTitle'), 22);
    fitSingleLine($('#tagline'), 9.2);
  }

  function bind() {
    updateClock();
    setInterval(updateClock, 1000);
    window.addEventListener('resize', () => requestAnimationFrame(fitHeader), { passive: true });
    window.addEventListener('beforeinstallprompt', e => e.preventDefault());

    $('#refreshBtn').addEventListener('click', loadDashboard);
    $('#shareBtn').addEventListener('click', async () => {
      const payload = { title: 'مرصد الإمارات الذكي', text: 'مرصد الإمارات الذكي', url: location.href };
      try {
        if (navigator.share) await navigator.share(payload);
        else { await navigator.clipboard.writeText(location.href); showNotice('تم نسخ رابط المرصد.'); }
      } catch { /* cancelled */ }
    });

    $$('.duration-strip button').forEach(btn => btn.addEventListener('click', () => {
      state.hours = Number(btn.dataset.hours);
      $$('.duration-strip button').forEach(x => x.classList.toggle('selected', x === btn));
      loadDashboard();
    }));

    $$('.category-tabs button').forEach(btn => btn.addEventListener('click', () => {
      state.category = btn.dataset.category;
      $$('.category-tabs button').forEach(x => x.classList.toggle('active', x === btn));
      renderTopNews();
    }));

    $('#showMoreLatest').addEventListener('click', () => {
      state.latestExpanded = !state.latestExpanded;
      renderLatest();
    });

    $$('.bottom-nav button').forEach(btn => btn.addEventListener('click', () => {
      $$('.bottom-nav button').forEach(x => x.classList.toggle('active', x === btn));
      if (btn.dataset.target === 'home') window.scrollTo({ top: 0, behavior: 'smooth' });
      if (btn.dataset.domainTarget) {
        document.querySelector(`.impact-card[data-domain="${btn.dataset.domainTarget}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }));
  }

  document.addEventListener('DOMContentLoaded', () => {
    bind();
    requestAnimationFrame(() => { fitHeader(); loadDashboard(); });
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
})();
