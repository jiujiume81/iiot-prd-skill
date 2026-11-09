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

import field_sites      # 渲染位抽取：与 check_contract.py 共用这一份实现

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


def rendered_caps(p):
    """本页组件树里实际渲染的 capId 集合（工具栏 + 行内）。

    不拿 contract.owns 当"这页显示什么"：owns 只回答"这条命令归哪一页负责"，
    过滤视图的按钮照样渲染但 owns 可能是空的；反过来主列表 owns 的判定按钮
    可能只画在验证页上（四眼校验）。取样看渲染，才和用户眼睛看到的一致。
    """
    out = set()
    for n in walk(p.get("componentTree") or {}, []):
        props = n.get("props") if isinstance(n.get("props"), dict) else {}
        refs = [props.get("capability")]          # ① 单按钮节点（PDA BigAction）
        refs += [a.get("capability") for a in (props.get("actions") or []) if isinstance(a, dict)]  # ② 工具栏/卡片
        cols = props.get("columns")
        for col in (cols if isinstance(cols, list) else []):
            if isinstance(col, dict):
                refs += [a.get("capability") for a in (col.get("actions") or []) if isinstance(a, dict)]  # ③ 行内
        out |= {c for c in refs if c}
    return out


def owns_of(p):
    return set((p.get("contract") or {}).get("owns") or [])


def host_page(pages, cid):
    """这条命令该在哪一页上点：优先「既 owns 又渲染」，其次「渲染了」，最后「owns 了」。"""
    for p in pages:
        if cid in owns_of(p) and cid in rendered_caps(p):
            return p.get("id")
    for p in pages:
        if cid in rendered_caps(p):
            return p.get("id")
    for p in pages:
        if cid in owns_of(p):
            return p.get("id")
    return None


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
    label_of = {s.get("key"): s.get("label")
                for sm in (proto.get("stateMachines") or [])
                for s in (sm.get("states") or [])}
    cases = []

    def carrier(pg, cap):
        """这条命令的按钮挂在哪儿：行内（返回 stateKey）还是表级/表单级（返回 None）。"""
        return _row_col_state_key(pg, cap.get("id"))

    # 1. 每条 dialog/drawer 命令：在它真正渲染出来的那一页上点开、看承载形式、Esc 关闭
    for c in proto.get("capabilities") or []:
        ui = c.get("ui") or {}
        if ui.get("kind") not in ("dialog", "drawer"):
            continue
        host = host_page(pages, c.get("id"))
        if not host:
            continue
        f0 = (c.get("from") or [None])[0]
        sk = carrier(page_by_id.get(host) or {}, c)
        cases.append({
            "kind": "cap",
            "name": f"{title_by_id.get(host)} · {c.get('label') or c.get('name')} 打开{ui.get('kind')}",
            "page": host,
            "cap": c.get("id"),
            "from": f0,
            "fromLabel": label_of.get(f0) or f0,
            "rowLevel": bool(sk),
            "stateKey": sk or "status",
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
            f0 = (cap.get("from") or [None])[0]
            sk = carrier(p, cap)
            cases.append({
                "kind": "cap",
                "name": f"{p.get('title')} · 交互 {ix.get('id')} 打开承载层",
                "page": p.get("id"),
                "cap": cap.get("id"),
                "from": f0,
                "fromLabel": label_of.get(f0) or f0,
                "rowLevel": bool(sk),
                "stateKey": sk or "status",
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
        host = host_page(pages, c.get("id"))
        if not host:
            continue
        f0 = (c.get("from") or [None])[0]
        sk = carrier(page_by_id.get(host) or {}, c)
        cases.append({
            "kind": "annot",
            "name": f"{title_by_id.get(host)} · 能在「{ui.get('title') or c.get('name')}」弹层里标注",
            "page": host,
            "cap": c.get("id"),
            "from": f0,
            "fromLabel": label_of.get(f0) or f0,
            "rowLevel": bool(sk),
            "stateKey": sk or "status",
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
    # 3d. 页面目录（顶栏「目录」）也是树：分组能开能合，点叶子能换页。
    # 平铺目录在页数一多时就退化成扫名字，这条守的是"分组真的折叠了"和"叶子真的能跳"。
    for m in (proto.get("modules") or []):
        grp = next((g for g in (m.get("pageGroups") or []) if (g.get("children") or [])), None)
        if not grp:
            continue
        leaf = next((c for c in grp["children"] if c.get("page")), None)
        if not leaf:
            continue
        start = next((x.get("id") for x in pages if x.get("id") != leaf.get("page")), None)
        if not start:
            continue
        cases.append({
            "kind": "toc",
            "name": f"目录面板 · 分组「{grp.get('title')}」能开能合，点「{leaf.get('title')}」能跳页",
            "page": start,
            "group": grp.get("title"),
            "leaf": leaf.get("title"),
            "target": leaf.get("page"),
        })
        break

    # 5. 升版不丢标注：往"上一版"的桶里塞一条，新版本打开时必须还在。
    # 这条守的是最容易复发的一处：存储键里带版本号，一升版就换个空桶，
    # 上一轮评审的意见整批消失，而且没有任何报错，只有人肉发现。
    cases.append({
        "kind": "migrate",
        "name": f"升到 {proto.get('meta', {}).get('version')} 后，旧版本桶里的标注还在",
        "seedId": "an-migrate-guard",
        "legacyKey": "iiot:%s:0.0.0-migrate" % (proto.get("meta", {}).get("product") or "proto"),
        "page": (pages[0].get("id") if pages else None),
    })

    # 6. 角色开关：四眼校验不能只写在契约的 actor 里。
    # R-06 切到一个"确实点不了这几条推进命令"的角色 → 按钮必须消失（不是置灰），
    #      且格子不能空着（空白等于既像"没做"又像"渲染挂了"）。
    # R-07 切回有权限的角色 → 按钮回来，且点得开承载层。
    # 两条要成对：只测藏不测回，"藏错了"和"藏对了"看起来一样。
    cases += role_cases(proto)
    # 7. R-08 默认态：一进来就是「全部角色（不限）」。
    # 8. R-09 引擎自保：绕过界面直接调 RD.action 也拦得住。
    cases += role_all_cases(proto)
    cases += bypass_cases(proto)
    cases += field_cases(proto)
    return cases


def field_cases(proto):
    """R-11 点字段定位 / R-12 不劫持输入与标注。

    一个页面一条用例，页内所有已绑定的渲染位在探针里循环点一遍：
    按位拆成 Python 用例会把 84 个渲染位变成 84 次浏览器跳页，
    budget 直接撞上限；页内循环既快，报错也能聚合。
    """
    # 条件是「这一位在 PRD 里有块」，不是「它绑定了主档」：
    # 条件筛选（关键词/日期区间/是否超期）没有业务字段，但同样有块、同样挂 data-field，
    # 用户点它一样期待跳过去。按「已绑定」筛会把它们漏掉，绿着但没测。
    sites = [s for s in field_sites.render_sites(proto) if not s["missing_key"]]
    by_page = {}
    for s in sites:
        by_page.setdefault(s["page_id"], []).append(s)

    cases = []
    for pid, grp in by_page.items():
        caps_by = {c.get("id"): c for c in (proto.get("capabilities") or [])}
        # 弹层挂在 owns 页的字典里，但按钮可能渲染在别页（越权渲染/双入口）；
        # 点击必须去"真正画了按钮"的那一页，否则入口找不到
        render_page = {}
        for pg in (proto.get("pages") or []):
            for nd in field_sites.walk_tree(pg.get("componentTree") or {}):
                pr = nd.get("props") or {}
                ids = [pr.get("capability")]
                ids += [a.get("capability") for a in (pr.get("actions") or []) if isinstance(a, dict)]
                cols = pr.get("columns")
                for c in (cols if isinstance(cols, list) else []):
                    if isinstance(c, dict):
                        ids += [a.get("capability") for a in (c.get("actions") or []) if isinstance(a, dict)]
                for cid in ids:
                    if cid and cid not in render_page:
                        render_page[cid] = pg.get("id")
        payload = [{
            "key": s["key"],
            "site": s["site_id"],
            "label": s["label"] or s["key"],
            "kind": s["kind"],
            "cap": s["cap_id"],
            "openPage": render_page.get(s["cap_id"]),
            "from": ((caps_by.get(s["cap_id"]) or {}).get("from") or [None])[0],
        } for s in grp]
        cases.append({
            "kind": "field",
            "name": "R-11 %s · %d 个渲染位点标签都能定位到字段块" % (pid, len(payload)),
            "page": pid,
            "sites": payload,
        })
        # R-12 挑一个带输入框的位置和一个有标签的位置：优先表单，其次筛选条
        typed = next((s for s in grp if s["kind"] in ("form", "filter")
                      and s["scope"] in ("in", "filter-field")
                      and s["raw"].get("type") not in ("upload", "readonly")
                      and not s["raw"].get("readonly")), None)
        labelled = next((s for s in grp if s["kind"] in ("form", "filter", "column", "desc")), None)
        if typed and labelled:
            cases.append({
                "kind": "fieldguard",
                "name": "R-12 %s · 字段点击不劫持输入、不劫持标注" % pid,
                "page": pid,
                "inputKey": typed["key"],
                "annotKey": labelled["key"],
                "annotSite": labelled["site_id"],
            })
    return cases


def _row_action_columns(proto, page):
    """这一页上每一列行内动作的 capability 列表（含"没有 capability"这个事实）。

    判"格子会不会全空"必须看整列，不能只看推进命令：列里只要还挂着一个不带
    capability 的「查看」，那个格子就永远有字，`无可用操作` 永远不该出现——
    拿推进命令算会把它误判成"该亮没亮"。
    """
    cols = []
    for n in walk(page.get("componentTree") or {}, []):
        props = n.get("props") if isinstance(n.get("props"), dict) else {}
        for col in (props.get("columns") or []):
            if not isinstance(col, dict) or col.get("type") != "action":
                continue
            if col.get("scope") != "row":
                continue        # 单据级操作列不按行判，格子永远不会因为角色而空
            acts = [a for a in (col.get("actions") or []) if isinstance(a, dict)]
            if acts:
                cols.append([a.get("capability") for a in acts])
    return cols


def role_cases(proto):
    """每条权限边界都出一条 R-06 + 一条 R-07。

    只测"藏得最多的那个角色"是不够的：5 个角色的台账切 1 次，
    等于 5 条边界里验了 1 条，剩下 4 条写错了也全绿。
    逐页 × 逐角色，隐藏集为空的角色跳过（它在这个页面没有边界可验）。
    """
    pages = proto.get("pages") or []
    caps = {c.get("id"): c for c in (proto.get("capabilities") or [])}
    actor_name = {a.get("id"): (a.get("name") or a.get("id")) for a in (proto.get("actors") or [])}
    out = []

    for p in pages:
        page_actors = (p.get("contract") or {}).get("actor") or []
        if len(page_actors) < 2:
            continue
        # sorted：rendered_caps 返回的是 set，不排序的话用例顺序每次都可能不一样
        adv = [caps[cid] for cid in sorted(rendered_caps(p))
               if cid in caps and caps[cid].get("to") and (caps[cid].get("actor") or [])]
        if not adv:
            continue
        for r in sorted(page_actors):
            hidden = [c for c in adv if r not in (c.get("actor") or [])]
            if not hidden:
                continue    # 这个角色在本页没有边界，不用造用例
            # 这一行里"一个动作都不剩"的情况真的会发生吗？条件是整列动作都带 capability、
            # 且都被这个角色滤光。真的会，就要求格子里出现「无可用操作」——
            # 空白的格子既像没做，也像渲染挂了。
            hide_ids = {h.get("id") for h in hidden}
            expect_none = False
            for col_caps in _row_action_columns(proto, p):
                if any(not cid for cid in col_caps):
                    continue                      # 列里有无权限动作（查看/详情），格子永远有字
                if col_caps and all(cid in hide_ids for cid in col_caps):
                    expect_none = True
                    break
            out.append({
                "kind": "role-hide",
                "name": "R-06 %s · 切到「%s」→ 看不到 %s（%d 条推进命令）" % (
                    p.get("title"), actor_name.get(r, r),
                    " / ".join(c.get("label") or c.get("name") or c.get("id") for c in hidden), len(hidden)),
                "page": p.get("id"),
                "role": r,
                "hide": [c.get("id") for c in hidden],
                "expectNone": expect_none,
            })

            # R-07 成对：换一个有权限的角色，同一批命令要回来，而且得点得动。
            # 不预定"点哪一条"：行级按钮的可用性跟着每一行的状态走，契约里的 from 是全局口径，
            # 硬指定一条会出现"切对了角色、但那一行状态不对"的假红。现场找一条启用态的。
            prove_role = None
            for c in hidden:
                for a in (c.get("actor") or []):
                    if a != r:
                        prove_role = a
                        break
                if prove_role:
                    break
            if not prove_role:
                continue
            show = [c for c in hidden if prove_role in (c.get("actor") or [])]
            out.append({
                "kind": "role-show",
                "name": "R-07 %s · 切到「%s」→ 这批命令回来，且点得动" % (
                    p.get("title"), actor_name.get(prove_role, prove_role)),
                "page": p.get("id"),
                "role": prove_role,
                "caps": [{
                    "id": c.get("id"),
                    "label": c.get("label") or c.get("name") or c.get("id"),
                    "kind": (c.get("ui") or {}).get("kind"),
                    "title": (c.get("ui") or {}).get("title") or c.get("name"),
                    "from": (c.get("from") or [None])[0],
                } for c in show],
            })
    return out


def _row_col_state_key(page, cap_id):
    """这条命令画在哪一列的行内动作里？返回那一列的 stateKey（没画在行内就返回 None）。

    R-10 拨状态的规则不同：行级按钮吃的是这一行 stateKey 的值，单据级才吃顶栏那个。
    拿主单状态去拨行级按钮，会出现"我明明拨到 from 了它还是灰的"这种假红。

    判据是列的 scope==row，不是"画在列里"：组件层是
    `rowState = col.scope === 'row' ? row[stateKey] : null`，
    没有 scope 的操作列（台账上的「审核」「导出」）吃的是单据状态。
    这里跟渲染层对齐，差一个字段就会把单据级按钮当行级按钮拨，拨不动还报红。
    """
    for n in walk(page.get("componentTree") or {}, []):
        props = n.get("props") if isinstance(n.get("props"), dict) else {}
        cols = props.get("columns")
        for col in (cols if isinstance(cols, list) else []):
            if not isinstance(col, dict) or col.get("type") != "action":
                continue
            if col.get("scope") != "row":
                continue
            if any(isinstance(a, dict) and a.get("capability") == cap_id for a in (col.get("actions") or [])):
                return col.get("stateKey") or "status"
    return None


def _row_level_caps(proto):
    """capId → 所在页面 id，只收"画在表格操作列里"的命令。

    行级命令和单据级命令吃的是两个状态：前者看这一行的 status，后者看 store.entityStatus。
    测 R-09 必须分开造，混着测就会出现"拨了单据状态、行状态没动"的假绿。
    """
    out = {}
    for p in proto.get("pages") or []:
        for n in walk(p.get("componentTree") or {}, []):
            props = n.get("props") if isinstance(n.get("props"), dict) else {}
            cols = props.get("columns")
            for col in (cols if isinstance(cols, list) else []):
                if not isinstance(col, dict) or col.get("type") != "action":
                    continue
                if col.get("scope") != "row":
                    continue      # 没有 scope:row 的操作列吃单据状态，不是行级
                for a in (col.get("actions") or []):
                    if isinstance(a, dict) and a.get("capability"):
                        out[a["capability"]] = p.get("id")
    return out


def role_all_cases(proto):
    """R-08：默认「全部角色（不限）」时，本页的推进命令必须全在、且都点得动。

    这条守的是"权限开关静默漂移"：默认值只要从「不限」改成某个具体角色，
    页面上一进来就少几条按钮，而 R-06/R-07 照样全绿——它们自己会切角色，
    切完看到的就是对的。所以 R-08 不看切换之后，只看一进来那一刻。
    """
    pages = proto.get("pages") or []
    caps = {c.get("id"): c for c in (proto.get("capabilities") or [])}
    actors = [a.get("id") for a in (proto.get("actors") or [])]
    actor_name = {a.get("id"): (a.get("name") or a.get("id")) for a in (proto.get("actors") or [])}
    label_of = {s.get("key"): s.get("label")
                for sm in (proto.get("stateMachines") or [])
                for s in (sm.get("states") or [])}
    out = []

    for p in pages:
        if len((p.get("contract") or {}).get("actor") or []) < 2:
            continue
        adv = [caps[cid] for cid in sorted(rendered_caps(p))
               if cid in caps and caps[cid].get("to") and (caps[cid].get("actor") or [])]
        if not adv:
            continue
        # 对拍用的探针命令：挑一条"actor 列表最窄"的，这样一定能找到一个真无权角色，
        # 否则 C 分支（有权限的角色反过来必须放行）退化成空断言。
        probe = min(adv, key=lambda c: len(c.get("actor") or []))
        wrong = next((a for a in actors if a not in (probe.get("actor") or [])), None)
        out.append({
            "kind": "role-all",
            "name": "R-08 %s · 默认「全部角色（不限）」→ %d 条推进命令全可见且可点" % (
                p.get("title"), len(adv)),
            "page": p.get("id"),
            "caps": [{
                "id": c.get("id"),
                "label": c.get("label") or c.get("name") or c.get("id"),
                "from": (c.get("from") or [None])[0],
                "fromLabel": label_of.get((c.get("from") or [None])[0]) or (c.get("from") or [None])[0],
                "rowLevel": bool(_row_col_state_key(p, c.get("id"))),
                "stateKey": _row_col_state_key(p, c.get("id")) or "status",
            } for c in adv],
            "probe": {
                "id": probe.get("id"),
                "state": (probe.get("from") or [None])[0],
                "wrongRole": wrong,
                "wrongName": actor_name.get(wrong, wrong),
            },
        })
    return out


def bypass_cases(proto):
    """R-09：绕过界面直接调 RD.action，角色和状态两半都要拦。

    这条不是"安全"（原型没有后端，拦不住谁），是保真：状态机的可达集被脚本扩大以后，
    导出的 mermaid 状态图就不再描述这台原型真实能走的路，业务方照着它评审会评错。
    所以断言只认一件事：**载体状态没变**。弹没弹 toast 不算数——toast 可以弹了却不返回。
    """
    pages = proto.get("pages") or []
    page_title = {p.get("id"): p.get("title") for p in pages}
    caps = {c.get("id"): c for c in (proto.get("capabilities") or [])}
    actors = [a.get("id") for a in (proto.get("actors") or [])]
    sms = {s.get("entity"): s for s in (proto.get("stateMachines") or [])}
    row_level = _row_level_caps(proto)
    out = []

    for cid in sorted(caps):
        c = caps[cid]
        ui = c.get("ui") or {}
        # 只测 inline：dialog/drawer 的推进发生在 submitLayer 里，action() 只负责开层，
        # 拿它断言"状态没变"会一直绿——那测的是开层，不是迁移闸门。
        if ui.get("kind") != "inline" or not c.get("to"):
            continue
        if not (c.get("actor") or []):
            continue
        # from == to 的自环：推进完状态不变，"该放行的能推进"这条正对照无从判断，
        # 只剩"没变"，而"没变"和"闸门坏了整个空转"长得一模一样。这种命令由 L2-94
        # 在契约层直接报错，R 层不给它发合格证，也不替它编一套断言。
        if c.get("to") in (c.get("from") or []):
            continue
        host = row_level.get(cid) or host_page(pages, cid)
        if not host:
            continue
        sm = sms.get(c.get("entity")) or {}
        label_of = {s.get("key"): s.get("label") for s in (sm.get("states") or [])}
        from_keys = [k for k in (c.get("from") or []) if k]
        wrong = next((a for a in actors if a not in (c.get("actor") or [])), None)
        if not wrong:
            continue
        # from 为空的创建命令只测角色那一半：它的 to 就是状态机的 initial，
        # 动作前后 entityStatus 恒等于 initial。"状态变了"恒假、"被设成 to"恒真，
        # 两个断言都是空的——判据不该为了凑覆盖率去断言恒真恒假的东西。
        # 创建命令的状态约束归 L2-77 的建单豁免，数据覆盖归 C-21，R-09 只管角色。
        create_only = not from_keys
        other = None
        if not create_only:
            other = next((s.get("key") for s in (sm.get("states") or [])
                          if s.get("key") not in from_keys), None)
            if not other:
                continue
        out.append({
            "kind": "bypass",
            "name": "R-09 %s · 绕过界面调 RD.action「%s」：%s" % (
                page_title.get(host), c.get("label") or c.get("name") or cid,
                "角色不对要拒，角色对要真执行" if create_only else "角色不对 / 状态不对都要拒"),
            "page": host,
            "cap": cid,
            "label": c.get("label") or c.get("name") or cid,
            "rowLevel": cid in row_level,
            "createOnly": create_only,
            "toLabel": label_of.get(c.get("to")) or c.get("to"),
            "fromKey": from_keys[0] if from_keys else None,
            "fromLabel": label_of.get(from_keys[0]) or from_keys[0] if from_keys else None,
            "wrongStateKey": other,
            "wrongStateLabel": label_of.get(other) or other,
            "wrongRole": wrong,
            "rightRole": (c.get("actor") or [])[0],
        })
    return out


PROBE = r"""(function () {
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
  function findClickable(text, cap) {
    // 有 data-cap 就按它找：按文字找按钮在"同名不同命令"时一定找错，
    // 而且改了文案就假红——那是在测文案，不是测按钮。
    var byCapAll = cap ? Array.prototype.slice.call(document.querySelectorAll('[data-cap="' + cap + '"]')) : [];
    if (byCapAll.length) {
      // 同一命令可能在每一行都有入口：优先取启用态的那个。
      // 全是禁用态时也返回它——点它给出的理由，比去点一个文字相同的顶栏按钮有价值。
      var byCapOn = byCapAll.filter(function (el) {
        return !el.classList.contains('is-off') && !el.classList.contains('is-disabled');
      });
      return byCapOn[0] || byCapAll[0];
    }
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
    // 文字一个都没匹配上（比如按钮文案在工具栏和在顶栏重名）时，
    // 回到 data-cap 上那个禁用态：点它给出的理由，比点错顶栏按钮更有价值
    return null;
  }
  function setRole(id) {
    // 走真实的顶栏下拉，不走 store 后门：后门能过只证明 store 能改，
    // 证明不了"用户切得动角色"。
    var sel = document.querySelector('[data-role-switch]');
    if (!sel) return false;
    sel.value = id;
    sel.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }
  function setStatus(id) {
    var sel = document.querySelector('[data-status-switch]');
    if (!sel) return false;
    sel.value = id;
    sel.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }
  // 点一下推进按钮会真的改数据。前面的用例把两行数据都推走了，后面的用例就"没有可执行的行"了，
  // 那是探针自己踩脏的地，不是原型的问题。所以每点完一次就还原。
  function snapRows() {
    var tree = (window.__RD_TEST__ && window.__RD_TEST__.renderTree) ? window.__RD_TEST__.renderTree() : null;
    var rows = [];
    (function w(n) {
      if (!n) return;
      var ps = n.props || {};
      if (Array.isArray(ps.data)) {
        ps.data.forEach(function (r) { if (r && typeof r === 'object') rows.push([r, r.status, r.state]); });
      }
      (n.children || []).forEach(w);
    })(tree);
    return { rows: rows, entity: (window.RD.state || {}).entityStatus };
  }
  function restoreRows(s) {
    if (!s) return;
    (s.rows || []).forEach(function (x) {
      if (!x[0]) return;
      if (x[1] !== undefined) x[0].status = x[1];
      if (x[2] !== undefined) x[0].state = x[2];
    });
    if (s.entity !== undefined) setStatus(s.entity);
  }
  async function run() {
    // 默认角色只能在"还没人动过开关"的时候看。角色用例跑完会把开关拨回「不限」，
    // 那时 store 已经被改过了，再去读就永远是「不限」——默认值改错了也测不出来。
    var bootSel = document.querySelector('[data-role-switch]');
    var BOOT_ROLE = bootSel ? bootSel.value : null;
    var BOOT_ROLE_TXT = (bootSel && bootSel.options[bootSel.selectedIndex] || {}).text || '';
    for (var i = 0; i < CASES.length; i++) {
      var c = CASES[i], ok = false, warn = false, detail = '';
      if (c.kind === 'migrate') {
        // 种子是在 app 脚本之前写进 localStorage 的（见 main 里插在 <body> 后），
        // 所以这里读到的是"迁移后的结果"，不是我们刚塞进去的那份。
        var S0 = (window.__RD_TEST__ || {}).store || {};
        var hit0 = (S0.annotations || []).filter(function (a) { return a.id === c.seedId; })[0];
        if (window.__SEED_FAIL__) {
          ok = false;
          detail = '浏览器不给 file:// 开 localStorage，这条判据没跑起来（不是原型的错，换 --chrome 或起本地服务再试）';
        } else if (hit0) {
          ok = true;
          detail = '旧桶 an-migrate-guard 已并入新版本，状态=' + hit0.status;
        } else {
          ok = false;
          detail = '旧版本桶里的标注没被搬过来：存储键前缀只认当前版本号，一升版就是空桶，上一轮意见全丢';
        }
        OUT.push({ name: c.name, ok: ok, warn: false, detail: detail });
        continue;
      }
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
      } else if (c.kind === 'toc') {
        var tocBtn = Array.prototype.slice.call(document.querySelectorAll('.tool-btn')).filter(function (b) {
          return txt(b) === '目录';
        })[0];
        if (!tocBtn) { detail = '顶栏没有「目录」按钮'; }
        else {
          tocBtn.click();
          var panel = await waitFor(function () { return document.querySelector('.overlay-left'); }, 1500);
          if (!panel) { detail = '点了目录没有打开页面目录面板'; }
          else {
            function tocRows() { return Array.prototype.slice.call(document.querySelectorAll('.toc-item')); }
            function rowByLabel(t) {
              return tocRows().filter(function (r) {
                var l = r.querySelector('.toc-label');
                return l && txt(l) === t;
              })[0];
            }
            var n0 = tocRows().length;
            var grp = rowByLabel(c.group);
            if (!grp) { detail = '面板里没有分组「' + c.group + '」（还是平铺的？）'; }
            else {
              grp.click();
              await sleep(280);
              var n1 = tocRows().length;
              var grp2 = rowByLabel(c.group);
              if (grp2) { grp2.click(); await sleep(280); }
              var n2 = tocRows().length;
              var leaf = rowByLabel(c.leaf);
              if (!leaf) { detail = '展开后找不到叶子「' + c.leaf + '」'; }
              else {
                leaf.click();
                await sleep(450);
                var jumped = (window.RD.state || {}).pageId === c.target;
                var shut = !document.querySelector('.overlay-left');
                ok = (n1 < n0) && (n2 === n0) && jumped;
                detail = '行数 ' + n0 + '→' + n1 + '→' + n2 +
                         '，点叶子跳页：' + (jumped ? '是' : '否（还在 ' + ((window.RD.state || {}).pageId) + '）') +
                         '，跳完面板已收起：' + (shut ? '是' : '否');
                if (!shut) {
                  var x = document.querySelector('.overlay-left .icon-btn');
                  if (x) x.click();
                  await sleep(200);
                }
              }
            }
          }
        }
      } else if (c.kind === 'role-hide') {
        if (!document.querySelector('[data-role-switch]')) { detail = '顶栏没有角色开关，切不了角色'; }
        else {
          setRole(c.role);
          await sleep(380);
          var left = (c.hide || []).filter(function (id) {
            return document.querySelector('[data-cap="' + id + '"]');
          });
          var blanks = Array.prototype.slice.call(document.querySelectorAll('.dt-cell.is-act')).filter(function (el) {
            return !txt(el);
          });
          // 整列都被这个角色滤光时，格子里必须是「无可用操作」：空白会被读成"没做"。
          var noneEls = Array.prototype.slice.call(document.querySelectorAll('.dt-none'));
          var noneTxt = noneEls.length ? txt(noneEls[0]) : '';
          var noneOk = !c.expectNone || (noneEls.length > 0 && !!noneTxt);
          // 工具栏也有同样的坑：动作全被权限滤光后剩一条空 bar，看起来像没做完
          var tbEl = document.querySelector('.toolbar');
          var tbBlank = tbEl && !txt(tbEl) ? 1 : 0;
          ok = left.length === 0 && blanks.length === 0 && !tbBlank && noneOk;
          detail = '仍显示：' + (left.join('、') || '无') +
                   '；操作格空白：' + blanks.length + ' 个' +
                   '；「无可用操作」：' + noneEls.length + ' 处' +
                   (noneEls.length ? '（文案「' + noneTxt + '」）' : '') +
                   '；工具栏空白：' + tbBlank + ' 个' +
                   ((blanks.length || tbBlank) ? '（空着会被读成"没做"，要写「无可用操作」）' : '') +
                   (c.expectNone && !noneOk ? '（本角色把整列动作滤光了，格子却还在留白）' : '');
          setRole('');
          await sleep(260);
        }
      } else if (c.kind === 'role-show') {
        if (!document.querySelector('[data-role-switch]')) { detail = '顶栏没有角色开关，切不了角色'; }
        else {
          setRole(c.role);
          await sleep(420);
          var meta = {};
          (c.caps || []).forEach(function (x) { meta[x.id] = x; });
          function collect() {
            var acc = [];
            Object.keys(meta).forEach(function (id) {
              Array.prototype.slice.call(document.querySelectorAll('[data-cap="' + id + '"]')).forEach(function (el) {
                acc.push(el);
              });
            });
            return acc;
          }
          function onOf(list) {
            return list.filter(function (el) {
              return !el.classList.contains('is-off') && !el.classList.contains('is-disabled');
            });
          }
          var allEls = collect();
          var cands = onOf(allEls);
          // 元素在、全灰着：先别记红。这多半是 mock 数据里没有落在 from 命中状态上的行，
          // 把单据状态拨到某条的 from 再试一次；仍不行记 WARN——数据巧合不许当成引擎缺陷。
          var retried = false;
          if (!cands.length && allEls.length) {
            var fTry = null;
            (c.caps || []).forEach(function (x) { if (!fTry && x.from) fTry = x.from; });
            if (fTry) { setStatus(fTry); await sleep(300); retried = true; allEls = collect(); cands = onOf(allEls); }
          }
          if (!cands.length) {
            if (!allEls.length) {
              detail = '该角色权限下本该出现的命令，一条都没有渲染出来（引擎问题，不是数据问题）';
            } else {
              warn = true;
              detail = '命令在 DOM 里但全部置灰：当前 mock 数据没有落在 from 命中状态上的行' +
                       (retried ? '（已拨到 from 再试，仍无可执行行）' : '');
            }
          } else {
            var elR = cands[0];
            var cid = elR.getAttribute('data-cap');
            var mm = meta[cid] || {};
            // 优先点有承载层的那一条：能一并验"看得见"和"点得开"
            var layered = cands.filter(function (el) {
              var k = (meta[el.getAttribute('data-cap')] || {}).kind;
              return k === 'dialog' || k === 'drawer';
            })[0];
            if (layered) { elR = layered; cid = elR.getAttribute('data-cap'); mm = meta[cid] || {}; }
            var snapR = snapRows();
            elR.click();
            if (mm.kind === 'dialog' || mm.kind === 'drawer') {
              var mR = await waitFor(mask, 1500);
              var LR = layer();
              if (!mR) {
                detail = '「' + (mm.label || cid) + '」点了没有弹层（' + (txt(document.querySelector('.toast')) || '无提示') + '）';
              } else {
                var kOk = LR && LR.classList.contains('layer-' + mm.kind);
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
                await sleep(250);
                ok = kOk && !mask();
                detail = '「' + (mm.label || cid) + '」已出现并点开 ' + (LR ? LR.className : '?') +
                         (!mask() ? ' / Esc 已关闭' : ' / Esc 关不掉');
              }
            } else {
              await sleep(300);
              var tR = txt(document.querySelector('.toast'));
              ok = true;
              detail = '「' + (mm.label || cid) + '」已出现并点得动' + (tR ? '（' + tR + '）' : '');
            }
          }
          restoreRows(snapR);
          await sleep(220);
          setRole('');
          await sleep(260);
        }
      } else if (c.kind === 'role-all') {
        var selAll = document.querySelector('[data-role-switch]');
        if (!selAll) { detail = '顶栏没有角色开关：默认「不限」这件事无从谈起'; }
        else {
          var defVal = selAll.value;
          var defTxt = (selAll.options[selAll.selectedIndex] || {}).text || '';
          var defOpt = Array.prototype.slice.call(selAll.options).filter(function (o) { return o.value === ''; })[0];
          setRole('');
          await sleep(420);
          function elsOf(id) { return Array.prototype.slice.call(document.querySelectorAll('[data-cap="' + id + '"]')); }
          function isOn(el) { return !el.classList.contains('is-off') && !el.classList.contains('is-disabled'); }
          function missing() { return (c.caps || []).filter(function (x) { return !elsOf(x.id).length; }); }
          function dead() {
            return (c.caps || []).filter(function (x) {
              var e = elsOf(x.id);
              return !e.length || !e.some(isOn);
            });
          }
          var missAll = missing(), deadAll = dead(), retriedAll = false;
          // 置灰可能只是"没有落在 from 上的行"，拨一次再判——这是数据巧合，不是引擎缺陷
          if (!missAll.length && deadAll.length) {
            var fstAll = (c.caps || []).filter(function (x) { return x.from && !x.rowLevel; })[0];
            if (fstAll) { setStatus(fstAll.from); await sleep(320); retriedAll = true; missAll = missing(); deadAll = dead(); }
          }
          // 置灰还要再分一次原因，和 R-10 同一个口径：数据里压根没有落在 from 上的行，
          // 那是 C-21 的活；状态能到位却仍然灰着，才是引擎的事。
          var treeA = (window.__RD_TEST__ && window.__RD_TEST__.renderTree) ? window.__RD_TEST__.renderTree() : null;
          var allRows = [];
          (function wA(n) {
            if (!n) return;
            var ps = n.props || {};
            if (Array.isArray(ps.data)) allRows = allRows.concat(ps.data);
            (n.children || []).forEach(wA);
          })(treeA);
          function deadCause(x) {
            if (!x.rowLevel) return 'engine';
            var hitA = allRows.some(function (r) {
              var v = r && r[x.stateKey];
              return v === x.from || v === x.fromLabel;
            });
            return hitA ? 'engine' : 'nodata';
          }
          var hardDead = deadAll.filter(function (x) { return deadCause(x) === 'engine'; });
          var softDead = deadAll.filter(function (x) { return deadCause(x) === 'nodata'; });
          // 合流断言：第三参缺省 与 顶栏「不限」传的空串必须落到同一个分支。
          // 再拿一个真无权角色对拍——否则"两边都放行"也能过，测的就不是合流是真空。
          var pr = c.probe || {};
          var pcA = pr.id ? window.RD.can(pr.id, pr.state || null) : null;
          var pcB = pr.id ? window.RD.can(pr.id, pr.state || null, '') : null;
          var pcC = (pr.id && pr.wrongRole) ? window.RD.can(pr.id, pr.state || null, pr.wrongRole) : null;
          var merged = !pcA || ((!!pcA.ok === !!pcB.ok) && (pcA.denied || '') === (pcB.denied || ''));
          var deniedOk = !pcC || (pcC.ok === false && pcC.denied === 'role');
          // 默认值看的是"一进页面那一刻"，不是现在——现在已经被前面的用例拨过了
          var bootOk = (BOOT_ROLE === '');
          ok = bootOk && defVal === '' && !!defOpt && !missAll.length && !hardDead.length && merged && deniedOk;
          // 数据缺行不记红，但也不能假装没看见：整条降成 WARN，把结论交给 C-21。
          warn = ok && softDead.length > 0;
          detail = '启动时选中「' + (BOOT_ROLE_TXT || '(空)') + '」' + (bootOk ? '' : '（默认不是不限：会静默藏掉一批按钮）') +
            '；此刻「' + (defTxt || '(空)') + '」' +
            '；未渲染：' + (missAll.map(function (x) { return x.label; }).join('、') || '无') +
            '；置灰（引擎）：' + (hardDead.map(function (x) { return x.label; }).join('、') || '无') +
            '；置灰（数据里没有落在 from 上的行，交 C-21）：' + (softDead.map(function (x) { return x.label; }).join('、') || '无') +
            (retriedAll ? '（已拨到 from 再试）' : '') +
            '；can(缺省第三参)=' + (pcA ? (pcA.ok ? '放行' : '拒/' + (pcA.denied || '?')) : '无') +
            '，can("")=' + (pcB ? (pcB.ok ? '放行' : '拒/' + (pcB.denied || '?')) : '无') +
            '，can("' + (pr.wrongName || pr.wrongRole || '-') + '")=' +
              (pcC ? (pcC.ok ? '放行（本该拒）' : '拒/' + (pcC.denied || '?')) : '未测') +
            (merged ? '；前两者同一条分支' : '；前两者不一致（缺省绕过了开关）');
        }
      } else if (c.kind === 'bypass') {
        // 绕过界面：直接调 window.RD.action。探针不点按钮，因为按钮本身已经被藏了，
        // 能点到的按钮证明不了"脚本绕过界面时还拦不拦"。
        var rowNode = null;
        if (c.rowLevel) {
          var treeR = (window.__RD_TEST__ && window.__RD_TEST__.renderTree) ? window.__RD_TEST__.renderTree() : null;
          (function findRows(n) {
            if (!n || rowNode) return;
            var ps = n.props || {};
            var cols = Array.isArray(ps.columns) ? ps.columns : [];
            var hitCol = cols.filter(function (cc) {
              return ((cc && cc.actions) || []).some(function (a) { return a.capability === c.cap; });
            })[0];
            if (hitCol && Array.isArray(ps.data)) { rowNode = n; return; }
            (n.children || []).forEach(findRows);
          })(treeR);
        }
        var rowsB = (rowNode && rowNode.props.data) || [];
        function isFrom(s) { return s === c.fromLabel || s === c.fromKey; }
        var okRow = c.rowLevel ? rowsB.filter(function (r) { return isFrom(r.status || r.state); })[0] : null;
        var badRow = c.rowLevel ? rowsB.filter(function (r) { return !isFrom(r.status || r.state); })[0] : null;
        function statusOf(rowObj) {
          return c.rowLevel ? (rowObj ? (rowObj.status || rowObj.state) : null) : (window.RD.state || {}).entityStatus;
        }
        if (c.rowLevel && !okRow && !c.createOnly) {
          // 没有一条行停在 from 上：角色分支没法"只让角色不对"地造出来，
          // 记 WARN。数据缺失不是引擎缺陷，报红只会训练人忽略红灯。
          warn = true;
          detail = 'mock 数据里没有停在「' + c.fromLabel + '」的行（共 ' + rowsB.length +
                   ' 行），角色分支造不出来';
        } else {
          // ① 角色不对：先保证状态是对的，否则拦下来的是状态不是角色
          setRole(c.wrongRole);
          await sleep(400);
          if (!c.rowLevel && c.fromKey) { setStatus(c.fromKey); await sleep(300); }
          var b1 = statusOf(okRow);
          var why1 = window.RD.can(c.cap, c.rowLevel ? b1 : null, c.wrongRole);
          window.RD.action('probe', c.label, okRow, c.cap);
          await sleep(280);
          var a1 = statusOf(okRow);
          var roleStop = (b1 === a1);
          var roleCause = !!(why1 && why1.ok === false && why1.denied === 'role');

          // ② 状态不对：角色换对的，只让状态不匹配
          if (c.createOnly) {
            // 创建命令（from=[]，to 就是 initial）没有"状态不对"这一半：
            // 动作前后 entityStatus 恒等于 initial，"变了"恒假、"被设成 to"恒真。
            // 所以只测角色，再加一条"角色对时真的执行了"——用 toast 判，不用状态值。
            setRole(c.rightRole);
            await sleep(380);
            window.RD.action('probe', c.label, null, c.cap);
            await sleep(320);
            var tRan = txt(document.querySelector('.toast'));
            var ran = !!tRan && (tRan.indexOf('已完成') >= 0 || tRan.indexOf(c.label) >= 0);
            ok = roleStop && roleCause && ran;
            detail = '角色「' + c.wrongRole + '」→ ' + (roleStop ? '没变' : '变了 ' + b1 + '→' + a1) +
                     (roleCause ? '（判定理由是角色）' : '（理由不是角色）') +
                     '；角色「' + c.rightRole + '」调用后 toast=' + (tRan || '无') +
                     (ran ? '，确实执行了' : '，没有执行痕迹') +
                     '（创建命令只测角色：它的 to 就是 initial，状态断言恒真恒假）';
            setRole('');
            await sleep(240);
          } else {
          setRole(c.rightRole);
          await sleep(380);
          if (!c.rowLevel) { setStatus(c.wrongStateKey); await sleep(280); }
          var b2 = statusOf(badRow);
          var why2 = window.RD.can(c.cap, c.rowLevel ? b2 : null, c.rightRole);
          window.RD.action('probe', c.label, badRow, c.cap);
          await sleep(280);
          var a2 = statusOf(badRow);
          var stateStop = (b2 === a2);
          var stateCause = !!(why2 && why2.ok === false && why2.denied === 'state');

          // ③ 正对照：角色对 + 状态对时必须真推进，否则前两步的"没变"是空转
          if (!c.rowLevel) { setStatus(c.fromKey); await sleep(280); }
          var b3 = statusOf(okRow);
          window.RD.action('probe', c.label, okRow, c.cap);
          await sleep(300);
          var a3 = statusOf(okRow);
          var alive = (a3 !== b3) && (!c.rowLevel || a3 === c.toLabel);
          // 还原：探针不留痕，后面的用例还得靠这行数据
          if (c.rowLevel && okRow) { okRow.status = b3; }
          else { setStatus(c.fromKey); }
          await sleep(260);
          ok = roleStop && roleCause && stateStop && stateCause && alive;
          detail = '角色「' + c.wrongRole + '」+状态「' + b1 + '」→ ' + (roleStop ? '没变' : '变了 ' + b1 + '→' + a1) +
                   (roleCause ? '（判定理由是角色）' : '（理由不是角色，可能顺带被状态拦下）') +
                   '；角色「' + c.rightRole + '」+状态「' + b2 + '」→ ' + (stateStop ? '没变' : '变了 ' + b2 + '→' + a2) +
                   (stateCause ? '（判定理由是状态）' : '（理由不是状态）') +
                   '；正对照 ' + b3 + '→' + a3 + (alive ? ' 能推进' : ' 推不动（闸门把该放行的也拦了）');
          setRole('');
          await sleep(240);
          }
        }
      } else if (c.kind === 'annot') {
        // 评审里最常见的动作是「开着弹框顺手圈一个字段」。如果弹层里的元素没有锚点，
        // 这条意见只能笼统写在整页上，落点说不清。
        // 但打开弹层这件事同样受数据制约：数据里没有落在 from 上的行，弹层就开不出来，
        // 那是 C-21 的活。这里也降 WARN，不然同一根因会在 R-10 之外再红一次。
        if (c.from && !c.rowLevel) { setStatus(c.from); await sleep(240); }
        var abEl = findClickable(c.text, c.cap);
        var offAb = abEl && (abEl.classList.contains('is-off') || abEl.classList.contains('is-disabled'));
        if (!abEl) { ok = false; detail = '找不到命令入口「' + c.text + '」'; }
        else if (offAb) {
          var treeN = (window.__RD_TEST__ && window.__RD_TEST__.renderTree) ? window.__RD_TEST__.renderTree() : null;
          var rowsN = [];
          (function wN(n) {
            if (!n) return;
            var ps = n.props || {};
            if (Array.isArray(ps.data)) rowsN = rowsN.concat(ps.data);
            (n.children || []).forEach(wN);
          })(treeN);
          var hitN = rowsN.some(function (r) {
            var v = r && r[c.stateKey];
            return v === c.from || v === c.fromLabel;
          });
          if (!hitN) {
            warn = true;
            detail = '入口全灰，mock 数据里没有一行落在「' + (c.fromLabel || c.from) +
                     '」上，弹层开不出来，标注这条没跑（交 C-21）';
          } else {
            ok = false;
            detail = '状态已到位入口仍全灰，弹层打不开，标注这条没跑';
          }
        }
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
                await sleep(200);
                var n1 = S ? S.annotations.length : -1;
                var last = S && n1 ? S.annotations[n1 - 1] : {};
                var carrier = (last && last.target && last.target.carrier) || '?';
                // 别用坐标猜"是不是在弹层上"：窗口宽不同，阈值就变了。
                // 直接看 pin 落点是否落在 .layer 的矩形内，再核对标注记的载体。
                // 固定 sleep 会偶发假红（保存后 pin 要等一帧重算），所以重试到成立或超时。
                var L0 = layer();
                var lr = L0 ? L0.getBoundingClientRect() : { left: 0, right: 0, top: 0, bottom: 0 };
                // pin 的 left/top 是相对 .annot-layer 的，而弹层矩形是视口坐标：
                // 标注层自己有 top 偏移（顶栏高度），不补这个偏移就是拿两套坐标系比大小。
                var AL0 = document.querySelector('.annot-layer');
                var ar0 = AL0 ? AL0.getBoundingClientRect() : { left: 0, top: 0 };
                function pinOnLayer() {
                  return Array.prototype.slice.call(document.querySelectorAll('.annot-pin')).some(function (p) {
                    var x = ar0.left + parseFloat(p.style.left);
                    var y = ar0.top + parseFloat(p.style.top);
                    return x >= lr.left - 6 && x <= lr.right + 6 && y >= lr.top - 6 && y <= lr.bottom + 6;
                  });
                }
                var onLayer = pinOnLayer();
                for (var t = 0; t < 8 && !onLayer; t++) {
                  await sleep(150);
                  onLayer = pinOnLayer();
                }
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
      } else if (c.kind === 'field') {
        // R-11：本页每个已绑定的渲染位，点它的标签都要定位到 field-{page}-{key} 块
        var S1 = (window.__RD_TEST__ || {}).store || {};
        var miss = [];
        for (var si = 0; si < c.sites.length; si++) {
          var sf = c.sites[si];
          if (sf.cap) {
            if (sf.openPage && sf.openPage !== c.page) {
              window.RD.goto(sf.openPage, '探针-入口页');
              await sleep(420);
            }
            var ent = findClickable('', sf.cap);
            if (!ent) { miss.push(sf.key + '：找不到命令入口'); continue; }
            if (ent.classList.contains('is-off') || ent.classList.contains('is-disabled')) {
              // 行级命令的可点性跟状态走；先把状态拨到这条命令的 from，再重取入口
              if (sf.from) { setStatus(sf.from); await sleep(300); }
              ent = findClickable('', sf.cap);
              if (!ent || ent.classList.contains('is-off') || ent.classList.contains('is-disabled')) {
                miss.push(sf.key + '：命令入口置灰（from=' + (sf.from || '未声明') + '）'); continue;
              }
            }
            ent.click();
            if (!await waitFor(mask, 1200)) { miss.push(sf.key + '：弹层打不开'); continue; }
          }
          var el1 = document.querySelector('[data-field="' + sf.key + '"][data-site="' + sf.site + '"]');
          if (!el1) { miss.push(sf.key + '：找不到 [data-field][data-site]（标识缺失）'); }
          else if (el1.getAttribute('data-page') !== c.page) {
            miss.push(sf.key + '：data-page=' + el1.getAttribute('data-page'));
          } else {
            var lab1 = el1.querySelector('.field-label, .form-label, .desc-k, .ff-label') ||
                       (el1.classList.contains('dt-cell') ? el1 : null);
            if (!lab1) { miss.push(sf.key + '：没有可点标签'); }
            else {
              lab1.click();
              await sleep(300);
              var id1 = 'field-' + c.page + '-' + sf.site + '-' + sf.key;
              var blk = document.getElementById(id1);
              if (!S1.showPrd || S1.prdTab !== 'page') { miss.push(sf.key + '：没打开 PRD 面板'); }
              else if (!blk) { miss.push(sf.key + '：目标块 ' + id1 + ' 不存在'); }
              else if (txt(blk).indexOf(sf.label) < 0) { miss.push(sf.key + '：块里没有「' + sf.label + '」'); }
              else if (txt(blk).indexOf(sf.site) < 0) { miss.push(sf.key + '：块里没写位置 ' + sf.site); }
              else if (!blk.classList.contains('is-flash')) { miss.push(sf.key + '：没高亮'); }
              S1.showPrd = false;
              await sleep(90);
            }
          }
          if (sf.cap) {
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
            await sleep(160);
          }
        }
        ok = miss.length === 0;
        detail = ok ? (c.sites.length + ' 个渲染位全部定位成功')
                    : (miss.length + ' 个失败：' + miss.slice(0, 6).join('；'));
      } else if (c.kind === 'fieldguard') {
        // R-12：输入不被劫持 / 标注优先级 / 关掉标注后恢复
        var S2 = (window.__RD_TEST__ || {}).store || {};
        var t1 = false, t2 = false, t3 = false, why2 = [];
        var inp = document.querySelector('[data-field="' + c.inputKey + '"] input, [data-field="' + c.inputKey + '"] textarea, [data-field="' + c.inputKey + '"] select');
        if (!inp) why2.push('找不到输入控件');
        else {
          S2.showPrd = false;
          var typedVal;
          if (inp.tagName === 'SELECT') {
            typedVal = (inp.options[1] || inp.options[0] || {}).value || inp.value;
            inp.value = typedVal;
            inp.dispatchEvent(new Event('change', { bubbles: true }));
          } else {
            typedVal = '涂布辊划痕';
            inp.focus(); inp.value = typedVal;
            inp.dispatchEvent(new Event('input', { bubbles: true }));
          }
          await sleep(150);
          t1 = (inp.value === typedVal) && !S2.showPrd;
          if (!t1) why2.push('输入/选择被字段点击劫持');
        }
        var host2 = document.querySelector('[data-field="' + c.annotKey + '"]');
        var lab2 = host2 ? (host2.querySelector('.field-label, .form-label, .desc-k, .ff-label') ||
                            (host2.classList.contains('dt-cell') ? host2 : null)) : null;
        if (!lab2) why2.push('找不到可点标签');
        else {
          S2.annotMode = true;
          await sleep(120);
          var r2 = lab2.getBoundingClientRect();
          lab2.dispatchEvent(new MouseEvent('click', {
            bubbles: true, clientX: r2.left + r2.width / 2, clientY: r2.top + r2.height / 2
          }));
          await sleep(280);
          t2 = !!document.querySelector('.annot-pop') && !S2.showPrd;
          if (!t2) why2.push('标注模式优先被破坏：点字段没弹标注框');
          S2.popover = null;
          S2.annotMode = false;
          await sleep(160);
          lab2.click();
          await sleep(280);
          t3 = !!S2.showPrd && !!document.getElementById('field-' + c.page + '-' + c.annotSite + '-' + c.annotKey);
          if (!t3) why2.push('关掉标注后点同一处没能打开字典');
          S2.showPrd = false;
        }
        ok = t1 && t2 && t3;
        detail = ok ? '输入不劫持 / 标注优先 / 关标注后定位恢复'
                    : why2.join('；');
      } else {

        // 这条用例问的是"契约说有的入口，点得开吗"，但点不开有两种原因：
        // ① 承载层没实现；② mock 数据里没有能触发的行。它自己分不清这两者，
        // 硬让它报红就是让它替数据层背锅（数据的事归 C-21）。
        // 所以只有"入口压根不在 DOM"和"状态已经到位了仍点不开"记红，
        // 数据里压根没有落在 from 上的行 → WARN，把判断权交回数据层。
        setRole('');   // 先回「不限」：默认态下才谈得上"入口在不在"
        await sleep(300);
        function capEls() {
          return c.cap ? Array.prototype.slice.call(document.querySelectorAll('[data-cap="' + c.cap + '"]')) : [];
        }
        function capOn() {
          return capEls().filter(function (el) {
            return !el.classList.contains('is-off') && !el.classList.contains('is-disabled');
          });
        }
        var els0 = capEls();
        var on0 = capOn();
        var reach = '';
        if (on0.length) {
          reach = 'direct';
        } else if (els0.length) {
          if (c.rowLevel) {
            // 行级：看这一列 stateKey 的实际取值里，有没有落在 from 上的。
            // 不能拿主单状态拨——行级按钮吃的是这一行的状态。
            var treeC = (window.__RD_TEST__ && window.__RD_TEST__.renderTree) ? window.__RD_TEST__.renderTree() : null;
            var rowsC = [];
            (function w(n) {
              if (!n) return;
              var ps = n.props || {};
              if (Array.isArray(ps.data)) rowsC = rowsC.concat(ps.data);
              (n.children || []).forEach(w);
            })(treeC);
            var hitRow = rowsC.filter(function (r) {
              var v = r && r[c.stateKey];
              return v === c.from || v === c.fromLabel;
            })[0];
            reach = hitRow ? 'blocked' : 'nodata';
          } else if (c.from) {
            setStatus(c.from);
            await sleep(320);
            reach = capOn().length ? 'retried' : 'blocked';
          } else {
            reach = 'blocked';
          }
        }

        if (!els0.length) {
          ok = false;
          detail = '默认「不限角色」下这条命令没有渲染出任何入口（' + (c.cap || '无 data-cap') +
                   '）：契约声明了入口，页面上没有';
        } else if (reach === 'nodata') {
          warn = true;
          detail = '入口在、但全部置灰，且 mock 数据里没有一行落在「' + (c.fromLabel || c.from) +
                   '」上（该列状态字段 ' + c.stateKey + '）：分不清是没实现还是没数据，交给 C-21 判';
        } else if (reach === 'blocked') {
          ok = false;
          detail = '状态已到位（' + (c.rowLevel ? '有行停在「' + (c.fromLabel || c.from) + '」' : '已拨到「' + (c.fromLabel || c.from) + '」') +
                   '）入口仍全灰：点了只会弹理由，承载层打不开';
        } else {
          var el = capOn()[0];
          el.click();
          var m = await waitFor(mask, 1500);
          if (!m) {
            // 期间列表重渲染会把节点换掉，点了个已经脱离文档的旧节点就等于没点。
            var el2 = capOn()[0];
            if (el2 && el2 !== el) { await sleep(150); el2.click(); m = await waitFor(mask, 1500); }
          }
          if (!m) {
            var el3 = capOn()[0];
            if (el3) { await sleep(150); el3.click(); m = await waitFor(mask, 1500); }
          }
          var L = layer();
          var body = L ? L.querySelector('.layer-body') : null;
          var shellEmpty = L ? (!body || !body.children.length) : true;
          if (!m) {
            ok = false;
            detail = '入口是可点的，点了却没有承载层（' + (txt(document.querySelector('.toast')) || '无提示') + '）';
          } else {
            var kindOk = L && L.classList.contains('layer-' + c.expectKind);
            var tbOk = topbarUsable();
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
            await sleep(250);
            var closed = !mask();
            ok = kindOk && closed && tbOk && !shellEmpty;
            detail = (L ? L.className : '?') + (closed ? ' / Esc 已关闭' : ' / Esc 关不掉') +
              (tbOk ? ' / 顶栏可点' : ' / 遮罩盖住了顶部工具条（标注、审核、导出点不到）') +
              (shellEmpty ? ' / 承载层是空壳（正文什么都没有）' : '') +
              (reach === 'retried' ? ' / 拨到「' + (c.fromLabel || c.from) + '」后才可点' : '');
          }
        }
      }
      OUT.push({ name: c.name, ok: ok, warn: warn, detail: detail });
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
    ap.add_argument("--budget", type=int, default=None,
                    help="虚拟时间预算(ms)。不给就按用例数自动算，别让使用者记公式")
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

    # 预算跟着用例数走，不写成"用例多了记得调 --budget"的规矩：
    # 那条规矩只有写它的人记得，下一个人只会看到一片假失败然后开始怀疑引擎。
    # 单条用例最坏约 2~3s 虚拟时间（跳页 450ms + 三轮拨状态与重渲染），按 6s 留余量。
    # 上限 300s：--virtual-time-budget 是虚拟时钟，撞到上限说明页面里有东西一直排任务，
    # 那不是"用例太多"，加钱（加预算）解决不了，得去查那个死循环。
    # R-11 会逐个渲染位点标签（弹层还要先切到按钮真实所在页），
    # 只按用例数估会低估虚拟时间，最后一段没跑完就被截断、报"没跑起来"
    field_sites_n = sum(len(c.get("sites") or []) for c in cases if c.get("kind") == "field")
    budget = args.budget or min(540000, max(60000, len(cases) * 6000 + field_sites_n * 1200))

    # 升版守卫的种子必须在 app 脚本跑起来之前落到 localStorage，
    # 所以插在 <body> 之后，而不是跟探针一起塞在 </body> 前。
    mig = next((c for c in cases if c["kind"] == "migrate"), None)
    if mig and mig.get("page"):
        payload = {"annotations": [{
            "id": mig["seedId"],
            "pageId": mig["page"],
            "nodeId": "n-root",
            "status": "open",
            "text": "升版守卫：这条来自上一版的存储桶",
            "createdAt": "2026-01-01T00:00:00",
            "target": {"pageTitle": "", "nodeLabel": "页面", "carrier": "page", "capId": None},
        }]}
        # 先清空这个产品的所有桶：上一次探针点过的状态会 persist 回来，
        # 不清就会出现"同样的输入、这次红下次绿"的假信号。
        prefix = "iiot:%s:" % (proto.get("meta", {}).get("product") or "proto")
        seed = ("<script>try{"
                "var __p=%s,__kill=[];"
                "for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);"
                "if(k&&k.indexOf(__p)===0)__kill.push(k);}"
                "__kill.forEach(function(k){localStorage.removeItem(k);});"
                "localStorage.setItem(%s, JSON.stringify(%s));"
                "}catch(e){window.__SEED_FAIL__=1;}</script>"
                % (json.dumps(prefix, ensure_ascii=False),
                   json.dumps(mig["legacyKey"], ensure_ascii=False),
                   json.dumps(payload, ensure_ascii=False)))
        b = doc.find("<body")
        if b >= 0:
            i = doc.find(">", b) + 1
            doc = doc[:i] + seed + doc[i:]

    inject = ("<script>window.__CASES__=" + json.dumps(cases, ensure_ascii=False) +
              ";</script><script>" + PROBE + "</script>")
    idx = doc.rfind("</body>")
    doc = doc[:idx] + inject + doc[idx:]

    tmp = os.path.join(tempfile.gettempdir(), "iiot-interact.html")
    open(tmp, "w", encoding="utf-8").write(doc)

    cmd = [chrome, "--headless=old", "--disable-gpu", "--no-sandbox",
           "--virtual-time-budget=%d" % budget, "--dump-dom", "file://" + tmp]
    dom = subprocess.run(cmd, capture_output=True, text=True).stdout

    k = dom.rfind('<pre id="INTERACT_RESULT">')
    if k < 0:
        print("实测没有跑起来（页面可能报错），请先用浏览器打开确认")
        return 2
    s = dom.find(">", k) + 1
    e = dom.find("</pre>", s)
    items = json.loads(htmllib.unescape(dom[s:e]))

    print("可点击性实测：%s" % os.path.basename(args.proto))
    # 预算写死在日志里，别让人反推：真卡死时要一眼分清"预算算多了"还是"页面挂了"
    print("budget: %ds (%d cases × 6s%s)" %
          (budget // 1000, len(cases), "，手动指定" if args.budget else "，自动算，--budget 可覆盖"))
    print("-" * 66)
    bad = 0
    warned = 0
    for it in items:
        if it.get("warn"):
            # 数据巧合不算引擎缺陷：mock 里没有落在 from 上的行，报红只会训练人忽略红灯
            warned += 1
            print("[WARN ] %s  —— %s" % (it["name"], it["detail"]))
        elif it["ok"]:
            # 角色开关这两条过没过，光看名字看不出来"藏了几条、点开的是哪条"，
            # 所以 OK 也把细节打出来——这两条最容易"绿得可疑"。
            if it["name"].startswith("R-0") and it.get("detail"):
                print("[OK   ] %s  —— %s" % (it["name"], it["detail"]))
            else:
                print("[OK   ] %s" % it["name"])
        else:
            bad += 1
            print("[FAIL ] %s  —— %s" % (it["name"], it["detail"]))
    print("-" * 66)
    print("结果：%d 项，通过 %d，警告 %d，失败 %d  %s" %
          (len(items), len(items) - bad - warned, warned, bad, "PASS" if bad == 0 else "FAIL"))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
