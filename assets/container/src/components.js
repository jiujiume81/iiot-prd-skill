/*!
 * IIOT-PRD 组件库（渲染层）
 * 每个组件输出的是可交付 DOM：语义 class + 设计令牌，开发可直接搬进工程。
 * 组件签名统一：{ p: 节点 props, node: 原始节点 }，避免把业务字段摊平成无数 prop。
 */
(function () {
  var h = Vue.h;

  function can(capId) {
    if (!capId) return { ok: true };
    return window.RD.can(capId);
  }

  function statusTone(text) {
    var t = String(text || '');
    if (/已审核|已归档|合格|通过/.test(t)) return 'tag-success';
    if (/待审核|待取样|待处理|超期/.test(t)) return 'tag-warning';
    if (/驳回|不合格|异常|失败/.test(t)) return 'tag-danger';
    if (/已取样|进行中|处理中/.test(t)) return 'tag-info';
    return '';
  }

  var AppShell = {
    name: 'AppShell',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props, ctx) {
      return function () {
        var p = props.p || {};
        var brand = p.brand || {};
        var header = p.header || {};
        var collapsed = !!p.siderCollapsed;
        var groups = p.groups || [];

        var siderChildren = [
          h('div', { class: 'app-sider-head' }, [
            h('div', { class: 'app-logo' }, 'NQ'),
            collapsed ? null : h('div', null, [
              h('div', { class: 'app-sider-name' }, brand.name || ''),
              h('div', { class: 'app-sider-sub' }, brand.sub || '')
            ])
          ]),
          collapsed ? null : h('div', { class: 'app-search' }, [
            h('span', { style: { fontSize: '12px' } }, '⌕'),
            h('span', null, p.search || '菜单搜索')
          ]),
          h('div', { class: 'app-nav' }, groups.map(function (g) {
            return h('div', { class: 'nav-group', key: g.title }, [
              collapsed ? null : h('div', { class: 'nav-group-title' }, g.title),
              (g.items || []).map(function (it) {
                return h('div', {
                  key: it.key,
                  class: ['nav-item', it.on ? 'is-on' : ''],
                  title: collapsed ? it.label : null
                }, [
                  collapsed ? h('span', { style: { fontSize: '11px', opacity: '0.7' } }, (it.label || '').slice(0, 1)) : null,
                  collapsed ? null : h('span', null, it.label),
                  !collapsed && it.count ? h('span', { class: 'nav-count num' }, it.count) : null
                ]);
              })
            ]);
          }))
        ];

        return h('div', { class: 'app' }, [
          h('aside', { class: ['app-sider', collapsed ? 'is-collapsed' : ''] }, siderChildren),
          h('div', { class: 'app-main' }, [
            h('header', { class: 'app-header' }, [
              h('div', { class: 'app-title' }, header.title || ''),
              h('div', { class: 'app-crumb' }, (header.crumb || []).map(function (c, i) {
                return h('span', { key: i, style: { display: 'inline-flex', gap: '6px', alignItems: 'center' } }, [
                  i ? h('i', null, '/') : null,
                  h('span', null, c)
                ]);
              })),
              h('div', { class: 'header-actions' }, [
                (header.actions || []).map(function (a, i) {
                  return h('button', { class: 'hdr-btn', key: 'a' + i }, a);
                }),
                h('div', { class: 'user-pill' }, [
                  h('div', { class: 'avatar' }, (header.user || '?').slice(0, 1)),
                  h('span', null, header.user || '')
                ])
              ])
            ]),
            ctx.slots.default ? ctx.slots.default() : null
          ])
        ]);
      };
    }
  };

  var PageShell = {
    name: 'PageShell',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props, ctx) {
      return function () {
        return h('div', { class: 'page' }, ctx.slots.default ? ctx.slots.default() : []);
      };
    }
  };

  var TabStrip = {
    name: 'TabStrip',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        return h('div', { class: 'tabstrip' }, (p.tabs || []).map(function (t) {
          var on = t.key === p.activeKey;
          return h('div', {
            key: t.key,
            class: ['tab', on ? 'is-on' : ''],
            onClick: function () { window.RD.toast('切换页签：' + t.label); }
          }, [
            h('span', null, t.label),
            t.closable ? h('span', { class: 'tab-x' }, '×') : null
          ]);
        }));
      };
    }
  };

  var FilterBar = {
    name: 'FilterBar',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var fields = (p.fields || []).map(function (f) {
          return h('div', { class: 'field', key: f.key }, [
            h('label', { class: 'field-label' }, f.label),
            h('input', {
              class: 'input',
              placeholder: f.placeholder || '请输入',
              value: (window.RD.state.filters || {})[f.key] || '',
              onInput: function (e) { window.RD.state.filters[f.key] = e.target.value; }
            })
          ]);
        });
        var acts = (p.actions || []).map(function (a) {
          return h('button', {
            key: a.key,
            class: ['btn', a.variant === 'primary' ? 'btn-primary' : (a.variant === 'ghost' ? 'btn-ghost' : '')],
            onClick: function () { window.RD.search(a.key); }
          }, a.text);
        });
        return h('div', { class: 'filter' }, [
          h('div', { class: 'filter-fields' }, fields),
          h('div', { class: 'filter-actions' }, acts)
        ]);
      };
    }
  };

  var StatusBar = {
    name: 'StatusBar',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var steps = p.steps || [];
        var curKey = window.RD.entityStatus();
        var curIdx = -1;
        steps.forEach(function (s, i) { if (s.key === curKey) curIdx = i; });

        var nodes = [];
        steps.forEach(function (s, i) {
          var cls = i < curIdx ? 'is-done' : (i === curIdx ? 'is-cur' : '');
          nodes.push(h('div', { class: ['sf-step', cls], key: s.key }, [
            h('div', { class: 'sf-dot' }),
            h('span', { class: 'sf-label' }, s.label)
          ]));
          if (i < steps.length - 1) nodes.push(h('div', { class: 'sf-bar', key: 'b' + i }));
        });

        return h('div', { class: 'statusbar' }, [
          h('span', { style: { color: 'var(--text-3)' } }, '单据状态'),
          h('div', { class: 'status-flow' }, nodes),
          h('span', { style: { marginLeft: 'auto', color: 'var(--text-3)' } }, p.note || '')
        ]);
      };
    }
  };

  var ToolBar = {
    name: 'ToolBar',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var actions = (p.actions || []).map(function (a) {
          var c = can(a.capability);
          var dis = a.capability && !c.ok;
          return h('button', {
            key: a.key,
            class: ['btn', a.variant === 'primary' ? 'btn-primary' : (a.variant === 'ghost' ? 'btn-ghost' : ''), dis ? 'is-disabled' : ''],
            title: dis ? c.reason : null,
            onClick: function () {
              if (dis) { window.RD.toast(c.reason); return; }
              window.RD.action(a.key, a.text);
            }
          }, [
            a.text,
            dis ? h('span', { class: 'hint-dot', title: c.reason }, '!') : null
          ]);
        });
        return h('div', { class: 'toolbar' }, actions.concat([
          h('div', { class: 'toolbar-right' }, [
            h('span', { class: 'sel-info' }, ['已选 ', h('b', null, String(p.selected || 0)), ' 项']),
            h('span', { style: { color: 'var(--line)' } }, '|'),
            h('span', { class: 'link-more' }, '列设置')
          ])
        ]));
      };
    }
  };

  function cellRender(col, row, i) {
    if (col.type === 'index') return h('div', { class: 'dt-cell is-idx num' }, String(i + 1));
    if (col.type === 'num') return h('div', { class: 'dt-cell is-num num' }, String(row[col.key] == null ? '-' : row[col.key]));
    if (col.type === 'tag') {
      var txt = row[col.key];
      return h('div', { class: 'dt-cell' }, [h('span', { class: ['tag', 'is-dot', statusTone(txt)] }, txt)]);
    }
    if (col.type === 'action') {
      var links = (col.actions || []).map(function (a) {
        var c = can(a.capability);
        var dis = a.capability && !c.ok;
        return h('a', {
          key: a.key,
          class: dis ? 'is-off' : '',
          title: dis ? c.reason : null,
          onClick: function () {
            if (dis) { window.RD.toast(c.reason); return; }
            window.RD.action(a.key, a.text, row);
          }
        }, a.text);
      });
      return h('div', { class: 'dt-cell is-act' }, links);
    }
    return h('div', { class: 'dt-cell', title: row[col.key] }, row[col.key] == null ? '-' : String(row[col.key]));
  }

  var StateBlock = {
    name: 'StateBlock',
    props: { kind: String, title: String, desc: String, hint: String, actions: Array },
    setup: function (props) {
      return function () {
        return h('div', { class: 'state-block' }, h('div', { class: 'state-inner' }, [
          h('div', { class: 'state-ico' }, props.kind === 'error' ? '!' : (props.kind === 'zero-result' ? '⌕' : '□')),
          h('div', { class: 'state-title' }, props.title || ''),
          h('div', { class: 'state-desc' }, props.desc || ''),
          h('div', null, (props.actions || []).map(function (a, i) {
            return h('button', {
              key: i,
              class: ['btn', i === 0 ? 'btn-primary' : ''],
              onClick: function () { window.RD.stateAction(a.key); }
            }, a.text);
          })),
          props.hint ? h('div', { class: 'state-hint' }, props.hint) : null
        ]));
      };
    }
  };

  var DataTable = {
    name: 'DataTable',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var cols = p.columns || [];
        var tpl = cols.map(function (c) { return (c.width || 120) + 'px'; }).join(' ');
        var minW = cols.reduce(function (s, c) { return s + (c.width || 120); }, 0);
        var ps = window.RD.pageState();
        var rows = p.data || [];

        var head = h('div', { class: 'dt-head', style: { gridTemplateColumns: tpl } },
          cols.map(function (c) {
            return h('div', { class: ['dt-cell', c.align === 'right' ? 'is-num' : ''], key: c.key, title: c.title }, c.title);
          }));

        var body;
        if (ps === 'loading') {
          body = h('div', null, Array.from({ length: 8 }).map(function (_, r) {
            return h('div', { class: 'dt-row', key: 'sk' + r, style: { gridTemplateColumns: tpl } },
              cols.map(function (c, ci) {
                return h('div', { class: 'dt-cell', key: ci }, [
                  h('div', { class: 'sk sk-line', style: { width: (40 + ((r * 7 + ci * 13) % 50)) + '%' } })
                ]);
              }));
          }));
        } else if (ps === 'empty') {
          body = h(StateBlock, {
            kind: 'empty',
            title: '还没有来料检验报告',
            desc: '当前系统内没有任何到货批次。先发起检验申请，取样完成后报告会自动出现在这里。',
            hint: '数据来源：QMS 来料检验 · 与 PDA 取样任务同源',
            actions: [{ key: 'create', text: '发起申请' }]
          });
        } else if (ps === 'zero-result') {
          body = h(StateBlock, {
            kind: 'zero-result',
            title: '没有符合条件的报告',
            desc: '已按「到货单号 / 任务单号 / 供应商 / 物资名称」筛选，共 0 条。试试放宽时间范围，或只保留一个条件。',
            hint: '查询条件已保留，不会因为切换状态丢失',
            actions: [{ key: 'clear', text: '清空条件' }]
          });
        } else if (ps === 'error') {
          body = h(StateBlock, {
            kind: 'error',
            title: '报告列表加载失败',
            desc: '接口返回 500（trace: iqc-report-7f3a）。已保留查询条件，重试不会重新填一遍。',
            hint: '若持续失败，请联系质量系统管理员',
            actions: [{ key: 'retry', text: '重新加载' }, { key: 'offline', text: '导出上次结果' }]
          });
        } else {
          body = h('div', null, rows.map(function (row, i) {
            return h('div', {
              class: 'dt-row',
              key: row[p.rowKey] ? row[p.rowKey] + '_' + i : i,
              style: { gridTemplateColumns: tpl },
              onClick: function (e) {
                if (e.target.tagName === 'A') return;
                window.RD.selectRow(row);
              }
            }, cols.map(function (c, ci) {
              var cell = cellRender(c, row, i);
              cell.key = 'c' + ci;
              return cell;
            }));
          }));
        }

        return h('div', { class: 'table-wrap' }, [
          h('div', { class: 'dt', style: { minWidth: minW + 'px' } }, [head, body])
        ]);
      };
    }
  };

  var Pager = {
    name: 'Pager',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var pages = p.pages || 1;
        var cur = p.current || 1;
        var nums = [1, 2, 3, 4, 5];
        var kids = [
          h('span', { class: 'num' }, cur + '/' + pages),
          h('span', { style: { color: 'var(--line)' } }, '|'),
          h('span', null, ['共 ', h('b', { class: 'num', style: { fontWeight: 500, color: 'var(--text-1)' } }, String(p.total || 0)), ' 项']),
          h('span', null, ['每页显示 ', h('select', { class: 'page-size' }, [10, 20, 50].map(function (n) {
            return h('option', { key: n, value: n, selected: n === p.pageSize }, String(n));
          }))]),
          h('div', { class: 'pager' }, [
            h('button', { class: 'pg', onClick: function () { window.RD.toast('上一页'); } }, '‹'),
            nums.map(function (n) { return h('button', { key: n, class: ['pg', n === cur ? 'is-on' : ''], onClick: function () { window.RD.toast('第 ' + n + ' 页'); } }, String(n)); }),
            h('span', { class: 'pg is-dots' }, '…'),
            h('button', { class: 'pg', onClick: function () { window.RD.toast('末页'); } }, String(pages)),
            h('button', { class: 'pg', onClick: function () { window.RD.toast('下一页'); } }, '›'),
            h('span', { class: 'pg-jump' }, ['跳转至', h('input', { class: 'num' }), '页'])
          ])
        ];
        return h('div', { class: 'footer' }, kids);
      };
    }
  };

  /* ---------------- 展示与统计 ---------------- */
  var SectionCard = {
    name: 'SectionCard',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props, ctx) {
      return function () {
        var p = props.p || {};
        var head = (p.title || p.extra || p.sub) ? h('header', { class: 'sec-head' }, [
          h('h3', { class: 'sec-title' }, p.title || ''),
          p.sub ? h('span', { class: 'sec-sub' }, p.sub) : null,
          p.extra ? h('span', { class: 'sec-extra' }, p.extra) : null
        ]) : null;
        var bodyStyle = p.cols ? { display: 'grid', gridTemplateColumns: 'repeat(' + p.cols + ', minmax(0,1fr))', gap: (p.gap || 12) + 'px' } : null;
        return h('section', { class: 'sec-card' }, [
          head,
          h('div', { class: ['sec-body', p.pad === false ? 'is-flush' : ''], style: bodyStyle },
            ctx.slots.default ? ctx.slots.default() : null)
        ]);
      };
    }
  };

  var Grid = {
    name: 'Grid',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props, ctx) {
      return function () {
        var p = props.p || {};
        var cols = p.cols || 2;
        return h('div', {
          class: 'grid-c',
          style: { gridTemplateColumns: 'repeat(' + cols + ', minmax(0,1fr))', gap: (p.gap || 12) + 'px' }
        }, ctx.slots.default ? ctx.slots.default() : null);
      };
    }
  };

  // 指标条：只用于统计页，列表页顶部不放（catalog 有明确约定）
  var StatStrip = {
    name: 'StatStrip',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var items = p.items || [];
        var ps = window.RD.pageState();
        if (ps === 'loading') {
          return h('div', { class: 'stat-strip' }, (items.length ? items : [1, 2, 3, 4]).map(function (_, i) {
            return h('div', { class: 'stat-item', key: i }, [
              h('div', { class: 'sk sk-line', style: { width: '46%' } }),
              h('div', { class: 'sk sk-line', style: { width: '64%', height: '20px', marginTop: '8px' } })
            ]);
          }));
        }
        if (ps === 'empty' || !items.length) {
          return h('div', { class: 'stat-strip' }, [
            h('div', { class: 'stat-item is-empty' }, '暂无指标（数据源未接入）')
          ]);
        }
        return h('div', { class: 'stat-strip', style: { gridTemplateColumns: 'repeat(' + Math.min(items.length, 6) + ', minmax(0,1fr))' } },
          items.map(function (it) {
            return h('div', { class: ['stat-item', it.on ? 'is-on' : ''], key: it.key }, [
              h('div', { class: 'stat-label' }, it.label),
              h('div', { class: 'stat-value' }, [
                h('span', null, String(it.value)),
                it.unit ? h('span', { class: 'stat-unit' }, it.unit) : null
              ]),
              it.note ? h('div', { class: 'stat-note' }, it.note) : null
            ]);
          }));
      };
    }
  };

  var KpiCard = {
    name: 'KpiCard',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var ps = window.RD.pageState();
        if (ps === 'loading') {
          return h('div', { class: 'kpi' }, [
            h('div', { class: 'sk sk-line', style: { width: '50%' } }),
            h('div', { class: 'sk sk-line', style: { width: '70%', height: '26px', marginTop: '10px' } })
          ]);
        }
        if (ps === 'empty' || p.value == null) {
          return h('div', { class: 'kpi is-empty' }, [h('div', { class: 'kpi-label' }, p.label || ''), h('div', { class: 'kpi-empty' }, '—')]);
        }
        // 涨跌配色：默认“涨红跌绿”（中国习惯）；positiveIsGood 时反色，因为“合格率上升”不该标红
        var d = typeof p.delta === 'number' ? p.delta : null;
        var good = p.positiveIsGood ? (d > 0) : (d < 0);
        var tone = p.tone || (d == null || d === 0 ? 'flat' : (good ? 'good' : 'bad'));
        return h('div', {
          class: ['kpi', p.href ? 'is-link' : ''],
          onClick: p.href ? function () { window.RD.goto(p.href, p.hrefLabel); } : null
        }, [
          h('div', { class: 'kpi-label' }, p.label || ''),
          h('div', { class: 'kpi-value' }, [
            h('span', null, String(p.value)),
            p.unit ? h('span', { class: 'kpi-unit' }, p.unit) : null
          ]),
          d == null ? null : h('div', { class: ['kpi-delta', 'is-' + tone] }, [
            h('span', { class: 'kpi-arrow' }, d > 0 ? '↑' : (d < 0 ? '↓' : '—')),
            h('span', null, Math.abs(d) + (p.deltaUnit || '%')),
            p.deltaLabel ? h('span', { class: 'kpi-delta-label' }, p.deltaLabel) : null
          ]),
          p.foot ? h('div', { class: 'kpi-foot' }, p.foot) : null
        ]);
      };
    }
  };

  // 轻量 SVG 图表：不引第三方库，避免单文件体积失控
  var Chart = {
    name: 'Chart',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var ps = window.RD.pageState();
        var W = 720, H = p.height || 260;

        if (ps === 'loading') return h('div', { class: 'chart is-skeleton' }, [h('div', { class: 'sk sk-block' })]);
        if (ps === 'error') {
          return h('div', { class: 'chart-empty' }, '图表数据加载失败（接口返回 500），已保留筛选条件');
        }
        var xs = p.xAxis || [];
        var series = (p.series || []).filter(function (s) { return s && (s.data || []).length; });
        if (!series.length || !xs.length) {
          return h('div', { class: 'chart-empty' }, p.emptyText || '暂无数据：所选时间范围内没有检验记录');
        }

        var PL = 48, PR = 18, PT = 16, PB = 32;
        var iw = W - PL - PR, ih = H - PT - PB;
        var vals = [];
        series.forEach(function (s) { s.data.forEach(function (v) { if (typeof v === 'number') vals.push(v); }); });
        var lim = p.limits || {};
        [lim.ucl, lim.lcl, lim.center].forEach(function (v) { if (typeof v === 'number') vals.push(v); });
        var max = Math.max.apply(null, vals), min = Math.min.apply(null, vals);
        if (p.yMin != null) min = p.yMin;
        if (p.yMax != null) max = p.yMax;
        var span = max - min || 1;
        max += span * 0.1; min = Math.max(p.yMin != null ? p.yMin : -Infinity, min - span * 0.1);
        span = max - min || 1;

        function X(i) { return PL + (xs.length === 1 ? iw / 2 : (iw * i) / (xs.length - 1)); }
        function Y(v) { return PT + ih - ((v - min) / span) * ih; }

        var kids = [];
        // 网格与 Y 轴刻度
        var ticks = 4;
        for (var t = 0; t <= ticks; t++) {
          var v = min + (span * t) / ticks;
          var y = Y(v);
          kids.push(h('line', { class: 'ch-grid', x1: PL, y1: y, x2: W - PR, y2: y }));
          kids.push(h('text', { class: 'ch-tick', x: PL - 8, y: y + 4, 'text-anchor': 'end' }, (Math.round(v * 10) / 10) + (p.yUnit || '')));
        }
        // X 轴标签（最多 8 个，避免重叠）
        var step = Math.max(1, Math.ceil(xs.length / 8));
        xs.forEach(function (x, i) {
          if (i % step) return;
          kids.push(h('text', { class: 'ch-tick', x: X(i), y: H - 10, 'text-anchor': 'middle' }, String(x)));
        });

        if (p.kind === 'bar' || p.kind === 'pareto') {
          var bw = Math.max(6, Math.min(28, (iw / xs.length) * 0.62));
          series.forEach(function (s, si) {
            s.data.forEach(function (v, i) {
              if (typeof v !== 'number') return;
              var x = X(i) - bw / 2 + (si - (series.length - 1) / 2) * (bw + 2);
              var y = Y(v), hh = Math.max(1, Y(min) - y);
              kids.push(h('rect', { class: 'ch-bar', x: x, y: y, width: bw, height: hh, rx: 2, style: s.color ? { fill: s.color } : {} }));
            });
          });
          if (p.kind === 'pareto') {
            var total = 0;
            series[0].data.forEach(function (v) { total += (typeof v === 'number' ? v : 0); });
            var cum = 0;
            var pts = series[0].data.map(function (v, i) {
              cum += (typeof v === 'number' ? v : 0);
              var pct = total ? (cum / total) * 100 : 0;
              return X(i) + ',' + Y(min + (pct / 100) * span);
            });
            kids.push(h('polyline', { class: 'ch-cum', points: pts.join(' ') }));
          }
        } else if (p.kind === 'line' || p.kind === 'control') {
          series.forEach(function (s) {
            var pts = s.data.map(function (v, i) { return typeof v === 'number' ? X(i) + ',' + Y(v) : null; }).filter(Boolean);
            kids.push(h('polyline', { class: 'ch-line', points: pts.join(' '), style: s.color ? { stroke: s.color } : {} }));
            s.data.forEach(function (v, i) {
              if (typeof v !== 'number') return;
              kids.push(h('circle', { class: 'ch-dot', cx: X(i), cy: Y(v), r: 2.5, style: s.color ? { fill: s.color } : {} }));
            });
          });
          if (p.kind === 'control') {
            [['ucl', 'UCL'], ['center', 'CL'], ['lcl', 'LCL']].forEach(function (pair) {
              var v = lim[pair[0]];
              if (typeof v !== 'number') return;
              kids.push(h('line', { class: ['ch-limit', pair[0] === 'center' ? 'is-center' : ''], x1: PL, y1: Y(v), x2: W - PR, y2: Y(v) }));
              kids.push(h('text', { class: 'ch-limit-label', x: W - PR, y: Y(v) - 4, 'text-anchor': 'end' }, pair[1] + ' ' + v));
            });
          }
        } else if (p.kind === 'pie') {
          var d0 = series[0].data, tot = d0.reduce(function (a, b) { return a + (b || 0); }, 0) || 1;
          var cx = W / 2, cy = H / 2 + 4, R = Math.min(iw, ih) / 2 - 10, ang = -Math.PI / 2;
          d0.forEach(function (v, i) {
            var a2 = ang + ((v || 0) / tot) * Math.PI * 2;
            var x1 = cx + R * Math.cos(ang), y1 = cy + R * Math.sin(ang);
            var x2 = cx + R * Math.cos(a2), y2 = cy + R * Math.sin(a2);
            var big = (a2 - ang) > Math.PI ? 1 : 0;
            kids.push(h('path', {
              class: 'ch-slice',
              d: 'M' + cx + ',' + cy + ' L' + x1 + ',' + y1 + ' A' + R + ',' + R + ' 0 ' + big + ' 1 ' + x2 + ',' + y2 + ' Z'
            }));
            ang = a2;
          });
        }

        var legend = series.length > 1 || series[0].name ? h('div', { class: 'ch-legend' }, series.map(function (s) {
          return h('span', { class: 'ch-legend-item', key: s.key || s.name }, [
            h('i', { class: 'ch-swatch', style: s.color ? { background: s.color } : {} }),
            s.name || s.key
          ]);
        })) : null;

        return h('div', { class: 'chart' }, [
          h('svg', { class: 'chart-svg', viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'xMidYMid meet' }, kids),
          legend
        ]);
      };
    }
  };

  var ProgressList = {
    name: 'ProgressList',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var items = p.items || [];
        if (window.RD.pageState() === 'empty' || !items.length) {
          return h('div', { class: 'chart-empty' }, p.emptyText || '暂无数据');
        }
        var max = p.max || Math.max.apply(null, items.map(function (i) { return i.value || 0; })) || 1;
        return h('div', { class: 'prog-list' }, items.map(function (it, i) {
          var pct = Math.max(2, Math.min(100, ((it.value || 0) / (it.max || max)) * 100));
          return h('div', { class: 'prog-item', key: it.key || i }, [
            h('div', { class: 'prog-head' }, [
              h('span', { class: 'prog-rank' }, String(i + 1)),
              h('span', { class: 'prog-label' }, it.label),
              h('span', { class: 'prog-val' }, [
                String(it.value),
                it.unit ? h('span', { class: 'prog-unit' }, it.unit) : null
              ])
            ]),
            h('div', { class: 'prog-track' }, [
              h('div', { class: ['prog-fill', 'is-' + (it.tone || 'normal')], style: { width: pct + '%' } })
            ]),
            it.note ? h('div', { class: 'prog-note' }, it.note) : null
          ]);
        }));
      };
    }
  };

  var DescList = {
    name: 'DescList',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var items = p.items || [];
        var cols = p.columns || 2;
        if (!items.length) return h('div', { class: 'chart-empty' }, '暂无字段');
        return h('div', { class: ['desc-list', p.bordered ? 'is-bordered' : ''], style: { gridTemplateColumns: 'repeat(' + cols + ', minmax(0,1fr))' } },
          items.map(function (it, i) {
            return h('div', { class: 'desc-item', key: it.key || i, style: it.span ? { gridColumn: 'span ' + it.span } : {} }, [
              h('span', { class: 'desc-k' }, it.label),
              h('span', { class: ['desc-v', it.tone ? 'is-' + it.tone : ''] }, it.value == null || it.value === '' ? '—' : String(it.value))
            ]);
          }));
      };
    }
  };

  var Timeline = {
    name: 'Timeline',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var items = p.items || [];
        if (!items.length) return h('div', { class: 'chart-empty' }, p.emptyText || '暂无操作记录');
        return h('ul', { class: 'tl' }, items.map(function (it, i) {
          return h('li', { class: ['tl-item', 'is-' + (it.tone || 'normal')], key: it.key || i }, [
            h('span', { class: 'tl-dot' }),
            h('div', { class: 'tl-body' }, [
              h('div', { class: 'tl-head' }, [
                h('span', { class: 'tl-actor' }, it.actor || ''),
                h('span', { class: 'tl-action' }, it.action || ''),
                h('span', { class: 'tl-at' }, it.at || '')
              ]),
              it.note ? h('div', { class: 'tl-note' }, it.note) : null
            ])
          ]);
        }));
      };
    }
  };

  // 按 stateMachines 渲染：状态机在原型上可见的载体（只读展示，不负责切换）
  var StatusFlow = {
    name: 'StatusFlow',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var data = (window.RD.data || {});
        var sm = (data.stateMachines || []).filter(function (s) { return s.id === p.stateMachine; })[0];
        if (!sm) {
          return h('div', { class: 'chart-empty' }, '状态机 ' + (p.stateMachine || '(未指定)') + ' 不存在');
        }
        var cur = p.followEntity ? window.RD.entityStatus() : (p.current || sm.initial);
        var caps = data.capabilities || [];
        function capLabel(id) {
          var c = caps.filter(function (x) { return x.id === id; })[0];
          return c ? (c.label || id) : id;
        }
        var keys = (sm.states || []).map(function (s) { return s.key; });
        var curIdx = keys.indexOf(cur);
        var trs = sm.transitions || [];
        return h('div', { class: 'sf' }, (sm.states || []).map(function (s, i) {
          var done = curIdx >= 0 && i < curIdx;
          var on = s.key === cur;
          var edge = trs.filter(function (t) { return t.from === s.key; })[0];
          return h('div', { class: 'sf-cell', key: s.key }, [
            h('div', { class: ['sf-node', done ? 'is-done' : '', on ? 'is-on' : ''] }, [
              h('span', { class: 'sf-dot' }),
              h('span', { class: 'sf-label' }, s.label || s.key),
              p.showGuard && edge ? h('span', { class: 'sf-guard' }, edge.system ? '系统自动' : (edge.trigger ? capLabel(edge.trigger) : '')) : null
            ]),
            i < keys.length - 1 ? h('div', { class: ['sf-line', done || on ? 'is-on' : ''] }) : null
          ]);
        }));
      };
    }
  };

  /* ---------------- PDA ---------------- */
  // 离线上传角标：现场没信号时，用户唯一能确认「数据还在」的东西
  var SyncBadge = {
    name: 'SyncBadge',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var map = {
          synced: { text: '已同步', tone: 'ok' },
          pending: { text: '待上传 ' + (p.count || 0) + ' 条', tone: 'warn' },
          offline: { text: '离线 · 暂存 ' + (p.count || 0) + ' 条', tone: 'danger' },
          syncing: { text: '上传中…', tone: 'info' }
        };
        var st = map[p.state] || map.synced;
        return h('span', { class: ['sync-badge', 'is-' + st.tone], title: p.hint || '' }, [
          h('i', { class: 'sync-dot' }),
          st.text
        ]);
      };
    }
  };

  var PdaShell = {
    name: 'PdaShell',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props, ctx) {
      return function () {
        var p = props.p || {};
        var syncMap = {
          synced: { text: '已同步', color: '#8ad9c0' },
          pending: { text: '待上传 1 条', color: '#f2d08a' },
          offline: { text: '离线模式', color: '#f0b4a8' }
        };
        var st = syncMap[p.sync] || syncMap.synced;
        return h('div', { class: 'pda' }, [
          h('div', { class: 'pda-status' }, [
            h('span', null, '9:41'),
            h('span', null, '4G · 82%')
          ]),
          h('header', { class: 'pda-head' }, [
            h('span', { style: { fontSize: '17px', lineHeight: '1', paddingRight: '4px' } }, '‹'),
            h('div', { class: 'pda-title' }, p.title || ''),
            h('div', { class: 'pda-sync', style: { color: st.color } }, [
              h('span', { style: { width: '6px', height: '6px', borderRadius: '50%', background: st.color, display: 'inline-block' } }),
              st.text
            ])
          ]),
          h('div', { class: 'pda-body' }, ctx.slots.default ? ctx.slots.default() : [])
        ]);
      };
    }
  };

  var ScanBar = {
    name: 'ScanBar',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        return h('div', {
          class: 'scanbar',
          onClick: function () { window.RD.scan(); }
        }, [
          h('div', { class: 'scan-ico' }, '⌗'),
          h('span', null, p.placeholder || '扫描码'),
          h('span', { style: { marginLeft: 'auto', fontSize: '12px', color: 'var(--brand-600)' } }, '手输')
        ]);
      };
    }
  };

  var PdaCardList = {
    name: 'PdaCardList',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        return h('div', null, (p.cards || []).map(function (c, i) {
          return h('div', { class: 'pda-card', key: c.id + i }, [
            h('div', { class: 'pda-card-top' }, [
              h('div', null, [
                h('div', { class: 'pda-card-id num' }, c.id),
                h('div', { class: 'pda-card-sub' }, c.sub)
              ]),
              h('span', { class: ['tag', 'is-dot', statusTone(c.status)] }, c.status)
            ]),
            c.kv ? h('div', { class: 'pda-kv' }, c.kv.map(function (kv, k) {
              return h('div', { class: 'pda-kv-cell', key: k }, [
                h('div', { class: 'pda-kv-k' }, kv.k),
                h('div', { class: 'pda-kv-v' }, kv.v)
              ]);
            })) : null
          ]);
        }));
      };
    }
  };

  var NumpadInput = {
    name: 'NumpadInput',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var st = window.RD.state;
        var bad = st.pdaQty > (p.max || 999999);
        return h('div', null, [
          h('div', { class: 'numpad' }, [
            h('span', { class: 'numpad-label' }, p.label || '数量'),
            h('input', {
              class: 'numpad-input',
              type: 'number',
              inputmode: 'numeric',
              value: st.pdaQty,
              style: bad ? { borderColor: 'var(--danger-600)', color: 'var(--danger-600)' } : null,
              onInput: function (e) { window.RD.setQty(e.target.value); }
            }),
            h('span', { class: 'numpad-unit' }, p.unit || '')
          ]),
          bad ? h('div', { style: { fontSize: '11px', color: 'var(--danger-600)', padding: '6px 2px 0' } },
            '取样数量不能超过到货数量 ' + p.max + ' 件') : null
        ]);
      };
    }
  };

  var BigAction = {
    name: 'BigAction',
    props: { p: { type: Object, default: function () { return {}; } } },
    setup: function (props) {
      return function () {
        var p = props.p || {};
        var c = can(p.capability);
        var dis = p.capability && !c.ok;
        return h('div', { class: 'big-action' }, [
          h('button', {
            class: ['big-btn', dis ? 'is-disabled' : ''],
            onClick: function () {
              if (dis) { window.RD.toast(c.reason); return; }
              window.RD.action('submit', p.label);
            }
          }, p.label || '提交'),
          p.sub ? h('div', { class: 'big-btn-sub' }, dis ? c.reason : p.sub) : null
        ]);
      };
    }
  };

  var Fallback = {
    name: 'Fallback',
    props: { type: String },
    setup: function (props) {
      return function () {
        return h('div', {
          style: {
            border: '1px dashed var(--danger-600)',
            color: 'var(--danger-600)',
            padding: '6px 10px',
            margin: '4px',
            fontSize: '12px',
            borderRadius: '4px'
          }
        }, '未登记组件：' + (props.type || '?') + '（已降级，不白屏）');
      };
    }
  };

  window.RD_COMPONENTS = {
    AppShell: AppShell,
    PageShell: PageShell,
    TabStrip: TabStrip,
    FilterBar: FilterBar,
    StatusBar: StatusBar,
    ToolBar: ToolBar,
    DataTable: DataTable,
    Pager: Pager,
    StateBlock: StateBlock,
    SectionCard: SectionCard,
    Grid: Grid,
    StatStrip: StatStrip,
    KpiCard: KpiCard,
    Chart: Chart,
    ProgressList: ProgressList,
    DescList: DescList,
    Timeline: Timeline,
    StatusFlow: StatusFlow,
    PdaShell: PdaShell,
    SyncBadge: SyncBadge,
    ScanBar: ScanBar,
    PdaCardList: PdaCardList,
    NumpadInput: NumpadInput,
    BigAction: BigAction,
    Fallback: Fallback
  };
  window.RD_STATUS_TONE = statusTone;
})();
