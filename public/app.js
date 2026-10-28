/* مرصد الإمارات الذكي — v1.2.1 */
(function () {
  'use strict';

  var HOURS = [6, 12, 24, 48, 72];
  var DUP_MAX = 12;      // a story that repeats a better-ranked one by this much is hidden from the «مؤثرة» tab
  var KEEP_MIN = 34;     // an earlier headline that the new answer no longer lists is kept while it is still inside the window if its impact is at least this (mid / high)
  var KEEP_MAX = 100;    // most headlines stored per window
  var IMPACT_MIN = 55;   // «مؤثرة» tab: stories whose potential impact on the UAE is at least this, wherever they happen
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
  var RADAR_MAX_AGE = 36 * 3600 * 1000;   // an edition older than this is ignored (the server applies the same limit)
  var LS = {
    radar: 'mirsad.radar',
    hours: 'mirsad.hours',
    tr: 'mirsad.tr',
    theme: 'mirsad.theme',
    news: function (h) { return 'mirsad.news.' + h; },
    ai: function (h) { return 'mirsad.ai.' + h; }
  };

  var state = {
    hours: 24, domain: 'all', scope: 'all',
    items: [], loaded: false, fetchedAt: null,
    tr: {}, ai: null, radar: null, busy: false, reqId: 0
  };

  var $ = function (id) { return document.getElementById(id); };

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

  /* ------------------------------------------------- keep what the last update found */
  // Each update asks for the whole window again, but an answer is never complete (a source can be slow or cut, a query returns a
  // limited number of rows). A headline that was on the page and is still inside the window is therefore kept when the new
  // answer does not list it, unless the new answer already has the same story under another headline. Importance is re-aged
  // (recency counts 20 points over the window, as on the server) so old finds do not outrank fresh ones.
  function normAr(t) {
    return String(t || '').replace(/[\u064B-\u0652\u0640]/g, '').replace(/[\u0623\u0625\u0622]/g, '\u0627').replace(/\u0649/g, '\u064A').replace(/\u0629/g, '\u0647').toLowerCase();
  }
  function tokenSet(t) {
    var out = {}, m = normAr(t).match(/[\u0600-\u06FFa-z0-9]+/g) || [];
    m.forEach(function (w) {
      if (w.indexOf('\u0627\u0644') === 0 && w.length > 4) w = w.slice(2);
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

  /* ------------------------------------------------------------ radar edition */
  // «رادار الأخبار»: while an edition is fresh (and inside the selected window) its executive overview and per-domain analysis feed the big picture and the
  // integrated analysis (same places, same cards); its stories arrive as ordinary news items flagged radar:true.
  // The edition feeds the big picture, the analysis and the «التحليل الكامل» sheet only while it lies inside the selected news
  // window (the same rule that decides whether its stories are listed). A 6-hour view never shows a morning edition's overview.
  function radarNow() {
    var r = state.radar;
    if (!r || !r.domains) return null;
    var age = Date.now() - Date.parse(r.created_at);
    return (age < RADAR_MAX_AGE && age <= state.hours * 3600 * 1000) ? r : null;
  }
  function stripRefs(t) { return String(t || '').replace(/\s*\[\d+(?:\s*[,،]\s*\d+)*\]/g, '').replace(/\s+([،.؛:)])/g, '$1').trim(); }
  function radarTime(r) { var m = /·\s*([\d:]+)\s*$/.exec(r.label_ar || ''); return m ? m[1] : ''; }
  // title = the Radar's own headline when it has one, else the first clause of the overview; the summary then continues
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

  /* --------------------------------------------------------------- analysis */
  function localDomainText(d, stat) {
    if (!stat.top) return 'لا توجد أخبار بارزة في هذا المجال خلال آخر ' + hoursLabel(state.hours) + '.';
    var lv = level(stat.impact);
    var tail = { high: 'التأثير المحتمل على الإمارات مرتفع ويستدعي المتابعة الدقيقة.', mid: 'التأثير المحتمل على الإمارات متوسط ويستحق المتابعة.', low: 'التأثير المحتمل على الإمارات محدود حاليًا.', none: '' }[lv];
    return 'عدد الأخبار المرصودة: ' + stat.list.length + '. الأعلى تأثيرًا: «' + stat.top.title + '». ' + tail;
  }
  // Order of preference: Gemini's analysis of the current list («تحليل ذكي AI», badge only when the text really is Gemini's),
  // then the Radar edition's own analysis (badge «رادار الأخبار»), then the local text. While an edition is fresh every
  // analysis block opens the Radar's full analysis of that domain.
  function analysisFor(V) {
    var stats = domainStats(V), rd = radarNow();
    var ai = state.ai && state.ai.analysis;
    if (ai && DOMAIN_KEYS.every(function (d) { return ai[d]; })) {
      return { rows: DOMAIN_KEYS.map(function (d) {
        return { d: d, impact: stats[d].impact, text: ai[d].text, radar: !!(rd && rd.domains[d]), deep: true };
      }), ai: true, stats: stats };
    }
    if (rd) {
      var rrows = DOMAIN_KEYS.map(function (d) {
        var dd = rd.domains[d];
        return { d: d, impact: stats[d].impact, radar: !!dd, text: dd ? stripRefs(dd.headline) : localDomainText(d, stats[d]) };
      });
      return { rows: rrows, ai: false, radar: true, stats: stats };
    }
    var rows = DOMAIN_KEYS.map(function (d) { return { d: d, impact: stats[d].impact, text: localDomainText(d, stats[d]) }; });
    return { rows: rows, ai: false, stats: stats };
  }
  function bigPictureFor(V) {
    var rd = radarNow();
    if (state.ai && state.ai.big_picture) return { title: state.ai.big_picture.title, summary: state.ai.big_picture.summary, ai: true };
    if (rd && rd.executive && rd.executive.overview) { var lead = radarLead(rd); return { title: lead.title, summary: lead.summary, ai: false, radar: true }; }
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
  function radarBadge() { return h('span', { class: 'ai-badge badge-radar' }, icon('i-spark'), 'رادار الأخبار'); }

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

  function renderBpSrc() {
    var rd = radarNow(), tm = rd ? radarTime(rd) : '';
    $('bpSrc').textContent = rd ? '· نشرة رادار الأخبار' + (tm ? ' ' + tm : '') : '';
  }

  function renderHero(V) {
    var t = $('bpTitle'), s = $('bpSummary'), slot = $('bpAi');
    slot.replaceChildren();
    if (!state.loaded && !V.length) {
      renderBpSrc();
      t.replaceChildren(skel(20, '85%'));
      s.replaceChildren(skel(14, '100%'), skel(14, '92%'));
      s.style.display = 'block';
      return;
    }
    s.style.display = '';
    renderBpSrc();
    var bp = bigPictureFor(V);
    if (!bp) {
      t.textContent = 'لا توجد أخبار لعرضها حاليًا';
      s.textContent = 'جرّب تغيير مدة الأخبار أو اضغط «تحديث».';
      return;
    }
    t.textContent = bp.title;
    s.textContent = bp.summary;
    if (bp.radar) slot.appendChild(radarBadge());
    else if (bp.ai) slot.appendChild(aiBadge());
  }

  function domainCard(d, st) {
    var lv = level(st.impact), has = st.impact != null;
    var gauge = h('div', { class: 'gauge' }, h('i'));
    gauge.firstChild.style.width = (has ? Math.max(0, Math.min(100, Math.round(st.impact))) : 0) + '%';
    return h('div', { class: 'dom lv-' + lv },
      h('div', { class: 'dom-top' }, icon(DOMAINS[d].icon), h('span', { class: 'dom-name' }, DOMAINS[d].name)),
      h('div', { class: 'dom-cap' }, 'التأثير: '),
      h('div', { class: 'dom-val' }, has ? h('span', { dir: 'ltr', style: 'unicode-bidi:isolate' }, h('b', null, Math.round(st.impact)), h('i', null, '%')) : h('b', null, '—')),
      gauge,
      h('div', { class: 'dom-lvl' }, LEVEL_AR[lv])
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
  function row(it, withScope) {
    var lv = level(it.uae_impact);
    var src = it.sources && it.sources[0] ? it.sources[0].name : '';
    var when = it.radar && it.when ? it.when : ago(it.published);
    var scopeName = withScope && SCOPES[it.scope] ? SCOPES[it.scope] : '';
    // «مؤثرة» only: the story's scope is a small pill in front of «source • time» (the bullet after it stays in the text, hidden)
    var meta = h('span', { class: 'row-meta' },
      scopeName ? h('i', { class: 'sc' }, scopeName) : null,
      scopeName ? h('span', { class: 'sep' }, ' • ') : null,
      src + ' • ' + when);
    return h('button', { class: 'row', type: 'button', 'data-scope': it.scope, 'data-domain': it.domain, onclick: function () { openItem(it); } },
      thumb(it),
      h('span', { class: 'row-main' },
        h('span', { class: 'row-title' }, it.title),
        meta
      ),
      h('span', { class: 'imp lv-' + lv }, h('b', null, pct(it.uae_impact)), h('small', null, LEVEL_AR[lv]))
    );
  }
  function fillList(el, items, emptyMsg, withScope) {
    if (!state.loaded && !items.length) { el.replaceChildren(skel(72), skel(72), skel(72)); return; }
    if (!items.length) { el.replaceChildren(h('div', { class: 'empty' }, emptyMsg)); return; }
    el.replaceChildren.apply(el, items.map(function (it) { return row(it, withScope); }));
  }
  var latestIds = {};   // stories already shown in «آخر الأخبار الهامة»: not repeated in the list below it
  function renderLatest(V) {
    var base = byDomain(V).slice(0, 12).sort(function (a, b) { return Date.parse(b.published) - Date.parse(a.published); }).slice(0, 3);
    latestIds = {};
    base.forEach(function (i) { latestIds[i.id] = 1; });
    fillList($('latestList'), base, state.loaded ? 'لا توجد أخبار هامة ضمن هذه الفترة.' : '');
  }
  function renderTop(V) {
    var list = byDomain(V), msg = 'لا توجد أخبار ضمن هذا التصنيف حاليًا.', impactTab = state.scope === 'impact';
    if (impactTab) {
      // near-copies of a better-ranked story (dup >= DUP_MAX) are left out of this tab so each line is a different event
      list = list.filter(function (i) { return i.uae_impact >= IMPACT_MIN && !(i.dup >= DUP_MAX); })
                 .sort(function (x, y) { return (y.uae_impact - x.uae_impact) || (y.importance - x.importance); });
      msg = 'لا توجد أخبار عالية التأثير على الإمارات حاليًا.';
    } else if (state.scope !== 'all') {
      list = list.filter(function (i) { return i.scope === state.scope; });
    }
    var rest = list.filter(function (i) { return !latestIds[i.id]; });
    if (rest.length) list = rest;      // never leave a tab empty just to avoid showing a story twice
    fillList($('topList'), list.slice(0, 10), state.loaded ? msg : '', impactTab);
  }
  function renderAnalysis(V) {
    var an = analysisFor(V), slot = $('anAi');
    slot.replaceChildren();
    if (an.radar) slot.appendChild(radarBadge());
    else if (an.ai) slot.appendChild(aiBadge());
    if (!state.loaded && !V.length) { $('anList').replaceChildren(skel(70), skel(70), skel(70)); return; }
    $('anList').replaceChildren.apply($('anList'), an.rows.map(analysisBlock));
  }
  function analysisBlock(r) {
    var lv = level(r.impact);
    var open = r.radar ? function () { openRadar(r.d); } : null;
    return h('div', { class: 'an' + (open ? ' tap' : ''), role: open ? 'button' : null, tabindex: open ? '0' : null,
        onclick: open, onkeydown: open ? function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } } : null },
      h('div', { class: 'an-head' }, h('span', { class: 'ach' }, icon(DOMAINS[r.d].icon)), h('b', null, DOMAINS[r.d].name),
        r.impact == null ? null : h('span', { class: 'imp lv-' + lv }, h('b', null, pct(r.impact)), h('small', null, LEVEL_AR[lv]))),
      h('p', null, r.text),
      open ? h('span', { class: 'more' }, r.deep ? 'تحليل الرادار الكامل' : 'التحليل الكامل', icon('i-left')) : null);
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

  function openItem(it, back) {
    var lv = level(it.uae_impact);
    var srcs = (it.sources || []).map(function (s) {
      var href = safeUrl(s.url);
      var tag = KIND_AR[s.kind] ? h('em', { class: 'tag k-' + s.kind }, KIND_AR[s.kind]) : null;
      var inner = [h('b', null, icon('i-out'), s.name || 'المصدر', tag)];
      if (s.title && s.title !== it.title) inner.push(h('span', { lang: s.lang === 'ar' ? 'ar' : 'en' }, s.title));
      return href ? h('a', { class: 'src', href: href, target: '_blank', rel: 'noopener noreferrer' }, inner)
                  : h('div', { class: 'src' }, inner);
    });
    openSheet(h('div', null,
      back ? backButton(back) : null,
      h('h3', { class: 'sh-title', id: 'sheetTitle' }, it.title),
      h('div', { class: 'sh-meta' },
        it.radar ? h('span', { class: 'chip chip-radar' }, 'رادار الأخبار') : null,
        h('span', { class: 'chip' }, DOMAINS[it.domain].name),
        h('span', { class: 'chip' }, SCOPES[it.scope] || ''),
        h('span', { class: 'chip' }, it.radar && it.when ? it.when : ago(it.published)),
        it.updates >= 3 ? h('span', { class: 'chip' }, 'قصة متطورة • ' + plural(it.updates, 'تحديث', 'تحديثان', 'تحديثات', 'تحديثًا')) : null,
        h('span', { class: 'chip imp-chip lv-' + lv }, 'التأثير: ', pct(it.uae_impact))),
      it.summary ? h('p', { class: 'sh-text' }, it.summary) : null,
      (it.why && it.uae_impact > 33) ? h('p', { class: 'sh-why lv-' + lv }, h('b', null, 'لماذا يهم الإمارات: '), it.why) : null,
      h('h4', { class: 'sh-h' }, 'المصادر الأصلية'),
      srcs));
  }

  function backButton(fn) {
    return h('button', { type: 'button', class: 'sh-back', onclick: fn }, icon('i-left'), 'العودة إلى التحليل');
  }
  // «[3]» inside the Radar's text becomes a button that opens story 3 of that domain
  function cites(text, d, dom) {
    var out = [], re = /\[(\d+(?:\s*[,،]\s*\d+)*)\]/g, last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) out.push(text.slice(last, m.index));
      m[1].split(/\s*[,،]\s*/).forEach(function (n) { out.push(citeBtn(d, dom, n)); });
      last = m.index + m[0].length;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
  }
  function citeBtn(d, dom, n) {
    var id = dom && dom.refs && dom.refs[n], it = null;
    if (id) { var V = visible(); for (var i = 0; i < V.length; i++) if (V[i].id === id) { it = V[i]; break; } }
    if (!it) return h('span', { class: 'cite off' }, n);
    return h('button', { type: 'button', class: 'cite', 'aria-label': 'الخبر ' + n, onclick: function () { openItem(it, function () { openRadar(d); }); } }, n);
  }
  function list(arr, d, dom) {
    if (!arr || !arr.length) return null;
    return h('ul', { class: 'rd-list' }, arr.map(function (t) { return h('li', null, d ? cites(t, d, dom) : t); }));
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
      var id = dom.refs && dom.refs[k.ref], V = id ? visible() : [], it = null;
      for (var i = 0; i < V.length; i++) if (V[i].id === id) { it = V[i]; break; }
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
    var R = radarNow(), V = visible(), lead = R ? radarLead(R) : null;
    if (!R || !lead) return;
    var ex = R.executive || {}, figs = (R.figures || []).map(function (f) {
      var arrow = f.dir === 'up' ? '▲' : (f.dir === 'down' ? '▼' : '');
      return h('div', { class: 'fig ' + (f.dir || 'flat') }, h('small', null, f.label),
        h('b', { dir: 'ltr', style: 'unicode-bidi:isolate' }, f.value),
        f.change ? h('i', null, (arrow ? arrow + ' ' : '') + f.change) : null);
    });
    var focusKey = DOMAIN_KEYS.indexOf(focus) >= 0 ? focus : null;
    var dets = DOMAIN_KEYS.filter(function (d) { return R.domains[d]; }).map(function (d) { return domainDetails(d, R.domains[d], d === focusKey); });
    openSheet(h('div', { class: 'an-sheet' },
      h('h3', { class: 'sh-title', id: 'sheetTitle' }, lead.title),
      h('div', { class: 'sh-meta' }, radarBadge(), R.label_ar ? h('span', { class: 'chip' }, R.label_ar) : null),
      h('p', { class: 'sh-text' }, ex.overview || lead.summary),
      section('أولويات صانع القرار', list(ex.top_priorities)),
      section('ترابط التطورات', list(ex.cross_links)),
      section('خلال 48 ساعة', list(ex.next_48h)),
      section('ما الذي تغيّر منذ الإصدار السابق', list(R.changes_since_last)),
      section('أرقام اليوم', figs.length ? h('div', { class: 'fig-grid' }, figs) : null),
      h('h4', { class: 'sh-h' }, 'التحليل المتكامل'),
      dets));
    if (focusKey) {
      var el = $('sheetBody').querySelector('details[data-d="' + focusKey + '"]');
      if (el && el.scrollIntoView) el.scrollIntoView({ block: 'start' });
    }
  }

  function openBigPicture() {
    var V = visible(), bp = bigPictureFor(V);
    if (!bp) return;
    if (radarNow()) { openRadar(); return; }      // the edition is the full analysis (also when the text above is Gemini's)
    var an = analysisFor(V);
    openSheet(h('div', { class: 'an-sheet' },
      h('h3', { class: 'sh-title', id: 'sheetTitle' }, bp.title),
      h('div', { class: 'sh-meta' }, bp.ai ? aiBadge() : null),
      h('p', { class: 'sh-text' }, bp.summary),
      h('h4', { class: 'sh-h' }, 'التحليل المتكامل'),
      an.rows.map(analysisBlock)));
  }

  /* ------------------------------------------------------------------ theme */
  // نهار / ليل: only a data-theme attribute on <html> (the colours live in style.css); the choice is remembered on this device
  function applyTheme(t, save) {
    var night = t === 'night';
    document.documentElement.setAttribute('data-theme', night ? 'night' : 'day');
    var m = document.querySelector('meta[name="theme-color"]');
    if (m) m.setAttribute('content', night ? '#4a38c0' : '#dff2ff');
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
    var top = visible().slice(0, 25);       // Radar stories are included as context; their impact is never re-scored
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
    $('themeBtn').addEventListener('click', toggleTheme);
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
      navigator.serviceWorker.register('/sw.js?v=1.2.1', { updateViaCache: 'none' }).then(function (reg) {
        reg.update().catch(function () {});
      }).catch(function () {});
    });
  }

  /* -------------------------------------------------------------------- init */
  function init() {
    var savedHours = lsGet(LS.hours);
    if (HOURS.indexOf(savedHours) >= 0) state.hours = savedHours;
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
    refresh();
    registerSW();
  }
  init();
})();
