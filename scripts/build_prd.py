#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把契约装配成一份可交出去的 PRD（五部分）。

原则：**页面规格不手写**。命令表、校验规则、字段字典全从契约与渲染位推出来，
人手再描述一遍就会出现「PRD 说 10 列、原型 11 列」这种只有评审才发现的漂移。

字段字典是 C-22 的比较对象：4.1 主档表 = fieldCatalog 声明顺序；
4.2 每页逐位块 = 该页 render_sites 的组件树先序，块 id = field-{pageId}-{key}。

用法：
    python3 scripts/build_prd.py --proto <proto.json> --out <PRD.md>
    python3 scripts/build_prd.py --proto ... --out ... --shaping <shaping 目录>
"""
import argparse
import hashlib
import json
import os
import sys
import time

import field_sites

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def label_of_state(proto):
    out = {}
    for sm in proto.get("stateMachines") or []:
        for s in sm.get("states") or []:
            out[s.get("key")] = s.get("label") or s.get("key")
    return out


def actors_of(proto, ids):
    m = {a.get("id"): a.get("name") or a.get("id") for a in (proto.get("actors") or [])}
    return "、".join(m.get(i, i) for i in (ids or [])) or "不限"


def site_local_text(s):
    """这一处的口径：录入看 rules，展示看 display.empty，筛选看 filterNote。"""
    r = (s["raw"].get("rules") or {}).get("text")
    d = (s["raw"].get("display") or {}).get("empty")
    f = s["raw"].get("filterNote")
    if r or d or f:
        return r or d or f
    # 字段筛选没写额外口径时，本身就是「按这个字段的值筛」，比留一个「未声明」清楚
    return "按该字段值筛选" if s["scope"] == "filter-field" else "未声明"


def scope_text(s):
    return {"in": "录入", "out": "展示", "filter-field": "字段筛选", "filter-cond": "条件筛选"}.get(s["scope"], s["scope"])


def local_label(s):
    """本处口径的标题按形态说人话：录入看规则、展示看空值、筛选看口径。"""
    return {"in": "校验规则", "out": "空值显示",
            "filter-field": "筛选口径", "filter-cond": "筛选口径"}.get(s["scope"], "本处口径")


def source_text(proto, src):
    ds = {d.get("id"): d for d in (proto.get("dataSources") or [])}.get((src or {}).get("ds"))
    if not ds:
        return "未声明"
    k = {"entity": "实体", "dict": "字典", "calc": "计算", "api": "接口", "system": "系统"}.get(ds.get("kind"), ds.get("kind"))
    ref = ds.get("ref") or ""
    fld = (src or {}).get("field")
    # dict 的 ref 本身就是「实体.字段」，再拼一次 field 会打成 accident.level.level
    if fld and not ref.endswith("." + fld):
        where = ref + "." + fld
    else:
        where = (src or {}).get("rule") or ref
    fb = (src or {}).get("fallback")
    return "%s · %s%s" % (k, where, ("；兜底：" + fb) if fb else "")


def target_text(t):
    return "%s.%s" % (t.get("entity"), t.get("field")) if t else "不落库"


def caps_of_page(proto, page):
    """本页渲染的命令（含行内），按组件树顺序。"""
    out, seen = [], set()
    for nd in field_sites.walk_tree(page.get("componentTree") or {}):
        pr = nd.get("props") or {}
        refs = [pr.get("capability")]
        refs += [a.get("capability") for a in (pr.get("actions") or []) if isinstance(a, dict)]
        cols = pr.get("columns")
        for c in (cols if isinstance(cols, list) else []):
            if isinstance(c, dict):
                refs += [a.get("capability") for a in (c.get("actions") or []) if isinstance(a, dict)]
        for cid in refs:
            if cid and cid not in seen:
                seen.add(cid)
                out.append(cid)
    return out


def build(proto, shaping_dir=None, source_path=None):
    meta = proto.get("meta") or {}
    sms = proto.get("stateMachines") or []
    pages = proto.get("pages") or []
    caps = {c.get("id"): c for c in (proto.get("capabilities") or [])}
    cat = proto.get("fieldCatalog") or []
    cat_by = {f.get("key"): f for f in cat}
    st = label_of_state(proto)
    L = []

    def h1(t):
        L.extend(["# " + t, ""])

    def h2(t):
        L.extend(["## " + t, ""])

    def h3(t):
        L.extend(["### " + t, ""])

    h1("%s · 产品需求文档" % (meta.get("product") or "未命名产品"))
    if source_path:
        with open(source_path, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()[:16]   # 契约文件字节级，不做 JSON 规范化
        L.append("> 生成源：%s @ sha256:%s（build_prd v1.2，%s）" %
                 (os.path.basename(source_path), sha, time.strftime("%Y-%m-%d %H:%M")))
    L.append("> 由 `scripts/build_prd.py` 从 `%s` 生成；字段字典与契约同源，改契约前请勿手改本文。" % os.path.basename(meta.get("source") or "proto.json"))
    L.append("> 版本 %s ｜ 生成于 %s" % (meta.get("version") or "-", meta.get("release", {}).get("date") or "-"))
    L.append("")

    # ---------------- 1 背景与目标 ----------------
    h2("1 背景与目标")
    h3("1.1 要解决的问题")
    for d in (proto.get("decisions") or []):
        if d.get("active", True):
            L.append("- " + (d.get("decision") or d.get("title") or ""))
            if d.get("rationale"):
                L.append("  - 理由：" + d["rationale"])
    if not (proto.get("decisions") or []):
        L.append("- （契约未登记决策，见 openQuestions）")
    L.append("")
    h3("1.2 目标与度量")
    L.append("- 端：%s" % "、".join(meta.get("targets") or []))
    L.append("- 页面：%d 个 ｜ 命令：%d 条 ｜ 业务字段：%d 个" % (len(pages), len(caps), len(cat)))
    L.append("")
    h3("1.3 非目标")
    for q in (proto.get("openQuestions") or []):
        if q.get("status") not in ("resolved", "assumed"):
            L.append("- 未决（%s）：%s" % (q.get("priority") or "-", q.get("question") or ""))
    L.append("")
    h3("1.4 角色")
    L.append("| 角色 | 说明 |")
    L.append("|---|---|")
    for a in (proto.get("actors") or []):
        L.append("| %s | %s |" % (a.get("name") or a.get("id"), a.get("desc") or a.get("note") or ""))
    L.append("")

    # ---------------- 2 业务流程与状态机 ----------------
    h2("2 业务流程与状态机")
    h3("2.1 业务流程")
    for sm in sms:
        L.append("- %s：%s" % (sm.get("label") or sm.get("id"),
                               " → ".join(st.get(x.get("key"), x.get("label") or x.get("key")) for x in (sm.get("states") or []))))
    L.append("")
    h3("2.2 状态机")
    for sm in sms:
        L.append("```mermaid")
        L.append("stateDiagram-v2")
        for x in (sm.get("states") or []):
            L.append("  state \"%s\" as %s" % (x.get("label") or x.get("key"), x.get("key")))
        L.append("  [*] --> %s" % sm.get("initial"))
        for t in (sm.get("transitions") or []):
            lbl = "系统" if t.get("system") else (caps.get(t.get("trigger"), {}).get("label") or t.get("trigger") or "")
            L.append("  %s --> %s : %s" % (t.get("from"), t.get("to"), lbl))
        L.append("```")
        L.append("")
    h3("2.3 按钮可用性矩阵")
    L.append("| 命令 | 角色 | 可用状态 | 不可用策略 | 提示 |")
    L.append("|---|---|---|---|---|")
    for c in (proto.get("capabilities") or []):
        L.append("| %s | %s | %s | %s | %s |" % (
            c.get("label") or c.get("name") or c.get("id"),
            actors_of(proto, c.get("actor")),
            "、".join(st.get(k, k) for k in (c.get("from") or [])) or "不限",
            c.get("policy") or "-", c.get("reason") or "-"))
    L.append("")
    h3("2.4 业务规则（guards）")
    if not (proto.get("guards") or []):
        L.append("- （契约未登记 guards）")
    else:
        L.append("| 规则 | 挂哪条命令 | 不满足时的界面表现 | 可判定形式 |")
        L.append("|---|---|---|---|")
        for g in (proto.get("guards") or []):
            cap = caps.get(g.get("capabilityId")) or {}
            L.append("| %s | %s | %s | %s |" % (
                g.get("statement") or "-",
                cap.get("label") or g.get("capabilityId") or "全局（提交时统一校验）",
                g.get("message") or "—（未单独提示，随命令置灰）",
                ("`%s`" % g["expr"]) if g.get("expr") else "—"))
        L.append("")
        L.append("- 角色限制不写在本列：权限不足时入口不出现（R-06），本列只写\"条件不满足\"的提示。")
        L.append("- 若某条规则依赖\"人是否相同\"，只能在提交时校验（选人之前无法预判），由开发在提交接口校验并返回本条 message；原型不预置灰。")
        L.append("- 与 `from` 的分工：`from` 判\"状态是否允许\"，本列说明\"为什么不允许\"，两层不合并。")
    L.append("")
    L[:] = L[:-1] if len(L) >= 2 and L[-1] == "" and L[-2] == "" else L

    # ---------------- 3 功能说明 ----------------
    h2("3 功能说明")
    h3("3.1 页面地图")
    for p in pages:
        L.append("- %s（%s，%s）" % (p.get("title"), p.get("id"), p.get("route")))
    L.append("")
    for pi, p in enumerate(pages):
        sec = "3.%d" % (2 + pi)          # 3.2 / 3.3 / 3.4… 不能四页都叫 3.2
        h3("%s %s" % (sec, p.get("title") or p.get("id")))
        ct = p.get("contract") or {}
        sn = 1                            # 子节号连续，缺节不留空号

        def sub(title):
            nonlocal sn
            L.append("**%s.%d %s**" % (sec, sn, title))
            L.append("")
            sn += 1

        sub("页面职责")
        L.append("- 任务：" + (ct.get("task") or "-"))
        L.append("- 角色：" + actors_of(proto, ct.get("actor")))
        L.append("- 完成条件：" + (ct.get("doneWhen") or "-"))
        L.append("")
        sub("功能逻辑")
        L.append("| 按钮 | 角色 | 前置状态 | 后置状态 | 幂等 | 失败处理 |")
        L.append("|---|---|---|---|---|---|")
        for cid in caps_of_page(proto, p):
            c = caps.get(cid) or {}
            L.append("| %s | %s | %s | %s | %s | %s |" % (
                c.get("label") or cid, actors_of(proto, c.get("actor")),
                "、".join(st.get(k, k) for k in (c.get("from") or [])) or "不限",
                st.get(c.get("to"), c.get("to")) if c.get("to") else "-",
                "按实体状态机" if c.get("to") else "-", c.get("reason") or "-"))
        L.append("")
        sub("交互逻辑")
        ixs = p.get("interactions") or []
        if not ixs:
            L.append("- （本页无声明交互）")
        for ix in ixs:
            L.append("- %s → %s（%s）" % (ix.get("on"), ix.get("target"), ix.get("do")))
        L.append("")
        sub("校验规则")
        ins = [s for s in field_sites.render_sites(proto) if s["page_id"] == p.get("id") and s["scope"] == "in"]
        if not ins:
            L.append("- （本页无录入位）")
        for s in ins:
            L.append("- %s：%s" % (s["label"] or s["key"], (s["raw"].get("rules") or {}).get("text") or "未声明"))
        L.append("")
        # guard 挂在命令上，命令归 owns 页；不能靠 guard.pageId（契约里没有这个字段）
        owns = set((p.get("contract") or {}).get("owns") or [])
        gs = [g for g in (proto.get("guards") or []) if g.get("capabilityId") in owns]
        if gs:
            sub("异常分支")
            for g in gs:
                L.append("- %s：%s%s" % (g.get("id") or "", g.get("statement") or "",
                                        ("（`%s`）" % g["expr"]) if g.get("expr") else ""))
            L.append("")
        sub("验收要点")
        rs = [r for r in (proto.get("requirements") or []) if p.get("id") in (r.get("pageIds") or [])]
        for r in rs:
            L.append("- %s %s" % (r.get("id"), r.get("title")))
        if not rs:
            L.append("- （无关联需求）")
        L.append("")

    # ---------------- 4 字段字典 ----------------
    h2("4 字段字典")
    h3("4.1 字段主档")
    # 「需求出处」整列全空就不渲染：一列占位符只稀释真正有值的列，
    # 将来谁填了 reqRefs，这一列自动出现
    has_refs = any((f.get("reqRefs") or []) for f in cat)
    if has_refs:
        L.append("| 字段 | key | 来源 | 去向 | 需求出处 |")
        L.append("|---|---|---|---|---|")
    else:
        L.append("| 字段 | key | 来源 | 去向 |")
        L.append("|---|---|---|---|")
    for f in cat:
        row = "| %s | %s | %s | %s |" % (
            f.get("label"), f.get("key"), source_text(proto, f.get("source")),
            target_text(f.get("target")))
        if has_refs:
            row += " %s |" % ("、".join(f.get("reqRefs") or []) or "—")
        L.append(row)
    L.append("")
    for pi, p in enumerate(pages):
        ss = [s for s in field_sites.render_sites(proto) if s["page_id"] == p.get("id")]
        if not ss:
            continue
        sec = "4.%d" % (2 + pi)
        h3("%s %s" % (sec, p.get("title") or p.get("id")))
        sn = 1

        def sub4(title):
            nonlocal sn
            L.append("**%s.%d %s**" % (sec, sn, title))
            L.append("")
            sn += 1

        sub4("本页取数链路")
        L.append("| 数据源 | 类型 | 取值 | 喂给哪些字段 | 兜底 |")
        L.append("|---|---|---|---|---|")
        feed = {}
        for s in ss:
            f = cat_by.get(s["biz"])
            if not f:
                continue
            dsid = ((f.get("source") or {}).get("ds")) or "?"
            # 同一业务字段在多处渲染只列一次；重复列会让"喂给哪些字段"看起来像两个字段
            feed.setdefault(dsid, {})[f.get("key")] = f.get("label")
        dsmap = {d.get("id"): d for d in (proto.get("dataSources") or [])}
        for dsid, names in feed.items():
            ds = dsmap.get(dsid) or {}
            srcs = [f.get("source") or {} for f in cat if ((f.get("source") or {}).get("ds") == dsid)]
            fb = next((x.get("fallback") for x in srcs if x.get("fallback")), "-")
            L.append("| %s | %s | %s | %s | %s |" % (
                dsid, ds.get("kind") or "-", ds.get("ref") or "-", "、".join(names.values()), fb))
        L.append("")
        sub4("本页渲染位速查")
        L.append("| 位置 | 文案 | 引用字段 | 形态 | 本处口径 |")
        L.append("|---|---|---|---|---|")
        for s in ss:
            f = cat_by.get(s["biz"])
            L.append("| %s / %s | %s | %s | %s | %s |" % (
                s["kind"], s["site_id"] or "-", s["label"] or s["key"],
                (f.get("label") + "（" + f.get("key") + "）") if f else "未绑定",
                scope_text(s), site_local_text(s)))
        L.append("")
        sub4("逐位说明")
        for i, s in enumerate(ss):
            f = cat_by.get(s["biz"])
            L.append("#### %s %s" % (field_sites.block_id(s, i), s["label"] or s["key"]))
            L.append("")
            L.append("- 形态：" + scope_text(s))
            L.append("- %s：%s" % (local_label(s), site_local_text(s)))
            L.append("- 业务字段：" + ((f.get("label") + "（" + f.get("key") + "）") if f else "未绑定"))
            L.append("- 来源：" + (source_text(proto, f.get("source")) if f else "—"))
            L.append("- 去向：" + (target_text(f.get("target")) if f else "—"))
            L.append("")

    # ---------------- 5 数据、分批与验收 ----------------
    h2("5 数据、分批与验收")
    h3("5.1 数据模型")
    for e in ((proto.get("dataModel") or {}).get("entities") or []):
        L.append("- %s（%s）：%s" % (e.get("label") or e.get("id"), e.get("id"),
                                    "、".join(f.get("name") for f in (e.get("fields") or []))))
    for d in ((proto.get("dataModel") or {}).get("derived") or []):
        L.append("- 派生 %s = `%s`（兜底：%s）" % (d.get("name"), d.get("expr"), d.get("fallback")))
    L.append("")
    h3("5.2 分批")
    sl = []
    for x in (proto.get("slices") or []):
        sl.append(x if isinstance(x, str) else (x.get("name") or x.get("id") or "?"))
    L.append("- 切片：" + ("、".join(sl) or "未分批"))
    L.append("")
    h3("5.3 验收清单")
    for r in (proto.get("requirements") or []):
        L.append("- %s %s（%s）" % (r.get("id"), r.get("title"), r.get("priority")))
        for a in (r.get("acceptance") or []):
            L.append("  - [%s] 给定 %s，当 %s，则 %s" % (
                "非法路径" if a.get("kind") == "illegal" else "主路径",
                a.get("given"), a.get("when"), a.get("then")))
    L.append("")
    h3("5.4 决策与未决")
    for d in (proto.get("decisions") or []):
        L.append("- %s：%s" % (d.get("id"), d.get("decision") or d.get("title") or ""))
    for q in (proto.get("openQuestions") or []):
        L.append("- %s：%s（%s）" % (q.get("id"), q.get("question"), q.get("status")))
    L.append("")
    h3("5.5 已知限制")
    L.append("- 取数链路只到「数据源/取值」两层，不下钻接口与库表字段。")
    L.append("- 外部字典与接口类数据源无法机器核对，只有 note 说明。")
    L.append("")
    if shaping_dir:
        L.extend(["## 附录 A 澄清原文", ""])
        for fn in sorted(os.listdir(shaping_dir)):
            if fn.endswith(".md"):
                L.append("- " + fn)
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proto", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--shaping", default=None)
    args = ap.parse_args()
    proto = load(args.proto)
    md = build(proto, args.shaping, args.proto)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)
    print("written: %s (%d 行)" % (args.out, md.count("\n") + 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
