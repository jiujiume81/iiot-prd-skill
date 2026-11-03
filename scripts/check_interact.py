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
            for it in g.get("items") or []:
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
        var nav = Array.prototype.slice.call(document.querySelectorAll('.nav-item')).filter(function (n) {
          return txt(n).indexOf(c.text) === 0;
        })[0];
        if (!nav) { detail = '目录里没有这一项'; }
        else { nav.click(); await sleep(450); ok = title() === c.expectTitle; detail = title(); }
      } else if (c.kind === 'row') {
        var row = document.querySelector('.dt-row');
        if (!row) { detail = '列表没有数据行'; }
        else { row.click(); await sleep(500); ok = title() === c.expectTitle; detail = title(); }
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
