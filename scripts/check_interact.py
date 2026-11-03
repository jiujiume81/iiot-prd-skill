#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可点击性实测（R 层）——把契约里声明的命令、导航、行跳转逐条真点一遍。

为什么需要这一层：check_contract 只能证明"契约里写了"，证明不了"点了有反应"。
上一版事故报告原型就是契约齐全、引擎不认，页面上点下去什么都不发生。

用法：
    python3 scripts/check_interact.py --proto examples/example-02-accident.proto.json \
        --html examples/dist-accident.html

判定：命令承载层要弹得出来 / Esc 关得上 / 导航点了要换页 / 行点了要进详情。
"""
import argparse
import html as htmllib
import json
import os
import re
import subprocess
import sys
import tempfile

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]


def walk(node, out=None):
    if out is None:
        out = []
    out.append(node)
    for c in node.get("children") or []:
        walk(c, out)
    return out


def find_node(proto, node_id):
    for p in proto.get("pages") or []:
        for n in walk(p.get("componentTree") or {}, []):
            if n.get("id") == node_id:
                return p, n
    return None, None


def actions_of(node):
    props = node.get("props") or {}
    acts = list(props.get("actions") or [])
    for col in props.get("columns") or []:
        acts += list(col.get("actions") or [])
    return acts


def entry_text(proto, entry, fallback):
    """从 ui.entry（nodeId__act_key）反查按钮上的字，用来在页面上定位。"""
    if not entry or "__act_" not in entry:
        return fallback
    base, key = entry.split("__act_", 1)
    _, node = find_node(proto, base)
    if node:
        for a in actions_of(node):
            if a.get("key") == key:
                return a.get("text") or fallback
    return fallback


def _walk_nav(items):
    """目录是树：所有用例都要能扫到二级、三级项。"""
    for it in items or []:
        yield it
        for sub in _walk_nav(it.get("children")):
            yield sub


def build_cases(proto):
    pages = proto.get("pages") or []
    title_by_id = {p.get("id"): p.get("title") for p in pages}
    page_by_id = {p.get("id"): p for p in pages}
    cases = []

    # 1. 每条 dialog/drawer 命令：在它的 owns 页上点开、看承载形式、Esc 关闭
    for c in proto.get("capabilities") or []:
        ui = c.get("ui") or {}
        if ui.get("kind") not in ("dialog", "drawer"):
            continue
        host = None
        for p in pages:
            if c.get("id") in ((p.get("contract") or {}).get("owns") or []):
                host = p.get("id")
                break
        if not host:
            continue
        cases.append({
            "kind": "cap",
            "name": f"{title_by_id.get(host)} · {c.get('label') or c.get('name')} 打开{ui.get('kind')}",
            "page": host,
            "text": entry_text(proto, ui.get("entry"), c.get("label") or c.get("name")),
            "expectKind": ui.get("kind"),
            "expectTitle": ui.get("title") or c.get("name"),
        })

    # 2. 每个页面上声明的 openModal / openDrawer 交互
    for p in pages:
        for ix in p.get("interactions") or []:
            if ix.get("do") not in ("openModal", "openDrawer"):
                continue
            cap = next((c for c in proto.get("capabilities") or [] if c.get("id") == ix.get("target")), None)
            if not cap:
                continue
            ui = cap.get("ui") or {}
            cases.append({
                "kind": "cap",
                "name": f"{p.get('title')} · 交互 {ix.get('id')} 打开承载层",
                "page": p.get("id"),
                "text": entry_text(proto, ix.get("on"), cap.get("label") or cap.get("name")),
                "expectKind": "drawer" if ix.get("do") == "openDrawer" else "dialog",
                "expectTitle": ui.get("title") or cap.get("name"),
            })

    # 3. 目录项：点了要真的换页
    seen = set()
    for p in pages:
        props = (p.get("componentTree") or {}).get("props") or {}
        for g in props.get("groups") or []:
            for it in _walk_nav(g.get("items")):
                tgt = it.get("page")
                label = it.get("label") or ""
                if not tgt and it.get("page") is None:
                    hit = next((x for x in pages
                                if x.get("layout") != "detail"
                                and (x.get("title") == label or x.get("navLabel") == label)), None)
                    tgt = hit.get("id") if hit else None
                if not tgt or (label, tgt) in seen:
                    continue
                seen.add((label, tgt))
                cases.append({
                    "kind": "nav",
                    "name": f"目录「{label}」可跳到 {title_by_id.get(tgt)}",
                    "page": p.get("id"),
                    "text": label,
                    "expectTitle": title_by_id.get(tgt),
                })

    # 3b. 目录树：分组能折叠、再展开，且展开时确实藏住了子项
    tree_seen = set()
    for p in pages:
        props = (p.get("componentTree") or {}).get("props") or {}
        for g in props.get("groups") or []:
            for it in g.get("items") or []:
                kids = it.get("children") or []
                if not kids:
                    continue
                lab = it.get("label") or ""
                # 子项必须是叶子且有 page，否则"藏住"没法从 DOM 判断
                child = next((k for k in kids if k.get("label") and not (k.get("children") or [])), None)
                if not child or lab in tree_seen:
                    continue
                tree_seen.add(lab)
                cases.append({
                    "kind": "navtree",
                    "name": f"目录分组「{lab}」可折叠 / 展开",
                    "page": p.get("id"),
                    "text": lab,
                    "child": child.get("label"),
                })

    # 3c. 标注能不能落在弹层上（评审最常见的动作：开着弹框顺手圈一个字段）
    for c in (proto.get("capabilities") or []):
        ui = c.get("ui") or {}
        if ui.get("kind") not in ("dialog", "drawer") or not (ui.get("fields") or []):
            continue
        host = next((p.get("id") for p in pages
                     if c.get("id") in ((p.get("contract") or {}).get("owns") or [])), None)
        if not host:
            continue
        cases.append({
            "kind": "annot",
            "name": f"{title_by_id.get(host)} · 能在「{ui.get('title') or c.get('name')}」弹层里标注",
            "page": host,
            "text": entry_text(proto, ui.get("entry"), c.get("label") or c.get("name")),
        })
        break

    # 4. 行点击：列表页每页抽一次
    for p in pages:
        for ix in p.get("interactions") or []:
            if ix.get("on") == "__row_click" and ix.get("do") == "navigate":
                tgt = page_by_id.get(ix.get("target"))
                if not tgt:
                    continue
                cases.append({
                    "kind": "row",
                    "name": f"{p.get('title')} · 点数据行进入「{tgt.get('title')}」",
                    "page": p.get("id"),
                    "expectTitle": tgt.get("title"),
                })
                break
    return cases


PROBE = r"""
(function () {
  var CASES = window.__CASES__ || [];
  var OUT = [];
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function txt(el) { return el ? (el.textContent || '').trim() : ''; }
  function title() {
    var el = document.querySelector('.app-title') || document.querySelector('.pda-title');
    return txt(el);
  }
  function mask() { return document.querySelector('.layer-mask'); }
  function layer() { return document.querySelector('.layer'); }
  async function waitFor(fn, ms) {
    var t0 = Date.now();
    while (Date.now() - t0 < (ms || 1500)) { var v = fn(); if (v) return v; await sleep(40); }
    return null;
  }
  // 弹层不许盖住顶部工具条：遮罩上沿不能高于顶栏下沿，
  // 且顶栏按钮中心做命中测试时必须还是按钮本身（拿到 layer-mask 就是被盖了）
  function topbarUsable() {
    var top = document.querySelector('.shell-top');
    var m = mask();
    if (!top || !m) return true;
    var tb = top.getBoundingClientRect();
    var mr = m.getBoundingClientRect();
    if (mr.top < tb.bottom - 1) return false;
    var btn = top.querySelector('.tool-btn');
    if (!btn) return true;
    var br = btn.getBoundingClientRect();
    var hit = document.elementFromPoint(br.left + br.width / 2, br.top + br.height / 2);
    if (!hit) return true;
    return !(hit.closest && hit.closest('.layer-mask'));
  }
  function findClickable(text) {
    // 先找行内动作：同名文本在工具栏里也有时（如「审核」），行内那个才是命令入口
    var groups = [
      Array.prototype.slice.call(document.querySelectorAll('.dt-row a, .dt-row button')),
      Array.prototype.slice.call(document.querySelectorAll('button'))
    ];
    for (var g = 0; g < groups.length; g++) {
      var hit = groups[g].filter(function (el) {
        return txt(el) === text && !el.classList.contains('is-off') && !el.classList.contains('is-disabled');
      })[0];
      if (hit) return hit;
    }
    // 都禁用也要找得到：点它应该给理由，不该没反应
    for (var g2 = 0; g2 < groups.length; g2++) {
      var off = groups[g2].filter(function (el) { return txt(el) === text; })[0];
      if (off) return off;
    }
    return null;
  }
  async function run() {
    for (var i = 0; i < CASES.length; i++) {
      var c = CASES[i], ok = false, detail = '';
      window.RD.goto(c.page, '探针');
      await sleep(450);
      if (c.kind === 'nav') {
        // 树形目录：先把折叠的分组都点开，否则子项不在 DOM 里，会被误判成"目录里没有"
        Array.prototype.slice.call(document.querySelectorAll('.nav-item.is-group .nav-caret')).forEach(function (cr) {
          if (txt(cr) === '▸') cr.click();
        });
        await sleep(200);
        var nav = Array.prototype.slice.call(document.querySelectorAll('.nav-item')).filter(function (n) {
          return txt(n).indexOf(c.text) === 0;
        })[0];
        if (!nav) { detail = '目录里没有这一项'; }
        else { nav.click(); await sleep(450); ok = title() === c.expectTitle; detail = title(); }
      } else if (c.kind === 'navtree') {
        function navLabels() {
          return Array.prototype.slice.call(document.querySelectorAll('.app-nav .nav-label')).map(txt);
        }
        function groupOf(label) {
          // 分组的 textContent 里含折叠箭头，不能整块比较，要拿 .nav-label 的文本
          var labs = Array.prototype.slice.call(document.querySelectorAll('.nav-item.is-group .nav-label'));
          var hit = labs.filter(function (e) { return txt(e) === label; })[0];
          return hit ? hit.closest('.nav-item') : null;
        }
        var grp = groupOf(c.text);
        if (!grp) { detail = '目录里没有分组「' + c.text + '」'; }
        else {
          var vis0 = navLabels().indexOf(c.child) >= 0;
          var cr1 = grp.querySelector('.nav-caret');
          if (!cr1) { detail = '分组左侧没有折叠箭头'; }
          else {
            cr1.click(); await sleep(280);
            var vis1 = navLabels().indexOf(c.child) >= 0;
            var grp2 = groupOf(c.text);
            var cr2 = grp2 && grp2.querySelector('.nav-caret');
            if (cr2) { cr2.click(); await sleep(280); }
            var vis2 = navLabels().indexOf(c.child) >= 0;
            ok = vis0 && !vis1 && vis2;
            detail = '初始' + (vis0 ? '展开' : '收起') + ' / 点箭头后' + (vis1 ? '子项仍在（折叠没生效）' : '子项已藏') +
                     ' / 再点' + (vis2 ? '已展开' : '没回来');
          }
        }
      } else if (c.kind === 'row') {
        var row = document.querySelector('.dt-row');
        if (!row) { detail = '列表没有数据行'; }
        else { row.click(); await sleep(500); ok = title() === c.expectTitle; detail = title(); }
      } else if (c.kind === 'annot') {
        // 评审里最常见的动作是「开着弹框顺手圈一个字段」。如果弹层里的元素没有锚点，
        // 这条意见只能笼统写在整页上，落点说不清。
        var abEl = findClickable(c.text);
        if (!abEl) { detail = '找不到命令入口「' + c.text + '」'; }
        else {
          abEl.click();
          var m2 = await waitFor(mask, 1500);
          if (!m2) { detail = '弹层没打开（前置条件不满足）'; }
          else {
            var S = window.__RD_TEST__ && window.__RD_TEST__.store;
            var n0 = S ? S.annotations.length : -1;
            var abBtn = Array.prototype.slice.call(document.querySelectorAll('.shell-top .tool-btn')).filter(function (b) {
              return txt(b).indexOf('标注') === 0;
            })[0];
            if (abBtn) abBtn.click();
            await sleep(220);
            var field = document.querySelector('.layer [data-node-id]');
            if (!field) { detail = '弹层里没有可标注的元素（缺 data-node-id）'; }
            else {
              var fr = field.getBoundingClientRect();
              field.dispatchEvent(new MouseEvent('click', {
                bubbles: true,
                clientX: fr.left + fr.width / 2,
                clientY: fr.top + fr.height / 2
              }));
              await sleep(320);
              var pop = document.querySelector('.annot-pop');
              if (!pop) { detail = '点弹层里的字段没有弹出标注框'; }
              else {
                var ta = pop.querySelector('textarea');
                ta.value = '探针：这个字段该拆开';
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                await sleep(120);
                var sv = Array.prototype.slice.call(pop.querySelectorAll('button')).filter(function (b) {
                  return txt(b) === '保存';
                })[0];
                if (sv) sv.click();
                await sleep(340);
                var n1 = S ? S.annotations.length : -1;
                var last = S && n1 ? S.annotations[n1 - 1] : {};
                var carrier = (last && last.target && last.target.carrier) || '?';
                var pins = Array.prototype.slice.call(document.querySelectorAll('.annot-pin'));
                // 别用坐标猜"是不是在弹层上"：窗口宽不同，阈值就变了。
                // 直接看 pin 落点是否落在 .layer 的矩形内，再核对标注记的载体。
                var L0 = layer();
                var lr = L0 ? L0.getBoundingClientRect() : { left: 0, right: 0, top: 0, bottom: 0 };
                var onLayer = pins.some(function (p) {
                  var x = parseFloat(p.style.left), y = parseFloat(p.style.top);
                  return x >= lr.left - 6 && x <= lr.right + 6 && y >= lr.top - 6 && y <= lr.bottom + 6;
                });
                ok = (n1 === n0 + 1) && carrier !== 'page' && onLayer;
                detail = '标注 ' + n0 + '→' + n1 + '，载体=' + carrier +
                         '，pin 落在弹层矩形内：' + (onLayer ? '是' : '否');
                if (S && n1 > n0) S.annotations.splice(n0, n1 - n0);   // 探针不留痕
                if (abBtn) abBtn.click();
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
                await sleep(220);
              }
            }
          }
        }
      } else {
        var el = findClickable(c.text);
        if (!el) { detail = '页面上找不到「' + c.text + '」（命令声明了但没落地）'; }
        else {
          el.click();
          var m = await waitFor(mask, 1500);
          var L = layer();
          if (!m) {
            detail = '点了没有弹层（禁用态提示：' + (txt(document.querySelector('.toast')) || '无') + '）';
            ok = false;
          } else {
            var kindOk = L && L.classList.contains('layer-' + c.expectKind);
            var tbOk = topbarUsable();
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
            await sleep(250);
            var closed = !mask();
            ok = kindOk && closed && tbOk;
            detail = (L ? L.className : '') + (closed ? ' / Esc 已关闭' : ' / Esc 关不掉')
              + (tbOk ? ' / 顶栏可点' : ' / 遮罩盖住了顶部工具条（标注、审核、导出点不到）');
          }
        }
      }
      OUT.push({ name: c.name, ok: ok, detail: detail });
    }
    var pre = document.createElement('pre');
    pre.id = 'INTERACT_RESULT';
    pre.textContent = JSON.stringify(OUT);
    document.body.appendChild(pre);
  }
  run();
})();
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proto", required=True)
    ap.add_argument("--html", required=True)
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--budget", type=int, default=60000)
    args = ap.parse_args()

    chrome = args.chrome or next((c for c in CHROME_CANDIDATES if os.path.exists(c)), None)
    if not chrome:
        print("找不到 Chrome/Chromium，可用 --chrome 指定路径")
        return 2

    proto = json.load(open(args.proto, encoding="utf-8"))
    cases = build_cases(proto)
    if not cases:
        print("没有可测的交互（契约里没有 dialog/drawer 命令、目录绑定或行跳转）")
        return 0

    doc = open(args.html, encoding="utf-8").read()
    inject = ("<script>window.__CASES__=" + json.dumps(cases, ensure_ascii=False) +
              ";</script><script>" + PROBE + "</script>")
    idx = doc.rfind("</body>")
    doc = doc[:idx] + inject + doc[idx:]

    tmp = os.path.join(tempfile.gettempdir(), "iiot-interact.html")
    open(tmp, "w", encoding="utf-8").write(doc)

    cmd = [chrome, "--headless=old", "--disable-gpu", "--no-sandbox",
           "--virtual-time-budget=%d" % args.budget, "--dump-dom", "file://" + tmp]
    dom = subprocess.run(cmd, capture_output=True, text=True).stdout

    k = dom.rfind('<pre id="INTERACT_RESULT">')
    if k < 0:
        print("实测没有跑起来（页面可能报错），请先用浏览器打开确认")
        return 2
    s = dom.find(">", k) + 1
    e = dom.find("</pre>", s)
    items = json.loads(htmllib.unescape(dom[s:e]))

    print("可点击性实测：%s" % os.path.basename(args.proto))
    print("-" * 66)
    bad = 0
    for it in items:
        if it["ok"]:
            print("[OK   ] %s" % it["name"])
        else:
            bad += 1
            print("[FAIL ] %s  —— %s" % (it["name"], it["detail"]))
    print("-" * 66)
    print("结果：%d 项，通过 %d，失败 %d  %s" %
          (len(items), len(items) - bad, bad, "PASS" if bad == 0 else "FAIL"))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
