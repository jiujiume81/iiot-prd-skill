#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PRD.md → 单文件 HTML（离线双击可看）。

复用上游两个文件（不改）：
  scripts/mdast.py           Markdown → 块级 AST
  scripts/render_common.py   行内标记与 slug
本文件只做本仓库的排版与装配：
  - SVG 内联（figs/*.svg 整段塞进 HTML，不用 <img> 外链）
  - 顶部两级目录（## / ###），可点跳转
  - 头部指纹与 md 一致，C-24 用来验这两个产物同源

用法：python3 scripts/build_prd_html.py <PRD.md> [--out x.html]
"""
import argparse
import html as htmllib
import os
import re
import sys

import mdast
import render_common

CSS = """
:root{--ink:#0f1f27;--ink2:#4b5f69;--ink3:#7e919b;--line:#e3ebed;--line2:#eff4f5;
--brand:#0a7183;--brand-bg:#eff8fa;--code:#f4f7f8;--page:#fff}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
font:15px/1.85 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{display:flex;gap:28px;max-width:1280px;margin:0 auto;padding:28px 20px 80px}
nav.toc{position:sticky;top:20px;align-self:flex-start;width:236px;flex:0 0 236px;
max-height:calc(100vh - 40px);overflow:auto;font-size:13px;border-right:1px solid var(--line);padding-right:14px}
nav.toc b{display:block;font-size:12px;color:var(--ink3);margin:0 0 8px;font-weight:600}
nav.toc a{display:block;color:var(--ink2);text-decoration:none;padding:3px 0;line-height:1.5}
nav.toc a:hover{color:var(--brand)}
nav.toc a.lv3{padding-left:14px;font-size:12px;color:var(--ink3)}
main{flex:1;min-width:0;max-width:900px}
h1{font-size:26px;margin:0 0 14px}
h2{font-size:20px;margin:34px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:16px;margin:22px 0 8px}
h4{font-size:14px;margin:16px 0 6px;color:var(--ink2)}
p{margin:8px 0}
blockquote{margin:10px 0;padding:8px 12px;background:var(--brand-bg);border-left:3px solid var(--brand);
color:var(--ink2);font-size:13px}
blockquote p{margin:2px 0}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px;table-layout:auto}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top;
word-break:break-word}
th{background:#f7fafb;font-weight:600}
tbody tr:nth-child(even){background:#fbfdfd}
code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:12.5px;
font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
pre{background:var(--code);padding:12px 14px;border-radius:6px;overflow:auto;font-size:12.5px;line-height:1.6}
pre code{background:none;padding:0}
ul,ol{margin:8px 0 8px 22px;padding:0}
li{margin:3px 0}
hr{border:none;border-top:1px solid var(--line);margin:22px 0}
.fig{margin:14px 0;padding:10px;border:1px solid var(--line);border-radius:8px;
background:#fff;overflow-x:auto}
.fig svg{display:block;max-width:none;height:auto}
.fig-hint{display:none;margin-top:6px;font-size:12px;color:var(--ink3)}
.fig.is-wide .fig-hint{display:block}
.fig-miss{padding:10px 12px;border:1px dashed #b23a31;color:#b23a31;background:#fbecea;border-radius:6px;font-size:13px}
.meta{font-size:12px;color:var(--ink3);margin:0 0 18px}
@media (max-width:900px){.wrap{display:block}nav.toc{position:static;width:auto;border-right:none;
border-bottom:1px solid var(--line);margin-bottom:16px;padding:0 0 12px;max-height:none}}
@media print{nav.toc{display:none}.wrap{display:block;padding:0}main{max-width:none}}
"""


def uniq_slug(text, used):
    base = render_common.slug(text)
    s, n = base, 2
    while s in used:
        s = "%s-%d" % (base, n)
        n += 1
    used.add(s)
    return s


def render_list(items):
    out = []
    stack = []  # (indent, tag)
    for it in items:
        ind = it["indent"]
        tag = "ol" if it["ordered"] else "ul"
        while stack and ind < stack[-1][0]:
            out.append("</li></%s>" % stack.pop()[1])
        if not stack or ind > stack[-1][0]:
            out.append("<%s>" % tag)
            stack.append((ind, tag))
        else:
            out.append("</li>")
        out.append("<li>" + render_common.inline(it["text"]))
    while stack:
        out.append("</li></%s>" % stack.pop()[1])
    return "".join(out)


def render_table(b):
    head = "".join("<th>%s</th>" % render_common.inline(c) for c in b["header"])
    rows = []
    for r in b["rows"]:
        rows.append("<tr>" + "".join("<td>%s</td>" % render_common.inline(c) for c in r) + "</tr>")
    return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (head, "".join(rows))


def render_image(b, base_dir, fig_index):
    src = b.get("src") or ""
    alt = htmllib.escape(b.get("alt") or "", quote=True)
    if not src.startswith("figs/"):
        return '<p class="fig-miss">未内联的图片：%s</p>' % htmllib.escape(src)
    path = os.path.join(base_dir, src.replace("/", os.sep))
    if not os.path.exists(path):
        return '<div class="fig-miss">图缺失：%s</div>' % htmllib.escape(src)
    svg = open(path, encoding="utf-8").read()
    svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg)
    svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg, flags=re.I)
    # 按 viewBox 给固有尺寸：不缩放，窄屏靠容器横向滚动，字才看得清
    vb = re.search(r'viewBox="([\d.\- ]+)"', svg)
    if vb:
        v = vb.group(1).split()
        if len(v) == 4:
            w, h = float(v[2]), float(v[3])
            svg = re.sub(r'width="100%"', 'width="%d"' % w, svg, count=1)
            svg = re.sub(r'style="max-width: [\d.]+px;"', 'style="max-width:%dpx;"' % w, svg, count=1)
            svg = re.sub(r'(<svg[^>]*?)(?<!height)(>)', r'\1 height="%d"\2' % h, svg, count=1)
    fig_index.append(src)
    fid = "fig-" + os.path.splitext(os.path.basename(src))[0]
    return ('<div class="fig" id="%s" data-fig="%s" role="img" aria-label="%s">%s'
            '<div class="fig-hint">← 可横向滚动查看完整流程 →</div></div>') % (
        fid, htmllib.escape(src, quote=True), alt, svg)


def convert(md_text, base_dir):
    blocks = mdast.parse(md_text)
    used = set()
    toc, body, fig_index = [], [], []
    for b in blocks:
        t = b["type"]
        if t == "head":
            lv, text = b["level"], b["text"]
            if lv > 4:
                lv = 4
            sid = uniq_slug(text, used)
            if lv in (2, 3):
                toc.append((lv, sid, text))
            body.append('<h%d id="%s">%s</h%d>' % (lv, sid, render_common.inline(text), lv))
        elif t == "para":
            body.append("<p>%s</p>" % render_common.inline(b["text"]).replace("\n", "<br>"))
        elif t == "quote":
            inner = "".join("<p>%s</p>" % render_common.inline(x) for x in b["lines"] if x)
            body.append("<blockquote>%s</blockquote>" % inner)
        elif t == "table":
            body.append(render_table(b))
        elif t == "list":
            body.append(render_list(b["items"]))
        elif t == "hr":
            body.append("<hr>")
        elif t == "image":
            body.append(render_image(b, base_dir, fig_index))
        elif t == "fence":
            body.append('<pre><code class="lang-%s">%s</code></pre>' % (
                htmllib.escape(b.get("lang") or "text"),
                htmllib.escape(b.get("code") or "")))
    nav = []
    for lv, sid, text in toc:
        nav.append('<a class="lv%d" href="#%s">%s</a>' % (lv, sid, render_common.inline(text)))
    return "".join(nav), "\n".join(body), fig_index


def build(md_path, out_path=None):
    md_path = os.path.abspath(md_path)
    out_path = out_path or (os.path.splitext(md_path)[0] + ".html")
    md = open(md_path, encoding="utf-8").read()
    base_dir = os.path.dirname(md_path)

    m = re.search(r"生成源：(.+?)@\s*sha256:([0-9a-f]{16})（(.+?)）", md)
    if m:
        meta_line = "生成源：%s @ sha256:%s（%s）" % (m.group(1).strip(), m.group(2), m.group(3))
        sha = m.group(2)
    else:
        meta_line, sha = "生成源：未标注", ""

    nav, body, figs = convert(md, base_dir)
    title = next((l.lstrip("#").strip() for l in md.splitlines() if l.startswith("# ")), "PRD")
    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="prd-source" content="sha256:%s">
<title>%s</title><style>%s</style></head>
<body><div class="wrap">
<nav class="toc"><b>目录</b>%s</nav>
<main><p class="meta">%s</p>%s</main>
</div>
<script>
document.querySelectorAll('.fig').forEach(function (f) {
  var s = f.querySelector('svg');
  if (s && s.getBoundingClientRect().width > f.clientWidth + 2) f.classList.add('is-wide');
});
</script>
</body></html>""" % (sha, htmllib.escape(title), CSS, nav, htmllib.escape(meta_line), body)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return {"out": out_path, "bytes": os.path.getsize(out_path), "figs": figs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    r = build(args.md, args.out)
    print("written: %s (%.1f KB, 内联图 %d 张)" % (r["out"], r["bytes"] / 1024.0, len(r["figs"])))


if __name__ == "__main__":
    main()
