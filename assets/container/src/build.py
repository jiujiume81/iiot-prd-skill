#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 Vue 运行时、渲染层、组件库、数据契约、样式内联成一个可双击打开的单文件 HTML。

用法：
  python3 build.py --proto ../../examples/example-01-qms-incoming.proto.json
  python3 build.py --proto <path> --out dist/index.html
"""
import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def read(p):
    with open(os.path.join(HERE, p), encoding="utf-8") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proto", required=True)
    ap.add_argument("--out", default=os.path.join("dist", "index.html"))
    args = ap.parse_args()

    proto_path = args.proto if os.path.isabs(args.proto) else os.path.abspath(os.path.join(HERE, args.proto))
    with open(proto_path, encoding="utf-8") as f:
        proto = json.load(f)

    css = read("styles.css")
    runtime = read("runtime.js")
    vue = read("vue.global.prod.js")
    components = read("components.js")
    app = read("app.js")

    for name, src in [("components.js", components), ("app.js", app)]:
        if re.search(r"</script", src, re.I):
            raise SystemExit(f"{name} 含 </script，内联会截断")

    data = json.dumps(proto, ensure_ascii=False, separators=(",", ":"))
    title = f"{proto['meta']['product']} · 原型与 PRD"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style id="iiot-css">
{css}
</style>
</head>
<body>
<div id="app"></div>
<script>
window.addEventListener('error', function (e) {{
  var d = document.createElement('div');
  d.id = 'boot-error';
  d.style.cssText = 'position:fixed;left:0;bottom:0;background:#b23a31;color:#fff;font:12px/1.6 monospace;padding:6px 10px;z-index:999';
  d.textContent = 'ERR: ' + (e.message || e.type);
  document.body.appendChild(d);
}});
window.__PROTO__ = {data};
</script>
<script>{vue}</script>
<script>{runtime}</script>
<script>{components}</script>
<script>{app}</script>
</body>
</html>
"""

    out = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    kb = len(html.encode("utf-8")) / 1024
    print(f"built: {out}")
    print(f"size : {kb:.0f} KB  (vue {len(vue)/1024:.0f}KB / css {len(css)/1024:.0f}KB / data {len(data)/1024:.0f}KB)")
    print(f"pages: {len(proto['pages'])}  modules: {len(proto['modules'])}  caps: {len(proto['capabilities'])}")


if __name__ == "__main__":
    main()
