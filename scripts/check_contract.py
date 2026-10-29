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
            if ix.get("do") in ("navigate", "openDrawer", "openModal") and tgt and tgt not in page_ids:
                add(E, "L2-19", f"页面 {pid} 的交互 {ix.get('id')} 跳转到不存在的页面 {tgt}")

    # ---------- L2 D. 命令策略 ----------
    owns = {}
    for p in pages:
        for cid in ((p.get("contract") or {}).get("owns") or []):
            if cid not in cap_ids:
                add(E, "L2-20", f"页面 {p.get('id')} 的 contract.owns 引用了不存在的命令 {cid}")
            if cid in owns:
                add(E, "L2-21", f"命令 {cid} 被 {owns[cid]} 与 {p.get('id')} 同时 owns（一条命令只能有一个主页面）")
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
