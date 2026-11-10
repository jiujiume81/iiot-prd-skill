#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mermaid -> SVG 离线渲染（构建时预渲染，产物内嵌，不依赖运行时 JS）。

依赖（都在仓库内/本机）：
  assets/vendor/mermaid.min.js   随仓库分发，不引 CDN
  Chrome / Chromium              仅构建时需要，用 CHROME_CANDIDATES 探测

缓存：figs/.cache/<sha256(源码+主题)[:16]>.svg，命中直接复制，不再启浏览器。
来源自证：SVG 里写 `<!-- proto-sha256:<16> -->`，C-24 用它核产物是哪版契约生成的。

单独跑（调试用）：
  python3 scripts/render_figs.py --mmd /tmp/x.mmd --out /tmp/x.svg --proto <proto>
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "assets", "vendor", "mermaid.min.js")

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]

# 注意：mermaid 的 stateDiagram 与 flowchart 是两套独立布局，配置不通用。
# 实测（2026-11-10）：flowchart 的 nodeSpacing / rankSpacing / nodeWidth
# 对 stateDiagram-v2 完全不生效；宽度只由 rank 数与边标签文本宽度决定。
#   原值 1744.8 → fontSize 14→13 后 1727.5（只省 17px）
#   删掉全部边标签后 1262.0（标签独占 465px）
#   改用 flowchart LR 反而 2125.4（更宽，SVG 315KB）
# 所以状态图想变窄只有两条路：缩短边标签（动业务文案）或自绘。
# 最终选择竖向（279×916）：横向压不进 1200，缩到 7px 等于看不清；
# 竖向 1:1 显示、13px 字，且标签落在线的侧面空白，不压线。
THEME = "iiot-prd-v5-tb-final"


# 状态图的边标签 DOM 是 .edgeLabel > .label > foreignObject > div.labelBkg > p。
# 实测 themeVariables.edgeLabelBackground 压根没落到这个 div 上，光配主题修不好，
# 只能对 .labelBkg / p 直接压白底（下面这段 CSS 随 SVG 一起进产物）。
LABEL_CSS = (".edgeLabel .labelBkg{background:#fff!important;}"
             ".edgeLabel p{background:#fff;margin:0;padding:0 4px;}"
             ".edgeLabel rect{fill:#fff;}")


class RenderError(RuntimeError):
    pass


def decorate(svg, proto_sha=None):
    """补标签白底 + 契约指纹；两条渲染路径共用。"""
    if "<style>" in svg:
        svg = svg.replace("<style>", "<style>" + LABEL_CSS, 1)
    else:
        svg = svg.replace(">", "><style>" + LABEL_CSS + "</style>", 1)
    if proto_sha:
        svg = svg.replace(">", "><!-- proto-sha256:%s -->" % proto_sha, 1)
    return svg


def sha16(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def file_sha16(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def find_chrome():
    return next((p for p in CHROME_CANDIDATES if os.path.exists(p)), None)


def _build_html(code):
    safe = code.replace("&", "&amp;").replace("<", "&lt;")
    return """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<script src="file://%s"></script></head>
<body style="margin:0;background:#fff">
<pre id="code" style="display:none">%s</pre><div id="out"></div>
<script>
const t0 = performance.now();
mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  securityLevel: 'loose',
  fontFamily: '-apple-system,"PingFang SC","Microsoft YaHei",sans-serif',
  themeVariables: {
    primaryColor: '#eff8fa', primaryBorderColor: '#2aa3b3', primaryTextColor: '#0f1f27',
    lineColor: '#2a5b68', secondaryColor: '#f2f6f7', tertiaryColor: '#ffffff',
    fontSize: '13px', edgeLabelBackground: '#ffffff'
  },
  state: { nodeSpacing: 8, rankSpacing: 8 },
  flowchart: { curve: 'basis', htmlLabels: true, useMaxWidth: false,
               nodeSpacing: 18, rankSpacing: 30, padding: 8, nodeWidth: 110 }
});
mermaid.render('fig1', document.getElementById('code').textContent).then(function (r) {
  document.getElementById('out').innerHTML = r.svg;
  var p = document.createElement('pre'); p.id = 'MS'; p.textContent = String(performance.now() - t0);
  document.body.appendChild(p);
}).catch(function (e) {
  var p = document.createElement('pre'); p.id = 'ERR'; p.textContent = String(e && e.message || e);
  document.body.appendChild(p);
});
</script></body></html>""" % (VENDOR.replace("\\", "/"), safe)


def render_svg(code, out_svg, proto_sha=None, chrome=None, timeout=120):
    """把一段 mermaid 源码渲成 SVG。返回 dict(ok, ms, cached, reason)。"""
    if not os.path.exists(VENDOR):
        raise RenderError("缺少 assets/vendor/mermaid.min.js")
    chrome = chrome or find_chrome()
    if not chrome:
        raise RenderError("找不到 Chrome/Chromium（CHROME_CANDIDATES 均为空）")

    out_dir = os.path.dirname(os.path.abspath(out_svg))
    os.makedirs(out_dir, exist_ok=True)
    cache_dir = os.path.join(out_dir, ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    h = sha16(code + "|" + THEME)
    cache = os.path.join(cache_dir, h + ".svg")

    if os.path.exists(cache):
        shutil.copyfile(cache, out_svg)
        return {"ok": True, "ms": 0.0, "cached": True, "hash": h}

    fd, tmp_html = tempfile.mkstemp(suffix=".html", prefix="mm-")
    os.close(fd)
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(_build_html(code))
    t0 = time.time()
    try:
        out = subprocess.run([chrome, "--headless=old", "--disable-gpu", "--no-sandbox",
                              "--virtual-time-budget=15000", "--dump-dom",
                              "file://" + tmp_html],
                             capture_output=True, text=True, timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        os.unlink(tmp_html)
        raise RenderError("Chrome 渲染超时（%ss）" % timeout)
    finally:
        if os.path.exists(tmp_html):
            os.unlink(tmp_html)
    wall = int((time.time() - t0) * 1000)

    err = re.search(r'<pre id="ERR">(.*?)</pre>', out, re.S)
    if err:
        raise RenderError("mermaid 报错：" + re.sub(r"\s+", " ", err.group(1))[:160])
    m = re.search(r'(<svg[\s\S]*?</svg>)', out)
    if not m:
        raise RenderError("Chrome 没有返回 SVG（页面可能未加载完）")
    svg = decorate(m.group(1), proto_sha)
    with open(cache, "w", encoding="utf-8") as f:
        f.write(svg)
    with open(out_svg, "w", encoding="utf-8") as f:
        f.write(svg)
    return {"ok": True, "ms": wall, "cached": False, "hash": h}


def _build_html_many(codes):
    blocks, scripts = [], []
    for i, code in enumerate(codes):
        safe = code.replace("&", "&amp;").replace("<", "&lt;")
        blocks.append('<pre id="c%d" style="display:none">%s</pre><pre id="o%d"></pre>' % (i, safe, i))
        scripts.append("mermaid.render('g%d', document.getElementById('c%d').textContent)" % (i, i))
    return """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<script src="file://%s"></script></head><body style="margin:0;background:#fff">
%s
<script>
const t0 = performance.now();
mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  securityLevel: 'loose',
  fontFamily: '-apple-system,"PingFang SC","Microsoft YaHei",sans-serif',
  themeVariables: {
    primaryColor: '#eff8fa', primaryBorderColor: '#2aa3b3', primaryTextColor: '#0f1f27',
    lineColor: '#2a5b68', secondaryColor: '#f2f6f7', tertiaryColor: '#ffffff',
    fontSize: '13px', edgeLabelBackground: '#ffffff'
  },
  state: { nodeSpacing: 8, rankSpacing: 8 },
  flowchart: { curve: 'basis', htmlLabels: true, useMaxWidth: false,
               nodeSpacing: 18, rankSpacing: 30, padding: 8, nodeWidth: 110 }
});
Promise.all([%s]).then(function (rs) {
  rs.forEach(function (r, i) { document.getElementById('o' + i).textContent = r.svg; });
  var p = document.createElement('pre'); p.id = 'MS';
  p.textContent = String(performance.now() - t0); document.body.appendChild(p);
}).catch(function (e) {
  var p = document.createElement('pre'); p.id = 'ERR';
  p.textContent = String(e && e.message || e); document.body.appendChild(p);
});
</script></body></html>""" % (VENDOR.replace("\\", "/"), "\n".join(blocks), ", ".join(scripts))


def render_many(items, proto_sha=None, chrome=None, timeout=180):
    """一批 mermaid 源码共用一次 Chrome。

    items: [{"key": str, "code": str, "out": path}, ...]
    返回 {key: {"ok": bool, "cached": bool, "error": str|None}}
    """
    if not os.path.exists(VENDOR):
        raise RenderError("缺少 assets/vendor/mermaid.min.js")
    chrome = chrome or find_chrome()
    if not chrome:
        raise RenderError("找不到 Chrome/Chromium（CHROME_CANDIDATES 均为空）")

    result, todo = {}, []
    for it in items:
        out_dir = os.path.dirname(os.path.abspath(it["out"]))
        os.makedirs(os.path.join(out_dir, ".cache"), exist_ok=True)
        h = sha16(it["code"] + "|" + THEME)
        cache = os.path.join(out_dir, ".cache", h + ".svg")
        it["_hash"] = h
        it["_cache"] = cache
        if os.path.exists(cache):
            shutil.copyfile(cache, it["out"])
            result[it["key"]] = {"ok": True, "cached": True, "ms": 0.0}
        else:
            todo.append(it)
    if not todo:
        return result

    page = _build_html_many([x["code"] for x in todo])
    fd, tmp = tempfile.mkstemp(suffix=".html", prefix="mm-many-")
    os.close(fd)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    t0 = time.time()
    try:
        out = subprocess.run([chrome, "--headless=old", "--disable-gpu", "--no-sandbox",
                              "--virtual-time-budget=20000", "--dump-dom", "file://" + tmp],
                             capture_output=True, text=True, timeout=timeout).stdout
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    ms = int((time.time() - t0) * 1000)

    err = re.search(r'<pre id="ERR">(.*?)</pre>', out, re.S)
    if err:
        msg = re.sub(r"\s+", " ", err.group(1))[:160]
        for it in todo:
            result[it["key"]] = {"ok": False, "cached": False, "error": "mermaid 报错：" + msg}
        return result

    for i, it in enumerate(todo):
        m = re.search(r'<pre id="o%d">([\s\S]*?)</pre>' % i, out)
        svg = html.unescape(m.group(1)) if m else ""
        if "<svg" not in svg:
            result[it["key"]] = {"ok": False, "cached": False, "error": "没有拿到第 %d 张图的 SVG" % (i + 1)}
            continue
        svg = decorate(svg, proto_sha)
        with open(it["_cache"], "w", encoding="utf-8") as f:
            f.write(svg)
        with open(it["out"], "w", encoding="utf-8") as f:
            f.write(svg)
        result[it["key"]] = {"ok": True, "cached": False, "ms": ms}
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mmd", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--proto", default=None)
    args = ap.parse_args()
    code = open(args.mmd, encoding="utf-8").read()
    sha = file_sha16(args.proto) if args.proto else None
    r = render_svg(code, args.out, sha)
    print(json.dumps(r, ensure_ascii=False))
    print("%s  %.1f KB" % (args.out, os.path.getsize(args.out) / 1024.0))


if __name__ == "__main__":
    try:
        main()
    except RenderError as e:
        print("渲染失败：" + str(e), file=sys.stderr)
        sys.exit(1)
