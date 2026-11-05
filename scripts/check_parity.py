#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IIOT-PRD 三处一致校验（C 系列判据）

「同一份 proto.json，容器所见 = 导出 MD = 校验报告」——这句话不能靠肉眼。

用法：
  python3 scripts/check_parity.py examples/example-01-qms-incoming.proto.json
  python3 scripts/check_parity.py <proto> --html assets/container/dist/index.html
  python3 scripts/check_parity.py <proto> --chrome "/path/to/Chrome" --keep

机制：用 headless Chrome 打开容器的两个 hash 入口
  #page=<id>              取渲染后的 DOM
  #page=<id>&export=md    取导出钩子写进 <pre id="export-out"> 的 Markdown
再拿 proto.json 做基准，逐项比对。

退出码：0 一致，1 不一致，2 跑不起来（没 Chrome / 没构建产物）。
"""
import argparse
import html as htmllib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

E, W = "ERROR", "WARN"
issues = []


def add(level, code, msg):
    issues.append((level, code, msg))


CHROMES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]


def find_chrome(explicit=None):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    for c in CHROMES:
        if os.path.exists(c):
            return c
    for name in ("google-chrome", "chromium", "chrome", "msedge"):
        p = shutil.which(name)
        if p:
            return p
    return None


def run_chrome(chrome, url, timeout=40):
    cmd = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
           "--hide-scrollbars", "--window-size=1440,1200",
           "--virtual-time-budget=3500", "--dump-dom", url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout or ""


def extract_export(dom):
    m = re.search(r'<pre id="export-out">(.*?)</pre>', dom, re.S)
    return htmllib.unescape(m.group(1)) if m else None


def section(md, title_kw):
    """取 MD 里 `## ...关键词...` 到下一个 `## ` 之间的内容。"""
    lines = md.splitlines()
    out, on = [], False
    for ln in lines:
        if ln.startswith("## "):
            on = title_kw in ln
            continue
        if on:
            out.append(ln)
    return "\n".join(out)


def table_body(block):
    rows = []
    for ln in (block or "").splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        if re.match(r"^\|[\s:\-|]+\|$", s):
            continue
        rows.append([c.strip() for c in s.strip("|").split("|")])
    return rows[1:] if rows else []


def visible_html(dom):
    """剔掉内联的 <script>/<style>。

    单文件容器把组件源码也内联进 HTML，直接搜文本会把源码里的字符串当成页面内容
    （比如 Fallback 组件里就写着「未登记组件」，一搜必中）。
    """
    dom = re.sub(r"<script\b[^>]*>.*?</script>", "", dom, flags=re.S | re.I)
    dom = re.sub(r"<style\b[^>]*>.*?</style>", "", dom, flags=re.S | re.I)
    return dom


def first_head_cells(dom):
    """表头第一行的单元格数。"""
    i = dom.find('class="dt-head"')
    if i < 0:
        return None
    j = dom.find('class="dt-row"', i)
    if j < 0:
        j = dom.find("</div></div>", i)
    if j < 0:
        j = i + 4000
    return dom.count('class="dt-cell', i, j)


def walk(node, out):
    out.append(node)
    for c in node.get("children") or []:
        walk(c, out)
    return out


def check(proto_path, html_path, chrome):
    proto = json.load(open(proto_path, encoding="utf-8"))
    base = "file://" + os.path.abspath(html_path)
    pages = proto.get("pages") or []
    caps = proto.get("capabilities") or []
    reqs = proto.get("requirements") or []
    sms = proto.get("stateMachines") or []

    state_keys = set()
    for sm in sms:
        for st in sm.get("states") or []:
            state_keys.add(st.get("key"))
    state_keys.discard(None)

    cap_ids = {c.get("id") for c in caps}
    tmpdir = tempfile.mkdtemp(prefix="iiot-parity-")

    for pg in pages:
        pid = pg.get("id")
        title = (pg.get("title") or "").strip()
        route = pg.get("route") or ""

        dom = run_chrome(chrome, base + "#page=" + pid)
        if not dom.strip():
            add(E, "C-00", f"页面 {pid} 渲染出空 DOM（容器打不开）")
            continue
        open(os.path.join(tmpdir, pid + ".dom.html"), "w", encoding="utf-8").write(dom)

        # ---- 容器侧 ----
        vis = visible_html(dom)
        if 'id="boot-error"' in vis:
            add(E, "C-01", f"页面 {pid} 出现 boot-error：容器启动失败")
        if "未登记组件" in vis:
            miss = sorted(set(re.findall(r"未登记组件：([A-Za-z0-9_]+)", vis)))
            add(E, "C-02", f"页面 {pid} 有组件降级成虚线框：{', '.join(miss) or '(类型名未输出)'}")

        m = re.search(r'class="app-title[^"]*">([^<]*)<', vis)
        dom_title = (m.group(1).strip() if m else None)
        if dom_title is None:
            m2 = re.search(r'class="pda-title[^"]*">([^<]*)<', vis)
            dom_title = m2.group(1).strip() if m2 else None
        if dom_title is not None and dom_title != title:
            add(E, "C-03", f"页面 {pid}：契约标题「{title}」≠ 容器页头「{dom_title}」")

        # 表格列数 vs 契约列定义
        nodes = walk(pg.get("componentTree") or {}, [])
        tables = [n for n in nodes if n.get("type") == "DataTable"]
        if tables:
            cols = (tables[0].get("props") or {}).get("columns") or []
            head_n = first_head_cells(dom)
            if head_n is not None and head_n != len(cols):
                add(E, "C-09", f"页面 {pid}：契约 {len(cols)} 列，容器渲染 {head_n} 列")

        # ---- 导出侧 ----
        dom_md = run_chrome(chrome, base + "#page=" + pid + "&export=md")
        open(os.path.join(tmpdir, pid + ".export.html"), "w", encoding="utf-8").write(dom_md)
        md = extract_export(dom_md)
        if md is None:
            add(E, "C-04", f"页面 {pid} 的 #export=md 钩子没产出内容")
            continue
        open(os.path.join(tmpdir, pid + ".md"), "w", encoding="utf-8").write(md)

        head_line = md.splitlines()[0] if md.splitlines() else ""
        if title not in head_line:
            add(E, "C-05", f"页面 {pid}：导出 MD 首行「{head_line}」不含页面标题「{title}」")
        if "undefined" in md:
            bad = [ln.strip()[:60] for ln in md.splitlines() if "undefined" in ln][:3]
            add(E, "C-06", f"页面 {pid}：导出 MD 出现 undefined（字段名不对）：{' / '.join(bad)}")
        if route and route not in md:
            add(E, "C-07", f"页面 {pid}：导出 MD 里没有路由 {route}")

        # 动作可用性表：行数、内部标识泄漏、状态 key 泄漏
        avail = section(md, "动作可用性")
        rows = table_body(avail)
        if len(rows) != len(caps):
            add(E, "C-08", f"页面 {pid}：可用性表 {len(rows)} 行，契约 {len(caps)} 条命令（漏了或多写了）")
        leak_cap = re.findall(r"\bcap-[A-Za-z0-9_-]+", avail)
        leak_usr = re.findall(r"\bu-[a-z]+[A-Za-z0-9_-]*", avail)
        if leak_cap or leak_usr:
            add(E, "C-10", f"页面 {pid}：可用性表泄漏内部标识 {sorted(set(leak_cap + leak_usr))[:4]}")
        leak_state = [r for r in rows for cell in r[2:3] for k in state_keys
                      if k and re.search(r"(?<![A-Za-z])" + re.escape(k) + r"(?![A-Za-z])", cell)]
        if leak_state:
            add(E, "C-11", f"页面 {pid}：可用状态列显示状态 key 而非中文名：{sorted(set(leak_state))[:4]}")

        # 需求条目是否都导出
        mine = [r for r in reqs if pid in (r.get("pageIds") or [])]
        miss_req = [r.get("id") for r in mine if r.get("id") not in md]
        if miss_req:
            add(E, "C-12", f"页面 {pid}：导出 MD 缺需求 {miss_req}")

    # 全站：命令 id 必须都有中文名，否则任何视图都会露出 cap-xxx
    for c in caps:
        if not c.get("label"):
            add(E, "C-13", f"命令 {c.get('id')} 没有 label，导出与状态流只能显示 id")

    # ---- C-21 数据层：to 命令的 from，在 mock 数据里必须真有对应行 ----
    # 承载用例（R-10）打不开有两种原因，这条只接"数据没铺到"那一半。
    # 报在数据层，是因为修法在数据层——要么 from 写错了，要么数据没铺到；
    # 引擎没错，别让 R-10 替它背这口锅（同一根因只在一个层级报红）。
    # 造红提示：这条判的是"这个状态在数据里有没有行"，不是"状态名合不合理"。
    # 我第一次拿 from=['closed'] 造红没红，因为台账里真有一行「已关闭」——
    # 换 from=['done']（措施状态，事故台账里不存在）才红。造红失败时先怀疑造红，再怀疑判据。
    label_of, states_of = {}, {}
    for sm in sms:
        states_of[sm.get("entity")] = {st.get("key") for st in (sm.get("states") or [])}
        for st in sm.get("states") or []:
            label_of[st.get("key")] = st.get("label")
    for c in caps:
        if not c.get("to") or not c.get("from"):
            continue
        hosts = []      # (page_id, 该列状态字段, 行数据)
        for pg in pages:
            for n in walk(pg.get("componentTree") or {}, []):
                props = n.get("props") if isinstance(n.get("props"), dict) else {}
                for col in (props.get("columns") if isinstance(props.get("columns"), list) else []):
                    # 只有 scope==row 的列才按行判状态；没有 scope 的操作列吃单据状态，
                    # 它的 from 跟 data[] 没有关系，拿去求交集会误报"数据没铺到"
                    if not isinstance(col, dict) or col.get("type") != "action" or col.get("scope") != "row":
                        continue
                    if any(isinstance(a, dict) and a.get("capability") == c.get("id")
                           for a in (col.get("actions") if isinstance(col.get("actions"), list) else [])):
                        data = props.get("data")
                        hosts.append((pg.get("id"), col.get("stateKey") or "status",
                                      data if isinstance(data, list) else []))
        if hosts:
            # cap.from 是状态 key，data[].{stateKey} 存的是 label，两边都要认
            want = set()
            for k in c.get("from"):
                want.add(k)
                if label_of.get(k):
                    want.add(label_of[k])
            hit = any(isinstance(row, dict) and row.get(sk) in want
                      for _, sk, data in hosts for row in data)
            if not hit:
                add(E, "C-21",
                    f"命令 {c.get('id')} 的 from={c.get('from')} 在「{hosts[0][0]}」的表格数据里没有任何一行"
                    f"（该列状态字段 {hosts[0][1]}）：要么 from 写错了，要么数据没铺到")
        else:
            # 表级/表单级命令没有 data，只能拿状态机全集判"这个状态名存不存在"
            unknown = [k for k in c.get("from") if k not in states_of.get(c.get("entity"), set())]
            if unknown:
                add(E, "C-21",
                    f"命令 {c.get('id')} 的 from={unknown} 不在 {c.get('entity')} 的状态机里：状态写错了")

    return tmpdir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("proto")
    ap.add_argument("--html", default=None, help="容器产物，默认 assets/container/dist/index.html")
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--keep", action="store_true", help="保留抓取到的 DOM 与 MD 便于排查")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = args.html or os.path.join(root, "assets", "container", "dist", "index.html")
    if not os.path.exists(html_path):
        print(f"找不到容器产物：{html_path}\n先跑 build.py 或指定 --html", file=sys.stderr)
        return 2
    chrome = find_chrome(args.chrome)
    if not chrome:
        print("找不到 Chrome/Chromium，三处一致校验必须在真实浏览器里跑（读不到 DOM 就无法比对）",
              file=sys.stderr)
        return 2

    tmpdir = check(args.proto, html_path, chrome)

    errors = [i for i in issues if i[0] == E]
    warns = [i for i in issues if i[0] == W]
    print(f"三处一致校验：{os.path.basename(args.proto)}")
    print(f"容器：{os.path.relpath(html_path, os.getcwd())}")
    print("-" * 66)
    for level, code, msg in issues:
        print(f"[{level:5}] {code:6} {msg}")
    if not issues:
        print("[OK   ] PASS   契约 / 容器 DOM / 导出 MD 三处一致")
    print("-" * 66)
    print(f"结果：ERROR={len(errors)}  WARN={len(warns)}  {'一致' if not errors else '不一致'}")
    if args.keep:
        print(f"抓取结果保留在：{tmpdir}")
    else:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
