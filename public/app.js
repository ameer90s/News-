/* مرصد الإمارات الذكي — v1.0.2 */
(function () {
  'use strict';

  var HOURS = [6, 12, 24, 48, 72];
  var DOMAINS = {
    political: { name: 'سياسي', icon: 'i-bank' },
    economic: { name: 'اقتصادي', icon: 'i-chart' },
    military: { name: 'عسكري', icon: 'i-shield' }
  };
  var DOMAIN_KEYS = ['political', 'economic', 'military'];
  var SCOPES = { local: 'محلي', regional: 'إقليمي', international: 'دولي' };
  var LEVEL_AR = { low: 'منخفض', mid: 'متوسط', high: 'مرتفع', none: '—' };
  var KIND_AR = { official: 'رسمي', specialized: 'متخصص', agency: 'وكالة/قناة كبرى', press: 'صحافة محلية' };
  var SVGNS = 'http://www.w3.org/2000/svg';
  var LS = {
    hours: 'mirsad.hours',
    tr: 'mirsad.tr',
    news: function (h) { return 'mirsad.news.' + h; },
    ai: function (h) { return 'mirsad.ai.' + h; }
  };

  var state = {
    hours: 24, domain: 'all', scope: 'all',
    items: [], loaded: false, fetchedAt: null,
    tr: {}, ai: null, busy: false, reqId: 0
  };

  var $ = function (id) { return document.getElementById(id); };

  /* ------------------------------------------------------------- storage */
  function lsGet(k) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage full / blocked */ } }

  /* ---------------------------------------------------------------- utils */
  function h(tag, props) {
    var el = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        var v = props[k];
        if (v == null || v === false) return;
        if (k === 'class') el.className = v;
        else if (k === 'text') el.textContent = v;
        else if (k.indexOf('on') === 0) el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? '' : v);
      });
    }
    for (var i = 2; i < arguments.length; i++) append(el, arguments[i]);
    return el;
  }
  function append(el, kid) {
    if (kid == null || kid === false) return;
    if (Array.isArray(kid)) { kid.forEach(function (k) { append(el, k); }); return; }
    el.appendChild(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  function icon(id, cls) {
    var s = document.createElementNS(SVGNS, 'svg');
    s.setAttribute('class', 'ic' + (cls ? ' ' + cls : ''));
    s.setAttribute('aria-hidden', 'true');
    var u = document.createElementNS(SVGNS, 'use');
    u.setAttribute('href', '#' + id);
    s.appendChild(u);
    return s;
  }
  function skel(height, width) {
    var d = h('div', { class: 'sk' });
    d.style.height = height + 'px';
    if (width) d.style.width = width;
    return d;
  }
  function level(v) {
    if (v == null || isNaN(v)) return 'none';
    v = Math.round(v);
    return v <= 33 ? 'low' : (v <= 66 ? 'mid' : 'high');
  }
  function pct(v) { return h('span', { dir: 'ltr', style: 'unicode-bidi:isolate' }, Math.round(v) + '%'); }
  function safeUrl(u) { try { var p = new URL(u); return (p.protocol === 'http:' || p.protocol === 'https:') ? p.href : null; } catch (e) { return null; } }
  function hoursLabel(n) { return n + (n <= 10 ? ' ساعات' : ' ساعة'); }

  // Defense in depth: never render a headline that is not Arabic.
  function isArabicText(s) {
    var ar = 0, lat = 0, oth = 0;
    for (var i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i);
      if ((c >= 0x600 && c <= 0x6FF) || (c >= 0x750 && c <= 0x77F) || (c >= 0xFB50 && c <= 0xFDFF) || (c >= 0xFE70 && c <= 0xFEFF)) ar++;
      else if ((c >= 65 && c <= 90) || (c >= 97 && c <= 122)) lat++;
      else if (c > 0x24F && /\p{L}/u.test(s.charAt(i))) oth++;
    }
    var t = ar + lat + oth;
    return t > 0 && ar / t >= 0.6;
  }

  function ago(iso) {
    var m = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
    if (m < 1) return 'الآن';
    if (m < 60) return 'منذ ' + plural(m, 'دقيقة', 'دقيقتين', 'دقائق', 'دقيقة');
    var hr = Math.round(m / 60);
    if (hr < 24) return 'منذ ' + plural(hr, 'ساعة', 'ساعتين', 'ساعات', 'ساعة');
    var d = Math.round(hr / 24);
    return 'منذ ' + plural(d, 'يوم', 'يومين', 'أيام', 'يومًا');
  }
  function plural(n, one, two, few, many) {
    if (n === 1) return one;
    if (n === 2) return two;
    return n + ' ' + (n <= 10 ? few : many);
  }

  /* ---------------------------------------------------------------- clock */
  var clockFmt = null;
  try {
    clockFmt = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Dubai', hour: 'numeric', minute: '2-digit', hour12: true });
  } catch (e) { clockFmt = null; }
  function fmtClock(d) {
    if (!clockFmt) {
      var u = new Date(d.getTime() + 4 * 3600 * 1000);
      var hh = u.getUTCHours(), mm = ('0' + u.getUTCMinutes()).slice(-2);
      return ((hh % 12) || 12) + ':' + mm + ' ' + (hh < 12 ? 'ص' : 'م');
    }
    var parts = clockFmt.formatToParts(d), o = {};
    parts.forEach(function (p) { o[p.type] = p.value; });
    return o.hour + ':' + o.minute + ' ' + (/am/i.test(o.dayPeriod) ? 'ص' : 'م');
  }
  var lastClock = '';
  function tickClock() {
    var t = fmtClock(new Date());
    if (t !== lastClock) { lastClock = t; $('clock').textContent = t; fit(); }
  }

  /* ----------------------------------------------------------- one-line fit */
  function fitOne(el, minPx) {
    el.style.fontSize = '';
    var size = parseFloat(getComputedStyle(el).fontSize);
    var guard = 60;
    while (el.scrollWidth > el.clientWidth + 0.5 && size > minPx && guard-- > 0) {
      size -= 0.5;
      el.style.fontSize = size + 'px';
    }
  }
  var fitTimer = 0;
  function fit() {
    cancelAnimationFrame(fitTimer);
    fitTimer = requestAnimationFrame(function () {
      fitOne($('appTitle'), 16);
      fitOne($('tagline'), 9);
    });
  }

  /* ------------------------------------------------------------ data access */
  function titleOf(it) {
    var t = it.title || state.tr[it.id];
    return (t && isArabicText(t)) ? t : null;
  }
  function visible() {
    var out = [];
    state.items.forEach(function (it) {
      var t = titleOf(it);
      if (t) out.push(Object.assign({}, it, { title: t }));
    });
    return out;
  }
  function byDomain(list) { return state.domain === 'all' ? list : list.filter(function (i) { return i.domain === state.domain; }); }
  function aiFor(hours) { return state.hours === hours ? state.ai : null; }

  function domainStats(V) {
    var out = {};
    DOMAIN_KEYS.forEach(function (d) {
      var list = V.filter(function (i) { return i.domain === d; });
      var ai = state.ai && state.ai.analysis && state.ai.analysis[d];
      var val = ai ? ai.uae_impact : (list[0] ? list[0].uae_impact : null);
      out[d] = { list: list, top: list[0] || null, impact: val, ai: !!ai };
    });
    return out;
  }

  /* --------------------------------------------------------------- analysis */
  function localDomainText(d, stat) {
    if (!stat.top) return 'لا توجد أخبار بارزة في هذا المجال خلال آخر ' + hoursLabel(state.hours) + '.';
    var lv = level(stat.impact);
    var tail = { high: 'التأثير المحتمل على الإمارات مرتفع ويستدعي المتابعة الدقيقة.', mid: 'التأثير المحتمل على الإمارات متوسط ويستحق المتابعة.', low: 'التأثير المحتمل على الإمارات محدود حاليًا.', none: '' }[lv];
    return 'عدد الأخبار المرصودة: ' + stat.list.length + '. الأعلى تأثيرًا: «' + stat.top.title + '». ' + tail;
  }
  function analysisFor(V) {
    var stats = domainStats(V);
    var ai = state.ai && state.ai.analysis;
    var complete = !!(ai && DOMAIN_KEYS.every(function (d) { return ai[d]; }));
    var rows = DOMAIN_KEYS.map(function (d) {
      return { d: d, impact: stats[d].impact, text: complete ? ai[d].text : localDomainText(d, stats[d]) };
    });
    return { rows: rows, ai: complete, stats: stats };
  }
  function bigPictureFor(V) {
    if (state.ai && state.ai.big_picture) return { title: state.ai.big_picture.title, summary: state.ai.big_picture.summary, ai: true };
    if (!V.length) return null;
    var stats = domainStats(V), best = null;
    DOMAIN_KEYS.forEach(function (d) { if (stats[d].impact != null && (!best || stats[d].impact > stats[best].impact)) best = d; });
    var s = 'خلال آخر ' + hoursLabel(state.hours) + ' رصد المرصد ' + V.length + ' خبرًا. أبرز التطورات: «' + V[0].title + '»';
    if (V[1]) s += '، و«' + V[1].title + '»';
    s += '.';
    if (best) s += ' أعلى مستوى تأثير على الإمارات في المجال ' + DOMAINS[best].name + ' (' + Math.round(stats[best].impact) + '%).';
    return { title: V[0].title, summary: s, ai: false };
  }
  function aiBadge() { return h('span', { class: 'ai-badge' }, icon('i-spark'), 'تحليل ذكي AI'); }

  /* ----------------------------------------------------------------- render */
  function render() {
    var V = visible();
    renderHero(V);
    renderDomains(V);
    renderLatest(V);
    renderAnalysis(V);
    renderTop(V);
    renderControls();
  }

  function renderHero(V) {
    var t = $('bpTitle'), s = $('bpSummary'), slot = $('bpAi');
    slot.replaceChildren();
    if (!state.loaded && !V.length) {
      t.replaceChildren(skel(20, '85%'));
      s.replaceChildren(skel(14, '100%'), skel(14, '92%'));
      s.style.display = 'block';
      return;
    }
    s.style.display = '';
    var bp = bigPictureFor(V);
    if (!bp) {
      t.textContent = 'لا توجد أخبار لعرضها حاليًا';
      s.textContent = 'جرّب تغيير مدة الأخبار أو اضغط «تحديث».';
      return;
    }
    t.textContent = bp.title;
    s.textContent = bp.summary;
    if (bp.ai) slot.appendChild(aiBadge());
  }

  function domainCard(d, st) {
    var lv = level(st.impact), n = { low: 1, mid: 2, high: 3, none: 0 }[lv];
    var bars = h('span', { class: 'meter' });
    for (var i = 0; i < 3; i++) bars.appendChild(h('i', { class: i < n ? 'f' : '' }));
    return h('div', { class: 'dom lv-' + lv },
      h('div', { class: 'dom-top' }, icon(DOMAINS[d].icon), h('span', { class: 'dom-name' }, DOMAINS[d].name)),
      h('div', { class: 'dom-lvl' }, h('b', null, LEVEL_AR[lv]), bars),
      h('div', { class: 'dom-val' }, 'التأثير: ', st.impact == null ? h('b', null, '—') : h('b', null, pct(st.impact)))
    );
  }
  function renderDomains(V) {
    var stats = domainStats(V);
    $('domains').replaceChildren.apply($('domains'), DOMAIN_KEYS.map(function (d) { return domainCard(d, stats[d]); }));
  }

  function thumb(it) {
    var t = it.title, id, fill = false;
    if (/نفط|غاز|برميل|أوبك|اوبك/.test(t)) id = 'i-drop';
    else if (/طيران|مطار|رحلات|الجوية|الجوي/.test(t)) { id = 'i-plane'; fill = true; }
    else id = DOMAINS[it.domain].icon;
    return h('span', { class: 'thumb' }, icon(id, fill ? 'fill' : ''));
  }
  function row(it) {
    var lv = level(it.uae_impact);
    var src = it.sources && it.sources[0] ? it.sources[0].name : '';
    return h('button', { class: 'row', type: 'button', 'data-scope': it.scope, 'data-domain': it.domain, onclick: function () { openItem(it); } },
      thumb(it),
      h('span', { class: 'row-main' },
        h('span', { class: 'row-title' }, it.title),
        h('span', { class: 'row-meta', style: 'display:block' }, src + ' • ' + ago(it.published))
      ),
      h('span', { class: 'imp lv-' + lv }, h('small', null, LEVEL_AR[lv]), h('b', null, pct(it.uae_impact)))
    );
  }
  function fillList(el, items, emptyMsg) {
    if (!state.loaded && !items.length) { el.replaceChildren(skel(72), skel(72), skel(72)); return; }
    if (!items.length) { el.replaceChildren(h('div', { class: 'empty' }, emptyMsg)); return; }
    el.replaceChildren.apply(el, items.map(row));
  }
  function renderLatest(V) {
    var base = byDomain(V).slice(0, 12).sort(function (a, b) { return Date.parse(b.published) - Date.parse(a.published); }).slice(0, 3);
    fillList($('latestList'), base, state.loaded ? 'لا توجد أخبار هامة ضمن هذه الفترة.' : '');
  }
  function renderTop(V) {
    var list = byDomain(V);
    if (state.scope !== 'all') list = list.filter(function (i) { return i.scope === state.scope; });
    fillList($('topList'), list.slice(0, 10), state.loaded ? 'لا توجد أخبار ضمن هذا التصنيف حاليًا.' : '');
  }
  function renderAnalysis(V) {
    var an = analysisFor(V), slot = $('anAi');
    slot.replaceChildren();
    if (an.ai) slot.appendChild(aiBadge());
    if (!state.loaded && !V.length) { $('anList').replaceChildren(skel(70), skel(70), skel(70)); return; }
    $('anList').replaceChildren.apply($('anList'), an.rows.map(analysisBlock));
  }
  function analysisBlock(r) {
    var lv = level(r.impact);
    return h('div', { class: 'an' },
      h('div', { class: 'an-head' }, icon(DOMAINS[r.d].icon), h('b', null, DOMAINS[r.d].name),
        r.impact == null ? null : h('span', { class: 'imp lv-' + lv }, h('small', null, LEVEL_AR[lv]), h('b', null, pct(r.impact)))),
      h('p', null, r.text));
  }

  function renderControls() {
    Array.prototype.forEach.call($('ranges').children, function (b) { b.classList.toggle('on', +b.dataset.h === state.hours); });
    Array.prototype.forEach.call($('scopeTabs').children, function (b) {
      var on = b.dataset.s === state.scope;
      b.classList.toggle('on', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    Array.prototype.forEach.call($('tabbar').children, function (b) { b.classList.toggle('on', b.dataset.d === state.domain); });
    $('lastTime').textContent = state.fetchedAt ? fmtClock(new Date(state.fetchedAt)) : '--';
  }

  /* ------------------------------------------------------------------ sheet */
  var sheet = $('sheet');
  function openSheet(node) {
    $('sheetBody').replaceChildren(node);
    if (!sheet.open) sheet.showModal();
    document.documentElement.style.overflow = 'hidden';
    sheet.querySelector('.sheet-in').scrollTop = 0;
  }
  sheet.addEventListener('close', function () { document.documentElement.style.overflow = ''; });
  sheet.addEventListener('click', function (e) { if (e.target === sheet) sheet.close(); });
  $('sheetX').addEventListener('click', function () { sheet.close(); });

  function openItem(it) {
    var lv = level(it.uae_impact);
    var srcs = (it.sources || []).map(function (s) {
      var href = safeUrl(s.url);
      var tag = KIND_AR[s.kind] ? h('em', { class: 'tag k-' + s.kind }, KIND_AR[s.kind]) : null;
      var inner = [h('b', null, icon('i-out'), s.name || 'المصدر', tag), h('span', { lang: s.lang === 'ar' ? 'ar' : 'en' }, s.title)];
      return href ? h('a', { class: 'src', href: href, target: '_blank', rel: 'noopener noreferrer' }, inner)
                  : h('div', { class: 'src' }, inner);
    });
    openSheet(h('div', null,
      h('h3', { class: 'sh-title', id: 'sheetTitle' }, it.title),
      h('div', { class: 'sh-meta' },
        h('span', { class: 'chip' }, DOMAINS[it.domain].name),
        h('span', { class: 'chip' }, SCOPES[it.scope] || ''),
        h('span', { class: 'chip' }, ago(it.published)),
        h('span', { class: 'chip imp-chip lv-' + lv }, 'التأثير: ', pct(it.uae_impact))),
      h('h4', { class: 'sh-h' }, 'المصادر الأصلية'),
      srcs));
  }

  function openBigPicture() {
    var V = visible(), bp = bigPictureFor(V);
    if (!bp) return;
    var an = analysisFor(V);
    openSheet(h('div', { class: 'an-sheet' },
      h('h3', { class: 'sh-title', id: 'sheetTitle' }, bp.title),
      h('div', { class: 'sh-meta' }, bp.ai ? aiBadge() : null),
      h('p', { class: 'sh-text' }, bp.summary),
      h('h4', { class: 'sh-h' }, 'التحليل المتكامل'),
      an.rows.map(analysisBlock)));
  }

  /* ------------------------------------------------------------------ toast */
  var toastTimer = 0;
  function toast(msg, isErr) {
    var t = $('toast');
    t.textContent = msg;
    t.classList.toggle('err', !!isErr);
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('show'); }, isErr ? 4000 : 1800);
  }

  /* ---------------------------------------------------------------- network */
  function fetchJSON(url, opts, ms) {
    var ctl = new AbortController();
    var timer = setTimeout(function () { ctl.abort(); }, ms);
    var o = Object.assign({ cache: 'no-store', signal: ctl.signal }, opts || {});
    return fetch(url, o).then(function (r) {
      if (!r.ok) throw new Error('http ' + r.status);
      return r.json();
    }).finally(function () { clearTimeout(timer); });
  }

  function setBusy(on) {
    state.busy = on;
    var b = $('refreshBtn');
    b.disabled = on;
    b.classList.toggle('busy', on);
    b.setAttribute('aria-busy', on ? 'true' : 'false');
    $('refreshLabel').textContent = on ? 'جاري التحديث...' : 'تحديث';
  }

  function loadCached(hours) {
    var c = lsGet(LS.news(hours));
    if (!c || !Array.isArray(c.items)) return false;
    var cutoff = Date.now() - hours * 3600 * 1000;
    state.items = c.items.filter(function (i) { return Date.parse(i.published) >= cutoff; });
    state.fetchedAt = c.fetchedAt || null;
    state.loaded = true;
    return true;
  }
  function freshAI(hours) {
    var c = lsGet(LS.ai(hours));
    return (c && c.data && Date.now() - c.at < 3 * 3600 * 1000) ? c.data : null;
  }

  function refresh() {
    var hours = state.hours, id = ++state.reqId;
    setBusy(true);
    return fetchJSON('/api/news?hours=' + hours, null, 15000).then(function (data) {
      if (id !== state.reqId) return;
      if (!data || !Array.isArray(data.items)) throw new Error('bad payload');
      state.items = data.items;
      state.loaded = true;
      state.fetchedAt = data.stale ? (Date.parse(data.generated_at) || state.fetchedAt) : Date.now();
      lsSet(LS.news(hours), { items: data.items.slice(0, 80), fetchedAt: state.fetchedAt });
      render();
      if (data.stale) toast('المصادر غير متاحة الآن، نعرض آخر نسخة محفوظة', true);
      runAI(id, hours);
    }).catch(function () {
      if (id !== state.reqId) return;
      state.loaded = true;
      render();
      toast('تعذّر التحديث، حاول مرة أخرى', true);
    }).finally(function () {
      if (id === state.reqId) setBusy(false);
    });
  }

  /* --------------------------------------------------------------------- AI */
  function post(url, body, ms) {
    return fetchJSON(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }, ms);
  }
  function runAI(id, hours) {
    var need = state.items.filter(function (i) { return !titleOf(i); }).slice(0, 30);
    if (need.length) doTranslate(need, id);
    var top = visible().slice(0, 25);
    if (top.length >= 3) doAnalyze(top, id, hours);
  }
  function doTranslate(need, id) {
    post('/api/translate', { items: need.map(function (i) { return { id: i.id, title: (i.sources[0] || {}).title || '' }; }) }, 28000)
      .then(function (res) {
        if (!res || !res.ok || !res.translations) return;
        var keys = Object.keys(res.translations);
        if (!keys.length) return;
        keys.forEach(function (k) { state.tr[k] = res.translations[k]; });
        var all = Object.keys(state.tr);
        if (all.length > 400) all.slice(0, all.length - 400).forEach(function (k) { delete state.tr[k]; });
        lsSet(LS.tr, state.tr);
        if (id === state.reqId) render();
      }).catch(function () { /* translation is best-effort; untranslated items simply stay hidden */ });
  }
  function doAnalyze(top, id, hours) {
    var sig = top.map(function (i) { return i.id; }).join(',');
    var cached = lsGet(LS.ai(hours));
    if (cached && cached.sig === sig && Date.now() - cached.at < 30 * 60 * 1000) {
      state.ai = cached.data;
      if (id === state.reqId) render();
      return;
    }
    post('/api/analyze', {
      hours: hours,
      items: top.map(function (i) { return { id: i.id, title: i.title, scope: i.scope, domain: i.domain, uae_impact: i.uae_impact }; })
    }, 30000).then(function (res) {
      if (!res || !res.ok || !res.big_picture) throw new Error('no ai');
      state.ai = res;
      lsSet(LS.ai(hours), { sig: sig, at: Date.now(), data: res });
    }).catch(function () {
      state.ai = (cached && Date.now() - cached.at < 3 * 3600 * 1000) ? cached.data : null;
    }).finally(function () {
      if (id === state.reqId) render();
    });
  }

  /* ----------------------------------------------------------------- events */
  function setHours(hrs) {
    if (hrs === state.hours) return;
    state.hours = hrs;
    lsSet(LS.hours, hrs);
    state.items = []; state.loaded = false; state.fetchedAt = null;
    state.ai = freshAI(hrs);
    loadCached(hrs);
    render();
    refresh();
  }

  function share() {
    var data = { title: 'مرصد الإمارات الذكي', text: 'متابعة ذكية لأهم الأخبار واتجاهاتها وتأثيرها المحتمل على الإمارات.', url: location.href.split('#')[0] };
    var copy = function () {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(data.url).then(function () { toast('تم نسخ الرابط'); }, function () { toast('تعذّر نسخ الرابط', true); });
      } else toast('تعذّر نسخ الرابط', true);
    };
    if (navigator.share) {
      navigator.share(data).catch(function (e) { if (!e || e.name !== 'AbortError') copy(); });
    } else copy();
  }

  function bind() {
    $('refreshBtn').addEventListener('click', function () { if (!state.busy) refresh(); });
    $('shareBtn').addEventListener('click', share);
    $('bpMore').addEventListener('click', openBigPicture);
    $('ranges').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-h]');
      if (b) setHours(+b.dataset.h);
    });
    $('scopeTabs').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-s]');
      if (!b) return;
      state.scope = b.dataset.s;
      render();
    });
    $('tabbar').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-d]');
      if (!b) return;
      state.domain = b.dataset.d;
      render();
    });
    window.addEventListener('resize', fit);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  }

  /* ------------------------------------------------------------ service worker */
  function registerSW() {
    if (!('serviceWorker' in navigator)) return;
    var hadController = !!navigator.serviceWorker.controller, reloaded = false;
    navigator.serviceWorker.addEventListener('controllerchange', function () {
      if (!hadController || reloaded) return;
      reloaded = true;
      location.reload();
    });
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js?v=1.0.2', { updateViaCache: 'none' }).then(function (reg) {
        reg.update().catch(function () {});
      }).catch(function () {});
    });
  }

  /* -------------------------------------------------------------------- init */
  function init() {
    var savedHours = lsGet(LS.hours);
    if (HOURS.indexOf(savedHours) >= 0) state.hours = savedHours;
    state.tr = lsGet(LS.tr) || {};
    loadCached(state.hours);
    state.ai = freshAI(state.hours);
    bind();
    tickClock();
    setInterval(tickClock, 1000);
    render();
    fit();
    refresh();
    registerSW();
  }
  init();
})();
