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

  var DATA = window.__PROTO__;
  var KEY = 'iiot:' + DATA.meta.product + ':' + DATA.meta.version;
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { saved = {}; }

  var capsById = {};
  (DATA.capabilities || []).forEach(function (c) { capsById[c.id] = c; });
  var smByEntity = {};
  (DATA.stateMachines || []).forEach(function (s) { smByEntity[s.entity] = s; });

  var hashPage = (location.hash.match(/page=([A-Za-z0-9_-]+)/) || [])[1];
  var hashStatus = (location.hash.match(/status=([A-Za-z0-9_-]+)/) || [])[1];
  function defaultStatus(pg) { return pg && pg.target === 'pda' ? 'created' : 'reported'; }
  var initialPageId = hashPage || saved.pageId || DATA.meta.currentPageId || DATA.pages[0].id;
  var initialPage = DATA.pages.filter(function (x) { return x.id === initialPageId; })[0] || DATA.pages[0];
  var store = reactive({
    pageId: initialPageId,
    pageState: 'default',
    entityStatus: hashStatus || saved.entityStatus || defaultStatus(initialPage),
    filters: {},
    pdaQty: 0,
    selectedRow: null,
    showToc: /toc=1/.test(location.hash),
    showPrd: /prd=1/.test(location.hash),
    prdTab: 'page',
    prdWidth: 500,
    annotMode: false,
    audit: false,
    showExport: false,
    annotations: saved.annotations || JSON.parse(JSON.stringify(DATA.annotations || [])),
    prdEdits: saved.prdEdits || {},
    pins: [],
    popover: null,
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
        annotations: store.annotations,
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

  window.RD = {
    state: store,
    data: DATA,
    can: function (capId) {
      var cap = capsById[capId];
      if (!cap) return { ok: true };
      if ((cap.from || []).length && (cap.from || []).indexOf(store.entityStatus) < 0) {
        var sm = smByEntity[cap.entity] || { states: [] };
        var cur = (sm.states || []).filter(function (x) { return x.key === store.entityStatus; })[0];
        var label = cur ? cur.label : store.entityStatus;
        return { ok: false, reason: (cap.reason || '当前状态不可用') + '（当前为「' + label + '」）' };
      }
      return { ok: true };
    },
    entityStatus: function () { return store.entityStatus; },
    pageState: function () { return store.pageState; },
    toast: toast,
    action: function (key, text, row) {
      if (key === 'approve') {
        store.entityStatus = 'approved';
        persist();
        toast('「' + (row ? row.batchNo : '本批') + '」已审核，状态置为已归档');
        return;
      }
      if (key === 'export') { toast('已按当前筛选导出 ' + (store.pageState === 'zero-result' ? 0 : 10) + ' 条'); return; }
      if (key === 'submit') {
        if (store.pdaQty <= 0) { toast('请先填写取样数量'); return; }
        store.entityStatus = 'sampled';
        persist();
        toast('取样已提交：' + store.pdaQty + ' 件 · 已进入待审核');
        return;
      }
      toast((text || key) + (row ? '：' + row.batchNo : '') + '（原型演示）');
    },
    search: function (key) {
      if (key !== 'search') { store.filters = {}; store.pageState = 'default'; toast('已重置查询条件'); return; }
      store.pageState = store.filters.batchNo || store.filters.taskNo || store.filters.supplier ? 'zero-result' : 'default';
      toast(store.pageState === 'zero-result' ? '查询完成：0 条' : '查询完成：9407 条');
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
    selectRow: function (row) { store.selectedRow = row; },
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
    var props = { p: node.props || {}, 'data-node-id': node.id };
    if (!known) props.type = node.type;
    var kids = (node.children || []).map(renderNode).filter(Boolean);
    if (kids.length) return h(C, props, { default: function () { return kids; } });
    return h(C, props);
  }

  /* ---------------- 标注 ---------------- */
  function refreshPins() {
    nextTick(function () {
      var stage = document.getElementById('stage');
      if (!stage) return;
      var base = stage.getBoundingClientRect();
      var out = [];
      store.annotations.filter(function (a) { return a.pageId === store.pageId && a.status !== 'deleted'; })
        .forEach(function (a) {
          var el = stage.querySelector('[data-node-id="' + a.nodeId + '"]');
          if (!el) return;
          var r = el.getBoundingClientRect();
          out.push({
            id: a.id,
            idx: store.annotations.filter(function (x) { return x.pageId === store.pageId; }).indexOf(a) + 1,
            x: r.left - base.left + r.width * a.anchor.x,
            y: r.top - base.top + r.height * a.anchor.y,
            status: a.status
          });
        });
      store.pins = out;
    });
  }

  function addAnnotation(nodeId, evt) {
    var stage = document.getElementById('stage');
    var el = stage.querySelector('[data-node-id="' + nodeId + '"]');
    var r = el.getBoundingClientRect();
    var base = stage.getBoundingClientRect();
    var ax = Math.min(0.98, Math.max(0.02, (evt.clientX - r.left) / r.width));
    var ay = Math.min(0.98, Math.max(0.02, (evt.clientY - r.top) / r.height));
    store.popover = {
      mode: 'new', nodeId: nodeId,
      x: evt.clientX - base.left, y: evt.clientY - base.top,
      text: '', anchor: { x: ax, y: ay }
    };
  }

  function saveAnnotation() {
    var p = store.popover;
    if (!p || !p.text.trim()) { toast('先写一句要改什么'); return; }
    if (p.mode === 'new') {
      var seq = store.annotations.length + 1;
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
        affects: ['componentTree']
      });
      toast('标注已加，点「标注」可导出成修改指令');
    } else {
      var a = store.annotations.filter(function (x) { return x.id === p.id; })[0];
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
      L.push('## 5 标注（待处理）');
      L.push('');
      store.annotations.filter(function (a) { return a.status === 'open'; }).forEach(function (a) {
        L.push('- `' + a.nodeId + '` ' + a.body);
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
    var list = store.annotations.filter(function (a) { return a.status === 'open'; });
    var L = ['# 原型修改指令（' + page.value.title + '）', ''];
    list.forEach(function (a, i) {
      L.push((i + 1) + '. 节点 `' + a.nodeId + '`：' + a.body);
    });
    if (!list.length) L.push('（无待处理标注）');
    download('修改指令-' + page.value.title + '.md', L.join('\n'), 'text/markdown;charset=utf-8');
    toast('已导出修改指令');
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
            })
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
          var list = store.annotations.filter(function (a) { return a.pageId === store.pageId; });
          body = h('div', { class: 'prd-body' }, [
            h('div', { class: 'prd-h1' }, '标注（' + list.length + '）'),
            h('div', { class: 'prd-sub' }, '点画布右上「标注」，再点页面元素即可添加；导出后可直接作为下一轮修改指令'),
            h('div', { class: 'annot-list' }, list.map(function (a, i) {
              return h('div', { class: ['annot-card', a.status === 'resolved' ? 'is-resolved' : ''], key: a.id }, [
                h('div', { class: 'annot-card-top' }, [
                  h('div', { class: 'annot-idx' }, String(i + 1)),
                  h('span', { class: 'annot-node' }, a.nodeId),
                  h('span', { style: { marginLeft: 'auto', fontSize: '10px', color: a.status === 'open' ? 'var(--warn-600)' : 'var(--ok-600)' } }, a.status === 'open' ? '待处理' : '已解决')
                ]),
                h('div', { class: 'annot-body' }, a.body),
                h('div', { class: 'annot-actions' }, [
                  h('a', { onClick: function () { a.status = a.status === 'open' ? 'resolved' : 'open'; persist(); refreshPins(); } }, a.status === 'open' ? '标记已解决' : '重新打开'),
                  h('a', { onClick: function () {
                    store.popover = { mode: 'edit', id: a.id, nodeId: a.nodeId, x: 120, y: 120, text: a.body, anchor: a.anchor };
                  } }, '编辑')
                ])
              ]);
            })),
            h('div', { style: { marginTop: '10px' } }, [
              h('button', { class: 'btn', onClick: exportAnnot }, '导出修改指令')
            ])
          ]);
        }

        return h('aside', { class: 'overlay overlay-right', style: { width: store.prdWidth + 'px' } }, [
          h('div', { class: 'overlay-grip', onMousedown: startDrag, title: '拖动调宽' }),
          h('div', { class: 'overlay-head' }, [
            h('div', { class: 'overlay-title' }, 'PRD'),
            h('button', { class: 'icon-btn', onClick: function () { store.showPrd = false; } }, '×')
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
        return h('aside', { class: 'overlay overlay-left' }, [
          h('div', { class: 'overlay-head' }, [
            h('div', { class: 'overlay-title' }, '页面目录'),
            h('button', { class: 'icon-btn', onClick: function () { store.showToc = false; } }, '×')
          ]),
          h('div', { class: 'overlay-body' }, DATA.modules.map(function (m) {
            return h('div', { class: 'toc-module', key: m.id }, [
              h('div', { class: 'toc-module-head' }, [h('span', null, m.code), h('span', null, m.name)]),
              (m.pages || []).map(function (pid) {
                var p = DATA.pages.filter(function (x) { return x.id === pid; })[0];
                if (!p) return null;
                return h('div', {
                  key: pid,
                  class: ['toc-item', store.pageId === pid ? 'is-on' : ''],
                  onClick: function () { store.pageId = pid; store.pageState = 'default'; store.entityStatus = defaultStatus(DATA.pages.filter(function (x) { return x.id === pid; })[0]); persist(); refreshPins(); }
                }, [
                  h('span', null, p.title),
                  h('span', { class: 'toc-badge' }, p.target.toUpperCase())
                ]);
              })
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
        return h('div', {
          class: 'annot-pop',
          style: { left: Math.min(p.x, 600) + 'px', top: Math.max(8, p.y - 20) + 'px' }
        }, [
          h('div', { class: 'annot-meta' }, [h('span', null, p.mode === 'new' ? '新标注' : '编辑标注'), h('code', null, p.nodeId)]),
          h('textarea', {
            placeholder: '要改什么？一句话说清，能落地的那种',
            value: p.text,
            onInput: function (e) { p.text = e.target.value; }
          }),
          h('div', { class: 'annot-pop-actions' }, [
            h('button', { class: 'btn btn-sm', onClick: function () { store.popover = null; } }, '取消'),
            h('button', { class: 'btn btn-sm btn-primary', onClick: saveAnnotation }, '保存')
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
        if (!store.annotMode) return;
        if (e.target.closest('.annot-pop') || e.target.closest('.annot-pin')) return;
        var el = e.target.closest('[data-node-id]');
        if (!el) { store.popover = null; return; }
        addAnnotation(el.getAttribute('data-node-id'), e);
      }

      Vue.onMounted && Vue.onMounted(function () {
        window.addEventListener('resize', refreshPins);
        document.querySelector('.canvas').addEventListener('scroll', refreshPins);
        refreshPins();
      });

      Vue.watch && Vue.watch(function () { return [store.pageId, store.pageState, store.entityStatus, store.showPrd, store.prdWidth, store.annotations.length]; }, function () {
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
              h('div', { class: 'shell-brand-mark' }, 'IQ'),
              h('div', null, [
                h('div', { class: 'shell-brand-name' }, DATA.meta.product),
                h('div', { class: 'shell-brand-sub' }, 'IIOT-PRD · ' + pg.title)
              ])
            ]),
            h('button', {
              class: ['tool-btn', store.showToc ? 'is-on' : ''],
              onClick: function () { store.showToc = !store.showToc; }
            }, '目录'),
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
                localStorage.removeItem(KEY);
                store.annotations = JSON.parse(JSON.stringify(DATA.annotations || []));
                store.prdEdits = {};
                store.entityStatus = 'reported';
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
            store.annotMode || !store.audit ? h('div', { class: 'annot-layer' }, store.pins.map(function (pin) {
              return h('div', {
                key: pin.id,
                class: ['annot-pin', pin.status === 'resolved' ? 'is-resolved' : ''],
                style: { left: pin.x + 'px', top: pin.y + 'px' },
                onClick: function (e) {
                  e.stopPropagation();
                  var a = store.annotations.filter(function (x) { return x.id === pin.id; })[0];
                  store.showPrd = true;
                  store.prdTab = 'annot';
                  store.popover = { mode: 'edit', id: a.id, nodeId: a.nodeId, x: pin.x + 24, y: pin.y, text: a.body, anchor: a.anchor };
                }
              }, String(pin.idx));
            })) : null,
            store.showToc ? h(TocPanel) : null,
            store.showPrd && !store.audit ? h(PrdPanel) : null,
            h(Popover)
          ]),
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
