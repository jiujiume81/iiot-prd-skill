#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IIOT-PRD 契约校验器（L1 结构 + L2 语义）

用法：
  python3 tools/check_contract.py examples/example-00-minimal.proto.json
  python3 tools/check_contract.py --plan examples/example-00-slices.json

设计原则：每条判据都要能真红。答不出「什么输入能让它红」的判据不写。
L3（宽度闭合 / 折行 / 表头被裁 / 截图非空白）读不到 JSON，必须在容器里跑，见 check_ui_shape。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "schemas", "catalog.json")

E, W = "ERROR", "WARN"
issues = []


def add(level, code, msg):
    issues.append((level, code, msg))


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def walk(node, out):
    out.append(node)
    for c in node.get("children") or []:
        walk(c, out)
    return out


def pg_reachable(it, mod_ids):
    """页面目录的分组（含子组）里有没有任何一页属于本模块。"""
    if it.get("page") in mod_ids:
        return True
    return any(pg_reachable(c, mod_ids) for c in (it.get("children") or []))


def nav_reachable(it, pages, page_ids):
    """目录项（含其子项）有没有任何一个能落到真实页面。"""
    if it.get("page") in page_ids:
        return True
    if any(nav_reachable(c, pages, page_ids) for c in (it.get("children") or [])):
        return True
    lab = it.get("label") or ""
    return any(x.get("layout") != "detail" and (x.get("title") == lab or x.get("navLabel") == lab)
               for x in pages)


def collect_capability_refs(nodes):
    refs = []
    for n in nodes:
        p = n.get("props") or {}
        if p.get("capability"):
            refs.append((n["id"], p["capability"]))
        for a in p.get("actions") or []:
            if isinstance(a, dict) and a.get("capability"):
                refs.append((n["id"], a["capability"]))
        for col in (p.get("columns") if isinstance(p.get("columns"), list) else []) or []:
            for a in (col.get("actions") or []):
                if isinstance(a, dict) and a.get("capability"):
                    refs.append((n["id"], a["capability"]))
    return refs


def rendered_caps(pg):
    """本页组件树里实际渲染的 capId 集合。

    `capability` 有三种写法，漏一种就等于没看见那个按钮：
      ① 单按钮节点的 props.capability（PDA 的 BigAction 就是这样挂的）
      ② 工具栏 / 卡片的 props.actions[].capability
      ③ 表格列的 columns[].actions[].capability
    """
    nodes = walk(pg.get("componentTree") or {}, [])
    return {cid for _, cid in collect_capability_refs(nodes)}


def check_proto(proto, catalog):
    types = catalog["types"]
    cat_of = {k: v.get("category", "common") for k, v in types.items()}

    # ---------- L1 结构 ----------
    for k in ["schemaVersion", "meta", "modules", "pages", "capabilities",
              "stateMachines", "dataModel", "requirements", "components", "annotations"]:
        if k not in proto:
            add(E, "L1-01", f"顶层缺少必填字段 {k}")
    if proto.get("schemaVersion") != "1.0":
        add(E, "L1-02", f"schemaVersion 必须为 1.0，实际 {proto.get('schemaVersion')}")

    meta = proto.get("meta") or {}
    for k in ["product", "version", "domain", "targets", "designWidth"]:
        if not meta.get(k):
            add(E, "L1-03", f"meta 缺少 {k}")
    targets = meta.get("targets") or []
    dw = meta.get("designWidth") or {}
    for t in targets:
        if t not in dw:
            add(E, "L1-04", f"meta.designWidth 未给 {t} 端声明设计宽")

    pages = proto.get("pages") or []
    modules = proto.get("modules") or []
    caps = proto.get("capabilities") or []
    sms = proto.get("stateMachines") or []
    reqs = proto.get("requirements") or []
    anns = proto.get("annotations") or []

    # ---------- L2 A. ID 与归属 ----------
    for name, coll, key in [("modules", modules, "id"), ("pages", pages, "id"),
                            ("capabilities", caps, "id"), ("stateMachines", sms, "id"),
                            ("requirements", reqs, "id"), ("annotations", anns, "id")]:
        seen = set()
        for it in coll:
            i = it.get(key)
            if not i:
                add(E, "L2-01", f"{name} 存在缺 {key} 的条目")
            elif i in seen:
                add(E, "L2-02", f"{name} 的 {key} 重复：{i}")
            else:
                seen.add(i)

    # schema 里 page.required 是写了 route 的，但校验器不查就等于没有
    PAGE_REQ = ["id", "moduleId", "target", "route", "title", "layout",
                "states", "componentTree", "interactions", "prd"]
    for p in pages:
        for k in PAGE_REQ:
            if k not in p or p.get(k) in (None, ""):
                add(E, "L1-05", f"页面 {p.get('id')} 缺必填字段 {k}")
        if p.get("route") and not str(p.get("route")).startswith("/"):
            add(E, "L1-06", f"页面 {p.get('id')} 的 route={p.get('route')} 必须以 / 开头")

    actor_ids = {a.get("id") for a in (proto.get("actors") or [])}
    page_ids = {p.get("id") for p in pages}
    page_by_id = {p.get("id"): p for p in pages}
    cap_ids = {c.get("id") for c in caps}
    sm_ids = {s.get("id") for s in sms}

    owner = {}
    for m in modules:
        for pid in m.get("pages") or []:
            if pid not in page_ids:
                add(E, "L2-03", f"模块 {m.get('id')} 声明了不存在的页面 {pid}")
            owner[pid] = m.get("id")
    for p in pages:
        pid = p.get("id")
        if p.get("moduleId") not in {m.get("id") for m in modules}:
            add(E, "L2-04", f"页面 {pid} 的 moduleId={p.get('moduleId')} 不存在")
        elif owner.get(pid) != p.get("moduleId"):
            add(E, "L2-05", f"页面 {pid} 与模块 pages 列表不一致（module.pages 未收录或归属不同）")

    # ---------- L2 B. 端与时态 ----------
    for p in pages:
        pid = p.get("id")
        if p.get("target") not in targets:
            add(E, "L2-06", f"页面 {pid} 的 target={p.get('target')} 不在 meta.targets {targets} 内")

        kinds = {s.get("kind") for s in (p.get("states") or [])}
        na = set(p.get("notApplicableStates") or [])
        for need in ["default", "loading", "empty", "error"]:
            if need not in kinds and need not in na:
                add(E, "L2-07", f"页面 {pid} 缺少 {need} 态（也未在 notApplicableStates 声明）")
        if "zero-result" not in kinds and "zero-result" not in na and p.get("layout") in ("list", "pda-list"):
            add(W, "L2-08", f"页面 {pid} 是列表页但缺 zero-result 态（零结果与空态文案应不同）")

        sections = ((p.get("prd") or {}).get("sections") or [])
        stypes = [s.get("type") for s in sections]
        if "goal" not in stypes:
            add(E, "L2-09", f"页面 {pid} 的 PRD 缺 goal 小节")
        if "flow" not in stypes and (p.get("interactions") or []):
            add(W, "L2-10", f"页面 {pid} 有交互但没有 flow 流程图小节")
        for sec in sections:
            if sec.get("type") == "flow":
                ids = {n.get("id") for n in (sec.get("nodes") or [])}
                for e in (sec.get("edges") or []):
                    if e.get("from") not in ids or e.get("to") not in ids:
                        add(E, "L2-11", f"页面 {pid} 流程图边的端点不存在：{e.get('from')}→{e.get('to')}")
                for n in (sec.get("nodes") or []):
                    if n.get("kind") == "decision":
                        outs = [e for e in (sec.get("edges") or []) if e.get("from") == n.get("id")]
                        if any(not e.get("label") for e in outs):
                            add(E, "L2-12", f"页面 {pid} 判定节点 {n.get('id')} 的出边缺 label")

    # ---------- L2 C. 组件树 ----------
    for p in pages:
        pid = p.get("id")
        tree = p.get("componentTree") or {}
        nodes = walk(tree, [])
        nids = [n.get("id") for n in nodes]
        if len(nids) != len(set(nids)):
            add(E, "L2-13", f"页面 {pid} 组件树节点 id 重复")
        for n in nodes:
            t = n.get("type")
            if t not in types:
                add(E, "L2-14", f"页面 {pid} 节点 {n.get('id')} 的 type={t} 不在组件白名单内")
                continue
            # catalog 登记 ≠ 组件库实现。用未实现的组件，运行时会降级成虚线框，
            # 原型就变成残的；这条把"账实不符"从运行时问题提前到构建前
            if (types.get(t) or {}).get("impl") != "done":
                add(E, "L2-51", f"页面 {pid} 节点 {n.get('id')} 用了未实现的组件 {t}"
                                "（catalog.impl != done），运行时会降级成虚线框")
            cat = cat_of.get(t)
            if p.get("target") == "pda" and cat and cat.startswith("pc-"):
                add(E, "L2-15", f"PDA 页面 {pid} 引用了 PC 专用组件 {t}（节点 {n.get('id')}）")
            if p.get("target") == "pc" and cat == "pda":
                add(E, "L2-16", f"PC 页面 {pid} 引用了 PDA 组件 {t}（节点 {n.get('id')}）")
            if t == "DataTable":
                pr = n.get("props") or {}
                if pr.get("tableLayout") == "fixed":
                    for col in pr.get("columns") or []:
                        if not col.get("width"):
                            add(E, "L2-17", f"页面 {pid} 表格在 fixed 布局下第「{col.get('title')}」列缺 width")

        for src, cid in collect_capability_refs(nodes):
            if cid not in cap_ids:
                add(E, "L2-18", f"页面 {pid} 节点 {src} 引用了不存在的 capability {cid}")

        for ix in (p.get("interactions") or []):
            tgt = ix.get("target")
            doit = ix.get("do")
            # navigate 去的是页面；openModal/openDrawer 打开的是"哪条命令的承载层"，target 应是 capId
            if doit == "navigate" and tgt and tgt not in page_ids:
                add(E, "L2-19", f"页面 {pid} 的交互 {ix.get('id')} 跳转到不存在的页面 {tgt}")
            if doit in ("openDrawer", "openModal") and tgt and tgt not in cap_ids and tgt not in page_ids:
                add(E, "L2-19", f"页面 {pid} 的交互 {ix.get('id')} 打开的 target={tgt} 既不是命令也不是页面")

    # ---------- L2 C2. 推进型动作：状态化 + 承载声明 ----------
    # 这一组是给「过程排查 / 原因分析 / 措施下发 全塞进详情页」这类产出兜底的。
    # 详情页只读、推进动作落成命令、每条命令声明承载与入口，三条缺一条就会退回"一屏表单不知道先干啥"。
    cap_by_id = {c.get("id"): c for c in caps}
    for p in pages:
        pid = p.get("id")
        if p.get("layout") != "detail":
            continue
        for nd in walk(p.get("componentTree") or {}, []):
            if nd.get("type") in ("FormGrid",):
                add(E, "L2-54", f"详情页 {pid} 含可编辑表单 {nd.get('type')}（节点 {nd.get('id')}）："
                                "推进动作应做成命令 + 弹框/抽屉/独立页，详情页只读")

    UI_KINDS = ("inline", "dialog", "drawer", "page")
    for c in caps:
        cid = c.get("id")
        ui = c.get("ui") or {}
        kind = ui.get("kind")
        entry = ui.get("entry")
        if kind not in UI_KINDS:
            add(E, "L2-55", f"命令 {cid} 未声明 ui.kind（{'/'.join(UI_KINDS)}），"
                            "说不清这个动作弹框、抽屉还是整页，落地时就会堆进详情页")
            continue
        if not entry:
            add(E, "L2-55", f"命令 {cid} 未声明 ui.entry，无法判断按钮挂在哪")
        if kind == "page" and ui.get("pageId") not in page_ids:
            add(E, "L2-56", f"命令 {cid} 用独立页面承载，但 pageId={ui.get('pageId')} 不存在")

        if entry:
            hit = False
            for p in pages:
                nodes = walk(p.get("componentTree") or {}, [])
                nids = {n.get("id") for n in nodes}
                if entry in nids:
                    hit = True
                    break
                if "__act_" in entry:
                    base, akey = entry.split("__act_", 1)
                    node = [n for n in nodes if n.get("id") == base]
                    if node:
                        props = node[0].get("props") or {}
                        keys = [a.get("key") for a in (props.get("actions") or [])]
                        for col in props.get("columns") or []:
                            keys += [a.get("key") for a in (col.get("actions") or [])]
                        if akey in keys:
                            hit = True
                            break
            if not hit:
                add(E, "L2-55", f"命令 {cid} 的 ui.entry={entry} 在页面组件树里找不到对应节点或行内动作")

    # 状态机不能有进得去出不来的非终态
    for sm in sms:
        outs = {}
        for t in (sm.get("transitions") or []):
            outs.setdefault(t.get("from"), []).append(t)
        for st in (sm.get("states") or []):
            if st.get("terminal"):
                continue
            if not outs.get(st.get("key")):
                add(E, "L2-57", f"状态机 {sm.get('id')} 的状态「{st.get('label')}」没有出向迁移，"
                                "单据会永久卡在这一步")

    # 契约里声明的交互，引擎得真的实现，否则"能点"只存在于文档里
    IMPLEMENTED_DO = {"navigate", "openModal", "openDrawer", "setState", "submit", "toast", "reset"}
    for p in pages:
        pid = p.get("id")
        for ix in (p.get("interactions") or []):
            if ix.get("do") not in IMPLEMENTED_DO:
                add(E, "L2-59", f"页面 {pid} 的交互 {ix.get('id')} 用了引擎未实现的 do={ix.get('do')}，"
                                "原型上点了不会有任何反应")
            on = ix.get("on") or ""
            if not on:
                add(E, "L2-60", f"页面 {pid} 的交互 {ix.get('id')} 没有 on，绑不到任何元素")
            elif not on.startswith("__"):
                base = on.split("__")[0]
                nids = {n.get("id") for n in walk(p.get("componentTree") or {}, [])}
                if base not in nids:
                    add(E, "L2-60", f"页面 {pid} 的交互 {ix.get('id')} 绑定的节点 {base} 不在本页组件树内")

    # 目录是"能不能走到某一页"的承诺。目录写 A、页面做 B，评审时点过去就是空的。
    # 目录是树：只扫第一层会漏掉二级叶子，功能一多就会误判「列表页没入口」。
    has_shell = any(
        n.get("type") == "AppShell"
        for p in pages for n in walk(p.get("componentTree") or {}, [])
    )

    def walk_nav(items, depth=0, trails=()):
        for it in items or []:
            yield it, depth, trails
            for sub in walk_nav(it.get("children"), depth + 1,
                                trails + (it.get("label") or it.get("key") or "",)):
                yield sub

    nav_targets = set()
    for p in pages:
        pts = ((p.get("componentTree") or {}).get("props") or {})
        for g in (pts.get("groups") or []):
            seen_keys = {}
            for it, depth, trails in walk_nav(g.get("items")):
                lab = it.get("label") or ""
                where = " / ".join(trails + (lab,))
                # 折叠状态按 key 记，同层重名会让两个节点一起开合
                k = it.get("key")
                if k:
                    if k in seen_keys and seen_keys[k] == depth:
                        add(E, "L2-68", f"页面 {p.get('id')} 的目录里「{where}」和第 {depth + 1} 层的"
                                        f"另一项用了同一个 key={k}：折叠状态按 key 记，两项会一起开合")
                    seen_keys[k] = depth
                # 三层以上不是导航，是文件夹浏览器；真要这么深，说明该拆模块了
                if depth >= 3:
                    add(E, "L2-67", f"页面 {p.get('id')} 的目录「{where}」已经到第 {depth + 1} 层："
                                    "超过三层用户就不翻目录了，要么拆模块，要么合并同级")
                kids = it.get("children") or []
                pg_ref = it.get("page")
                if pg_ref:
                    if pg_ref not in page_ids:
                        add(E, "L2-61", f"页面 {p.get('id')} 的目录项「{where}」指向不存在的页面 {pg_ref}")
                    else:
                        nav_targets.add(pg_ref)
                    continue
                if kids:
                    # 分组本身不是目的地，要看它的孩子；孩子全是灰的，这组就是个空壳
                    if not any(nav_reachable(x, pages, page_ids) for x in kids):
                        add(E, "L2-69", f"页面 {p.get('id')} 的目录分组「{where}」展开后没有一项能到页面："
                                        "点它只能折叠，展开全灰，用户会以为整个模块都坏了")
                    continue
                # 没写 page 的，按标签去对页面名；对上了算能到达，对不上就是本原型没建模的模块
                hit = next((x for x in pages
                            if x.get("layout") != "detail"
                            and (x.get("title") == lab or x.get("navLabel") == lab)), None)
                if hit:
                    nav_targets.add(hit.get("id"))
    for p in pages:
        if not has_shell:
            break
        if p.get("layout") in ("list", "pda-list") and p.get("id") not in nav_targets:
            add(E, "L2-61", f"列表页 {p.get('id')}「{p.get('title')}」在目录里没有入口："
                            "用户只能靠直达链接才到得了，实际使用中等于不存在")

    # 页面目录（顶栏「目录」）的分组树。树比平铺更难自查：
    # 一页漏在树外就彻底找不到；一页挂在两个组里，改一处漏一处。
    mod_page_ids = {m.get("id"): set(m.get("pages") or []) for m in (proto.get("modules") or [])}
    counted = {}

    def walk_pg(items, depth, trails, m, seen, mod_ids):
        for it in items:
            t = it.get("title") or ""
            where = " / ".join(trails + (t,))
            k = it.get("key")
            if k:
                if k in seen and seen[k] == depth:
                    add(E, "L2-73",
                        f"模块 {m.get('id')} 的页面目录里「{where}」和第 {depth + 1} 层的另一组用了同一个 key={k}："
                        "开合状态按 key 记，两组会一起开一起合")
                seen[k] = depth
            if depth >= 3:
                add(E, "L2-73",
                    f"模块 {m.get('id')} 的页面目录「{where}」已经到第 {depth + 1} 层："
                    "超过三层就不是目录而是文件浏览器了，上面的组该合并")
            pid = it.get("page")
            if pid:
                if pid not in mod_ids:
                    add(E, "L2-74",
                        f"模块 {m.get('id')} 的页面目录「{where}」挂的页面 {pid} 不属于本模块："
                        "跨模块挂载会让同一页出现在两处，改一处漏一处")
                elif pid in counted:
                    add(E, "L2-74",
                        f"页面 {pid} 在模块 {m.get('id')} 的页面目录里出现了两次"
                        f"（另一次在「{counted[pid]}」）：用户不知道该从哪条进，改完也容易只改一处")
                else:
                    counted[pid] = where
            kids = it.get("children") or []
            if kids:
                if not any(pg_reachable(x, mod_ids) for x in kids):
                    add(E, "L2-74",
                        f"模块 {m.get('id')} 的页面目录分组「{where}」展开后一页都没有："
                        "点开是个空壳，不如把这个组去掉")
                walk_pg(kids, depth + 1, trails + (t,), m, seen, mod_ids)
            elif not pid:
                add(E, "L2-74",
                    f"模块 {m.get('id')} 的页面目录「{where}」既没挂页面也没有子组："
                    "点上去没有任何反应")

    for m in (proto.get("modules") or []):
        groups = m.get("pageGroups") or []
        if not groups:
            continue
        mod_ids = mod_page_ids.get(m.get("id")) or set()
        walk_pg(groups, 0, (), m, {}, mod_ids)
        for pid in sorted(mod_ids):
            if pid not in counted:
                add(E, "L2-74",
                    f"页面 {pid} 没有出现在模块 {m.get('id')} 的页面目录里："
                    "目录是唯一的页面清单，漏一页等于这页在导航里不存在")

    # 状态不是页面：一张单据只能有一个主列表。
    # 把流程阶段拆成页面，是这套 skill 最容易犯也最难自查的错——
    # 每个页面单看都合理，合起来用户要在三页之间找同一张单，
    # 同一条命令有两个入口，置灰原因、四眼校验、操作日志都得维护两份。
    #
    # 主/次是语义，不是计数：执行视图天然比管理视图按钮更多（我的待办要覆盖排查/分析/
    # 措施开始/完成/验证 6 条，台账只有下发/审批/驳回/新增/导出 5 条）。
    # 所以第一步是「取消推断、强制声明」，不是换个权重。
    def owns_of(pg):
        return set((pg.get("contract") or {}).get("owns") or [])

    def entry_hosts(entry):
        """ui.entry 落在哪些页面的组件树里。

        返回集合而不是单页：nodeId 是页内作用域，两个列表页都有 n-table / n-toolbar，
        按 entry 反查"那一页"必然查错，只能问"主列表在不在这些页里"。
        """
        hosts = set()
        if not entry:
            return hosts
        if "__act_" in entry:
            base, akey = entry.split("__act_", 1)
        else:
            base, akey = entry, None
        for pg in pages:
            nodes = walk(pg.get("componentTree") or {}, [])
            if akey is None:
                if any(n.get("id") == base for n in nodes):
                    hosts.add(pg.get("id"))
                continue
            node = next((n for n in nodes if n.get("id") == base), None)
            if not node:
                continue
            props = node.get("props") or {}
            keys = [a.get("key") for a in (props.get("actions") or [])]
            for col in props.get("columns") or []:
                keys += [a.get("key") for a in (col.get("actions") or [])]
            if akey in keys:
                hosts.add(pg.get("id"))
        return hosts

    def cap_of(cid):
        return cap_by_id.get(cid) or {}

    # 只在同一 (entity, target) 内比较：PDA 执行页是另一个端，不是第二个列表
    lists_by_et = {}
    for p in pages:
        if p.get("layout") in ("list", "pda-list") and p.get("entity"):
            lists_by_et.setdefault((p.get("entity"), p.get("target")), []).append(p)

    for (ent, tgt), grp in lists_by_et.items():
        if len(grp) < 2:
            continue        # 只有一个列表页：不判 listRole，否则 example-00 这类单页模块会被误伤
        names = "、".join(f"{x.get('title')}({x.get('id')})" for x in grp)

        # 第 1 步：不许推断。没写 listRole 直接报，逼着写契约的人自己说清主次
        missing = [p for p in grp if p.get("listRole") not in ("primary", "filter")]
        for p in missing:
            add(E, "L2-80",
                f"实体 {ent}（{tgt}）有 {len(grp)} 个列表页（{names}），但 {p.get('id')}「{p.get('title')}」没写 listRole："
                "哪个是主列表、哪个是它的过滤视图，必须显式声明。"
                "推断一定错——执行视图天然按钮更多，按数量认主次会把待办页认成主列表")
        prim = [p for p in grp if p.get("listRole") == "primary"]
        if len(prim) != 1:
            if not missing:
                add(E, "L2-80",
                    f"实体 {ent}（{tgt}）有 {len(prim)} 个 listRole=primary 的列表页"
                    f"（{'、'.join(x.get('id') for x in prim) or '无'}）：一张单据只能有一个主列表，"
                    "0 个或 2 个都不许，其余列表页一律是它的过滤视图")
            continue
        P = prim[0]
        p_owns = owns_of(P)
        p_actors = set((P.get("contract") or {}).get("actor") or [])

        # 管理视角与执行视角：是同一张表的两个筛选，面向两种人。
        # 只判"两种视角是不是真的两种人"，不再判"几个状态就必须几个页面"——
        # 那是"按阶段拆页"时代的规则，已被 L2-80/81 取代；
        # 留着会把"一张台账走完全流程"（做对的样子）判死，两条判据互相打架。
        filters = [f for f in grp if f.get("listRole") == "filter"]
        if filters:
            # actor 必填：空集合和任何集合都"不相等"，只判相同会把"没写"当"已判过"放行。
            # schema 里 page.contract.actor 是必填，但 check_contract 不读 schema，
            # 这里是唯一真正兜住它的地方。
            blank = [p.get("id") for p in [P] + filters
                     if not ((p.get("contract") or {}).get("actor") or [])]
            if blank:
                add(E, "L2-58",
                    f"实体 {ent}（{tgt}）的列表页 {blank} 没写 contract.actor："
                    "主列表和过滤视图各自面向谁，必须明说——空着就没法判'两个视角是不是两种人'，"
                    "也没法核对按钮该给谁看")
            else:
                f_actors = [set((f.get("contract") or {}).get("actor") or []) for f in filters]
                if all(fa == p_actors for fa in f_actors):
                    add(E, "L2-58",
                        f"实体 {ent}（{tgt}）的 {len(grp)} 个列表页（{names}）面向同一批角色 {sorted(p_actors)}："
                        "过滤视图只是主列表换个筛选，两页的 actor 必须不同（一个管全量、一个只看我的），"
                        "同一批人看到的两份拷贝不叫两个视角")

        # 第 2 步：主列表必须装得下整条生命周期，不能把命令全挪走只剩个空壳
        if not any(cap_of(cid).get("to") for cid in p_owns):
            add(E, "L2-80",
                f"主列表 {P.get('id')}「{P.get('title')}」的 contract.owns 里没有任何 to!=null 的命令："
                "推进动作被挪到别的页面了，主列表只剩个壳，用户看得到单却推不动它")

        # 第 3 步：过滤视图只能筛，不许自造
        for f in grp:
            if f.get("id") == P.get("id") or f.get("listRole") != "filter":
                continue
            f_owns = owns_of(f)
            # 只比同一 entity 的命令：我的待办这类跨单据收件箱会同时收措施任务，
            # 那些命令推进的是「措施单」，不是本张单据的生命周期
            same = {cid for cid in f_owns if cap_of(cid).get("entity") == ent}
            adv = sorted(cid for cid in same if cap_of(cid).get("to"))
            if adv:
                add(E, "L2-82",
                    f"{f.get('id')}「{f.get('title')}」是 {ent} 的过滤视图，却定义了推进命令 {adv}："
                    "过滤视图只能换筛选。这些动作应该只在主列表"
                    f" {P.get('id')} 的工具栏/行内出现，靠单据状态决定亮灭，两处各放一份等于维护两套")
            # 不再判"filter owns 必须 ⊆ primary owns"：owns 的含义已收窄为「这条命令归哪一页负责」，
            # 全局唯一（L2-21 保证）。过滤视图认领一条纯查询命令，是它自己的责任归属，
            # 不是"自造"——按钮画在哪由组件树决定（L2-90 保证画了就得有人管）。

        # 第 5 步：生命周期不许跨页
        # 只认 contract.owns，不看 ui.entry 落在哪一页：entry 是单值，表达不了
        # "同一个按钮在两页都渲染"；nodeId 又是页内作用域（台账页与待办页共用
        # n-root/n-page/n-toolbar/n-table/n-tabs/n-filter/n-footer 七个 id）。
        # 拿它判"按钮在哪一页"，只会逼着人改 entry 字符串去骗判据——
        # measure 就是这么被扭成"验证页当主列表"的。
        for c in caps:
            if c.get("entity") != ent or c.get("target") not in (None, "", tgt):
                continue
            ui = c.get("ui") or {}
            if not c.get("to") or ui.get("kind") not in ("inline", "dialog", "drawer"):
                continue
            hosts = entry_hosts(ui.get("entry"))
            # 建单页（form/wizard/pda-step）上的提交是这张单据的"出生"，不是生命周期的一段：
            # 它天然不在主列表上，不该被这条判据误伤
            if hosts and all((page_by_id.get(h) or {}).get("layout") in ("form", "wizard", "pda-step")
                             for h in hosts):
                continue
            if c.get("id") not in p_owns:
                add(E, "L2-81",
                    f"命令 {c.get('id')}「{c.get('label') or c.get('name')}」会改 {ent} 的状态（→{c.get('to')}），"
                    f"却不在主列表 {P.get('id')} 的 contract.owns 里："
                    "生命周期不许跨页，主列表必须能一个人走完全程")

    # 详情页是"看全貌"的地方，不是第二个操作入口。
    # 这是 L2-54（详情页不许有可编辑表单）的补位：只堵组件不堵命令，
    # 就会出现"详情页里放一个按钮直接改状态"——比表单更难查，因为按钮不在表单节点里。
    for p in pages:
        if p.get("layout") != "detail":
            continue
        for cid in sorted(owns_of(p)):
            c = cap_of(cid)
            if c.get("to"):
                add(E, "L2-83",
                    f"详情页 {p.get('id')}「{p.get('title')}」的 contract.owns 里认领了推进命令 {cid}"
                    f"「{c.get('label') or c.get('name')}」（→{c.get('to')}）：详情页只读，"
                    "改状态的动作只能挂在主列表的工具栏或行内，否则同一条命令有了第二个入口")

    # 模块里出现的实体，至少要有一个页面认领它的某条命令。
    # 抓的是"页面画出来了、命令没人认领"这种根因：两页都没写 listRole 时，
    # 按钮照样在组件树里、契约里却没有任何一处说"这个实体的动作归哪页管"，
    # 后面 L2-80/81/82 全靠 owns，owns 一空就全部失效。
    for m in modules:
        mpages = [page_by_id[x] for x in (m.get("pages") or []) if x in page_by_id]
        for ent in sorted({p.get("entity") for p in mpages if p.get("entity")}):
            claimed = [p.get("id") for p in pages
                       if any(cap_of(cid).get("entity") == ent for cid in owns_of(p))]
            if not claimed:
                add(E, "L2-89",
                    f"模块 {m.get('id')} 里有 {ent} 的页面，但没有任何页面的 contract.owns "
                    f"认领一条 {ent} 的命令：这个实体的动作现在是「画在组件树上、契约里没人管」——"
                    "L2-80/81/82 全部依赖 owns，owns 一空，判据就全哑了")

    # 页面名里的「和 / 与 / 及」是拆页的征兆：「处置与闭环」= 两个阶段被做成一个页面。
    # 只查 title，不查 contract.task：task 是描述性长文本，正常写法就含「与」
    #（"责任部门建单与发布、质量部确认…"），一查必响，等于每个工具栏范式页面都报警。
    # 只报 WARN，不替人下结论：「来料检验与判定」这类名是合法的。
    for p in pages:
        if p.get("layout") not in ("list", "pda-list"):
            continue
        val = p.get("title") or ""
        m = re.search(r"和|与|及", val)
        if not m:
            continue
        lo = max(0, m.start() - 8)
        add(W, "L2-86",
            f"页面 {p.get('id')} 的标题含并列词「{m.group(0)}」：「…{val[lo:m.start() + 9]}…」。"
            "先确认是不是把两个流程阶段拆成了两个页面——单据的状态该做成行上的字段和按钮的亮灭条件，"
            "不是换一个页面")

    # 菜单只放"可以主动开始的任务"：表单页 / 详情页不是菜单项。
    # 扫的是左侧业务菜单（AppShell.props.groups）——那是"我每天从哪开始"；
    # 不是顶栏页面目录（modules[].pageGroups）——那是"这个模块有哪些页面"。
    # 两棵树用途不同，L2-74 要求每页都在后者里，与这里不冲突。
    # 刻意不按标题判定：startswith("新建") 换个名字（"开单""建单"）就绕过了，layout 才是语义。
    menu_reported = set()
    for p in pages:
        tree = p.get("componentTree") or {}
        if tree.get("type") != "AppShell":
            continue
        seen_menu = {}
        for g in ((tree.get("props") or {}).get("groups") or []):
            for it, depth, trails in walk_nav(g.get("items")):
                pid = it.get("page")
                if not pid:
                    continue
                where = " / ".join(trails + (it.get("label") or "",))
                tp = page_by_id.get(pid) or {}
                if tp.get("layout") in ("form", "wizard", "detail") and ("leaf", pid) not in menu_reported:
                    menu_reported.add(("leaf", pid))
                    add(E, "L2-84",
                        f"左侧菜单「{where}」挂的 {pid}「{tp.get('title')}」是 {tp.get('layout')} 页："
                        "表单页 / 详情页不是用户可以主动开始的任务，它们靠列表工具栏的「新增」或行点击进入。"
                        "进了菜单，用户会以为建单要先找到这个页面，而且它和列表是两套入口")
                if pid in seen_menu:
                    # 每个页面的 AppShell 挂的是同一份菜单，同一条错只报一次
                    if ("dup", pid) not in menu_reported:
                        menu_reported.add(("dup", pid))
                        add(E, "L2-84",
                            f"左侧菜单里 {pid} 出现了两次（「{seen_menu[pid]}」和「{where}」）："
                            "同一张表两个入口，改一处漏一处，用户也不知道该从哪条进")
                else:
                    seen_menu[pid] = where

    # 组件树里画出来的按钮，契约里必须有人管。
    # owns 只回答"这条命令归哪一页负责"（全局唯一），"这页显示什么"由组件树决定；
    # 两者之间没有判据，就会出现"按钮画了、契约里没人管"——过滤视图 owns 清空后
    # 正好能钻这个洞：按钮还在、状态机还在，但没有一处声明它归谁。
    cap_owner = {}
    for p in pages:
        for cid in owns_of(p):
            cap_owner.setdefault(cid, p.get("id"))
    rend = {p.get("id"): rendered_caps(p) for p in pages}
    pact = {p.get("id"): set((p.get("contract") or {}).get("actor") or []) for p in pages}
    ref_reported = set()
    for p in pages:
        refs = collect_capability_refs(walk(p.get("componentTree") or {}, []))
        for nid, cid in refs:
            if not cid or (p.get("id"), cid) in ref_reported:
                continue
            ref_reported.add((p.get("id"), cid))
            if cid not in cap_ids:
                add(E, "L2-90",
                    f"页面 {p.get('id')} 的节点 {nid} 挂了一个不存在的命令 {cid}："
                    "按钮画得出来，点了不会发生任何事")
            elif cid not in cap_owner:
                add(E, "L2-90",
                    f"页面 {p.get('id')} 的节点 {nid} 渲染了命令 {cid}"
                    f"「{(cap_by_id.get(cid) or {}).get('label') or cid}」，但没有任何页面的 contract.owns 认领它："
                    "按钮是画上了，可契约里没人管它的状态、权限和置灰原因")

    # L2-91 幽灵命令：契约说归谁管，界面上根本没这个按钮。
    # 没有豁免：没有按钮的动作不该写成命令，它是状态机的系统迁移（transitions[].system）。
    for c in caps:
        cid = c.get("id")
        if cid not in cap_owner:
            continue
        if not any(cid in s for s in rend.values()):
            add(E, "L2-91",
                f"命令 {cid}「{c.get('label') or c.get('name')}」被 {cap_owner[cid]} 认领，"
                "但没有任何页面的组件树渲染它：契约里写着归它管，界面上找不到这个按钮")

    # L2-92 无人可执行：会改状态的命令，渲染它的页面没有一个角色的 actor 与它相交。
    # 两边任一为空不判（空集合和谁都不相交，会把"没写"当成"没人能做"，那是 L2-58 的事）。
    for c in caps:
        cid = c.get("id")
        if not c.get("to"):
            continue
        cap_actors = set(c.get("actor") or [])
        hosts = [pid for pid, s in rend.items() if cid in s]
        if not hosts or not cap_actors:
            continue
        if not any(pact.get(pid, set()) & cap_actors for pid in hosts):
            add(E, "L2-92",
                f"命令 {cid}「{c.get('label') or c.get('name')}」（→{c.get('to')}）只出现在 "
                f"{'、'.join(sorted(hosts))} 上，而这些页面的 contract.actor 与它的 actor "
                f"{sorted(cap_actors)} 没有一个相交：整条流程里没有任何角色点得到这个按钮")

    # L2-93 越权渲染：某页画了自己角色不该碰的推进命令。
    # 只报 WARN——"一张列表管全流程、把别人的按钮也画出来当流程提示"是合法设计，要人看一眼。
    for p in pages:
        pid = p.get("id")
        my_actors = pact.get(pid) or set()
        if not my_actors:
            continue
        for cid in sorted(rend.get(pid) or []):
            c = cap_by_id.get(cid) or {}
            cap_actors = set(c.get("actor") or [])
            if not c.get("to") or not cap_actors or (my_actors & cap_actors):
                continue
            add(W, "L2-93",
                f"页面 {pid}「{p.get('title')}」渲染了推进命令 {cid}「{c.get('label') or cid}」"
                f"（→{c.get('to')}，actor={sorted(cap_actors)}），与本页 contract.actor "
                f"{sorted(my_actors)} 不相交：要么本页 actor 写漏了，要么这个按钮不该画在这页")

    # 命令落在哪要写清：placement 可缺省，所以只写"工具栏必须给 from"这条会被"不写"绕过。
    # 弹层承载（dialog/drawer）一定落在某个位置（工具栏 / 行内 / 表单内），必须声明。
    PLACEMENTS = ("toolbar", "row", "form")
    for c in caps:
        cid = c.get("id")
        ui = c.get("ui") or {}
        pm = c.get("placement")
        if pm is not None and pm not in PLACEMENTS:
            add(E, "L2-85",
                f"命令 {cid} 的 placement={pm} 非法（只认 {'/'.join(PLACEMENTS)}）："
                "toolbar=列表工具栏、row=行内、form=表单内。"
                "别用 inline 表示位置——那是 ui.kind 的取值，同名不同义，读契约的人十有八九会混。"
                "没有按钮的动作不写命令：它是状态机的系统迁移，写 transitions[].system=true + trigger=system-*")
        # 缺 placement 只报 WARN：它不影响 L2-81（走 owns）、也只影响 L2-77（工具栏亮灭）。
        # 实测 09:41 工程一口气报 13 条，全是这一条，13 条 ERROR 换 0 收益，只会训练人忽略报错。
        if ui.get("kind") in ("dialog", "drawer") and not pm:
            add(W, "L2-85",
                f"命令 {cid}「{c.get('name')}」用 {ui.get('kind')} 承载，却没写 placement："
                "它一定落在某个位置（工具栏 / 行内 / 表单内），写上才能核对按钮长在哪")

    # 列表上的按钮，亮灭只能由单据状态决定：from 是唯一依据（app.js 就是拿 cap.from 判的）。
    # 前置条件刻意不限定 placement=toolbar：写 row、或者干脆不写 placement，都绕不过去。
    # 没有"无界面命令"这个例外——没有按钮的动作不是命令，是状态机的系统迁移
    # （transitions[].system=true），它根本不该出现在 capabilities 里。
    # 豁免「建单」：from=[] 且 to 是该实体状态机的 initial，它本来就该一直亮着——
    # 不加这条，「工具栏新增 + 抽屉」这个正确范式会被判成"不知道什么时候点亮"。
    sm_by_entity = {}
    for sm in sms:
        sm_by_entity.setdefault(sm.get("entity"), sm)
    for c in caps:
        cid = c.get("id")
        if not c.get("to"):
            continue
        if c.get("from"):
            continue
        sm = sm_by_entity.get(c.get("entity")) or {}
        if c.get("to") == sm.get("initial"):
            continue        # 建单命令：from 为空是它的定义，不是漏写
        where = "工具栏" if c.get("placement") == "toolbar" else "列表上（工具栏 / 行内）"
        add(E, "L2-77",
            f"命令 {cid}「{c.get('label') or c.get('name')}」挂在{where}且会改状态（→{c.get('to')}），"
            f"却没写 from：按钮会一直亮，能重复建单 / 重复提交。"
            f"按钮的可用性完全由单据状态决定；若它是建单命令，to 必须等于 {c.get('entity')} 状态机的 initial")

    # L2-94 自环：to 落在 from 里，等于"说自己会改状态，改完还是同一个状态"。
    # 三条理由，第一条最硬：
    #   ① 它制造 R 层测不了的东西。自环推进完状态不变，R-09 的正对照（推进后应等于 to）
    #      无从判断，只能跳过——判据不该给自己造一个永久盲区；
    #   ② 状态图上画出指向自己的箭头，读图的人会以为这一步能重来；
    #   ③ 不改状态的动作用 to=null 表达，契约里已经有这个写法，不需要第二种。
    for c in caps:
        cid = c.get("id")
        if not c.get("to"):
            continue
        if c.get("to") in (c.get("from") or []):
            add(E, "L2-94",
                f"命令 {cid}「{c.get('label') or c.get('name')}」的 to={c.get('to')} 出现在 from 里："
                f"这条命令声称会改状态，可改完还是同一个状态。不改状态的动作用 to=null；"
                f"建单用 from=[] 且 to 等于状态机的 initial")

    # 每个状态都要有人指向它：画得出来、走不进去
    for sm in (proto.get("stateMachines") or []):
        pointed = {t.get("to") for t in (sm.get("transitions") or [])}
        for st in (sm.get("states") or []):
            if st.get("key") == sm.get("initial") or st.get("key") in pointed:
                continue
            add(E, "L2-79",
                f"状态机 {sm.get('id')} 的状态「{st.get('label') or st.get('key')}」既不是 initial，"
                "也没有任何迁移指向它：状态条上画得出来，实际走不进去，用户永远到不了这一步")

    # TODO(P0-2d): L2-78（复刻视觉取值必须有出处）已随 meta.skinTokens 撤回一并删除，
    # 不在这里留实现——留着就是读一个 schema 里已不存在的字段，永不触发的死判据。
    # 重写规格见 specs/2026-11-05-skill-improve.md §9.4，落地为 L2-87（出处 + 令牌名白名单）
    # / L2-88（raw÷deviceScale 算术校验）/ C-15（渲染实测），三条一起才算"复刻"。

    # 页头标题要跟页面名一致：写死一张单据号，换数据进来就张冠李戴
    for p in pages:
        hdr = (((p.get("componentTree") or {}).get("props") or {}).get("header") or {})
        ht = hdr.get("title")
        if ht and ht != p.get("title"):
            add(E, "L2-62", f"页面 {p.get('id')} 的页头标题「{ht}」与页面名「{p.get('title')}」不一致："
                            "页头是页面身份，不能拿某条数据的编号顶替")

    # 弹层不能是空壳：要么有要填的字段，要么说清确认后发生什么
    for c in caps:
        ui = c.get("ui") or {}
        if ui.get("kind") in ("dialog", "drawer") and not (ui.get("fields") or ui.get("successText")):
            add(E, "L2-63", f"命令 {c.get('id')} 用 {ui.get('kind')} 承载，但既没有 fields 也没有 successText："
                            "点开是个空弹层，用户不知道要干什么")

    # 状态条不能渲染成空白：StatusBar 只认 steps 或 stateMachine，
    # 两者都没给（或给的 stateMachine 不存在）时页面上就只剩「单据状态」两个字和一条空线，
    # 而 JSON 里看起来什么都写了——这类"契约有、引擎无"只有读渲染结果才能发现，先在这里拦一道。
    sm_by_id = {s.get("id"): s for s in sms}
    for p in pages:
        for n in walk(p.get("componentTree") or {}, []):
            if n.get("type") != "StatusBar":
                continue
            pr = n.get("props") or {}
            steps, smref = pr.get("steps") or [], pr.get("stateMachine")
            if not steps and not smref:
                add(E, "L2-64", f"页面 {p.get('id')} 的状态条 {n.get('id')} 既没有 steps 也没有 stateMachine："
                                "渲染出来是一条空白状态条")
            elif not steps and smref not in sm_by_id:
                add(E, "L2-65", f"页面 {p.get('id')} 的状态条 {n.get('id')} 引用了不存在的状态机 {smref}："
                                "引擎查不到就渲染成空白条")
            elif steps and len(steps) < 2:
                add(E, "L2-64", f"页面 {p.get('id')} 的状态条 {n.get('id')} 只有 {len(steps)} 个步骤："
                                "只有一条状态的「状态条」没有意义")

    # 表单栅格同理：契约写 fields、组件只认 items 的那一版，整张表单渲染成「暂无字段」，
    # 而 JSON 校验全绿。字段名对不上属于引擎契约问题，不能指望评审时肉眼发现。
    for p in pages:
        for n in walk(p.get("componentTree") or {}, []):
            if n.get("type") != "FormGrid":
                continue
            pr = n.get("props") or {}
            if not (pr.get("items") or pr.get("fields")):
                add(E, "L2-66", f"页面 {p.get('id')} 的表单 {n.get('id')} 没有 items/fields："
                                "渲染出来是「暂无字段」的空表单")

    # 标注是"下一轮改原型的输入"，不是评论区。三条底线：
    #   1) 标了完成必须写怎么改的；2) 落点页面还得在；3) 落点元素（或弹层命令）还得在。
    # 少了任何一条，标注就会变成"看起来记录了，实际没人能据此改"。
    node_ids_by_page = {}
    for p in pages:
        node_ids_by_page[p.get("id")] = {n.get("id") for n in walk(p.get("componentTree") or {}, [])}
    for a in anns:
        aid = a.get("id")
        if a.get("status") in ("resolved", "wontfix") and not str(a.get("resolution") or "").strip():
            add(E, "L2-70", f"标注 {aid} 已经标为 {a.get('status')}，但没写 resolution（怎么改的）："
                            "下一个接手的人只能重新发现同一个问题")
        pid = a.get("pageId")
        if pid not in page_ids:
            add(E, "L2-71", f"标注 {aid} 指向不存在的页面 {pid}")
            continue
        nid = str(a.get("nodeId") or "")
        if nid.startswith("layer:"):
            parts = nid.split(":")
            cid = parts[1] if len(parts) > 1 else ""
            if cid not in cap_ids:
                add(E, "L2-72", f"标注 {aid} 落在弹层 {cid} 上，但契约里没有这条命令")
            continue
        if nid not in node_ids_by_page[pid]:
            add(E, "L2-72", f"标注 {aid} 的落点 {nid} 不在页面 {pid} 的组件树里："
                            "引擎找不到元素就画不出 pin，这条意见等于丢了")

    # ---------- L2 D. 命令策略 ----------
    # 一条命令只能有一个认领页（单一事实来源）。
    # 过滤视图不 owns 推进命令：它渲染按钮靠组件树里的 capability 引用，和 owns 是两件事。
    # 早先给过滤视图开过"可以复认一次"的口子，会逼着每条新命令改两个 owns 数组，
    # 正是"改一处漏一处"；已撤回。
    owns = {}
    for p in pages:
        for cid in ((p.get("contract") or {}).get("owns") or []):
            if cid not in cap_ids:
                add(E, "L2-20", f"页面 {p.get('id')} 的 contract.owns 引用了不存在的命令 {cid}")
            if cid in owns:
                add(E, "L2-21", f"命令 {cid} 被 {owns[cid]} 与 {p.get('id')} 同时 owns"
                                "（一条命令只能有一个主页面；过滤视图靠组件树引用渲染按钮，不重复认领）")
            else:
                owns[cid] = p.get("id")

    for c in caps:
        cid = c.get("id")
        if not c.get("actor"):
            add(E, "L2-22", f"命令 {cid} 未声明 actor")
        # 角色必须来自 actors 表，否则 UI/PRD 只能显示 u-xxx
        for a in (c.get("actor") or []):
            if actor_ids and a not in actor_ids:
                add(E, "L2-53", f"命令 {cid} 的 actor={a} 不在 actors 表中")
        if c.get("policy") not in ("hidden", "disabled", "reject"):
            add(E, "L2-23", f"命令 {cid} 的 policy={c.get('policy')} 非法")
        if not c.get("reason"):
            add(E, "L2-24", f"命令 {cid} 缺 reason（置灰时必须告诉用户为什么）")
        # label 是用户看到的动作名。缺了 UI 只能显示 cap-xxx，
        # 状态流、按钮、PRD 可用性表都会露出内部 ID
        if not c.get("label"):
            add(E, "L2-52", f"命令 {cid} 缺 label（用户可见的动作名，如「审核」），UI 会退化成显示 ID")

    # ---------- L2 E. 状态机 ----------
    for sm in sms:
        sid = sm.get("id")
        keys = {s.get("key") for s in (sm.get("states") or [])}
        if sm.get("initial") not in keys:
            add(E, "L2-25", f"状态机 {sid} 的 initial={sm.get('initial')} 不在 states 内")
        for t in (sm.get("transitions") or []):
            if t.get("from") not in keys or t.get("to") not in keys:
                add(E, "L2-26", f"状态机 {sid} 的迁移 {t.get('from')}→{t.get('to')} 引用了未声明的状态")
            tr = t.get("trigger")
            if t.get("system"):
                continue
            if tr not in cap_ids:
                add(E, "L2-27", f"状态机 {sid} 的人工迁移 trigger={tr} 没有对应命令（系统流转须标 system:true）")
            else:
                cap = next(c for c in caps if c.get("id") == tr)
                if t.get("from") not in (cap.get("from") or []):
                    add(E, "L2-28", f"命令 {tr} 的 from 不含迁移起点 {t.get('from')}")
                if cap.get("to") != t.get("to"):
                    add(E, "L2-29", f"命令 {tr} 的 to={cap.get('to')} 与迁移目标 {t.get('to')} 不一致")

    subs = [c for c in caps if c.get("stage") == "submit"]
    vers = [c for c in caps if c.get("stage") == "verify"]
    for s in subs:
        for v in vers:
            if v.get("sameActorOk"):
                continue
            inter = set(s.get("actor") or []) & set(v.get("actor") or [])
            if inter:
                add(E, "L2-30", f"提交命令 {s.get('id')} 与验证命令 {v.get('id')} 的 actor 交集非空：{sorted(inter)}（四眼原则）")
    # 提交后的状态可能先被系统迁移（自动出报告等）带一段，再轮到验证，所以按「系统迁移可达」判
    sys_edges = {}
    for sm in sms:
        for t in (sm.get("transitions") or []):
            if t.get("system"):
                sys_edges.setdefault(t.get("from"), set()).add(t.get("to"))

    def reach(start):
        seen, stack = {start}, [start]
        while stack:
            cur = stack.pop()
            for nxt in sys_edges.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    for v in vers:
        ok = False
        for s in subs:
            if not s.get("to"):
                continue
            if set(v.get("from") or []) & reach(s.get("to")):
                ok = True
                break
        if not ok:
            add(W, "L2-31", f"验证命令 {v.get('id')} 的 from 未接住任何提交命令的 to（含系统迁移，中间状态可能没人管）")

    # ---------- L2 F. EARS 条目 ----------
    for r in reqs:
        rid = r.get("id")
        for k in ["actor", "trigger", "rule", "stateMachine", "expectation", "acceptance", "priority"]:
            if not r.get(k):
                add(E, "L2-32", f"需求 {rid} 缺 EARS 字段 {k}")
        acc = r.get("acceptance") or []
        if not acc:
            add(E, "L2-33", f"需求 {rid} 没有验收用例")
        elif not any(a.get("kind") == "illegal" for a in acc):
            add(E, "L2-34", f"需求 {rid} 只有成功路径验收，缺非法路径（状态不符/权限不足/并发冲突）")
        smref = re.search(r"sm-[A-Za-z0-9_-]+", r.get("stateMachine") or "")
        if smref and smref.group(0) not in sm_ids:
            add(E, "L2-35", f"需求 {rid} 引用了不存在的状态机 {smref.group(0)}")
        for pid in (r.get("pageIds") or []):
            if pid not in page_ids:
                add(E, "L2-36", f"需求 {rid} 引用了不存在的页面 {pid}")

    # ---------- L2 G. 标注 / 字段登记 ----------
    tree_of = {p.get("id"): {n.get("id") for n in walk(p.get("componentTree") or {}, [])} for p in pages}
    for a in anns:
        if a.get("pageId") not in page_ids:
            add(E, "L2-37", f"标注 {a.get('id')} 指向不存在的页面 {a.get('pageId')}")
        elif a.get("nodeId") not in tree_of.get(a.get("pageId"), set()):
            add(E, "L2-38", f"标注 {a.get('id')} 锚定的节点 {a.get('nodeId')} 不在页面 {a.get('pageId')} 的组件树内")
        ax = (a.get("anchor") or {})
        for k in ("x", "y"):
            if not isinstance(ax.get(k), (int, float)) or not (0 <= ax.get(k) <= 1):
                add(E, "L2-39", f"标注 {a.get('id')} 的 anchor.{k} 必须是 0~1 的归一化坐标")

    for f in (proto.get("fieldRegistry") or []):
        pid = f.get("pageId")
        if pid not in page_ids:
            add(E, "L2-40", f"字段登记「{f.get('name')}」指向不存在的页面 {pid}")
        elif f.get("block") not in tree_of.get(pid, set()):
            add(E, "L2-41", f"字段登记「{f.get('name')}」的 block={f.get('block')} 不指向 {pid} 的真实节点")
        if f.get("scope") == "out" and not f.get("reason"):
            add(E, "L2-42", f"字段登记「{f.get('name')}」标了 scope=out 却没写 reason")

    # ---------- L2 H. 数据模型 ----------
    ents = (proto.get("dataModel") or {}).get("entities") or []
    eids = {e.get("id") for e in ents}
    for e in ents:
        if not e.get("fields"):
            add(E, "L2-43", f"实体 {e.get('id')} 没有字段")
        for fld in e.get("fields") or []:
            if fld.get("fk") and fld.get("fk") not in eids:
                add(E, "L2-44", f"实体 {e.get('id')} 字段 {fld.get('name')} 的 fk 指向不存在的实体 {fld.get('fk')}")
            if fld.get("type") == "enum" and not fld.get("enum"):
                add(E, "L2-45", f"实体 {e.get('id')} 字段 {fld.get('name')} 是 enum 但没写候选值")
    for rel in (proto.get("dataModel") or {}).get("relations") or []:
        if rel.get("from") not in eids or rel.get("to") not in eids:
            add(E, "L2-46", f"关系 {rel.get('from')}→{rel.get('to')} 的实体不存在")
    for d in (proto.get("dataModel") or {}).get("derived") or []:
        if not d.get("fallback"):
            add(E, "L2-47", f"派生指标 {d.get('name')} 缺 fallback（无数据口径）")

    # ---------- L2 I. PDA 现场策略 ----------
    for p in pages:
        if p.get("target") != "pda":
            continue
        pid = p.get("id")
        pol = p.get("pda") or {}
        if "onlineOnly" not in pol and not pol.get("offline"):
            add(E, "L2-48", f"PDA 页面 {pid} 未声明 onlineOnly 或 offline 策略")
        nodes = walk(p.get("componentTree") or {}, [])
        if not any(n.get("type") == "BigAction" for n in nodes):
            add(E, "L2-49", f"PDA 页面 {pid} 缺少 BigAction（一屏必须有一个拇指区主操作）")
        pa = pol.get("primaryAction")
        if pa and pa not in {n.get("id") for n in nodes}:
            add(E, "L2-50", f"PDA 页面 {pid} 的 primaryAction={pa} 不是本页节点")

    if not issues:
        add("OK", "PASS", "全部判据通过")


def check_plan(plan):
    for k in ["planVersion", "product", "slices"]:
        if k not in plan:
            add(E, "P-01", f"计划缺 {k}")
    slices = plan.get("slices") or []
    ids = [s.get("id") for s in slices]
    if len(ids) != len(set(ids)):
        add(E, "P-02", "切片 id 重复")

    page_owner, cap_owner = {}, {}
    for s in slices:
        sid = s.get("id")
        for pid in s.get("pages") or []:
            if pid in page_owner:
                add(E, "P-03", f"页面 {pid} 被 {page_owner[pid]} 与 {sid} 同时认领")
            page_owner[pid] = sid
        for cid in s.get("capabilities") or []:
            if cid in cap_owner:
                add(E, "P-04", f"命令 {cid} 被 {cap_owner[cid]} 与 {sid} 同时认领")
            cap_owner[cid] = sid
        if len(s.get("pages") or []) > 4:
            add(E, "P-05", f"切片 {sid} 页面数 {len(s.get('pages'))} 超上限 4")
        if len(s.get("capabilities") or []) > 6:
            add(E, "P-06", f"切片 {sid} 命令数超上限 6")
        if len(s.get("requirements") or []) > 12:
            add(E, "P-07", f"切片 {sid} 需求数超上限 12")
        if (s.get("nodesBudget") or 0) > 80:
            add(E, "P-08", f"切片 {sid} 节点预算超上限 80")
        if not s.get("acceptance"):
            add(E, "P-09", f"切片 {sid} 没有可独立验收的标准")

    known = set(ids)
    graph = {s.get("id"): list(s.get("dependsOn") or []) for s in slices}
    for sid, deps in graph.items():
        for d in deps:
            if d not in known:
                add(E, "P-10", f"切片 {sid} 依赖不存在的切片 {d}")
    color = {}

    def dfs(u, stack):
        color[u] = 1
        for v in graph.get(u, []):
            if color.get(v) == 1:
                add(E, "P-11", f"切片依赖成环：{' → '.join(stack + [u, v])}")
            elif color.get(v, 0) == 0:
                dfs(v, stack + [u])
        color[u] = 2

    for sid in graph:
        if color.get(sid, 0) == 0:
            dfs(sid, [])
    if not issues:
        add("OK", "PASS", "切片计划判据通过")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    plan_mode = "--plan" in sys.argv
    if not args:
        print(__doc__)
        return 2
    path = args[0]

    if plan_mode:
        check_plan(load(path))
        title = "切片计划"
    else:
        check_proto(load(path), load(CATALOG))
        title = "数据契约"

    errors = [i for i in issues if i[0] == E]
    warns = [i for i in issues if i[0] == W]
    oks = [i for i in issues if i[0] == "OK"]

    print(f"检查对象：{os.path.relpath(path, ROOT)}")
    print(f"检查类型：{title}")
    print("-" * 66)
    for level, code, msg in issues:
        print(f"[{level:5}] {code:6} {msg}")
    print("-" * 66)
    print(f"结果：ERROR={len(errors)}  WARN={len(warns)}  {'PASS' if not errors else 'FAIL'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
