/*!
 * IIOT-PRD 容器应用层
 * 三栏：目录（覆盖层）· 原型画布（1:1，永不被挤压）· PRD（覆盖层）
 */
(function () {
  var Vue = window.Vue || window.MiniVue;
  var h = Vue.h;
  var reactive = Vue.reactive;
  var computed = Vue.computed;
  var nextTick = Vue.nextTick || function (fn) { setTimeout(fn, 0); };

  // 数据必须是响应式的：行级命令（措施开始/完成、逐条排查）改的是某一行，
  // 如果 DATA 是普通对象，Vue 追不到，就会出现"提交成功了但列表还是旧状态"。
  var DATA = reactive ? reactive(window.__PROTO__) : window.__PROTO__;
  // 存储按「产品 + 模块前缀」分键，**不带版本号**：
  // 版本一升、原型一重建，上一轮的标注就整批消失，等于每轮评审都不留痕。
  // 这是"改完之后之前的标注没了"的根因，不是浏览器清缓存。
  var MOD_SIG = ((DATA.pages || [])[0] || {}).id
    ? String(DATA.pages[0].id).split('-').slice(0, 2).join('-') : 'misc';
  var KEY = 'iiot:' + DATA.meta.product + ':' + MOD_SIG;
  // 老键里带版本号（iiot:产品:1.0.0），而每升一版就换一个桶。
  // 只认「当前版本号」那一把是不够的：升到 1.1.0 之后它恰好是空桶，
  // 真正有标注的是 1.0.0 那一把。所以按产品前缀扫全库，一次性全搬过来。
  var KEY_PREFIX = 'iiot:' + DATA.meta.product + ':';

  function bucketKeys() {
    var out = [];
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (!k || k.indexOf(KEY_PREFIX) !== 0) continue;
        if (k === KEY) out.unshift(k); else out.push(k); // 现用键优先，旧的补缺
      }
    } catch (e) { /* 隐私模式下读不到就当空 */ }
    return out;
  }

  var saved = {};
  try {
    var acc = { annotations: [], navOpen: {}, prdEdits: {} };
    var seenId = {};
    bucketKeys().forEach(function (k) {
      var b = {};
      try { b = JSON.parse(localStorage.getItem(k) || '{}') || {}; } catch (e) { return; }
      // 同一条标注可能在多个桶里，按 id 去重，先读到的（现用键）说了算
      (b.annotations || []).forEach(function (a) {
        if (a && a.id && !seenId[a.id]) { seenId[a.id] = 1; acc.annotations.push(a); }
      });
      ['navOpen', 'prdEdits', 'tocOpen'].forEach(function (f) {
        for (var kk in (b[f] || {})) if (acc[f][kk] === undefined) acc[f][kk] = b[f][kk];
      });
      ['pageId', 'entityStatus', 'currentUser'].forEach(function (f) {
        if (acc[f] === undefined && b[f] !== undefined) acc[f] = b[f];
      });
    });
    saved = acc;
  } catch (e) { saved = {}; }

  var capsById = {};
  (DATA.capabilities || []).forEach(function (c) { capsById[c.id] = c; });
  var smByEntity = {};
  (DATA.stateMachines || []).forEach(function (s) { smByEntity[s.entity] = s; });

  // 角色与状态在界面上一律显示中文名；内部 id 只活在契约里
  var actorNameMap = {};
  (DATA.actors || []).forEach(function (a) { actorNameMap[a.id] = a.name || a.id; });
  var stateNameMap = {};
  (DATA.stateMachines || []).forEach(function (sm) {
    (sm.states || []).forEach(function (st) { stateNameMap[st.key] = st.label || st.key; });
  });
  function actorName(id) { return actorNameMap[id] || id; }
  function stateNames(list) {
    return (list || []).map(function (k) { return stateNameMap[k] || k; }).join('、');
  }

  // 重建原型后 DATA.annotations 是新一份，本地存档是上一轮的意见。
  // 按 id 合并：本地有的一律保留（含已解决状态与解决方法），新契约里多出来的追加进来；
  // 若契约里的版本已经被处理过（resolved + resolution）而本地还是 open，以契约为准。
  function mergeAnnotations(builtin, local) {
    var out = [], seen = {};
    (builtin || []).forEach(function (a) {
      if (a && a.id && !seen[a.id]) { out.push(a); seen[a.id] = 1; }
    });
    (local || []).forEach(function (a) {
      if (!a || !a.id) return;
      var i = -1;
      out.forEach(function (x, k) { if (x.id === a.id) i = k; });
      if (i < 0) { out.push(a); seen[a.id] = 1; return; }
      var b = out[i];
      var builtinDone = b.status && b.status !== 'open' && b.resolution;
      var localDone = a.status && a.status !== 'open';
      out[i] = (builtinDone && !localDone) ? b : a;
    });
    return out;
  }

  var hashPage = (location.hash.match(/page=([A-Za-z0-9_-]+)/) || [])[1];
  var hashStatus = (location.hash.match(/status=([A-Za-z0-9_-]+)/) || [])[1];
  // 本页组件树里实际渲染的命令（工具栏 + 行内），按出现顺序去重。
  // 不读 contract.owns：owns 只回答"这条命令归哪一页负责"，过滤视图的 owns 可能是空的，
  // 按它推默认态就会落到 initial，整页按钮全灰。渲染了什么，才是这一页能做什么。
  function renderedCaps(pg) {
    var out = [], seen = {};
    (function walk(n) {
      if (!n || typeof n !== 'object') return;
      var props = (n.props && typeof n.props === 'object') ? n.props : {};
      var refs = [];
      (props.actions || []).forEach(function (a) { if (a && a.capability) refs.push(a.capability); });
      var cols = Array.isArray(props.columns) ? props.columns : [];
      cols.forEach(function (col) {
        if (col && col.actions) {
          (col.actions || []).forEach(function (a) { if (a && a.capability) refs.push(a.capability); });
        }
      });
      refs.forEach(function (cid) { if (!seen[cid]) { seen[cid] = 1; out.push(cid); } });
      (n.children || []).forEach(walk);
    })(pg && pg.componentTree);
    return out;
  }
  // 打开页面时落在「这一页有动作可做」的状态上，而不是状态机的 initial：
  // 否则评审第一眼看到的是一屏灰按钮，还得先去顶栏找状态切换。
  // 判定顺序 = 本页渲染的命令顺序 × 每个命令的 from 顺序，第一个命中状态机 states 的即为默认态。
  function defaultStatus(pg) {
    var sm = pg && smByEntity[pg.entity];
    if (!sm) return 'new';
    var keys = (sm.states || []).map(function (s) { return s.key; });
    var caps = renderedCaps(pg);
    for (var i = 0; i < caps.length; i++) {
      var cap = capsById[caps[i]];
      var from = (cap && cap.from) || [];
      for (var j = 0; j < from.length; j++) {
        if (keys.indexOf(from[j]) >= 0) return from[j];
      }
    }
    return sm.initial || keys[0] || 'new';
  }
  var initialPageId = hashPage || saved.pageId || DATA.meta.currentPageId || DATA.pages[0].id;
  var initialPage = DATA.pages.filter(function (x) { return x.id === initialPageId; })[0] || DATA.pages[0];
  // 评审经常要"直接看空态/异常态"：允许用 #page=x&state=empty 直达，省得每次点顶栏
  var hashState = (location.hash.match(/state=([A-Za-z0-9_-]+)/) || [])[1];
  var store = reactive({
    pageId: initialPageId,
    pageState: hashState || 'default',
    entityStatus: hashStatus || saved.entityStatus || defaultStatus(initialPage),
    // 当前操作人（角色 id）。空串 = 不限制，所有角色都能看见全部按钮。
    // 默认不限制是刻意的：原型是给一群人评审的，一进来就按某个岗位过滤，
    // 别人会以为"这个按钮没做"。要看四眼校验，顶栏切到具体角色即可。
    currentUser: saved.currentUser || '',
    filters: {},
    pdaQty: 0,
    selectedRow: null,
    showToc: /toc=1/.test(location.hash),
    showPrd: /prd=1/.test(location.hash),
    prdTab: 'page',
    prdWidth: 500,
    annotMode: false,
    annotScope: 'page',
    audit: false,
    showExport: false,
    // 目录树的开合状态与搜索词：功能一多，平铺菜单就靠记忆找了
    navOpen: saved.navOpen || {},
    navQuery: '',
    // 页面目录的开合状态，按 模块id/分组key 记
    tocOpen: saved.tocOpen || {},
    annotations: mergeAnnotations(DATA.annotations || [], saved.annotations || []),
    prdEdits: saved.prdEdits || {},
    pins: [],
    missingPins: [],
    popover: null,
    layer: null,
    toastMsg: ''
  });

  var page = computed(function () {
    return DATA.pages.filter(function (p) { return p.id === store.pageId; })[0] || DATA.pages[0];
  });
  var moduleOf = computed(function () {
    return DATA.modules.filter(function (m) { return m.id === page.value.moduleId; })[0] || {};
  });

  function persist() {
    try {
      localStorage.setItem(KEY, JSON.stringify({
        pageId: store.pageId,
        entityStatus: store.entityStatus,
        currentUser: store.currentUser,
        annotations: store.annotations,
        navOpen: store.navOpen,
        tocOpen: store.tocOpen,
        prdEdits: store.prdEdits
      }));
    } catch (e) { /* 隐私模式下静默失败 */ }
  }

  var toastTimer = null;
  function toast(msg) {
    store.toastMsg = msg;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { store.toastMsg = ''; }, 2200);
  }

  /* ---------------- 命令承载层（dialog / drawer） ----------------
   * 推进型动作不写在页面里，写在契约的 capabilities[].ui 上：
   * 入口节点 + 承载形式 + 字段清单。这里只负责按契约把层打开、校验、提交、关闭。
   */
  // 弹层字段属于哪一页的字典：认 cap.owns，不按节点 id 反查（n-table 多页复用）
  function ownsPageOf(capId) {
    var hit = (DATA.pages || []).filter(function (p) {
      return ((p.contract || {}).owns || []).indexOf(capId) >= 0;
    })[0];
    return hit ? hit.id : store.pageId;
  }

  /* ---------------- 字段字典（面板合成，不写进 prd.sections） ----------------
   * 面板正文按 pageId:index 存，插进数组中间会让用户改过的正文整体错位一行，
   * 所以字典小节是渲染时追加在最后一节之后，只读。
   * 顺序 = 本页渲染位的组件树先序（PRD 章节 id 也按这个生成）。
   */
  function walkTree(n, out) {
    out.push(n);
    (n.children || []).forEach(function (c) { walkTree(c, out); });
    return out;
  }

  function siteOf(nodeId, raw, kind, label, capId) {
    var key = raw.key;
    var ro = raw.type === 'readonly' || !!raw.readonly;
    var scope = (kind === 'form' || kind === 'dialog')
      ? (ro ? 'out' : 'in')
      : (kind === 'filter' ? (raw.field ? 'filter-field' : 'filter-cond') : 'out');
    return {
      nodeId: nodeId, capId: capId, siteId: capId || nodeId, kind: kind, key: key,
      biz: raw.field || key, label: label || key || '（无 key）',
      scope: scope, raw: raw
    };
  }

  function fieldSites(pageId) {
    var pg = (DATA.pages || []).filter(function (p) { return p.id === pageId; })[0];
    var out = [];
    if (!pg) return out;
    walkTree(pg.componentTree || {}, []).forEach(function (nd) {
      var pr = nd.props || {}, t = nd.type;
      if (t === 'FilterBar') {
        (pr.fields || []).forEach(function (f) { out.push(siteOf(nd.id, f, 'filter', f.label)); });
      } else if (t === 'FormGrid') {
        (pr.fields || pr.items || []).forEach(function (f) { out.push(siteOf(nd.id, f, 'form', f.label)); });
      } else if (t === 'DataTable') {
        (pr.columns || []).forEach(function (c) {
          if (c.type === 'action' || c.type === 'index') return;
          out.push(siteOf(nd.id, c, 'column', c.title));
        });
      } else if (t === 'DescList') {
        (pr.items || []).forEach(function (it) { out.push(siteOf(nd.id, it, 'desc', it.label)); });
      }
    });
    (DATA.capabilities || []).forEach(function (c) {
      if (ownsPageOf(c.id) !== pageId) return;
      ((c.ui || {}).fields || []).forEach(function (f) { out.push(siteOf(null, f, 'dialog', f.label, c.id)); });
    });
    return out;
  }

  function dsOf(id) {
    return (DATA.dataSources || []).filter(function (d) { return d.id === id; })[0];
  }

  function sourceText(src) {
    if (!src) return '未声明';
    var ds = dsOf(src.ds);
    if (!ds) return (src.ds || '?') + '（未声明的数据源）';
    var k = { entity: '实体', dict: '字典', calc: '计算', api: '接口', system: '系统' }[ds.kind] || ds.kind;
    var where = src.field ? (ds.ref + '.' + src.field) : (src.rule || ds.ref);
    return k + ' · ' + where + (src.fallback ? '；兜底：' + src.fallback : '');
  }

  function targetText(t) {
    return t ? (t.entity + '.' + t.field) : '不落库（纯展示/计算/筛选）';
  }

  function scopeText(s) {
    return { 'in': '录入', 'out': '展示', 'filter-field': '字段筛选', 'filter-cond': '条件筛选' }[s.scope] || s.scope;
  }

  function localLabel(s) {
    return { 'in': '校验规则', 'out': '空值显示', 'filter-field': '筛选口径', 'filter-cond': '筛选口径' }[s.scope] || '本处口径';
  }

  function localValue(s) {
    var v = ((s.raw.rules || {}).text) || ((s.raw.display || {}).empty) || s.raw.filterNote;
    if (v) return v;
    return s.scope === 'filter-field' ? '按该字段值筛选' : '未声明';
  }

  // 点字段标签 → 打开 PRD 面板并定位到该渲染位的块。
  // 优先级由 fieldClick 保证：标注模式 > 输入控件 > 字段标签 > 其余。
  function jumpToField(pid, site, key) {
    var target = (DATA.pages || []).filter(function (p) { return p.id === pid; })[0];
    if (!target) return;
    if (store.pageId !== pid) {
      store.pageId = pid;
      store.pageState = 'default';
      store.entityStatus = defaultStatus(target);
      refreshPins();
    }
    var id = 'field-' + pid + '-' + site + '-' + key;
    store.showPrd = true;
    store.prdTab = 'page';
    // 高亮用「标记 + 一次性淡出动画」而不是定时清标记：
    // headless 的虚拟时钟会把 1.6s 定时器瞬间推完，定时清标记会让 R-11 永远读不到高亮
    store.prdFocus = id;
    persist();
    setTimeout(function () {
      var el = document.getElementById(id);
      if (el && el.scrollIntoView) el.scrollIntoView({ block: 'center' });
    }, 0);
  }

  function fieldClick(e) {
    if (store.annotMode) return false;                       // 标注优先，已在 annotClick 里处理
    var t = e.target;
    if (!t.closest) return false;
    // 输入控件内的点击是填表，不是查字典
    if (t.closest('input, textarea, select, .input, .form-ro, .ff-ro')) return false;
    // 只认标签区：表格只认表头（点单元格要留给选中行）
    var lab = t.closest('.dt-head [data-field], .field-label, .form-label, .desc-k, .ff-label');
    if (!lab) return false;
    var host = lab.closest('[data-field]');
    if (!host) return false;
    var key = host.getAttribute('data-field');
    var site = host.getAttribute('data-site') || '';
    var pid = host.getAttribute('data-page') || store.pageId;
    if (!key) return false;
    jumpToField(pid, site, key);
    return true;
  }

  function dictBlock(pageId, s, i) {
    // 三段：页 + 容器 + key。同页同 key 出现在筛选/列/弹层时，只带 key 会撞
    var id = 'field-' + pageId + '-' + (s.siteId || 'no-site') + '-' + (s.key || ('x' + i));
    var cat = (DATA.fieldCatalog || []).filter(function (f) { return f.key === s.biz; })[0];
    var local = localValue(s);
    return h('div', {
      class: ['prd-field', store.prdFocus === id ? 'is-flash' : ''],
      id: id,
      key: id
    }, [
      h('div', { class: 'prd-field-h' }, [
        h('span', { class: 'prd-field-k' }, s.label),
        h('span', { class: 'prd-field-type' }, scopeText(s) + ' · ' + (s.siteId || '-') + ' · ' + s.key)
      ]),
      h('div', { class: 'prd-field-row' }, [h('b', null, localLabel(s)), h('span', null, local)]),
      h('div', { class: 'prd-field-row' }, [h('b', null, '业务字段'), h('span', null,
        cat ? (cat.label + '（' + cat.key + '）') : ('未绑定：' + (s.biz || '?')))]),
      h('div', { class: 'prd-field-row' }, [h('b', null, '来源'), h('span', null,
        cat ? sourceText(cat.source) : '—')]),
      h('div', { class: 'prd-field-row' }, [h('b', null, '去向'), h('span', null,
        cat ? targetText(cat.target) : '—')])
    ]);
  }

  function openLayer(capId, row, kindOverride) {
    var cap = capsById[capId];
    if (!cap) { toast('命令不存在：' + capId); return; }
    var ui = cap.ui || {};
    var values = {};
    (ui.fields || []).forEach(function (f) {
      values[f.key] = f.value != null ? f.value : (f.type === 'select' && (f.options || []).length ? f.options[0] : '');
    });
    store.layer = {
      capId: capId,
      row: row || null,
      kind: kindOverride || ui.kind || 'dialog',
      title: ui.title || cap.name || capId,
      width: ui.width || (kindOverride === 'drawer' ? 520 : 560),
      fields: ui.fields || [],
      submitLabel: ui.submitLabel || cap.name || '提交',
      successText: ui.successText || '',
      values: values,
      errors: {}
    };
    // 弹层里也可能有标注要钉：开了层就把 pin 重算一遍
    refreshPins();
  }

  function closeLayer() { store.layer = null; refreshPins(); }

  function submitLayer() {
    var L = store.layer;
    if (!L) return;
    var cap = capsById[L.capId] || {};
    var missing = [];
    L.errors = {};
    L.fields.forEach(function (f) {
      if (f.required && !String(L.values[f.key] == null ? '' : L.values[f.key]).trim()) {
        L.errors[f.key] = '必填：' + f.label;
        missing.push(f.label);
      }
    });
    if (missing.length) { toast('还有必填项没填：' + missing.join('、')); return; }

    var toLabel = '';
    if (cap.to) {
      var sm = smByEntity[cap.entity] || { states: [] };
      var to = (sm.states || []).filter(function (x) { return x.key === cap.to; })[0];
      toLabel = to ? to.label : cap.to;
      // 行级命令（措施单验证）只推进这一行，不动主单状态：它们是两张单据
      if (L.row) { L.row.status = toLabel; } else { store.entityStatus = cap.to; }
      persist();
    }

    var msg = L.successText || ((cap.name || '') + '已完成');
    if (toLabel) msg += (L.row ? '（本条措施 → ' : '（单据 → ') + toLabel + '）';
    store.layer = null;
    toast(msg);
    // 提交后若本页已无该状态可做的事，退回默认态，避免留在空白页
    if (store.pageState !== 'default') store.pageState = 'default';
    setTimeout(refreshPins, 0);
  }

  /* ---------------- 交互引擎 ----------------
   * pages[].interactions 是契约里的交互真源。以前只有 schema 和校验器认它，
   * 引擎从不读，于是"能点"只存在于文档里。这里把它接上。
   */
  function interactionsOf(pageId) {
    var p = (DATA.pages || []).filter(function (x) { return x.id === pageId; })[0] || {};
    return p.interactions || [];
  }

  function runInteraction(ix, row) {
    if (!ix) return;
    var doIt = ix.do;
    if (doIt === 'navigate') { window.RD.goto(ix.target); return; }
    if (doIt === 'openModal' || doIt === 'openDrawer') {
      openLayer(ix.target, row, doIt === 'openDrawer' ? 'drawer' : 'dialog');
      return;
    }
    if (doIt === 'setState') {
      var st = (ix.params || {}).status;
      if (st) { store.entityStatus = st; persist(); toast('单据状态已置为「' + ((smByEntity[page.value.entity] || {}).states || []).filter(function (x) { return x.key === st; }).map(function (x) { return x.label; })[0] + '」'); }
      return;
    }
    if (doIt === 'reset') { store.filters = {}; store.pageState = 'default'; toast('已重置'); return; }
    if (doIt === 'submit') {
      var cap = capsById[ix.target];
      if (cap && cap.ui && cap.ui.kind !== 'inline') { openLayer(ix.target, row); return; }
      window.RD.action(ix.target, ix.effect, row, ix.target);
      return;
    }
    if (doIt === 'toast') { toast((ix.params || {}).text || ix.effect || ''); return; }
  }

  window.RD = {
    state: store,
    data: DATA,
    /* 这个角色能不能点这条命令。
     * 第三参 actor 决定「权限」这半边，rowState 决定「状态」这半边，两件事不能混：
     *   权限不足 → 按钮根本不该出现（R-06）
     *   状态不对 → 按钮在、但是灰的，点一下给理由
     * actor 不传（undefined）时按"未声明角色 → 全部可见"处理：
     * 插件式调用方、老脚本、导出钩子都只传两个参数，硬要第三参会让整页按钮凭空消失。
     * 内部一律三参调用（components.js 的 can() 负责补当前角色）。
     */
    can: function (capId, rowState, actor) {
      var cap = capsById[capId];
      if (!cap) return { ok: true };
      // 第三参缺省（undefined / null）与顶栏选「全部角色（不限）」传的空串，走同一条分支：
      // 都是"不限制角色"。这个合流是刻意的——否则就是两个语义相同的开关，
      // 一个在界面上明写、一个在代码里静默放行，后者没人看得见。
      var who = (actor === undefined || actor === null) ? '' : String(actor);
      var allowed = cap.actor || [];
      if (who && allowed.length && allowed.indexOf(who) < 0) {
        return {
          ok: false, denied: 'role',
          reason: '当前角色「' + actorName(who) + '」不能做这个操作（仅 ' + allowed.map(actorName).join('、') + ' 可用）'
        };
      }
      // 行级按钮（措施单/验证行）按自身状态判定，不跟随主单状态
      var curKey = store.entityStatus;
      var curLabel = null;
      if (rowState) {
        var smRow = smByEntity[cap.entity] || { states: [] };
        var hit = (smRow.states || []).filter(function (x) {
          return x.label === rowState || x.key === rowState;
        })[0];
        curKey = hit ? hit.key : rowState;
        curLabel = hit ? hit.label : rowState;
      }
      if ((cap.from || []).length && (cap.from || []).indexOf(curKey) < 0) {
        var sm = smByEntity[cap.entity] || { states: [] };
        var cur = curLabel || ((sm.states || []).filter(function (x) { return x.key === curKey; })[0] || {}).label || curKey;
        return { ok: false, denied: 'state', reason: (cap.reason || '当前状态不可用') + '（当前为「' + cur + '」）' };
      }
      return { ok: true };
    },
    entityStatus: function () { return store.entityStatus; },
    pageState: function () { return store.pageState; },
    toast: toast,
    // 点按钮 = 走一次命令。命令里写了 to 就真的迁移状态（原型因此能跑通整条状态机），
    // 没写 to 的是查询/导出类动作，只提示不迁移。
    // 命令声明了 ui 承载的，先按契约开层；填完在层里提交，而不是点一下就跳过填报。
    action: function (key, text, row, capId) {
      var cap = capId ? capsById[capId] : null;
      // 角色和状态都要在引擎里拦一道：按钮藏着是界面的事，
      // 键盘/脚本/插件绕过界面直接调 action 时，状态机不能跟着破。
      // 行级命令按这一行的状态判（措施单的状态与主单是两回事），单据级才看 store.entityStatus。
      // 这不是"安全"——原型没有后端——是保真：可达集被脚本扩大以后，
      // 导出的状态图就不再描述这台原型真实能走的路。
      if (cap) {
        var rowStatus = row ? (row.status || row.state) : null;
        var perm = window.RD.can(capId, rowStatus, store.currentUser || '');
        if (!perm.ok) { toast(perm.reason); return; }
      }
      if (cap && cap.ui) {
        var kind = cap.ui.kind;
        if (kind === 'dialog' || kind === 'drawer') { openLayer(capId, row || null, kind); return; }
        if (kind === 'page') { window.RD.goto(cap.ui.pageId || cap.target, cap.ui.title); return; }
      }
      if (cap && cap.to) {
        var sm = smByEntity[cap.entity] || { states: [] };
        var to = (sm.states || []).filter(function (x) { return x.key === cap.to; })[0];
        var toLabel = to ? to.label : cap.to;
        // 行级命令只推进该行，不动主单状态（措施单与事故报告是两张单据）
        if (row) {
          var from = row.status;
          row.status = toLabel;
          toast('「' + (row.content || row.accNo || '本行') + '」' + from + ' → ' + toLabel + '（本条措施已推进，主单状态不变）');
          return;
        }
        store.entityStatus = cap.to;
        persist();
        toast((cap.label || text || key) + '已完成，单据状态置为「' + toLabel + '」');
        return;
      }
      if (key === 'export') {
        toast('已按当前筛选导出 ' + (store.pageState === 'zero-result' ? 0 : 10) + ' 条，导出人与时间已留痕');
        return;
      }
      if (key === 'create') { toast('新建：已打开建单页（原型演示）'); return; }
      toast((text || key) + (row ? '（' + (row.accNo || row.id || '') + '）' : '') + ' · 原型演示，未接后端');
    },
    search: function (key) {
      if (key !== 'search') { store.filters = {}; store.pageState = 'default'; toast('已重置查询条件'); return; }
      var any = false;
      for (var k in store.filters) {
        if (String(store.filters[k] == null ? '' : store.filters[k]).trim()) { any = true; break; }
      }
      store.pageState = any ? 'zero-result' : 'default';
      toast(any ? '查询完成：0 条（条件已保留）' : '查询完成');
    },
    stateAction: function (key) {
      if (key === 'retry') {
        store.pageState = 'loading';
        setTimeout(function () { store.pageState = 'default'; toast('已恢复'); }, 700);
        return;
      }
      if (key === 'clear') { store.filters = {}; store.pageState = 'default'; toast('已清空条件'); return; }
      if (key === 'create') { toast('跳转「发起申请」（原型演示）'); return; }
      if (key === 'offline') { toast('已导出上次成功结果'); return; }
    },
    // 行点击也是一次交互：列表点行去详情，靠契约的 __row_click 声明，不靠组件写死
    selectRow: function (row) {
      store.selectedRow = row;
      var ix = interactionsOf(store.pageId).filter(function (x) { return x.on === '__row_click'; })[0];
      if (ix) runInteraction(ix, row);
    },
    openLayer: openLayer,
    closeLayer: closeLayer,
    submitLayer: submitLayer,
    layer: function () { return store.layer; },
    // 页面间跳转：统计页指标卡下钻、详情跳回列表都走这里
    goto: function (pid, label) {
      var target = (DATA.pages || []).filter(function (p) { return p.id === pid; })[0];
      if (!target) { toast('目标页面不存在：' + pid); return; }
      store.pageId = pid;
      store.pageState = 'default';
      store.entityStatus = defaultStatus(target);
      if (target.target === 'pc' && target.states) {
        var kinds = target.states.map(function (s) { return s.kind; });
        if (kinds.indexOf('default') < 0) store.pageState = kinds[0];
      }
      persist();
      refreshPins();
      toast('已跳转：' + (label || target.title || pid));
    },
    scan: function () { store.pdaQty = 32; toast('已识别 PA-20261028-001，取样上限 320 件'); },
    setQty: function (v) { store.pdaQty = Number(v) || 0; }
  };

  /* ---------------- 渲染 JSON 组件树 ---------------- */
  function renderNode(node) {
    if (!node) return null;
    var known = window.RD_COMPONENTS[node.type];
    var C = known || window.RD_COMPONENTS.Fallback;
    // site 传给组件：字段级 data-site 要用容器节点 id（与 check 里的 siteId 同一口径）
    var props = { p: node.props || {}, site: node.id, 'data-node-id': node.id };
    if (!known) props.type = node.type;
    var kids = (node.children || []).map(renderNode).filter(Boolean);
    if (kids.length) return h(C, props, { default: function () { return kids; } });
    return h(C, props);
  }

  /* ---------------- 标注 ----------------
   * 锚点有两种载体：
   *   1) 页面元素        data-node-id = "n-xxx"
   *   2) 弹框/抽屉字段    data-node-id = "layer:<capId>:<fieldKey>"
   * 第二种是评审里最常被漏掉的地方——"这个字段该拆成两个"往往是在弹框打开时才发现的。
   * 所以 pin 层挂在视口上（fixed），不是挂在画布上；否则弹层一开、pin 就被压在遮罩下面。
   */
  function anchorEl(nodeId) {
    if (!nodeId) return null;
    if (String(nodeId).indexOf('layer:') === 0) {
      var host = document.querySelector('.layer-mask');
      if (!host) return null;            // 弹层没开：这枚 pin 暂时无处安放，但仍留在列表里
      return host.querySelector('[data-node-id="' + nodeId + '"]');
    }
    return document.querySelector('#stage [data-node-id="' + nodeId + '"]');
  }

  function nodeLabelOf(el) {
    if (!el) return '';
    var lab = el.getAttribute('data-node-label');
    if (lab) return lab;
    return (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 24);
  }

  function annById(id) {
    return store.annotations.filter(function (x) { return x.id === id; })[0] || null;
  }

  function refreshPins() {
    nextTick(function () {
      var cur = store.pageId;
      var out = [], missing = [];
      store.annotations.forEach(function (a) {
        if (a.pageId !== cur || a.status === 'deleted') return;
        var el = anchorEl(a.nodeId);
        if (!el) { missing.push(a.id); return; }
        var r = el.getBoundingClientRect();
        if (!r.width && !r.height) { missing.push(a.id); return; }
        // 老版本存下来的标注可能没有 anchor（或存成了字符串）。
        // 这里不能直接取 a.anchor.x：一条脏数据会抛异常，把整页的 pin 全带没了，
        // 表现就是"标注一条都看不见"，而数据其实还在。
        var anc = a.anchor || {};
        var ax = parseFloat(anc.x), ay = parseFloat(anc.y);
        if (!isFinite(ax)) ax = 0.5;
        if (!isFinite(ay)) ay = 0.5;
        out.push({
          id: a.id,
          idx: store.annotations.filter(function (x) { return x.pageId === cur; }).indexOf(a) + 1,
          x: r.left + r.width * ax,
          y: r.top + r.height * ay,
          status: a.status
        });
      });
      store.pins = out;
      store.missingPins = missing;
    });
  }

  function addAnnotation(nodeId, evt) {
    var el = anchorEl(nodeId);
    if (!el) return;
    var r = el.getBoundingClientRect();
    var ax = Math.min(0.98, Math.max(0.02, (evt.clientX - r.left) / (r.width || 1)));
    var ay = Math.min(0.98, Math.max(0.02, (evt.clientY - r.top) / (r.height || 1)));
    var inLayer = String(nodeId).indexOf('layer:') === 0;
    store.popover = {
      mode: 'new', nodeId: nodeId,
      x: evt.clientX, y: evt.clientY,
      text: '', anchor: { x: ax, y: ay },
      // 落点快照：换一版原型后 nodeId 可能不在了，靠它把意见还原成"哪个页面的哪一块"
      target: {
        pageTitle: page.value.title,
        nodeLabel: nodeLabelOf(el),
        nodeText: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40),
        carrier: inLayer ? ((store.layer && store.layer.kind) || 'dialog') : 'page',
        capId: inLayer ? String(nodeId).split(':')[1] : undefined
      }
    };
  }

  // 标注模式下的点击统一入口：画布和弹层共用。弹层不共用的话，
  // "这个弹框字段该拆开"这类意见就只能写在整页上，落点说不清。
  function annotClick(e) {
    if (!store.annotMode) return false;
    if (e.target.closest('.annot-pop') || e.target.closest('.annot-pin')) return true;
    var ael = e.target.closest('[data-node-id]');
    if (!ael) { store.popover = null; return true; }
    addAnnotation(ael.getAttribute('data-node-id'), e);
    return true;
  }

  function saveAnnotation() {
    var p = store.popover;
    if (!p) return;
    if (!p.text.trim()) {
      toast(p.mode === 'resolve' ? '写一句「怎么改的」——下一轮的人只能看到这句话' : '先写一句要改什么');
      return;
    }
    if (p.mode === 'new') {
      var seq = store.annotations.length + 1;
      while (annById('an-' + seq)) seq += 1;
      store.annotations.push({
        id: 'an-' + seq,
        pageId: store.pageId,
        nodeId: p.nodeId,
        anchor: p.anchor,
        body: p.text.trim(),
        severity: 'major',
        status: 'open',
        author: '我',
        createdAt: new Date().toISOString(),
        target: p.target,
        affects: ['componentTree']
      });
      toast('标注已加，点「标注」可导出成修改指令');
    } else if (p.mode === 'resolve') {
      var r = annById(p.id);
      if (r) {
        r.status = 'resolved';
        r.resolution = p.text.trim();
        r.resolvedAt = new Date().toISOString();
      }
      toast('已标记完成，并记下解决方法');
    } else {
      var a = annById(p.id);
      if (a) a.body = p.text.trim();
      toast('标注已更新');
    }
    store.popover = null;
    persist();
    refreshPins();
  }

  /* ---------------- 导出 ---------------- */
  function download(name, text, mime) {
    var blob = new Blob([text], { type: mime || 'text/plain;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1200);
  }

  function buildMd() {
    var L = [];
    var m = DATA.meta;
    // 角色 id 只活在契约里，导出的 PRD 一律用中文岗位名
    var actorMap = {};
    (DATA.actors || []).forEach(function (a) { actorMap[a.id] = a.name || a.id; });
    function anames(list) { return (list || []).map(function (x) { return actorMap[x] || x; }).join('、'); }
    // 状态 key 同理：reported 是给程序看的，人看的是「待审核」
    var stateMap = {};
    (DATA.stateMachines || []).forEach(function (sm) {
      (sm.states || []).forEach(function (st) { stateMap[st.key] = st.label || st.key; });
    });
    function snames(list) {
      if (!(list || []).length) return '不限';
      return list.map(function (x) { return stateMap[x] || x; }).join('、');
    }
    L.push('# ' + m.product + ' · ' + page.value.title);
    L.push('');
    L.push('> 模块：' + (moduleOf.value.name || '') + '（' + (moduleOf.value.code || '') + '） ｜ 端：' + page.value.target.toUpperCase() + ' ｜ 路由：' + page.value.route);
    L.push('');
    L.push('## 1 页面职责');
    L.push('');
    L.push('- 任务：' + (page.value.contract.task || ''));
    L.push('- 角色：' + anames(page.value.contract.actor));
    L.push('- 完成条件：' + (page.value.contract.doneWhen || ''));
    L.push('');
    L.push('## 2 需求（EARS）');
    L.push('');
    (page.value.prd.sections || []).forEach(function (s, i) {
      var body = store.prdEdits[page.value.id + ':' + i] || s.body || '';
      L.push('### ' + s.heading);
      L.push('');
      if (s.type === 'flow') {
        (s.nodes || []).forEach(function (n) { L.push('- ' + n.label + (n.sub ? '（' + n.sub + '）' : '')); });
        (s.edges || []).forEach(function (e) { L.push('  - ' + e.from + ' → ' + e.to + (e.label ? '  [' + e.label + ']' : '')); });
      } else if (body) {
        L.push(body);
      }
      L.push('');
    });
    L.push('## 3 动作可用性');
    L.push('');
    L.push('| 命令 | 允许角色 | 可用状态 | 不可用策略 | 提示文案 |');
    L.push('|---|---|---|---|---|');
    DATA.capabilities.forEach(function (c) {
      L.push('| ' + (c.label || c.name || c.id) + ' | ' + anames(c.actor) + ' | ' + snames(c.from) + ' | ' + c.policy + ' | ' + c.reason + ' |');
    });
    L.push('');
    L.push('## 4 验收用例');
    L.push('');
    DATA.requirements.forEach(function (r) {
      L.push('### ' + r.id + ' ' + r.title);
      (r.acceptance || []).forEach(function (a) {
        L.push('- [' + (a.kind === 'illegal' ? '非法路径' : '主路径') + '] 给定 ' + a.given + '，当 ' + a.when + '，则 ' + a.then);
      });
    });
    if (store.annotations.length) {
      L.push('');
      L.push('## 5 标注');
      L.push('');
      var op = store.annotations.filter(function (a) { return a.status === 'open'; });
      var dn = store.annotations.filter(function (a) { return a.status && a.status !== 'open' && a.status !== 'deleted'; });
      op.forEach(function (a) {
        L.push('- [待处理] `' + a.nodeId + '` ' + a.body);
      });
      if (!op.length) L.push('- （无待处理标注）');
      if (dn.length) {
        L.push('');
        L.push('已完成 ' + dn.length + ' 条，处理方法：');
        dn.forEach(function (a) {
          L.push('- ' + a.body + ' → ' + (a.resolution || '（未填）'));
        });
      }
    }
    // 字段字典：与面板同源（fieldSites + fieldCatalog），顺序 = 组件树先序
    var fss = fieldSites(page.value.id);
    if (fss.length) {
      L.push('');
      L.push('## 6 字段字典');
      L.push('');
      L.push('| 位置 | 文案 | 形态 | 业务字段 | 来源 | 去向 | 本处口径 |');
      L.push('|---|---|---|---|---|---|---|');
      fss.forEach(function (s) {
        var cat = (DATA.fieldCatalog || []).filter(function (f) { return f.key === s.biz; })[0];
        var local = localValue(s);
        L.push('| ' + s.kind + ' | ' + (s.label || s.key) + ' | ' + scopeText(s) + ' | '
          + (cat ? cat.label + '（' + cat.key + '）' : '未绑定') + ' | '
          + (cat ? sourceText(cat.source) : '—') + ' | '
          + (cat ? targetText(cat.target) : '—') + ' | ' + local + ' |');
      });
      L.push('');
      fss.forEach(function (s, i) {
        var cat = (DATA.fieldCatalog || []).filter(function (f) { return f.key === s.biz; })[0];
        L.push('### field-' + page.value.id + '-' + (s.key || ('x' + i)) + ' ' + (s.label || s.key));
        L.push('');
        L.push('- 形态：' + scopeText(s));
        L.push('- ' + localLabel(s) + '：' + localValue(s));
        L.push('- 业务字段：' + (cat ? cat.label + '（' + cat.key + '）' : '未绑定'));
        L.push('- 来源：' + (cat ? sourceText(cat.source) : '—'));
        L.push('- 去向：' + (cat ? targetText(cat.target) : '—'));
        L.push('');
      });
    }
    return L.join('\n');
  }

  function exportMd() {
    download(DATA.meta.product + '-' + page.value.title + '-PRD.md', buildMd(), 'text/markdown;charset=utf-8');
    toast('已导出 Markdown');
    store.showExport = false;
  }

  function exportHtml() {
    var css = document.getElementById('iiot-css').textContent;
    var appEl = document.querySelector('#stage .app') || document.querySelector('#stage .pda');
    var html = '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
      + '<meta name="viewport" content="width=device-width,initial-scale=1">'
      + '<title>' + DATA.meta.product + ' · ' + page.value.title + '</title>'
      + '<style>' + css + '\nhtml,body{height:100%}\n.shell-top,.overlay,.annot-layer,.toast-wrap{display:none!important}\n</style>'
      + '</head><body><div class="shell"><div class="stage"><div class="canvas">'
      + (appEl ? appEl.outerHTML : '')
      + '</div></div></div></body></html>';
    download(DATA.meta.product + '-' + page.value.title + '.html', html, 'text/html;charset=utf-8');
    toast('已导出单页 HTML（可直接给前端）');
    store.showExport = false;
  }

  function exportPng() {
    var el = document.querySelector('#stage .app') || document.querySelector('#stage .pda');
    if (!el) return;
    var css = document.getElementById('iiot-css').textContent;
    var w = el.scrollWidth, ht = el.scrollHeight;
    var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + ht + '">'
      + '<foreignObject width="100%" height="100%"><div xmlns="http://www.w3.org/1999/xhtml">'
      + '<style>' + css + '</style>' + el.outerHTML + '</div></foreignObject></svg>';
    var img = new Image();
    img.onload = function () {
      var cv = document.createElement('canvas');
      cv.width = w; cv.height = ht;
      var ctx = cv.getContext('2d');
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, w, ht);
      ctx.drawImage(img, 0, 0);
      cv.toBlob(function (blob) {
        if (!blob) { toast('截图失败，可改用浏览器打印'); return; }
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = DATA.meta.product + '-' + page.value.title + '.png';
        a.click();
        toast('已导出 PNG');
      }, 'image/png');
    };
    img.onerror = function () { toast('截图失败，可改用「打印 / 存 PDF」'); };
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    store.showExport = false;
  }

  function exportAnnot() {
    var pageTitle = {};
    (DATA.pages || []).forEach(function (p) { pageTitle[p.id] = p.title; });
    var all = store.annotations.filter(function (a) { return a.status !== 'deleted'; });
    var open = all.filter(function (a) { return a.status === 'open'; });
    var done = all.filter(function (a) { return a.status !== 'open'; });
    var L = ['# 原型修改指令', '',
             '> 来源：' + DATA.meta.product + ' ' + (DATA.meta.version || '') + '　｜　待处理 ' + open.length + ' 条，已完成 ' + done.length + ' 条', ''];
    L.push('## 待处理（' + open.length + '）', '');
    open.forEach(function (a, i) {
      var where = pageTitle[a.pageId] || ('（页面已下线：' + a.pageId + '）');
      var tgt = a.target ? ('「' + (a.target.nodeLabel || a.nodeId) + '」') : ('`' + a.nodeId + '`');
      L.push((i + 1) + '. **' + where + '** · ' + tgt +
             (a.target && a.target.carrier && a.target.carrier !== 'page' ? '（弹层内）' : ''));
      L.push('   - 要改：' + a.body);
      L.push('   - 锚点：`' + a.nodeId + '`（' + a.id + '）');
    });
    if (!open.length) L.push('（无待处理标注）');
    if (done.length) {
      L.push('', '## 已完成（' + done.length + '）', '',
             '> 保留它们是为了下一个人不用重新发现同一个问题。', '');
      done.forEach(function (a, i) {
        L.push((i + 1) + '. **' + (pageTitle[a.pageId] || a.pageId) + '** ' + a.body);
        L.push('   - 处理方法：' + (a.resolution || '（当时没写，建议补一句）'));
      });
    }
    download('修改指令-' + DATA.meta.product + '.md', L.join('\n'), 'text/markdown;charset=utf-8');
    toast('已导出修改指令（含已完成记录）');
  }

  /* ---------------- 小部件 ---------------- */
  var FlowList = {
    name: 'FlowList',
    props: { section: Object },
    setup: function (props) {
      return function () {
        var s = props.section || {};
        var nodes = s.nodes || [];
        var edges = s.edges || [];
        var kindColor = { start: 'var(--brand-600)', end: 'var(--ok-600)', task: 'var(--text-2)', decision: 'var(--warn-600)', warn: 'var(--danger-600)', system: 'var(--info-600)' };
        var rows = [];
        nodes.forEach(function (n) {
          var outs = edges.filter(function (e) { return e.from === n.id; });
          rows.push(h('div', { key: 'n' + n.id, style: { display: 'flex', gap: '8px', padding: '5px 0' } }, [
            h('div', {
              style: {
                width: '6px', height: '6px', borderRadius: n.kind === 'decision' ? '1px' : '50%',
                background: kindColor[n.kind] || 'var(--text-3)', marginTop: '6px', flex: '0 0 6px'
              }
            }),
            h('div', { style: { flex: '1' } }, [
              h('div', { style: { fontSize: '12px', color: 'var(--text-1)', lineHeight: '1.6' } }, [
                n.label,
                n.sub ? h('span', { class: 'mono', style: { fontSize: '10px', color: 'var(--text-3)', marginLeft: '6px' } }, n.sub) : null
              ]),
              outs.length && (outs.length > 1 || outs[0].label) ? h('div', { style: { fontSize: '11px', color: 'var(--text-3)', marginTop: '2px' } },
                outs.map(function (e, i) {
                  var tgt = nodes.filter(function (x) { return x.id === e.to; })[0];
                  return h('span', { key: i }, [(i ? '　·　' : '') + (e.label || '') + ' → ' + (tgt ? tgt.label : e.to)]);
                })) : null
            ])
          ]));
        });
        return h('div', { class: 'flow-box' }, rows);
      };
    }
  };

  var PrdPanel = {
    name: 'PrdPanel',
    setup: function () {
      function startDrag(e) {
        e.preventDefault();
        var startX = e.clientX;
        var startW = store.prdWidth;
        function move(ev) {
          store.prdWidth = Math.min(760, Math.max(360, startW + (startX - ev.clientX)));
        }
        function up() {
          window.removeEventListener('mousemove', move);
          window.removeEventListener('mouseup', up);
        }
        window.addEventListener('mousemove', move);
        window.addEventListener('mouseup', up);
      }
      return function () {
        var pg = page.value;
        var tabs = [
          { key: 'page', label: '页面 PRD' },
          { key: 'global', label: '全局' },
          { key: 'annot', label: '标注 ' + store.annotations.filter(function (a) { return a.pageId === store.pageId; }).length }
        ];
        var body;

        if (store.prdTab === 'page') {
          body = h('div', { class: 'prd-body' }, [
            h('div', { class: 'prd-h1' }, pg.title),
            h('div', { class: 'prd-sub' }, [
              (moduleOf.value.name || '') + ' · ' + pg.target.toUpperCase() + ' · ' + pg.route,
              h('span', { style: { marginLeft: '8px', color: 'var(--brand-600)', cursor: 'pointer' }, onClick: function () { store.prdTab = 'global'; } }, '看命令矩阵 →')
            ]),
            (pg.prd.sections || []).map(function (s, i) {
              var edited = store.prdEdits[pg.id + ':' + i];
              var isFlow = s.type === 'flow';
              return h('div', { class: 'prd-sec', key: i }, [
                h('div', { class: 'prd-sec-h' }, [s.heading, h('span', null, s.type)]),
                isFlow ? h(FlowList, { section: s }) : h('div', {
                  class: 'prd-text',
                  contentEditable: store.audit ? 'false' : 'true',
                  onBlur: function (e) { store.prdEdits[pg.id + ':' + i] = e.target.innerText; persist(); },
                  innerText: edited || s.body || ''
                })
              ]);
            }),
            // 字段字典：合成在最后一节之后，只读。没有渲染位的页面不生成空小节
            (function () {
              var ss = fieldSites(pg.id);
              if (!ss.length) return null;
              return h('div', { class: 'prd-sec' }, [
                h('div', { class: 'prd-sec-h' }, ['字段字典', h('span', null, 'fields')]),
                h('div', { class: 'prd-dict' }, ss.map(function (s, i) { return dictBlock(pg.id, s, i); }))
              ]);
            })()
          ]);
        } else if (store.prdTab === 'global') {
          var sm = smByEntity[pg.entity] || { states: [] };
          body = h('div', { class: 'prd-body' }, [
            h('div', { class: 'prd-h1' }, '命令 × 状态矩阵'),
            h('div', { class: 'prd-sub' }, '按钮可用性不写在组件上，全部由这里推导'),
            h('table', { class: 'matrix' }, [
              h('thead', null, h('tr', null, [h('th', null, '命令'), h('th', null, '角色'), h('th', null, '可用状态'), h('th', null, '策略')])),
              h('tbody', null, DATA.capabilities.map(function (c, i) {
                return h('tr', { key: i }, [
                  h('td', null, c.name),
                  h('td', null, (c.actor || []).join('、')),
                  h('td', null, (c.from || []).map(function (k) {
                    var st = (sm.states || []).filter(function (x) { return x.key === k; })[0];
                    return st ? st.label : k;
                  }).join(' / ')),
                  h('td', null, c.policy + '：' + c.reason)
                ]);
              }))
            ]),
            h('div', { class: 'prd-h1', style: { marginTop: '18px' } }, '状态机'),
            h('div', { class: 'prd-sub' }, sm.label || ''),
            h('div', { class: 'flow-box' }, [
              h('div', { style: { fontSize: '12px', color: 'var(--text-2)', lineHeight: '1.9' } },
                (sm.states || []).map(function (s) { return s.label + '(' + s.key + ')'; }).join('  ·  ')),
              h('div', { style: { fontSize: '11px', color: 'var(--text-3)', marginTop: '6px', lineHeight: '1.9' } },
                (sm.transitions || []).map(function (t) {
                  return t.from + ' → ' + t.to + ' ← ' + t.trigger + (t.system ? '（系统）' : '');
                }).join('　'))
            ]),
            h('div', { class: 'prd-h1', style: { marginTop: '18px' } }, '需求条目'),
            DATA.requirements.map(function (r) {
              return h('div', { class: 'req-card', key: r.id }, [
                h('div', null, [h('span', { class: 'req-id' }, r.id), h('span', { style: { fontSize: '10px', color: 'var(--text-3)', marginLeft: '6px' } }, r.priority)]),
                h('div', { class: 'req-title' }, r.title),
                h('div', { class: 'req-row' }, [h('b', null, '角色'), h('span', null, r.actor)]),
                h('div', { class: 'req-row' }, [h('b', null, '触发'), h('span', null, r.trigger)]),
                h('div', { class: 'req-row' }, [h('b', null, '规则'), h('span', null, r.rule)]),
                h('div', { class: 'req-row' }, [h('b', null, '状态机'), h('span', null, r.stateMachine)]),
                h('div', { class: 'req-row' }, [h('b', null, '预期'), h('span', null, r.expectation)]),
                h('div', { class: 'acc' }, (r.acceptance || []).map(function (a, i) {
                  return h('div', { class: ['acc-item', a.kind === 'illegal' ? 'is-illegal' : ''], key: i },
                    (a.kind === 'illegal' ? '✕ ' : '✓ ') + a.given + '，当 ' + a.when + '，则 ' + a.then);
                }))
              ]);
            })
          ]);
        } else {
          // 标注面板按状态分成两组：待处理 / 已完成（带解决方法）。
          // 落点失效不单独成组——那会让"已完成"的意见退回"待处理"的错觉，
          // 而是在卡片里加一条黄色提示，写清它原本指哪儿。
          // 这一段是"改完之后之前的标注去哪了"的答案：不删、不藏。
          var allScope = store.annotScope === 'all';
          var pageIds = {};
          (DATA.pages || []).forEach(function (x) { pageIds[x.id] = 1; });
          var pool = store.annotations.filter(function (a) {
            if (a.status === 'deleted') return false;
            return allScope || a.pageId === store.pageId;
          });
          function isOrphan(a) { return !pageIds[a.pageId]; }
          function pinMissing(a) {
            if (isOrphan(a)) return true;
            if (a.pageId !== store.pageId) return false;   // 别的页没渲染，谈不上失效
            return store.missingPins.indexOf(a.id) >= 0;
          }
          var openList = pool.filter(function (a) { return a.status === 'open'; });
          var doneList = pool.filter(function (a) { return a.status !== 'open'; });
          var orphans = pool.filter(isOrphan);

          function card(a, i) {
            var missing = pinMissing(a);
            var page = (DATA.pages || []).filter(function (x) { return x.id === a.pageId; })[0];
            var where = (a.target && a.target.nodeLabel) || a.nodeId;
            return h('div', {
              class: ['annot-card', a.status === 'open' ? '' : 'is-resolved', missing ? 'is-missing' : ''],
              key: a.id
            }, [
              h('div', { class: 'annot-card-top' }, [
                h('div', { class: 'annot-idx' }, String(i + 1)),
                h('span', { class: 'annot-node', title: a.nodeId }, where),
                h('span', {
                  style: { marginLeft: 'auto', fontSize: '10px', color: a.status === 'open' ? 'var(--warn-600)' : 'var(--ok-600)' }
                }, a.status === 'open' ? '待处理' : '已完成')
              ]),
              allScope || missing
                ? h('div', { class: 'annot-where' }, [
                    (page ? page.title : '（该页面已不在本版原型里）'),
                    a.target && a.target.carrier && a.target.carrier !== 'page' ? ' · 弹层内' : '',
                    a.pageId !== store.pageId && page ? h('a', {
                      style: { marginLeft: '6px' },
                      onClick: function () { store.pageId = a.pageId; }
                    }, '去这一页') : null
                  ])
                : null,
              h('div', { class: 'annot-body' }, a.body),
              missing ? h('div', { class: 'annot-stale' },
                '落点已失效：这一版原型里找不到原来的元素（页面结构可能调过了）。意见保留在这里，改动前请人工确认。') : null,
              a.status !== 'open' && a.resolution
                ? h('div', { class: 'annot-resolution' }, [h('b', null, '解决方法　'), a.resolution])
                : null,
              h('div', { class: 'annot-actions' }, [
                a.status === 'open'
                  ? h('a', {
                      onClick: function () {
                        store.popover = {
                          mode: 'resolve', id: a.id, nodeId: a.nodeId, text: '',
                          anchor: a.anchor, x: Math.max(40, (window.innerWidth || 1200) / 2 - 150), y: 200
                        };
                      }
                    }, '标记完成')
                  : h('a', {
                      onClick: function () {
                        a.status = 'open';
                        a.resolvedAt = undefined;
                        persist(); refreshPins();
                      }
                    }, '重新打开'),
                h('a', {
                  onClick: function () {
                    store.popover = {
                      mode: 'edit', id: a.id, nodeId: a.nodeId, text: a.body, anchor: a.anchor,
                      x: Math.max(40, (window.innerWidth || 1200) / 2 - 150), y: 200
                    };
                  }
                }, '编辑'),
                h('a', {
                  onClick: function () {
                    if (!window.confirm('删掉这条标注？删除后不再保留（建议标记完成，留个结论）。')) return;
                    a.status = 'deleted'; persist(); refreshPins();
                  }
                }, '删除')
              ])
            ]);
          }

          body = h('div', { class: 'prd-body' }, [
            h('div', { class: 'prd-h1' }, '标注（待处理 ' + openList.length + ' / 已完成 ' + doneList.length + '）'),
            h('div', { class: 'prd-sub' }, '点顶栏「标注」，再点页面元素即可添加——弹框/抽屉里的字段也能标。换一版原型后标注不会消失。'),
            h('div', { class: 'annot-scope' }, [
              h('button', { class: ['chip', !allScope ? 'is-on' : ''], onClick: function () { store.annotScope = 'page'; } }, '本页'),
              h('button', { class: ['chip', allScope ? 'is-on' : ''], onClick: function () { store.annotScope = 'all'; } }, '全部页面')
            ]),
            orphans.length
              ? h('div', { class: 'annot-alert' }, [
                  '有 ' + orphans.length + ' 条标注指向已经不在本版原型里的页面。它们被保留在「全部页面」里，',
                  '不会自动删除——要不要保留由你决定。'
                ])
              : null,
            h('div', { class: 'annot-group-title' }, '待处理'),
            h('div', { class: 'annot-list' }, openList.length
              ? openList.map(card)
              : h('div', { class: 'annot-empty' }, '没有待处理的标注')),
            h('div', { class: 'annot-group-title' }, '已完成'),
            h('div', { class: 'annot-list' }, doneList.length
              ? doneList.map(card)
              : h('div', { class: 'annot-empty' }, '还没有已完成的标注')),
            h('div', { style: { marginTop: '10px', display: 'flex', gap: '8px' } }, [
              h('button', { class: 'btn', onClick: exportAnnot }, '导出修改指令'),
              h('button', {
                class: 'btn', onClick: function () {
                  if (!window.confirm('清空全部标注（含已完成）？此操作不可撤销。')) return;
                  store.annotations = [];
                  persist(); refreshPins(); toast('标注已清空');
                }
              }, '清空')
            ])
          ]);
        }

        return h('aside', { class: 'overlay overlay-right', style: { width: store.prdWidth + 'px' } }, [
          h('div', { class: 'overlay-grip', onMousedown: startDrag, title: '拖动调宽' }),
          h('div', { class: 'overlay-head' }, [
            h('div', { class: 'overlay-title' }, 'PRD'),
            h('button', { class: 'icon-btn', onClick: function () { store.showPrd = false; store.prdFocus = ''; } }, '×')
          ]),
          h('div', { class: 'prd-tabs' }, tabs.map(function (t) {
            return h('button', {
              key: t.key,
              class: ['prd-tab', store.prdTab === t.key ? 'is-on' : ''],
              onClick: function () { store.prdTab = t.key; }
            }, t.label);
          })),
          body
        ]);
      };
    }
  };

  var TocPanel = {
    name: 'TocPanel',
    setup: function () {
      return function () {
        // 页面目录也是树：一个模块底下十几个页面，平铺就退化成"扫一遍找名字"。
        // 数据三级兜底，优先级从"人写的"到"推出来的"：
        //   ① modules[].pageGroups —— 策划时按功能分好的组，最准
        //   ② pages[].parentId    —— 契约里本来就有的层级，只是以前没人用
        //   ③ 按页面用途分组       —— 什么都没有时，至少别给一坨平行项
        var KIND = {
          list: '列表', form: '表单', detail: '详情', dashboard: '看板',
          wizard: '分步', 'pda-list': '列表', 'pda-step': '分步', 'pda-scan': '扫码'
        };
        function pageOf(id) {
          return (DATA.pages || []).filter(function (x) { return x.id === id; })[0] || null;
        }
        function modulePages(m) {
          return (m.pages || []).map(pageOf).filter(Boolean);
        }
        function fromParentId(m) {
          var ps = modulePages(m), inMod = {};
          ps.forEach(function (p) { inMod[p.id] = 1; });
          var kids = {};
          ps.forEach(function (p) {
            var par = p.parentId && inMod[p.parentId] ? p.parentId : null;
            if (par) (kids[par] = kids[par] || []).push(p);
          });
          function node(p) {
            return {
              key: 'p-' + p.id, title: p.title, page: p.id,
              children: (kids[p.id] || []).map(node)
            };
          }
          return ps.filter(function (p) { return !(p.parentId && inMod[p.parentId]); }).map(node);
        }
        function fromLayout(m) {
          var order = ['list', 'pda-list', 'form', 'wizard', 'pda-step', 'pda-scan', 'detail', 'dashboard'];
          var bucket = {};
          modulePages(m).forEach(function (p) {
            var k = p.layout || 'other';
            (bucket[k] = bucket[k] || []).push(p);
          });
          return order.filter(function (k) { return bucket[k]; }).map(function (k) {
            return {
              key: 'k-' + k, title: (KIND[k] || k) + '页',
              children: bucket[k].map(function (p) {
                return { key: 'p-' + p.id, title: p.title, page: p.id, children: [] };
              })
            };
          });
        }
        function treeOf(m) {
          if ((m.pageGroups || []).length) return m.pageGroups;
          var t = fromParentId(m);
          if (t.length && t.some(function (n) { return (n.children || []).length; })) return t;
          return fromLayout(m);
        }
        function pagesUnder(n) {
          var n2 = n.page ? 1 : 0;
          return n2 + (n.children || []).reduce(function (a, c) { return a + pagesUnder(c); }, 0);
        }
        function hasPage(n, pid) {
          if (n.page === pid) return true;
          return (n.children || []).some(function (c) { return hasPage(c, pid); });
        }
        function isOpen(m, n, depth) {
          var v = store.tocOpen[m.id + '/' + n.key];
          if (v !== undefined) return !!v;
          if (hasPage(n, store.pageId)) return true;   // 当前页所在分支一律展开
          if (n.collapsed !== undefined) return !n.collapsed;
          return depth < 1;                            // 一级展开，二级起收起
        }
        function goto(pid) {
          var t = pageOf(pid);
          if (!t) return;
          store.pageId = pid;
          store.pageState = 'default';
          store.entityStatus = defaultStatus(t);
          // 面板是覆盖在页面上的：跳完不收起来，就把目标页面又挡住了
          store.showToc = false;
          persist();
          refreshPins();
        }
        function row(m, n, depth) {
          var kids = n.children || [];
          var on = n.page && store.pageId === n.page;
          var open = kids.length ? isOpen(m, n, depth) : false;
          var cnt = kids.length ? pagesUnder(n) : 0;
          return h('div', { class: 'toc-node', key: n.key }, [
            h('div', {
              class: ['toc-item', depth > 0 ? 'is-kid' : '', on ? 'is-on' : '',
                      kids.length ? 'is-group' : '', n.page ? 'is-link' : ''],
              style: depth ? { paddingLeft: (14 + depth * 14) + 'px' } : null,
              onClick: function () {
                if (kids.length) {
                  store.tocOpen[m.id + '/' + n.key] = !open;
                  if (!n.page) return;
                }
                if (n.page) goto(n.page);
              }
            }, [
              kids.length
                ? h('span', { class: 'toc-caret' }, open ? '▾' : '▸')
                : h('span', { class: 'toc-dot' }, '·'),
              h('span', { class: 'toc-label' }, n.title || (pageOf(n.page) || {}).title || ''),
              kids.length ? h('span', { class: 'toc-count' }, cnt) : null,
              n.page ? h('span', { class: 'toc-badge' },
                String((pageOf(n.page) || {}).target || 'pc').toUpperCase()) : null
            ])
          ].concat(open ? [h('div', { class: 'toc-kids' },
            kids.map(function (c) { return row(m, c, depth + 1); }))] : []));
        }
        var mods = DATA.modules || [];
        var total = (DATA.pages || []).length;
        return h('aside', { class: 'overlay overlay-left' }, [
          h('div', { class: 'overlay-head' }, [
            h('div', { class: 'overlay-title' }, ['页面目录',
              h('span', { class: 'toc-total' }, total + ' 页')]),
            h('button', { class: 'icon-btn', onClick: function () { store.showToc = false; } }, '×')
          ]),
          h('div', { class: 'overlay-body' }, mods.map(function (m) {
            var tree = treeOf(m);
            return h('div', { class: 'toc-module', key: m.id }, [
              h('div', { class: 'toc-module-head' }, [
                h('span', null, m.code), h('span', null, m.name),
                h('span', { class: 'toc-count' }, modulePages(m).length)
              ]),
              tree.map(function (n) { return row(m, n, 0); })
            ]);
          }))
        ]);
      };
    }
  };

  var Popover = {
    name: 'Popover',
    setup: function () {
      return function () {
        var p = store.popover;
        if (!p) return null;
        var isNew = p.mode === 'new';
        var isResolve = p.mode === 'resolve';
        var meta = isNew ? (p.target && p.target.nodeLabel) : p.nodeId;
        if (isNew && p.target && p.target.carrier !== 'page') {
          meta = (meta || '') + '（弹层内）';
        }
        var W = 268;
        var vw = window.innerWidth || 1200;
        var vh = window.innerHeight || 800;
        var left = Math.min(Math.max(8, p.x + 14), vw - W - 12);
        var top = Math.min(Math.max(48, p.y - 18), vh - 190);
        return h('div', {
          class: ['annot-pop', isResolve ? 'is-resolve' : ''],
          style: { left: left + 'px', top: top + 'px' }
        }, [
          h('div', { class: 'annot-meta' }, [
            h('span', null, isNew ? '新标注' : (isResolve ? '标记完成' : '编辑标注')),
            meta ? h('code', { title: p.nodeId }, meta) : null
          ]),
          isResolve ? h('div', { class: 'annot-hint' }, '写清怎么改的。下一轮的人只能看到这句话，看不到你当时的想法。') : null,
          h('textarea', {
            placeholder: isResolve ? '例：操作列拆成「查看 / 处置 / 归档」，审核移到抽屉里'
              : '要改什么？一句话说清，能落地的那种',
            value: p.text,
            onInput: function (e) { p.text = e.target.value; }
          }),
          h('div', { class: 'annot-pop-actions' }, [
            h('button', { class: 'btn btn-sm', onClick: function () { store.popover = null; } }, '取消'),
            h('button', { class: 'btn btn-sm btn-primary', onClick: saveAnnotation }, isNew ? '保存' : (isResolve ? '存为已完成' : '保存'))
          ])
        ]);
      };
    }
  };

  /* 命令承载层：dialog 居中 / drawer 右侧。字段由 capabilities[].ui.fields 渲染，
     所以"要填什么"在契约里，不在组件里。 */
  var LayerPanel = {
    name: 'LayerPanel',
    setup: function () {
      return function () {
        var L = store.layer;
        if (!L) return null;
        var cap = capsById[L.capId] || {};
        var toLabel = cap.to ? (stateNameMap[cap.to] || cap.to) : '';
        var fromLabel = stateNames(cap.from);

        function field(f) {
          var v = L.values[f.key] == null ? '' : L.values[f.key];
          var err = L.errors[f.key];
          var onIn = function (e) { L.values[f.key] = e.target.value; delete L.errors[f.key]; };
          var ctl;
          if (f.type === 'readonly') {
            ctl = h('div', { class: 'ff-ro' }, v || '-');
          } else if (f.type === 'textarea') {
            ctl = h('textarea', { class: ['ff-input', err ? 'is-err' : ''], rows: 3, value: v, placeholder: f.placeholder || '', onInput: onIn });
          } else if (f.type === 'select' || f.type === 'user') {
            ctl = h('select', { class: ['ff-input', err ? 'is-err' : ''], value: v, onChange: onIn },
              (f.options || []).map(function (o) {
                return h('option', { key: o, value: o, selected: o === v }, o);
              }));
          } else if (f.type === 'radio') {
            ctl = h('div', { class: 'ff-radio' }, (f.options || []).map(function (o) {
              return h('label', { key: o, class: ['ff-r', v === o ? 'is-on' : ''] }, [
                h('input', { type: 'radio', checked: v === o, onChange: function () { L.values[f.key] = o; } }),
                o
              ]);
            }));
          } else {
            ctl = h('input', {
              class: ['ff-input', err ? 'is-err' : ''],
              type: f.type === 'number' ? 'number' : (f.type === 'date' ? 'date' : 'text'),
              value: v, placeholder: f.placeholder || '', onInput: onIn
            });
          }
          return h('label', {
            class: ['ff', f.span === 2 ? 'is-wide' : ''],
            key: f.key,
            'data-field': f.key || null,
            'data-site': L.capId,
            'data-page': ownsPageOf(L.capId),
            'data-node-id': 'layer:' + L.capId + ':' + f.key,
            'data-node-label': (L.title || '') + ' · ' + f.label
          }, [
            h('span', { class: 'ff-label' }, [f.label, f.required ? h('i', { class: 'ff-req' }, '*') : null]),
            ctl,
            err ? h('span', { class: 'ff-err' }, err) : (f.hint ? h('span', { class: 'ff-hint' }, f.hint) : null)
          ]);
        }

        return h('div', {
          class: 'layer-mask',
          onClick: function (e) { if (e.target.classList && e.target.classList.contains('layer-mask')) closeLayer(); }
        }, [
          h('div', {
            class: ['layer', 'layer-' + L.kind],
            style: { width: L.width + 'px' },
            onClick: function (e) { if (!annotClick(e)) fieldClick(e); }
          }, [
            h('div', { class: 'layer-head' }, [
              h('div', null, [
                h('div', {
                  class: 'layer-title',
                  'data-node-id': 'layer:' + L.capId + ':__title',
                  'data-node-label': '弹层标题「' + L.title + '」'
                }, L.title),
                h('div', {
                  class: 'layer-sub',
                  'data-node-id': 'layer:' + L.capId + ':__sub',
                  'data-node-label': '弹层副标题（命令/角色/状态迁移）'
                }, [
                  (cap.name || ''),
                  '　角色：' + ((cap.actor || []).map(actorName).join('、') || '不限'),
                  cap.from && cap.from.length ? '　' + fromLabel + ' → ' + toLabel : ''
                ])
              ]),
              h('button', { class: 'icon-btn', title: '关闭（Esc）', onClick: closeLayer }, '×')
            ]),
            h('div', { class: 'layer-body' },
              L.fields.length
                ? L.fields.map(field)
                : h('div', { class: 'layer-empty' }, (cap.ui && cap.ui.successText) || '这一步只做确认，确认后单据进入下一个状态。')),
            h('div', { class: 'layer-foot' }, [
              h('span', { class: 'layer-tip' }, 'Esc 关闭'),
              h('button', { class: 'btn', onClick: closeLayer }, '取消'),
              h('button', {
                class: 'btn btn-primary',
                'data-node-id': 'layer:' + L.capId + ':__submit',
                'data-node-label': '弹层主按钮「' + L.submitLabel + '」',
                onClick: submitLayer
              }, L.submitLabel)
            ])
          ])
        ]);
      };
    }
  };

  var Container = {
    name: 'Container',
    setup: function () {
      var stageRef = Vue.ref ? Vue.ref(null) : { value: null };

      function onStageClick(e) {
        if (annotClick(e)) return;
        // 命令按钮/行内操作自己有 onClick，冒泡到这里不重复处理
        if (e.target.closest('button') || e.target.closest('a')) return;
        // 字段标签：打开 PRD 并定位；输入控件内的点击不拦（R-12）
        if (fieldClick(e)) return;
        var el = e.target.closest('[data-node-id]');
        if (!el) return;
        var nid = el.getAttribute('data-node-id');
        var ix = interactionsOf(store.pageId).filter(function (x) { return x.on === nid; })[0];
        if (ix) runInteraction(ix);
      }

      function onKey(e) {
        if (e.key === 'Escape') {
          if (store.layer) { closeLayer(); return; }
          if (store.popover) { store.popover = null; return; }
          if (store.showToc) { store.showToc = false; return; }
          if (store.showPrd) { store.showPrd = false; store.prdFocus = ''; }
        }
      }

      Vue.onMounted && Vue.onMounted(function () {
        window.addEventListener('resize', refreshPins);
        window.addEventListener('keydown', onKey);
        document.querySelector('.canvas').addEventListener('scroll', refreshPins);
        refreshPins();
      });

      Vue.watch && Vue.watch(function () { return [store.pageId, store.pageState, store.entityStatus, store.showPrd, store.prdWidth, store.annotations.length, store.layer]; }, function () {
        refreshPins();
      });

      return function () {
        var pg = page.value;
        var stateChips = [
          { key: 'default', label: '默认' },
          { key: 'loading', label: '加载' },
          { key: 'empty', label: '空' },
          { key: 'zero-result', label: '零结果' },
          { key: 'error', label: '异常' }
        ];
        var sm = smByEntity[pg.entity];

        return h('div', { class: 'shell' }, [
          h('div', { class: 'shell-top' }, [
            h('div', { class: 'shell-brand' }, [
              h('div', { class: 'shell-brand-mark' }, String(DATA.meta.product || 'II').slice(0, 2)),
              h('div', null, [
                h('div', { class: 'shell-brand-name' }, DATA.meta.product),
                h('div', { class: 'shell-brand-sub' }, 'IIOT-PRD · ' + pg.title)
              ])
            ]),
            h('button', {
              class: ['tool-btn', store.showToc ? 'is-on' : ''],
              onClick: function () { store.showToc = !store.showToc; }
            }, '目录'),
            // 角色开关：不加这个，"执行人看不到验证按钮"这类四眼校验在容器里只能靠嘴说。
            // 第一项是"不限"，默认就是它——原型给一群人看，一进来就按岗位过滤会被当成按钮没做。
            (DATA.actors || []).length ? h('div', { class: 'chip-group' }, [
              h('span', { class: 'chip-group-label' }, '当前角色'),
              h('select', {
                class: 'chip',
                'data-role-switch': '1',
                style: { border: '0', background: 'transparent', paddingRight: '4px' },
                value: store.currentUser,
                onChange: function (e) { store.currentUser = e.target.value; persist(); }
              }, [h('option', { value: '', selected: !store.currentUser }, '全部角色（不限）')].concat(
                (DATA.actors || []).map(function (a) {
                  return h('option', { key: a.id, value: a.id, selected: a.id === store.currentUser }, actorName(a.id));
                })
              ))
            ]) : null,
            store.audit ? null : h('div', { class: 'chip-group' }, [h('span', { class: 'chip-group-label' }, '页面态')].concat(stateChips.map(function (c) {
              return h('button', {
                key: c.key,
                class: ['chip', store.pageState === c.key ? 'is-on' : ''],
                onClick: function () { store.pageState = c.key; }
              }, c.label);
            }))),
            sm && !store.audit ? h('div', { class: 'chip-group' }, [
              h('span', { class: 'chip-group-label' }, '单据状态'),
              h('select', {
                class: 'chip',
                'data-status-switch': '1',
                style: { border: '0', background: 'transparent', paddingRight: '4px' },
                value: store.entityStatus,
                onChange: function (e) { store.entityStatus = e.target.value; persist(); }
              }, (sm.states || []).map(function (s) {
                return h('option', { key: s.key, value: s.key, selected: s.key === store.entityStatus }, s.label);
              }))
            ]) : null,
            h('div', { class: 'shell-spacer' }),
            h('button', {
              class: ['tool-btn', store.annotMode ? 'is-on' : ''],
              onClick: function () { store.annotMode = !store.annotMode; store.popover = null; toast(store.annotMode ? '标注模式：点页面元素即可加标注' : '已退出标注模式'); }
            }, ['标注', h('span', { class: 'dot' })]),
            h('button', {
              class: ['tool-btn', store.audit ? 'is-on' : ''],
              onClick: function () { store.audit = !store.audit; store.annotMode = false; toast(store.audit ? '审核模式：已隐藏标注与过程控件' : '已退出审核模式'); }
            }, '审核'),
            h('button', {
              class: ['tool-btn', store.showPrd ? 'is-on' : ''],
              onClick: function () { store.showPrd = !store.showPrd; }
            }, 'PRD'),
            h('div', { style: { position: 'relative' } }, [
              h('button', { class: 'tool-btn', onClick: function () { store.showExport = !store.showExport; } }, '导出 ▾'),
              store.showExport ? h('div', {
                style: {
                  position: 'absolute', right: 0, top: '34px', background: '#fff',
                  border: '1px solid var(--line)', borderRadius: '8px', boxShadow: 'var(--shadow-2)',
                  padding: '4px', zIndex: 60, minWidth: '150px'
                }
              }, [
                h('div', { class: 'toc-item', onClick: exportMd }, 'PRD → Markdown'),
                h('div', { class: 'toc-item', onClick: exportHtml }, '当前页 → 单页 HTML'),
                h('div', { class: 'toc-item', onClick: exportPng }, '当前页 → PNG'),
                h('div', { class: 'toc-item', onClick: exportAnnot }, '标注 → 修改指令'),
                h('div', { class: 'toc-item', onClick: function () { window.print(); } }, '打印 / 存 PDF')
              ]) : null
            ]),
            h('button', {
              class: 'tool-btn',
              onClick: function () {
                // 连旧版本号的桶一起清，否则下次打开又被"迁移"回来
                bucketKeys().forEach(function (k) {
                  try { localStorage.removeItem(k); } catch (e) { /* 忽略 */ }
                });
                store.annotations = JSON.parse(JSON.stringify(DATA.annotations || []));
                store.prdEdits = {};
                store.currentUser = '';
                store.entityStatus = defaultStatus(page.value);
                store.pageState = 'default';
                toast('已重置为 AI 生成版本');
                refreshPins();
              }
            }, '重置')
          ]),
          h('div', { class: 'stage' }, [
            h('div', { id: 'stage', class: 'canvas' + (pg.target === 'pda' ? ' is-pda' : ''), onClick: onStageClick }, [
              renderNode(pg.componentTree)
            ]),
            store.showToc ? h(TocPanel) : null,
            store.showPrd && !store.audit ? h(PrdPanel) : null
          ]),
          h(LayerPanel),
          // pin 层在弹层之后渲染、在视口层级：弹框开着时标注照样能钉、能点开
          store.annotMode || !store.audit ? h('div', { class: 'annot-layer' }, store.pins.map(function (pin) {
            return h('div', {
              key: pin.id,
              class: ['annot-pin', pin.status === 'resolved' ? 'is-resolved' : ''],
              style: { left: pin.x + 'px', top: pin.y + 'px' },
              title: '标注 ' + pin.idx + (pin.status === 'resolved' ? '（已完成）' : ''),
              onClick: function (e) {
                e.stopPropagation();
                var a = store.annotations.filter(function (x) { return x.id === pin.id; })[0];
                store.showPrd = true;
                store.prdTab = 'annot';
                store.popover = {
                  mode: 'edit', id: a.id, nodeId: a.nodeId, text: a.body, anchor: a.anchor,
                  x: Math.min(pin.x + 24, (window.innerWidth || 1200) - 292), y: pin.y
                };
              }
            }, String(pin.idx));
          })) : null,
          h(Popover),
          store.toastMsg ? h('div', { class: 'toast-wrap' }, [h('div', { class: 'toast' }, store.toastMsg)]) : null
        ]);
      };
    }
  };

  window.__RD_TEST__ = {
    store: store,
    md: buildMd,
    can: window.RD.can,
    renderTree: function () { return page.value.componentTree; }
  };

  (Vue.createApp(Container)).mount('#app');
  refreshPins();

  // 标注锚点是相对坐标：字体加载、侧栏折叠、窗口缩放都会让位置漂移，统一在这里重算
  window.addEventListener('resize', refreshPins);
  if (window.ResizeObserver) {
    var stageEl = document.getElementById('stage');
    if (stageEl) new ResizeObserver(function () { refreshPins(); }).observe(stageEl);
  }
  requestAnimationFrame(function () {
    refreshPins();
    setTimeout(refreshPins, 250);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(refreshPins);
  });

  // 自检钩子：#test=1 时量一遍覆盖层是否挤压画布、表格是否横滚，结果写进 #selftest
  if (/test=1/.test(location.hash)) {
    setTimeout(function () {
      var canvas = document.getElementById('stage');
      var w0 = canvas.offsetWidth;
      store.showToc = true;
      store.showPrd = true;
      nextTick(function () {
        var w1 = canvas.offsetWidth;
        var wrap = document.querySelector('.table-wrap');
        var out = {
          canvasClosed: w0,
          canvasOpen: w1,
          notSqueezed: w0 === w1,
          rows: document.querySelectorAll('.dt-row').length,
          hScroll: wrap ? (wrap.scrollWidth > wrap.clientWidth) : null,
          pins: document.querySelectorAll('.annot-pin').length,
          sider: document.querySelector('.app-sider') ? document.querySelector('.app-sider').offsetWidth : null
        };
        var d = document.createElement('div');
        d.id = 'selftest';
        d.textContent = JSON.stringify(out);
        document.body.appendChild(d);
      });
    }, 250);
  }

  // 导出钩子：#export=md / #export=html 时把结果写进 DOM，供脚本抓取做三处一致校验
  if (/export=/.test(location.hash)) {
    var kind = (location.hash.match(/export=([a-z]+)/) || [])[1];
    setTimeout(function () {
      var pre = document.createElement('pre');
      pre.id = 'export-out';
      try {
        pre.textContent = kind === 'html'
          ? (document.querySelector('#stage .app') || {}).outerHTML || ''
          : buildMd();
      } catch (err) {
        pre.textContent = 'ERROR: ' + (err && err.message);
      }
      document.body.appendChild(pre);
    }, 300);
  }
})();
