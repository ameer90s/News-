/* مرصد الإمارات الذكي — v2.0.0 */
(function () {
  'use strict';

  /* 2.0.0 «نبض»: a new interface. The news pipeline, the edition («نشرة المرصد», twice a day), the kept-headlines merge and the
     Gemini enrichment are unchanged from 1.3.0; what changed is how they are shown:
       - the 6/12/24/48/72-hour buttons are gone: «مباشر» has three periods (since the last edition / today / 3 days), served by
         two requests (24 h and 72 h);
       - tapping the app name plays the edition as stories (5 × 12 s = 60 s), with a red dot until the current edition is seen;
       - the big picture is a hero with three pulse lanes (the faster the pulse, the higher the potential impact on the UAE). */

  var DUP_MAX = 12;      // a story that repeats a better-ranked one by this much is hidden from «مؤثرة»
  var KEEP_MIN = 34;     // an earlier headline the new answer no longer lists is kept (inside the window) if its impact is at least this
  var KEEP_MAX = 100;    // most headlines stored per window
  var IMPACT_MIN = 55;   // «مؤثرة»: potential impact on the UAE at least this, wherever the story happens
  var TICKER_MIN = 67;   // «عاجل»: high impact (same threshold as the «مرتفع» level) and published in the last 12 hours
  var LIST_MAX = 20;     // «مباشر»: the most important stories of the period, then shown newest first
  var LIST_SHORT = 6;    // shown before «عرض كل الأخبار»
  var STORY_MS = 12000;  // one story = 12 s, five stories = the edition in 60 seconds
  var STORY_N = 5;
  var EDITION_AT = [[11, 43], [23, 43]];          // Dubai time of the scheduled edition (tools/edition_task.md)
  var RADAR_MAX_AGE = 36 * 3600 * 1000;            // an edition older than this is ignored (the server applies the same limit)
  var DUBAI = 4 * 3600 * 1000;                     // the UAE has no daylight saving: UTC+4 all year
  var PERIODS = { edition: 24, today: 24, days3: 72 };
  var DOMAINS = {
    political: { name: 'سياسي', icon: 'i-bank' },
    economic: { name: 'اقتصادي', icon: 'i-chart' },
    military: { name: 'عسكري', icon: 'i-shield' }
  };
  var DOMAIN_KEYS = ['political', 'economic', 'military'];
  var SCOPES = { local: 'محلي', regional: 'إقليمي', international: 'دولي' };
  var SCOPES_F = { local: 'محلية', regional: 'إقليمية', international: 'دولية' };
  var LEVEL_AR = { low: 'منخفض', mid: 'متوسط', high: 'مرتفع', none: '—' };
  var KIND_AR = { official: 'رسمي', specialized: 'متخصص', agency: 'وكالة/قناة كبرى', press: 'صحافة محلية' };
  var LEAK_CLS = { unverified: 'st-unv', partial: 'st-part', denied: 'st-den', confirmed: 'st-conf' };
  var CONF_N = { 'منخفضة': 1, 'متوسطة': 2, 'عالية': 3 };
  var MONTHS = { 'يناير': 1, 'فبراير': 2, 'مارس': 3, 'أبريل': 4, 'ابريل': 4, 'إبريل': 4, 'مايو': 5, 'يونيو': 6, 'يوليو': 7,
    'أغسطس': 8, 'اغسطس': 8, 'سبتمبر': 9, 'أكتوبر': 10, 'اكتوبر': 10, 'نوفمبر': 11, 'ديسمبر': 12 };
  var MONTH_AR = ['', 'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];
  var ECG = {   // pulse shapes for the hero lanes: calmer line for a lower level
    none: 'M0 16H200',
    low: 'M0 16H60L66 16L70 11L74 21L78 16H140L146 16L150 12L154 20L158 16H200',
    mid: 'M0 16H30L36 16L42 6L48 26L54 12L58 16H110L116 16L122 8L128 24L132 16H200',
    high: 'M0 16H20L26 16L32 3L38 29L44 9L48 16H78L84 16L90 4L96 28L102 10L106 16H140L146 16L152 3L158 29L164 9L168 16H200'
  };
  var STORY_BG = {
    economic: ['linear-gradient(160deg,#F59E0B 0%,#DB2777 40%,#4C1D95 75%,#05070D 100%)', 'linear-gradient(160deg,#10B981 0%,#0891B2 45%,#1E293B 78%,#05070D 100%)'],
    political: ['linear-gradient(160deg,#22D3EE 0%,#2563EB 40%,#312E81 75%,#05070D 100%)', 'linear-gradient(160deg,#A78BFA 0%,#4F46E5 42%,#1E1B4B 76%,#05070D 100%)'],
    military: ['linear-gradient(160deg,#E11D48 0%,#9333EA 45%,#1E1B4B 78%,#05070D 100%)', 'linear-gradient(160deg,#DB2777 0%,#7C3AED 40%,#0B0F1A 78%,#05070D 100%)']
  };
  var SVGNS = 'http://www.w3.org/2000/svg';
  var EDITION = 'نشرة المرصد';
  var LS = {
    radar: 'mirsad.radar',
    period: 'mirsad.period',
    domain: 'mirsad.domain',
    tr: 'mirsad.tr',
    theme: 'mirsad.theme',
    visit: 'mirsad.visit',
    seen: 'mirsad.storySeen',
    news: function (h) { return 'mirsad.news.' + h; },
    ai: function (h) { return 'mirsad.ai.' + h; }
  };

  var state = {
    period: 'edition', hours: 24, scope: 'all', domain: 'political', expanded: false,
    items: [], loaded: false, fetchedAt: null,
    tr: {}, ai: null, radar: null, busy: false, reqId: 0, prevVisit: null
  };

  var $ = function (id) { return document.getElementById(id); };
  var reduceMotion = false;
  try { reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { reduceMotion = false; }

  /* ------------------------------------------------------------- storage */
  function lsGet(k) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage full / blocked */ } }
  function lsDel(k) { try { localStorage.removeItem(k); } catch (e) { /* blocked */ } }

  /* ---------------------------------------------------------------- utils */
  function h(tag, props) {
    var el = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        var v = props[k];
        if (v == null || v === false) return;
        if (k === 'class') el.className = v;
        else if (k === 'text') el.textContent = v;
        else if (k === 'style') el.setAttribute('style', v);
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
  function svgEl(tag, attrs) {
    var e = document.createElementNS(SVGNS, tag);
    Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }
  // like replaceChildren, but skips null / false parts (replaceChildren would print them as the text "null")
  function fill(el) {
    el.replaceChildren();
    for (var i = 1; i < arguments.length; i++) append(el, arguments[i]);
    return el;
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
  function hoursLabel(n) { return n === 72 ? '3 أيام' : n + (n <= 10 ? ' ساعات' : ' ساعة'); }
  function scrollBehavior() { return reduceMotion ? 'auto' : 'smooth'; }

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

  /* ------------------------------------------------------------ Dubai time */
  function dubai(ts) {
    var u = new Date(ts + DUBAI);
    return { y: u.getUTCFullYear(), m: u.getUTCMonth() + 1, d: u.getUTCDate(), hh: u.getUTCHours(), mm: u.getUTCMinutes() };
  }
  function dayIndex(y, m, d) { return Math.round(Date.UTC(y, m - 1, d) / 86400000); }
  function two(n) { return ('0' + n).slice(-2); }
  function fmtClock(d) {
    var p = dubai(d.getTime());
    return ((p.hh % 12) || 12) + ':' + two(p.mm) + ' ' + (p.hh < 12 ? 'ص' : 'م');
  }
  function nextEdition(now) {
    var p = dubai(now), base = Date.UTC(p.y, p.m - 1, p.d) - DUBAI;
    for (var day = 0; day < 2; day++) {
      for (var i = 0; i < EDITION_AT.length; i++) {
        var t = base + day * 86400000 + (EDITION_AT[i][0] * 60 + EDITION_AT[i][1]) * 60000;
        if (t > now) return new Date(t);
      }
    }
    return new Date(base + 86400000 + (EDITION_AT[0][0] * 60 + EDITION_AT[0][1]) * 60000);
  }

  /* ------------------------------------------------- keep what the last update found */
  // Each update asks for the whole window again, but an answer is never complete (a source can be slow or cut, a query returns a
  // limited number of rows). A headline that was on the page and is still inside the window is therefore kept when the new
  // answer does not list it, unless the new answer already has the same story under another headline. Importance is re-aged
  // (recency counts 20 points over the window, as on the server) so old finds do not outrank fresh ones.
  function normAr(t) {
    return String(t || '').replace(/[ً-ْـ]/g, '').replace(/[أإآ]/g, 'ا').replace(/ى/g, 'ي').replace(/ة/g, 'ه').toLowerCase();
  }
  function tokenSet(t) {
    var out = {}, m = normAr(t).match(/[؀-ۿa-z0-9]+/g) || [];
    m.forEach(function (w) {
      if (w.indexOf('ال') === 0 && w.length > 4) w = w.slice(2);
      if (w.length >= 3 || (/^\d+$/.test(w) && w.length === 2)) out[w] = 1;
    });
    return out;
  }
  function sameStory(a, b) {
    var na = Object.keys(a).length, nb = Object.keys(b).length;
    if (na < 3 || nb < 3) return false;
    var shared = 0;
    Object.keys(a).forEach(function (k) { if (b[k]) shared++; });
    var j = shared / (na + nb - shared);
    return j >= 0.4 || (shared >= 4 && j >= 0.3);
  }
  function mergeKept(incoming, previous, prevAt, hours) {
    if (!previous || !previous.length) return incoming;
    var now = Date.now(), cutoff = now - hours * 3600 * 1000, have = {}, sets = [];
    incoming.forEach(function (i) {
      have[i.id] = 1;
      sets.push(tokenSet(titleOf(i) || i.title || ''));
      (i.sources || []).forEach(function (s) { if (s.title) sets.push(tokenSet(s.title)); });
    });
    var aged = Math.max(0, now - (prevAt || now)) / (hours * 3600 * 1000) * 20, kept = [];
    previous.forEach(function (p) {
      if (have[p.id] || p.radar || !(p.uae_impact >= KEEP_MIN) || !(Date.parse(p.published) >= cutoff)) return;
      var t = titleOf(p);
      if (!t) return;
      var ts = tokenSet(t);
      for (var k = 0; k < sets.length; k++) if (sameStory(ts, sets[k])) return;
      kept.push(Object.assign({}, p, { importance: (p.importance || 0) - aged, kept: true }));
    });
    if (!kept.length) return incoming;
    return incoming.concat(kept).sort(function (x, y) { return y.importance - x.importance; }).slice(0, KEEP_MAX + 20);
  }

  /* ---------------------------------------------------------------- clock */
  var lastClock = '';
  function tickClock() {
    var now = new Date(), t = fmtClock(now);
    if (t === lastClock) return;
    lastClock = t;
    $('clock').textContent = t;
    $('nextEd').textContent = fmtClock(nextEdition(now.getTime()));
    fit();
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
    var rs = state.ai && state.ai.rescored, out = [];
    state.items.forEach(function (it) {
      var t = titleOf(it);
      if (!t) return;
      var o = Object.assign({}, it, { title: t, impact0: it.uae_impact });
      var r = rs && !it.radar && rs[it.id];
      if (r && typeof r.impact === 'number') {
        o.importance = (it.importance || 0) + 0.65 * (r.impact - it.uae_impact);
        o.uae_impact = r.impact;
        if (r.why) o.why = r.why;
      }
      out.push(o);
    });
    if (rs) out.sort(function (x, y) { return y.importance - x.importance; });
    return out;
  }
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

  /* ------------------------------------------------------------ the edition */
  // «نشرة المرصد»: a UAE-focused edition written twice a day by a scheduled task. While it is fresh it leads the hero, the
  // analysis, «أرقام اليوم», «خلال 48 ساعة», the rumours file and the 60-second stories; its stories arrive as ordinary news
  // items flagged radar:true.
  function radarNow() {
    var r = state.radar;
    if (!r || !r.domains) return null;
    var age = Date.now() - Date.parse(r.created_at);
    return age < RADAR_MAX_AGE ? r : null;
  }
  function stripRefs(t) { return String(t || '').replace(/\s*\[\d+(?:\s*[,،]\s*\d+)*\]/g, '').replace(/\s+([،.؛:)])/g, '$1').trim(); }
  function radarTime(r) { var m = /·\s*([\d:]+)\s*$/.exec(r.label_ar || ''); return m ? m[1] : fmtClock(new Date(Date.parse(r.created_at))); }
  // title = the edition's own headline when it has one, else the first clause of the overview; the summary then continues
  // from the second sentence so the card does not say the same thing twice
  function radarLead(r) {
    var ex = r.executive || {}, ov = ex.overview || '';
    if (ex.headline) return { title: ex.headline, summary: ov };
    var m = /[.؟!]\s/.exec(ov), first = m ? ov.slice(0, m.index) : ov, rest = m ? ov.slice(m.index + 2).trim() : '';
    var title = first;
    if (title.length > 95) {
      var c = title.indexOf('،', 28);
      title = (c > 0 && c <= 95) ? title.slice(0, c) : title.slice(0, Math.max(40, title.lastIndexOf(' ', 92))) + '…';
    }
    return { title: title, summary: rest || ov };
  }
  function clip(t, max) {
    t = String(t || '');
    if (t.length <= max) return t;
    var cut = t.lastIndexOf('. ', max);
    if (cut > max * 0.5) return t.slice(0, cut + 1);
    return t.slice(0, Math.max(0, t.lastIndexOf(' ', max - 1))) + '…';
  }

  /* --------------------------------------------------------------- analysis */
  function localDomainText(d, stat) {
    if (!stat.top) return 'لا توجد أخبار بارزة في هذا المجال خلال آخر ' + hoursLabel(state.hours) + '.';
    var lv = level(stat.impact);
    var tail = { high: 'التأثير المحتمل على الإمارات مرتفع ويستدعي المتابعة الدقيقة.', mid: 'التأثير المحتمل على الإمارات متوسط ويستحق المتابعة.', low: 'التأثير المحتمل على الإمارات محدود حاليًا.', none: '' }[lv];
    return 'عدد الأخبار المرصودة: ' + stat.list.length + '. الأعلى تأثيرًا: «' + stat.top.title + '». ' + tail;
  }
  // Order of preference: the edition's own analysis (written after reading the articles), then Gemini's analysis of the
  // current list (badge «تحليل ذكي AI» only when the text really is Gemini's), then the local text.
  function bigPictureFor(V) {
    var rd = radarNow();
    if (rd && rd.executive && rd.executive.overview) { var lead = radarLead(rd); return { title: lead.title, summary: lead.summary, radar: true }; }
    if (state.ai && state.ai.big_picture) return { title: state.ai.big_picture.title, summary: state.ai.big_picture.summary, ai: true };
    if (!V.length) return null;
    var stats = domainStats(V), best = null;
    DOMAIN_KEYS.forEach(function (d) { if (stats[d].impact != null && (!best || stats[d].impact > stats[best].impact)) best = d; });
    var s = 'خلال آخر ' + hoursLabel(state.hours) + ' رصد المرصد ' + V.length + ' خبرًا. أبرز التطورات: «' + V[0].title + '»';
    if (V[1]) s += '، و«' + V[1].title + '»';
    s += '.';
    if (best) s += ' أعلى مستوى تأثير على الإمارات في المجال ' + DOMAINS[best].name + ' (' + Math.round(stats[best].impact) + '%).';
    return { title: V[0].title, summary: s };
  }
  function aiBadge() { return h('span', { class: 'ai-badge' }, icon('i-spark'), 'تحليل ذكي AI'); }
  function edBadge() { return h('span', { class: 'ai-badge ed' }, icon('i-spark'), EDITION); }

  /* ----------------------------------------------------------------- render */
  function render() {
    var V = visible();
    renderHero(V);
    renderTicker(V);
    renderFigures();
    renderLive(V);
    renderAnalysis(V);
    renderAgenda();
    renderLeaks();
    renderControls();
    renderRing();
  }

  // re-renders must not replay the entry animations of cards that were already on screen
  var shown = {};
  function once(el, key, i) {
    if (shown[key]) { el.style.animation = 'none'; el.classList.add('noanim'); }
    else { shown[key] = 1; if (i) el.style.animationDelay = Math.min(i, 8) * 0.07 + 's'; }
    return el;
  }

  /* ---- hero */
  function emphasize(title) {
    var re = /\d[\d.,٫]*\s*(?:%|٪)?(?:\s*(?:مليار|مليون|ألف))?(?:\s*(?:دولارًا|دولارا|دولار|درهمًا|درهم|برميل))?/;
    var m = re.exec(title);
    if (!m) return title;
    var tok = m[0].trim();
    if (!(/\d{2,}|[.,٫%٪]/.test(tok) || /[؀-ۿ]/.test(tok))) return title;
    return [title.slice(0, m.index), h('em', null, tok), title.slice(m.index + tok.length)];
  }
  function laneSpeed(v) {
    if (v == null) return '6s';
    return v >= 85 ? '1.5s' : (v > 66 ? '1.9s' : (v > 33 ? '3.4s' : '4.6s'));
  }
  function buildLane(d) {
    var path = function (cls) { return svgEl('path', { class: cls, d: ECG.none }); };
    var svg = svgEl('svg', { class: 'ecg', viewBox: '0 0 200 32', preserveAspectRatio: 'none', 'aria-hidden': 'true' });
    svg.appendChild(path('bgp'));
    svg.appendChild(path('fgp'));
    return h('div', { class: 'lane lv-none', 'data-d': d },
      h('span', { class: 'lname' }, icon(DOMAINS[d].icon), DOMAINS[d].name),
      svg,
      h('span', { class: 'lpct' }, h('b'), h('small')));
  }
  function renderLanes(stats) {
    var box = $('lanes');
    if (box.children.length !== 3) box.replaceChildren.apply(box, DOMAIN_KEYS.map(buildLane));
    DOMAIN_KEYS.forEach(function (d, i) {
      var el = box.children[i], v = stats[d].impact, lv = level(v);
      el.className = 'lane lv-' + lv;
      el.style.setProperty('--sp', laneSpeed(v));
      var ps = el.querySelectorAll('path');
      if (ps[0].getAttribute('d') !== ECG[lv]) { ps[0].setAttribute('d', ECG[lv]); ps[1].setAttribute('d', ECG[lv]); }
      el.querySelector('.lpct b').textContent = v == null ? '—' : Math.round(v) + '%';
      el.querySelector('.lpct small').textContent = v == null ? 'لا أخبار' : LEVEL_AR[lv];
    });
  }
  function renderHero(V) {
    var t = $('heroTitle'), s = $('heroSum'), chip = $('heroChip'), more = $('heroMore');
    chip.replaceChildren();
    renderLanes(domainStats(V));
    if (!state.loaded && !V.length) {
      t.replaceChildren(skel(22, '88%'), skel(22, '60%'));
      s.replaceChildren(skel(13, '100%'), skel(13, '90%'));
      more.hidden = true;
      return;
    }
    var bp = bigPictureFor(V);
    if (!bp) {
      t.textContent = 'لا توجد أخبار لعرضها حاليًا';
      s.textContent = 'اضغط «تحديث» للمحاولة من جديد.';
      more.hidden = true;
      return;
    }
    var rd = radarNow();
    if (bp.radar) chip.appendChild(h('span', { class: 'hbadge ed' }, icon('i-spark'), EDITION + ' · ' + radarTime(rd)));
    else if (bp.ai) chip.appendChild(h('span', { class: 'hbadge ai' }, icon('i-spark'), 'تحليل ذكي AI'));
    t.replaceChildren.apply(t, [].concat(emphasize(bp.title)));
    s.replaceChildren(h('span', { class: 'hero-legend' }, 'سرعة النبض = مستوى التأثير على الإمارات.'), clip(bp.summary, 320));
    more.hidden = false;
    more.textContent = bp.radar ? 'اقرأ النشرة كاملة' : 'التحليل الكامل';
  }

  /* ---- ticker */
  var tickerSig = '';
  function renderTicker(V) {
    var cutoff = Date.now() - 12 * 3600 * 1000;
    var list = V.filter(function (i) { return i.uae_impact >= TICKER_MIN && Date.parse(i.published) >= cutoff && !(i.dup >= DUP_MAX); }).slice(0, 6);
    var sig = list.map(function (i) { return i.id + ':' + i.title; }).join('|');
    if (sig === tickerSig) return;
    tickerSig = sig;
    $('ticker').hidden = !list.length;
    if (!list.length) { $('tickerStrip').replaceChildren(); return; }
    var copy = function (hidden) {
      var out = [];
      list.forEach(function (it) {
        out.push(h('button', { type: 'button', tabindex: hidden ? '-1' : null, onclick: function () { openItem(it); } }, it.title));
        out.push(h('span', { class: 'tk-sep', 'aria-hidden': 'true' }, '|'));
      });
      return h('span', { style: 'display:flex', 'aria-hidden': hidden ? 'true' : null }, out);
    };
    var strip = $('tickerStrip'), chars = list.reduce(function (n, i) { return n + i.title.length; }, 0);
    strip.replaceChildren(copy(false), copy(true));
    strip.style.animationDuration = Math.max(22, Math.round(chars * 0.22)) + 's';
  }

  /* ---- figures */
  function renderFigures() {
    var rd = radarNow(), figs = rd && Array.isArray(rd.figures) ? rd.figures : [];
    $('figures').hidden = !figs.length;
    if (!figs.length) return;
    $('figSrc').textContent = EDITION + ' · ' + radarTime(rd);
    $('tiles').replaceChildren.apply($('tiles'), figs.map(function (f, i) {
      var dir = f.dir === 'up' || f.dir === 'down' ? f.dir : 'flat';
      var arrow = dir === 'up' ? '▲ ' : (dir === 'down' ? '▼ ' : '');
      return once(h('div', { class: 'tile' },
        h('small', null, f.label),
        h('b', { dir: 'auto' }, f.value),
        f.change ? h('span', { class: 'chg ' + dir }, arrow + f.change) : null), 'fig:' + rd.id + ':' + i, i);
    }));
  }

  /* ---- «مباشر» */
  function periodList(V) {
    var rd = radarNow(), now = Date.now();
    if (state.period === 'edition') {
      var since = rd ? Date.parse(rd.created_at) : now - 12 * 3600 * 1000;
      return V.filter(function (i) { return !i.radar && Date.parse(i.published) > since; });
    }
    if (state.period === 'today') return V.filter(function (i) { return i.radar || Date.parse(i.published) >= now - 24 * 3600 * 1000; });
    return V;
  }
  function liveItems(V) {
    var list = periodList(V);
    if (state.scope === 'impact') {
      return list.filter(function (i) { return i.uae_impact >= IMPACT_MIN && !(i.dup >= DUP_MAX); })
                 .sort(function (x, y) { return (y.uae_impact - x.uae_impact) || (y.importance - x.importance); }).slice(0, LIST_MAX);
    }
    if (state.scope !== 'all') list = list.filter(function (i) { return i.scope === state.scope; });
    return list.slice(0, LIST_MAX).sort(function (a, b) { return Date.parse(b.published) - Date.parse(a.published); });
  }
  function timeCell(it) {
    if (it.radar && it.when) {
      var w = String(it.when).trim(), sp = w.indexOf(' ');
      return h('span', { class: 'tt day' }, sp > 0 ? [w.slice(0, sp), h('br'), w.slice(sp + 1)] : w, h('i', { class: 'tdot' }));
    }
    var ts = Date.parse(it.published), p = dubai(ts), n = dubai(Date.now());
    var diff = dayIndex(n.y, n.m, n.d) - dayIndex(p.y, p.m, p.d);
    var fresh = Date.now() - ts < 3600 * 1000;
    if (diff <= 0) return h('span', { class: 'tt' }, two(p.hh) + ':' + two(p.mm), h('i', { class: 'tdot' + (fresh ? ' now' : '') }));
    if (diff === 1) return h('span', { class: 'tt day' }, 'أمس', h('i', { class: 'tdot' }));
    return h('span', { class: 'tt day' }, String(p.d), h('br'), MONTH_AR[p.m], h('i', { class: 'tdot' }));
  }
  function isNew(it) {
    if (it.radar || !state.prevVisit) return false;
    var ts = Date.parse(it.published);
    return ts > state.prevVisit && Date.now() - ts < 24 * 3600 * 1000;
  }
  function tlRow(it, i) {
    var lv = level(it.uae_impact), src = it.sources && it.sources[0] ? it.sources[0].name : '';
    var meta = [src, SCOPES_F[it.scope]].filter(Boolean).join(' • ');
    return h('div', { class: 'tl', 'data-id': it.id, 'data-scope': it.scope },
      timeCell(it),
      once(h('button', { type: 'button', class: 'titem', onclick: function () { openItem(it); } },
        h('span', { class: 'tmain' },
          h('b', null, it.title, isNew(it) ? h('span', { class: 'new' }, 'جديد') : null),
          h('small', null, meta)),
        h('span', { class: 'imp lv-' + lv }, h('b', null, pct(it.uae_impact)), h('small', null, LEVEL_AR[lv]))), 'tl:' + it.id, i));
  }
  function renderLive(V) {
    var el = $('liveList'), more = $('liveMore');
    if (!state.loaded && !V.length) {
      el.replaceChildren(skel(70), skel(70), skel(70));
      more.hidden = true;
      $('liveCount').textContent = '';
      return;
    }
    var list = liveItems(V);
    $('liveCount').textContent = list.length ? plural(list.length, 'خبر واحد', 'خبران', 'أخبار', 'خبرًا') : '';
    if (!list.length) {
      var rd = radarNow(), msg, act = null;
      if (state.scope === 'impact') msg = 'لا توجد أخبار عالية التأثير على الإمارات في هذه الفترة.';
      else if (state.scope !== 'all') msg = 'لا توجد أخبار ضمن هذا التصنيف في هذه الفترة.';
      else if (state.period === 'edition') {
        msg = rd ? 'لا أخبار جديدة منذ ' + EDITION + ' (' + radarTime(rd) + ').' : 'لا أخبار جديدة خلال آخر 12 ساعة.';
        act = h('button', { type: 'button', class: 'more', onclick: function () { setPeriod('today'); } }, 'اعرض أخبار اليوم');
      } else msg = 'لا توجد أخبار في هذه الفترة.';
      fill(el, h('div', { class: 'empty' }, msg), act);
      more.hidden = true;
      return;
    }
    var shownList = state.expanded ? list : list.slice(0, LIST_SHORT);
    el.replaceChildren.apply(el, shownList.map(tlRow));
    more.hidden = list.length <= LIST_SHORT;
    more.textContent = state.expanded ? 'عرض أقل' : 'عرض كل الأخبار (' + list.length + ')';
  }

  /* ---- analysis */
  function renderAnalysis(V) {
    var body = $('anBody'), badge = $('anBadge'), d = state.domain, rd = radarNow();
    var stats = domainStats(V), st = stats[d], ai = state.ai && state.ai.analysis && state.ai.analysis[d];
    badge.replaceChildren();
    if (!state.loaded && !V.length) { body.replaceChildren(skel(14, '70%'), skel(20, '90%'), skel(60)); return; }
    var dd = rd && rd.domains[d], risk, riskWord, head, text, watch = [], open;
    if (dd) {
      badge.appendChild(edBadge());
      risk = dd.risk && dd.risk !== 'none' ? dd.risk : 'none';
      riskWord = dd.risk_level || LEVEL_AR[risk];
      head = stripRefs(dd.headline);
      text = dd.levels && dd.levels.uae ? [h('b', null, 'على الإمارات: '), clip(stripRefs(dd.levels.uae), 280)] : (dd.summary ? clip(stripRefs(dd.summary), 280) : '');
      watch = (dd.watch_list || []).slice(0, 4);
      open = function () { openRadar(d); };
    } else {
      if (ai) badge.appendChild(aiBadge());
      risk = level(st.impact);
      riskWord = LEVEL_AR[risk];
      head = ai ? '' : (st.top ? st.top.title : '');
      text = ai ? ai.text : localDomainText(d, st);
      open = openBigPicture;
    }
    var ilv = level(st.impact);
    fill(body,
      h('div', { class: 'an-row lv-' + risk }, h('span', null, 'المخاطر'),
        h('div', { class: 'risk', 'data-r': risk, 'aria-hidden': 'true' }, h('i'), h('i'), h('i')), h('b', null, riskWord)),
      st.impact != null ? h('span', { class: 'an-imp lv-' + ilv }, 'التأثير على الإمارات', h('b', null, Math.round(st.impact) + '%'), LEVEL_AR[ilv]) : null,
      head ? h('h4', { class: 'an-h' }, head) : null,
      text ? h('p', { class: 'an-p' }, text) : null,
      watch.length ? h('div', { class: 'wls' }, h('span', { class: 'wl-h' }, 'ما يُراقَب'), watch.map(function (w) { return h('span', { class: 'wl' }, stripRefs(w)); })) : null,
      (dd || st.top) ? h('button', { type: 'button', class: 'an-more', onclick: open }, dd ? 'التحليل الكامل لهذا المجال' : 'التحليل الكامل', icon('i-left')) : null);
  }

  /* ---- «خلال 48 ساعة» */
  function parseAgenda(s, base) {
    var raw = stripRefs(s), t = raw.replace(/[٠-٩]/g, function (c) { return String(c.charCodeAt(0) - 0x660); });
    var m = /^\s*(\d{1,2})(?:\s*[–—-]\s*(\d{1,2}))?\s+([؀-ۿ]+)\s*[:：]\s*(.+)$/.exec(t);
    if (!m || !MONTHS[m[3]]) return { text: raw };
    var mon = MONTHS[m[3]], y = base.y;
    if (mon < base.m - 6) y++;
    else if (mon > base.m + 6) y--;
    var d1 = +m[1], d2 = m[2] ? +m[2] : d1;
    return { start: dayIndex(y, mon, d1), end: dayIndex(y, mon, d2), label: m[2] ? d1 + '–' + d2 : String(d1), month: MONTH_AR[mon], text: m[4].trim() };
  }
  function relDay(a) {
    var n = dubai(Date.now()), today = dayIndex(n.y, n.m, n.d), diff = a.start - today;
    if (a.end < today) return null;
    if (diff < 0) return { t: 'جارٍ الآن', now: true };
    if (diff === 0) return { t: 'اليوم', now: true };
    if (diff === 1) return { t: 'غدًا' };
    if (diff === 2) return { t: 'بعد غد' };
    return { t: 'بعد ' + plural(diff, 'يوم', 'يومين', 'أيام', 'يومًا') };
  }
  var AG_DAY = ['#0E7490', '#BE185D', '#6D28D9', '#B45309'], AG_NIGHT = ['#22D3EE', '#F472B6', '#A78BFA', '#FBBF24'];
  function renderAgenda() {
    var rd = radarNow(), src = rd && rd.executive && Array.isArray(rd.executive.next_48h) ? rd.executive.next_48h : [];
    var base = rd ? dubai(Date.parse(rd.created_at)) : null, rows = [];
    src.forEach(function (s) {
      var a = parseAgenda(s, base);
      var rel = a.start != null ? relDay(a) : { t: '' };
      if (!rel) return;                                   // already over
      var i = rows.length;
      var block = h('span', { class: 'agd', style: '--ag:' + AG_DAY[i % 4] + ';--agn:' + AG_NIGHT[i % 4], 'aria-hidden': a.start != null ? null : 'true' },
        a.start != null ? [h('b', { dir: 'ltr' }, a.label), h('small', null, a.month)] : icon('i-doc'));
      rows.push(once(h('div', { class: 'ag' }, block, h('span', { class: 'ag-t' }, a.text),
        rel.t ? h('span', { class: 'ag-rel' + (rel.now ? ' today' : '') }, rel.t) : null), 'ag:' + rd.id + ':' + s, i));
    });
    $('agenda').hidden = !rows.length;
    $('agList').replaceChildren.apply($('agList'), rows);
  }

  /* ---- rumours file */
  // Claims reported by named outlets that are not (all) confirmed. They come only from the edition, never feed the hero, the
  // analysis or the news list, and are always shown with their status (the stamp), confidence and source.
  function leakCard(lk, onOpen, key, i) {
    var cls = LEAK_CLS[lk.state] || 'st-unv', n = CONF_N[lk.confidence] || 1, dots = [];
    for (var k = 0; k < 3; k++) dots.push(h('i', { class: k < n ? 'f' : null }));
    var meta = [lk.reported_by, lk.when].filter(Boolean).join(' • ');
    var b = h('button', { type: 'button', class: 'lk', 'data-domain': lk.domain || '', onclick: onOpen },
      h('span', { class: 'stp ' + cls }, lk.status),
      h('span', { class: 'lk-t' }, lk.claim),
      h('span', { class: 'lk-m' }, meta ? meta + ' • ' : '', 'الثقة: ' + (lk.confidence || 'منخفضة'),
        h('span', { class: 'conf ' + cls, 'aria-hidden': 'true' }, dots)));
    return key ? once(b, key, i) : b;
  }
  function renderLeaks() {
    var el = $('leakList');
    if (!state.loaded && !state.items.length) { el.replaceChildren(skel(84), skel(84)); return; }
    var rd = radarNow(), L = rd && Array.isArray(rd.leaks) ? rd.leaks : null;
    if (!L) { el.replaceChildren(h('div', { class: 'empty' }, 'التسريبات والإشاعات تأتي مع ' + EDITION + ' (مرتين يوميًا)، ولا توجد نشرة حديثة الآن.')); return; }
    if (!L.length) { el.replaceChildren(h('div', { class: 'empty' }, 'لا توجد تسريبات أو إشاعات بارزة في هذه النشرة.')); return; }
    el.replaceChildren.apply(el, L.map(function (lk, i) { return leakCard(lk, function () { openLeak(lk); }, 'lk:' + rd.id + ':' + i, i); }));
  }

  /* ---- controls */
  function setOn(box, attr, val) {
    Array.prototype.forEach.call(box.children, function (b) {
      var on = b.getAttribute(attr) === val;
      b.classList.toggle('on', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
  }
  function renderControls() {
    setOn($('periodTabs'), 'data-p', state.period);
    setOn($('scopeChips'), 'data-s', state.scope);
    setOn($('domainTabs'), 'data-d', state.domain);
    $('lastTime').textContent = state.fetchedAt ? fmtClock(new Date(state.fetchedAt)) : '--';
    $('refreshBtn').setAttribute('aria-label', state.busy ? 'جاري التحديث' : 'تحديث الأخبار' + (state.fetchedAt ? '، آخر تحديث ' + fmtClock(new Date(state.fetchedAt)) : ''));
  }
  function renderRing() {
    var rd = radarNow();
    $('ringDot').hidden = !(rd && lsGet(LS.seen) !== rd.id);
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

  function srcLinks(list, title) {
    return (list || []).map(function (s) {
      var href = safeUrl(s.url);
      var tag = KIND_AR[s.kind] ? h('em', { class: 'tag k-' + s.kind }, KIND_AR[s.kind]) : null;
      var inner = [h('b', null, icon('i-out'), s.name || 'المصدر', tag)];
      if (s.title && s.title !== title) inner.push(h('span', { lang: s.lang === 'ar' ? 'ar' : 'en' }, s.title));
      return href ? h('a', { class: 'src', href: href, target: '_blank', rel: 'noopener noreferrer' }, inner) : h('div', { class: 'src' }, inner);
    });
  }
  function openItem(it, back) {
    var lv = level(it.uae_impact);
    openSheet(h('div', null,
      back ? backButton(back) : null,
      h('h3', { class: 'sh-title', id: 'sheetTitle' }, it.title),
      h('div', { class: 'sh-meta' },
        it.radar ? h('span', { class: 'chip chip-ed' }, EDITION) : null,
        h('span', { class: 'chip' }, DOMAINS[it.domain] ? DOMAINS[it.domain].name : ''),
        SCOPES[it.scope] ? h('span', { class: 'chip' }, SCOPES[it.scope]) : null,
        h('span', { class: 'chip' }, it.radar && it.when ? it.when : ago(it.published)),
        it.updates >= 3 ? h('span', { class: 'chip' }, 'قصة متطورة • ' + plural(it.updates, 'تحديث', 'تحديثان', 'تحديثات', 'تحديثًا')) : null,
        h('span', { class: 'chip imp-chip lv-' + lv }, 'التأثير: ', pct(it.uae_impact))),
      it.summary ? h('p', { class: 'sh-text' }, it.summary) : null,
      (it.why && it.uae_impact > 33) ? h('p', { class: 'sh-why lv-' + lv }, h('b', null, 'لماذا يهم الإمارات: '), it.why) : null,
      h('h4', { class: 'sh-h' }, 'المصادر الأصلية'),
      srcLinks(it.sources, it.title)));
  }
  function openLeak(lk, back) {
    var cls = LEAK_CLS[lk.state] || 'st-unv';
    openSheet(h('div', null,
      back ? backButton(back) : null,
      h('h3', { class: 'sh-title', id: 'sheetTitle' }, lk.claim),
      h('div', { class: 'sh-meta' },
        h('span', { class: 'chip st-chip ' + cls }, lk.status),
        h('span', { class: 'chip' }, 'الثقة: ' + (lk.confidence || 'منخفضة')),
        lk.domain && DOMAINS[lk.domain] ? h('span', { class: 'chip' }, DOMAINS[lk.domain].name) : null,
        lk.when ? h('span', { class: 'chip' }, lk.when) : null),
      h('p', { class: 'lk-warn' }, 'ادعاء منقول عن مصادر، وليس خبرًا مؤكدًا.'),
      lk.reported_by ? h('p', { class: 'sh-text' }, h('b', null, 'من نشره: '), lk.reported_by) : null,
      lk.why ? h('p', { class: 'sh-text' }, h('b', null, 'لماذا يهم: '), lk.why) : null,
      lk.denial ? h('p', { class: 'sh-text' }, h('b', null, 'الرد أو النفي: '), lk.denial) : null,
      h('h4', { class: 'sh-h' }, 'المصادر'),
      srcLinks(lk.sources)));
  }
  function backButton(fn) {
    return h('button', { type: 'button', class: 'sh-back', onclick: fn }, icon('i-left'), 'العودة إلى النشرة');
  }
  // «[3]» inside the edition's text becomes a button that opens story 3 of that domain
  function findItem(id) {
    if (!id) return null;
    var V = visible();
    for (var i = 0; i < V.length; i++) if (V[i].id === id) return V[i];
    return null;
  }
  function cites(text, d, dom) {
    var out = [], re = /\[(\d+(?:\s*[,،]\s*\d+)*)\]/g, last = 0, m;
    text = String(text || '');
    while ((m = re.exec(text))) {
      if (m.index > last) out.push(text.slice(last, m.index));
      m[1].split(/\s*[,،]\s*/).forEach(function (n) { out.push(citeBtn(d, dom, n)); });
      last = m.index + m[0].length;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
  }
  function citeBtn(d, dom, n) {
    var it = findItem(dom && dom.refs && dom.refs[n]);
    if (!it) return h('span', { class: 'cite off' }, n);
    return h('button', { type: 'button', class: 'cite', 'aria-label': 'الخبر ' + n, onclick: function () { openItem(it, function () { openRadar(d); }); } }, n);
  }
  function list(arr, d, dom) {
    if (!arr || !arr.length) return null;
    return h('ul', { class: 'rd-list' }, arr.map(function (t) { return h('li', null, d ? cites(t, d, dom) : stripRefs(t)); }));
  }
  function section(title, node) { return node ? [h('h4', { class: 'sh-h' }, title), node] : null; }

  function domainDetails(d, dom, open) {
    var lv = dom.risk && dom.risk !== 'none' ? dom.risk : 'none';
    var det = h('details', { class: 'dd', 'data-d': d });
    if (open) det.setAttribute('open', '');
    det.appendChild(h('summary', null, icon(DOMAINS[d].icon), h('b', null, DOMAINS[d].name),
      dom.risk_level ? h('span', { class: 'chip imp-chip lv-' + lv }, 'المخاطر: ' + dom.risk_level) : null,
      icon('i-left', 'chev')));
    var lvl = dom.levels || {};
    var kd = (dom.key_developments || []).map(function (k) {
      var it = findItem(dom.refs && dom.refs[k.ref]);
      var inner = [h('b', null, k.title), k.significance ? h('span', null, k.significance) : null];
      return it ? h('button', { type: 'button', class: 'kd', onclick: function () { openItem(it, function () { openRadar(d); }); } }, inner)
                : h('div', { class: 'kd' }, inner);
    });
    det.appendChild(h('div', { class: 'dd-body' },
      dom.headline ? h('p', { class: 'dd-head' }, cites(dom.headline, d, dom)) : null,
      dom.summary ? h('p', { class: 'sh-text' }, cites(dom.summary, d, dom)) : null,
      dom.confidence ? h('p', { class: 'dd-conf' }, 'درجة الثقة: ' + dom.confidence) : null,
      section('على مستوى الإمارات', lvl.uae ? h('p', { class: 'sh-text' }, cites(lvl.uae, d, dom)) : null),
      section('على مستوى المنطقة', lvl.region ? h('p', { class: 'sh-text' }, cites(lvl.region, d, dom)) : null),
      section('على مستوى العالم', lvl.world ? h('p', { class: 'sh-text' }, cites(lvl.world, d, dom)) : null),
      section('أين تتقاطع المستويات', dom.comparison ? h('p', { class: 'sh-text' }, cites(dom.comparison, d, dom)) : null),
      section('أبرز التطورات', kd.length ? h('div', { class: 'kd-list' }, kd) : null),
      section('انعكاسات على الإمارات', list(dom.uae_implications, d, dom)),
      section('المخاطر', list(dom.risks, d, dom)),
      section('الفرص', list(dom.opportunities, d, dom)),
      section('أثر الأسواق', list(dom.market_impact, d, dom)),
      section('النظرة للأسبوعين المقبلين', dom.outlook ? h('p', { class: 'sh-text' }, cites(dom.outlook, d, dom)) : null),
      section('ما يُراقَب', list(dom.watch_list, d, dom))));
    return det;
  }

  function openRadar(focus) {
    var R = radarNow(), lead = R ? radarLead(R) : null;
    if (!R || !lead) { openBigPicture(); return; }
    var ex = R.executive || {}, figs = (R.figures || []).map(function (f) {
      var arrow = f.dir === 'up' ? '▲' : (f.dir === 'down' ? '▼' : '');
      return h('div', { class: 'fig ' + (f.dir || 'flat') }, h('small', null, f.label),
        h('b', { dir: 'auto' }, f.value),
        f.change ? h('i', null, (arrow ? arrow + ' ' : '') + f.change) : null);
    });
    var focusKey = DOMAIN_KEYS.indexOf(focus) >= 0 ? focus : null;
    var dets = DOMAIN_KEYS.filter(function (d) { return R.domains[d]; }).map(function (d) { return domainDetails(d, R.domains[d], d === focusKey); });
    openSheet(h('div', { class: 'an-sheet' },
      h('h3', { class: 'sh-title', id: 'sheetTitle' }, lead.title),
      h('div', { class: 'sh-meta' }, h('span', { class: 'chip chip-ed' }, EDITION), R.label_ar ? h('span', { class: 'chip' }, R.label_ar) : null),
      h('p', { class: 'sh-text' }, ex.overview || lead.summary),
      section('أولويات صانع القرار', list(ex.top_priorities)),
      section('ترابط التطورات', list(ex.cross_links)),
      section('خلال 48 ساعة', list(ex.next_48h)),
      section('ما الذي تغيّر منذ الإصدار السابق', list(R.changes_since_last)),
      section('أرقام اليوم', figs.length ? h('div', { class: 'fig-grid' }, figs) : null),
      h('h4', { class: 'sh-h' }, 'التحليل المتكامل'),
      dets,
      section('تسريبات وإشاعات (غير مؤكدة)', (R.leaks || []).length ? h('div', { class: 'lklist' }, R.leaks.map(function (lk) {
        var b = leakCard(lk, function () { openLeak(lk, function () { openRadar(focus); }); });
        b.classList.add('in-sheet');
        return b;
      })) : null)));
    if (focusKey) {
      var el = $('sheetBody').querySelector('details[data-d="' + focusKey + '"]');
      if (el && el.scrollIntoView) el.scrollIntoView({ block: 'start' });
    }
  }

  function openBigPicture() {
    var V = visible(), bp = bigPictureFor(V);
    if (!bp) return;
    if (bp.radar) { openRadar(); return; }
    var stats = domainStats(V), ai = state.ai && state.ai.analysis;
    openSheet(h('div', { class: 'an-sheet' },
      h('h3', { class: 'sh-title', id: 'sheetTitle' }, bp.title),
      h('div', { class: 'sh-meta' }, bp.ai ? aiBadge() : null),
      h('p', { class: 'sh-text' }, bp.summary),
      h('h4', { class: 'sh-h' }, 'التحليل المتكامل'),
      DOMAIN_KEYS.map(function (d) {
        var st = stats[d], lv = level(st.impact), txt = ai && ai[d] ? ai[d].text : localDomainText(d, st);
        return h('div', { class: 'ablock' },
          h('div', { class: 'ab-h' }, icon(DOMAINS[d].icon), DOMAINS[d].name,
            st.impact == null ? null : h('span', { class: 'chip imp-chip lv-' + lv }, pct(st.impact), ' ' + LEVEL_AR[lv])),
          h('p', null, txt));
      })));
  }

  /* ------------------------------------------------------- the 60-second stories */
  // Tapping the app name plays the edition's five main stories, 12 seconds each, like Instagram stories. Without a fresh edition
  // it plays the five most important live stories. The red dot on the ring stays until the current edition has been opened.
  var story = { open: false, slides: [], i: 0, t: 0, last: 0, paused: false, raf: 0, bg: 0, back: null };
  function storySlides() {
    var V = visible(), rd = radarNow();
    var ed = rd ? V.filter(function (i) { return i.radar; }) : [];
    var src = ed.length ? ed : V.filter(function (i) { return !(i.dup >= DUP_MAX); });
    return { list: src.slice(0, STORY_N), edition: !!ed.length };
  }
  function openStory() {
    var s = storySlides();
    if (!s.list.length) { toast(state.loaded ? 'لا توجد أخبار لعرضها الآن' : 'جاري تحميل الأخبار...'); return; }
    var rd = radarNow();
    story.slides = s.list;
    story.open = true;
    story.i = 0; story.t = 0; story.paused = false;
    story.back = document.activeElement;
    $('stLabel').textContent = s.edition && rd ? (rd.label_ar || EDITION) : 'أهم الأخبار الآن';
    $('stBars').replaceChildren.apply($('stBars'), story.slides.map(function () { return h('span', { class: 'st-bar' }, h('i')); }));
    if (s.edition && rd) { lsSet(LS.seen, rd.id); renderRing(); }
    $('story').hidden = false;
    document.documentElement.classList.add('story-open');
    try { if (!(history.state && history.state.story)) history.pushState({ story: 1 }, ''); } catch (e) { /* sandboxed */ }
    showSlide();
    setPaused(false);
    $('stClose').focus();
    story.last = Date.now();
    cancelAnimationFrame(story.raf);
    story.raf = requestAnimationFrame(storyTick);
  }
  function closeStory(fromPop) {
    if (!story.open) return;
    story.open = false;
    cancelAnimationFrame(story.raf);
    $('story').hidden = true;
    document.documentElement.classList.remove('story-open');
    if (!fromPop) { try { if (history.state && history.state.story) history.back(); } catch (e) { /* sandboxed */ } }
    var b = story.back && story.back !== document.body && document.body.contains(story.back) ? story.back : $('storyLink');
    if (b && b.focus) b.focus();
  }
  function showSlide() {
    var it = story.slides[story.i], lv = level(it.uae_impact), bgs = STORY_BG[it.domain] || STORY_BG.political;
    var sameBefore = story.slides.slice(0, story.i).filter(function (x) { return x.domain === it.domain; }).length;
    $('story').className = 'story lv-' + lv;
    $('stBg').style.backgroundImage = bgs[sameBefore % bgs.length];
    $('stNum').textContent = String(story.i + 1);
    $('stDom').textContent = (DOMAINS[it.domain] ? DOMAINS[it.domain].name : '') + (SCOPES[it.scope] ? ' · ' + SCOPES[it.scope] : '');
    $('stTitle').textContent = it.title;
    $('stSum').textContent = it.summary || '';
    $('stMeter').style.width = Math.max(4, Math.min(100, Math.round(it.uae_impact))) + '%';
    $('stPct').textContent = Math.round(it.uae_impact) + '%';
    $('stLvl').textContent = LEVEL_AR[lv];
    $('stWhy').textContent = it.why || '';
    $('stWhyBox').hidden = !it.why;
    var s0 = it.sources && it.sources[0], a = $('stSrc'), href = s0 ? safeUrl(s0.url) : null;
    a.textContent = s0 ? s0.name : '';
    if (href) a.setAttribute('href', href); else a.removeAttribute('href');
    a.parentNode.hidden = !s0;
    $('stPrev').disabled = story.i === 0;
    $('stNext').lastChild.previousSibling.textContent = story.i === story.slides.length - 1 ? 'إنهاء' : 'التالي';
    paintBars();
  }
  function paintBars() {
    var bars = $('stBars').children, frac = Math.min(1, story.t / STORY_MS);
    for (var k = 0; k < bars.length; k++) bars[k].firstChild.style.width = (k < story.i ? 100 : (k === story.i ? frac * 100 : 0)) + '%';
    var left = Math.max(0, Math.ceil(((story.slides.length - story.i) * STORY_MS - story.t) / 1000));
    var el = $('stLeft');
    if (el.textContent !== String(left)) el.textContent = String(left);
  }
  function storyTick() {
    if (!story.open) return;
    var now = Date.now(), dt = Math.min(1000, Math.max(0, now - story.last));
    story.last = now;
    if (!story.paused) {
      story.t += dt;
      if (story.t >= STORY_MS) { if (!go(1)) return; }
      else paintBars();
    }
    story.raf = requestAnimationFrame(storyTick);
  }
  function go(step) {
    var n = story.i + step;
    if (n >= story.slides.length) { closeStory(); return false; }
    story.i = Math.max(0, n);
    story.t = 0;
    showSlide();
    return true;
  }
  function setPaused(p) {
    story.paused = p;
    var b = $('stPause');
    b.setAttribute('aria-label', p ? 'تشغيل' : 'إيقاف مؤقت');
    b.setAttribute('aria-pressed', p ? 'true' : 'false');
    b.firstChild.firstChild.setAttribute('href', p ? '#i-play' : '#i-pause');
  }

  /* ------------------------------------------------------------------ theme */
  function applyTheme(t, save) {
    var night = t === 'night';
    document.documentElement.setAttribute('data-theme', night ? 'night' : 'day');
    var m = document.querySelector('meta[name="theme-color"]');
    if (m) m.setAttribute('content', night ? '#05070D' : '#F2F5FA');
    var b = $('themeBtn');
    b.setAttribute('aria-label', night ? 'التبديل إلى الوضع النهاري' : 'التبديل إلى الوضع الليلي');
    b.setAttribute('aria-pressed', night ? 'true' : 'false');
    b.firstChild.firstChild.setAttribute('href', night ? '#i-sun' : '#i-moon');
    if (save) lsSet(LS.theme, night ? 'night' : 'day');
  }
  function toggleTheme() {
    applyTheme(document.documentElement.getAttribute('data-theme') === 'night' ? 'day' : 'night', true);
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
    renderControls();
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
    // no short cut-off: the server itself waits for every source up to the platform limit (~25s); this 35s is only a safety net so the button can never stay locked
    return fetchJSON('/api/news?hours=' + hours, null, 35000).then(function (data) {
      if (id !== state.reqId) return;
      if (!data || !Array.isArray(data.items)) throw new Error('bad payload');
      state.items = mergeKept(data.items, state.items, state.fetchedAt, hours);
      state.loaded = true;
      state.fetchedAt = data.stale ? (Date.parse(data.generated_at) || state.fetchedAt) : Date.now();
      state.radar = (data.radar && data.radar.domains) ? data.radar : null;
      if (state.radar) lsSet(LS.radar, state.radar); else lsDel(LS.radar);
      lsSet(LS.news(hours), { items: state.items.slice(0, KEEP_MAX), fetchedAt: state.fetchedAt });
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
  // One request per refresh: Arabic headlines for English stories + big picture / integrated analysis + a second
  // opinion on the impact of the top stories. Each part is optional: whatever fails simply keeps its local fallback.
  function runAI(id, hours) {
    var need = state.items.filter(function (i) { return !titleOf(i); }).slice(0, 30);
    var top = visible().slice(0, 25);       // edition stories are included as context; their impact is never re-scored
    var wantAn = top.length >= 3;
    var ids = top.map(function (i) { return i.id; }).sort();
    var cached = lsGet(LS.ai(hours));
    // the saved analysis is reused while it still covers most of the current top stories (items translated by the
    // previous call join the list afterwards, so an exact match would make every refresh pay for a new request)
    var covered = 0;
    if (cached && cached.ids) { var had = {}; cached.ids.forEach(function (k) { had[k] = 1; }); ids.forEach(function (k) { if (had[k]) covered++; }); }
    if (wantAn && cached && cached.ids && covered >= 0.6 * ids.length && Date.now() - cached.at < 30 * 60 * 1000) {
      state.ai = cached.data;
      if (id === state.reqId) render();
      wantAn = false;
    }
    if (!need.length && !wantAn) return;
    post('/api/enrich', {
      hours: hours,
      translate: need.map(function (i) { return { id: i.id, title: (i.sources[0] || {}).title || '' }; }),
      items: wantAn ? top.map(function (i) { return { id: i.id, title: i.title, scope: i.scope, domain: i.domain, uae_impact: i.impact0, radar: !!i.radar }; }) : []
    }, 29000).then(function (res) {
      if (!res || !res.ok) throw new Error('no ai');
      var keys = Object.keys(res.translations || {});
      if (keys.length) {
        keys.forEach(function (k) { state.tr[k] = res.translations[k]; });
        var all = Object.keys(state.tr);
        if (all.length > 400) all.slice(0, all.length - 400).forEach(function (k) { delete state.tr[k]; });
        lsSet(LS.tr, state.tr);
      }
      if (wantAn) {
        if (!res.big_picture) throw new Error('no analysis');
        state.ai = res;
        lsSet(LS.ai(hours), { ids: ids, at: Date.now(), data: res });
      }
    }).catch(function () {
      if (wantAn) state.ai = (cached && Date.now() - cached.at < 3 * 3600 * 1000) ? cached.data : null;
    }).finally(function () {
      if (id === state.reqId) render();
    });
  }

  /* ----------------------------------------------------------------- events */
  function setPeriod(p) {
    if (!PERIODS[p]) return;
    var hrs = PERIODS[p];
    state.period = p;
    state.expanded = false;
    lsSet(LS.period, p);
    if (hrs === state.hours) { render(); return; }
    state.hours = hrs;
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

  function goSection(key) {
    if (key === 'edition') { if (radarNow()) openRadar(); else openBigPicture(); return; }
    if (key === 'top') { window.scrollTo({ top: 0, behavior: scrollBehavior() }); return; }
    var el = $(key);
    if (el) el.scrollIntoView({ behavior: scrollBehavior(), block: 'start' });
  }
  var navTimer = 0;
  function syncNav() {
    cancelAnimationFrame(navTimer);
    navTimer = requestAnimationFrame(function () {
      var line = window.innerHeight * 0.4, cur = 'top';
      ['live', 'leaks'].forEach(function (k) { var el = $(k); if (el && el.getBoundingClientRect().top <= line) cur = k; });
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) cur = 'leaks';
      Array.prototype.forEach.call($('nav').children, function (b) {
        var on = b.dataset.go === cur;
        b.classList.toggle('on', on);
        if (on) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
      });
    });
  }

  function bind() {
    $('refreshBtn').addEventListener('click', function () { if (!state.busy) refresh(); });
    $('shareBtn').addEventListener('click', share);
    $('themeBtn').addEventListener('click', toggleTheme);
    $('heroMore').addEventListener('click', openBigPicture);
    $('storyLink').addEventListener('click', function (e) { e.preventDefault(); openStory(); });
    $('periodTabs').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-p]');
      if (b && b.dataset.p !== state.period) setPeriod(b.dataset.p);
    });
    $('scopeChips').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-s]');
      if (!b || b.dataset.s === state.scope) return;
      state.scope = b.dataset.s;
      state.expanded = false;
      render();
    });
    $('domainTabs').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-d]');
      if (!b || b.dataset.d === state.domain) return;
      state.domain = b.dataset.d;
      lsSet(LS.domain, state.domain);
      render();
    });
    $('liveMore').addEventListener('click', function () {
      state.expanded = !state.expanded;
      render();
      if (!state.expanded) $('live').scrollIntoView({ behavior: scrollBehavior(), block: 'start' });
    });
    $('nav').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-go]');
      if (b) goSection(b.dataset.go);
    });
    window.addEventListener('scroll', syncNav, { passive: true });
    window.addEventListener('resize', function () { fit(); syncNav(); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);

    // stories
    $('stClose').addEventListener('click', function () { closeStory(); });
    $('stPause').addEventListener('click', function () { setPaused(!story.paused); });
    $('stNext').addEventListener('click', function () { go(1); });
    $('stPrev').addEventListener('click', function () { go(-1); });
    $('stZoneNext').addEventListener('click', function () { go(1); });
    $('stZonePrev').addEventListener('click', function () { go(-1); });
    document.addEventListener('keydown', function (e) {
      if (!story.open) return;
      if (e.key === 'Escape') { e.preventDefault(); closeStory(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); go(1); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); go(-1); }
      else if (e.key === ' ' && e.target === document.body) { e.preventDefault(); setPaused(!story.paused); }
    });
    window.addEventListener('popstate', function () { if (story.open) closeStory(true); });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) {
        lsSet(LS.visit, Date.now());
        if (story.open) setPaused(true);
      }
    });
    window.addEventListener('pagehide', function () { lsSet(LS.visit, Date.now()); });
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
      navigator.serviceWorker.register('/sw.js?v=2.0.0', { updateViaCache: 'none' }).then(function (reg) {
        reg.update().catch(function () {});
      }).catch(function () {});
    });
  }

  /* -------------------------------------------------------------------- init */
  function init() {
    var p = lsGet(LS.period), d = lsGet(LS.domain);
    if (PERIODS[p]) state.period = p;
    if (DOMAINS[d]) state.domain = d;
    state.hours = PERIODS[state.period];
    state.prevVisit = lsGet(LS.visit);
    if (typeof state.prevVisit !== 'number') { state.prevVisit = null; lsSet(LS.visit, Date.now()); }
    applyTheme(lsGet(LS.theme) === 'night' ? 'night' : 'day', false);
    state.tr = lsGet(LS.tr) || {};
    state.radar = lsGet(LS.radar);
    loadCached(state.hours);
    state.ai = freshAI(state.hours);
    bind();
    tickClock();
    setInterval(tickClock, 1000);
    render();
    fit();
    syncNav();
    refresh();
    registerSW();
  }
  init();
})();
