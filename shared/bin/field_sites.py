#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
渲染位抽取（唯一实现）。

`fieldCatalog` 是业务字段主档，组件 props 上的 `field` 是"这一处画的是哪个字段"。
要做双向绑定，先得有一份"原型上到底有哪些数据渲染位"的清单——
`check_contract.py`（L2-96~101）与 `check_interact.py`（R-11/R-12）共用本模块。

为什么要单独一个文件：复制两份必然漂移，下一轮就会出现
"契约说缺 3 个、交互脚本说都登记了"。只许有一份。

抽取范围（规格 2026-11-09 v2.1 §4）：
  FilterBar.fields       → filter
  FormGrid.fields/items  → form
  DataTable.columns      → column（排除 type=action / index）
  DescList.items         → desc
  capabilities[].ui.fields → dialog（归属页由 cap.owns 反推）

不算渲染位：操作列、序号列、状态条、时间线、按钮、KPI、图表、进度条。

归属页只认两种（硬约束 5）：组件树内用 (pageId, nodeId)，弹层用 cap.owns。
**禁止按节点 id 全局反查页面**——n-root/n-page/n-table 在多页重复。
"""


def walk_tree(node, out=None):
    out = [] if out is None else out
    out.append(node)
    for c in node.get("children") or []:
        walk_tree(c, out)
    return out


def _readonly(f):
    """只读有两种写法，必须都认（规格 §1.5）。

    弹层用控件类型 type:"readonly"；页面表单用布尔 prop readonly:true。
    实测 09-41 的 5 个弹层只读字段是前者，它们的 readonly 布尔全是 false——
    只认布尔会把预填字段误判成录入位，L2-99/100 直接假红。
    """
    return f.get("type") == "readonly" or bool(f.get("readonly"))


def _site(page_id, node_id, raw, kind, label, cap_id=None):
    key = raw.get("key")
    # 位置身份：树内用容器节点 id，弹层用 capId。
    # 只带 key 会撞——同一页「筛选/列/弹层」常画同一个 key（dept 一页三次）。
    site_id = cap_id or node_id
    biz = raw.get("field") or key
    ro = _readonly(raw)
    if kind in ("form", "dialog"):
        scope = "out" if ro else "in"
    elif kind in ("column", "desc"):
        scope = "out"
    else:  # filter
        scope = "filter-field" if raw.get("field") else "filter-cond"
    return {
        "page_id": page_id,
        "node_id": node_id,
        "site_id": site_id,
        "cap_id": cap_id,
        "kind": kind,
        "key": key,
        "biz": biz,
        "label": label,
        # 界面文案：列头用 title、详情用 label、表单用 label、筛选用 label
        "scope": scope,
        "readonly": ro,
        "has_field": bool(raw.get("field")),
        "has_filter_note": bool(raw.get("filterNote")),
        "missing_key": "key" not in raw,
        "raw": raw,
    }


def render_sites(proto):
    """返回原型上全部数据渲染位。顺序 = 逐页 + 组件树先序（PRD 章节顺序按它）。"""
    out = []
    owns_of = {}
    for pg in proto.get("pages") or []:
        for cid in ((pg.get("contract") or {}).get("owns") or []):
            owns_of.setdefault(cid, pg.get("id"))

    for pg in proto.get("pages") or []:
        pid = pg.get("id")
        for nd in walk_tree(pg.get("componentTree") or {}):
            pr = nd.get("props") or {}
            t = nd.get("type")
            if t == "FilterBar":
                for f in pr.get("fields") or []:
                    out.append(_site(pid, nd.get("id"), f, "filter", f.get("label")))
            elif t == "FormGrid":
                for f in pr.get("fields") or pr.get("items") or []:
                    out.append(_site(pid, nd.get("id"), f, "form", f.get("label")))
            elif t == "DataTable":
                for c in pr.get("columns") or []:
                    # 序号列只渲染行号，不取 row[key]（components.js:343）；算进来等于给"序号"编假字段
                    if c.get("type") in ("action", "index"):
                        continue
                    out.append(_site(pid, nd.get("id"), c, "column", c.get("title")))
            elif t == "DescList":
                for it in pr.get("items") or []:
                    out.append(_site(pid, nd.get("id"), it, "desc", it.get("label")))

    for cap in proto.get("capabilities") or []:
        cid = cap.get("id")
        for f in (cap.get("ui") or {}).get("fields") or []:
            out.append(_site(owns_of.get(cid), None, f, "dialog", f.get("label"), cap_id=cid))
    return out


def block_id(site, idx=0):
    """PRD 里的块 id / DOM 锚点。三段的第三段用 site_id，重复 key 才不会撞。"""
    return "field-%s-%s-%s" % (site["page_id"], site["site_id"] or "no-site",
                               site["key"] or ("x%d" % idx))


def bound_sites(proto, catalog_keys):
    """已绑定的渲染位：能拿到业务键且该键在主档里。"""
    return [s for s in render_sites(proto)
            if not s["missing_key"] and s["biz"] in catalog_keys]


def catalog_index(proto):
    return {f.get("key"): f for f in proto.get("fieldCatalog") or []}
